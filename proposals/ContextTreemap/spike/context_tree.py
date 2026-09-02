#!/usr/bin/env python3
"""DISPOSABLE SPIKE — not the tool, not on the CLI, delete when 06- is read.

This exists to answer one question that no amount of further measurement answers:
does a TreeSize-style picture of a context tell the operator anything they cannot
already see? It renders `05-recommendation.md`'s chosen hierarchy (H1, by
provenance, with H3 as the second level under `tool traffic`) over a finished
transcript, biggest-first, nested, with every figure carrying its derivation.

It is deliberately the smallest thing that can be looked at:

  * ended sessions only — no watch, no poll, no interactivity, no colour
  * no packaging, no CLI framework, no tests beyond `--audit`'s own arithmetic
  * one file, no state, no writes of any kind (§C1)

What it does take seriously, because the whole point is whether the picture reads
honestly: §C2 (every number carries a provenance kind), §C3 (the total is exact
and the parts are apportioned inside it), §C4 (the closed exclusion list), §C5
(bytes are never an area), §C6 (reset at the compaction boundary), §C8 (dedupe on
message.id, tolerant read), §C9 (say when what was read is not what was sent),
§C11 (a sub-agent's own budget is never added to the parent's).

Anything the transcript cannot see is drawn as an `unknown` block with no number,
never omitted and never folded into a neighbour.

usage:
    context_tree.py <session-id | prefix | path> [--depth N] [--json] [--audit]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The spike is run from a checkout, not an install: `winnow` is only importable
# from a venv that has it editable. Putting src/ on the path makes it work under
# a bare python3 too. This is friction, not design — see 06-spike-findings.md.
_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

from winnow.legacy.session import load_messages  # noqa: E402  (list[(idx, dict, bytes)])
from winnow.report import resolve_session  # noqa: E402
from winnow.rules import bash_head  # noqa: E402

CPT = 2.6  # chars per token, 01- §2.3; four methods put it in 2.4–3.0
BAR_COLUMNS = 22
ROLLUP_SHARE = 0.004  # nodes under 0.4% of the window collapse into "smaller nodes"
KEEP_MIN, KEEP_MAX = 3, 8  # ...but always between three and eight rows per level

# §C4, the closed exclusion list, as a set of record types that contribute zero.
# `system` is here because 01- §1.1 puts it at "mostly no" and 98 records in
# 34,467; counting it would be a guess dressed as a measurement.
BOOKKEEPING = {
    "last-prompt", "ai-title", "mode", "bridge-session", "queue-operation",
    "agent-setting", "permission-mode", "atis-latch", "file-history-delta",
    "file-history-snapshot", "frame-link", "agent-name", "cost-state",
    "artifact-autoreact-ledger", "artifact-comment-monitor", "system",
}

# How each provenance kind was arrived at. §C2 says there are exactly three plus
# the reserved `residual`; `unknown` is this spike's fourth and it carries no
# number, which is the only reason it is allowed to exist beside them.
DERIVATION = {
    "exact": "read from usage.{input,cache_creation,cache_read}_tokens on the anchoring request",
    "derived": "an exact number minus an estimate — see the per-node note",
    "est": f"payload characters / {CPT} (01- §2.3; the band is 2.4-3.0)",
    "residual": "window - everything above it; what no kind accounts for",
    "unknown": "in the window, in no record type, not separable — deliberately unsized",
}


@dataclass
class Node:
    label: str
    tokens: float
    kind: str
    note: str = ""
    children: list["Node"] = field(default_factory=list)

    def sorted_children(self) -> list["Node"]:
        return sorted(self.children, key=lambda n: -n.tokens)


# ---------------------------------------------------------------- measurement


def est(chars: float) -> float:
    return chars / CPT


def payload_chars(block: dict) -> tuple[float, str]:
    """Characters this content block puts on the wire, and a note if it is odd.

    01- §2.4's table, plus §C5 for images and §C9 for spills. Returns characters
    rather than tokens so that images — which are priced by area, not by text —
    can hand back their token count already multiplied by CPT.
    """
    kind = block.get("type")
    if kind == "text":
        return len(block.get("text") or ""), ""
    if kind == "tool_use":
        return len(json.dumps(block.get("input"), ensure_ascii=False)) + len(block.get("name") or ""), ""
    if kind == "thinking":
        # The text is stripped on disk and the signature is not context (§1.3).
        # What was retained in the window is priced separately, from output_tokens.
        return 0, ""
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
            return total, "; ".join(notes)
    return 0, ""


def spill_note(text: str) -> str:
    """§C9 — the block on the wire is a pointer; say how big the thing pointed at was."""
    if "<persisted-output>" not in text:
        return ""
    return "pointer: model saw the preview, full output is in a tool-results/ sidecar"


IMAGES = {"sized": 0, "unsized": 0, "base64_chars": 0, "tokens": 0.0}


def image_chars(block: dict) -> tuple[float, str]:
    """§C5 — width x height / 750, from the header. Never len(base64)/4 (14x wrong)."""
    source = block.get("source") or {}
    data = source.get("data") or ""
    IMAGES["base64_chars"] += len(data)
    head = b""
    if data:
        try:
            head = base64.b64decode(data[:6000] + "==", validate=False)
        except Exception:
            head = b""
    dims = (png_dimensions(head) or jpeg_dimensions(head)) if head else None
    if not dims:
        IMAGES["unsized"] += 1
        return 0, "image whose header did not parse: sized ZERO and labelled, never len(base64)/4"
    width, height = dims
    tokens = width * height / 750
    IMAGES["sized"] += 1
    IMAGES["tokens"] += tokens
    return tokens * CPT, "image priced at w*h/750 from its decoded header, not its base64 length"


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
    """The payload strings only — the CLI renders attachments into prose (§C4)."""
    def strings(obj):
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for value in obj.values():
                yield from strings(value)
        elif isinstance(obj, list):
            for value in obj:
                yield from strings(value)
    return sum(len(s) for s in strings(attachment))


# ------------------------------------------------------------------- the walk


def responses(records: list[dict]) -> list[dict]:
    """One entry per API response, keyed on message.id (§C8).

    A response reaches disk as several lines, one per content block, each
    repeating the same usage object. Summing per line inflates by 1.7-2.4x.
    """
    grouped: dict[str, dict] = {}
    for index, record in enumerate(records):
        if record.get("type") != "assistant":
            continue
        message = record.get("message") or {}
        message_id, usage = message.get("id"), message.get("usage") or {}
        if not message_id or not usage:
            continue
        entry = grouped.setdefault(message_id, dict(
            index=index,
            output_tokens=usage.get("output_tokens") or 0,
            context=((usage.get("input_tokens") or 0)
                     + (usage.get("cache_creation_input_tokens") or 0)
                     + (usage.get("cache_read_input_tokens") or 0)),
            model=message.get("model"),
            blocks={},
        ))
        for block in message.get("content") or []:
            if isinstance(block, dict):
                entry["blocks"][json.dumps(block, sort_keys=True, ensure_ascii=False)] = block
    # A `<synthetic>` record — an interrupt or an API error the CLI wrote in the
    # model's place — carries a usage object of all zeros. It is not a priced
    # request, and if it lands last it would anchor the whole readout at zero.
    return sorted((e for e in grouped.values() if e["context"] > 0),
                  key=lambda e: e["index"])


def emitted_chars(entry: dict) -> tuple[float, int]:
    """Visible output characters and thinking-block count for one response."""
    chars, thinking = 0.0, 0
    for block in entry["blocks"].values():
        if block.get("type") == "thinking":
            thinking += 1
        chars += payload_chars(block)[0]
    return chars, thinking


def subagent_index(session_path: Path) -> dict[str, dict]:
    """toolUseId -> {type, description, own window} for every sub-agent sidecar (§C11)."""
    directory = session_path.with_suffix("") / "subagents"
    if not directory.is_dir():
        return {}
    index = {}
    for meta_path in sorted(directory.glob("agent-*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            continue
        transcript = meta_path.with_name(meta_path.name.replace(".meta.json", ".jsonl"))
        window = 0
        if transcript.exists():
            try:
                own = responses([r for _, r, _ in load_messages(transcript)])
                window = own[-1]["context"] if own else 0
            except Exception:
                window = 0
        index[meta.get("toolUseId")] = dict(
            agent_type=meta.get("agentType") or "?",
            description=meta.get("description") or "",
            window=window,
        )
    return index


def artefact_key(tool: str, tool_input: dict) -> str | None:
    """H3, in its right place: the second level under a tool (05-, 'what the tree is')."""
    if not isinstance(tool_input, dict):
        return None
    if tool == "Bash":
        head = bash_head(tool_input.get("command") or "")
        return f"$ {head}" if head else None
    if tool in ("Read", "Edit", "Write", "NotebookEdit"):
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        return redact(path) if path else None
    if tool in ("Grep", "Glob"):
        return tool_input.get("pattern")
    if tool == "Skill":
        return tool_input.get("skill")
    if tool == "Agent":
        return tool_input.get("subagent_type") or tool_input.get("description")
    if tool.startswith("mcp__"):
        parts = tool.split("__")
        return parts[1] if len(parts) > 1 else None
    return None


HOME_PREFIX = re.compile(r"^(/Users|/home)/[^/]+")


def redact(path: str) -> str:
    """Collapse any home directory to `~`.

    Not only this process's own: a transcript written on the laptop and read in
    the container carries the other one, and the leaf is the actionable part.
    """
    if not isinstance(path, str):
        return path
    return HOME_PREFIX.sub("~", path.replace(os.path.expanduser("~"), "~"))


# --------------------------------------------------------------- composition


def compose(session_path: Path, records: list[dict]) -> dict:
    """Everything the readout needs, as plain numbers. No printing here."""
    priced = responses(records)
    if not priced:
        raise SystemExit("no assistant record carries `usage`: there is no exact anchor, "
                         "and §C3's architecture does not apply to this session")

    boundaries = [(i, r.get("compactMetadata") or {})
                  for i, r in enumerate(records) if r.get("subtype") == "compact_boundary"]
    # §C6 — the window was emptied here; everything before it is not in it.
    window_start = boundaries[-1][0] if boundaries else 0
    dropped = sum(m.get("cumulativeDroppedTokens") or 0 for _, m in boundaries[-1:])

    anchor = priced[-1]
    window = anchor["context"]
    in_window = [e for e in priced if e["index"] >= window_start]

    # Prefix: the first request of the session is priced, and everything else in
    # it is on disk. The system prompt and tool definitions survive compaction,
    # so this subtraction still describes the current window (§3.1).
    first = priced[0]
    visible_before_first = sum(record_chars(r)[0] for r in records[:first["index"]])
    prefix = first["context"] - est(visible_before_first)

    # Retained reasoning: one exact number minus two small estimates, per
    # response, for every response still inside the window (02-, the correction).
    retained, thinking_blocks, per_block = 0.0, 0, []
    for entry in in_window[:-1]:
        if entry["output_tokens"] <= 0:
            continue
        chars, thinking = emitted_chars(entry)
        residual = entry["output_tokens"] - est(chars)
        retained += max(0.0, residual)
        thinking_blocks += thinking
        if thinking:
            per_block.append(residual / thinking)

    # The window can shrink between two requests with no compaction boundary:
    # on session 939a04dc a `deferred_tools_delta` took 78,167 tokens out of it
    # mid-session by moving tool schemas behind ToolSearch. Nothing in the file
    # says what left, so the honest move is to name the drop, not model it.
    shed = []
    for earlier, later in zip(in_window, in_window[1:]):
        if later["context"] < earlier["context"] - 2000:
            shed.append(dict(at=later["index"],
                             lost=earlier["context"] - later["context"],
                             cause=shed_cause(records, earlier["index"], later["index"])))

    tree = classify(records, window_start, anchor["index"], session_path)
    visible = sum(n.tokens for n in tree)

    return dict(
        path=session_path,
        records=len(records),
        requests=len(priced),
        requests_in_window=len(in_window),
        model=anchor["model"],
        window=window,
        boundaries=[m for _, m in boundaries],
        dropped=dropped,
        prefix=prefix,
        first_context=first["context"],
        visible_before_first=est(visible_before_first),
        retained=retained,
        thinking_blocks=thinking_blocks,
        per_block=sorted(per_block)[len(per_block) // 2] if per_block else 0.0,
        visible=visible,
        visible_nodes=tree,
        shed=shed,
        unattributed=window - prefix - retained - visible,
        notes=NOTES,
    )


def shed_cause(records: list[dict], start: int, stop: int) -> str:
    """The best available guess at what took material out of the window, or nothing."""
    seen = []
    for record in records[start:stop + 1]:
        if record.get("type") == "attachment":
            atype = (record.get("attachment") or {}).get("type")
            if atype and atype.endswith("_delta") and atype not in seen:
                seen.append(atype)
        if (record.get("message") or {}).get("model") == "<synthetic>":
            if "<synthetic> response (interrupt or API error)" not in seen:
                seen.append("<synthetic> response (interrupt or API error)")
    return ", ".join(seen) if seen else "nothing in the file names a cause"


NOTES: list[str] = []


def record_chars(record: dict) -> tuple[float, str]:
    """Payload characters one transcript line contributes, and any §C9 note."""
    kind = record.get("type")
    if kind in BOOKKEEPING:
        return 0, ""
    if kind == "attachment":
        return attachment_chars(record.get("attachment") or {}), ""
    message = record.get("message")
    if not isinstance(message, dict):
        return 0, ""
    content = message.get("content")
    if isinstance(content, str):
        return len(content), ""
    if not isinstance(content, list):
        return 0, ""
    total, notes = 0.0, []
    for block in content:
        if isinstance(block, dict):
            chars, note = payload_chars(block)
            total += chars
            if note:
                notes.append(note)
    return total, "; ".join(notes)


def classify(records: list[dict], start: int, stop: int, session_path: Path) -> list[Node]:
    """H1's top level over the records still in the window, with H3 beneath tools."""
    NOTES.clear()
    # compose() has already walked some records to price the prefix and the
    # retained reasoning; only the in-window walk below should be counted here.
    IMAGES.update(sized=0, unsized=0, base64_chars=0, tokens=0.0)
    agents = subagent_index(session_path)

    # tool_use id -> (tool name, artefact key), so a result can be attributed to
    # its caller. Built over the whole file: a result inside the window can be
    # answering a call that is itself inside it, and the pairing is by id anyway.
    callers: dict[str, tuple[str, str | None]] = {}
    for record in records:
        if record.get("type") != "assistant":
            continue
        for block in (record.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name") or "?"
                callers[block.get("id")] = (name, artefact_key(name, block.get("input") or {}))

    buckets: dict[tuple[str, ...], float] = {}
    labels: dict[tuple[str, ...], str] = {}
    counts: dict[tuple[str, ...], int] = {}
    spent = [0, 0]  # sub-agent window tokens, sub-agent count — reported, never summed in

    def add(path: tuple[str, ...], chars: float, note: str = "") -> None:
        buckets[path] = buckets.get(path, 0.0) + est(chars)
        counts[path] = counts.get(path, 0) + 1
        # A block can raise several notes at once; dedupe the reasons, not the
        # joined strings, or a session with images prints one line per image.
        for reason in (note.split("; ") if note else []):
            if reason and reason not in NOTES:
                NOTES.append(reason)

    for record in records[start:stop]:
        kind = record.get("type")
        if kind in BOOKKEEPING:
            continue
        if kind == "attachment":
            attachment = record.get("attachment") or {}
            atype = attachment.get("type") or "?"
            leaf = redact(attachment.get("path") or "") if atype == "nested_memory" else ""
            path = ("standing configuration", atype) + ((leaf,) if leaf else ())
            add(path, attachment_chars(attachment))
            continue
        if record.get("isCompactSummary"):
            add(("compaction summary",), record_chars(record)[0])
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            add(("conversation", "user turns"), len(content))
            continue
        if not isinstance(content, list):
            continue
        # A `user` text block is not necessarily a user turn. When the record
        # carries `sourceToolUseID` it is a tool's return delivered outside the
        # tool_result envelope — a Skill body arrives this way, and on session
        # c3566197 that was 53.5% of the window filed under `conversation`.
        # H1 asks who put it there, and the record type does not say.
        source_tool = record.get("sourceToolUseID")
        if source_tool and source_tool in callers:
            tool, artefact = callers[source_tool]
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    add(("tool traffic", f"{tool} results") + ((artefact,) if artefact else ()),
                        len(block.get("text") or ""),
                        "a `user` text block carrying a tool's return outside a tool_result "
                        "envelope, paired by sourceToolUseID (a Skill body arrives this way)")
            continue
        if record.get("isMeta"):
            add(("conversation", "harness notices"), record_chars(record)[0])
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            chars, note = payload_chars(block)
            btype = block.get("type")
            if btype == "tool_result":
                tool, artefact = callers.get(block.get("tool_use_id"), ("(unpaired)", None))
                if tool == "Agent":
                    meta = agents.get(block.get("tool_use_id"))
                    leaf = agent_label(block.get("tool_use_id"), meta)
                    spent[0] += (meta or {}).get("window", 0)
                    spent[1] += 1
                    add(("tool traffic", "Agent returns", leaf), chars, note)
                else:
                    path = ("tool traffic", f"{tool} results") + ((artefact,) if artefact else ())
                    add(path, chars, note)
            elif btype == "tool_use":
                add(("tool traffic", "tool_use inputs", block.get("name") or "?"), chars, note)
            elif btype == "image":
                add(("conversation", "images"), chars, note)
            elif btype == "text" and kind == "assistant":
                add(("conversation", "assistant text"), chars, note)
            else:
                add(("conversation", "user turns"), chars, note)

    tree = build(buckets, counts, labels)
    if spent[1]:
        for root in tree:
            for child in root.children:
                if child.label == "Agent returns":
                    child.note = (f"{spent[1]} sub-agents spent {spent[0]:,} tokens of their own "
                                  f"windows to return {round(child.tokens):,} into this one "
                                  f"(§C11: their budgets are never added to it)")
    return tree


def agent_label(tool_use_id: str | None, meta: dict | None) -> str:
    """§C11 — the return is the node; the sub-agent's own window is a label, never a summand."""
    if not meta:
        return f"{(tool_use_id or '?')[-8:]} (no sidecar found)"
    own = f"own window {meta['window']:,}" if meta["window"] else "own window unknown"
    return f"{meta['agent_type']}: {meta['description'][:32]}  [{own}, not added]"


def build(buckets: dict, counts: dict, labels: dict) -> list[Node]:
    """Turn flat (path -> tokens) into the nested tree, rolling up the tail."""
    roots: dict[str, Node] = {}
    for path, tokens in buckets.items():
        node = None
        for depth, part in enumerate(path):
            here = roots if node is None else {c.label: c for c in node.children}
            if part not in here:
                fresh = Node(label=part, tokens=0.0, kind="est")
                if node is None:
                    roots[part] = fresh
                else:
                    node.children.append(fresh)
                here[part] = fresh
            node = here[part]
            node.tokens += tokens
            if depth == len(path) - 1:
                # The repeat count is the actionable half of H3 — 01- §5 measured
                # 34% of Read/Edit output on this machine coming from paths
                # touched more than once — so it goes on the label, not a note.
                repeats = counts.get(path, 1)
                if repeats > 1 and depth >= 2:
                    node.label = f"{node.label}  x{repeats}"
    return list(roots.values())


def rollup(children: list[Node], window: float) -> list[Node]:
    """Biggest-first, with everything under ROLLUP_SHARE named as a count, not dropped.

    `unknown` nodes are never rolled up: they carry no tokens by construction, so
    a size threshold would silently delete exactly the blocks this spike exists
    to keep visible.
    """
    ordered = sorted(children, key=lambda n: -n.tokens)
    unsized = [n for n in ordered if n.kind == "unknown"]
    sized = [n for n in ordered if n.kind != "unknown"]
    big = [n for n in sized if n.tokens >= ROLLUP_SHARE * window]
    # Always show a few rows even when every child is small: rolling 48 sub-agent
    # returns into one line deletes exactly the comparison §C11 is for.
    big = (big if len(big) >= KEEP_MIN else sized[:KEEP_MIN])[:KEEP_MAX]
    small = sized[len(big):]
    if len(small) > 1:
        big.append(Node(label=f"{len(small)} more nodes, each smaller", kind="est",
                        tokens=sum(n.tokens for n in small)))
    else:
        big.extend(small)
    return sorted(big, key=lambda n: -n.tokens) + unsized


# ------------------------------------------------------------------ printing

LABEL_COLUMNS = 44


def bar(share: float) -> str:
    filled = share * BAR_COLUMNS
    whole = int(filled)
    if whole:
        return "█" * whole
    return "▏" if share > 0 else " "


def fit(label: str, indent: int) -> str:
    """Indent, then keep the informative end of a long path rather than the head."""
    room = LABEL_COLUMNS - 2 * indent
    if len(label) > room:
        label = "…" + label[-(room - 1):]
    return "  " * indent + label


def print_node(node: Node, window: float, depth: int, max_depth: int) -> None:
    share = node.tokens / window if window else 0
    size = "  unsized" if node.kind == "unknown" else f"{round(node.tokens):>9,}"
    pct = "     —" if node.kind == "unknown" else f"{100 * share:5.1f}%"
    print(f"  {bar(share):<{BAR_COLUMNS}}  {fit(node.label, depth):<{LABEL_COLUMNS}}"
          f"{size}  {pct}  {node.kind}")
    if node.note:
        # Not fitted: a derivation that has been truncated is not a derivation.
        print(f"  {'':<{BAR_COLUMNS}}  {'  ' * (depth + 1)}· {node.note}")
    if depth >= max_depth:
        if node.children:
            print(f"  {'':<{BAR_COLUMNS}}  "
                  f"{fit(f'… {len(node.children)} nodes below --depth {max_depth}', depth + 1)}")
        return
    for child in rollup(node.children, window):
        print_node(child, window, depth + 1, max_depth)


def render(c: dict, max_depth: int) -> None:
    window = c["window"]
    sid = c["path"].stem[:8]
    compaction = (f"{len(c['boundaries'])} compaction boundaries" if c["boundaries"]
                  else "no compaction")
    head = BAR_COLUMNS + LABEL_COLUMNS + 4
    print(f"session {sid}  ·  {c['records']:,} records  ·  {c['requests']} requests "
          f"({c['requests_in_window']} in the window)  ·  {c['model']}  ·  {compaction}")
    print(f"{'window at the last request':<{head}}{window:>9,}  100.0%  exact")
    if c["boundaries"]:
        last = c["boundaries"][-1]
        print(f"{'dropped by compaction (cumulative)':<{head}}"
              f"{last.get('cumulativeDroppedTokens') or 0:>9,}      —  exact")
        print(f"{'  last boundary: ' + str(last.get('trigger')) + ' compaction, pre/post':<{head}}"
              f"{last.get('preTokens') or 0:,} / {last.get('postTokens') or 0:,}")
    for drop in c["shed"]:
        print(f"{'shed with no compaction boundary':<{head}}{drop['lost']:>9,}      —  exact")
        print(f"{'  at record ' + str(drop['at']) + '; what left is not in the file':<{head}}"
              f"cause: {drop['cause']}")
    print()

    top = [
        Node("prefix (not in the file)", c["prefix"], "derived",
             note=f"= ctx(req 1) {c['first_context']:,.0f} - est(visible before it) "
                  f"{c['visible_before_first']:,.0f}",
             children=[
                 Node("system prompt", 0, "unknown", note="carried by no record type"),
                 Node("tool definitions", 0, "unknown", note="names only, never schemas"),
             ]),
        Node("retained reasoning (not in the file)", c["retained"], "derived",
             note=f"= sum over {c['requests_in_window'] - 1} responses of "
                  f"(output_tokens - est(text + tool_use))",
             children=[
                 Node("thinking text", 0, "unknown",
                      note=f"stripped on disk; {c['thinking_blocks']} blocks, "
                           f"{c['per_block']:,.0f} tok/block median for this session"),
             ]),
        *c["visible_nodes"],
        Node("unattributed", c["unattributed"], "residual"),
    ]
    for node in rollup(top, window):
        print_node(node, window, 0, max_depth)

    print()
    by_kind: dict[str, float] = {}
    for node in top:
        by_kind[node.kind] = by_kind.get(node.kind, 0.0) + node.tokens
    summary = " · ".join(f"{k} {round(v):,} ({100 * v / window:.1f}%)"
                         for k, v in sorted(by_kind.items(), key=lambda kv: -kv[1]))
    print(f"exact {window:,} = {summary}")
    print("\nhow each kind was derived")
    for kind in ("exact", "derived", "est", "residual", "unknown"):
        print(f"  {kind:<9s} {DERIVATION[kind]}")
    for note in c["notes"]:
        print(f"  note      {note}")
    if IMAGES["sized"] or IMAGES["unsized"]:
        print(f"  note      {IMAGES['sized']} images priced at {round(IMAGES['tokens']):,} tokens "
              f"total; {IMAGES['unsized']} unsized. Their base64 is "
              f"{IMAGES['base64_chars'] / 1e6:.1f} MB, which /4 would have called "
              f"{round(IMAGES['base64_chars'] / 4):,} tokens (§C5)")
    print("  note      no '% of window full' is printed: nothing in a transcript states "
          "the window size (§C7)")


def audit(c: dict) -> None:
    window, prefix, retained = c["window"], c["prefix"], c["retained"]
    visible_chars = c["visible"] * CPT
    print("\naudit")
    print(f"  window (exact)                          {window:>12,}")
    print(f"  - prefix (derived)                      {round(prefix):>12,}")
    print(f"  - retained reasoning (derived)          {round(retained):>12,}")
    print(f"  - visible material (estimated)          {round(c['visible']):>12,}")
    print(f"  = unattributed (residual)               {round(c['unattributed']):>12,}"
          f"   {100 * c['unattributed'] / window:+.1f}% of the window")
    if c["shed"]:
        print(f"    of which unmodelled shedding            "
              f"{sum(d['lost'] for d in c['shed']):>12,}   material that left the window "
              f"with no record of what it was")
    remaining = window - prefix - retained
    solved = visible_chars / remaining if remaining > 0 else float("nan")
    print(f"\n  chars/token that would zero this session's residual: {solved:.2f}  "
          f"(shipped: {CPT})")
    print("  NOT APPLIED — §C10: a residual that cannot be non-zero is not evidence.")


def sweep(sample: int) -> None:
    """The spike's own self-check, over the corpus rather than over one session.

    05-recommendation.md's first two success criteria are paired against a
    same-day prototype run, so this prints the same quantities
    `scratch/thinking_price.py` prints, computed by the classifier instead of by
    the prototype's four-term subtraction.
    """
    root = Path("~/.claude/projects").expanduser()
    paths = sorted(root.glob("*/*.jsonl"))
    paths = paths[::max(1, len(paths) // sample)][:sample]
    rows = []
    for path in paths:
        try:
            records = [r for _, r, _ in load_messages(path)]
            composed = compose(path, records)
        except (SystemExit, Exception):  # noqa: B014 — a spike sweep never stops on one file
            continue
        if composed["requests_in_window"] < 5 or composed["window"] <= 0:
            continue
        rows.append(composed)

    def quantile(values, q):
        ordered = sorted(values)
        return ordered[min(len(ordered) - 1, int(len(ordered) * q))] if ordered else float("nan")

    window = [r["window"] for r in rows]
    residual = [100 * r["unattributed"] / r["window"] for r in rows]
    visible_only = [100 * (r["window"] - r["visible"]) / r["window"] for r in rows]
    prefix = [100 * r["prefix"] / r["window"] for r in rows]
    retained = [100 * r["retained"] / r["window"] for r in rows]
    shed = [r for r in rows if r["shed"]]
    compacted = [r for r in rows if r["boundaries"]]

    print(f"{len(rows)} sessions of {len(paths)} sampled ({sample} requested), "
          f">=5 requests in the window")
    print(f"  window                       median {quantile(window, .5):>9,}")
    for label, values in (("unexplained, visible only", visible_only),
                          ("unexplained, fully decomposed", residual),
                          ("prefix share", prefix),
                          ("retained reasoning share", retained)):
        print(f"  {label:<28s} p25 {quantile(values, .25):6.1f}%   "
              f"median {quantile(values, .5):6.1f}%   p75 {quantile(values, .75):6.1f}%")
    within = sum(1 for r in rows if abs(r["unattributed"]) <= 0.15 * r["window"])
    over = sum(1 for r in rows if r["unattributed"] < 0)
    print(f"  |residual| <= 15% of the window: {within}/{len(rows)}")
    print(f"  over-explained (residual < 0):   {over}/{len(rows)}")
    print(f"  compacted:                       {len(compacted)}/{len(rows)}")
    print(f"  sessions that shed context with no compaction boundary: "
          f"{len(shed)}/{len(rows)}, "
          f"median lost {quantile([sum(d['lost'] for d in r['shed']) for r in shed], .5):,} tokens")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", nargs="?")
    parser.add_argument("--sweep", type=int, metavar="N",
                        help="run over an even N-file sample of the corpus and print the "
                             "residual distribution instead of one tree")
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()

    if args.sweep:
        sweep(args.sweep)
        return
    if not args.session:
        parser.error("give a session id, or --sweep N")

    path = Path(args.session)
    if not path.exists():
        path = resolve_session(args.session)
    records = [record for _, record, _ in load_messages(path)]
    composed = compose(path, records)

    if args.json:
        def as_dict(node: Node) -> dict:
            return dict(label=node.label, tokens=round(node.tokens), kind=node.kind,
                        note=node.note, children=[as_dict(c) for c in node.sorted_children()])
        print(json.dumps(dict(
            session=path.stem, window=composed["window"], kind="exact",
            nodes=[as_dict(n) for n in composed["visible_nodes"]],
            prefix=round(composed["prefix"]), retained=round(composed["retained"]),
            unattributed=round(composed["unattributed"]),
        ), indent=2))
        return

    render(composed, args.depth)
    if args.audit:
        audit(composed)


if __name__ == "__main__":
    main()
