"""The cache-write invariant, asserted over grown conversations rather than examples.

Everything the intake filter is rests on one sentence, and until this file it was
written nowhere as a checkable statement:

> **No result whose rendering the filter will later change may sit at or before
> the last `cache_control` breakpoint in the request it emits.**

It has two halves, checked at different times:

**W1, per request.** In the body `apply` returns, every *deferred* candidate is
strictly after the last breakpoint. A deferred candidate is the only kind of
block whose rendering is going to change.

**W2, across a conversation.** Replay a growing message list request by request.
Once a block has been at or before the last breakpoint on some request, its
rendering never changes on any later one.

W2 is the property that matters and W1 is how the code buys it. `filter.py`
states the consequence of losing it — *"a policy whose output varied between two
requests over the same conversation would change the prefix under the cache and
destroy the thing it exists to protect"* — and the licence is precise: the rule
is not "the bytes never change", it is "the bytes never change once they have
been cache-written", and the filter buys its one exception by controlling where
the prefix ends.

**Writing the property down was enough to break the mechanism.** At
`--keep-newest 2`, a documented flag, a deferred result was cache-written in full
and then replaced by a pointer on the next request — `1.9·S` on a warm cache,
once per turn, in the component built to avoid paying it once. Five hand-built
breakpoint tests passed while it happened, because the examples in a test file
are the cases somebody already reasoned about correctly. The seed for this work
asked about the two paths that looked dangerous — the breakpoint-cap branch and
`_place_breakpoint_before`'s early return — and both turned out to be safe. The
path nobody suspected was not.

Stdlib only, so no Hypothesis: a hand-rolled generator explores a grid the author
thought of and the shrinking that makes property testing pleasant is absent. That
is a real limitation and it found the defect anyway, because the defect is at
`keep_newest = 2` and any grid over that parameter reaches it.

Seeds are fixed and listed, so this is a regression pin rather than a flaky test,
and a failure names the seed. It deliberately does **not** assert on exact byte
output — that is `test_filter_golden.py`, a different instrument. A property test
does not notice a reworded pointer; a golden does not notice a body nobody wrote
down.
"""

from __future__ import annotations

import copy
import json
import random

import pytest

from winnow.filter import FILTER_MIN_BYTES, MAX_BREAKPOINTS, apply

# Fixed and listed. Enough of them that the grid below is actually covered, few
# enough that a failure is readable.
SEEDS = tuple(range(40))

# The calls the generator draws from, and the rule each one lands on. `None` is a
# result no rule claims, which is the collateral the breakpoint moves in front of.
CALLS = [
    ("Bash", {"command": "ls -la"}, "B2"),
    ("Bash", {"command": "git status"}, "B2"),
    ("Bash", {"command": "npm run test"}, "C3"),
    ("Bash", {"command": "pytest -q"}, "C3"),
    ("Glob", {"pattern": "**/*.py"}, "C1"),
    ("LS", {"path": "/repo"}, "C1"),
    ("Grep", {"output_mode": "files_with_matches", "pattern": "x"}, "C1"),
    ("Bash", {"command": "python train.py"}, None),
    ("Read", {"file_path": "/repo/x.py"}, None),
    ("Edit", {"file_path": "/repo/x.py"}, None),
]

# Sizes drawn to straddle the floor, including the exact boundary and the region
# where guard G4 decides.
SIZES = [0, 1, 40, 112, 113, 200, FILTER_MIN_BYTES - 1, FILTER_MIN_BYTES,
         FILTER_MIN_BYTES + 1, 900, 4000]


def _content(rng: random.Random, size: int):
    """A result's content, in one of the shapes the wire actually carries.

    A list-form content with an image block is a shape no other test in this
    suite constructs, and `result_size` measures it through `json.dumps`.
    """
    text = "x" * size
    roll = rng.random()
    if roll < 0.80:
        return text
    if roll < 0.90:
        return [{"type": "text", "text": text}]
    return [
        {"type": "text", "text": text},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": "iVBOR" * 4}},
    ]


def generate_turns(rng: random.Random, count: int) -> list[dict]:
    """`count` assistant turns and the user messages answering them.

    One turn is one assistant message holding 1-4 `tool_use` blocks. Its answers
    come back either as one user message with several `tool_result` blocks or as
    one message each — both layouts, because the filter must group by the *call*
    and every user record in this operator's corpus carries exactly one result.
    """
    messages: list[dict] = []
    uid = 0
    for _ in range(count):
        batch = rng.randint(1, 4)
        uses, results = [], []
        for _ in range(batch):
            uid += 1
            name, tool_input, _rule = rng.choice(CALLS)
            uses.append({"type": "tool_use", "id": f"t{uid}",
                         "name": name, "input": tool_input})
            block = {"type": "tool_result", "tool_use_id": f"t{uid}",
                     "content": _content(rng, rng.choice(SIZES))}
            if rng.random() < 0.15:
                block["is_error"] = True
            results.append(block)
        messages.append({"role": "assistant", "content": uses})
        if rng.random() < 0.5:
            messages.append({"role": "user", "content": results})
        else:
            messages.extend({"role": "user", "content": [b]} for b in results)
        # An occasional plain-text user turn, and an occasional string-valued
        # message content, which `_blocks` has to survive.
        if rng.random() < 0.15:
            messages.append({"role": "user", "content": "carry on"})
        if rng.random() < 0.08:
            messages.append({"role": "assistant", "content": [{"type": "text",
                                                               "text": "thinking"}]})
    return messages


def place_breakpoints(rng: random.Random, body: dict) -> None:
    """0-4 client breakpoints, over all three regions a `cache_control` may sit in.

    Weighted towards the newest block, because that is where Claude Code puts one
    and it is the case the strip-then-place path exists for.
    """
    blocks = [
        block
        for section in ("tools", "system")
        for block in (body.get(section) or [])
        if isinstance(block, dict)
    ]
    blocks.extend(
        block
        for message in (body.get("messages") or [])
        if isinstance(message, dict) and isinstance(message.get("content"), list)
        for block in message["content"]
        if isinstance(block, dict)
    )
    if not blocks:
        return
    wanted = rng.randint(0, MAX_BREAKPOINTS)
    chosen: list[dict] = []
    if wanted and rng.random() < 0.6:
        chosen.append(blocks[-1])  # the newest block, where Claude Code puts one
        wanted -= 1
    if wanted:
        pool = [b for b in blocks if b is not (chosen[0] if chosen else None)]
        chosen.extend(rng.sample(pool, min(wanted, len(pool))))
    ttl = {"type": "ephemeral"}
    if rng.random() < 0.4:
        ttl = {"type": "ephemeral", "ttl": "1h"}
    for block in chosen:
        block["cache_control"] = dict(ttl)


def generate_body(rng: random.Random, turns: int) -> dict:
    body = {"model": "claude-opus-5", "max_tokens": 100,
            "messages": generate_turns(rng, turns)}
    if rng.random() < 0.5:
        body["system"] = [{"type": "text", "text": "be helpful"}]
    if rng.random() < 0.5:
        body["tools"] = [{"name": "Bash", "description": "run", "input_schema": {}}]
    # Shapes a real wire eventually produces and no other test constructs.
    if rng.random() < 0.10 and body["messages"]:
        body["messages"].append({"role": "user", "content": ["not a dict", 7, None]})
    if rng.random() < 0.10 and body["messages"]:
        body["messages"].append(None)
    if rng.random() < 0.10:
        for message in body["messages"]:
            if isinstance(message, dict) and isinstance(message.get("content"), list):
                for block in message["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        block.pop("tool_use_id", None)
                        break
                break
    return body


# ─── Reading a body back ─────────────────────────────────────────────────────


def all_breakpoints(body: dict) -> list[tuple[int, int]]:
    """Message-region breakpoints, in wire order."""
    return [
        (m, b)
        for m, message in enumerate(body.get("messages") or [])
        if isinstance(message, dict) and isinstance(message.get("content"), list)
        for b, block in enumerate(message["content"])
        if isinstance(block, dict) and "cache_control" in block
    ]


def total_breakpoints(body: dict) -> int:
    """Every `cache_control` in the request. The cap is over all three regions,
    and counting only `messages` is how the filter could push a request to five."""
    count = len(all_breakpoints(body))
    for key in ("system", "tools"):
        section = body.get(key)
        if isinstance(section, list):
            count += sum(1 for b in section
                         if isinstance(b, dict) and "cache_control" in b)
    return count


def result_positions(body: dict) -> dict[str, tuple[int, int]]:
    return {
        block["tool_use_id"]: (m, b)
        for m, message in enumerate(body.get("messages") or [])
        if isinstance(message, dict) and isinstance(message.get("content"), list)
        for b, block in enumerate(message["content"])
        if isinstance(block, dict) and block.get("type") == "tool_result"
        and isinstance(block.get("tool_use_id"), str)
    }


def renderings(body: dict) -> dict[str, str]:
    return {
        block["tool_use_id"]: json.dumps(block.get("content"), sort_keys=True)
        for m, message in enumerate(body.get("messages") or [])
        if isinstance(message, dict) and isinstance(message.get("content"), list)
        for block in message["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
        and isinstance(block.get("tool_use_id"), str)
    }


def pairing(body: dict) -> tuple[list[str], list[str]]:
    uses, results = [], []
    for message in body.get("messages") or []:
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue
        for block in message["content"]:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and isinstance(block.get("id"), str):
                uses.append(block["id"])
            elif (block.get("type") == "tool_result"
                  and isinstance(block.get("tool_use_id"), str)):
                results.append(block["tool_use_id"])
    return sorted(uses), sorted(results)


# ─── W1: one call ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("keep_newest", [1, 2, 3])
@pytest.mark.parametrize("seed", SEEDS)
def test_w1_every_deferred_candidate_is_after_the_last_breakpoint(seed, keep_newest):
    """The three lines that fail on the old code at `keep_newest = 2`."""
    rng = random.Random(seed)
    body = generate_body(rng, rng.randint(1, 8))
    place_breakpoints(rng, body)
    original = copy.deepcopy(body)

    _, plan = apply(body, keep_newest=keep_newest)
    if not plan.deferred:
        return
    breaks = all_breakpoints(body)
    if not breaks:
        return  # nothing is cached at all, so nothing can be cache-written
    last = max(breaks)
    positions = result_positions(body)
    for entry in plan.deferred:
        use_id = entry["tool_use_id"]
        if use_id is None:
            continue
        assert positions[use_id] > last, (
            f"seed={seed} keep_newest={keep_newest}: deferred {use_id} at "
            f"{positions[use_id]} is at or before the last breakpoint {last}, so "
            f"the API caches bytes the next request replaces with a pointer\n"
            f"{json.dumps(original)[:2000]}"
        )


@pytest.mark.parametrize("keep_newest", [1, 2, 3])
@pytest.mark.parametrize("seed", SEEDS)
def test_the_cap_holds_across_all_three_regions(seed, keep_newest):
    """W1 is not the property that catches this: it needs its own assertion. The
    API caps `cache_control` per request over `system`, `tools` and `messages`
    together, and the fifth is a 400 rather than a lost saving."""
    rng = random.Random(seed)
    body = generate_body(rng, rng.randint(1, 8))
    place_breakpoints(rng, body)
    before = total_breakpoints(body)
    assert before <= MAX_BREAKPOINTS, "the generator must respect the cap it tests"

    apply(body, keep_newest=keep_newest)
    assert total_breakpoints(body) <= MAX_BREAKPOINTS, f"seed={seed}"


@pytest.mark.parametrize("seed", SEEDS)
def test_g5_pairing_survives(seed):
    """The multiset of `tool_use` ids equals the multiset of `tool_use_id`s,
    before and after. The API requires every call to be answered, and a filter
    that removed a block rather than replacing its content would 400 the
    request."""
    rng = random.Random(seed)
    body = generate_body(rng, rng.randint(1, 8))
    place_breakpoints(rng, body)
    before = pairing(body)
    apply(body)
    assert pairing(body) == before, f"seed={seed}"


# ─── W2: the replay ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("keep_newest", [1, 2, 3])
@pytest.mark.parametrize("seed", SEEDS)
def test_w2_a_rendering_never_changes_once_it_has_been_cache_written(seed, keep_newest):
    """The property the whole design is.

    A *fresh* copy per request, built from the client's own bytes plus one more
    turn — which is what Claude Code sends, and the reason the existing
    idempotence test does not model this: that one re-applies `apply` to the same
    body, which is a different property.
    """
    rng = random.Random(seed)
    turns = generate_turns(rng, 8)
    breakpoint_rng = random.Random(seed + 10_000)

    # `tool_use_id → the rendering it had when it was first inside the write region`
    written: dict[str, str] = {}

    for count in range(1, len(turns) + 1):
        body = {"model": "claude-opus-5", "max_tokens": 100,
                "messages": copy.deepcopy(turns[:count])}
        place_breakpoints(random.Random(breakpoint_rng.randint(0, 1 << 30)), body)
        apply(body, keep_newest=keep_newest)

        breaks = all_breakpoints(body)
        last = max(breaks) if breaks else None
        rendered = renderings(body)
        positions = result_positions(body)

        for use_id, text in rendered.items():
            if use_id in written:
                assert text == written[use_id], (
                    f"seed={seed} keep_newest={keep_newest} at turn {count}: "
                    f"{use_id} was cache-written as {written[use_id][:80]!r} and is "
                    f"now {text[:80]!r}. The prefix match breaks at its position "
                    f"and everything behind it is re-written at 2.0x."
                )
            elif last is not None and positions[use_id] <= last:
                written[use_id] = text


@pytest.mark.parametrize("seed", SEEDS)
def test_a_pointer_is_never_re_dropped_or_re_counted(seed):
    """Invariant I8, which is what `POINTER_RE` exists for, over generated bodies
    rather than one hand-built pair. Re-deciding a result that already carries a
    pointer would strip the pointer and count its bytes a second time."""
    rng = random.Random(seed)
    body = generate_body(rng, rng.randint(2, 8))
    place_breakpoints(rng, body)
    apply(body)
    once = json.dumps(body, sort_keys=True)
    _, second = apply(body)
    assert second.bytes_dropped == 0, f"seed={seed}"
    assert json.dumps(body, sort_keys=True) == once, f"seed={seed}"


@pytest.mark.parametrize("seed", SEEDS)
def test_an_error_result_is_never_removed(seed):
    """G3, over the grid. `is_error` is drawn true about one time in seven, and
    C3's whole rationale is that a failing verification is the information."""
    rng = random.Random(seed)
    body = generate_body(rng, rng.randint(1, 8))
    errored = {
        block["tool_use_id"]
        for message in (body.get("messages") or [])
        if isinstance(message, dict) and isinstance(message.get("content"), list)
        for block in message["content"]
        if isinstance(block, dict) and block.get("is_error")
        and isinstance(block.get("tool_use_id"), str)
    }
    place_breakpoints(rng, body)
    _, plan = apply(body)
    touched = {entry["tool_use_id"] for entry in plan.dropped}
    assert not (touched & errored), f"seed={seed}"


@pytest.mark.parametrize("seed", SEEDS)
def test_nothing_admitted_ever_inflates(seed):
    """G4, over the grid: no result is replaced by a pointer longer than itself."""
    rng = random.Random(seed)
    body = generate_body(rng, rng.randint(1, 8))
    place_breakpoints(rng, body)
    _, plan = apply(body)
    for entry in plan.dropped:
        pointer_text = None
        for message in (body.get("messages") or []):
            if not isinstance(message, dict) or not isinstance(message.get("content"), list):
                continue
            for block in message["content"]:
                if (isinstance(block, dict)
                        and block.get("tool_use_id") == entry["tool_use_id"]):
                    pointer_text = block["content"]
        assert pointer_text is not None
        assert len(pointer_text) <= entry["bytes"], f"seed={seed}: {entry}"
