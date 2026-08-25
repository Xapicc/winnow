"""The intake filter: drop a tool result before it is ever written to cache.

`winnow fork` (milestone 2) edits a conversation that is already cached, so it
pays `1.9·S − 2·D` once and earns `0.1·D` a turn back. Measured over this
operator's corpus, that nets **+3.27%** and needs a median of 182 further turns
([COZEMPIC.md](../../docs/COZEMPIC.md) §3.4). The invalidation is the whole of
that cost, and it is avoidable — but only by never letting the bytes into the
cached prefix in the first place.

**The mechanism, in one paragraph.** A tool result that a rule would strip is
sent in full on the one request where the model actually acts on it, placed
*after* the last `cache_control` breakpoint so the API never writes it to cache.
On the next request it is gone. Baseline for those bytes is a 2.0× cache write
followed by a 0.1× read on every later turn; this pays 1.0× once and nothing
after. There is no break-even: it is cheaper from the first request, at every
`S/D`, which is exactly what the pruner cannot say.

**Why it is stateless.** The decision is recomputed from the request body on
every request and depends on nothing else. That is not an implementation
convenience — a policy whose output varied between two requests over the same
conversation would change the prefix under the cache and destroy the thing it
exists to protect. The same conversation must always render to the same bytes.

**What it can and cannot decide.** Only the rules that need no hindsight: C1
(locator), C3 (passing verification) and B2 (Bash inspection), which are
decidable from the call and its `is_error` alone. C2 needs a later duplicate, B1
a later read, A1 a later edit; all three are the pruner's and stay there. The
information loss is identical to the pruner's at those three rules — this changes
what the strip costs, not what it removes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .rules import (
    LOCATOR_GREP_MODES,
    LOCATOR_TOOLS,
    VERIFICATION_RE,
    is_inspection,
    result_size,
)

# SPEC §4 G2. The same floor the pruner uses, for the same reason: below it the
# pointer costs more than the content and G4 would refuse the strip anyway.
DEFAULT_MIN_BYTES = 2048

# How many of the newest tool results are exempt. One is the design: a candidate
# is sent uncached on the request where the model acts on it and dropped on the
# next. Raising it keeps a result alive for longer but lengthens the uncached
# tail, and the tail is re-sent at 1.0× on every request it survives — so the
# guarantee "cheaper from the first request" holds at 1 and is a trade above it.
DEFAULT_KEEP_NEWEST = 1

# The API caps `cache_control` breakpoints per request. Adding one without
# removing another turns a working request into a 400.
MAX_BREAKPOINTS = 4

POINTER_RE = re.compile(r"^\[winnow: .* removed, rule [A-Z]\d, \d+ bytes")


@dataclass
class Plan:
    """What the filter did to one request, for the ledger and the tests."""

    dropped: list[dict] = field(default_factory=list)
    deferred: list[dict] = field(default_factory=list)
    bytes_dropped: int = 0
    bytes_deferred: int = 0
    breakpoint_moved: bool = False
    tool_results_seen: int = 0
    # Neither is used to decide anything; both exist so `winnow savings` can price
    # what the filter did without guessing. One ledger spans several models, and the
    # write class is a property of the request rather than of the documentation.
    model: str | None = None
    cache_ttl: str | None = None

    @property
    def changed(self) -> bool:
        return bool(self.dropped) or self.breakpoint_moved


def pointer(tool_name: str, rule: str, size: int) -> str:
    """SPEC §4's substitution discipline: a pointer, not an empty result.

    Shorter than the pruner's, and deliberately so — it carries no `winnow
    recover` command, because the filter keeps no copy. The recovery path is
    SPEC §7 route 1, the file system, which returns fresher bytes than these
    were. Saying otherwise would be a promise nothing here can keep.
    """
    return (
        f"[winnow: {tool_name} result removed, rule {rule}, {size} bytes. "
        f"Not cached, not stored. Re-run the call if it is needed again.]"
    )


def rule_for(name: str, tool_input: dict, is_error: bool) -> str | None:
    """The hindsight-free subset of SPEC §4: C1, C3, B2, or None.

    Deliberately not `inspect._first_matching_rule`: that one also answers C2,
    B1 and A1, every one of which needs to see the future of the conversation.
    Calling it here would silently make the filter's decision depend on where in
    the session the request was made, which is the one thing a cache-stable
    policy may not do.
    """
    if is_error:
        return None  # G3, and for C3 the failure is the information
    if name in LOCATOR_TOOLS:
        return "C1"
    if name == "Grep" and tool_input.get("output_mode") in LOCATOR_GREP_MODES:
        return "C1"
    if name == "Bash":
        command = tool_input.get("command")
        if isinstance(command, str) and VERIFICATION_RE.search(command):
            return "C3"
        if is_inspection(command):
            return "B2"
    return None


def _blocks(message: dict) -> list:
    content = message.get("content")
    return content if isinstance(content, list) else []


def _index_tool_uses(messages: list) -> dict[str, tuple[str, dict]]:
    index: dict[str, tuple[str, dict]] = {}
    for message in messages:
        if not isinstance(message, dict):
            continue
        for block in _blocks(message):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                use_id = block.get("id")
                if isinstance(use_id, str):
                    tool_input = block.get("input")
                    index[use_id] = (
                        block.get("name") or "",
                        tool_input if isinstance(tool_input, dict) else {},
                    )
    return index


def _strip_breakpoints_from(messages: list, start: tuple[int, int]) -> bool:
    """Remove every `cache_control` at or after `(message_index, block_index)`.

    Claude Code puts a breakpoint on the newest block. When that block is a
    candidate, leaving the breakpoint there would cache exactly the bytes the
    filter exists to keep out of the cache.
    """
    removed = False
    for m_index, message in enumerate(messages):
        if m_index < start[0] or not isinstance(message, dict):
            continue
        for b_index, block in enumerate(_blocks(message)):
            if m_index == start[0] and b_index < start[1]:
                continue
            if isinstance(block, dict) and block.pop("cache_control", None) is not None:
                removed = True
    return removed


def _count_breakpoints(messages: list) -> int:
    return sum(
        1
        for message in messages
        if isinstance(message, dict)
        for block in _blocks(message)
        if isinstance(block, dict) and "cache_control" in block
    )


def _place_breakpoint_before(messages: list, position: tuple[int, int], ttl: str | None) -> bool:
    """Put a breakpoint on the last block before `position`, so everything up to
    the candidate is cached and the candidate is not."""
    m_index, b_index = position
    for m in range(m_index, -1, -1):
        message = messages[m]
        if not isinstance(message, dict):
            continue
        blocks = _blocks(message)
        last = (b_index - 1) if m == m_index else (len(blocks) - 1)
        for b in range(last, -1, -1):
            block = blocks[b]
            if not isinstance(block, dict):
                continue
            if "cache_control" in block:
                return False  # already the boundary; nothing to move
            control = {"type": "ephemeral"}
            if ttl:
                control["ttl"] = ttl
            block["cache_control"] = control
            return True
    return False


def _ttl_in_force(messages: list) -> str | None:
    """Which cache write class this request would actually have been billed at.

    Named for `usage.cache_creation`'s own keys so the ledger and the transcript can
    be compared without a mapping. It is read rather than looked up: COZEMPIC §3.1 is
    the record of taking the 1.25× five-minute figure from the documentation and
    understating an invalidation by about 40%. A request carrying no breakpoint at all
    has no class, and says so rather than defaulting to one.
    """
    if not _count_breakpoints(messages):
        return None
    return "ephemeral_1h" if _existing_ttl(messages) == "1h" else "ephemeral_5m"


def _existing_ttl(messages: list) -> str | None:
    """Whatever TTL the client was already asking for, so the filter never
    silently reprices a request from the 1h class to the 5m one."""
    for message in messages:
        if not isinstance(message, dict):
            continue
        for block in _blocks(message):
            if isinstance(block, dict) and isinstance(block.get("cache_control"), dict):
                ttl = block["cache_control"].get("ttl")
                if isinstance(ttl, str):
                    return ttl
    return None


def apply(
    body: dict,
    min_bytes: int = DEFAULT_MIN_BYTES,
    keep_newest: int = DEFAULT_KEEP_NEWEST,
) -> tuple[dict, Plan]:
    """Rewrite one Messages API request body in place, and say what changed.

    Returns `(body, plan)`. The body is mutated, which is what the proxy wants;
    the caller owns the copy if it needs the original.
    """
    plan = Plan()
    messages = body.get("messages")
    if not isinstance(messages, list):
        return body, plan

    model = body.get("model")
    plan.model = model if isinstance(model, str) else None
    plan.cache_ttl = _ttl_in_force(messages)

    uses = _index_tool_uses(messages)

    # Every tool_result in wire order, with the rule that would fire on it.
    results: list[tuple[int, int, dict, str | None, int]] = []
    for m_index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        for b_index, block in enumerate(_blocks(message)):
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            plan.tool_results_seen += 1
            content = block.get("content")
            # A result already carrying a pointer has been through this filter on
            # an earlier request. Re-deciding it would strip a pointer and count
            # its bytes a second time, which is the double-count `79dd165`
            # records for the pruner's own re-runs.
            if isinstance(content, str) and POINTER_RE.match(content):
                continue
            name, tool_input = uses.get(block.get("tool_use_id", ""), ("", {}))
            rule = rule_for(name, tool_input, bool(block.get("is_error")))
            size = result_size(content)
            results.append((m_index, b_index, block, rule, size))

    candidates = [r for r in results if r[3] is not None and r[4] >= min_bytes]
    if not candidates:
        return body, plan

    # The newest `keep_newest` results are exempt: the model is still acting on
    # them. Exemption is counted over *all* results, not only candidates, so a
    # candidate two calls back is dropped even when the two after it are not.
    exempt_from = len(results) - keep_newest
    exempt_ids = {id(results[i][2]) for i in range(max(0, exempt_from), len(results))}

    newest_candidate: tuple[int, int] | None = None
    for m_index, b_index, block, rule, size in candidates:
        name = uses.get(block.get("tool_use_id", ""), ("", {}))[0]
        if id(block) in exempt_ids:
            # Kept this turn, dropped on the next. Remember where it sits so the
            # breakpoint can be moved in front of it and it is never written.
            newest_candidate = (m_index, b_index)
            plan.deferred.append(_entry(block, name, rule, size))
            plan.bytes_deferred += size
            continue
        block["content"] = pointer(name or "tool", rule, size)
        block.pop("cache_control", None)
        plan.dropped.append(_entry(block, name, rule, size))
        plan.bytes_dropped += size

    if newest_candidate is not None:
        ttl = _existing_ttl(messages)
        _strip_breakpoints_from(messages, newest_candidate)
        if _count_breakpoints(messages) < MAX_BREAKPOINTS:
            plan.breakpoint_moved = _place_breakpoint_before(messages, newest_candidate, ttl)
    return body, plan


def _entry(block: dict, name: str, rule: str, size: int) -> dict:
    """One ledger entry for one result.

    `tool_use_id` is the whole reason this is a function. The filter is stateless, so
    it re-drops the same result on every later request that still carries it, and a
    ledger without an identity for the result cannot tell one removal from its own
    echo — summing `bytes_dropped` over lines overstated this operator's by 27.2×.
    See `savings.py`.
    """
    use_id = block.get("tool_use_id")
    return {
        "tool": name,
        "rule": rule,
        "bytes": size,
        "tool_use_id": use_id if isinstance(use_id, str) else None,
    }


def ledger_line(plan: Plan, request_id: str | None = None) -> str:
    """One JSON line per changed request.

    The filter never touches the transcript — Claude Code writes what it holds,
    which still contains every byte the API never saw. So `winnow inspect` read
    off disk overstates both `D` and `S` for any session this filtered, and
    `winnow fork` would pay `1.9·S` to remove bytes that are not in the prefix.
    This line is what lets the pruner know, and it is the reason the two can run
    together at all.

    `model`, `cache_ttl` and each entry's `tool_use_id` are here for the second
    reader, `winnow savings`: identity so a removal is not counted once per surviving
    request, and the model and write class so it is priced at what this request would
    have cost rather than at a documentation figure. Lines written before those fields
    existed are readable without them, at a cost that reader reports.
    """
    return json.dumps(
        {
            "request_id": request_id,
            "model": plan.model,
            "cache_ttl": plan.cache_ttl,
            "dropped": plan.dropped,
            "deferred": plan.deferred,
            "bytes_dropped": plan.bytes_dropped,
            "bytes_deferred": plan.bytes_deferred,
            "tool_results_seen": plan.tool_results_seen,
        },
        sort_keys=True,
    )
