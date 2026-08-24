"""Standard-tier strategies: recommended pruning with cross-message correlation."""

from __future__ import annotations

import hashlib
import json
import re

from ..helpers import get_content_blocks, get_msg_type, hashable_str, is_protected, msg_bytes, set_content_blocks, text_of
from ..registry import strategy
from ..types import Message, PruneAction, StrategyResult
from ._config import coerce_choice, coerce_non_negative_int, coerce_ordered_pair

_THINKING_MODES: tuple[str, ...] = ("remove", "truncate", "signature-only")


@strategy("thinking-blocks", "Truncate or remove thinking/signature blocks", "standard", "2-5%")
def strategy_thinking_blocks(messages: list[Message], config: dict) -> StrategyResult:
    """Remove or truncate thinking blocks and signatures from assistant messages.

    Modes (via config['thinking_mode']):
        'remove'         - Remove thinking blocks entirely (default)
        'truncate'       - Keep first 200 chars of thinking
        'signature-only' - Only strip signature fields
    """
    mode = coerce_choice(config, "thinking_mode", _THINKING_MODES, default="remove")
    actions: list[PruneAction] = []
    total_orig = sum(b for _, _, b in messages)
    total_pruned = 0
    replaced = 0

    for pos, (idx, msg, size) in enumerate(messages):
        if is_protected(msg):
            continue
        if get_msg_type(msg) != "assistant":
            continue

        blocks = get_content_blocks(msg)
        if not blocks:
            continue

        new_blocks = []
        changed = False
        for block in blocks:
            btype = block.get("type", "")
            if btype == "thinking":
                changed = True
                if mode == "remove":
                    continue
                elif mode == "truncate":
                    thinking = block.get("thinking", "")
                    new_block = {k: v for k, v in block.items() if k != "signature"}
                    if len(thinking) > 200:
                        new_block["thinking"] = thinking[:200] + "...[truncated]"
                    new_blocks.append(new_block)
                elif mode == "signature-only":
                    new_block = {k: v for k, v in block.items() if k != "signature"}
                    new_blocks.append(new_block)
                    changed = new_block != block
            else:
                if "signature" in block:
                    changed = True
                    new_blocks.append({k: v for k, v in block.items() if k != "signature"})
                else:
                    new_blocks.append(block)

        if changed:
            new_msg = set_content_blocks(msg, new_blocks)
            new_size = msg_bytes(new_msg)
            saved = size - new_size
            if saved > 0:
                actions.append(PruneAction(
                    line_index=idx,
                    action="replace",
                    reason=f"thinking-blocks ({mode})",
                    original_bytes=size,
                    pruned_bytes=new_size,
                    replacement=new_msg,
                ))
                total_pruned += saved
                replaced += 1

    return StrategyResult(
        strategy_name="thinking-blocks",
        actions=actions,
        original_bytes=total_orig,
        pruned_bytes=total_pruned,
        messages_affected=replaced,
        messages_removed=0,
        messages_replaced=replaced,
        summary=f"Processed {replaced} thinking blocks (mode={mode})",
    )


@strategy("tool-output-trim", "Trim large tool_result blocks (>8KB or >100 lines)", "standard", "1-8%")
def strategy_tool_output_trim(messages: list[Message], config: dict) -> StrategyResult:
    """Trim oversized tool results while preserving structure."""
    max_bytes = coerce_non_negative_int(config, "tool_output_max_bytes", default=8192)
    max_lines = coerce_non_negative_int(config, "tool_output_max_lines", default=100)

    actions: list[PruneAction] = []
    total_orig = sum(b for _, _, b in messages)
    total_pruned = 0
    replaced = 0

    # T2.3: Collect tool IDs already summarized by microcompact — don't trim those
    compacted_tool_ids: set[str] = set()
    for _, msg, _ in messages:
        if msg.get("type") == "system" and msg.get("subtype") == "microcompact_boundary":
            _ctids = msg.get("compactedToolIds", [])
            for tid in (_ctids if isinstance(_ctids, list) else []):
                if isinstance(tid, str):  # unhashable/non-str element -> skip (R6 crash class)
                    compacted_tool_ids.add(tid)

    for pos, (idx, msg, size) in enumerate(messages):
        if is_protected(msg):
            continue
        blocks = get_content_blocks(msg)
        if not blocks:
            continue

        new_blocks = []
        changed = False
        for block in blocks:
            if not isinstance(block, dict):  # non-dict element preserved, never .get()'d (R6)
                new_blocks.append(block)
                continue
            if block.get("type") == "tool_result":
                # Skip tool results already microcompacted
                tool_use_id = hashable_str(block.get("tool_use_id"))
                if tool_use_id and tool_use_id in compacted_tool_ids:
                    new_blocks.append(block)
                    continue
                content = block.get("content", "")
                if isinstance(content, str):
                    content_bytes = len(content.encode("utf-8"))
                    content_lines = content.count("\n") + 1
                    if content_bytes > max_bytes or content_lines > max_lines:
                        lines = content.split("\n")
                        if len(lines) > max_lines:
                            keep = max_lines // 2
                            trimmed = (
                                lines[:keep]
                                + [f"\n... [{len(lines) - max_lines} lines trimmed by winnow] ...\n"]
                                + lines[-keep:]
                            )
                            new_content = "\n".join(trimmed)
                        else:
                            half = max_bytes // 2
                            new_content = (
                                content[:half]
                                + f"\n... [{content_bytes - max_bytes} bytes trimmed by winnow] ...\n"
                                + content[-half:]
                            )
                        new_blocks.append({**block, "content": new_content})
                        changed = True
                        continue
                elif isinstance(content, list):
                    block_json = json.dumps(content, separators=(",", ":"))
                    if len(block_json.encode("utf-8")) > max_bytes:
                        trimmed_content = []
                        for sub in content:
                            if isinstance(sub, dict) and sub.get("type") == "text":
                                text = sub.get("text", "")
                                if isinstance(text, str) and len(text.encode("utf-8", "surrogateescape")) > max_bytes:
                                    half = max_bytes // 2
                                    sub = {**sub, "text": text[:half] + "\n...[trimmed by winnow]...\n" + text[-half:]}
                            trimmed_content.append(sub)
                        new_blocks.append({**block, "content": trimmed_content})
                        changed = True
                        continue
            new_blocks.append(block)

        if changed:
            new_msg = set_content_blocks(msg, new_blocks)
            new_size = msg_bytes(new_msg)
            saved = size - new_size
            if saved > 0:
                actions.append(PruneAction(
                    line_index=idx,
                    action="replace",
                    reason="tool-output-trim",
                    original_bytes=size,
                    pruned_bytes=new_size,
                    replacement=new_msg,
                ))
                total_pruned += saved
                replaced += 1

    return StrategyResult(
        strategy_name="tool-output-trim",
        actions=actions,
        original_bytes=total_orig,
        pruned_bytes=total_pruned,
        messages_affected=replaced,
        messages_removed=0,
        messages_replaced=replaced,
        summary=f"Trimmed {replaced} oversized tool outputs",
    )


# ── Read supersession ────────────────────────────────────────────────────────
# Two strategies below index `Read` calls by file path, and the pair is
# deliberate. `identical-reread` drops a read whose exact bytes come back again
# later — nothing is lost whatever the file did afterwards. `stale-reads` drops
# a read the session later EDITED — those bytes are wrong now. Neither subsumes
# the other, and a read can qualify under both.


def _range_token(value: object) -> object:
    """A hashable, comparison-stable token for a `Read`'s `offset` / `limit`.

    Untrusted JSONL can hold a list or dict where an int belongs, and an
    unhashable value used inside a dict key crashes the whole strategy (the R6
    crash class). `int` / `str` / `None` pass through unchanged, so `offset=40`
    and `offset="40"` stay DISTINCT: a grouping key must never merge two calls
    the model wrote differently.
    """
    if value is None or isinstance(value, (int, str)):
        return value
    return repr(value)


def _read_range_key(block: dict) -> tuple | None:
    """`(file_path, offset, limit)` for a `Read` tool_use block, else None.

    Exact equality only. No interval arithmetic that would let a whole-file read
    supersede a ranged one — DECISIONS §4 prices that at a week and names the
    honest v1 rule as the exact one.
    """
    if block.get("name") not in ("Read", "read"):
        return None
    tool_input = block.get("input")
    if not isinstance(tool_input, dict):
        return None
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return None
    return (
        file_path,
        _range_token(tool_input.get("offset")),
        _range_token(tool_input.get("limit")),
    )


# Every placeholder winnow writes into a tool_result opens with this — the two
# re-read rules, `tool-result-age`'s stub, `mega-block-trim`. `stale-reads` is
# the exception (it writes "[stale read - ...") and the prescriptions in
# registry.py keep it downstream of both re-read rules for that reason.
# The G2 floor usually gets there first, since every placeholder is far under
# 2,048 bytes; this is what holds when an operator lowers the floor.
_WINNOW_POINTER_PREFIX = "[winnow"


def _tool_result_payload(block: dict) -> str | None:
    """The exact bytes of a `tool_result`'s content, tagged by container type,
    or None when there is nothing safely comparable.

    Keys are NOT sorted and nothing is normalised: the comparison this feeds has
    to be byte-for-byte, and a re-serialisation that tidied the content would let
    two results that differ on the wire compare equal. The `s`/`l` tag keeps
    `"abc"` apart from `[{"type":"text","text":"abc"}]`, which are different
    payloads even when they render the same.

    An `is_error` result returns None: G3 in SPEC §4 — a failure is the
    information, and is never stripped at any tier. So does a block that already
    carries a winnow pointer: the guard re-prunes the same session on a cycle,
    and a rule that compared pointers would strip a pointer, double-count the
    saving and overwrite the first rule's explanation with its own.
    """
    if block.get("is_error"):
        return None
    content = block.get("content")
    if isinstance(content, str):
        if content.startswith(_WINNOW_POINTER_PREFIX):
            return None
        return "s\x00" + content
    if isinstance(content, list):
        try:
            return "l\x00" + json.dumps(content, separators=(",", ":"))
        except (TypeError, ValueError):
            return None
    return None


def _index_reads(messages: list[Message]) -> tuple[list[tuple[tuple, str]], dict[str, tuple[int, int]]]:
    """`(reads, result_at)` — every `Read` call in call order as
    `(range key, tool_use_id)`, and where each `tool_use_id`'s result block sits
    as `(message position, block index)`.

    Protected messages ARE indexed, unlike the top-of-loop skip the other
    strategies use, so a protected later read can still supersede an earlier
    one; protection is enforced where it bites, at the point of replacement.
    Pairing goes through a global `tool_use_id` index rather than a scan of the
    next few messages, because progress ticks and sidechain entries routinely
    push a result further from its call than any fixed window.
    """
    reads: list[tuple[tuple, str]] = []
    result_at: dict[str, tuple[int, int]] = {}

    for pos, (idx, msg, size) in enumerate(messages):
        for bi, block in enumerate(get_content_blocks(msg)):
            if not isinstance(block, dict):  # non-dict element never .get()'d (R6)
                continue
            btype = block.get("type")
            if btype == "tool_use":
                key = _read_range_key(block)
                if key is None:
                    continue
                tool_use_id = hashable_str(block.get("id"))  # unhashable -> "" (R6)
                if tool_use_id:
                    reads.append((key, tool_use_id))
            elif btype == "tool_result":
                tool_use_id = hashable_str(block.get("tool_use_id"))
                # First result wins: a tool_use_id duplicated in poisoned JSONL
                # must not leave the index pointing at the wrong block.
                if tool_use_id and tool_use_id not in result_at:
                    result_at[tool_use_id] = (pos, bi)

    return reads, result_at


def _result_payload_at(
    messages: list[Message],
    result_at: dict[str, tuple[int, int]],
    tool_use_id: str,
) -> tuple[int, int, str, str] | None:
    """`(message position, block index, payload, tool_use_id)` for a read's
    result, or None when it was never answered, is not comparable, or the
    indexed block is gone."""
    loc = result_at.get(tool_use_id)
    if loc is None:
        return None  # an in-flight call that was never answered
    pos, bi = loc
    blocks = get_content_blocks(messages[pos][1])
    if bi >= len(blocks) or not isinstance(blocks[bi], dict):
        return None
    payload = _tool_result_payload(blocks[bi])
    if payload is None:
        return None
    return pos, bi, payload, tool_use_id


@strategy("identical-reread", "Drop an earlier Read whose exact range came back byte-identical later", "standard", "0-3%")
def strategy_identical_reread(messages: list[Message], config: dict) -> StrategyResult:
    """SPEC §4 rule B1, restricted to the case where it cannot lose information.

    A `Read` result is dropped only when a LATER `Read` in the same session used
    the identical `(file_path, offset, limit)` and came back byte-for-byte
    identical. The copy that survives is the later one, so every byte removed is
    still in the conversation downstream and the session's most recent view of
    the file is the one retained.

    **Why the range still has to match**, when byte-identity alone would already
    make the strip lossless: two different windows of one file — or two
    different files, empty ones, vendored licences, generated headers — can hold
    identical bytes, and then the surviving read names a range the stripped one
    never asked for and the pointer's claim is false. The key keeps the pointer
    honest; the byte comparison keeps the strip safe.

    **What it does not cover** is the re-read whose content CHANGED between the
    two calls; that is `changed-reread` below, which is lossy where this rule is
    not and sits in the aggressive tier for it. Measured on 2026-08-24 over the operator's own corpus — 1,298
    transcripts, of which 625 clear the same >400 KB cut SPEC §6 applies — this
    rule reaches **0.072%** of message content there, firing in 19 of the 1,298
    with a best single session of 3.05%. Same convenience sample as SPEC §6, one
    operator, and a live one: the corpus grew between two runs minutes apart.

    Widening B1 further than `changed-reread` already does means dropping the
    range from the key, and that is not B1 at all: keyed on `file_path` alone
    the rule would reach 1.842% of message content, but **93.2% of that is a
    read no later read covers** — a different window of the file, complemented
    rather than superseded, whose bytes exist nowhere else once removed. SPEC §4
    B1 requires provable coverage precisely to exclude that case, and honouring
    the coverage clause in full rather than requiring an exact match adds
    0.003%. Whatever the case for widening this rule, it is not a
    2%-of-the-session case.

    The exact-range key costs almost nothing on that corpus: keyed on
    `file_path` alone the byte-identical variant finds the same 0.072%, and
    every byte-identical re-read above the floor was also an exact-range match.
    The interval arithmetic DECISIONS §4 defers is not what holds this rule
    back — changed content is.

    **Ordering.** Must run before `tool-output-trim`, `tool-result-age` and
    `stale-reads`, each of which rewrites `tool_result` content and would
    destroy the byte-identity this rule tests for. The prescriptions in
    `registry.py` place it accordingly.

    G1 (keep the tail) needs no separate guard here: the newest read of a range
    is never the one stripped, so a result cannot be removed unless identical
    bytes sit later in the session than it does.
    """
    min_bytes = coerce_non_negative_int(config, "identical_reread_min_bytes", default=2048)

    actions: list[PruneAction] = []
    total_orig = sum(b for _, _, b in messages)
    total_pruned = 0

    reads, result_at = _index_reads(messages)
    groups: dict[tuple, list[str]] = {}
    for key, tool_use_id in reads:
        groups.setdefault(key, []).append(tool_use_id)

    # ── Pass 2: walk each group backwards, so "the newest copy wins" falls out
    # of the iteration order. A group that read A, A, B collapses to A, B — the
    # first A goes because the second still carries those bytes, the second A
    # stays because nothing after it is identical, and B is untouched.
    replacements: dict[int, dict[int, dict]] = {}  # message position -> {block index: new block}

    for key, ids in groups.items():
        if len(ids) < 2:
            continue
        survivors: dict[str, str] = {}  # sha256 -> payload of the latest read carrying it
        for tool_use_id in reversed(ids):
            found = _result_payload_at(messages, result_at, tool_use_id)
            if found is None:
                continue
            pos, bi, payload, _tid = found
            raw = payload.encode("utf-8", "surrogateescape")
            digest = hashlib.sha256(raw).hexdigest()
            survivor = survivors.get(digest)
            if survivor is None:
                survivors[digest] = payload
                continue
            # The digest matched. Confirm byte-for-byte before removing anything:
            # sha256 makes this redundant in practice, it costs one comparison on
            # a path that only runs for actual matches, and the rule claims byte
            # identity — so it checks byte identity rather than asserting it.
            if payload != survivor:
                continue
            if is_protected(messages[pos][1]):
                continue
            content_bytes = len(raw) - 2  # minus the container tag
            if content_bytes < min_bytes:  # G2 size floor, SPEC §4
                continue
            file_path, offset, limit = key
            span = "" if offset is None and limit is None else f" [offset={offset}, limit={limit}]"
            replacements.setdefault(pos, {})[bi] = {
                **get_content_blocks(messages[pos][1])[bi],
                "content": (
                    f"[winnow: identical re-read removed - this Read of {file_path}{span} "
                    f"returned the same {content_bytes} bytes as a later Read in this "
                    f"session, which is retained. sha256 {digest[:12]}]"
                ),
            }

    # ── Pass 3: one action per message. Parallel Read calls put several results
    # in a single user message, so the blocks are rewritten together or the
    # second action would silently overwrite the first in execute_actions.
    blocks_removed = 0
    for pos in sorted(replacements):
        idx, msg, size = messages[pos]
        blocks = get_content_blocks(msg)
        new_blocks = [replacements[pos].get(bi, block) for bi, block in enumerate(blocks)]
        new_msg = set_content_blocks(msg, new_blocks)
        new_size = msg_bytes(new_msg)
        saved = size - new_size
        if saved <= 0:
            continue  # G4: a pointer longer than what it replaces is not a saving
        actions.append(PruneAction(
            line_index=idx,
            action="replace",
            reason="identical-reread",
            original_bytes=size,
            pruned_bytes=new_size,
            replacement=new_msg,
        ))
        total_pruned += saved
        blocks_removed += len(replacements[pos])

    return StrategyResult(
        strategy_name="identical-reread",
        actions=actions,
        original_bytes=total_orig,
        pruned_bytes=total_pruned,
        messages_affected=len(actions),
        messages_removed=0,
        messages_replaced=len(actions),
        summary=f"Removed {blocks_removed} identical re-read result(s)",
    )


@strategy("changed-reread", "Drop a Read the same range later returned different bytes for", "aggressive", "0-10%")
def strategy_changed_reread(messages: list[Message], config: dict) -> StrategyResult:
    """The lossy half of SPEC §4 rule B1: the file moved on underneath the read.

    Groups `Read` calls exactly as `identical-reread` does, keeps the LAST read
    of each `(file_path, offset, limit)`, and drops the earlier ones whose
    content no longer matches it. A read whose bytes still match that final
    state is left alone — it is not outdated, and a duplicate is
    `identical-reread`'s business rather than this rule's.

    **This one loses information, which is why it is aggressive-tier.** What it
    removes is a version of a file that no longer exists: not in the
    conversation, because the later read holds different bytes, and not on disk,
    because the file has moved on further still. The original transcript is the
    only copy, and `winnow recover` (milestone 2) does not exist yet, so the
    pointer promises nothing it cannot do. `stale-reads` makes the same trade on
    the same rationale — a read the session later EDITED — and this rule is that
    argument reached through a stronger signal: an edit only *implies* the file
    changed, whereas two different byte strings prove it.

    **What it is worth**, measured through `run_prescription` over the operator's
    corpus on 2026-08-24, on the 625 sessions above 400 KB (740 MB pooled) that
    SPEC §6 uses as its population: **0.109%** of message content, firing in 9
    of the 625 with a median hit of 0.46% and a maximum of 10.33%. Run together
    with `identical-reread` the pair reaches 0.179%, and **0.121% of that is an
    increment over `stale-reads`**, which by itself reaches 4.124% and fires in
    364 of the 625. The read-then-edit rule is where this family's mass is; B1
    is a rounding error beside it on this corpus.

    **Exact ranges only, and the measurement says that costs nothing.** Extending
    to SPEC §4's full provable-coverage clause — a whole-file read superseding a
    ranged one — adds 0.003%, which does not buy the interval arithmetic
    DECISIONS §4 prices at a week.

    **What it deliberately refuses.** Keying on `file_path` alone, ignoring the
    window, would reach 1.842% — but 93.2% of that is a read that no later read
    covers: a different part of the file, complemented rather than superseded,
    whose bytes exist nowhere else once removed. §4's coverage clause exists to
    exclude exactly that, and this rule honours it.
    """
    min_bytes = coerce_non_negative_int(config, "changed_reread_min_bytes", default=2048)

    actions: list[PruneAction] = []
    total_orig = sum(b for _, _, b in messages)
    total_pruned = 0

    reads, result_at = _index_reads(messages)
    groups: dict[tuple, list[str]] = {}
    for key, tool_use_id in reads:
        groups.setdefault(key, []).append(tool_use_id)

    replacements: dict[int, dict[int, dict]] = {}

    for key, ids in groups.items():
        if len(ids) < 2:
            continue

        # The last answered read of a window is the session's current truth
        # about it. Everything is judged against that one, not against its
        # immediate successor: a read whose bytes match the final state is
        # still accurate however many times the file changed in between.
        current = None
        for tool_use_id in reversed(ids):
            current = _result_payload_at(messages, result_at, tool_use_id)
            if current is not None:
                break
        if current is None:
            continue
        _cpos, _cbi, current_payload, current_id = current

        for tool_use_id in ids:
            if tool_use_id == current_id:
                continue
            found = _result_payload_at(messages, result_at, tool_use_id)
            if found is None:
                continue
            pos, bi, payload, _tid = found
            if payload == current_payload:
                continue  # still accurate — identical-reread's call, not this one's
            if is_protected(messages[pos][1]):
                continue
            raw = payload.encode("utf-8", "surrogateescape")
            content_bytes = len(raw) - 2  # minus the container tag
            if content_bytes < min_bytes:  # G2 size floor, SPEC §4
                continue
            digest = hashlib.sha256(raw).hexdigest()
            file_path, offset, limit = key
            span = "" if offset is None and limit is None else f" [offset={offset}, limit={limit}]"
            replacements.setdefault(pos, {})[bi] = {
                **get_content_blocks(messages[pos][1])[bi],
                "content": (
                    f"[winnow: superseded re-read removed - this Read of {file_path}{span} "
                    f"returned {content_bytes} bytes the file no longer had; a later Read of "
                    f"the same range in this session holds what replaced them. Removed from "
                    f"this file only: the original transcript is unmodified. sha256 {digest[:12]}]"
                ),
            }

    blocks_removed = 0
    for pos in sorted(replacements):
        idx, msg, size = messages[pos]
        blocks = get_content_blocks(msg)
        new_blocks = [replacements[pos].get(bi, block) for bi, block in enumerate(blocks)]
        new_msg = set_content_blocks(msg, new_blocks)
        new_size = msg_bytes(new_msg)
        saved = size - new_size
        if saved <= 0:
            continue  # G4: a pointer longer than what it replaces is not a saving
        actions.append(PruneAction(
            line_index=idx,
            action="replace",
            reason="changed-reread",
            original_bytes=size,
            pruned_bytes=new_size,
            replacement=new_msg,
        ))
        total_pruned += saved
        blocks_removed += len(replacements[pos])

    return StrategyResult(
        strategy_name="changed-reread",
        actions=actions,
        original_bytes=total_orig,
        pruned_bytes=total_pruned,
        messages_affected=len(actions),
        messages_removed=0,
        messages_replaced=len(actions),
        summary=f"Removed {blocks_removed} superseded re-read result(s)",
    )


@strategy("stale-reads", "Remove file reads superseded by later edits", "standard", "0.5-2%")
def strategy_stale_reads(messages: list[Message], config: dict) -> StrategyResult:
    """If a file was read and then later edited/written, the read result is stale."""
    actions: list[PruneAction] = []
    total_orig = sum(b for _, _, b in messages)
    total_pruned = 0

    file_events: dict[str, list[tuple[int, str, int]]] = {}

    for pos, (idx, msg, size) in enumerate(messages):
        if is_protected(msg):
            continue
        for block in get_content_blocks(msg):
            if block.get("type") == "tool_use":
                tool_name = block.get("name", "")
                tool_input = block.get("input", {})
                if tool_name in ("Read", "read"):
                    fp = tool_input.get("file_path", "")
                    if fp:
                        file_events.setdefault(fp, []).append((pos, "read", idx))
                elif tool_name in ("Edit", "edit", "Write", "write"):
                    fp = tool_input.get("file_path", "")
                    if fp:
                        file_events.setdefault(fp, []).append((pos, "edit", idx))

    stale_read_positions: set[int] = set()
    for fp, events in file_events.items():
        events.sort(key=lambda x: x[0])
        for i, (pos, etype, idx) in enumerate(events):
            if etype == "read":
                for j in range(i + 1, len(events)):
                    if events[j][1] == "edit":
                        stale_read_positions.add(pos)
                        break

    for pos, (idx, msg, size) in enumerate(messages):
        if pos not in stale_read_positions:
            continue
        for block in get_content_blocks(msg):
            if block.get("type") == "tool_use" and block.get("name") in ("Read", "read"):
                tool_use_id = block.get("id", "")
                if not tool_use_id:
                    continue
                for fpos in range(pos + 1, min(pos + 5, len(messages))):
                    fidx, fmsg, fsize = messages[fpos]
                    for fb in get_content_blocks(fmsg):
                        if fb.get("type") == "tool_result" and fb.get("tool_use_id") == tool_use_id:
                            content = fb.get("content", "")
                            if isinstance(content, str) and len(content) > 500:
                                new_fb = {**fb, "content": "[stale read - file was later edited, trimmed by winnow]"}
                                new_blocks = []
                                did_replace = False
                                for ob in get_content_blocks(fmsg):
                                    if ob.get("type") == "tool_result" and ob.get("tool_use_id") == tool_use_id and not did_replace:
                                        new_blocks.append(new_fb)
                                        did_replace = True
                                    else:
                                        new_blocks.append(ob)
                                new_msg = set_content_blocks(fmsg, new_blocks)
                                new_size = msg_bytes(new_msg)
                                saved = fsize - new_size
                                if saved > 0:
                                    actions.append(PruneAction(
                                        line_index=fidx,
                                        action="replace",
                                        reason="stale-read (file later edited)",
                                        original_bytes=fsize,
                                        pruned_bytes=new_size,
                                        replacement=new_msg,
                                    ))
                                    total_pruned += saved

    replaced = len(actions)
    return StrategyResult(
        strategy_name="stale-reads",
        actions=actions,
        original_bytes=total_orig,
        pruned_bytes=total_pruned,
        messages_affected=replaced,
        messages_removed=0,
        messages_replaced=replaced,
        summary=f"Trimmed {replaced} stale file read results",
    )


@strategy("system-reminder-dedup", "Deduplicate repeated <system-reminder> tags", "standard", "0.1-3%")
def strategy_system_reminder_dedup(messages: list[Message], config: dict) -> StrategyResult:
    """Remove duplicate system-reminder content, keeping only the first occurrence."""
    actions: list[PruneAction] = []
    total_orig = sum(b for _, _, b in messages)
    total_pruned = 0
    replaced = 0

    reminder_pattern = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
    seen_hashes: set[str] = set()

    for pos, (idx, msg, size) in enumerate(messages):
        if is_protected(msg):
            continue
        blocks = get_content_blocks(msg)
        if not blocks:
            continue

        new_blocks = []
        changed = False
        for block in blocks:
            if block.get("type") in ("text", "tool_result"):
                text = block.get("text", "") or (block.get("content", "") if isinstance(block.get("content"), str) else "")
                if not text:
                    new_blocks.append(block)
                    continue

                reminders = reminder_pattern.findall(text)
                if reminders:
                    new_text = text
                    for reminder in reminders:
                        h = hashlib.md5(reminder.encode()).hexdigest()
                        if h in seen_hashes:
                            new_text = new_text.replace(reminder, "")
                            changed = True
                        else:
                            seen_hashes.add(h)

                    if changed:
                        new_text = re.sub(r"\n{3,}", "\n\n", new_text).strip()
                        if block.get("type") == "text":
                            new_blocks.append({**block, "text": new_text})
                        elif block.get("type") == "tool_result" and isinstance(block.get("content"), str):
                            new_blocks.append({**block, "content": new_text})
                        else:
                            new_blocks.append(block)
                    else:
                        new_blocks.append(block)
                else:
                    new_blocks.append(block)
            else:
                new_blocks.append(block)

        if changed:
            new_msg = set_content_blocks(msg, new_blocks)
            new_size = msg_bytes(new_msg)
            saved = size - new_size
            if saved > 0:
                actions.append(PruneAction(
                    line_index=idx,
                    action="replace",
                    reason="system-reminder-dedup",
                    original_bytes=size,
                    pruned_bytes=new_size,
                    replacement=new_msg,
                ))
                total_pruned += saved
                replaced += 1

    return StrategyResult(
        strategy_name="system-reminder-dedup",
        actions=actions,
        original_bytes=total_orig,
        pruned_bytes=total_pruned,
        messages_affected=replaced,
        messages_removed=0,
        messages_replaced=replaced,
        summary=f"Deduped system-reminders in {replaced} messages ({len(seen_hashes)} unique)",
    )


@strategy("tool-result-age", "Compact old tool results by age — minify mid-age, stub old", "standard", "10-40%")
def strategy_tool_result_age(messages: list[Message], config: dict) -> StrategyResult:
    """Three-tier age-based tool result compaction.

    Tool results decay in value exponentially. A file read from 50 turns ago
    is stale (the file has been edited since) and wastes tokens. Claude can
    always re-read if needed.

    Tiers (configurable via config):
      Recent (0 to mid_age turns):  untouched
      Mid-age (mid_age to old_age): minify JSON, strip diff context lines
      Old (old_age+):               replace content with compact stub

    Research: JetBrains validated observation masking on SWE-bench — matched
    LLM summarization quality at zero compute cost.
    """
    mid_age, old_age = coerce_ordered_pair(
        config, "tool_result_mid_age", "tool_result_old_age", defaults=(15, 40)
    )

    actions: list[PruneAction] = []
    total_orig = sum(b for _, _, b in messages)
    total_pruned = 0
    replaced = 0

    # Count actual user prompts (not tool_result wrappers which also have type="user")
    def _is_user_prompt(msg: dict) -> bool:
        if get_msg_type(msg) != "user":
            return False
        content = msg.get("message", {}).get("content", "")
        # tool_result messages have list content with tool_result blocks
        if isinstance(content, list):
            return not any(b.get("type") == "tool_result" for b in content if isinstance(b, dict))
        return isinstance(content, str)

    total_turns = sum(1 for _, msg, _ in messages if _is_user_prompt(msg))

    # Build turn index: for each message position, how many user prompts precede it?
    turn_count = 0
    msg_turn: list[int] = []
    for _, msg, _ in messages:
        if _is_user_prompt(msg):
            turn_count += 1
        msg_turn.append(turn_count)

    for pos, (idx, msg, size) in enumerate(messages):
        if is_protected(msg):
            continue

        blocks = get_content_blocks(msg)
        if not blocks:
            continue

        has_tool_result = any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks)
        if not has_tool_result:
            continue

        turns_ago = total_turns - msg_turn[pos]

        if turns_ago < mid_age:
            continue  # Recent — keep verbatim

        new_blocks = []
        changed = False

        for block in blocks:
            if block.get("type") != "tool_result":
                new_blocks.append(block)
                continue

            content = block.get("content", "")
            if not isinstance(content, str) or len(content) < 100:
                new_blocks.append(block)
                continue

            tool_use_id = block.get("tool_use_id", "")

            if turns_ago >= old_age:
                # OLD: replace with compact stub
                stub = _build_stub(block, blocks, messages, pos)
                new_blocks.append({**block, "content": stub})
                changed = True
            else:
                # MID-AGE: minify content
                compacted = _minify_tool_content(content)
                if compacted != content:
                    new_blocks.append({**block, "content": compacted})
                    changed = True
                else:
                    new_blocks.append(block)

        if changed:
            new_msg = set_content_blocks(msg, new_blocks)
            new_size = msg_bytes(new_msg)
            saved = size - new_size
            if saved > 0:
                actions.append(PruneAction(
                    line_index=idx,
                    action="replace",
                    reason=f"tool-result-age ({turns_ago} turns ago)",
                    original_bytes=size,
                    pruned_bytes=new_size,
                    replacement=new_msg,
                ))
                total_pruned += saved
                replaced += 1

    return StrategyResult(
        strategy_name="tool-result-age",
        actions=actions,
        original_bytes=total_orig,
        pruned_bytes=total_pruned,
        messages_affected=replaced,
        messages_removed=0,
        messages_replaced=replaced,
        summary=f"Compacted {replaced} old tool results ({total_pruned / 1024:.0f}KB saved)",
    )


def _build_stub(block: dict, all_blocks: list[dict], messages: list[Message], pos: int) -> str:
    """Build a compact stub for an old tool result."""
    content = block.get("content", "")
    tool_use_id = block.get("tool_use_id", "")
    content_len = len(content)
    line_count = content.count("\n") + 1 if content else 0

    # Try to find the matching tool_use to get tool name and input
    tool_name = ""
    tool_path = ""
    for search_pos in range(max(0, pos - 10), pos + 1):
        if search_pos >= len(messages):
            break
        _, search_msg, _ = messages[search_pos]
        for b in get_content_blocks(search_msg):
            if b.get("type") == "tool_use" and b.get("id") == tool_use_id:
                tool_name = b.get("name", "")
                tool_input = b.get("input", {})
                tool_path = (
                    tool_input.get("file_path", "")
                    or tool_input.get("path", "")
                    or tool_input.get("pattern", "")
                    or tool_input.get("command", "")[:80]
                )
                break

    parts = ["[winnow"]
    if tool_name:
        parts.append(f": {tool_name}")
    if tool_path:
        parts.append(f" {tool_path}")
    parts.append(f" — {line_count} lines, {content_len / 1024:.1f}KB]")

    return "".join(parts)


def _minify_tool_content(content: str) -> str:
    """Minify mid-age tool result content: strip JSON whitespace, collapse diff context."""
    # Try JSON minification first
    try:
        parsed = json.loads(content)
        minified = json.dumps(parsed, separators=(",", ":"))
        if len(minified) < len(content) * 0.85:  # Only if meaningful savings
            return minified
    except (json.JSONDecodeError, TypeError):
        pass

    # Collapse diff context lines — but ONLY for a GENUINE unified diff. The gate
    # requires the unified-diff ENVELOPE (a `--- `/`+++ ` file-header pair or a
    # `diff ` command line) AND a real hunk header. A lone coincidental `@@ … @@`
    # line in non-diff output (a git-log fragment, CI text, an indented config
    # block) no longer triggers collapse — and even past the gate,
    # _collapse_diff_context only collapses context lines INSIDE a hunk, so it can
    # never wholesale-destroy indented non-diff content (the audit P1).
    if "\0" not in content and _looks_like_unified_diff(content):
        collapsed = _collapse_diff_context(content)
        if collapsed != content:
            return collapsed

    return content


# A real unified-diff hunk header, anchored at line start: "@@ -12,7 +12,9 @@".
_UNIFIED_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@", re.M)
# The file-header pair every unified diff carries: a "--- …" line immediately
# followed by a "+++ …" line.
_DIFF_FILE_HDR_RE = re.compile(r"^--- .*\n\+\+\+ ", re.M)


def _looks_like_unified_diff(content: str) -> bool:
    """True only for content with the unified-diff envelope (so we never collapse
    non-diff output that merely contains a hunk-shaped line)."""
    if not _UNIFIED_HUNK_RE.search(content):
        return False
    if _DIFF_FILE_HDR_RE.search(content):
        return True
    return content.startswith("diff ") or "\ndiff --git " in content or "\ndiff " in content


def _collapse_diff_context(diff_text: str) -> str:
    """Strip unchanged context lines from unified diffs, keep +/- and headers.

    Context lines (" "-prefixed) are collapsed ONLY while inside a hunk (after an
    `@@` header). Lines before the first hunk, and any non-hunk content, are kept
    verbatim — so a stray indented block cannot be destroyed even if the gate
    passed on a real diff that also contains trailing prose."""
    lines = diff_text.split("\n")
    result = []
    context_run = 0
    in_hunk = False

    def _flush():
        nonlocal context_run
        if context_run > 0:
            result.append(f"  [...{context_run} unchanged lines...]")
            context_run = 0

    for line in lines:
        if line.startswith("@@"):
            _flush()
            in_hunk = True
            result.append(line)
        elif line.startswith(("diff ", "---", "+++", "+", "-")):
            _flush()
            result.append(line)
        elif in_hunk and line.startswith(" "):
            context_run += 1
        else:
            # A non-context line: we're no longer inside a hunk's body. Reset
            # in_hunk so indented content AFTER the hunk (e.g. a git-log-p second
            # commit's message body, or trailing prose) is kept verbatim and never
            # collapsed (the audit P1 — in_hunk was set but never reset).
            in_hunk = False
            _flush()
            result.append(line)

    _flush()
    collapsed = "\n".join(result)
    return collapsed if len(collapsed) < len(diff_text) else diff_text
