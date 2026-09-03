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
    """

    tokens: float = 0.0
    count: int = 0
    spilled: float = 0.0


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
            use = paths.setdefault(artefact, PathUse())
            use.tokens += estimate(payload_chars(block)[0])
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
            spilled: float = 0.0) -> None:
        leaf = leaves.setdefault(key, Leaf())
        leaf.tokens += estimate(chars)
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
            add(("compaction summary",), message_chars(message, notes))
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
            chars, note = payload_chars(block)
            add(content_key(block, record, callers, agents, delegations, by_path),
                chars, note, spilled_bytes(block))

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


# ─── the tree ────────────────────────────────────────────────────────────────


@dataclass
class Branch:
    """The nested form of `classify`'s flat map, still in unrounded tokens."""

    key: str
    tokens: float = 0.0
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
                    tokens=amount, kind="estimated", note=spill_label(branch))
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

    nodes = [Node(label=label, tokens=round(tree[label].tokens), kind="estimated")
             for label in TOP_LEVEL if label in tree and round(tree[label].tokens)]
    nodes.sort(key=lambda node: -node.tokens)
    for node in nodes:
        node.children = materialise(tree[node.label].children, node.tokens,
                                    labels, (node.label,), depth, level=2)
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
        depth=depth,
        by_path=by_path,
        pooled=pooled(paths),
    )


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
    filled = int(share * BAR_COLUMNS)
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
    if window is not None:
        lines.append("  note       no prefix node and no retained-reasoning node "
                     "yet (M3), so both sit inside `unattributed`.")
    if composition.depth < 3:
        lines.append(f"  note       drawn to --depth {composition.depth}; "
                     "--depth 3 reaches the file paths and Bash command heads.")
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


# ─── the command ─────────────────────────────────────────────────────────────


def context_command(session: str, *, as_json: bool = False,
                    window: int | None = None, depth: int = 3,
                    by_path: bool = False) -> tuple[int, str]:
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
    payload = (json.dumps(to_dict(composition, window), indent=2) if as_json
               else render(composition, window))
    return (0 if composition.window is not None else 3), payload
