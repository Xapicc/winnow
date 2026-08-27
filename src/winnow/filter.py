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
    LOCATOR_TOOLS,
    STATELESS_RULES,
    inflates,
    result_size,
    stateless_rule_for,
)

# SPEC §4 G2. **Deliberately not the pruner's 2,048**, and the divergence is the
# point rather than an oversight — `rules.DEFAULT_MIN_BYTES` stays at 2,048
# because the pruner's comparison really is file bytes against a 163-byte
# pointer with a whole session's `S` behind it.
#
# The filter's arithmetic is different. A candidate is sent once in full and the
# pointer then lives in the cached prefix, so with `P` the pointer's length and
# `T` the turns that follow, the strip pays when
#
#     D  >  P · (2.0 + 0.1T) / (1.0 + 0.1T)
#
# which is bounded between `P` and `2P` at every `T` — 230 bytes at T=0, 120 at
# T=224. No session length makes 2,048 right for this component. The comment
# that used to sit here claimed otherwise, on the pruner's reasoning, and its
# second clause — "G4 would refuse the strip anyway" — was wrong twice over:
# G4 refuses only below the pointer's own length, and until now the filter did
# not implement G4 at all.
DEFAULT_MIN_BYTES = 2048

# The tool names `rule_for` can fire on. `pointer` interpolates one of them, so
# the longest bounds the pointer's own length — which is what makes the
# `--min-bytes` floor below checkable before a single request arrives. Widening
# `rule_for` past these four literals moves that bound and re-opens the unbounded
# tool name `rules._safe_tool_name` exists for.
FILTER_TOOL_NAMES = frozenset(LOCATOR_TOOLS | {"Grep", "Bash"})

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
    # Guard G4's refusals. A count rather than the results themselves: `plan.py`
    # keeps them so `--explain` can name them, and the filter has no `--explain`.
    # It is a number rather than a silence because a strip that inflates is a
    # silent fallback in both directions at once — the request grows and the
    # ledger records a saving.
    inflated: int = 0
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


def longest_pointer(size: int) -> int:
    """The longest pointer this filter can produce for a result of `size` bytes.

    Bounded because `rule_for` fires on four literal tool names and three
    two-character rule ids, so the only free term is the size's own digit count.
    """
    return max(
        len(pointer(name, rule, size))
        for name in FILTER_TOOL_NAMES
        for rule in ("C1", "C3", "B2")
    )


def smallest_safe_min_bytes() -> int:
    """The lowest `min_bytes` at which no admitted result can inflate.

    Guard G4 refuses a strip whose pointer is longer than the content it
    replaces, so a floor below this admits results the guard then refuses — a
    flag that reads as "strip more" and does nothing. Making that a usage error
    at parse time is SPEC §10's discipline: no fallback that silently keeps a
    result the operator asked to strip.

    The crossing is unique. `longest_pointer` grows by one byte per decade of
    `size`, so once `longest_pointer(D) <= D` the same holds for every larger
    `D`, and the first crossing is the answer.
    """
    size = 1
    while longest_pointer(size) > size:
        size += 1
    return size


def rule_for(
    name: str,
    tool_input: dict,
    is_error: bool,
    enabled: frozenset[str] = STATELESS_RULES,
) -> str | None:
    """The prefix-determined subset of SPEC §4: C1, C3, B2, or None.

    Deliberately not `inspect._first_matching_rule`: that one also answers C2,
    B1 and A1, every one of which needs to see the future of the conversation.
    Calling it here would silently make the filter's decision depend on where in
    the session the request was made, which is the one thing a cache-stable
    policy may not do.

    `enabled` is SPEC §8's rule selection, resolved once at process start and
    held in `proxy.Config`. It must not be re-read per request: `default_disabled`
    reads `os.environ` at call time, and a filter whose verdict could change
    because somebody exported a variable in another shell would render the same
    conversation two ways — the §K1 break, arriving from outside the process.

    **What is left here is guard G3 and nothing else.** The three rules themselves
    live in `rules.stateless_rule_for`, so the filter is no longer a fourth
    opinion about what a locator or an inspection is. G3 stays here because the
    contracts differ and the difference is the trap: `classify` applies G1, G2, G3
    and G5 before the shared engine is entered, and this is handed unguarded
    blocks straight off the wire. Both are correct in their own component; called
    across the boundary the mismatch is silent and it strips exactly the results
    SPEC §4 says must never be stripped.
    """
    if is_error:
        return None  # G3, and for C3 the failure is the information
    return stateless_rule_for(name, tool_input, enabled)


def _blocks(message: dict) -> list:
    content = message.get("content")
    return content if isinstance(content, list) else []


def _index_tool_uses(messages: list) -> dict[str, tuple[str, dict, int]]:
    """`tool_use_id → (tool name, input, the message index of the *call*)`.

    The third element is what makes deferral a property of the turn rather than
    of the result. The model issues a parallel batch as several `tool_use` blocks
    in one assistant message; whether the answers come back as one user message
    with several `tool_result` blocks or as several user messages is a wire
    detail nothing in a transcript can settle — every user record in this corpus
    carries exactly one `tool_result`, 64,651 of 64,651 — so the assistant
    message the results answer is the only grouping that is correct under either
    layout.
    """
    index: dict[str, tuple[str, dict, int]] = {}
    for m_index, message in enumerate(messages):
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
                        m_index,
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


def _prefix_blocks(body: dict) -> list:
    """The blocks of `system` and `tools`, the two places above the conversation
    where a `cache_control` can sit.

    A Messages API request carries three cacheable regions and the invalidation
    cascade runs tools → system → messages, so a breakpoint on either of the
    first two is as real as one in a message and counts against the same cap.
    `system` may also arrive as a plain string, which carries no block and so no
    breakpoint.
    """
    blocks: list = []
    for key in ("tools", "system"):
        section = body.get(key)
        if isinstance(section, list):
            blocks.extend(block for block in section if isinstance(block, dict))
    return blocks


def _count_breakpoints(body: dict) -> int:
    """Every `cache_control` in the request, not only the ones in `messages`.

    Counting only `messages` made the cap check an undercount: a client placing a
    breakpoint on `system` or on a tool definition — which Claude Code is free to
    do, and which nothing here can see from a transcript — left the filter
    believing it had a slot free when it did not, and adding the fifth turns a
    working request into a 400. The property test asserts the total rather than
    the message count for exactly this reason.
    """
    messages = body.get("messages")
    blocks = list(_prefix_blocks(body))
    if isinstance(messages, list):
        blocks.extend(
            block
            for message in messages
            if isinstance(message, dict)
            for block in _blocks(message)
            if isinstance(block, dict)
        )
    return sum(1 for block in blocks if "cache_control" in block)


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


def _ttl_in_force(body: dict) -> str | None:
    """Which cache write class this request would actually have been billed at.

    Named for `usage.cache_creation`'s own keys so the ledger and the transcript can
    be compared without a mapping. It is read rather than looked up: COZEMPIC §3.1 is
    the record of taking the 1.25× five-minute figure from the documentation and
    understating an invalidation by about 40%. A request carrying no breakpoint at all
    has no class, and says so rather than defaulting to one — and "at all" now
    includes a breakpoint on `system` or `tools`, so a request cached only above
    the conversation is no longer priced as if it were uncached.
    """
    if not _count_breakpoints(body):
        return None
    return "ephemeral_1h" if _existing_ttl(body) == "1h" else "ephemeral_5m"


def _existing_ttl(body: dict) -> str | None:
    """Whatever TTL the client was already asking for, so the filter never
    silently reprices a request from the 1h class to the 5m one.

    `system` and `tools` are read first because they are first in the cache key:
    a client that asks for a one-hour prefix and leaves the conversation's own
    breakpoints implicit is asking for one-hour, and reading only `messages`
    would have answered from the wrong region.
    """
    messages = body.get("messages")
    blocks = list(_prefix_blocks(body))
    if isinstance(messages, list):
        blocks.extend(
            block
            for message in messages
            if isinstance(message, dict)
            for block in _blocks(message)
            if isinstance(block, dict)
        )
    for block in blocks:
        if isinstance(block.get("cache_control"), dict):
            ttl = block["cache_control"].get("ttl")
            if isinstance(ttl, str):
                return ttl
    return None


def apply(
    body: dict,
    min_bytes: int = DEFAULT_MIN_BYTES,
    keep_newest: int = DEFAULT_KEEP_NEWEST,
    enabled: frozenset[str] = STATELESS_RULES,
) -> tuple[dict, Plan]:
    """Rewrite one Messages API request body in place, and say what changed.

    Returns `(body, plan)`. The body is mutated, which is what the proxy wants;
    the caller owns the copy if it needs the original.

    `enabled` defaults to every prefix-determined rule, which is what the filter
    did before it could be told otherwise. It is resolved at startup and held in
    `proxy.Config`; see `rule_for` for why it may not be resolved per request.
    """
    plan = Plan()
    messages = body.get("messages")
    if not isinstance(messages, list):
        return body, plan

    model = body.get("model")
    plan.model = model if isinstance(model, str) else None
    plan.cache_ttl = _ttl_in_force(body)

    uses = _index_tool_uses(messages)

    # Every tool_result in wire order, with the rule that would fire on it and
    # the assistant turn it answers.
    results: list[tuple[int, int, dict, str | None, int, int]] = []
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
            name, tool_input, turn = uses.get(
                block.get("tool_use_id", ""), ("", {}, m_index)
            )
            rule = rule_for(name, tool_input, bool(block.get("is_error")), enabled)
            size = result_size(content)
            results.append((m_index, b_index, block, rule, size, turn))

    # G2 the size floor, then G4 no net inflation. G4 is the one guard SPEC §4
    # applies *after* a rule has fired, because it compares the result against the
    # pointer that would replace it and the pointer names the rule. It is applied
    # here rather than at the substitution below so that a result the pointer would
    # inflate is not a candidate at all — otherwise it could be the deferred one,
    # and the breakpoint would be moved in front of a result nothing will replace.
    #
    # `rules.inflates` rather than a comparison written out here: the filter is the
    # fourth reader of SPEC §4 and it must not acquire a fourth opinion about a
    # guard. The pointer computed for the test is the one that gets used.
    candidates: list[tuple[int, int, dict, str, int, str, str]] = []
    for m_index, b_index, block, rule, size, _turn in results:
        if rule is None or size < min_bytes:
            continue
        name = uses.get(block.get("tool_use_id", ""), ("", {}, m_index))[0]
        text = pointer(name or "tool", rule, size)
        if inflates(text, size):
            plan.inflated += 1
            continue
        candidates.append((m_index, b_index, block, rule, size, name, text))
    if not candidates:
        return body, plan

    # The results answering the newest `keep_newest` assistant **turns** are
    # exempt: the model is still acting on them. Exemption is counted over *all*
    # results, not only candidates, so a candidate two turns back is dropped even
    # when the ones after it are not.
    #
    # **Turns, not results, and this is the correction.** The module docstring's
    # own sentence is that a candidate "is sent in full on the one request where
    # the model actually acts on it"; counting the last `keep_newest` entries of a
    # flat list does not say that. When the model issues several tool calls in one
    # turn, only the last answer was exempt and the rest were replaced by pointers
    # on the very request carrying them to the model for the first time. Measured
    # over 866 transcripts: 15.58% of tool-issuing requests are parallel batches,
    # and **one byte in seven of everything the filter removes was removed before
    # the model had read it** — 3,516,979 bytes across 332 sessions. The model
    # asked three questions and got one answer and two receipts.
    #
    # It is not a cache break — those results render as a pointer from their first
    # request onward and never change — which is why nothing caught it. It is an
    # information failure, invisible in every number the filter reports, and it
    # makes milestone 3's quality arm unmeasurable: an arm that sometimes withholds
    # an answer the model asked for is not "the same session with once-only results
    # removed", so a difference in task success cannot be attributed.
    #
    # Grouped on the *`tool_use` block's* message index rather than the
    # `tool_result`'s own, because the two disagree exactly where it matters. A
    # parallel batch is one assistant message and, on this corpus, several user
    # records — every user record carries exactly one `tool_result`, 64,651 of
    # 64,651 — so grouping by the message the results sit in would restore the
    # defect for the layout Claude Code actually writes. Grouping by the call is
    # correct under either wire layout.
    exempt_ids: set[int] = set()
    if keep_newest > 0:
        turns: list[int] = []
        for entry in results:
            if entry[5] not in turns:
                turns.append(entry[5])
        exempt_turns = set(turns[-keep_newest:])
        exempt_ids = {id(entry[2]) for entry in results if entry[5] in exempt_turns}

    # The *oldest* deferred candidate, not the newest. The breakpoint goes in
    # front of this one, so every deferred candidate ends up strictly after the
    # boundary and none of them is cache-written. Keeping the latest instead —
    # which is what this did, under the name `newest_candidate` — left every
    # earlier exempt candidate inside the write region, so at `--keep-newest 2`
    # the API cached bytes the next request replaced with a pointer: a prefix
    # break worth `1.9·S` on every request from the third onward, in the
    # component built to avoid paying it once.
    oldest_deferred: tuple[int, int] | None = None
    for m_index, b_index, block, rule, size, name, text in candidates:
        if id(block) in exempt_ids:
            # Kept this turn, dropped on the next. Remember where the earliest
            # of them sits so the breakpoint can be moved in front of the whole
            # deferred group and none of it is ever written.
            if oldest_deferred is None:
                oldest_deferred = (m_index, b_index)
            plan.deferred.append(_entry(block, name, rule, size))
            plan.bytes_deferred += size
            continue
        block["content"] = text
        block.pop("cache_control", None)
        plan.dropped.append(_entry(block, name, rule, size))
        plan.bytes_dropped += size

    if oldest_deferred is not None:
        ttl = _existing_ttl(body)
        _strip_breakpoints_from(messages, oldest_deferred)
        if _count_breakpoints(body) < MAX_BREAKPOINTS:
            plan.breakpoint_moved = _place_breakpoint_before(messages, oldest_deferred, ttl)
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
