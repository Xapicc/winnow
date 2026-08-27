"""The bytes the intake filter emits are pinned, exactly, against twelve bodies.

`winnow inspect --json` is pinned byte for byte because its deliverable is a
published number. The filter has something stronger: **a byte-level contract with
a cache it cannot observe.** `inspect` being wrong produces a misleading readout
that a second run corrects. The filter being wrong by one byte in the wrong place
produces `1.9·S` on a warm prefix, silently, in a bill that arrives weeks later,
in a process nobody is watching.

`tests/test_filter.py` states the right principle — *"the policy tests assert on
request bodies, because the request body **is** the cache key"* — and then asserts
properties of bodies rather than bodies. So all of these used to pass the suite:

* **rewording the pointer.** Three substrings are asserted; every other word is
  free. Changing it is a legitimate experiment and it should be a visible one.
* **moving where `_place_breakpoint_before` lands**, one block earlier, say. Four
  tests assert ordering; none asserts position.
* **emitting `cache_control` as `{"type": "ephemeral"}` versus with a `"ttl"`
  key** on a request where the client asked for none.
* **changing whether `cache_control` is popped off a dropped block** — the line
  that decides whether a pointered result carries a stale breakpoint into the
  prefix.

Each is a byte on the wire, and the wire is the cache key.

**The invariant writing this surfaced, which is nowhere else in the tree.**
`proxy._rewrite` has two exits: on a changed request it returns
`json.dumps(body).encode()` — re-rendered from scratch in Python's default style,
`", "` and `": "` separators, `ensure_ascii=True`, so every non-ASCII character
becomes a `\\uXXXX` escape — and on an unchanged one it returns the client's own
bytes verbatim. **So one conversation is transmitted in two different encodings
depending on whether the filter found a candidate that turn.** That is safe if and
only if:

> **I11 — the API's cache key is computed over the parsed content, not over the
> request's JSON encoding.**

If it were not, the filter would break its own cache on every request where
`plan.changed` flipped, which is most of them. It plainly does not. But it was
written down nowhere, and it is the assumption that licenses the one line of
`proxy.py` a reader is most likely to think is free. This golden cannot test I11;
it makes any change to that line visible.

Fixtures are request bodies rather than sessions, because the filter's deliverable
is a transformation. Twelve of them, and small: a golden that fails on every
legitimate change teaches regeneration as a reflex, and a diff has to stay
readable. Two of the shapes here — a parallel batch, and a list-form content with
an image block — were shapes no test in this suite constructed at all, which is
the second reason to write it.

Regenerate deliberately, never to make this pass:

    WINNOW_REGEN_GOLDEN=1 uv run --extra dev pytest tests/test_filter_golden.py

and commit the diff with the reason it moved.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from winnow.filter import FILTER_MIN_BYTES, apply, ledger_line, pointer

GOLDEN = Path(__file__).parent / "fixtures" / "filter_golden.json"

BIG = "x" * (FILTER_MIN_BYTES + 100)
SMALL = "y" * 10
TINY = "z" * 30  # below the pointer's own length, so guard G4 decides


def _use(uid: str, name: str, tool_input: dict) -> dict:
    return {"type": "tool_use", "id": uid, "name": name, "input": tool_input}


def _result(uid: str, content=BIG, *, is_error: bool = False, cache=None) -> dict:
    block = {"type": "tool_result", "tool_use_id": uid, "content": content,
             "is_error": is_error}
    if cache is not None:
        block["cache_control"] = cache
    return block


def _body(*messages: dict) -> dict:
    return {"model": "claude-opus-5", "max_tokens": 100, "messages": list(messages)}


def _turn(uid: str, name: str, tool_input: dict, **kw) -> list[dict]:
    return [
        {"role": "assistant", "content": [_use(uid, name, tool_input)]},
        {"role": "user", "content": [_result(uid, **kw)]},
    ]


EPHEMERAL = {"type": "ephemeral"}
ONE_HOUR = {"type": "ephemeral", "ttl": "1h"}


def _four_client_breakpoints() -> dict:
    messages = []
    for i in range(4):
        messages.extend(_turn(f"k{i}", "Bash", {"command": f"python x{i}.py"},
                              cache=EPHEMERAL))
    messages.extend(_turn("a", "Bash", {"command": "ls -la"}))
    messages.extend(_turn("b", "Bash", {"command": "git diff"}))
    return _body(*messages)


def _parallel_batch() -> dict:
    """Three calls in one turn, two of them claimed. The shape nothing
    constructed before deferral was counted in turns."""
    return _body(
        {"role": "assistant", "content": [
            _use("a", "Bash", {"command": "ls -la"}),
            _use("b", "Bash", {"command": "python train.py"}),
            _use("c", "Glob", {"pattern": "**/*.py"}),
        ]},
        {"role": "user", "content": [_result("a"), _result("b"), _result("c")]},
        *_turn("d", "Bash", {"command": "git status"}),
    )


def _already_pointered() -> dict:
    """A body that has been through the filter once. Re-deciding it would strip a
    pointer and count its bytes a second time."""
    body = _body(*_turn("a", "Bash", {"command": "ls -la"}),
                 *_turn("b", "Bash", {"command": "git diff"}))
    body["messages"][1]["content"][0]["content"] = pointer("Bash", "B2", len(BIG))
    return body


def _list_content_with_an_image() -> dict:
    """`result_size` measures this through `json.dumps`, and no other test in the
    suite builds one."""
    payload = [
        {"type": "text", "text": BIG},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": "iVBORw0KGgo="}},
    ]
    return _body(*_turn("a", "Bash", {"command": "ls -la"}, content=payload),
                 *_turn("b", "Bash", {"command": "git diff"}))


def _prefix_breakpoints() -> dict:
    """A client that spent two of its four breakpoints above the conversation.
    Counting only `messages` is how the filter could push a request to five."""
    body = _body(*_turn("a", "Bash", {"command": "ls -la"}),
                 *_turn("b", "Bash", {"command": "git diff"}))
    body["system"] = [{"type": "text", "text": "be helpful", "cache_control": ONE_HOUR}]
    body["tools"] = [{"name": "Bash", "input_schema": {}, "cache_control": ONE_HOUR}]
    return body


# `name → (body, kwargs for apply)`. Each covers one branch, and the list is
# asserted against the golden so a fixture cannot be added without regenerating.
FIXTURES: dict[str, tuple[dict, dict]] = {
    "01-one-candidate-no-client-breakpoint": (
        _body(*_turn("a", "Bash", {"command": "ls -la"}),
              *_turn("b", "Bash", {"command": "git diff"})),
        {},
    ),
    "02-client-breakpoint-on-the-candidate": (
        _body(*_turn("a", "Bash", {"command": "ls -la"}),
              *_turn("b", "Bash", {"command": "git diff"}, cache=ONE_HOUR)),
        {},
    ),
    "03-four-client-breakpoints-before-the-candidate": (_four_client_breakpoints(), {}),
    "04-parallel-batch-of-three": (_parallel_batch(), {}),
    "05-one-below-the-floor-and-one-above": (
        _body(*_turn("a", "Bash", {"command": "ls -la"}, content=SMALL),
              *_turn("b", "Bash", {"command": "git status"}),
              *_turn("c", "Bash", {"command": "git diff"})),
        {},
    ),
    "06-an-error-candidate": (
        _body(*_turn("a", "Bash", {"command": "npm run test"}, is_error=True),
              *_turn("b", "Bash", {"command": "git diff"})),
        {},
    ),
    "07-list-content-with-an-image-block": (_list_content_with_an_image(), {}),
    "08-a-body-already-carrying-a-pointer": (_already_pointered(), {}),
    "09-g4-refuses-below-the-pointer": (
        _body(*_turn("a", "Bash", {"command": "ls -la"}, content=TINY),
              *_turn("b", "Bash", {"command": "git diff"}, content=TINY)),
        {"min_bytes": 1},
    ),
    "10-breakpoints-on-system-and-tools": (_prefix_breakpoints(), {}),
    "11-keep-newest-two": (
        _body(*_turn("a", "Bash", {"command": "ls -la"}),
              *_turn("b", "Bash", {"command": "git status"}),
              *_turn("c", "Bash", {"command": "git diff"})),
        {"keep_newest": 2},
    ),
    "12-tier-c-only": (
        _body(*_turn("a", "Bash", {"command": "git status"}),
              *_turn("b", "Glob", {"pattern": "**/*.py"}),
              *_turn("c", "Bash", {"command": "git diff"})),
        {"enabled": frozenset({"C1", "C3"})},
    ),
}


def payload_for(name: str) -> dict:
    """The three things worth pinning, for one fixture.

    The emitted body is recorded as the **string** `_rewrite` would put on the
    wire, not as a parsed object and not sorted — a golden that re-serialised it
    would pin something the wire never carries. The ledger line matters as much as
    the body: it is the durable artefact two commands read, and its next migration
    changes what a key *means*, which a golden catches and a schema check does not.
    """
    body, kwargs = FIXTURES[name]
    emitted, plan = apply(copy.deepcopy(body), **kwargs)
    return {
        "emitted_body": json.dumps(emitted),
        "ledger_line": ledger_line(plan, "req_golden"),
        "plan": {
            "dropped": plan.dropped,
            "deferred": plan.deferred,
            "bytes_dropped": plan.bytes_dropped,
            "bytes_deferred": plan.bytes_deferred,
            "breakpoint_moved": plan.breakpoint_moved,
            "tool_results_seen": plan.tool_results_seen,
            "inflated": plan.inflated,
            "model": plan.model,
            "cache_ttl": plan.cache_ttl,
            "changed": plan.changed,
        },
    }


def build_golden() -> dict:
    return {name: payload_for(name) for name in sorted(FIXTURES)}


def test_the_emitted_bytes_have_not_changed():
    if os.environ.get("WINNOW_REGEN_GOLDEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(build_golden(), indent=2, sort_keys=True) + "\n")
        pytest.skip(f"regenerated {GOLDEN.name}; review and commit the diff")
    expected = json.loads(GOLDEN.read_text())
    assert sorted(expected) == sorted(FIXTURES), (
        "a fixture was added or removed without regenerating the golden"
    )
    # Per fixture rather than as one blob, so a failure names the branch that moved.
    for name in sorted(FIXTURES):
        assert payload_for(name) == expected[name], f"the filter's output moved for {name}"


def test_the_same_body_twice_is_byte_identical():
    """SPEC §10 determinism. `apply` has no clock, no counter and no random
    source, so this is a check that none has been added."""
    for name in sorted(FIXTURES):
        assert payload_for(name) == payload_for(name), name


def test_every_branch_the_fixtures_claim_to_cover_is_reached():
    """A golden whose fixtures all take the same path pins one branch twelve
    times. This asserts the set actually spreads across the outcomes."""
    outcomes = {name: payload_for(name)["plan"] for name in FIXTURES}
    assert any(p["breakpoint_moved"] for p in outcomes.values()), "placement path"
    assert any(not p["breakpoint_moved"] and p["changed"] for p in outcomes.values()), (
        "changed without moving a breakpoint"
    )
    assert any(not p["changed"] for p in outcomes.values()), "the no-op path"
    assert any(p["inflated"] for p in outcomes.values()), "guard G4"
    assert any(len(p["deferred"]) > 1 for p in outcomes.values()), "a deferred batch"
    assert any(p["cache_ttl"] == "ephemeral_1h" for p in outcomes.values()), "1h class"
    assert any(p["cache_ttl"] is None for p in outcomes.values()), "no breakpoint at all"
