"""Rendering for `winnow inspect` — the readout and its `--json` twin.

Separate from `inspect.py` because the analysis has to be usable without a
terminal: the corpus sweep that checks SPEC §9's reproduction criterion consumes
`Report` objects directly, and a formatter that only existed inside the command
would have to be reimplemented there.
"""

from __future__ import annotations

import json
from pathlib import Path

from .inspect import (
    CONTENT_CLASSES,
    RULE_ORDER,
    RULE_TIER,
    Report,
    inspect_session,
)

# What each rule is, in the fewest words that still let an operator argue with
# the rule rather than with the tool (SPEC §4's pointer rationale, applied to
# the readout).
RULE_LABELS = {
    "C1": "locator (Glob/LS/Grep -l)",
    "C2": "exact duplicate call",
    "C3": "passing verification",
    "B1": "superseded read",
    "B2": "Bash inspection",
    "A1": "read then written",
}


def _human(n: int) -> str:
    for unit, scale in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= scale:
            return f"{n / scale:.1f} {unit}"
    return f"{n} B"


def resolve_session(argument: str) -> Path:
    """A session ID, a path, or a prefix long enough to be unambiguous.

    Deliberately not `legacy.session.resolve_session`, for two reasons: that one
    reads every transcript on disk to count lines before it can answer (1.1 GB
    on this install, for a lookup), and it returns the first prefix match rather
    than refusing an ambiguous one, which is the opposite of what SPEC §8 asks
    for.

    Raises LookupError, whose message is the refusal. Nothing here exits.
    """
    from .legacy.session import get_projects_dir

    candidate = Path(argument).expanduser()
    if candidate.suffix == ".jsonl" and candidate.exists():
        return candidate

    projects = get_projects_dir()
    if not projects.exists():
        raise LookupError(f"no projects directory at {projects}")

    exact: list[Path] = []
    prefixed: list[Path] = []
    for found in projects.glob("*/*.jsonl"):
        if found.name.startswith(".") or found.name.endswith(".bak"):
            continue
        if found.stem == argument:
            exact.append(found)
        elif found.stem.startswith(argument):
            prefixed.append(found)

    if len(exact) == 1:
        return exact[0]
    matches = exact or prefixed
    if not matches:
        raise LookupError(f"no session matches {argument!r}")
    if len(matches) > 1:
        names = ", ".join(sorted(m.stem for m in matches)[:4])
        raise LookupError(
            f"{argument!r} matches {len(matches)} sessions ({names}…); "
            "use a longer prefix"
        )
    return matches[0]


def to_dict(report: Report, tier: str) -> dict:
    """The `--json` shape. Every share is a percentage of message content."""
    total = report.message_content_bytes
    share = (lambda n: round(n / total * 100, 4)) if total else (lambda n: 0.0)
    return {
        "session_id": report.session_id,
        "path": str(report.path),
        "records": {
            "total": report.records,
            "by_type": report.record_types,
            "unrecognised": report.unrecognised_records,
            "parse_errors": report.parse_errors,
        },
        "message_content_bytes": total,
        "content_bytes": {c: report.content_bytes.get(c, 0) for c in CONTENT_CLASSES},
        "content_share": {c: share(report.content_bytes.get(c, 0)) for c in CONTENT_CLASSES},
        "tool_calls": report.tool_calls,
        "unanswered_tool_uses": report.unanswered_tool_uses,
        "tool_result_bytes_by_tool": dict(
            sorted(report.tool_result_bytes_by_tool.items(), key=lambda kv: -kv[1])
        ),
        "rules": {
            rule: {
                "tier": RULE_TIER[rule],
                "hits": report.rule_hits.get(rule, 0),
                "bytes": report.rule_bytes.get(rule, 0),
                "share": share(report.rule_bytes.get(rule, 0)),
            }
            for rule in RULE_ORDER
        },
        "guards": report.guard_blocked,
        "tiers": {
            t: {"bytes": report.tier_bytes(t), "share": round(report.tier_share(t), 4)}
            for t in ("C", "CB", "CBA")
        },
        "compact_boundaries": {
            "count": len(report.compact_boundaries),
            "lines": report.compact_boundaries,
        },
        "usage": {
            "turns": report.usage.turns,
            "input_tokens": report.usage.input_tokens,
            "output_tokens": report.usage.output_tokens,
            "cache_read_input_tokens": report.usage.cache_read,
            "cache_creation_input_tokens": report.usage.cache_creation,
            "ephemeral_1h_input_tokens": report.usage.ephemeral_1h,
            "ephemeral_5m_input_tokens": report.usage.ephemeral_5m,
            "write_class": report.usage.write_class,
        },
        "arithmetic": {
            "tier": tier,
            "cut_line": report.cut_line,
            "removed_bytes": report.tier_bytes(tier),
            "suffix_bytes": report.suffix_bytes,
            "suffix_over_removed": (
                round(report.suffix_bytes / report.tier_bytes(tier), 3)
                if report.tier_bytes(tier)
                else None
            ),
            "break_even_turns": (
                round(report.break_even_turns(tier), 1)
                if report.break_even_turns(tier) is not None
                else None
            ),
        },
    }


def render(report: Report, tier: str) -> str:
    """The human readout. Useful whether or not anything is ever stripped."""
    total = report.message_content_bytes
    out: list[str] = []
    add = out.append

    add(f"session {report.session_id}")
    add(f"  {report.path}")
    add("")
    add(f"records          {report.records:>10,}   "
        f"unrecognised {report.unrecognised_records:,}   "
        f"unparseable {report.parse_errors:,}")
    types = sorted(report.record_types.items(), key=lambda kv: -kv[1])
    add("  " + "  ".join(f"{name} {count:,}" for name, count in types[:8]))
    add("")

    add(f"message content  {_human(total):>10}")
    for cls in CONTENT_CLASSES:
        size = report.content_bytes.get(cls, 0)
        pct = (size / total * 100) if total else 0.0
        add(f"  {cls:<16} {_human(size):>10}   {pct:5.1f}%")
    add("")

    if report.tool_result_bytes_by_tool:
        add(f"tool_result by tool ({report.tool_calls:,} calls, "
            f"{report.unanswered_tool_uses} unanswered)")
        ranked = sorted(report.tool_result_bytes_by_tool.items(), key=lambda kv: -kv[1])
        for name, size in ranked[:8]:
            pct = (size / total * 100) if total else 0.0
            add(f"  {name:<16} {_human(size):>10}   {pct:5.1f}%")
        add("")

    add("strippable by rule")
    for rule in RULE_ORDER:
        size = report.rule_bytes.get(rule, 0)
        pct = (size / total * 100) if total else 0.0
        marker = "*" if rule in ("A1",) else " "
        add(f"  {rule}{marker} {RULE_LABELS[rule]:<28} {_human(size):>10}   "
            f"{pct:5.2f}%   {report.rule_hits.get(rule, 0):,} results")
    add("  * tier A is opt-in and never a default (SPEC §4)")
    add("")

    add("by tier")
    for name in ("C", "CB", "CBA"):
        flag = " ← current" if name == tier else ""
        add(f"  {name:<4} {_human(report.tier_bytes(name)):>10}   "
            f"{report.tier_share(name):5.2f}%{flag}")
    add("")

    refused = "  ".join(
        f"{name} {count:,}" for name, count in report.guard_blocked.items() if count
    )
    # "none" is a result, not an absence: a session where no guard fired and no
    # rule fired is a different finding from one where the guards took everything.
    add(f"guards refused   {refused or 'none'}")
    add("")

    usage = report.usage
    if usage.turns:
        add(f"cache economics ({usage.turns:,} assistant turns, "
            f"write class {usage.write_class})")
        add(f"  cache_read_input_tokens      {usage.cache_read:>14,}")
        add(f"  cache_creation_input_tokens  {usage.cache_creation:>14,}")
        add(f"    ephemeral_1h               {usage.ephemeral_1h:>14,}")
        add(f"    ephemeral_5m               {usage.ephemeral_5m:>14,}")
        add(f"  input_tokens                 {usage.input_tokens:>14,}")
        add(f"  output_tokens                {usage.output_tokens:>14,}")
    else:
        add("cache economics  no usage on any assistant record")
    add("")

    boundaries = report.compact_boundaries
    add(f"compact boundaries  {len(boundaries)}"
        + (f" at lines {', '.join(str(b) for b in boundaries[:6])}" if boundaries else ""))
    add("")

    removed = report.tier_bytes(tier)
    if not removed:
        add(f"arithmetic       nothing fires at tier {tier}; no cut, no break-even")
    else:
        ratio = report.suffix_bytes / removed
        turns = report.break_even_turns(tier)
        add(f"arithmetic       tier {tier}, cut at line {report.cut_line}")
        add(f"  D removed      {_human(removed):>10}")
        add(f"  S suffix       {_human(report.suffix_bytes):>10}")
        add(f"  S/D            {ratio:>10.1f}")
        add(f"  T* = 19·(S/D) − 20 = {turns:,.0f} further turns to pay for itself")
        add(f"  ({usage.turns:,} assistant turns in this session so far)")
        add("  S/D is a ratio of message-content bytes; SPEC §6's bytes÷4 token")
        add("  estimate cancels, but bytes-per-token differing between log and")
        add("  prose does not. See inspect.Report.break_even_turns.")
    return "\n".join(out)


def inspect_command(
    session: str,
    tier: str,
    keep_last: int,
    min_bytes: int,
    as_json: bool,
) -> tuple[int, str]:
    """`(exit code, output)`. Exit codes follow SPEC §8: 1 usage, 2 nothing to do."""
    try:
        path = resolve_session(session)
    except LookupError as exc:
        return 1, f"winnow: {exc}"
    report = inspect_session(path, keep_last=keep_last, min_bytes=min_bytes)
    payload = json.dumps(to_dict(report, tier), indent=2) if as_json else render(report, tier)
    # Exit 2 is "nothing to do — no result met a rule". It is not an error and
    # the readout is still printed: SPEC §8 makes inspect useful whether or not
    # anything is ever stripped.
    return (2 if not report.tier_bytes(tier) else 0), payload
