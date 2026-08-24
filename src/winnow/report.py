"""Rendering for `winnow inspect` and `winnow savings` — the readouts and their
`--json` twins.

Separate from `inspect.py` and `savings.py` because the analysis has to be usable
without a terminal: the corpus sweep that checks SPEC §9's reproduction criterion
consumes `Report` objects directly, and a formatter that only existed inside the
command would have to be reimplemented there. Both readouts live here for the same
reason and so that they read alike — an operator comparing what a cut *would* be
worth against what the filter *has* been worth should not have to learn two layouts.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import savings as savings_mod
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


# ─── `winnow savings` ────────────────────────────────────────────────────────

# Said in the command's own output and not only in the docs. Other tools report bytes
# removed and call that a saving; the whole of this project's claim to be different is
# that it says which of its numbers were measured and which were modelled.
MODELLED_NOT_BILLED = (
    "This is modelled, not billed. The bytes were never sent, so no invoice line "
    "corresponds to them. D and T are measured and the prices are published; the "
    "counterfactual — that these bytes would have been cache-written once and read "
    "every turn after — is COZEMPIC.md §3.5's model, not an observation."
)


def savings_to_dict(result: savings_mod.Savings) -> dict:
    """`--json`. Same fields as the readout, in the same split."""
    bill, sessions_priced, unpriced_models = result.bill()
    total = result.dollars
    turns = result.turns
    return {
        "ledger": {
            "path": str(result.ledger.path),
            "lines": result.ledger.lines,
            "parse_errors": result.ledger.parse_errors,
            "removal_events": result.ledger.removal_events,
            "bytes_summed_over_events": result.ledger.bytes_summed,
            "legacy_lines_without_tool_use_id": result.ledger.legacy_lines,
            "lines_without_model": result.ledger.lines_without_model,
            "lines_without_cache_ttl": result.ledger.lines_without_ttl,
            "malformed_entries": result.ledger.malformed_entries,
            # removal_events + malformed_entries; every entry the file described.
            "entries_total": result.ledger.events,
        },
        "removed": {
            "unique_results": len(result.priced),
            "unique_bytes": result.unique_bytes,
            "overstatement_if_summed": (
                round(result.ledger.bytes_summed / result.ledger.unique_bytes, 2)
                if result.ledger.unique_bytes
                else None
            ),
            "priced_results": len(result.counted),
        },
        "turns_after": savings_mod.turn_distribution(turns),
        "dollars": {
            "avoided_write": round(result.write_dollars, 4),
            "avoided_reads": round(result.read_dollars, 4),
            "total": round(total, 4),
            "bill": round(bill, 4),
            "share_of_bill_pct": round(total / bill * 100, 3) if bill else None,
            "bill_sessions": sessions_priced,
            "bill_models_without_price": unpriced_models,
            "write_classes": result.write_classes,
        },
        "tokens": {
            "bytes_per_token": savings_mod.DEFAULT_BYTES_PER_TOKEN,
            "source": "SPEC §6 estimate; no per-session calibration (COZEMPIC §3.5.2)",
            "per_session": {
                sid: {
                    "turns": facts.turns,
                    "assistant_records": facts.records,
                }
                for sid, facts in sorted(result.sessions.items())
            },
        },
        "excluded": {
            reason: {"results": count, "bytes": size}
            for reason, (count, size) in sorted(result.exclusions.items())
        },
        "caveat": MODELLED_NOT_BILLED,
    }


def render_savings(result: savings_mod.Savings) -> str:
    """The human readout, laid out like `render`."""
    ledger = result.ledger
    out: list[str] = []
    add = out.append

    add("winnow savings — what the intake filter has done on this install")
    add(f"  {ledger.path}")
    add("")

    add(f"ledger           {ledger.lines:>10,} lines   "
        f"unparseable {ledger.parse_errors:,}")
    add(f"  removal events {ledger.removal_events:>10,}   "
        f"{_human(ledger.bytes_summed)} if summed")
    add(f"  unique results {len(result.priced):>10,}   "
        f"{_human(result.unique_bytes)} actually removed")
    if ledger.unique_bytes:
        # The one number that decides whether any of the rest is right. The filter is
        # stateless and re-drops the same result on every later request, so the naive
        # sum is a per-turn quantity read as a one-time one (COZEMPIC.md §3.4).
        add(f"  summing events would overstate this by "
            f"{ledger.bytes_summed / ledger.unique_bytes:.1f}×")
    if ledger.legacy_lines:
        add(f"  {ledger.legacy_lines:,} lines predate tool_use_id and were de-duped "
            "on (tool, rule, bytes)")
    if ledger.malformed_entries:
        add(f"  {ledger.malformed_entries:,} entries carried no usable size and could "
            "not be counted as removals")
    add("")

    turns = result.turns
    dist = savings_mod.turn_distribution(turns)
    if dist:
        add(f"T, turns after removal ({dist['count']:,} results joined)")
        add(f"  min {dist['min']:,}   p25 {dist['p25']:,.0f}   "
            f"median {dist['median']:,.0f}   p75 {dist['p75']:,.0f}   "
            f"max {dist['max']:,}")
        add("  one API request is one turn, however many records it left on disk")
        add("  capped at the next compact boundary: a result cannot be read back "
            "across one")
    else:
        add("T, turns after removal   nothing joined; no read term can be priced")
    add("")

    add(f"tokens           bytes ÷ {savings_mod.DEFAULT_BYTES_PER_TOKEN:.0f}, "
        "SPEC §6's estimate for every result")
    add("  no per-session calibration: the fit it used was not a measurement "
        "(COZEMPIC §3.5.2)")
    for sid, facts in sorted(result.sessions.items()):
        add(f"  {sid[:8]}  {facts.turns:>5,} requests   "
            f"{facts.records:,} assistant records")
    add("")

    bill, sessions_priced, unpriced = result.bill()
    total = result.dollars
    classes = result.write_classes
    add(f"saved ({len(result.counted):,} of {len(result.priced):,} results priced)")
    add(f"  avoided write  ${result.write_dollars:>9.2f}   "
        "(W−1)·D once, W read from what the request carried")
    for label, count in sorted(classes.items(), key=lambda kv: -kv[1]):
        add(f"                              {count:,} at {label}")
    add(f"  avoided reads  ${result.read_dollars:>9.2f}   "
        "0.1·D·T — the repeats, priced as repeats")
    add(f"  total          ${total:>9.2f}")
    add("")

    add(f"share of the bill ({sessions_priced:,} joined sessions, their own usage)")
    add(f"  bill           ${bill:>9.2f}")
    if bill:
        add(f"  saved          {total / bill * 100:>9.2f}%")
    else:
        add("  saved                  n/a   no priced usage in the joined sessions")
    if unpriced:
        add(f"  {len(unpriced)} model(s) with no published price excluded from the "
            f"bill: {', '.join(unpriced)}")
    add("")

    exclusions = result.exclusions
    add("not counted")
    if not exclusions:
        add("  nothing; every unique removal was joined and priced")
    for reason, (count, size) in sorted(exclusions.items(), key=lambda kv: -kv[1][0]):
        add(f"  {count:>4,} results  {_human(size):>10}   {reason}")
    add("")

    add(MODELLED_NOT_BILLED)
    return "\n".join(out)


def savings_command(
    ledger: str | None,
    projects: str | None,
    as_json: bool,
) -> tuple[int, str]:
    """`(exit code, output)`. Exit codes follow SPEC §8: 1 usage, 2 nothing to do."""
    path = Path(ledger).expanduser() if ledger else savings_mod.DEFAULT_LEDGER
    if not path.is_file():
        return 1, (f"winnow: no ledger at {path}. The filter writes one only when "
                   "started with --ledger; there is nothing to price without it.")
    projects_dir = (
        Path(projects).expanduser() if projects else savings_mod.DEFAULT_PROJECTS
    )
    result = savings_mod.compute(path, projects_dir)
    payload = (
        json.dumps(savings_to_dict(result), indent=2)
        if as_json
        else render_savings(result)
    )
    # Exit 2 is "nothing to do — the filter has removed nothing yet". Not an error,
    # and the readout still prints, for the same reason `inspect` does.
    return (2 if not result.priced else 0), payload
