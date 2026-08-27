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

from . import filter as filter_mod
from . import savings as savings_mod
from . import trial as trial_mod
from .inspect import (
    CONTENT_CLASSES,
    Report,
    inspect_session,
)
from .rules import RULE_ORDER, RULE_TIER

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
        "wire_content_bytes": report.wire_content_bytes,
        "filter_ledger": (
            {
                "requests": report.filtered.requests,
                "bytes_dropped": report.filtered.bytes_dropped,
                "by_rule": report.filtered.by_rule,
                # The naive sum and the entry count, so the echo the stateless
                # filter writes into its own ledger is visible rather than
                # silently corrected. `bytes_dropped` above is de-duplicated.
                "removal_events": report.filtered.removal_events,
                "bytes_summed": report.filtered.bytes_summed,
                "legacy_entries": report.filtered.legacy_entries,
            }
            if report.filtered is not None
            else None
        ),
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
    if report.filtered is not None:
        dropped = report.filtered.bytes_dropped
        add(f"  kept off the wire by the intake filter, on "
            f"{report.filtered.requests:,} of this session's requests:")
        add(f"    {_human(dropped):>10}   "
            + "  ".join(f"{rule} {_human(b)}" for rule, b in
                        sorted(report.filtered.by_rule.items())))
        if report.filtered.bytes_summed > dropped:
            add(f"    from {report.filtered.removal_events:,} ledger entries "
                f"({report.filtered.echo_factor:.1f}x echo) — the filter is "
                f"stateless and re-drops a result on every later request")
        add(f"  the API saw   {_human(report.wire_content_bytes):>10}   "
            "— every share below is of what is on disk, not of that")
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
    filter_ledger: Path | None = None,
) -> tuple[int, str]:
    """`(exit code, output)`. Exit codes follow SPEC §8: 1 usage, 2 nothing to do."""
    try:
        path = resolve_session(session)
    except LookupError as exc:
        return 1, f"winnow: {exc}"
    report = inspect_session(path, keep_last=keep_last, min_bytes=min_bytes,
                             filter_ledger=filter_ledger)
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
            "lines_without_version": result.ledger.lines_without_version,
            "heartbeats": result.ledger.heartbeats,
            "last_heartbeat": result.ledger.last_heartbeat,
            "prefix_lines": result.ledger.prefix_lines,
            "prefix_breaks": result.ledger.prefix_breaks,
            "last_prefix": result.ledger.last_prefix,
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
    if ledger.lines_without_version:
        add(f"  {ledger.lines_without_version:,} lines predate the schema version "
            "and are read as v0")
    if ledger.heartbeats:
        # The denominator this command has never had. A ledger line is written
        # only on a *changed* request, so without these the file records successes
        # and nothing else, and "the filter ran all week and found nothing" is
        # indistinguishable from "the filter has not been in the path since
        # Tuesday". Baseline on this operator's corpus: 7.29% of tool results are
        # candidates, 6.5% of turns produce a line, 67.4% of sessions have at
        # least one. An order of magnitude below that is not a quiet week.
        add("")
        add(f"heartbeat        {ledger.heartbeats:>10,} lines   "
            "what the filter looked at, including the requests it changed nothing on")
        last = ledger.last_heartbeat
        if last:
            seen = last.get("tool_results_seen", 0)
            claimed = last.get("candidates", 0)
            rate = (claimed / seen * 100) if seen else 0.0
            add(f"  latest: {last.get('requests', 0):,} requests, "
                f"{last.get('filtered', 0):,} filtered, "
                f"{seen:,} tool results seen, {claimed:,} claimed ({rate:.2f}%)")
            if last.get("unreadable") or last.get("filter_errors"):
                add(f"  {last.get('unreadable', 0):,} unreadable bodies, "
                    f"{last.get('filter_errors', 0):,} filter errors")
            if seen and not claimed:
                add("  nothing claimed against results that were seen — that is a "
                    "fault, not a quiet week")
    if ledger.malformed_entries:
        add(f"  {ledger.malformed_entries:,} entries carried no usable size and could "
            "not be counted as removals")
    if ledger.prefix_lines:
        # The bytes nothing else in this tree has ever counted. Zero of 866
        # transcripts carry a system prompt or a tool definition — Claude Code
        # writes the conversation, and the fixed prefix is built at request time
        # from the CLI's configuration, CLAUDE.md, the plugins and every connected
        # MCP server. The only process that has ever held them is the proxy.
        last = ledger.last_prefix or {}
        add("")
        add("fixed prefix     "
            f"{_human(last.get('system_bytes', 0) + last.get('tools_bytes', 0)):>10}   "
            f"system {_human(last.get('system_bytes', 0))}   "
            f"tools {_human(last.get('tools_bytes', 0))} "
            f"in {last.get('tool_count', 0)} definitions")
        breaks = last.get("breakpoints") or {}
        if breaks:
            add(f"  breakpoints: system {breaks.get('system', 0)}  "
                f"tools {breaks.get('tools', 0)}  "
                f"messages {breaks.get('messages', 0)}  "
                f"(the API caps them at {filter_mod.MAX_BREAKPOINTS} across all three)")
        widest = sorted((last.get("tools") or {}).items(), key=lambda kv: -kv[1])[:5]
        if widest:
            add("  largest definitions: "
                + "  ".join(f"{name} {_human(size)}" for name, size in widest))
        if ledger.prefix_breaks:
            # A prefix that never matches turns this install's $4,409 cache-read
            # line into an $88,171 write line. Nothing in Claude Code or in the
            # vendor's reporting would say so.
            add(f"  **{ledger.prefix_breaks:,} prefix changes** across "
                f"{ledger.prefix_lines:,} observations — each one invalidates the "
                "whole conversation behind it")
            changed = last.get("changed") or {}
            for field_name, label in (("tools_added", "added"),
                                      ("tools_removed", "removed"),
                                      ("tools_resized", "changed size")):
                names = changed.get(field_name) or []
                if names:
                    add(f"    last change {label}: {', '.join(names[:6])}")
        else:
            add("  stable across every observation")
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


# ─── `winnow trial` ──────────────────────────────────────────────────────────


def _money(value: float | None) -> str:
    """A dollar figure, or a dash where there is no number rather than a zero.

    `savings_to_dict`'s rule about unknowns, applied to a column: an arm with no
    priced session has *no* cost per session, and printing $0.00 there would put
    the cheapest-looking arm in the column an operator is scanning for exactly
    that.
    """
    return "—" if value is None else f"${value:,.2f}"


def trial_to_dict(trial: trial_mod.Trial) -> dict:
    return {
        "corpus": trial.corpus,
        "unattributed_sessions": trial.unattributed_sessions,
        "straddling_sessions": trial.straddling_sessions,
        "unpriced_sessions": trial.unpriced_sessions,
        "billed_not_modelled": True,
        "arms": [
            {
                "label": arm.label,
                "sessions": arm.sessions,
                "priced_sessions": arm.priced_sessions,
                "turns": arm.turns,
                "billed_input_tokens": arm.billed_input,
                "output_tokens": arm.output_tokens,
                "dollars": round(arm.dollars, 4),
                "dollars_per_session": arm.dollars_per_session,
                "median_session_dollars": arm.median_session_dollars,
                "dollars_per_turn": arm.dollars_per_turn,
                "tasks": arm.tasks,
                "dollars_per_task": arm.dollars_per_task,
                "tool_calls": arm.tool_calls,
                "repeat_tool_calls": arm.repeat_tool_calls,
                "repeat_rate": arm.repeat_rate,
            }
            for arm in trial.arms
        ],
    }


def render_trial(trial: trial_mod.Trial) -> str:
    """The human readout, laid out like `render_savings`."""
    out: list[str] = []
    add = out.append

    add("winnow trial — what each arm actually cost, from the bill")
    add(f"  {trial.corpus}")
    add("")

    if not trial.arms:
        add("no arms declared. `winnow trial arm --label <name>` marks the moment a")
        add("configuration went live; a session is attributed to whichever arm was in")
        add("force when its first turn was billed, so the marks have to come first.")
        return "\n".join(out)

    add(f"{'arm':<16}{'sessions':>9}{'turns':>8}{'billed $':>11}"
        f"{'$/session':>11}{'median':>10}{'$/turn':>9}{'$/task':>9}")
    for arm in trial.arms:
        add(f"{arm.label[:15]:<16}{arm.sessions:>9,}{arm.turns:>8,}"
            f"{_money(arm.dollars):>11}{_money(arm.dollars_per_session):>11}"
            f"{_money(arm.median_session_dollars):>10}"
            f"{_money(arm.dollars_per_turn):>9}{_money(arm.dollars_per_task):>9}")
    add("")

    add(f"{'arm':<16}{'tool calls':>11}{'repeats':>9}{'repeat rate':>13}")
    for arm in trial.arms:
        rate = "—" if arm.repeat_rate is None else f"{arm.repeat_rate * 100:.1f}%"
        add(f"{arm.label[:15]:<16}{arm.tool_calls:>11,}{arm.repeat_tool_calls:>9,}"
            f"{rate:>13}")
    add(f"  repeats: {trial_mod.REPEAT_NOTE}")
    add("")

    # Everything below is the reader being told what the table above cannot carry.
    # A trial that printed only the table would be the thing this project exists
    # to argue against — a number with its assumptions left off.
    missing = [arm.label for arm in trial.arms if arm.tasks is None]
    if missing:
        add(f"$/task is blank for {', '.join(missing)} — pass --tasks "
            "<arm>=<count>.")
        add("  It is the only column that decides anything. A tool that made the")
        add("  model cheaper per turn and worse at finishing would win every other")
        add("  column here, and SPEC §9 denominates milestone 3 per *successful*")
        add("  task for that reason. Nothing in a transcript records whether the")
        add("  work was any good, so the count has to come from you.")
        add("")

    if trial.straddling_sessions:
        add(f"{trial.straddling_sessions} session(s) were still running when the arm "
            "changed, and are")
        add("  counted under the arm they started in. They carry both configurations.")
    if trial.unattributed_sessions:
        add(f"{trial.unattributed_sessions} session(s) predate the first arm and are "
            "in no column.")
    if trial.unpriced_sessions:
        add(f"{trial.unpriced_sessions} session(s) ran on a model with no price here; "
            "their turns are")
        add("  counted and their dollars are not, so $/turn and $/session differ in "
            "population.")

    add("")
    add("These are billed figures — `message.usage`, priced at list. Nothing here")
    add("is modelled, and nothing here is a saving: it is what each arm cost. The")
    add("arms ran on different days over different work, so interleave them and")
    add("read the medians, not one week against the next.")
    return "\n".join(out)


def trial_command(
    corpus: str | None,
    arms: str | None,
    tasks: list[str] | None,
    as_json: bool,
) -> tuple[int, str]:
    """`(exit code, output)`. Exit codes follow SPEC §8: 1 usage, 2 nothing to do."""
    if not corpus:
        return 1, "winnow: --corpus is required; there is no default."
    corpus_path = Path(corpus).expanduser()
    if not corpus_path.exists():
        return 1, f"winnow: no corpus at {corpus_path}."
    arms_path = Path(arms).expanduser() if arms else trial_mod.DEFAULT_ARMS

    counts: dict[str, int] = {}
    for pair in tasks or []:
        label, _, raw = pair.partition("=")
        if not label or not raw.isdigit():
            return 1, (f"winnow: --tasks wants <arm>=<count>, got {pair!r}. The count "
                       "is how many tasks that arm actually finished.")
        counts[label] = int(raw)

    declared = trial_mod.read_arms(arms_path)
    unknown = sorted(set(counts) - {a.label for a in declared})
    if unknown:
        # Refused rather than ignored: a task count silently attached to nothing
        # produces a report whose most important column is empty for a reason the
        # operator has no way to see.
        return 1, (f"winnow: --tasks names {', '.join(unknown)}, which no arm in "
                   f"{arms_path} declares.")

    result = trial_mod.build_trial(trial_mod.collect(corpus_path), declared, counts)
    result.corpus = str(corpus_path)
    payload = (
        json.dumps(trial_to_dict(result), indent=2)
        if as_json
        else render_trial(result)
    )
    # Exit 2 is "nothing to do" — no arm has been declared, so nothing can be
    # attributed. Not an error, and the readout still says what to do about it.
    return (2 if not result.arms else 0), payload
