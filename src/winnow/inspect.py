"""`winnow inspect` — the instrument. Reads a transcript, writes nothing.

This is milestone 1 ([MILESTONES.md](../../docs/MILESTONES.md)), whose deliverable
is a number rather than a binary: the share of a session's message content that
[SPEC.md](../../docs/SPEC.md) §4's rules would replace, the cache arithmetic that
says whether replacing it pays, and the count of records the parser did not
recognise. Every layer the finished tool needs is exercised here except the
writer, and that omission is the point — milestone 1 has to be able to say "do
not build the writer".

Three things in here are easy to get subtly wrong, so they are stated once:

**Rules are first-match-wins, in the order C1, C2, C3, B1, B2, A1.** SPEC §6's
per-rule table sums to its own tier totals (3.50% for C, +19.11% for B against a
22.6% C+B), which is only true if every result is attributed to exactly one rule.
Attributing a result to every rule that matches would double-count it.

**The measure is SPEC §6's measure, not a byte count.** `len()` of the content
string, or of `json.dumps()` for a structured result. On ASCII the two agree; on
anything else they do not, and the baseline this reproduces was taken with
`len()`.

**Guards run before rules, never after.** A result the guards protect is not
"stripped by B2 and then restored" — it never enters the rule engine, so it
cannot appear in a per-rule share.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .legacy.session import load_messages

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


# ─── SPEC §4 rule patterns ───────────────────────────────────────────────────

# C1: the output is a list of paths whose only consumer is the call that
# followed it.
LOCATOR_TOOLS = frozenset({"Glob", "LS"})
LOCATOR_GREP_MODES = frozenset({"files_with_matches", "count"})

# C3: a verification run that passed. A failing one is never stripped — the
# failure is the information (SPEC §4 C3, and guard G3 independently).
VERIFICATION_RE = re.compile(
    r"\b("
    r"(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:test|build|lint|typecheck|check)"
    r"|pytest"
    r"|go\s+(?:test|build|vet)"
    r"|cargo\s+(?:test|build|clippy)"
    r"|tsc"
    r"|eslint"
    r"|make\s+(?:test|build|check)"
    r"|jest"
    r"|vitest"
    r"|ruff"
    r"|mypy"
    r")\b"
)

# B2: inspection commands. Matching is on the first token of the first segment,
# so a pipeline whose head is `ls` counts and one whose head is `python` does
# not, whatever follows (SPEC §4 B2).
INSPECTION_HEADS = frozenset({
    "ls", "cat", "head", "tail", "find", "grep", "rg", "wc", "tree", "pwd",
    "which", "type", "file", "stat", "du", "df", "env", "printenv", "echo",
    "jq", "awk", "sort", "uniq", "column", "nl", "realpath", "basename",
    "dirname",
})
INSPECTION_GIT_SUBCOMMANDS = frozenset({
    "status", "log", "diff", "show", "branch", "remote", "ls-files",
})

# A1: the tools whose call makes an earlier Read of the same path stale.
MUTATING_TOOLS = frozenset({"Edit", "Write"})

RULE_ORDER = ("C1", "C2", "C3", "B1", "B2", "A1")
RULE_TIER = {"C1": "C", "C2": "C", "C3": "C", "B1": "B", "B2": "B", "A1": "A"}
TIER_RULES = {
    "C": ("C1", "C2", "C3"),
    "CB": ("C1", "C2", "C3", "B1", "B2"),
    "CBA": RULE_ORDER,
}

# SPEC §8 defaults.
DEFAULT_KEEP_LAST = 6
DEFAULT_MIN_BYTES = 2048

# The prefix that stays warm across the cut: tools plus system, measured at
# 15,903 tokens on this install (`ContextControl/01-constraints.md:52`, quoted in
# COZEMPIC.md §3.1). It sits before `messages`, so a message-content cut never
# invalidates it and it is excluded from S by construction here — recorded so a
# reader does not go looking for a subtraction that is structurally unnecessary.
BASE_PREFIX_TOKENS = 15_903


@dataclass
class ToolCall:
    """One `tool_use` and the `tool_result` that answered it.

    `order` is the position among tool calls, which is what guard G1 counts in;
    `line` is the transcript line of the result, which is what the cut point is
    measured from.
    """

    order: int
    line: int
    name: str
    tool_input: dict
    result_size: int
    is_error: bool
    has_result: bool


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
        removed = self.tier_bytes(tier)
        if not removed or not self.suffix_bytes:
            return None
        return 19 * (self.suffix_bytes / removed) - 20


# ─── Measurement ─────────────────────────────────────────────────────────────


def _result_size(content) -> int:
    """SPEC §6's measure of a `tool_result` content: `len(str)` or `len(json.dumps(list))`."""
    if isinstance(content, str):
        return len(content)
    if content is None:
        return 0
    try:
        return len(json.dumps(content))
    except (TypeError, ValueError):
        # A result carrying something json cannot serialise is still content the
        # session pays for every turn. Falling back to repr() keeps it counted;
        # returning 0 would quietly shrink the denominator.
        return len(repr(content))


def _input_size(tool_input) -> int:
    if tool_input is None:
        return 0
    try:
        return len(json.dumps(tool_input))
    except (TypeError, ValueError):
        return len(repr(tool_input))


def _canonical_input(tool_input) -> str:
    """The key C2 compares on. Sorted so that key order cannot make two
    identical calls look different."""
    try:
        return json.dumps(tool_input, sort_keys=True)
    except (TypeError, ValueError):
        return repr(tool_input)


def _bash_head(command: str) -> str | None:
    """The first token of the first segment, normalised for SPEC §4 B2.

    Returns `git status`-style two-token heads for git, `sed -n` for the one
    inspection use of sed, and the bare token otherwise. None when there is no
    token to match.
    """
    if not isinstance(command, str):
        return None
    # `&&` and `|` are the separators SPEC §4 B2 names. `||` and `|&` are caught
    # by the `|` split; `;` is deliberately not, because SPEC named two.
    segment = re.split(r"&&|\|", command, maxsplit=1)[0]
    tokens = segment.split()
    if not tokens:
        return None
    head = tokens[0]
    # A leading `VAR=value` is the shell setting the environment for the command
    # that follows, not the command. Skipping it means `FOO=1 ls` is still an
    # `ls`; not skipping it would make the head `FOO=1` and match nothing.
    while "=" in head and not head.startswith("=") and len(tokens) > 1:
        tokens = tokens[1:]
        head = tokens[0]
    head = head.rsplit("/", 1)[-1]  # /bin/ls → ls
    if head == "git" and len(tokens) > 1:
        return f"git {tokens[1]}"
    if head == "sed":
        return "sed -n" if "-n" in tokens[1:2] else "sed"
    return head


def _is_inspection(command: str) -> bool:
    head = _bash_head(command)
    if head is None:
        return False
    if head in INSPECTION_HEADS or head == "sed -n":
        return True
    if head.startswith("git "):
        return head.split(" ", 1)[1] in INSPECTION_GIT_SUBCOMMANDS
    return False


def _read_range(tool_input: dict) -> tuple[str | None, int, float]:
    """`(file_path, start, end)` for a Read, with a missing range meaning the
    whole file.

    SPEC §4 B1 compares ranged reads on `(file_path, offset, limit)` and
    supersedes one only by a read that provably covers its range. A read with
    neither offset nor limit is the whole file, so it covers everything and is
    covered by nothing narrower — which is why `end` is a float: `inf` is the
    only honest upper bound for "to the end of a file whose length is not in the
    transcript".
    """
    path = tool_input.get("file_path")
    if not isinstance(path, str):
        return None, 0, float("inf")
    offset = tool_input.get("offset")
    limit = tool_input.get("limit")
    if offset is None and limit is None:
        return path, 0, float("inf")
    start = offset if isinstance(offset, int) and offset > 0 else 1
    if not isinstance(limit, int) or limit <= 0:
        return path, start, float("inf")
    return path, start, start + limit


# ─── The rule engine ─────────────────────────────────────────────────────────


def classify(calls: list[ToolCall], keep_last: int, min_bytes: int) -> tuple[dict[int, str], dict[str, int]]:
    """Attribute each tool call to the first SPEC §4 rule that fires, or none.

    Returns `(order → rule id)` and a count of what each guard refused, so a
    session where the guards did all the work is distinguishable from one where
    no rule matched.
    """
    guard_blocked = {"G1_keep_last": 0, "G2_min_bytes": 0, "G3_errors": 0, "G5_unpaired": 0}
    eligible: list[ToolCall] = []
    cutoff = len(calls) - keep_last

    for call in calls:
        if not call.has_result:
            # G5 in its read-only form. A `tool_use` with no `tool_result` is the
            # last in-flight call of a session (SPEC §4 measured 5 across 42,966);
            # there is nothing to strip and nothing to pair.
            guard_blocked["G5_unpaired"] += 1
            continue
        if call.order >= cutoff:
            guard_blocked["G1_keep_last"] += 1
            continue
        if call.result_size < min_bytes:
            guard_blocked["G2_min_bytes"] += 1
            continue
        if call.is_error:
            guard_blocked["G3_errors"] += 1
            continue
        eligible.append(call)

    # C2 and B1 and A1 each need to know what happens *later* in the session, so
    # the indices are built once over every call — not only the eligible ones. A
    # guarded result still supersedes an earlier one: the guard protects the
    # result from being stripped, it does not make the call invisible.
    # C2 supersedes an earlier *result* with a later *result*: SPEC §4 words it as
    # "an earlier `tool_result` … byte-identical to a later one". A later call
    # that never returned has no bytes to supersede with, so it is not an index
    # entry — unlike B1 and A1 below, which SPEC words on `tool_use` and which
    # therefore do count a call whose result never arrived.
    last_input_seen: dict[tuple[str, str], int] = {}
    for call in calls:
        if call.has_result:
            last_input_seen[(call.name, _canonical_input(call.tool_input))] = call.order

    reads: list[tuple[int, str, int, float]] = []
    mutations: dict[str, list[int]] = {}
    for call in calls:
        if call.name == "Read":
            path, start, end = _read_range(call.tool_input)
            if path is not None:
                reads.append((call.order, path, start, end))
        elif call.name in MUTATING_TOOLS:
            path = call.tool_input.get("file_path")
            if isinstance(path, str):
                mutations.setdefault(path, []).append(call.order)

    assigned: dict[int, str] = {}
    for call in eligible:
        rule = _first_matching_rule(call, last_input_seen, reads, mutations)
        if rule is not None:
            assigned[call.order] = rule
    return assigned, guard_blocked


def _first_matching_rule(
    call: ToolCall,
    last_input_seen: dict[tuple[str, str], int],
    reads: list[tuple[int, str, int, float]],
    mutations: dict[str, list[int]],
) -> str | None:
    """The first rule in C1, C2, C3, B1, B2, A1 that fires on this call.

    First-match-wins is what makes SPEC §6's per-rule table sum to its own tier
    totals; see the module docstring.
    """
    name = call.name
    tool_input = call.tool_input

    # C1 locator.
    if name in LOCATOR_TOOLS:
        return "C1"
    if name == "Grep" and tool_input.get("output_mode") in LOCATOR_GREP_MODES:
        return "C1"

    # C2 exact duplicate — only the earlier of an identical pair is stripped.
    if last_input_seen.get((name, _canonical_input(tool_input)), call.order) > call.order:
        return "C2"

    if name == "Bash":
        command = tool_input.get("command")
        # C3 passing verification. `is_error` was already excluded by G3, so
        # reaching here means the run passed.
        if isinstance(command, str) and VERIFICATION_RE.search(command):
            return "C3"
        # B2 Bash inspection.
        if _is_inspection(command):
            return "B2"
        return None

    if name == "Read":
        path, start, end = _read_range(tool_input)
        if path is None:
            return None
        # B1 superseded read: a later Read of the same path that provably covers
        # this range.
        for order, other_path, other_start, other_end in reads:
            if (
                order > call.order
                and other_path == path
                and other_start <= start
                and other_end >= end
            ):
                return "B1"
        # A1 read then written, with no intervening Read of that path. An
        # intervening read is the one adjacent to the edit; this one would be
        # superseded by it under B1 rather than made stale by the edit.
        for edit_order in mutations.get(path, ()):
            if edit_order <= call.order:
                continue
            intervening = any(
                call.order < order < edit_order and other_path == path
                for order, other_path, _, _ in reads
            )
            if not intervening:
                return "A1"
    return None


# ─── Reading one session ─────────────────────────────────────────────────────


def _inner(record: dict) -> dict:
    inner = record.get("message")
    return inner if isinstance(inner, dict) else {}


def _blocks(record: dict) -> list:
    content = _inner(record).get("content")
    if isinstance(content, list):
        return content
    return []


def inspect_session(
    path: Path,
    keep_last: int = DEFAULT_KEEP_LAST,
    min_bytes: int = DEFAULT_MIN_BYTES,
) -> Report:
    """Read one transcript and report. Opens the file once, read-only."""
    report = Report(session_id=path.stem, path=path)
    report.content_bytes = {cls: 0 for cls in CONTENT_CLASSES}

    messages = load_messages(path)
    report.records = len(messages)

    calls: list[ToolCall] = []
    results: dict[str, tuple[int, int, bool]] = {}  # tool_use_id → (line, size, is_error)
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
                size = _result_size(block.get("content"))
                report.content_bytes["tool_result"] += size
                use_id = block.get("tool_use_id")
                if isinstance(use_id, str):
                    results[use_id] = (line_index, size, bool(block.get("is_error")))
            elif btype == "tool_use":
                size = _input_size(block.get("input"))
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
            calls.append(ToolCall(order, use_line, name, tool_input, 0, False, False))
            continue
        result_line, size, is_error = found
        calls.append(ToolCall(order, result_line, name, tool_input, size, is_error, True))
        report.tool_result_bytes_by_tool[name] = (
            report.tool_result_bytes_by_tool.get(name, 0) + size
        )

    report.tool_calls = len(calls)
    assigned, report.guard_blocked = classify(calls, keep_last, min_bytes)

    report.rule_bytes = {rule: 0 for rule in RULE_ORDER}
    report.rule_hits = {rule: 0 for rule in RULE_ORDER}
    by_order = {call.order: call for call in calls}
    for order, rule in assigned.items():
        report.rule_bytes[rule] += by_order[order].result_size
        report.rule_hits[rule] += 1

    if assigned:
        report.cut_line = min(by_order[o].line for o in assigned)
        report.suffix_bytes = sum(
            size for line, size in line_content.items() if line >= report.cut_line
        )
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
