"""Tests for the intake filter: the policy, and the proxy that carries it.

The policy tests assert on request bodies, because the request body *is* the
cache key — a policy that produced the right decision and the wrong bytes would
be worse than no policy at all. The proxy tests run a real server against a stub
upstream, because the two things most likely to break a session (streaming, and
credentials) cannot be checked any other way.
"""

from __future__ import annotations

import json
import threading
import time
import typing
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from winnow.filter import DEFAULT_MIN_BYTES, Plan, apply, pointer, rule_for
from winnow.proxy import Config, Stats, _Handler, _rewrite

BIG = "x" * (DEFAULT_MIN_BYTES + 100)
SMALL = "y" * 10


def use(uid: str, name: str, tool_input: dict) -> dict:
    return {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": uid, "name": name, "input": tool_input}],
    }


def res(uid: str, content=BIG, *, is_error: bool = False, cache: bool = False) -> dict:
    block = {
        "type": "tool_result",
        "tool_use_id": uid,
        "content": content,
        "is_error": is_error,
    }
    if cache:
        block["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
    return {"role": "user", "content": [block]}


def body(*messages: dict) -> dict:
    return {"model": "claude-opus-5", "max_tokens": 100, "messages": list(messages)}


def turn(uid: str, name: str, tool_input: dict, **kw) -> list[dict]:
    return [use(uid, name, tool_input), res(uid, **kw)]


def results_of(request: dict) -> list[dict]:
    return [
        block
        for message in request["messages"]
        for block in message["content"]
        if block.get("type") == "tool_result"
    ]


def breakpoints_of(request: dict) -> list[tuple[int, int]]:
    return [
        (m, b)
        for m, message in enumerate(request["messages"])
        for b, block in enumerate(message["content"])
        if isinstance(block, dict) and "cache_control" in block
    ]


# ─── Which rules the filter is allowed to decide ─────────────────────────────


@pytest.mark.parametrize(
    "name,tool_input,expected",
    [
        ("Glob", {"pattern": "*.py"}, "C1"),
        ("LS", {"path": "/r"}, "C1"),
        ("Grep", {"output_mode": "files_with_matches"}, "C1"),
        ("Grep", {"output_mode": "content"}, None),
        ("Bash", {"command": "npm run test"}, "C3"),
        ("Bash", {"command": "git status"}, "B2"),
        ("Bash", {"command": "python train.py"}, None),
        ("Read", {"file_path": "/r/x.py"}, None),
        ("Edit", {"file_path": "/r/x.py"}, None),
    ],
)
def test_only_the_hindsight_free_rules_fire(name, tool_input, expected):
    """C2, B1 and A1 each need to see the future of the conversation. A filter
    that used them would give a different answer on two requests over the same
    prefix, which is the one thing a cache-stable policy may not do."""
    assert rule_for(name, tool_input, False) == expected


def test_an_error_result_is_never_dropped(tmp_path):
    assert rule_for("Bash", {"command": "npm run test"}, True) is None


# ─── The policy ──────────────────────────────────────────────────────────────


def test_the_newest_candidate_survives_and_the_older_one_goes():
    request = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    _, plan = apply(request)
    kept, dropped = results_of(request)[1], results_of(request)[0]
    assert dropped["content"].startswith("[winnow:")
    assert kept["content"] == BIG
    assert plan.bytes_dropped == len(BIG)
    assert [d["rule"] for d in plan.dropped] == ["B2"]


def test_the_newest_candidate_is_pushed_out_of_the_cached_prefix():
    """The whole mechanism: the bytes the model still needs are sent, but after
    the last breakpoint, so the API never writes them to cache."""
    request = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}, cache=True))
    _, plan = apply(request)
    assert plan.breakpoint_moved
    newest = (len(request["messages"]) - 1, 0)
    assert newest not in breakpoints_of(request)
    assert all(position < newest for position in breakpoints_of(request))


def test_a_result_no_rule_claims_keeps_its_breakpoint():
    """No candidate, no intervention. A filter that moved the breakpoint on every
    request would cost 0.9x on content it never intended to drop."""
    request = body(*turn("a", "Bash", {"command": "python train.py"}, cache=True))
    before = breakpoints_of(request)
    _, plan = apply(request)
    assert not plan.changed
    assert breakpoints_of(request) == before


def test_a_small_result_is_left_alone():
    request = body(*turn("a", "Bash", {"command": "ls -la"}, content=SMALL),
                   *turn("b", "Bash", {"command": "ls /tmp"}, content=SMALL))
    _, plan = apply(request)
    assert plan.dropped == []
    assert results_of(request)[0]["content"] == SMALL


def test_pairing_is_preserved_because_content_is_replaced_not_removed():
    """SPEC §4 G5. The API requires every tool_use to be answered, so a dropped
    result is substituted, never deleted."""
    request = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    apply(request)
    uses = sum(1 for m in request["messages"] for b in m["content"]
               if b.get("type") == "tool_use")
    assert len(results_of(request)) == uses == 2
    assert all("tool_use_id" in r for r in results_of(request))


def test_the_policy_is_idempotent_so_the_prefix_never_flaps():
    """Running twice over the same conversation must produce the same bytes, or
    the cache is destroyed by the thing meant to protect it."""
    first = body(*turn("a", "Bash", {"command": "ls -la"}),
                 *turn("b", "Bash", {"command": "git diff"}))
    apply(first)
    once = json.dumps(first, sort_keys=True)
    apply(first)
    assert json.dumps(first, sort_keys=True) == once


def test_a_pointer_is_never_re_dropped_or_re_counted():
    request = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    apply(request)
    _, second = apply(request)
    assert second.bytes_dropped == 0


def test_growing_the_conversation_drops_what_left_the_newest_slot():
    """Turn by turn: a candidate is sent whole once, then goes."""
    request = body(*turn("a", "Bash", {"command": "ls -la"}))
    _, plan = apply(request)
    assert plan.dropped == [] and plan.deferred  # still the newest
    request["messages"].extend(turn("b", "Bash", {"command": "git diff"}))
    _, plan = apply(request)
    assert [d["tool"] for d in plan.dropped] == ["Bash"]
    assert results_of(request)[0]["content"].startswith("[winnow:")


def test_keep_newest_can_be_raised():
    request = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}),
                   *turn("c", "Bash", {"command": "git log"}))
    _, plan = apply(request, keep_newest=2)
    assert plan.bytes_dropped == len(BIG)  # only `a`
    assert len(plan.deferred) == 2


def test_the_clients_ttl_is_carried_onto_the_moved_breakpoint():
    """Moving a breakpoint must not silently reprice a request from the 1h write
    class to the 5m one — COZEMPIC.md §3.1's 40% error, in the other direction."""
    request = body(*turn("a", "Bash", {"command": "ls -la"}, cache=True),
                   *turn("b", "Bash", {"command": "git diff"}, cache=True))
    apply(request)
    moved = breakpoints_of(request)
    assert moved
    m, b = moved[-1]
    assert request["messages"][m]["content"][b]["cache_control"]["ttl"] == "1h"


def test_the_filter_never_pushes_a_request_over_the_breakpoint_cap():
    """The API caps `cache_control` at 4 per request. Adding a fifth turns a
    working request into a 400, so a full request is left as it is."""
    messages = []
    for i in range(4):
        messages.extend(turn(f"k{i}", "Bash", {"command": f"python x{i}.py"}, cache=True))
    messages.extend(turn("c", "Bash", {"command": "ls -la"}))
    request = body(*messages)
    _, plan = apply(request)
    assert len(breakpoints_of(request)) <= 4
    assert not plan.breakpoint_moved


def test_a_breakpoint_on_the_candidate_is_removed_which_frees_a_slot():
    """When the client put its breakpoint on the candidate itself, taking it off
    both un-caches the candidate and leaves room to place one in front of it."""
    messages = []
    for i in range(3):
        messages.extend(turn(f"k{i}", "Bash", {"command": f"python x{i}.py"}, cache=True))
    messages.extend(turn("c", "Bash", {"command": "ls -la"}, cache=True))
    request = body(*messages)
    _, plan = apply(request)
    assert plan.breakpoint_moved
    assert len(breakpoints_of(request)) <= 4
    newest = (len(request["messages"]) - 1, 0)
    assert newest not in breakpoints_of(request)


def test_a_body_without_messages_is_returned_untouched():
    request = {"model": "claude-opus-5"}
    out, plan = apply(request)
    assert out is request and not plan.changed


def test_the_pointer_says_where_the_bytes_went():
    text = pointer("Bash", "B2", 41208)
    assert "rule B2" in text and "41208 bytes" in text
    # No `winnow recover`: the filter keeps no copy, and SPEC §7 route 1 (re-run
    # the call) returns fresher bytes than these were.
    assert "recover" not in text


# ─── Failure is passthrough, never breakage ──────────────────────────────────


def test_an_unparseable_body_is_forwarded_unchanged():
    stats = Stats()
    raw = b"{not json"
    out, ledger = _rewrite(raw, Config(), stats)
    assert out == raw and ledger is None and stats.errors == 1


def test_a_filter_that_raises_forwards_the_original(monkeypatch):
    stats = Stats()
    monkeypatch.setattr("winnow.proxy.apply", lambda *a, **k: 1 / 0)
    raw = json.dumps(body(*turn("a", "Bash", {"command": "ls -la"}))).encode()
    out, ledger = _rewrite(raw, Config(), stats)
    assert out == raw and ledger is None and stats.errors == 1


def test_a_json_body_that_is_not_an_object_is_forwarded():
    stats = Stats()
    out, _ = _rewrite(b"[1,2,3]", Config(), stats)
    assert out == b"[1,2,3]" and stats.errors == 1


# ─── The proxy, against a real upstream ──────────────────────────────────────


class _Upstream(BaseHTTPRequestHandler):
    """Records the body it was sent and streams a reply back in pieces."""

    # Class attributes rather than instance: the server constructs a handler per
    # request, so anything an assertion needs to see has to outlive it. The
    # headers are kept as the parsed message object, not a dict — header lookup
    # is case-insensitive on the wire and must be here too.
    received: typing.ClassVar[list] = []
    headers_seen: typing.ClassVar[list] = []

    def log_message(self, *a):
        pass

    # Named for the server's dispatch, which looks up "do_" + the method.
    def do_POST(self):
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length)
        type(self).received.append(json.loads(raw))
        type(self).headers_seen.append(self.headers)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("request-id", "req_test")
        self.end_headers()
        for part in (b"event: a\n", b"event: b\n", b"event: done\n"):
            self.wfile.write(part)
            self.wfile.flush()


@pytest.fixture
def wired(tmp_path):
    """A filter proxy in front of a stub upstream, both on ephemeral ports."""
    _Upstream.received = []
    _Upstream.headers_seen = []
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()

    config = Config(
        upstream=f"http://127.0.0.1:{upstream.server_address[1]}",
        ledger=tmp_path / "ledger.jsonl",
    )
    handler = type("_Bound", (_Handler,), {"config": config, "stats": Stats()})
    proxy = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{proxy.server_address[1]}", config, handler
    proxy.shutdown()
    upstream.shutdown()


def _post(base: str, payload: dict, headers: dict | None = None):
    request = urllib.request.Request(
        f"{base}/v1/messages",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.read()


def test_the_proxy_filters_the_body_the_upstream_receives(wired):
    base, _, handler = wired
    payload = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    status, _ = _post(base, payload)
    assert status == 200
    sent = _Upstream.received[0]
    assert results_of(sent)[0]["content"].startswith("[winnow:")
    assert results_of(sent)[1]["content"] == BIG
    assert handler.stats.bytes_dropped == len(BIG)


def test_the_response_streams_through_intact(wired):
    base, _, _ = wired
    _, payload = _post(base, body(*turn("a", "Bash", {"command": "ls -la"})))
    assert payload == b"event: a\nevent: b\nevent: done\n"


def test_credentials_are_relayed_and_never_altered(wired):
    base, _, _ = wired
    _post(base, body(*turn("a", "Bash", {"command": "ls -la"})),
          {"x-api-key": "sk-test-key", "anthropic-version": "2023-06-01"})
    seen = _Upstream.headers_seen[0]
    assert seen["x-api-key"] == "sk-test-key"
    assert seen["anthropic-version"] == "2023-06-01"


def test_content_length_is_recomputed_after_a_rewrite(wired):
    """The body shrinks. A stale content-length is a hung request."""
    base, _, _ = wired
    payload = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    _post(base, payload)
    seen = _Upstream.headers_seen[0]
    assert int(seen["content-length"]) == len(json.dumps(_Upstream.received[0]))


def test_a_path_that_is_not_messages_is_relayed_verbatim(wired):
    base, _, handler = wired
    payload = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    request = urllib.request.Request(
        f"{base}/v1/messages/count_tokens",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()
    # A filtered count_tokens would count a body the real request never sends.
    assert results_of(_Upstream.received[0])[0]["content"] == BIG
    assert handler.stats.bytes_dropped == 0


def test_the_ledger_records_what_the_transcript_will_not(wired):
    base, config, _ = wired
    _post(base, body(*turn("a", "Bash", {"command": "ls -la"}),
                     *turn("b", "Bash", {"command": "git diff"})))
    lines = config.ledger.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["bytes_dropped"] == len(BIG)
    assert record["request_id"] == "req_test"
    assert record["dropped"][0]["rule"] == "B2"


def test_stats_line_reports_passthrough_on_error():
    stats = Stats()
    stats.record(error=True)
    stats.record(filtered=True, dropped=100)
    assert "1 passthrough on error" in stats.line()
    assert "100 bytes dropped" in stats.line()


def test_plan_is_unchanged_when_nothing_fired():
    assert not Plan().changed


# ─── The kill switch ─────────────────────────────────────────────────────────


def test_the_kill_switch_stops_rewriting_but_keeps_relaying(wired, tmp_path):
    """Turning the proxy *off* is not the safe operation: ANTHROPIC_BASE_URL is
    fixed in an agent's environment when it spawns, so a listener that goes away
    takes every request with it. Stopping the rewriting is the safe one."""
    base, config, _ = wired
    off = tmp_path / "filter-off"
    config.off_file = off

    payload = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    _post(base, payload)
    assert results_of(_Upstream.received[0])[0]["content"].startswith("[winnow:")

    off.touch()
    _post(base, payload)
    # Same conversation, nothing rewritten, and the request still reached the API.
    assert results_of(_Upstream.received[1])[0]["content"] == BIG
    assert len(_Upstream.received) == 2

    off.unlink()
    _post(base, payload)
    assert results_of(_Upstream.received[2])[0]["content"].startswith("[winnow:")


def test_no_off_file_configured_means_no_kill_switch(tmp_path):
    from winnow.proxy import _filtering_disabled

    assert _filtering_disabled(Config(off_file=None)) is False


def test_an_unreadable_switch_is_not_an_off_switch(monkeypatch, tmp_path):
    """Failing the other way would let a permissions change silently disable the
    filter, which is the one outcome that should never happen by accident."""
    from winnow.proxy import _filtering_disabled

    target = tmp_path / "off"

    def boom(*a, **k):
        raise PermissionError("nope")

    monkeypatch.setattr(Path, "exists", boom)
    assert _filtering_disabled(Config(off_file=target)) is False


def test_serving_creates_the_directory_the_kill_switch_lives_in(tmp_path):
    """The documented way to reach the switch is one `touch`. It has to work —
    the first version of this shipped without the mkdir, and the one command an
    operator is told to run failed with "No such file or directory"."""
    import threading as _threading

    import winnow.proxy as proxy_mod

    off = tmp_path / "nested" / "deeper" / "filter-off"
    done = _threading.Event()

    def run():
        try:
            proxy_mod.serve(Config(port=0, off_file=off))
        finally:
            done.set()

    thread = _threading.Thread(target=run, daemon=True)
    thread.start()
    for _ in range(200):  # up to 2s for the socket to bind and the mkdir to run
        if off.parent.is_dir():
            break
        time.sleep(0.01)
    assert off.parent.is_dir()

    off.touch()  # the command an operator is told to run
    assert proxy_mod._filtering_disabled(Config(off_file=off))
