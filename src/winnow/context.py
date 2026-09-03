"""`winnow context <session>` — what is actually in one context window.

The walking skeleton of proposals/ContextTreemap (M1). It resolves a session,
parses it, deduplicates the assistant responses, takes the exact window from the
anchoring request, classifies everything still inside that window into the top
level of H1 — provenance, *who put this here* — and apportions the estimate
inside the exact total.

The architecture is `02-constraints.md` §C3 and it is the whole reason to prefer
this over counting bytes: **the total is exact and the parts are apportioned into
it.** Estimates never sum to a total here, so the error lives entirely in *where*
tokens are attributed and never in *how many* there are. What no category claims
is rendered as one `residual` node rather than hidden, and on this slice that
node is large — M1 has no `prefix` node and no `retained reasoning` node, so
roughly the ~40% that `01-` §3.2 measured lands in it. That is the correct
reading of this milestone, not a defect in it.

Four labels and no others (§C2): `exact` is lifted from a number the CLI wrote
down, `estimated` is payload characters over a constant, `derived` is an exact
number minus an estimate (M1 renders none — the two derived blocks are M3), and
`residual` is reserved for the single unattributed node.

Writes nothing, anywhere (§C1).
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path

from .legacy.session import load_messages
from .report import resolve_session

# 01- §2.3 puts the constant in 2.4-3.0 by three independent methods and
# 02-constraints.md's residual-zeroing solve puts it at 2.57 by a fourth. It is
# shipped fixed and never fitted: §C10, a residual that cannot be non-zero is
# not evidence.
CHARS_PER_TOKEN = 2.6

# §C4's closed exclusion list, as the record types that contribute zero tokens.
# `queue-operation` is named in it explicitly because it carries a copy of the
# user's prompt and therefore *looks* like context — 1.96 MB across 530 records
# on this machine, none of it on the wire. `system` is here for the opposite
# reason: 01- §1.1 puts it at "mostly no", and counting a maybe is a guess
# dressed as a measurement.
BOOKKEEPING = frozenset({
    "last-prompt", "ai-title", "mode", "bridge-session", "queue-operation",
    "agent-setting", "permission-mode", "atis-latch", "file-history-delta",
    "file-history-snapshot", "frame-link", "agent-name", "cost-state",
    "artifact-autoreact-ledger", "artifact-comment-monitor", "system",
})

KINDS = ("exact", "derived", "estimated", "residual")

DERIVATION = {
    "exact": "read from usage.{input,cache_creation,cache_read}_tokens on the "
             "anchoring request",
    "derived": "an exact number minus an estimate",
    "estimated": f"payload characters / {CHARS_PER_TOKEN} "
                 "(01- §2.3; the band is 2.4-3.0)",
    "residual": "the window less everything above it; what no kind accounts for",
}

# H1's top level, in the order 01- §5 draws it. `prefix` and `retained
# reasoning` belong here too and are M3's; M1 leaves their tokens in the
# residual rather than drawing an empty node for them.
TOP_LEVEL = ("standing configuration", "conversation", "tool traffic",
             "compaction summary")

NO_ANCHOR = (
    "no assistant record in this session carries a `usage` block, so there is "
    "no exact anchor to apportion into. Every figure below is an estimate of "
    "what the transcript can see and no share is printed: §C3 forbids summing "
    "estimates into a total, and §C2 forbids a percentage of one."
)


@dataclass
class Node:
    """One row of the readout. `children` is always empty in M1 (no drill-down).

    It exists on the type anyway because `--json` is the interface M2 and M3
    build on, and a consumer that has to learn a new shape when the drill-down
    lands is a consumer that will not be updated.
    """

    label: str
    tokens: int
    kind: str
    note: str = ""
    children: list[Node] = field(default_factory=list)


@dataclass
class Composition:
    """Everything the readout needs, as plain numbers. Nothing here prints."""

    path: Path
    records: int
    requests: int
    requests_in_window: int
    model: str | None
    window: int | None
    nodes: list[Node]
    boundaries: list[dict]
    notes: list[str]


# ─── measurement ─────────────────────────────────────────────────────────────


def estimate(chars: float) -> float:
    return chars / CHARS_PER_TOKEN


def payload_chars(block: dict) -> tuple[float, str]:
    """Characters this content block puts on the wire, and a note if it is odd.

    01- §2.4's table. Characters rather than tokens, so that one caller can
    divide by the constant once — images are the exception and hand back a
    character count that has already been multiplied by it, because they are
    priced by area rather than by text (§C5).
    """
    kind = block.get("type")
    if kind == "text":
        return len(block.get("text") or ""), ""
    if kind == "tool_use":
        rendered = json.dumps(block.get("input"), ensure_ascii=False)
        return len(rendered) + len(block.get("name") or ""), ""
    if kind == "thinking":
        # Zero, always. The text is stripped on disk and the signature is 1.4-2.7
        # KB of opaque blob worth no tokens at all (01- §1.3). What the model
        # retained of its own reasoning is priced from output_tokens, in M3.
        return 0.0, ""
    if kind == "image":
        return image_chars(block)
    if kind == "tool_result":
        content = block.get("content")
        if isinstance(content, str):
            return len(content), spill_note(content)
        if isinstance(content, list):
            total, notes = 0.0, []
            for sub in content:
                if not isinstance(sub, dict):
                    continue
                chars, note = payload_chars(sub)
                total += chars
                if note:
                    notes.append(note)
            return total, "; ".join(n for n in notes if n)
    return 0.0, ""


def spill_note(text: str) -> str:
    """§C9 — the block on the wire is a pointer; say so rather than follow it."""
    if "<persisted-output>" not in text:
        return ""
    return ("a <persisted-output> wrapper is sized at the preview the model saw, "
            "not at the tool-results/ sidecar behind it (§C9)")


def image_chars(block: dict) -> tuple[float, str]:
    """§C5 — width x height / 750 from the header, never len(base64)/4.

    Sizing an image by its base64 length over-reports it by 14x (01- §2.5, four
    images measured). Where the header does not parse the block is zero and
    labelled, because a guess that looks like a measurement is worse than a gap.
    """
    source = block.get("source") or {}
    data = source.get("data") or ""
    head = b""
    if data:
        try:
            head = base64.b64decode(data[:6000] + "==", validate=False)
        except ValueError:
            head = b""
    dimensions = (png_dimensions(head) or jpeg_dimensions(head)) if head else None
    if not dimensions:
        return 0.0, ("an image whose header did not parse is sized ZERO and "
                     "labelled, never at len(base64)/4 (§C5)")
    width, height = dimensions
    return width * height / 750 * CHARS_PER_TOKEN, ""


def png_dimensions(head: bytes) -> tuple[int, int] | None:
    if not head.startswith(b"\x89PNG\r\n\x1a\n") or len(head) < 24:
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def jpeg_dimensions(head: bytes) -> tuple[int, int] | None:
    if not head.startswith(b"\xff\xd8"):
        return None
    i = 2
    while i + 9 < len(head):
        if head[i] != 0xFF:
            i += 1
            continue
        marker = head[i + 1]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return (int.from_bytes(head[i + 7:i + 9], "big"),
                    int.from_bytes(head[i + 5:i + 7], "big"))
        i += 2 + int.from_bytes(head[i + 2:i + 4], "big")
    return None


def attachment_chars(attachment: dict) -> float:
    """The payload strings only, recursively.

    §C4: the CLI renders an attachment into prose before it reaches the wire, so
    its JSON keys and structure are this file's scaffolding and not context.
    """
    def strings(obj):
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for value in obj.values():
                yield from strings(value)
        elif isinstance(obj, list):
            for value in obj:
                yield from strings(value)

    return float(sum(len(s) for s in strings(attachment)))


# ─── the walk ────────────────────────────────────────────────────────────────


def priced_responses(records: list[dict]) -> list[dict]:
    """One entry per API response, keyed on `message.id` (§C8).

    One response reaches disk as several JSONL lines, one per content block,
    each repeating the same `usage` object. Summing per line inflates the window
    by 1.7-2.4x (01- §2.1), and a neighbouring repository ships that bug today.
    """
    grouped: dict[str, dict] = {}
    for index, record in enumerate(records):
        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        message_id, usage = message.get("id"), message.get("usage")
        if not message_id or not isinstance(usage, dict):
            continue
        grouped.setdefault(message_id, {
            "index": index,
            "id": message_id,
            "model": message.get("model"),
            "context": ((usage.get("input_tokens") or 0)
                        + (usage.get("cache_creation_input_tokens") or 0)
                        + (usage.get("cache_read_input_tokens") or 0)),
        })
    # A `<synthetic>` record — an interrupt, or an API error the CLI wrote in
    # the model's place — carries a usage object of all zeros. It is not a
    # priced request, and if it lands last it would anchor the readout at zero.
    return sorted((e for e in grouped.values() if e["context"] > 0),
                  key=lambda entry: entry["index"])


def compaction_boundaries(records: list[dict]) -> list[dict]:
    """Every `compact_boundary`'s metadata, in file order (§C6)."""
    return [record.get("compactMetadata") or {}
            for record in records if record.get("subtype") == "compact_boundary"]


def window_start(records: list[dict], before: int) -> int:
    """The first record still inside the window: the last compaction boundary.

    §C6. Session 2551cd0c sums to 416,774 estimated tokens from the top of the
    file against a real final window of 116,030 — a 3.6x over-report for a tool
    that walks from record zero and adds.

    `before` is the anchoring record. A boundary after it emptied a window that
    no request has been priced against yet, so it cannot be the start of the one
    being described; `compose` says so rather than silently using it.
    """
    for index in range(min(before, len(records)) - 1, -1, -1):
        if records[index].get("subtype") == "compact_boundary":
            return index
    return 0


def tool_callers(records: list[dict]) -> dict[str, str]:
    """`tool_use` id -> tool name, so a result can be attributed to its caller.

    Built over the whole file rather than over the window: a result inside the
    window can answer a call that compaction has since dropped, and the pairing
    is by id anyway.
    """
    callers: dict[str, str] = {}
    for record in records:
        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                callers[block.get("id")] = block.get("name") or "?"
    return callers


def classify(records: list[dict], start: int, stop: int,
             notes: list[str]) -> dict[str, float]:
    """H1's top level over the records still in the window, in estimated tokens.

    M1 stops here: no second level, no per-tool and no per-path nodes. The
    question "*which* Bash" is M2's and this cannot answer it.
    """
    callers = tool_callers(records)
    buckets: dict[str, float] = {}

    def add(category: str, chars: float, note: str = "") -> None:
        buckets[category] = buckets.get(category, 0.0) + estimate(chars)
        for reason in note.split("; ") if note else ():
            if reason and reason not in notes:
                notes.append(reason)

    for record in records[start:stop]:
        kind = record.get("type")
        if kind in BOOKKEEPING or record.get("_parse_error"):
            continue
        if kind == "attachment":
            add("standing configuration",
                attachment_chars(record.get("attachment") or {}))
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        if record.get("isCompactSummary"):
            add("compaction summary", message_chars(message, notes))
            continue
        content = message.get("content")
        if isinstance(content, str):
            add("conversation", len(content))
            continue
        if not isinstance(content, list):
            continue
        # A `user` text block is not necessarily a user turn. When the record
        # carries `sourceToolUseID` it is a tool's return delivered outside the
        # tool_result envelope — a Skill body arrives this way. 06-spike-findings
        # §5 measures the cost of keying on `type` alone: 53.0% of session
        # c3566197's window sat under `conversation` before the spike paired
        # these through, which is a confidently drawn, entirely wrong picture.
        # H1 asks who put the material here and the record type does not say.
        source_tool = record.get("sourceToolUseID")
        if source_tool and source_tool in callers:
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    add("tool traffic", len(block.get("text") or ""),
                        f"a `user` text block carrying {callers[source_tool]}'s "
                        "return outside a tool_result envelope is counted as "
                        "tool traffic, paired by sourceToolUseID")
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            chars, note = payload_chars(block)
            block_type = block.get("type")
            if block_type in ("tool_result", "tool_use"):
                add("tool traffic", chars, note)
            else:
                add("conversation", chars, note)
    return buckets


def message_chars(message: dict, notes: list[str]) -> float:
    """Payload characters of one message's whole content, with §C9 notes kept."""
    content = message.get("content")
    if isinstance(content, str):
        return float(len(content))
    if not isinstance(content, list):
        return 0.0
    total = 0.0
    for block in content:
        if not isinstance(block, dict):
            continue
        chars, note = payload_chars(block)
        total += chars
        for reason in note.split("; ") if note else ():
            if reason and reason not in notes:
                notes.append(reason)
    return total


# ─── composition ─────────────────────────────────────────────────────────────


def compose(path: Path, records: list[dict]) -> Composition:
    """Resolve the exact window and apportion the estimate inside it (§C3)."""
    notes: list[str] = []
    priced = priced_responses(records)
    boundaries = compaction_boundaries(records)

    anchor = priced[-1] if priced else None
    window = anchor["context"] if anchor else None
    # Everything before the anchoring assistant record is what that request
    # carried; the anchor's own output was not in the window it was priced for.
    stop = anchor["index"] if anchor else len(records)
    start = window_start(records, stop)
    if anchor and compaction_boundaries(records[stop:]):
        notes.append(
            "a compaction boundary follows the anchoring request, so this "
            "describes the window as it stood at that request and not the one "
            "the session is in now — nothing has been priced since (§C6)")
    buckets = classify(records, start, stop, notes)

    # §C8's trailing fragment: the CLI is appending to this file while it is
    # read, so the last physical line can be half-written JSON. The parser hands
    # it back marked rather than raising; it is counted as unread rather than as
    # a record, because a record it is not yet.
    torn = sum(1 for record in records if record.get("_parse_error"))
    if torn:
        notes.append(
            f"{torn} line(s) did not parse and are not counted — on a live "
            "session the last one is normally a record the CLI is still writing "
            "(§C8)")

    nodes = [Node(label=label, tokens=round(buckets[label]), kind="estimated")
             for label in TOP_LEVEL if round(buckets.get(label, 0.0))]
    nodes.sort(key=lambda node: -node.tokens)
    if window is not None:
        # Subtraction rather than addition, so that the rendered rows sum to the
        # exact window however the rounding falls. This node is the tool's
        # confession and it is load-bearing (§C10).
        nodes.append(Node(label="unattributed",
                          tokens=window - sum(node.tokens for node in nodes),
                          kind="residual"))
    else:
        notes.append(NO_ANCHOR)

    return Composition(
        path=path,
        records=len(records) - torn,
        requests=len(priced),
        requests_in_window=sum(1 for e in priced if e["index"] >= start),
        model=anchor["model"] if anchor else None,
        window=window,
        nodes=nodes,
        boundaries=boundaries,
        notes=notes,
    )


def dropped_tokens(boundaries: list[dict]) -> int:
    """What compaction has taken out of this session, cumulatively and exactly.

    `cumulativeDroppedTokens` is already a running total, so it is read off the
    last boundary rather than summed across them.
    """
    return boundaries[-1].get("cumulativeDroppedTokens") or 0 if boundaries else 0


# ─── rendering ───────────────────────────────────────────────────────────────

BAR_COLUMNS = 22
LABEL_COLUMNS = 44
_HEAD_COLUMNS = BAR_COLUMNS + LABEL_COLUMNS + 4


def bar(share: float) -> str:
    filled = int(share * BAR_COLUMNS)
    if filled:
        return "█" * filled
    return "▏" if share > 0 else " "


def render(composition: Composition, window_argument: int | None) -> str:
    """The terminal readout. No colour, no drill-down — M1 looks like a skeleton."""
    lines: list[str] = []
    window = composition.window
    compaction = (f"{len(composition.boundaries)} compaction boundaries"
                  if composition.boundaries else "no compaction")
    lines.append(
        f"session {composition.path.stem}  ·  {composition.records:,} records  ·  "
        f"{composition.requests} requests ({composition.requests_in_window} in the "
        f"window)  ·  {composition.model or 'no model recorded'}  ·  {compaction}"
    )

    if window is None:
        lines.append(f"{'window at the last request':<{_HEAD_COLUMNS}}"
                     f"{'unanchored':>9}       —  —")
    else:
        lines.append(f"{'window at the last request':<{_HEAD_COLUMNS}}"
                     f"{window:>9,}  100.0%  exact")
    if composition.boundaries:
        last = composition.boundaries[-1]
        lines.append(f"{'dropped by compaction (cumulative)':<{_HEAD_COLUMNS}}"
                     f"{dropped_tokens(composition.boundaries):>9,}       —  exact")
        lines.append(f"  last boundary: {last.get('trigger')} compaction, "
                     f"pre/post {last.get('preTokens') or 0:,} / "
                     f"{last.get('postTokens') or 0:,}")
    if window is not None and window_argument:
        lines.append(f"{f'of a --window of {window_argument:,}':<{_HEAD_COLUMNS}}"
                     f"{100 * window / window_argument:8.1f}% full  exact")
    lines.append("")

    for node in composition.nodes:
        share = node.tokens / window if window else 0.0
        percent = f"{100 * share:5.1f}%" if window else "     —"
        label = node.label if len(node.label) <= LABEL_COLUMNS else (
            "…" + node.label[-(LABEL_COLUMNS - 1):])
        lines.append(f"  {bar(share):<{BAR_COLUMNS}}  {label:<{LABEL_COLUMNS}}"
                     f"{node.tokens:>9,}  {percent}  {node.kind}")

    if window is not None:
        by_kind: dict[str, int] = {}
        for node in composition.nodes:
            by_kind[node.kind] = by_kind.get(node.kind, 0) + node.tokens
        summary = " · ".join(
            f"{kind} {value:,} ({100 * value / window:.1f}%)"
            for kind, value in sorted(by_kind.items(), key=lambda kv: -kv[1]))
        lines.append("")
        lines.append(f"exact {window:,} = {summary}")
    lines.append("")
    lines.append("how each kind was derived")
    for kind in KINDS:
        if any(node.kind == kind for node in composition.nodes) or kind == "exact":
            lines.append(f"  {kind:<10s} {DERIVATION[kind]}")
    for note in composition.notes:
        lines.append(f"  note       {note}")
    if window is not None and not window_argument:
        lines.append("  note       no '% of window full' is printed: nothing in a "
                     "transcript states the window size (§C7). Pass --window N to "
                     "state the denominator yourself.")
    if window is not None:
        lines.append("  note       M1: no prefix node and no retained-reasoning "
                     "node yet, so both sit inside `unattributed`.")
    return "\n".join(lines)


def _figure(tokens: int, kind: str) -> dict:
    return {"tokens": tokens, "kind": kind}


def to_dict(composition: Composition, window_argument: int | None) -> dict:
    """The `--json` shape, which is the real interface (05-, M1).

    Every token figure is an object carrying its own `kind`, so that a consumer
    — or a test — can walk the document and find a number with no provenance
    without knowing which keys exist. §C2 is enforceable rather than reviewed.
    """
    window = composition.window

    def as_dict(node: Node) -> dict:
        return {
            "label": node.label,
            "tokens": node.tokens,
            "kind": node.kind,
            "share": round(node.tokens / window, 6) if window else None,
            "note": node.note,
            "children": [as_dict(child) for child in node.children],
        }

    boundaries = composition.boundaries
    last = boundaries[-1] if boundaries else {}
    return {
        "session": composition.path.stem,
        "path": str(composition.path),
        "records": composition.records,
        "requests": composition.requests,
        "requests_in_window": composition.requests_in_window,
        "model": composition.model,
        "chars_per_token": CHARS_PER_TOKEN,
        "window": _figure(window, "exact") if window is not None else None,
        "fullness": None if not (window and window_argument) else {
            "window_argument": window_argument,
            "percent": round(100 * window / window_argument, 4),
            "kind": "exact",
        },
        "compaction": {
            "boundaries": len(boundaries),
            "dropped": _figure(dropped_tokens(boundaries), "exact"),
            "last_boundary": None if not boundaries else {
                "trigger": last.get("trigger"),
                "pre": _figure(last.get("preTokens") or 0, "exact"),
                "post": _figure(last.get("postTokens") or 0, "exact"),
            },
        },
        "nodes": [as_dict(node) for node in composition.nodes],
        "notes": composition.notes,
        "derivations": DERIVATION,
    }


# ─── the command ─────────────────────────────────────────────────────────────


def context_command(session: str, *, as_json: bool = False,
                    window: int | None = None) -> tuple[int, str]:
    """`(exit code, output)`. 1 usage error, 3 refused — no anchor, no shares.

    Exit 3 rather than 0 when no assistant record carries `usage`: the readout
    is still printed and still useful, but every share and every percentage is
    withheld, and a caller that cannot see the stderr line has to be able to
    tell that from a normal run (§C7, and 05-'s refusable set).
    """
    try:
        path = resolve_session(session)
    except LookupError as exc:
        return 1, f"winnow: {exc}"

    records = [record for _, record, _ in load_messages(path)]
    composition = compose(path, records)
    payload = (json.dumps(to_dict(composition, window), indent=2) if as_json
               else render(composition, window))
    return (0 if composition.window is not None else 3), payload
