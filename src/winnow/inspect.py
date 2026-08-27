"""`winnow inspect` — the instrument. Reads a transcript, writes nothing.

This is milestone 1 ([MILESTONES.md](../../docs/MILESTONES.md)), whose deliverable
is a number rather than a binary: the share of a session's message content that
[SPEC.md](../../docs/SPEC.md) §4's rules would replace, the cache arithmetic that
says whether replacing it pays, and the count of records the parser did not
recognise. Every layer the finished tool needs is exercised here except the
writer, and that omission is the point — milestone 1 has to be able to say "do
not build the writer".

SPEC §4's rules, guards and pointer are not here. They live in `rules.py`,
because `plan` and `fork` classify with the same engine and a second copy of B1
would be a second definition of it. What is here is the reading and the
measuring: the record walk, the byte accounting, the `usage` totals, and the
break-even arithmetic that prices a cut this command never makes.

The one rule-adjacent thing worth stating here: **`inspect` classifies with every
rule enabled and applies a tier by summing.** SPEC §6's per-rule table is the
ceiling of the mechanism, so the readout reports what each rule *could* claim.
Guard G4 is therefore not applied — it compares a result against the pointer that
would replace it, and no pointer is written here. `plan` applies it, and its
totals are the ones that describe a fork.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .legacy.session import load_messages
from .rules import (
    DEFAULT_KEEP_LAST,
    DEFAULT_MIN_BYTES,
    RULE_ORDER,
    TIER_RULES,
    ToolCall,
    classify,
    content_digest,
    input_size,
    result_size,
)

# ─── Record classification ───────────────────────────────────────────────────

# Record types the parser understands. Anything else is counted and reported
# rather than dropped: SPEC §9's milestone-1 criterion is that inspect "reports
# the count of records it did not recognise", because a transcript format that
# has moved on is the failure mode that would silently shrink every share below.
KNOWN_RECORD_TYPES = frozenset({
    "user", "assistant", "system", "summary", "attachment", "progress",
    "file-history-snapshot", "file-history-delta", "mode", "bridge-session",
    "ai-title", "last-prompt", "queue-operation", "x-claude-log",
})

# The five content classes SPEC §1 splits message content into. The denominator
# for every share reported here is their sum, so a class added to the transcript
# format and not added here would inflate every share at once.
CONTENT_CLASSES = ("tool_result", "tool_use", "user_text", "assistant_text", "thinking")


# The prefix that stays warm across the cut: tools plus system, measured at
# 15,903 tokens on this install (`ContextControl/01-constraints.md:52`, quoted in
# COZEMPIC.md §3.1). It sits before `messages`, so a message-content cut never
# invalidates it and it is excluded from S by construction here — recorded so a
# reader does not go looking for a subtraction that is structurally unnecessary.
BASE_PREFIX_TOKENS = 15_903


@dataclass
class Usage:
    """The cache economics, summed from `message.usage` off disk.

    Every field is read, not modelled. COZEMPIC.md §3.1's measurement table
    needs `cache_creation_input_tokens` on the first turn after a boundary to be
    the invalidation actually paid, and that is only true if nothing here
    estimates.
    """

    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_creation: int = 0
    ephemeral_1h: int = 0
    ephemeral_5m: int = 0

    @property
    def write_class(self) -> str:
        """Which write class this session actually paid.

        The 2.0× multiplier in `T* = 19·(S/D) − 20` is a property of the install,
        not a documentation lookup — pricing it at the 1.25× five-minute write
        understates a cut by about 40% (COZEMPIC.md §3.1). So it is read back per
        session rather than assumed.
        """
        if self.ephemeral_1h and not self.ephemeral_5m:
            return "1h"
        if self.ephemeral_5m and not self.ephemeral_1h:
            return "5m"
        if self.ephemeral_1h or self.ephemeral_5m:
            return "mixed"
        return "unknown"


@dataclass
class FilterLedger:
    """What the intake filter kept off the wire for one session.

    The filter never touches the transcript — Claude Code writes what it holds,
    which still contains every byte the API never saw. So every figure `inspect`
    derives from disk overstates a filtered session, and `fork` would pay
    `1.9·S` to remove bytes that are not in the prefix. This is the correction,
    joined on `requestId`: the ledger records the id the API returned, and the
    transcript records the same id on the assistant turn it answered.
    """

    requests: int = 0
    bytes_dropped: int = 0
    by_rule: dict[str, int] = field(default_factory=dict)
    # The filter is stateless, so it re-drops the same result on every later
    # request that still carries it, and each of those writes another entry.
    # Summing them counts one removal once per surviving request: 8.6× on this
    # corpus and 27.2× on the one real ledger. `bytes_dropped` above is therefore
    # the de-duplicated figure and these two exist so the gap can be shown rather
    # than assumed away.
    removal_events: int = 0  # entries seen, repeats included
    bytes_summed: int = 0  # the naive sum, kept only to show the echo
    legacy_entries: int = 0  # entries predating `tool_use_id`, de-duped on the fallback

    @property
    def echo_factor(self) -> float:
        """How many times the average removal was recorded. 1.0 means no echo."""
        return (self.bytes_summed / self.bytes_dropped) if self.bytes_dropped else 1.0


@dataclass
class Report:
    """Everything `winnow inspect` knows about one session. Writes nothing."""

    session_id: str
    path: Path
    records: int = 0
    record_types: dict[str, int] = field(default_factory=dict)
    unrecognised_records: int = 0
    parse_errors: int = 0
    content_bytes: dict[str, int] = field(default_factory=dict)
    tool_result_bytes_by_tool: dict[str, int] = field(default_factory=dict)
    tool_calls: int = 0
    unanswered_tool_uses: int = 0
    rule_bytes: dict[str, int] = field(default_factory=dict)
    rule_hits: dict[str, int] = field(default_factory=dict)
    guard_blocked: dict[str, int] = field(default_factory=dict)
    compact_boundaries: list[int] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    cut_line: int | None = None
    suffix_bytes: int = 0
    filtered: FilterLedger | None = None
    # The paired call index and the per-line byte map, kept rather than discarded
    # so `plan` can re-classify under a different rule selection and re-price the
    # cut without reading the transcript a second time. Neither reaches `--json`:
    # `report.to_dict` names its fields explicitly, so the readout is unchanged.
    calls: list[ToolCall] = field(default_factory=list)
    line_content: dict[int, int] = field(default_factory=dict)

    @property
    def wire_content_bytes(self) -> int:
        """Message content minus what the filter kept off the wire.

        The denominator every share should use on a filtered session. Equal to
        `message_content_bytes` when no ledger was supplied, so nothing changes
        for a session that was never filtered.
        """
        if self.filtered is None:
            return self.message_content_bytes
        return max(0, self.message_content_bytes - self.filtered.bytes_dropped)

    @property
    def message_content_bytes(self) -> int:
        return sum(self.content_bytes.values())

    def tier_bytes(self, tier: str) -> int:
        return sum(self.rule_bytes.get(r, 0) for r in TIER_RULES[tier])

    def tier_share(self, tier: str) -> float:
        total = self.message_content_bytes
        return (self.tier_bytes(tier) / total * 100) if total else 0.0

    def break_even_turns(self, tier: str) -> float | None:
        """`T* = 19·(S/D) − 20` — further turns before a cut at this tier pays.

        Returned as a ratio of message-content bytes rather than tokens. SPEC §6
        estimates tokens at bytes ÷ 4 and flags the estimate wherever it is used;
        here the estimate cancels, because S and D are both in the same unit and
        only their ratio enters the formula. What does not cancel is that bytes
        per token differ between a log and prose, so a session whose suffix is
        mostly log and whose cut is mostly prose has a real error here. Named
        rather than corrected: correcting it needs a tokeniser, and SPEC §3 puts
        a model call out of scope.

        None when nothing would be stripped — there is no cut, so no break-even.
        """
        return break_even_turns(self.suffix_bytes, self.tier_bytes(tier))

    def suffix_from(self, cut_line: int) -> int:
        """Bytes of message content standing at or after `cut_line`.

        `suffix_bytes` is this for the cut `inspect` would make with every rule
        enabled. `plan` cuts at a different line whenever the operator selects a
        different set, so the map stays available rather than being collapsed to
        one answer.
        """
        return sum(size for line, size in self.line_content.items() if line >= cut_line)


def break_even_turns(suffix_bytes: int, removed_bytes: int) -> float | None:
    """`T* = 19·(S/D) − 20` — further turns before a cut pays for itself.

    `ContextControl/01-` derives it; SPEC §7 quotes it and names the one moment
    where it goes negative. A ratio of message-content bytes rather than tokens:
    SPEC §6 estimates tokens at bytes ÷ 4 and flags the estimate wherever it is
    used, and here the estimate cancels, because S and D are in the same unit and
    only their ratio enters. What does not cancel is that bytes per token differ
    between a log and prose, so a session whose suffix is mostly log and whose
    cut is mostly prose has a real error here. Named rather than corrected:
    correcting it needs a tokeniser, and SPEC §3 puts a model call out of scope.

    None when nothing would be removed — there is no cut, so no break-even.
    """
    if not removed_bytes or not suffix_bytes:
        return None
    return 19 * (suffix_bytes / removed_bytes) - 20


# ─── Reading one session ─────────────────────────────────────────────────────


def _inner(record: dict) -> dict:
    inner = record.get("message")
    return inner if isinstance(inner, dict) else {}


def _blocks(record: dict) -> list:
    content = _inner(record).get("content")
    if isinstance(content, list):
        return content
    return []


def read_filter_ledger(ledger_path: Path, request_ids: set[str]) -> FilterLedger:
    """Total what the filter dropped on the requests this session made.

    Joined on `requestId` rather than a session field because the filter cannot
    know the session: it sees a Messages API request body, which carries no
    session identity. The id the API returns is the only thing both sides hold.

    **De-duplicated on `tool_use_id`, which is the whole difficulty.** The filter
    is stateless: a result it dropped on request *n* is dropped again on *n+1* and
    on every later request that still carries it, and each drop writes another
    entry. This used to sum `bytes_dropped` over the joining lines, which counts
    one removal once per surviving request — 8.6× on this corpus, 27.2× on the one
    real ledger. `savings.read_ledger` has always collapsed on identity; the two
    readers of one file disagreed by exactly that factor, and this is the reader
    whose number reaches `wire_content_bytes`, which clamps at zero. An 8.6×
    overstatement there silently produces a denominator of nothing.

    The de-dupe keys are `savings.read_ledger`'s, for the same reasons and with
    the same trade: an entry carrying a `tool_use_id` is exact, an entry predating
    that field falls back to `(tool, rule, bytes)` which can merge two genuinely
    distinct results, and both errors the fallback can make are undercounts —
    the direction a correction to a savings claim should err in.
    """
    found = FilterLedger()
    seen_ids: set[str] = set()
    seen_triples: set[tuple[str, str, int]] = set()
    claimed_triples: set[tuple[str, str, int]] = set()
    try:
        with ledger_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                if record.get("request_id") not in request_ids:
                    continue
                found.requests += 1
                for dropped in record.get("dropped") or ():
                    if not isinstance(dropped, dict):
                        continue
                    size = _as_int(dropped.get("bytes"))
                    rule = str(dropped.get("rule", "?"))
                    tool = dropped.get("tool") if isinstance(dropped.get("tool"), str) else ""
                    use_id = dropped.get("tool_use_id")
                    use_id = use_id if isinstance(use_id, str) and use_id else None
                    found.removal_events += 1
                    found.bytes_summed += size
                    triple = (tool, rule, size)
                    if use_id is not None:
                        if use_id in seen_ids:
                            continue
                        seen_ids.add(use_id)
                        claimed_triples.add(triple)
                    else:
                        found.legacy_entries += 1
                        if triple in seen_triples or triple in claimed_triples:
                            continue
                        seen_triples.add(triple)
                    found.bytes_dropped += size
                    found.by_rule[rule] = found.by_rule.get(rule, 0) + size
    except OSError:
        # A ledger that cannot be read is a missing correction, not a failure to
        # inspect. The readout says so rather than silently reporting uncorrected
        # figures as if they were correct.
        return FilterLedger()
    return found


def inspect_session(
    path: Path,
    keep_last: int = DEFAULT_KEEP_LAST,
    min_bytes: int = DEFAULT_MIN_BYTES,
    filter_ledger: Path | None = None,
) -> Report:
    """Read one transcript and report. Opens the file once, read-only."""
    report = Report(session_id=path.stem, path=path)
    report.content_bytes = {cls: 0 for cls in CONTENT_CLASSES}

    messages = load_messages(path)
    report.records = len(messages)

    calls: list[ToolCall] = []
    request_ids: set[str] = set()
    # tool_use_id → (line, size, is_error, sha256)
    results: dict[str, tuple[int, int, bool, str]] = {}
    pending: list[tuple[int, str, str, dict]] = []  # (line, id, name, input)
    # Byte offsets are accumulated per line so the cut point can be priced
    # without a second pass: `suffix_bytes` is everything from the earliest
    # stripped result to the end.
    line_content: dict[int, int] = {}

    for line_index, record, _ in messages:
        if record.get("_parse_error"):
            report.parse_errors += 1
            continue
        rtype = record.get("type", "?")
        report.record_types[rtype] = report.record_types.get(rtype, 0) + 1
        if rtype not in KNOWN_RECORD_TYPES:
            report.unrecognised_records += 1

        if record.get("subtype") == "compact_boundary" or rtype == "compact_boundary":
            report.compact_boundaries.append(line_index)

        if rtype == "assistant":
            _read_usage(record, report.usage)
            request_id = record.get("requestId")
            if isinstance(request_id, str):
                request_ids.add(request_id)

        role = _inner(record).get("role") or rtype
        raw_content = _inner(record).get("content")
        if isinstance(raw_content, str):
            cls = "assistant_text" if role == "assistant" else "user_text"
            size = len(raw_content)
            report.content_bytes[cls] += size
            line_content[line_index] = line_content.get(line_index, 0) + size

        for block in _blocks(record):
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            size = 0
            if btype == "tool_result":
                content = block.get("content")
                size = result_size(content)
                report.content_bytes["tool_result"] += size
                use_id = block.get("tool_use_id")
                if isinstance(use_id, str):
                    # The digest is taken here, where the content is already in
                    # hand, so that `plan` and `fork` never re-read the file to
                    # find out what they are about to replace.
                    results[use_id] = (
                        line_index, size, bool(block.get("is_error")), content_digest(content),
                    )
            elif btype == "tool_use":
                size = input_size(block.get("input"))
                report.content_bytes["tool_use"] += size
                use_id = block.get("id")
                name = block.get("name")
                tool_input = block.get("input")
                if isinstance(use_id, str) and isinstance(name, str):
                    pending.append(
                        (line_index, use_id, name, tool_input if isinstance(tool_input, dict) else {})
                    )
            elif btype == "text":
                text = block.get("text")
                size = len(text) if isinstance(text, str) else 0
                cls = "assistant_text" if role == "assistant" else "user_text"
                report.content_bytes[cls] += size
            elif btype == "thinking":
                thinking = block.get("thinking")
                size = len(thinking) if isinstance(thinking, str) else 0
                report.content_bytes["thinking"] += size
            if size:
                line_content[line_index] = line_content.get(line_index, 0) + size

    for order, (use_line, use_id, name, tool_input) in enumerate(pending):
        found = results.get(use_id)
        if found is None:
            report.unanswered_tool_uses += 1
            calls.append(
                ToolCall(order, use_line, name, tool_input, 0, False, False, use_id=use_id)
            )
            continue
        result_line, size, is_error, digest = found
        calls.append(
            ToolCall(order, result_line, name, tool_input, size, is_error, True,
                     use_id=use_id, digest=digest)
        )
        report.tool_result_bytes_by_tool[name] = (
            report.tool_result_bytes_by_tool.get(name, 0) + size
        )

    report.tool_calls = len(calls)
    report.calls = calls
    report.line_content = line_content
    assigned, report.guard_blocked = classify(calls, keep_last, min_bytes)

    report.rule_bytes = {rule: 0 for rule in RULE_ORDER}
    report.rule_hits = {rule: 0 for rule in RULE_ORDER}
    by_order = {call.order: call for call in calls}
    for order, rule in assigned.items():
        report.rule_bytes[rule] += by_order[order].result_size
        report.rule_hits[rule] += 1

    if filter_ledger is not None:
        report.filtered = read_filter_ledger(filter_ledger, request_ids)

    if assigned:
        report.cut_line = min(by_order[o].line for o in assigned)
        report.suffix_bytes = report.suffix_from(report.cut_line)
    return report


def _read_usage(record: dict, usage: Usage) -> None:
    """Sum one assistant record's `message.usage` into the running total.

    `<synthetic>` models are skipped for the reason `tokens.extract_usage_tokens`
    skips them: their usage block is all zeros and would dilute the write-class
    reading with turns that were never billed.
    """
    inner = _inner(record)
    if inner.get("model") == "<synthetic>":
        return
    raw = inner.get("usage")
    if not isinstance(raw, dict):
        return
    usage.turns += 1
    usage.input_tokens += _as_int(raw.get("input_tokens"))
    usage.output_tokens += _as_int(raw.get("output_tokens"))
    usage.cache_read += _as_int(raw.get("cache_read_input_tokens"))
    usage.cache_creation += _as_int(raw.get("cache_creation_input_tokens"))
    detail = raw.get("cache_creation")
    if isinstance(detail, dict):
        usage.ephemeral_1h += _as_int(detail.get("ephemeral_1h_input_tokens"))
        usage.ephemeral_5m += _as_int(detail.get("ephemeral_5m_input_tokens"))


def _as_int(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
