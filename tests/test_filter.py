"""Tests for the intake filter: the policy, and the proxy that carries it.

The policy tests assert on request bodies, because the request body *is* the
cache key — a policy that produced the right decision and the wrong bytes would
be worse than no policy at all. The proxy tests run a real server against a stub
upstream, because the two things most likely to break a session (streaming, and
credentials) cannot be checked any other way.
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time
import typing
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from winnow.filter import FILTER_MIN_BYTES, Plan, apply, pointer, rule_for
from winnow.proxy import Config, PrefixWatch, Stats, _Handler, _rewrite

BIG = "x" * (FILTER_MIN_BYTES + 100)
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


def batch(*calls: tuple[str, str, dict], split: bool = False) -> list[dict]:
    """One assistant turn issuing several tool calls, and the answers.

    `split=False` puts every `tool_result` in one user message; `split=True` puts
    each in its own, which is the layout every user record in this operator's
    corpus actually has (64,651 of 64,651 carry exactly one result). The filter
    must group by the *call* rather than by the message the answers sit in, so
    both layouts have to behave the same and both are exercised.
    """
    uses = [
        {"type": "tool_use", "id": uid, "name": name, "input": tool_input}
        for uid, name, tool_input in calls
    ]
    blocks = [
        {"type": "tool_result", "tool_use_id": uid, "content": BIG, "is_error": False}
        for uid, _, _ in calls
    ]
    assistant = {"role": "assistant", "content": uses}
    if split:
        return [assistant] + [{"role": "user", "content": [b]} for b in blocks]
    return [assistant, {"role": "user", "content": blocks}]


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


# ─── Deferral is by turn, not by result ──────────────────────────────────────


@pytest.mark.parametrize("split", [False, True], ids=["one-message", "one-per-message"])
def test_a_parallel_batch_is_deferred_whole(split):
    """The model asked three questions. It must not get one answer and two
    receipts.

    Counting the last `keep_newest` entries of a flat list exempted only the last
    result of a batch and replaced the rest with pointers on the very request
    carrying them to the model for the first time: 15.58% of tool-issuing requests
    are batches on this corpus, and one byte in seven of everything the filter
    removes was removed before the model had read it.
    """
    request = body(*batch(("a", "Bash", {"command": "ls -la"}),
                          ("b", "Bash", {"command": "git status"}),
                          ("c", "Glob", {"pattern": "*.py"}), split=split))
    _, plan = apply(request)
    assert plan.dropped == []
    assert plan.bytes_dropped == 0
    assert len(plan.deferred) == 3
    assert all(r["content"] == BIG for r in results_of(request))


@pytest.mark.parametrize("split", [False, True], ids=["one-message", "one-per-message"])
def test_the_previous_batch_goes_whole_on_the_next_request(split):
    """And it is a deferral, not an exemption: once the model has answered, the
    whole batch is a pointer."""
    request = body(*batch(("a", "Bash", {"command": "ls -la"}),
                          ("b", "Bash", {"command": "git status"}), split=split),
                   *batch(("c", "Bash", {"command": "git diff"}),
                          ("d", "Glob", {"pattern": "*.py"}), split=split))
    _, plan = apply(request)
    assert len(plan.dropped) == 2
    assert len(plan.deferred) == 2
    contents = [r["content"] for r in results_of(request)]
    assert contents[0].startswith("[winnow:") and contents[1].startswith("[winnow:")
    assert contents[2] == BIG and contents[3] == BIG


@pytest.mark.parametrize("split", [False, True], ids=["one-message", "one-per-message"])
def test_the_breakpoint_goes_in_front_of_the_whole_batch(split):
    """Every member of the deferred batch is going to become a pointer next
    request, so every member has to be outside the write region — not just the
    last one."""
    request = body(*batch(("a", "Bash", {"command": "ls -la"}), split=split),
                   *batch(("b", "Bash", {"command": "git status"}),
                          ("c", "Bash", {"command": "git diff"}),
                          ("d", "Glob", {"pattern": "*.py"}), split=split))
    _, plan = apply(request)
    assert plan.breakpoint_moved
    last_break = max(breakpoints_of(request))
    deferred_ids = {entry["tool_use_id"] for entry in plan.deferred}
    positions = [
        (m, b)
        for m, message in enumerate(request["messages"])
        for b, block in enumerate(message["content"])
        if isinstance(block, dict) and block.get("tool_use_id") in deferred_ids
    ]
    assert len(positions) == 3
    assert all(position > last_break for position in positions)


def test_a_result_whose_call_is_missing_still_groups_by_its_own_message():
    """A `tool_result` with no matching `tool_use` — 3 in 64,654 on this corpus —
    has no turn to be grouped by. It falls back to its own position rather than
    joining an unrelated batch."""
    request = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    request["messages"][2]["content"] = []  # the tool_use for `b` disappears
    _, plan = apply(request)
    assert len(plan.dropped) == 1
    assert plan.dropped[0]["tool_use_id"] == "a"


# ─── Rule selection reaches the filter ───────────────────────────────────────


def test_a_disabled_rule_does_not_fire():
    """`docs/MILESTONE-2-VALIDATION.md`'s scorer prints `export WINNOW_RULES_OFF=B2`
    as the remediation for a rule below its precision bar, and B2 is 96.07% of what
    the filter removes. Before this the pruner would stop firing it and the filter
    would go on firing it, on a live request, with nothing saying so."""
    request = body(*turn("a", "Bash", {"command": "git status"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    _, plan = apply(request, enabled=frozenset({"C1", "C3"}))
    assert plan.dropped == []
    assert results_of(request)[0]["content"] == BIG


def test_the_env_switch_reaches_the_filters_rule_set(monkeypatch):
    from winnow.cli import _filter_rules

    monkeypatch.setenv("WINNOW_RULES_OFF", "B2")
    args = argparse.Namespace(tier="CB", rule=[], no_rule=[])
    selected, suppressed = _filter_rules(args)
    assert selected == frozenset({"C1", "C3"})
    assert suppressed == ("B2",)


def test_a_tier_restricts_the_filter_to_what_it_can_decide():
    from winnow.cli import _filter_rules

    for tier, expected in [("C", {"C1", "C3"}), ("CB", {"C1", "C3", "B2"}),
                           ("CBA", {"C1", "C3", "B2"})]:
        selected, _ = _filter_rules(argparse.Namespace(tier=tier, rule=[], no_rule=[]))
        assert selected == frozenset(expected), tier


def test_naming_a_hindsight_rule_is_a_usage_error():
    """An operator typing `--rule C2` is asking for something this component
    cannot do. Silence would leave them believing it was doing it."""
    from winnow.cli import _filter_rules
    from winnow.rules import RuleSelectionError

    for rule in ("C2", "B1", "A1"):
        with pytest.raises(RuleSelectionError):
            _filter_rules(argparse.Namespace(tier="CB", rule=[rule], no_rule=[]))


def test_turning_off_a_rule_the_filter_never_had_is_allowed():
    """`--no-rule C2` asks for strictly less than the filter already does. An
    operator sharing one set of rule flags across `plan` and `filter` should not
    be stopped by it."""
    from winnow.cli import _filter_rules

    selected, _ = _filter_rules(argparse.Namespace(tier="CB", rule=[], no_rule=["C2"]))
    assert selected == frozenset({"C1", "C3", "B2"})


def test_the_rule_set_is_resolved_once_not_per_request(monkeypatch):
    """`rules.default_disabled` reads `os.environ` at call time. A filter that
    resolved per request would render the same conversation two ways the moment
    somebody exported a variable in another shell — the §K1 break, arriving from
    outside the process."""
    from winnow.proxy import Config, Stats, _rewrite

    config = Config(rules=frozenset({"C1", "C3", "B2"}))
    stats = Stats()
    first = json.dumps(body(*turn("a", "Bash", {"command": "git status"}),
                            *turn("b", "Bash", {"command": "git diff"}))).encode()
    once, _, _ = _rewrite(first, config, stats)
    monkeypatch.setenv("WINNOW_RULES_OFF", "B2")
    twice, _, _ = _rewrite(first, config, stats)
    assert once == twice


def test_g4_refuses_a_strip_whose_pointer_is_longer_than_the_content():
    """SPEC §4 G4. `--min-bytes 10` used to replace 30 bytes with a 112-byte
    pointer and record 30 bytes saved: the request grew and the ledger called it
    a saving. The guard is `rules.inflates`, so the filter has no fourth opinion
    about it."""
    tiny = "z" * 30
    request = body(*turn("a", "Bash", {"command": "ls -la"}, content=tiny),
                   *turn("b", "Bash", {"command": "ls /tmp"}, content=tiny))
    _, plan = apply(request, min_bytes=10)
    assert plan.dropped == []
    assert plan.bytes_dropped == 0
    assert plan.inflated == 2
    assert [r["content"] for r in results_of(request)] == [tiny, tiny]


def test_g4_admits_a_result_that_clears_the_pointer():
    """The other side of the guard: above the pointer's length the strip stands,
    so G4 is a floor and not an off switch."""
    payload = "z" * 400
    request = body(*turn("a", "Bash", {"command": "ls -la"}, content=payload),
                   *turn("b", "Bash", {"command": "ls /tmp"}, content=payload))
    _, plan = apply(request, min_bytes=256)
    assert plan.inflated == 0
    assert plan.bytes_dropped == 400
    assert results_of(request)[0]["content"].startswith("[winnow:")


def test_a_min_bytes_below_the_pointer_is_a_usage_error(monkeypatch, capsys):
    """The floor is checked before a request arrives, and the environment is held
    to the same bar as the flag."""
    from winnow.cli import main

    monkeypatch.setenv("WINNOW_FILTER", "1")
    monkeypatch.setenv("WINNOW_FILTER_MIN_BYTES", "10")
    assert main(["filter"]) == 1
    assert "below the longest pointer" in capsys.readouterr().err


def test_the_floor_is_where_the_pointer_stops_inflating():
    from winnow.filter import longest_pointer, smallest_safe_min_bytes

    floor = smallest_safe_min_bytes()
    assert longest_pointer(floor) <= floor
    assert longest_pointer(floor - 1) > floor - 1


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


def test_every_deferred_candidate_is_outside_the_cached_prefix():
    """Invariant W1. A deferred result is sent in full now and replaced by a
    pointer on the next request, so if the cache writes it the prefix breaks
    there — `1.9·S` on a warm conversation, every request from the third on.

    The breakpoint therefore goes in front of the *oldest* deferred candidate,
    not the newest. At `--keep-newest 2` this asserted the opposite before the
    fix, and no test noticed.
    """
    request = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}),
                   *turn("c", "Bash", {"command": "git log"}))
    _, plan = apply(request, keep_newest=2)
    breaks = breakpoints_of(request)
    assert breaks, "the filter must leave a boundary to defer behind"
    last_break = max(breaks)
    deferred_ids = {entry["tool_use_id"] for entry in plan.deferred}
    positions = [
        (m, b)
        for m, message in enumerate(request["messages"])
        for b, block in enumerate(message["content"])
        if isinstance(block, dict) and block.get("tool_use_id") in deferred_ids
    ]
    assert positions
    assert all(position > last_break for position in positions)


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


def test_breakpoints_on_system_and_tools_count_against_the_cap():
    """A Messages API request has three cacheable regions and the cap is over all
    of them. Counting only `messages` let the filter believe it had a slot free
    when it did not, and the fifth `cache_control` is a 400 — not a lost saving.
    """
    messages = []
    for i in range(2):
        messages.extend(turn(f"k{i}", "Bash", {"command": f"python x{i}.py"}, cache=True))
    messages.extend(turn("c", "Bash", {"command": "ls -la"}))
    request = body(*messages)
    request["system"] = [{"type": "text", "text": "be helpful",
                          "cache_control": {"type": "ephemeral"}}]
    request["tools"] = [{"name": "Bash", "input_schema": {},
                         "cache_control": {"type": "ephemeral"}}]
    _, plan = apply(request)
    total = (len(breakpoints_of(request))
             + sum(1 for b in request["system"] if "cache_control" in b)
             + sum(1 for b in request["tools"] if "cache_control" in b))
    assert total <= 4
    assert not plan.breakpoint_moved


def test_a_ttl_asked_for_above_the_conversation_is_the_one_carried_down():
    """`system` and `tools` are first in the cache key. A client asking for a
    one-hour prefix there and leaving the conversation's breakpoints implicit is
    asking for one hour, and reading only `messages` answered from the wrong
    region — COZEMPIC.md §3.1's 40% error, in the other direction."""
    request = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    request["system"] = [{"type": "text", "text": "be helpful",
                          "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    _, plan = apply(request)
    assert plan.cache_ttl == "ephemeral_1h"
    moved = breakpoints_of(request)
    assert moved
    m, b = moved[-1]
    assert request["messages"][m]["content"][b]["cache_control"]["ttl"] == "1h"


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
    out, ledger, _ = _rewrite(raw, Config(), stats)
    assert out == raw and ledger is None and stats.errors == 1


def test_a_filter_that_raises_forwards_the_original(monkeypatch):
    stats = Stats()
    monkeypatch.setattr("winnow.proxy.apply", lambda *a, **k: 1 / 0)
    raw = json.dumps(body(*turn("a", "Bash", {"command": "ls -la"}))).encode()
    out, ledger, _ = _rewrite(raw, Config(), stats)
    assert out == raw and ledger is None and stats.errors == 1


def test_a_json_body_that_is_not_an_object_is_forwarded():
    stats = Stats()
    out, _, _ = _rewrite(b"[1,2,3]", Config(), stats)
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
    handler = type("_Bound", (_Handler,),
                   {"config": config, "stats": Stats(), "watch": PrefixWatch()})
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
    records = [json.loads(line) for line in
               config.ledger.read_text().strip().splitlines()]
    # Selected by `kind`, which is what the tag is for: one file, several record
    # types, and a reader that asks what a line *is* rather than guessing from
    # which fields it happens to carry.
    filtered = [r for r in records if r["kind"] == "filter"]
    assert len(filtered) == 1
    record = filtered[0]
    assert record["bytes_dropped"] == len(BIG)
    assert record["request_id"] == "req_test"
    assert record["dropped"][0]["rule"] == "B2"


def test_the_prefix_is_reported_once_while_it_is_stable(wired):
    """A stable prefix costs one line per process. An unstable one is the most
    expensive thing that can happen to a Claude Code install and is otherwise
    completely invisible — a tool description carrying a timestamp, an MCP server
    returning its tools in a different order each connection, a CLAUDE.md
    re-rendered with a directory listing. The only symptom is the bill."""
    base, config, _ = wired
    payload = body(*turn("a", "Bash", {"command": "python train.py"}))
    payload["system"] = [{"type": "text", "text": "be helpful"}]
    payload["tools"] = [{"name": "Bash", "description": "run a command"}]
    for _ in range(3):
        _post(base, json.loads(json.dumps(payload)))

    records = [json.loads(line) for line in
               config.ledger.read_text().strip().splitlines()]
    prefixes = [r for r in records if r["kind"] == "prefix"]
    assert len(prefixes) == 1
    # The per-tool map is the definitions themselves; `tools_bytes` is the list
    # around them, so it carries the two brackets as well.
    assert list(prefixes[0]["tools"]) == ["Bash"]
    assert prefixes[0]["tools_bytes"] == prefixes[0]["tools"]["Bash"] + 2
    assert prefixes[0]["tool_count"] == 1
    assert prefixes[0]["changed"] is None
    assert "be helpful" not in config.ledger.read_text(), "sizes and hashes, never content"


def test_a_prefix_line_carries_the_request_it_was_observed_on(wired):
    """The join `winnow context --filter-ledger` needs, and the one this line
    could not make: it used to be written before the upstream call with a null
    id, so a prefix observation belonged to no session at all."""
    base, config, _ = wired
    payload = body(*turn("a", "Bash", {"command": "python train.py"}))
    payload["system"] = [{"type": "text", "text": "be helpful"}]
    payload["tools"] = [{"name": "Bash", "description": "run a command"}]
    _post(base, payload)

    records = [json.loads(line) for line in
               config.ledger.read_text().strip().splitlines()]
    prefix = next(r for r in records if r["kind"] == "prefix")
    assert prefix["request_id"] == "req_test"
    assert prefix["digest"] == (f"{prefix['system_digest']}."
                                f"{prefix['tools_digest']}")


def test_the_prefix_line_precedes_the_filter_line_it_describes(wired):
    """Both are written on the response path now, so the order is a choice: a
    reader walking an append-only file should meet the prefix before the traffic
    sent under it."""
    base, config, _ = wired
    payload = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    payload["system"] = [{"type": "text", "text": "be helpful"}]
    _post(base, payload)

    kinds = [json.loads(line)["kind"] for line
             in config.ledger.read_text().strip().splitlines()]
    assert kinds[:2] == ["prefix", "filter"]


def test_every_filter_line_names_the_prefix_in_force(wired):
    """The digest is on the line whether or not the prefix moved, which is the
    whole point: a `kind: prefix` line is written once per process and belongs
    to whichever session started it, so a later session can only find its own
    prefix by being told which one it was sent under."""
    base, config, _ = wired
    payload = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    payload["system"] = [{"type": "text", "text": "be helpful"}]
    payload["tools"] = [{"name": "Bash", "description": "run a command"}]
    for _ in range(3):
        _post(base, json.loads(json.dumps(payload)))

    records = [json.loads(line) for line in
               config.ledger.read_text().strip().splitlines()]
    prefixes = [r for r in records if r["kind"] == "prefix"]
    filters = [r for r in records if r["kind"] == "filter"]
    assert len(prefixes) == 1 and len(filters) == 3
    assert {r["prefix_digest"] for r in filters} == {prefixes[0]["digest"]}


def test_an_upstream_that_never_answers_still_records_the_prefix(wired):
    """`PrefixWatch` has already forgotten the prefix before this one, so an
    observation dropped here is lost for the life of the process. It is written
    with no request id rather than not at all — unjoinable, which is what a
    reader must treat a null id as, but not absent."""
    base, config, _ = wired
    # A port nothing is listening on, so the proxy's own upstream call fails
    # after the prefix has been observed and before any response exists to
    # stamp it with. Closed here rather than never opened, so the port is known
    # to be free and known to be dead.
    dead = socket.socket()
    dead.bind(("127.0.0.1", 0))
    config.upstream = f"http://127.0.0.1:{dead.getsockname()[1]}"
    dead.close()

    payload = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    payload["system"] = [{"type": "text", "text": "be helpful"}]
    with pytest.raises(urllib.error.HTTPError) as caught:
        _post(base, payload)
    assert caught.value.code == 502

    # The 502 is sent before the handler unwinds, so the client is back here
    # while the write is still pending. That order is the right one — the
    # operator's request should not wait on a ledger — and it is the test that
    # has to wait.
    for _ in range(200):  # up to 2s
        if config.ledger.exists():
            break
        time.sleep(0.01)
    records = [json.loads(line) for line in
               config.ledger.read_text().strip().splitlines()]
    prefixes = [r for r in records if r["kind"] == "prefix"]
    assert len(prefixes) == 1
    assert prefixes[0]["request_id"] is None
    assert prefixes[0]["system_bytes"] > 0
    # And nothing claims a removal that never reached the API.
    assert not [r for r in records if r["kind"] == "filter"]


def test_a_moved_prefix_is_reported_and_attributed(wired):
    """Enough to attribute a prefix break to the thing the operator did that
    morning: which region moved, which tools appeared, and which kept their name
    while changing size — the last being the shape a timestamped tool description
    takes, and the one that is otherwise invisible."""
    base, config, _ = wired
    payload = body(*turn("a", "Bash", {"command": "python train.py"}))
    payload["system"] = [{"type": "text", "text": "be helpful"}]
    payload["tools"] = [{"name": "Bash", "description": "run a command"}]
    _post(base, json.loads(json.dumps(payload)))

    payload["tools"].append({"name": "mcp__uf__propose_run", "description": "x" * 400})
    _post(base, json.loads(json.dumps(payload)))

    payload["tools"][0]["description"] = "run a command at 12:01:33"
    _post(base, json.loads(json.dumps(payload)))

    prefixes = [json.loads(line) for line in
                config.ledger.read_text().strip().splitlines()
                if json.loads(line)["kind"] == "prefix"]
    assert len(prefixes) == 3
    assert prefixes[1]["changed"]["tools_added"] == ["mcp__uf__propose_run"]
    assert prefixes[1]["changed"]["regions"] == ["tools"]
    assert prefixes[1]["changed"]["tools_bytes_delta"] > 400
    assert prefixes[2]["changed"]["tools_resized"] == ["Bash"]
    assert prefixes[2]["changed"]["tools_added"] == []


def test_the_prefix_readout_names_breakpoints_nothing_else_can_see(wired):
    """§K4 records that the filter's whole mechanism is drawn against a budget of
    four breakpoints it does not own, and no figure existed anywhere for how the
    client spends them — because the two regions it may also place them in are
    never written to disk."""
    base, config, _ = wired
    payload = body(*turn("a", "Bash", {"command": "python train.py"}))
    payload["system"] = [{"type": "text", "text": "be helpful",
                          "cache_control": {"type": "ephemeral"}}]
    payload["tools"] = [{"name": "Bash", "description": "run",
                         "cache_control": {"type": "ephemeral"}}]
    _post(base, payload)
    prefixes = [json.loads(line) for line in
                config.ledger.read_text().strip().splitlines()
                if json.loads(line)["kind"] == "prefix"]
    assert prefixes[0]["breakpoints"] == {"system": 1, "tools": 1, "messages": 0}


def test_a_prefix_readout_that_raises_does_not_fail_the_request(monkeypatch):
    """A reporting subsystem inside the credential path must not acquire a
    failure mode. This is the whole of the objection §K2 makes to it."""
    from winnow import proxy as proxy_mod

    def boom(_body):
        raise RuntimeError("no")

    monkeypatch.setattr(proxy_mod, "prefix_facts", boom)
    watch = PrefixWatch()
    assert watch.observe({"model": "claude-opus-5"}) == (None, None)


def test_the_readout_is_skipped_when_asked(tmp_path):
    from winnow.filter import prefix_facts

    path = tmp_path / "filter.jsonl"
    config = Config(ledger=path, prefix_readout=False, heartbeat_every=0)
    payload = json.dumps(body(*turn("a", "Bash", {"command": "python train.py"}))).encode()
    _rewrite(payload, config, Stats(), PrefixWatch())
    assert not path.exists()
    # And the facts themselves stay computable, so nothing is coupled to the flag.
    assert prefix_facts({"system": "hi"})["system_bytes"] == 2


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


# ─── One rule engine ─────────────────────────────────────────────────────────


def _engine_verdict(name: str, tool_input: dict, enabled=None) -> str | None:
    """`rules._first_matching_rule` on a call with no session around it.

    Empty indices, so C2, B1 and A1 cannot fire and what is left is exactly the
    three rules the filter also answers.
    """
    from winnow.rules import STATELESS_RULES, ToolCall, _first_matching_rule

    call = ToolCall(order=0, line=0, name=name, tool_input=tool_input,
                    result_size=9999, is_error=False, has_result=True)
    return _first_matching_rule(
        call, {}, [], {}, enabled if enabled is not None else STATELESS_RULES
    )


def _cross_product() -> list[tuple[str, dict]]:
    """Every (tool, input) shape the constants can produce, not nine by hand."""
    from winnow.rules import (
        INSPECTION_GIT_SUBCOMMANDS,
        INSPECTION_HEADS,
        LOCATOR_GREP_MODES,
        LOCATOR_TOOLS,
    )

    cases: list[tuple[str, dict]] = []
    for tool in sorted(LOCATOR_TOOLS) + ["Grep", "Bash", "Read", "Edit", "Write", "Agent"]:
        cases.append((tool, {}))
    for mode in sorted(LOCATOR_GREP_MODES) + ["content", None]:
        cases.append(("Grep", {"output_mode": mode}))
    for head in sorted(INSPECTION_HEADS):
        cases.append(("Bash", {"command": f"{head} something"}))
        cases.append(("Bash", {"command": f"FOO=1 /usr/bin/{head} x | wc -l"}))
    for sub in sorted(INSPECTION_GIT_SUBCOMMANDS) + ["push", "commit"]:
        cases.append(("Bash", {"command": f"git {sub}"}))
    for verify in ["npm run test", "pytest -q", "go test ./...", "cargo clippy",
                   "tsc --noEmit", "make check", "ruff check .", "mypy src"]:
        cases.append(("Bash", {"command": verify}))
        cases.append(("Bash", {"command": f"cat x.txt && {verify}"}))
    for other in ["python train.py", "", "   ", "./deploy.sh", "sed -n 1,5p f",
                  "sed s/a/b/ f"]:
        cases.append(("Bash", {"command": other}))
    cases.extend([("Bash", {}), ("Bash", {"command": None}), ("Bash", {"command": 7})])
    return cases


@pytest.mark.parametrize("name,tool_input", _cross_product())
def test_the_two_engines_agree_on_every_non_error_input(name, tool_input):
    """`filter.rule_for` and `rules._first_matching_rule` answered the same three
    rules from the same constants in two hand-written `if` chains. The data had
    one owner; the decision procedure had two, and the copy was faithful on all
    63,931 non-error results in this corpus — which says it is faithful today,
    not that it will stay so. This is what makes the next divergence fail in CI
    rather than in a bill."""
    assert rule_for(name, tool_input, False) == _engine_verdict(name, tool_input)


@pytest.mark.parametrize("name,tool_input", _cross_product())
def test_they_agree_under_every_rule_selection(name, tool_input):
    """Including when a rule is switched off — the order is load-bearing, and a
    selection is where a difference in ordering would show."""
    from winnow.rules import STATELESS_RULES

    for off in sorted(STATELESS_RULES):
        enabled = STATELESS_RULES - {off}
        assert rule_for(name, tool_input, False, enabled) == _engine_verdict(
            name, tool_input, enabled
        )


def test_the_shared_engine_cannot_be_asked_about_an_error():
    """G3 is the caller's, and the signature is what keeps it there.

    `classify` applies G1, G2, G3 and G5 before the engine is entered; the filter
    is handed unguarded blocks off the wire and applies G3 itself. Merging the two
    by passing `is_error` into the shared function is the regression this
    signature makes impossible to write by accident — it would newly claim 753
    results on this corpus, and G3 is "errors survive, at any tier"."""
    import inspect as inspect_mod

    from winnow.rules import stateless_rule_for

    assert "is_error" not in inspect_mod.signature(stateless_rule_for).parameters
    # And the filter's own G3 still stands in front of it.
    for command in ("npm run test", "git status"):
        assert rule_for("Bash", {"command": command}, True) is None
        assert stateless_rule_for("Bash", {"command": command}) is not None


def test_prefix_determined_declares_the_filters_whole_rule_set():
    """The declaration and the enforcement have to agree, or the map is a
    comment. A seventh rule has to answer this question at the point it is
    written."""
    from winnow.rules import ALL_RULES, PREFIX_DETERMINED, RULE_ORDER, STATELESS_RULES

    assert set(PREFIX_DETERMINED) == ALL_RULES
    assert STATELESS_RULES == {"C1", "C3", "B2"}
    # Every rule the filter can return is declared prefix-determined, and nothing
    # else can be returned at all.
    fired = {rule_for(n, i, False) for n, i in _cross_product()} - {None}
    assert fired <= STATELESS_RULES
    assert all(PREFIX_DETERMINED[rule] for rule in fired)
    assert [r for r in RULE_ORDER if PREFIX_DETERMINED[r]] == ["C1", "C3", "B2"]


def test_the_filters_floor_is_not_the_pruners():
    """They should not be the same number, and the comment that used to say they
    were for the same reason was wrong. The pruner's 2,048 compares file bytes
    against a 163-byte pointer with a session's `S` behind it; the filter sends a
    candidate once in full and the pointer then lives in the prefix, so its
    break-even is between one and two pointer lengths."""
    from winnow.filter import FILTER_MIN_BYTES, smallest_safe_min_bytes
    from winnow.rules import DEFAULT_MIN_BYTES as PRUNER_MIN_BYTES

    assert FILTER_MIN_BYTES == 256
    assert PRUNER_MIN_BYTES == 2048
    # Above G4's floor, and by enough that the guard is a guard and not the policy.
    assert FILTER_MIN_BYTES > smallest_safe_min_bytes()
    # Above the T=0 break-even of 230, so every admitted result pays at every T.
    assert FILTER_MIN_BYTES >= 230


def test_a_result_between_the_two_floors_is_now_claimed():
    """The whole point of the change, in one body: 1 KB of `git status` was
    invisible to the filter and is now a candidate."""
    payload = "z" * 1024
    request = body(*turn("a", "Bash", {"command": "git status"}, content=payload),
                   *turn("b", "Bash", {"command": "git diff"}, content=payload))
    _, plan = apply(request)
    assert plan.bytes_dropped == 1024
    _, at_old_floor = apply(
        body(*turn("a", "Bash", {"command": "git status"}, content=payload),
             *turn("b", "Bash", {"command": "git diff"}, content=payload)),
        min_bytes=2048,
    )
    assert at_old_floor.bytes_dropped == 0


# ─── The instruments ─────────────────────────────────────────────────────────


def test_the_ledger_line_carries_a_version_and_a_type():
    """Two keys, because the next migration is not like the last three.
    `tool_use_id`, `model` and `cache_ttl` were each *added*, and a reader
    survives an addition by asking whether a key is present. A `bytes` that
    became net rather than gross would produce a line every current reader parses
    successfully and prices wrongly, in the flattering direction."""
    from winnow.filter import LEDGER_VERSION, ledger_line

    request = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    _, plan = apply(request)
    line = json.loads(ledger_line(plan, "req_1"))
    assert line["v"] == LEDGER_VERSION
    assert line["kind"] == "filter"
    assert line["inflated"] == 0


def test_stats_separate_what_was_looked_at_from_what_was_claimed():
    """`0 filtered` beside `6,410 tool results seen` is a fault; `0 filtered`
    beside `0 seen` is a proxy nobody is talking to. One counter could not tell
    them apart, and the number that does was computed on every request and thrown
    away."""
    stats = Stats()
    config = Config(rules=frozenset({"C1", "C3", "B2"}))
    payload = json.dumps(body(*turn("a", "Bash", {"command": "ls -la"}),
                              *turn("b", "Bash", {"command": "git diff"}))).encode()
    _rewrite(payload, config, stats)
    assert stats.tool_results_seen == 2
    assert stats.candidates == 2
    assert stats.filtered == 1

    quiet = Stats()
    _rewrite(json.dumps(body()).encode(), config, quiet)
    assert quiet.requests == 1
    assert quiet.tool_results_seen == 0
    assert quiet.candidates == 0


def test_a_request_that_changed_nothing_is_still_counted():
    """The population a health signal is about is exactly the one the ledger has
    never recorded, because the line is gated on `plan.changed`."""
    stats = Stats()
    config = Config(rules=frozenset({"C1", "C3", "B2"}))
    payload = json.dumps(body(*turn("a", "Bash", {"command": "python train.py"}))).encode()
    _, ledger, _ = _rewrite(payload, config, stats)
    assert ledger is None
    assert stats.requests == 1
    assert stats.tool_results_seen == 1
    assert stats.candidates == 0


def test_the_two_error_kinds_are_counted_apart():
    """An unreadable body says the wire format moved under the filter; a filter
    that raised says the filter has a bug. Different reactions, and one integer
    could not ask for either."""
    stats = Stats()
    config = Config()
    _rewrite(b"{not json", config, stats)
    assert (stats.unreadable, stats.filter_errors) == (1, 0)
    assert "1 unreadable" in stats.line()
    assert "0 filter errors" in stats.line()


def test_stats_line_still_reports_passthrough_on_error():
    stats = Stats()
    stats.record(error=True, unreadable=True)
    stats.record(filtered=True, dropped=100)
    assert "1 passthrough on error" in stats.line()
    assert "100 bytes dropped" in stats.line()


def test_a_heartbeat_is_written_every_n_requests(tmp_path):
    from winnow.filter import LEDGER_VERSION

    path = tmp_path / "filter.jsonl"
    config = Config(ledger=path, heartbeat_every=3,
                    rules=frozenset({"C1", "C3", "B2"}))
    stats = Stats()
    payload = json.dumps(body(*turn("a", "Bash", {"command": "python train.py"}))).encode()
    for _ in range(6):
        _rewrite(payload, config, stats)

    lines = [json.loads(raw) for raw in path.read_text().splitlines()]
    beats = [line for line in lines if line["kind"] == "heartbeat"]
    assert len(beats) == 2
    assert beats[-1]["requests"] == 6
    assert beats[-1]["tool_results_seen"] == 6
    assert beats[-1]["candidates"] == 0
    assert beats[-1]["v"] == LEDGER_VERSION
    # A heartbeat answers no request, so it is not stamped with one — a null id
    # would join to every transcript record that also has none.
    assert "request_id" not in beats[-1]


def test_a_heartbeat_is_off_when_asked_to_be(tmp_path):
    path = tmp_path / "filter.jsonl"
    config = Config(ledger=path, heartbeat_every=0)
    stats = Stats()
    payload = json.dumps(body(*turn("a", "Bash", {"command": "python train.py"}))).encode()
    for _ in range(5):
        _rewrite(payload, config, stats)
    assert not path.exists()


def test_both_readers_skip_a_heartbeat_rather_than_misreading_it(tmp_path):
    """Both keyed off field presence rather than off a tag, so without `kind` the
    first heartbeat would arrive in `savings.read_ledger` as a malformed entry and
    in `inspect.read_filter_ledger` as a request id matching nothing."""
    from winnow.filter import heartbeat_line, ledger_line
    from winnow.inspect import read_filter_ledger
    from winnow.savings import read_ledger

    request = body(*turn("a", "Bash", {"command": "ls -la"}),
                   *turn("b", "Bash", {"command": "git diff"}))
    _, plan = apply(request)
    path = tmp_path / "filter.jsonl"
    beat = heartbeat_line({"requests": 10, "filtered": 1, "tool_results_seen": 20,
                           "candidates": 2})
    line = json.loads(ledger_line(plan, "req_1"))
    path.write_text(json.dumps(line) + "\n" + beat + "\n")

    read = read_ledger(path)
    assert read.heartbeats == 1
    assert read.malformed_entries == 0
    assert read.lines_without_version == 0
    assert len(read.removals) == 2  # one dropped, one deferred
    assert read.last_heartbeat["tool_results_seen"] == 20

    found = read_filter_ledger(path, {"req_1"})
    assert found.requests == 1


def test_a_ledger_written_before_the_version_is_read_as_v0(tmp_path):
    from winnow.savings import read_ledger

    path = tmp_path / "filter.jsonl"
    path.write_text(json.dumps({
        "request_id": "req_old", "bytes_dropped": 5000,
        "dropped": [{"rule": "B2", "tool": "Bash", "bytes": 5000,
                     "tool_use_id": "toolu_old"}],
    }) + "\n")
    read = read_ledger(path)
    assert read.lines_without_version == 1
    assert len(read.removals) == 1  # still readable, at a cost the reader reports


def test_an_unknown_record_kind_is_left_for_a_future_reader(tmp_path):
    """Not ours, and not an error either. Counting it as malformed would put a
    number in the readout that means nothing."""
    from winnow.savings import read_ledger

    path = tmp_path / "filter.jsonl"
    path.write_text(json.dumps({"v": 2, "kind": "prefix", "system_bytes": 900}) + "\n")
    read = read_ledger(path)
    assert read.malformed_entries == 0
    assert read.parse_errors == 0
    assert read.removals == []
