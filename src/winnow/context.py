"""`winnow context <session>` — what is actually in one context window.

proposals/ContextTreemap, M1 and M2. It resolves a session, parses it,
deduplicates the assistant responses, takes the exact window from the anchoring
request, classifies everything still inside that window into H1 — provenance,
*who put this here* — and apportions the estimate inside the exact total.

M2 is the drill-down, which is the reason the tool exists. Three levels:
provenance, then the tool or attachment class, then the artefact — a file path
with its repeat count, a Bash command head, an MCP tool, a memory file, one
sub-agent's return. `--depth` caps it and `--by-path` re-keys the `tool traffic`
subtree artefact-first, pooling a path across every tool that touched it,
because 06-spike-findings §4 measured what tool-first keying costs: on session
f6ea2591 the repeated-path share — 01- §5's "single most actionable question
there is" — halves, from 33.2% to 16.8%, because one file read twice and edited
once is two nodes in two different subtrees rather than one node marked ×3.

The architecture is `02-constraints.md` §C3 and it is the whole reason to prefer
this over counting bytes: **the total is exact and the parts are apportioned into
it.** Estimates never sum to a total here, so the error lives entirely in *where*
tokens are attributed and never in *how many* there are. That holds at every
level: a node's children are rounded by largest remainder so they sum to the row
above them exactly. What no category claims is rendered as one `residual` node
rather than hidden, and it is still large — there is no `prefix` node and no
`retained reasoning` node until M3, so roughly the ~40% that `01-` §3.2 measured
lands in it. That is the correct reading of this milestone, not a defect in it.

Four labels and no others (§C2): `exact` is lifted from a number the CLI wrote
down, `estimated` is payload characters over a constant, `derived` is an exact
number minus an estimate (M1 renders none — the two derived blocks are M3), and
`residual` is reserved for the single unattributed node.

Writes nothing, anywhere (§C1).
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .legacy.session import load_messages
from .report import resolve_session
from .rules import bash_head

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
    """One row of the readout, and its drill-down.

    `children` is empty at `--depth 1`, which is exactly M1's readout, and holds
    the tool level at 2 and the artefact level at 3. Children's tokens always
    sum to their parent's, whichever way the rounding falls (`apportion`).
    """

    label: str
    tokens: int
    kind: str
    note: str = ""
    children: list[Node] = field(default_factory=list)
    # The characters behind an estimated row, kept for `--explain` and kept out
    # of `--json`, which is a document about tokens (§C5 — bytes are never an
    # area, and characters are not a unit the readout trades in either).
    chars: float = 0.0


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
    depth: int = 1
    by_path: bool = False
    pooled: dict[str, float] = field(default_factory=dict)
    floor: Floor | None = None
    audit: Audit | None = None


# ─── measurement ─────────────────────────────────────────────────────────────


def estimate(chars: float) -> float:
    return chars / CHARS_PER_TOKEN


def payload_chars(block: dict) -> tuple[float, float, str]:
    """Characters on the wire, tokens on the wire, and a note if it is odd.

    01- §2.4's table. Two numbers rather than one because an image is priced by
    area and not by text (§C5): its cost does not move when the chars-per-token
    constant moves, and `--audit`'s solve for the constant that would zero this
    session's residual has to hold it fixed while everything else scales.
    Everything except an image returns zero in the second slot.
    """
    kind = block.get("type")
    if kind == "text":
        return len(block.get("text") or ""), 0.0, ""
    if kind == "tool_use":
        rendered = json.dumps(block.get("input"), ensure_ascii=False)
        return len(rendered) + len(block.get("name") or ""), 0.0, ""
    if kind == "thinking":
        # Zero, always. The text is stripped on disk and the signature is 1.4-2.7
        # KB of opaque blob worth no tokens at all (01- §1.3). What the model
        # retained of its own reasoning is priced from output_tokens, by
        # `retained_reasoning` below, and lands in its own derived node.
        return 0.0, 0.0, ""
    if kind == "image":
        tokens, note = image_tokens(block)
        return 0.0, tokens, note
    if kind == "tool_result":
        content = block.get("content")
        if isinstance(content, str):
            return len(content), 0.0, spill_note(content)
        if isinstance(content, list):
            total, fixed, notes = 0.0, 0.0, []
            for sub in content:
                if not isinstance(sub, dict):
                    continue
                chars, tokens, note = payload_chars(sub)
                total += chars
                fixed += tokens
                if note:
                    notes.append(note)
            return total, fixed, "; ".join(n for n in notes if n)
    return 0.0, 0.0, ""


def spill_note(text: str) -> str:
    """§C9 — the block on the wire is a pointer; say so rather than follow it."""
    if "<persisted-output>" not in text:
        return ""
    return ("a <persisted-output> wrapper is sized at the preview the model saw, "
            "not at the tool-results/ sidecar behind it (§C9)")


# The wrapper states the sidecar's size in its own first line — `Output too
# large (45.9KB). Full output saved to: …` — so the size that is *not* being
# counted can be put in the label without opening the sidecar, and without
# depending on the sidecar still being there.
SPILL_SIZE = re.compile(r"Output too large \(([\d.]+)\s*(B|KB|MB|GB)\)")
SPILL_UNITS = {"B": 1.0, "KB": 1024.0, "MB": 1024.0 ** 2, "GB": 1024.0 ** 3}


def spilled_bytes(block: dict) -> float:
    """Bytes behind every `<persisted-output>` preview in this block (§C9).

    Carried beside the token count and never added to it: the node is sized at
    what the model saw, and this is what it did *not* see. The two are different
    units on purpose — bytes on disk against tokens on the wire — so that nobody
    can accidentally sum them.
    """
    content = block.get("content")
    if isinstance(content, str):
        return sum(float(size) * SPILL_UNITS[unit]
                   for size, unit in SPILL_SIZE.findall(content))
    if isinstance(content, list):
        return sum(spilled_bytes(sub) if sub.get("type") == "tool_result"
                   else _spilled_in_text(sub)
                   for sub in content if isinstance(sub, dict))
    return 0.0


def _spilled_in_text(block: dict) -> float:
    return sum(float(size) * SPILL_UNITS[unit]
               for size, unit in SPILL_SIZE.findall(block.get("text") or ""))


def human_bytes(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}".replace(".0 ", " ")
        size /= 1024
    return f"{size:.1f} GB"


def image_tokens(block: dict) -> tuple[float, str]:
    """§C5 — width x height / 750 from the header, never len(base64)/4.

    Sizing an image by its base64 length over-reports it by 14x (01- §2.5, four
    images measured). Where the header does not parse the block is zero and
    labelled, because a guess that looks like a measurement is worse than a gap.
    Tokens directly: there is no character count behind this figure to divide.
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
    return width * height / 750, ""


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


# ─── the artefact level (H3, under `tool traffic` rather than at the root) ───

HOME_PREFIX = re.compile(r"^(/Users|/home)/[^/]+")

# The tools whose artefact is a filesystem path, and therefore the tools
# `--by-path` pools across. `Write` is in this list for a measured reason.
# 01- §5 reports "37 distinct file paths, 211,557 characters" on f6ea2591 with
# 34% of that output from paths touched more than once; 06-spike-findings §4
# counted `Read` and `Edit` alone, got 29 paths and 209,163 characters, and
# concluded the acceptance criterion was unmeetable. Counting `Write` too
# reproduces 01- exactly: 37 paths, 211,557 characters, 33.5% repeated. The
# criterion was reachable; one tool was missing from the set.
PATH_TOOLS = frozenset({"Read", "Edit", "Write", "NotebookEdit"})


def redact(path: str) -> str:
    """Collapse any home directory to `~`, not only this process's own.

    A transcript written on the laptop and read in the container carries the
    other machine's home, and the leaf is the actionable part either way.
    """
    if not isinstance(path, str):
        return path
    return HOME_PREFIX.sub("~", path.replace(os.path.expanduser("~"), "~"))


def artefact_key(tool: str, tool_input: dict) -> str | None:
    """What real-world thing this call was about, or nothing.

    H3's node key. `None` where a tool has no artefact — the honest answer for
    most of them, and the reason H3 is not the root: 01- §5's "other" bin would
    otherwise be the largest node in the tree.
    """
    if not isinstance(tool_input, dict):
        return None
    if tool == "Bash":
        head = bash_head(tool_input.get("command") or "")
        return f"$ {head}" if head else None
    if tool in PATH_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        return redact(path) if path else None
    if tool in ("Grep", "Glob"):
        return tool_input.get("pattern")
    if tool == "Skill":
        return tool_input.get("skill")
    return None


def result_key(tool: str, tool_input: dict, by_path: bool) -> tuple[str, ...]:
    """Where one tool result hangs beneath `tool traffic`.

    Two shapes over the same measurement. The default is tool-then-artefact,
    which 05- §M2 mandates and acceptance 2 pins. `by_path` inverts the two so
    that a path read twice and edited once is one node rather than two in
    different subtrees — 06- §4 measures what the default shape costs on
    f6ea2591: the repeated-path share halves, 33.2% to 16.8%.
    """
    if tool.startswith("mcp__"):
        # `per MCP server → tool` (01- §5's H1 sketch), so that six calls to one
        # server are one subtree rather than six second-level nodes.
        parts = tool.split("__")
        server = parts[1] if len(parts) > 1 else "?"
        return (f"mcp__{server} results", "__".join(parts[2:]) or tool)
    artefact = artefact_key(tool, tool_input)
    if by_path and artefact:
        return (artefact, tool)
    return (f"{tool} results",) + ((artefact,) if artefact else ())


def subagent_index(session_path: Path, wanted: set[str]) -> dict[str, dict]:
    """`toolUseId` -> the sub-agent's type, description and *own* window (§C11).

    Only for the ids asked for, and the transcript of each is parsed only then:
    a session with no `Agent` call in its window pays nothing, and one with
    forty pays for forty rather than for every sidecar ever written beside it.
    """
    directory = session_path.with_suffix("") / "subagents"
    if not wanted or not directory.is_dir():
        return {}
    index: dict[str, dict] = {}
    for meta_path in sorted(directory.glob("agent-*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, ValueError):
            continue
        tool_use_id = meta.get("toolUseId")
        if tool_use_id not in wanted or tool_use_id in index:
            continue
        index[tool_use_id] = {
            "agent_type": meta.get("agentType") or "?",
            "description": meta.get("description") or "",
            "window": subagent_window(
                meta_path.with_name(meta_path.name[:-len(".meta.json")] + ".jsonl")),
        }
    return index


def subagent_window(transcript: Path) -> int:
    """The last priced request in a sub-agent's own transcript, or 0.

    Its *own* window, anchored the same way the parent's is, and never added to
    the parent's total — §C11, and 05-'s fourth non-goal.
    """
    if not transcript.is_file():
        return 0
    try:
        priced = priced_responses([r for _, r, _ in load_messages(transcript)])
    except OSError:
        return 0
    return priced[-1]["context"] if priced else 0


def agent_label(tool_use_id: str | None, meta: dict | None) -> str:
    """The return is the node; the sub-agent's own window is a label (§C11).

    Adding the two produces a number that is not the size of any window that
    ever existed, so they are printed in one row and never summed.
    """
    if not meta:
        return f"{(tool_use_id or '?')[-8:]}  [no sidecar found beside this session]"
    own = (f"own window {meta['window']:,}, not added" if meta["window"]
           else "own window unknown")
    description = meta["description"][:40]
    return f"{meta['agent_type']}: {description}  [{own}]"


# ─── the walk ────────────────────────────────────────────────────────────────


def block_identity(block: dict) -> str:
    """A key equal for two copies of the same content block, and cheap.

    `priced_responses` sees every JSONL line of one response and has to keep one
    copy of each block. Serialising every block to compare them is the obvious
    way and it is the expensive one on an 8 MB transcript, so a block that
    already carries something unique is keyed on it: a `tool_use` has an `id`
    and a `thinking` block has a 1.4-2.7 KB signature (01- §1.3). A `text` block
    is its own text, which costs a hash and no serialisation.
    """
    kind = block.get("type")
    if kind == "tool_use" and block.get("id"):
        return f"tool_use:{block['id']}"
    if kind == "thinking" and block.get("signature"):
        return f"thinking:{block['signature']}"
    if kind == "text":
        return f"text:{block.get('text') or ''}"
    return "other:" + json.dumps(block, sort_keys=True, ensure_ascii=False)


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
        entry = grouped.setdefault(message_id, {
            "index": index,
            "id": message_id,
            "model": message.get("model"),
            "context": ((usage.get("input_tokens") or 0)
                        + (usage.get("cache_creation_input_tokens") or 0)
                        + (usage.get("cache_read_input_tokens") or 0)),
            "output_tokens": usage.get("output_tokens") or 0,
            "blocks": {},
        })
        # The blocks of one response arrive across those several lines and
        # nothing in a line says which index it carries, so they are collected
        # under the response and deduplicated on their own content. This is what
        # makes `output_tokens` usable: it prices the whole response, so it can
        # only be compared against the whole response's visible output.
        for block in message.get("content") or []:
            if isinstance(block, dict):
                entry["blocks"][block_identity(block)] = block
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


def tool_callers(records: list[dict]) -> dict[str, tuple[str, dict]]:
    """`tool_use` id -> (tool name, its input), so a result knows its caller.

    Built over the whole file rather than over the window: a result inside the
    window can answer a call that compaction has since dropped, and the pairing
    is by id anyway. The input comes along because the artefact — the path, the
    command head, the MCP server — is only in the call, never in the result.
    """
    callers: dict[str, tuple[str, dict]] = {}
    for record in records:
        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                callers[block.get("id")] = (block.get("name") or "?",
                                            block.get("input") or {})
    return callers


@dataclass
class Leaf:
    """One accumulation point in the flat `key -> measurement` map.

    `count` is appearances at exactly this key — the `×N` on a path node, which
    is the actionable half of H3 — and `spilled` is the bytes sitting behind a
    `<persisted-output>` preview, carried so the label can name what the node is
    deliberately *not* sized at (§C9).

    Characters and fixed tokens are kept apart rather than collapsed into one
    figure so that `--audit` can re-price the whole window at a different
    chars-per-token constant without re-walking it, and without an image — which
    is priced by area (§C5) — silently scaling with a constant it does not use.
    """

    chars: float = 0.0
    fixed: float = 0.0
    count: int = 0
    spilled: float = 0.0

    @property
    def tokens(self) -> float:
        return estimate(self.chars) + self.fixed


@dataclass
class PathUse:
    """Every appearance of one artefact path, pooled across the tools that touched it.

    Built during the same walk that builds the tree, whichever keying the tree
    is using, because "which file is in my window more than once" is a fact
    about the session and not about the shape it happens to be drawn in.
    """

    tokens: float = 0.0
    tools: dict[str, int] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return sum(self.tools.values())

    def describe(self) -> str:
        parts = [f"{tool} ×{n}" if n > 1 else tool
                 for tool, n in sorted(self.tools.items(), key=lambda kv: -kv[1])]
        prefix = f"×{self.count} " if self.count > 1 else ""
        return f"{prefix}({', '.join(parts)})"


@dataclass
class Delegations:
    """§C11's tally: how many sub-agents returned into this window, and what
    they spent in their own. Reported beside the node and never summed into it."""

    count: int = 0
    spent: int = 0

    def record(self, meta: dict | None) -> None:
        self.count += 1
        self.spent += (meta or {}).get("window", 0)

    def note(self) -> str:
        # `spent` is zero when no sidecar was found beside the session, which is
        # a different statement from "they spent nothing" and has to read as one.
        own = (f"the {self.spent:,} tokens those sub-agents spent in their own "
               "windows are printed in the label and never added to this one"
               if self.spent else
               "no sub-agent transcript was found beside this session, so their "
               "own windows are unknown rather than zero")
        return (f"{self.count} sub-agent return(s) are sized at what came back; "
                f"{own} (§C11)")


def content_key(block: dict, record: dict, callers: dict, agents: dict,
                delegations: Delegations, by_path: bool) -> tuple[str, ...]:
    """Where one content block hangs in H1. The only place the shape is decided."""
    block_type = block.get("type")
    if block_type == "tool_result":
        tool, tool_input = callers.get(block.get("tool_use_id"), ("(unpaired)", {}))
        if tool == "Agent":
            meta = agents.get(block.get("tool_use_id"))
            delegations.record(meta)
            return ("tool traffic", "Agent returns",
                    agent_label(block.get("tool_use_id"), meta))
        return ("tool traffic",) + result_key(tool, tool_input, by_path)
    if block_type == "tool_use":
        # A sibling of the result nodes rather than a child of them (05- §M2's
        # second acceptance): an `Edit` input carries the new content and is
        # routinely larger than the result it produces, so folding the two
        # together hides which of the pair is the cost. 06- §4 measured `Write
        # ×9` inputs at 21.8% of one window three rows from `Write results` at
        # 0.3%.
        return ("tool traffic", "tool_use inputs", block.get("name") or "?")
    if block_type == "image":
        return ("conversation", "images")
    if record.get("isMeta"):
        return ("conversation", "harness notices")
    if record.get("type") == "assistant":
        return ("conversation", "assistant text")
    return ("conversation", "user turns")


def pool_paths(records: list[dict], start: int, stop: int,
               callers: dict[str, tuple[str, dict]]) -> dict[str, PathUse]:
    """Every artefact path in the window, pooled across the tools that touched it.

    Its own walk rather than a side effect of building the tree, because "which
    file is in my window more than once" is a fact about the session and not
    about the shape it happens to be drawn in — so the readout can state the
    number even in the keying that cannot reach it (06- §4).
    """
    paths: dict[str, PathUse] = {}
    for record in records[start:stop]:
        message = record.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue
        for block in message["content"]:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tool, tool_input = callers.get(block.get("tool_use_id"), ("", {}))
            if tool not in PATH_TOOLS:
                continue
            artefact = artefact_key(tool, tool_input)
            if not artefact:
                continue
            chars, fixed, _ = payload_chars(block)
            use = paths.setdefault(artefact, PathUse())
            # `Read` on a PNG comes back as an image block inside the result, so
            # a path node can carry area-priced tokens and no characters at all.
            use.tokens += estimate(chars) + fixed
            use.tools[tool] = use.tools.get(tool, 0) + 1
    return paths


def classify(records: list[dict], start: int, stop: int, notes: list[str],
             callers: dict[str, tuple[str, dict]], agents: dict[str, dict],
             *, by_path: bool = False) -> dict[tuple[str, ...], Leaf]:
    """H1 over the records still in the window, keyed all the way to the artefact.

    The key is a tuple, which is the whole of M2: `("tool traffic", "Read
    results", "~/src/db.ts")` is one row of a flat map that `build_tree` nests.
    Nothing here knows about depth, sorting or rendering.
    """
    leaves: dict[tuple[str, ...], Leaf] = {}
    delegations = Delegations()

    def add(key: tuple[str, ...], chars: float, note: str = "",
            spilled: float = 0.0, fixed: float = 0.0) -> None:
        leaf = leaves.setdefault(key, Leaf())
        leaf.chars += chars
        leaf.fixed += fixed
        leaf.count += 1
        leaf.spilled += spilled
        # A block can raise several notes at once; dedupe the reasons rather
        # than the joined string, or a session with ten images prints ten lines.
        for reason in note.split("; ") if note else ():
            if reason and reason not in notes:
                notes.append(reason)

    for record in records[start:stop]:
        kind = record.get("type")
        if kind in BOOKKEEPING or record.get("_parse_error"):
            continue
        if kind == "attachment":
            for key, chars in attachment_keys(record.get("attachment") or {}):
                add(key, chars)
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        if record.get("isCompactSummary"):
            summary_chars, summary_fixed = message_chars(message, notes)
            add(("compaction summary",), summary_chars, fixed=summary_fixed)
            continue
        content = message.get("content")
        if isinstance(content, str):
            add(("conversation", "user turns"), len(content))
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
            tool, tool_input = callers[source_tool]
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    add(("tool traffic",) + result_key(tool, tool_input, by_path),
                        len(block.get("text") or ""),
                        f"a `user` text block carrying {tool}'s "
                        "return outside a tool_result envelope is counted as "
                        "tool traffic, paired by sourceToolUseID")
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            chars, fixed, note = payload_chars(block)
            add(content_key(block, record, callers, agents, delegations, by_path),
                chars, note, spilled_bytes(block), fixed)

    if delegations.count:
        notes.append(delegations.note())
    return leaves


def agent_results(records: list[dict], start: int, stop: int,
                  callers: dict[str, tuple[str, dict]]) -> set[str]:
    """The `tool_use` ids of every `Agent` return still inside the window."""
    wanted: set[str] = set()
    for record in records[start:stop]:
        message = record.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue
        for block in message["content"]:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tool_use_id = block.get("tool_use_id")
            if callers.get(tool_use_id, ("", {}))[0] == "Agent":
                wanted.add(tool_use_id)
    return wanted


def attachment_keys(attachment: dict) -> list[tuple[tuple[str, ...], float]]:
    """`standing configuration` → attachment class → the file or server named.

    Only the two classes that name one (05- §M2): `nested_memory` carries the
    memory file's path, and `mcp_instructions_delta` carries one block of prose
    per server, so the server can take its own block's characters rather than a
    share of the whole attachment.
    """
    kind = attachment.get("type") or "?"
    if kind == "nested_memory":
        leaf = redact(attachment.get("path") or attachment.get("displayPath") or "")
        return [(("standing configuration", kind) + ((leaf,) if leaf else ()),
                 attachment_chars(attachment))]
    if kind == "mcp_instructions_delta":
        names = attachment.get("addedNames") or []
        blocks = attachment.get("addedBlocks") or []
        weights = [float(len(name) + len(block)) for name, block in zip(names, blocks)]
        if names and len(names) == len(blocks) and sum(weights) > 0:
            # The attachment's own total, split between servers by the length of
            # each server's block. Splitting rather than taking the blocks
            # directly keeps the parent equal to the sum of its children, which
            # is the one thing a drill-down must not get wrong.
            total = attachment_chars(attachment)
            return [(("standing configuration", kind, str(name)),
                     total * weight / sum(weights))
                    for name, weight in zip(names, weights)]
    return [(("standing configuration", kind), attachment_chars(attachment))]


def message_chars(message: dict, notes: list[str]) -> tuple[float, float]:
    """Payload characters and fixed tokens of one message, with §C9 notes kept."""
    content = message.get("content")
    if isinstance(content, str):
        return float(len(content)), 0.0
    if not isinstance(content, list):
        return 0.0, 0.0
    total, fixed = 0.0, 0.0
    for block in content:
        if not isinstance(block, dict):
            continue
        chars, block_fixed, note = payload_chars(block)
        total += chars
        fixed += block_fixed
        for reason in note.split("; ") if note else ():
            if reason and reason not in notes:
                notes.append(reason)
    return total, fixed


# ─── the floor, priced (M3) ──────────────────────────────────────────────────
#
# Two blocks that are in every window and in no transcript, and neither is a
# guess. `02-constraints.md`'s correction measures them at a median 24% and 14%
# of the window, which is 38% of it that M1 and M2 had to leave in the residual.
# Both are **derived** — an exact number the CLI wrote down, minus an estimate —
# rather than estimated, so they survive the chars-per-token argument better
# than anything else on the screen (§C2).


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def response_output(entry: dict) -> tuple[float, int]:
    """Characters this response wrote to disk, and its thinking-block count.

    Text and `tool_use` only. A thinking block's text is stripped before the
    line is written (01- §1.3) so it contributes nothing here, and that absence
    is the entire instrument: `output_tokens` prices everything the model
    emitted, two of the three kinds are on disk verbatim, and what the
    subtraction leaves is the third.
    """
    chars, thinking = 0.0, 0
    for block in entry["blocks"].values():
        kind = block.get("type")
        if kind == "text":
            chars += len(block.get("text") or "")
        elif kind == "tool_use":
            chars += (len(json.dumps(block.get("input"), ensure_ascii=False))
                      + len(block.get("name") or ""))
        elif kind == "thinking":
            thinking += 1
            chars += len(block.get("thinking") or "")
    return chars, thinking


@dataclass
class Floor:
    """The two derived blocks, and every number they were derived from.

    Kept whole rather than reduced to two totals because `--explain prefix` owes
    the operator three numbers and a subtraction rather than a paragraph, and
    because `--audit` re-prices the retained-reasoning sum at other constants.

    `output` is one `(output_tokens, visible chars)` pair per response still
    inside the window — which is the whole of H2, the per-turn dataset, built
    here as a side effect of pricing reasoning. M4 would render it as
    `--by-turn`; nothing here does.
    """

    first_context: int
    first_index: int
    visible_before_chars: float
    visible_before_fixed: float
    prefix: float
    retained: float
    thinking_blocks: int
    thinking_responses: int
    per_block_median: float
    control_median: float
    control_responses: int
    output: list[tuple[int, float]] = field(default_factory=list)

    @property
    def visible_before_first(self) -> float:
        return estimate(self.visible_before_chars) + self.visible_before_fixed

    @property
    def claims_prefix(self) -> bool:
        """§C7 — measure the prefix per session, or do not claim one.

        A subtraction that comes out at or below zero says the estimate of the
        material before the first request exceeds what that request was priced
        at. That is a statement about the estimator, not about the prefix, so
        the node is not drawn and `--audit` says why.
        """
        return self.prefix > 0


def visible_material(records: list[dict], start: int, stop: int,
                     callers: dict[str, tuple[str, dict]]) -> tuple[float, float]:
    """Characters and area-priced tokens in one slice of the transcript.

    The prefix subtraction has to be in the tool's own units or the books do not
    balance, so it runs the same classifier over the records before the first
    priced request rather than a second, simpler walk that would drift from it
    the first time either changed.
    """
    scratch: list[str] = []
    leaves = classify(records, start, stop, scratch, callers, {}).values()
    return (sum(leaf.chars for leaf in leaves),
            sum(leaf.fixed for leaf in leaves))


def price_floor(records: list[dict], priced: list[dict], start: int, stop: int,
                callers: dict[str, tuple[str, dict]]) -> Floor | None:
    """Prefix by first-request subtraction; reasoning by per-response subtraction.

        prefix    = ctx(first request in this window) - est(visible before it)
        retained  = Σ max(0, output_tokens - est(text + tool_use)) over responses
                    still inside the window and before the anchoring one

    The anchor is excluded from the sum because its own output was not in the
    window it was priced for — the same reason `compose` stops the tree at it.
    The clamp at zero is the prototype's and it is not free: a response the
    estimator over-explains contributes nothing rather than a negative, which
    biases `retained` upwards. It is kept because the alternative charges
    reasoning for the estimator's error in the other direction, and because the
    control below states what that error is on responses that did no reasoning.
    """
    in_window = [entry for entry in priced if start <= entry["index"] <= stop]
    if not in_window:
        return None
    first = in_window[0]
    before_chars, before_fixed = visible_material(records, start, first["index"],
                                                  callers)

    retained, blocks, per_block, control, output = 0.0, 0, [], [], []
    for entry in in_window:
        if entry["index"] >= stop or entry["output_tokens"] <= 0:
            continue
        chars, thinking = response_output(entry)
        left = entry["output_tokens"] - estimate(chars)
        output.append((entry["output_tokens"], chars))
        retained += max(0.0, left)
        if thinking:
            blocks += thinking
            per_block.append(left / thinking)
        else:
            control.append(left)

    return Floor(
        first_context=first["context"],
        first_index=first["index"],
        visible_before_chars=before_chars,
        visible_before_fixed=before_fixed,
        prefix=first["context"] - estimate(before_chars) - before_fixed,
        retained=retained,
        thinking_blocks=blocks,
        thinking_responses=len(per_block),
        per_block_median=median(per_block),
        control_median=median(control),
        control_responses=len(control),
        output=output,
    )


@dataclass
class Audit:
    """The reconciliation, and the constant that would zero it — not applied.

    §C10 is why this is a record and not a switch. The solved constant is a
    diagnostic: fitting it would make the residual zero by construction and
    destroy the tool's only self-check, and worse, it would silently absorb any
    category the classifier missed and report perfect books over a wrong model.
    There is deliberately no flag that applies it.
    """

    window: int
    visible_chars: float
    visible_fixed: float
    prefix_chars: float
    prefix_fixed: float
    first_context: int
    output: list[tuple[int, float]]
    claims_prefix: bool

    def parts_at(self, constant: float) -> tuple[float, float, float]:
        """Visible, prefix and retained, re-priced at one chars-per-token value.

        Images are in `*_fixed` and do not move: they are priced by area (§C5),
        so a sweep that scaled them too would be sweeping a number that has no
        characters behind it.
        """
        visible = self.visible_chars / constant + self.visible_fixed
        prefix = self.first_context - self.prefix_chars / constant - self.prefix_fixed
        retained = sum(max(0.0, out - chars / constant)
                       for out, chars in self.output)
        # Mirror what is drawn rather than what could be: a prefix this session
        # does not claim is not in the tree, so it is not in the solve either.
        return visible, (prefix if prefix > 0 else 0.0), retained

    def residual_at(self, constant: float) -> float:
        return self.window - sum(self.parts_at(constant))

    def solve(self) -> float | None:
        """Bisect for the constant that zeroes the residual, or `None`.

        Bisection rather than algebra because the retained-reasoning term is
        piecewise: each response's contribution is clamped at zero, so the
        residual is continuous in the constant and not smooth. `None` when no
        constant in the bracket balances the books, which is the honest answer
        for a session whose residual has the same sign at both ends.
        """
        low, high = 0.5, 20.0
        if self.residual_at(low) * self.residual_at(high) > 0:
            return None
        for _ in range(48):
            middle = (low + high) / 2
            if self.residual_at(low) * self.residual_at(middle) <= 0:
                high = middle
            else:
                low = middle
        return (low + high) / 2


# ─── the tree ────────────────────────────────────────────────────────────────


@dataclass
class Branch:
    """The nested form of `classify`'s flat map, still in unrounded tokens."""

    key: str
    tokens: float = 0.0
    chars: float = 0.0
    count: int = 0
    spilled: float = 0.0
    children: dict[str, Branch] = field(default_factory=dict)


def build_tree(leaves: dict[tuple[str, ...], Leaf]) -> dict[str, Branch]:
    """Nest the flat map, summing tokens and sidecar bytes up every level."""
    roots: dict[str, Branch] = {}
    for key, leaf in leaves.items():
        here, branch = roots, None
        for part in key:
            branch = here.setdefault(part, Branch(key=part))
            branch.tokens += leaf.tokens
            branch.chars += leaf.chars
            branch.spilled += leaf.spilled
            here = branch.children
        if branch is not None:
            # The repeat count belongs to the exact key, not to its ancestors:
            # `Read results` appearing 40 times is not `db.ts ×40`.
            branch.count += leaf.count
    return roots


def apportion(values: list[float], target: int) -> list[int]:
    """Round a level's shares so they sum to their parent's rounded total exactly.

    Largest remainder, because the alternative — rounding each child on its own
    — leaves a drill-down whose children do not add up to the row above them,
    and a tool whose whole claim is that the rows sum cannot afford that.
    """
    if not values:
        return []
    total = sum(values)
    if total <= 0:
        return [0] * len(values)
    scaled = [value * target / total for value in values]
    amounts = [math.floor(share) for share in scaled]
    short = target - sum(amounts)
    order = sorted(range(len(values)), key=lambda i: -(scaled[i] - amounts[i]))
    for index in order[:max(0, short)]:
        amounts[index] += 1
    return amounts


def materialise(branches: dict[str, Branch], target: int, labels: dict, prefix: tuple,
                depth: int, level: int) -> list[Node]:
    """Turn one level of `Branch` into sorted, rounded `Node`s.

    `level` is the depth of the nodes being made — 2 for a top node's children —
    so `--depth 1` is exactly M1's readout and `--depth 3` reaches the artefact.
    Biggest-first at every level, and no roll-up of the tail: the tree and
    `--json` render identically, and a tool asked *which* file cannot answer
    "17 more, each smaller".
    """
    if level > depth or not branches:
        return []
    ordered = sorted(branches.values(), key=lambda branch: -branch.tokens)
    nodes = []
    for branch, amount in zip(ordered, apportion([b.tokens for b in ordered], target)):
        key = prefix + (branch.key,)
        node = Node(label=decorate(branch, labels.get(key), level),
                    tokens=amount, kind="estimated", note=spill_label(branch),
                    chars=branch.chars)
        node.children = materialise(branch.children, amount, labels, key,
                                    depth, level + 1)
        # §C9 belongs on the innermost row that is drawn: the sidecar figure is
        # summed up the tree, so a parent whose child already says it would
        # print the same sentence twice. At a depth that cuts the child off,
        # the parent says it instead.
        if any(child.note for child in node.children):
            node.note = ""
        nodes.append(node)
    return nodes


def decorate(branch: Branch, override: str | None, level: int) -> str:
    """The rendered label: the key, its repeat count, and nothing else.

    The count goes on the label rather than into a note because it is the
    actionable half of H3 — 01- §5 measured 34% of `Read`/`Edit` output on
    f6ea2591 coming from paths touched more than once — and a note is read last.
    Only from the third level down, where the key is an artefact rather than a
    category: `Read results ×40` says nothing anyone can act on.
    """
    if override:
        return override
    return f"{branch.key}  ×{branch.count}" if level >= 3 and branch.count > 1 \
        else branch.key


def spill_label(branch: Branch) -> str:
    """§C9, on the node it happened to: what this row is *not* sized at."""
    if not branch.spilled:
        return ""
    return (f"sized at the <persisted-output> preview the model saw; "
            f"{human_bytes(branch.spilled)} of sidecar behind it, not counted (§C9)")


def path_labels(paths: dict[str, PathUse]) -> dict[tuple[str, ...], str]:
    """`--by-path`'s second-level labels: the path, with its per-tool counts.

    Visible at `--depth 2`, where the per-tool children are cut, which is the
    point of pooling — one row per file that says how it got there.
    """
    return {("tool traffic", path): f"{path}  {use.describe()}"
            for path, use in paths.items()}


def pooled(paths: dict[str, PathUse]) -> dict[str, float]:
    """01- §5's headline, computed on this session rather than transcribed.

    "Which file is in my window more than once, and do I need any of them" —
    the number that keying the tree tool-first halves (06- §4).
    """
    total = sum(use.tokens for use in paths.values())
    repeated = sum(use.tokens for use in paths.values() if use.count > 1)
    return {
        "paths": len(paths),
        "repeated_paths": sum(1 for use in paths.values() if use.count > 1),
        "tokens": total,
        "repeated_tokens": repeated,
        "repeated_percent": 100 * repeated / total if total else 0.0,
    }


# ─── composition ─────────────────────────────────────────────────────────────


def compose(path: Path, records: list[dict], *, depth: int = 1,
            by_path: bool = False) -> Composition:
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
    callers = tool_callers(records)
    agents = subagent_index(path, agent_results(records, start, stop, callers))
    leaves = classify(records, start, stop, notes, callers, agents, by_path=by_path)
    paths = pool_paths(records, start, stop, callers)
    tree = build_tree(leaves)
    labels = path_labels(paths) if by_path else {}

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

    nodes = [Node(label=label, tokens=round(tree[label].tokens), kind="estimated",
                  chars=tree[label].chars)
             for label in TOP_LEVEL if label in tree and round(tree[label].tokens)]
    for node in nodes:
        node.children = materialise(tree[node.label].children, node.tokens,
                                    labels, (node.label,), depth, level=2)

    floor = price_floor(records, priced, start, stop, callers) if anchor else None
    if floor is not None:
        nodes.extend(floor_nodes(floor, notes))
    nodes.sort(key=lambda node: -node.tokens)
    if window is not None:
        # Subtraction rather than addition, so that the rendered rows sum to the
        # exact window however the rounding falls. This node is the tool's
        # confession and it is load-bearing (§C10). It is allowed to be
        # negative: over-explaining a window is what an unbiased estimator does
        # on about a third of sessions, and hiding the sign would make the one
        # number that audits the tool the one number the tool tidies up.
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
        depth=depth,
        by_path=by_path,
        pooled=pooled(paths),
        floor=floor,
        audit=None if floor is None or window is None else Audit(
            window=window,
            visible_chars=sum(leaf.chars for leaf in leaves.values()),
            visible_fixed=sum(leaf.fixed for leaf in leaves.values()),
            prefix_chars=floor.visible_before_chars,
            prefix_fixed=floor.visible_before_fixed,
            first_context=floor.first_context,
            output=floor.output,
            claims_prefix=floor.claims_prefix,
        ),
    )


def floor_nodes(floor: Floor, notes: list[str]) -> list[Node]:
    """M3's two derived rows, and the note for a prefix this session cannot claim."""
    nodes = []
    if floor.claims_prefix:
        nodes.append(Node(
            label="prefix", tokens=round(floor.prefix), kind="derived",
            note=(f"{floor.first_context:,} exact at the first request in this "
                  f"window, less {round(floor.visible_before_first):,} estimated "
                  "visible before it — the system prompt and tool definitions, "
                  "which no transcript records (--explain prefix)")))
    else:
        notes.append(
            f"no prefix node: the first request in this window was priced at "
            f"{floor.first_context:,} and the transcript before it estimates to "
            f"{round(floor.visible_before_first):,}, so the subtraction comes out "
            f"at {round(floor.prefix):,}. That is a statement about the estimate "
            "and not about the prefix, and §C7 says measure it per session or do "
            "not claim one — so it stays in `unattributed`.")
    if round(floor.retained):
        nodes.append(Node(
            label="retained reasoning", tokens=round(floor.retained),
            kind="derived",
            note=(f"{floor.thinking_blocks:,} thinking blocks over "
                  f"{floor.thinking_responses:,} responses, median "
                  f"{floor.per_block_median:,.0f} tokens per block in this "
                  f"session; the control is {floor.control_responses:,} "
                  f"responses with no thinking block, median "
                  f"{floor.control_median:,.0f} left over")))
    return nodes


def dropped_tokens(boundaries: list[dict]) -> int:
    """What compaction has taken out of this session, cumulatively and exactly.

    `cumulativeDroppedTokens` is already a running total, so it is read off the
    last boundary rather than summed across them.
    """
    return boundaries[-1].get("cumulativeDroppedTokens") or 0 if boundaries else 0


# ─── rendering ───────────────────────────────────────────────────────────────

BAR_COLUMNS = 22
LABEL_COLUMNS = 54
_HEAD_COLUMNS = BAR_COLUMNS + LABEL_COLUMNS + 4


def bar(share: float) -> str:
    """The magnitude, in a glyph that says which side of zero it is on.

    A negative residual is normal rather than exceptional — the estimator
    over-explains the window on roughly a third of sessions (02-, and 60 of 162
    on this run's own sweep) — and `03-option-a`'s mock readout does not
    contemplate one. Drawn hatched and leading with a minus so that
    over-explained reads differently from under-explained at a glance, rather
    than as an empty row that looks like a rounding artefact.
    """
    filled = min(BAR_COLUMNS, int(abs(share) * BAR_COLUMNS))
    if share < 0:
        return "-" + "▒" * min(BAR_COLUMNS - 1, filled)
    if filled:
        return "█" * filled
    return "▏" if share > 0 else " "


def walk(nodes: list[Node], level: int = 1):
    """Every node in render order, with its depth, parents before children."""
    for node in nodes:
        yield node, level
        yield from walk(node.children, level + 1)


def indent(label: str, level: int) -> str:
    """One label column, indented by level, truncated from the *left*.

    Left, because these labels are mostly paths and the leaf is the actionable
    part: `…/winnow/src/winnow/context.py` beats `/workspace/.uf-worktree…`.
    """
    room = LABEL_COLUMNS - 2 * (level - 1)
    if len(label) > room:
        label = "…" + label[-(room - 1):]
    return "  " * (level - 1) + f"{label:<{room}}"


def pooled_line(stats: dict[str, float]) -> str:
    """Acceptance 5: the pooled figures, computed here rather than transcribed."""
    if not stats.get("paths"):
        return ("pooled by path: no Read/Edit/Write result in this window names a "
                "file path")
    return (f"pooled by path: {stats['paths']:,.0f} distinct paths across "
            f"{'/'.join(sorted(PATH_TOOLS - {'NotebookEdit'}))}, "
            f"{stats['tokens']:,.0f} estimated tokens, of which "
            f"{stats['repeated_percent']:.1f}% came from the "
            f"{stats['repeated_paths']:,.0f} path(s) touched more than once")


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

    for node, level in walk(composition.nodes):
        share = node.tokens / window if window else 0.0
        percent = f"{100 * share:5.1f}%" if window else "     —"
        lines.append(f"  {bar(share):<{BAR_COLUMNS}}  {indent(node.label, level)}"
                     f"{node.tokens:>9,}  {percent}  {node.kind}")
        if node.note:
            lines.append(f"  {'':<{BAR_COLUMNS}}  {'  ' * level}· {node.note}")

    if composition.by_path:
        lines.append("")
        lines.append(pooled_line(composition.pooled))

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
    if any(node.kind == "residual" and node.tokens < 0 for node in composition.nodes):
        lines.append("  note       the residual is negative: this readout explains "
                     "more of the window than there is. That is what an unbiased "
                     "estimator does on roughly a third of sessions and it is "
                     "printed with its sign rather than clamped (§C10).")
    if composition.depth < 3:
        lines.append(f"  note       drawn to --depth {composition.depth}; "
                     "--depth 3 reaches the file paths and Bash command heads.")
    return "\n".join(lines)


# ─── the audit ───────────────────────────────────────────────────────────────

NOT_APPLIED = (
    "NOT APPLIED, and there is no flag that applies it. Fitting the constant to "
    "zero the residual would make the residual zero by construction and destroy "
    "the only self-check this tool has; worse, it would silently absorb any "
    "category the classifier missed and report perfect books over a wrong model. "
    "A residual that cannot be non-zero is not evidence (§C10)."
)


def audit_rows(composition: Composition) -> list[tuple[str, int, str]]:
    """The reconciliation, as `(what, tokens, kind)` in subtraction order.

    Every top-level node, signed the way the arithmetic reads: the window, less
    each thing that claims part of it, leaving the residual.
    """
    rows = [("window at the last request", composition.window or 0, "exact")]
    for node in composition.nodes:
        if node.kind == "residual":
            continue
        rows.append((f"less {node.label}", -node.tokens, node.kind))
    residual = next((n for n in composition.nodes if n.kind == "residual"), None)
    if residual is not None:
        rows.append(("= unattributed", residual.tokens, "residual"))
    return rows


def render_audit(composition: Composition) -> str:
    """`--audit` — the full reconciliation, and the constant it does not apply."""
    audit, floor, window = composition.audit, composition.floor, composition.window
    lines = ["", "audit — the reconciliation, at "
             f"{CHARS_PER_TOKEN} chars/token"]
    if audit is None or floor is None or not window:
        lines.append("  there is no exact anchor in this session, so there are no "
                     "books to balance. " + NO_ANCHOR)
        return "\n".join(lines)

    for label, tokens, kind in audit_rows(composition):
        share = tokens / window
        lines.append(f"  {label:<{_HEAD_COLUMNS - 2}}{tokens:>9,}  "
                     f"{100 * share:5.1f}%  {kind}")

    lines.append("")
    lines.append("  the prefix, by first-request subtraction")
    lines.append(f"    {floor.first_context:>12,}   context at the first request "
                 "in this window, exact")
    lines.append(f"    {round(floor.visible_before_first):>12,}   estimated visible "
                 f"in the transcript before it "
                 f"({round(floor.visible_before_chars):,} chars / {CHARS_PER_TOKEN})")
    lines.append(f"    {round(floor.prefix):>12,}   = prefix"
                 + ("" if floor.claims_prefix else
                    "  — not claimed, and not drawn: §C7"))

    lines.append("")
    lines.append("  retained reasoning, by per-response subtraction")
    lines.append(f"    {len(floor.output):>12,}   responses inside the window and "
                 "before the anchoring one")
    lines.append(f"    {floor.thinking_blocks:>12,}   thinking blocks over "
                 f"{floor.thinking_responses:,} of them, median "
                 f"{floor.per_block_median:,.0f} tokens each")
    lines.append(f"    {floor.control_responses:>12,}   responses with no thinking "
                 f"block — the control — median {floor.control_median:,.0f} left "
                 "over")
    lines.append(f"    {round(floor.retained):>12,}   = retained reasoning")
    lines.append("    the control is the estimator's own error, measured on this "
                 "session: a response")
    lines.append("    that emitted no reasoning should be explained by its own "
                 "visible output to within it.")

    solved = audit.solve()
    lines.append("")
    lines.append("  the chars-per-token constant that would zero this session's "
                 "residual")
    if solved is None:
        lines.append("    none in 0.5-20.0 balances these books, so the residual "
                     "here is not the constant's")
    else:
        lines.append(f"    {solved:.3f} chars/token  (shipped: {CHARS_PER_TOKEN}, "
                     f"corpus median 2.57, IQR 2.41-2.75)")
        lines.append(f"    {NOT_APPLIED}")
    return "\n".join(lines)


# ─── --explain ───────────────────────────────────────────────────────────────


def find_nodes(composition: Composition, target: str) -> list[Node]:
    """Every node whose label matches, exact before prefix before substring."""
    wanted = " ".join(target.split()).lower()
    nodes = [node for node, _ in walk(composition.nodes)]
    for match in (lambda label: label == wanted,
                  lambda label: label.startswith(wanted),
                  lambda label: wanted in label):
        found = [node for node in nodes if match(node.label.lower())]
        if found:
            return found
    return []


def explain(composition: Composition, target: str) -> tuple[int, str]:
    """The derivation of one node, in the arithmetic that produced it.

    Not a paragraph. `04-comparison.md` scores option B above A on exactly two
    rows and this flag buys the first of them — floor honesty — for a small
    fraction of B's build, but only if it answers with numbers.
    """
    found = find_nodes(composition, target)
    if not found:
        labels = sorted({node.label for node, _ in walk(composition.nodes)})
        return 1, (f"winnow: no node matching {target!r} in this readout. "
                   f"There are {len(labels)}: " + ", ".join(labels[:12])
                   + (", …" if len(labels) > 12 else ""))
    if len(found) > 1:
        return 1, (f"winnow: {target!r} matches {len(found)} nodes: "
                   + ", ".join(sorted({node.label for node in found})[:12]))

    node = found[0]
    window = composition.window
    header = [f"{node.label} — {node.kind}, {node.tokens:,} tokens"
              + (f" ({100 * node.tokens / window:.1f}% of the window)"
                 if window else "")]
    return 0, "\n".join(header + [""] + explain_body(composition, node))


def explain_body(composition: Composition, node: Node) -> list[str]:
    floor, window = composition.floor, composition.window
    if node.label == "prefix" and floor is not None:
        # Three numbers and a subtraction, which is what the operator asked of
        # the largest single block in most readouts. A paragraph here would be
        # the tool explaining itself instead of showing its working.
        return [
            f"  {floor.first_context:>12,}   context at the first priced request "
            f"in this window (record {floor.first_index}), exact from usage",
            f"− {round(floor.visible_before_first):>12,}   everything the "
            "transcript holds before that request, estimated",
            f"= {round(floor.prefix):>12,}   prefix — the system prompt and the "
            "tool definitions, which no transcript records",
        ]
    if node.label == "retained reasoning" and floor is not None:
        return [
            "  per response: output_tokens (exact) − est(text + tool_use chars), "
            "clamped at zero,",
            f"  summed over the {len(floor.output):,} responses inside the window "
            "and before the anchoring one.",
            "",
            f"  {floor.thinking_blocks:>12,}   thinking blocks, over "
            f"{floor.thinking_responses:,} responses",
            f"  {floor.per_block_median:>12,.0f}   median tokens per block in "
            "this session",
            f"  {floor.control_median:>12,.0f}   median left over on the "
            f"{floor.control_responses:,} responses with no thinking block — "
            "the control",
            f"  {round(floor.retained):>12,}   = retained reasoning",
        ]
    if node.kind == "residual":
        claimed = sum(other.tokens for other in composition.nodes
                      if other.kind != "residual")
        sign = ("this readout explains more of the window than there is; the "
                "sign is printed rather than clamped"
                if node.tokens < 0 else
                "what no category claims, which is what is left rather than "
                "what is hidden")
        return [
            f"  {window or 0:>12,}   the exact window, from usage",
            f"− {claimed:>12,}   every node above, summed",
            f"= {node.tokens:>12,}   unattributed — {sign} (§C10)",
        ]
    return [
        f"  {round(node.chars):>12,}   payload characters counted on the wire "
        "(01- §2.4; §C4's exclusions already removed)",
        f"÷ {CHARS_PER_TOKEN:>12}   chars per token, shipped fixed and never "
        "fitted (01- §2.3, band 2.4-3.0)",
        f"= {node.tokens:>12,}   apportioned by largest remainder inside the "
        "exact total, so this row and its siblings sum to it",
    ] + ([""] + [f"  its {len(node.children)} children are drawn beneath it; "
                 f"the largest is {node.children[0].label!r} at "
                 f"{node.children[0].tokens:,}"] if node.children else [])


def _figure(tokens: int, kind: str) -> dict:
    return {"tokens": tokens, "kind": kind}


def audit_dict(composition: Composition) -> dict:
    """`--audit --json`: the reconciliation and the constant, machine-readable.

    The constant carries `applied: false` as a field rather than only as prose,
    because the sweep that measures this tool reads this document and a reader
    that only sees a number would be entitled to use it (§C10).
    """
    audit, floor, window = composition.audit, composition.floor, composition.window
    if audit is None or floor is None or not window:
        return {"anchored": False, "note": NO_ANCHOR}
    solved = audit.solve()
    return {
        "anchored": True,
        "chars_per_token": CHARS_PER_TOKEN,
        "reconciliation": [
            {"label": label, "tokens": tokens, "kind": kind,
             "share": round(tokens / window, 6)}
            for label, tokens, kind in audit_rows(composition)
        ],
        "prefix": {
            "first_request_context": _figure(floor.first_context, "exact"),
            "visible_before": _figure(round(floor.visible_before_first),
                                      "estimated"),
            "prefix": _figure(round(floor.prefix), "derived"),
            "claimed": floor.claims_prefix,
        },
        "retained_reasoning": {
            "responses": floor.thinking_responses + floor.control_responses,
            "thinking_blocks": floor.thinking_blocks,
            "per_block_median": _figure(round(floor.per_block_median), "derived"),
            "control_responses": floor.control_responses,
            "control_median": _figure(round(floor.control_median), "derived"),
            "retained": _figure(round(floor.retained), "derived"),
        },
        "solved_constant": {
            "chars_per_token": None if solved is None else round(solved, 4),
            "applied": False,
            "why_not": NOT_APPLIED,
        },
    }


def to_dict(composition: Composition, window_argument: int | None,
            audit: bool = False) -> dict:
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
    document = {
        "session": composition.path.stem,
        "path": str(composition.path),
        "records": composition.records,
        "requests": composition.requests,
        "requests_in_window": composition.requests_in_window,
        "model": composition.model,
        "chars_per_token": CHARS_PER_TOKEN,
        "depth": composition.depth,
        "by_path": composition.by_path,
        # 01- §5's headline, always computed and never transcribed, whichever
        # keying the tree above is drawn in: it is a fact about the session.
        "pooled_by_path": {
            "tools": sorted(PATH_TOOLS),
            "paths": int(composition.pooled.get("paths", 0)),
            "repeated_paths": int(composition.pooled.get("repeated_paths", 0)),
            "tokens": _figure(round(composition.pooled.get("tokens", 0.0)),
                              "estimated"),
            "repeated": {
                "tokens": round(composition.pooled.get("repeated_tokens", 0.0)),
                "percent": round(composition.pooled.get("repeated_percent", 0.0), 4),
                "kind": "estimated",
            },
        },
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
    if audit:
        document["audit"] = audit_dict(composition)
    return document


# ─── the command ─────────────────────────────────────────────────────────────


def context_command(session: str, *, as_json: bool = False,
                    window: int | None = None, depth: int = 3,
                    by_path: bool = False, audit: bool = False,
                    explain_node: str | None = None) -> tuple[int, str]:
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

    if depth < 1:
        return 1, f"winnow: --depth must be at least 1, got {depth}"

    records = [record for _, record, _ in load_messages(path)]
    composition = compose(path, records, depth=depth, by_path=by_path)
    refused = 0 if composition.window is not None else 3

    if explain_node is not None:
        code, text = explain(composition, explain_node)
        return (code or refused), text
    if as_json:
        return refused, json.dumps(to_dict(composition, window, audit), indent=2)
    readout = render(composition, window)
    if audit:
        readout += "\n" + render_audit(composition)
    return refused, readout
