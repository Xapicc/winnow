"""`winnow plan` — the dry run. What would go, and the arithmetic. Writes nothing.

SPEC §8 gives `fork` no `--dry-run` because dry is the default; `plan` is that
default given its own name, so an operator can ask the question without the flag
that answers it destructively being anywhere on the command line.

**This is the module that decides what a fork removes, not just what it reports.**
`inspect` measures the ceiling of SPEC §4's mechanism: every rule enabled, guard
G4 not applied, because no pointer is written there and a ceiling is what
milestone 1 published. `plan` is the other thing — the operator's actual
selection, each surviving result paired with the exact pointer that would replace
it, and G4 applied per result against that pointer's own length. The writer run
builds `fork` on top of this list rather than reclassifying, which is what makes
"`plan` and `fork` agree" a property of the code instead of a promise.

**Why G4 has to be here and cannot be left to the writer.** G4 compares a result
against its pointer, and the pointer names the rule that fired and the size of
what it replaces — so it does not exist until a rule has fired. Deciding it at
write time would mean `plan` reporting a saving the fork then declines to take,
and SPEC §8's whole reason for `plan` existing is that the dry run is believable.

What is deliberately *not* here, because it belongs to the writer: `--write`,
`--out`, `--force`, `--min-cold-age`, and G5's enforcing form. `plan` cannot
reach SPEC §8's exit code 3 at all — nothing it does can be refused for warmth or
liveness, because nothing it does touches a file. Its guard refusals are
outcomes, reported, and it exits 2 when they leave nothing to do.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .inspect import Report, break_even_turns, inspect_session
from .report import RULE_LABELS, _human, resolve_session
from .rules import (
    DEFAULT_KEEP_LAST,
    DEFAULT_MIN_BYTES,
    OPT_IN_RULES,
    RULE_ORDER,
    RULE_TIER,
    TIER_RULES,
    RuleSelectionError,
    classify,
    inflates,
    pointer_id,
    render_pointer,
    resolve_rules,
    suppressed_by_default,
)

# How much of a tool's arguments `--explain` prints. SPEC §8 asks for the
# arguments; SPEC §10 records that they routinely contain credentials pasted into
# a Bash command. A bound is not redaction and is not claimed to be — winnow
# cannot tell a secret from a path — but an unbounded echo of a 40 KB input into
# a terminal is a different kind of exposure from one line, and one line is what
# SPEC §8 asked for.
EXPLAIN_ARGUMENT_CHARS = 160

# How many further turns `fork` assumes the session has left, when the operator
# does not say. SPEC §7 gives the formula and names the quantity; this is the
# other half of it, and it is a **budget rather than a measurement**: T* is a
# property of the transcript and can be computed, the turns the session has left
# are not and cannot.
#
# 60 is where the corpus puts it. Over 396 local sessions truncated at the moment
# they first pass 150k of context, forked through this code path and scored
# against the API requests each session actually went on to make:
#
#     fork whenever a rule fires   396 cuts, 30% of them paid, net −$10.85
#     T* <= 60                     114 cuts, 64% of them paid, net +$56.06
#
# The ungated row is the finding — writing a fork because a rule fired is, on this
# corpus, worse than not forking at all, because a rule firing is evidence that a
# result *can* go and no evidence at all that removing it pays. The budget sweep
# is flat across the middle (+$55.95, +$56.06, +$58.46 at 40, 60, 100) and falls
# away outside it, so the sign is load-bearing and the exact value is not; 60 is
# taken because the median session in that set had 64 turns left.
DEFAULT_MAX_BREAK_EVEN = 60

EXPLAIN_WARNING = (
    "These lines carry tool arguments verbatim, and a transcript routinely "
    "contains credentials pasted into a Bash command (SPEC §10). Treat this "
    "output as sensitive; winnow writes no log of it."
)


class PlanError(ValueError):
    """A usage error: SPEC §8 exit code 1. The message is the whole explanation."""


@dataclass(frozen=True)
class Strip:
    """One `tool_result` that would be replaced, and the pointer replacing it.

    Frozen and self-contained: the writer run needs `use_id` to find the block,
    `pointer` to put in it, and `digest` to record — and needs none of them
    re-derived, because a second derivation is a second chance to disagree.
    """

    pointer_id: str
    order: int
    line: int
    tool: str
    rule: str
    use_id: str
    result_size: int
    digest: str
    pointer: str
    arguments: str

    @property
    def pointer_size(self) -> int:
        return len(self.pointer)

    @property
    def net(self) -> int:
        """Bytes actually leaving the prefix. Positive for every strip: G4
        refused the rest."""
        return self.result_size - self.pointer_size


@dataclass
class Plan:
    """What `winnow plan` found. Nothing here has been written anywhere."""

    session_id: str
    path: Path
    tier: str
    rules: frozenset[str]
    keep_last: int
    min_bytes: int
    report: Report
    strips: list[Strip] = field(default_factory=list)
    # G4's refusals, kept rather than counted. A result whose pointer would cost
    # more than the result is the one case where an operator's reaction should be
    # to lower --min-bytes' opposite — and they cannot react to a number.
    inflated: list[Strip] = field(default_factory=list)
    # Rules the tier names that are off by default on their own measured
    # precision (rules.DISABLED_BY_DEFAULT). Carried so the readout can say so:
    # an operator comparing this run against last month's needs to be told the
    # tier means fewer rules now, not left to work it out from a smaller share.
    suppressed: tuple[str, ...] = ()

    @property
    def removed_bytes(self) -> int:
        return sum(s.result_size for s in self.strips)

    @property
    def pointer_bytes(self) -> int:
        return sum(s.pointer_size for s in self.strips)

    @property
    def net_bytes(self) -> int:
        """What the fork actually saves: the content removed, less the pointers
        that replace it. The number SPEC §8 calls "the net"."""
        return self.removed_bytes - self.pointer_bytes

    @property
    def cut_line(self) -> int | None:
        """The earliest line this plan would touch. The cut point SPEC §7 prices."""
        return min((s.line for s in self.strips), default=None)

    @property
    def suffix_bytes(self) -> int:
        cut = self.cut_line
        return self.report.suffix_from(cut) if cut is not None else 0

    def by_rule(self) -> dict[str, dict[str, int]]:
        """Per-rule totals, in RULE_ORDER. Every enabled rule appears, including
        the ones that fired on nothing — a rule that claimed nothing is a finding."""
        out = {
            rule: {"hits": 0, "bytes": 0, "pointer_bytes": 0, "net_bytes": 0}
            for rule in RULE_ORDER
            if rule in self.rules
        }
        for strip in self.strips:
            entry = out[strip.rule]
            entry["hits"] += 1
            entry["bytes"] += strip.result_size
            entry["pointer_bytes"] += strip.pointer_size
            entry["net_bytes"] += strip.net
        return out

    def by_tier(self) -> dict[str, dict[str, int]]:
        """The same totals grouped by the tier each firing rule belongs to."""
        out: dict[str, dict[str, int]] = {
            t: {"hits": 0, "bytes": 0, "pointer_bytes": 0, "net_bytes": 0}
            for t in ("C", "B", "A")
        }
        for strip in self.strips:
            entry = out[RULE_TIER[strip.rule]]
            entry["hits"] += 1
            entry["bytes"] += strip.result_size
            entry["pointer_bytes"] += strip.pointer_size
            entry["net_bytes"] += strip.net
        return out

    def break_even_turns(self) -> float | None:
        """`T* = 19·(S/D) − 20` for this plan's own cut.

        D is the **net**, not the removed bytes: the pointers stay in the prefix
        and are cache-written with everything else, so a cut that removes 10 KB
        and adds 1 KB of pointer has moved 9 KB. `inspect` prices the gross,
        because it has no pointers to subtract, so `plan`'s T* is slightly the
        longer of the two on the same session and tier. That gap is real and this
        side of it is the honest one.

        S follows `inspect`'s convention — every byte of message content standing
        at or after the cut line, the removed ones included — so that the two
        commands' arithmetic is comparable rather than subtly differently scaled.
        """
        return break_even_turns(self.suffix_bytes, self.net_bytes)

    def pays_within(self, turns: int | None) -> bool | None:
        """Does this cut clear its own invalidation inside `turns` further turns?

        None when there is no cut to price, or no budget to price it against —
        the two cases a caller must not read as "yes". Kept here rather than
        spelled at each call site so `plan`'s readout and `fork`'s refusal cannot
        come to different verdicts on the same number, which is the same reason
        the rule engine has one home.
        """
        if turns is None:
            return None
        needed = self.break_even_turns()
        return None if needed is None else needed <= turns


def resolve_selection(
    tier: str,
    enable: list[str] | None = None,
    disable: list[str] | None = None,
    i_know: bool = False,
) -> frozenset[str]:
    """SPEC §8's rule selection, with tier A's acknowledgement enforced.

    SPEC §8 attaches `--i-know` to `--tier CBA`. It is enforced here on the
    *resolved selection* instead, so that `--rule A1` needs it too. SPEC §4 says
    tier A "is opt-in, never a default" and calls it "the rule most likely to be
    wrong"; a flag that guards the tier but not the rule inside it guards
    nothing, since `--tier CB --rule A1` reaches the same place.
    """
    try:
        selected = resolve_rules(tier, enable or (), disable or ())
    except RuleSelectionError as exc:
        raise PlanError(str(exc)) from exc

    opt_in = sorted(selected & OPT_IN_RULES)
    if opt_in and not i_know:
        raise PlanError(
            f"tier A rules ({', '.join(opt_in)}) are opt-in and never a default: "
            "SPEC §4 calls A1 the rule most likely to be wrong, because a file the "
            "session edited is a file it was reasoning about. Pass --i-know to "
            "select them anyway."
        )
    return selected


def build_plan(
    path: Path,
    tier: str = "CB",
    rules: frozenset[str] | None = None,
    keep_last: int | None = None,
    min_bytes: int | None = None,
    filter_ledger: Path | None = None,
) -> Plan:
    """Classify one session under one selection and pair each hit with its pointer.

    Reads the transcript once, through `inspect_session`, so that `plan` and
    `inspect` cannot disagree about what the file contains either.

    `filter_ledger` is `winnow filter --ledger`, joined on `requestId`. Without it
    every figure below is computed from a transcript that still contains bytes the
    API never received — the filter does not touch the transcript, so Claude Code
    writes what it held. On a filtered session that is up to 8.49% of message
    content, and 79.0% of what `winnow plan --tier CB` proposes to remove is
    content the filter claims too. The correction existed, was tested and was
    rendered, and was reachable only from the one command that writes nothing.
    """
    keep_last = DEFAULT_KEEP_LAST if keep_last is None else keep_last
    min_bytes = DEFAULT_MIN_BYTES if min_bytes is None else min_bytes
    if keep_last < 0:
        raise PlanError(f"--keep-last must not be negative, got {keep_last}")
    if min_bytes < 0:
        raise PlanError(f"--min-bytes must not be negative, got {min_bytes}")
    if rules is None:
        rules = frozenset(TIER_RULES[tier]) if tier in TIER_RULES else frozenset()

    report = inspect_session(path, keep_last=keep_last, min_bytes=min_bytes,
                             filter_ledger=filter_ledger)
    assigned, _ = classify(report.calls, keep_last, min_bytes, enabled=rules)

    plan = Plan(
        session_id=report.session_id,
        path=path,
        tier=tier,
        rules=rules,
        keep_last=keep_last,
        min_bytes=min_bytes,
        report=report,
    )
    # Sorted by call order rather than by dict iteration: SPEC §10 forbids map
    # iteration order in the output, and every downstream figure here is a sum
    # over this list.
    for call in sorted(report.calls, key=lambda c: c.order):
        rule = assigned.get(call.order)
        if rule is None:
            continue
        identifier = pointer_id(rule, call.order)
        pointer = render_pointer(
            tool=call.name,
            rule=rule,
            size=call.result_size,
            digest=call.digest,
            session_id=report.session_id,
            identifier=identifier,
        )
        strip = Strip(
            pointer_id=identifier,
            order=call.order,
            line=call.line,
            tool=call.name,
            rule=rule,
            use_id=call.use_id,
            result_size=call.result_size,
            digest=call.digest,
            pointer=pointer,
            arguments=_arguments(call.tool_input),
        )
        # G4, per result, against this result's own pointer.
        if inflates(pointer, call.result_size):
            plan.inflated.append(strip)
        else:
            plan.strips.append(strip)
    return plan


def _arguments(tool_input: dict) -> str:
    """The `--explain` rendering of a call's input: one line, bounded.

    `sort_keys` so that two runs over the same transcript print the same line —
    the same reason `rules.canonical_input` sorts.
    """
    try:
        text = json.dumps(tool_input, sort_keys=True)
    except (TypeError, ValueError):
        text = repr(tool_input)
    text = " ".join(text.split())
    if len(text) > EXPLAIN_ARGUMENT_CHARS:
        return text[: EXPLAIN_ARGUMENT_CHARS - 1] + "…"
    return text


# ─── Rendering ───────────────────────────────────────────────────────────────


def to_dict(plan: Plan, explain: bool = False,
            max_break_even: int | None = None) -> dict:
    """The `--json` shape. Deterministic: every list is ordered, every map is
    built in a fixed key order (SPEC §10)."""
    # The wire denominator, not the disk one. On a session the intake filter ran
    # over, the transcript still holds bytes the API never received, so a share
    # against `message_content_bytes` is a share of a session that did not happen.
    # Equal to the disk figure when no ledger was supplied, so nothing moves for a
    # session that was never filtered.
    total = plan.report.wire_content_bytes
    share = (lambda n: round(n / total * 100, 4)) if total else (lambda n: 0.0)
    turns = plan.break_even_turns()
    payload = {
        "session_id": plan.session_id,
        "path": str(plan.path),
        "selection": {
            "tier": plan.tier,
            "rules": sorted(plan.rules),
            "keep_last": plan.keep_last,
            "min_bytes": plan.min_bytes,
            "suppressed_by_default": list(plan.suppressed),
        },
        "message_content_bytes": plan.report.message_content_bytes,
        # The denominator every share in this payload is against.
        "wire_content_bytes": total,
        "filter_ledger": (
            {
                "requests": plan.report.filtered.requests,
                "bytes_dropped": plan.report.filtered.bytes_dropped,
                "by_rule": plan.report.filtered.by_rule,
                # `S` is the suffix after the cut and it is still measured from
                # disk. Correcting it needs the ledger's per-result ids matched
                # against positions in this session, which is a join `inspect`
                # does not do. Named here rather than left to be inferred.
                "suffix_corrected": False,
            }
            if plan.report.filtered is not None
            else None
        ),
        "results": {
            "tool_calls": plan.report.tool_calls,
            "stripped": len(plan.strips),
            "refused_by_g4": len(plan.inflated),
        },
        "bytes": {
            "removed": plan.removed_bytes,
            "pointer_overhead": plan.pointer_bytes,
            "net": plan.net_bytes,
            "removed_share": share(plan.removed_bytes),
            "net_share": share(plan.net_bytes),
        },
        "by_rule": {
            rule: {"tier": RULE_TIER[rule], **totals, "share": share(totals["bytes"])}
            for rule, totals in plan.by_rule().items()
        },
        "by_tier": {
            name: {**totals, "share": share(totals["bytes"])}
            for name, totals in plan.by_tier().items()
        },
        "guards": {
            **plan.report.guard_blocked,
            "G4_would_inflate": len(plan.inflated),
        },
        "arithmetic": {
            "tier": plan.tier,
            "cut_line": plan.cut_line,
            "removed_bytes": plan.net_bytes,
            "suffix_bytes": plan.suffix_bytes,
            "suffix_over_removed": (
                round(plan.suffix_bytes / plan.net_bytes, 3) if plan.net_bytes else None
            ),
            "break_even_turns": round(turns, 1) if turns is not None else None,
            "max_break_even": max_break_even,
            "pays_within_budget": plan.pays_within(max_break_even),
        },
        "pointers": [
            {
                "id": strip.pointer_id,
                "line": strip.line,
                "tool_use_id": strip.use_id,
                "tool": strip.tool,
                "rule": strip.rule,
                "bytes": strip.result_size,
                "pointer_bytes": strip.pointer_size,
                "sha256": strip.digest,
            }
            for strip in plan.strips
        ],
    }
    if explain:
        payload["explain"] = {
            "warning": EXPLAIN_WARNING,
            "results": [
                {
                    "id": strip.pointer_id,
                    "rule": strip.rule,
                    "tool": strip.tool,
                    "arguments": strip.arguments,
                    "bytes": strip.result_size,
                }
                for strip in plan.strips
            ],
        }
    return payload


def render(plan: Plan, explain: bool = False,
           max_break_even: int | None = None) -> str:
    """The human readout, laid out like `report.render` so the two read alike.

    `_human` and `RULE_LABELS` come from `report` rather than being redefined:
    an operator reading `inspect` and then `plan` should not have to notice that
    one says `2.0 KB` and the other `2048 B`.
    """
    header = [
        f"plan for session {plan.session_id}",
        f"  {plan.path}",
        (f"  tier {plan.tier}   rules {', '.join(sorted(plan.rules)) or 'none'}   "
         f"keep-last {plan.keep_last}   min-bytes {plan.min_bytes:,}"),
        *suppression_note(plan),
        "  writes nothing; this is what `winnow fork --write` would do",
        "",
    ]
    return "\n".join([*header, render_body(plan, explain, max_break_even)])


def suppression_note(plan: Plan) -> list[str]:
    """The line that says a tier meant fewer rules than its name lists, or nothing.

    A list rather than a string so a caller can splice it into a header without
    testing it, and so that the note is written once for `plan` and `fork` alike.
    """
    if not plan.suppressed:
        return []
    note = (
        f"  off by default: {', '.join(plan.suppressed)} — measured precision "
        f"below the bar (MILESTONES milestone 2). Re-enable with "
        f"--rule {' --rule '.join(plan.suppressed)}"
    )
    return [note]


def render_body(plan: Plan, explain: bool = False,
                max_break_even: int | None = None) -> str:
    """Everything below the heading: the rules, the bytes, the guards, the T*.

    Split from `render` so that `fork` can print the same arithmetic under its own
    heading. A fork that has just written a file cannot say "writes nothing", and
    a second copy of this table would be a second chance for the dry run and the
    write to disagree about what they removed.
    """
    total = plan.report.wire_content_bytes
    out: list[str] = []
    add = out.append

    add(f"would strip       {len(plan.strips):>10,} of {plan.report.tool_calls:,} "
        "tool results")
    # A share that silently changed base is worse than one that is consistently
    # conservative, so when the base moves the readout says so — and says which
    # figure did *not* move with it.
    if plan.report.filtered is not None and plan.report.filtered.bytes_dropped:
        seen = plan.report.filtered
        add("")
        add(f"the intake filter kept {_human(seen.bytes_dropped)} off the wire on "
            f"{seen.requests:,} of this session's requests")
        add(f"  every share below is of the {_human(total)} the API saw, not of "
            f"the {_human(plan.report.message_content_bytes)} on disk")
        add("  S is still measured from disk: the positional correction needs the "
            "ledger's")
        add("  per-result ids matched against this session, and that join is not "
            "implemented")
    add("")

    add("by rule")
    for rule, totals in plan.by_rule().items():
        pct = (totals["bytes"] / total * 100) if total else 0.0
        marker = "*" if rule in OPT_IN_RULES else " "
        add(f"  {rule}{marker} {RULE_LABELS[rule]:<28} {_human(totals['bytes']):>10}   "
            f"{pct:5.2f}%   {totals['hits']:,} results")
    if plan.rules & OPT_IN_RULES:
        add("  * tier A, selected with --i-know (SPEC §4)")
    if not plan.by_rule():
        add("  no rule is enabled by this selection")
    add("")

    add("by tier")
    for name, totals in plan.by_tier().items():
        if not totals["hits"] and name not in {RULE_TIER[r] for r in plan.rules}:
            continue
        pct = (totals["bytes"] / total * 100) if total else 0.0
        add(f"  {name:<4} {_human(totals['bytes']):>10}   {pct:5.2f}%   "
            f"{totals['hits']:,} results")
    add("")

    add("bytes")
    add(f"  removed        {_human(plan.removed_bytes):>10}")
    add(f"  pointers add   {_human(plan.pointer_bytes):>10}   "
        f"{len(plan.strips):,} pointers")
    add(f"  net            {_human(plan.net_bytes):>10}   "
        f"{(plan.net_bytes / total * 100) if total else 0.0:5.2f}% of message content")
    add("")

    refused = "  ".join(
        f"{name} {count:,}" for name, count in plan.report.guard_blocked.items() if count
    )
    add(f"guards refused   {refused or 'none'}")
    if plan.inflated:
        # Named rather than folded into the count, because G4 is the one guard an
        # operator can act on: it fires when a result is barely above --min-bytes,
        # and raising that flag makes the whole class go away.
        worst = min(plan.inflated, key=lambda s: s.result_size)
        add(f"  G4_would_inflate {len(plan.inflated):,}   the pointer is longer than "
            "the result, so the result stays")
        add(f"    smallest: {worst.tool} at line {worst.line}, "
            f"{worst.result_size:,} bytes against a {worst.pointer_size:,}-byte pointer")
        add(f"    raising --min-bytes above {max(s.result_size for s in plan.inflated):,} "
            "removes the class")
    add("")

    turns = plan.break_even_turns()
    if not plan.strips:
        add(f"arithmetic       nothing fires at tier {plan.tier}; no cut, no break-even")
    elif turns is None:
        add(f"arithmetic       tier {plan.tier}, cut at line {plan.cut_line}")
        add("  net is zero or negative after pointer overhead; no break-even")
    else:
        add(f"arithmetic       tier {plan.tier}, cut at line {plan.cut_line}")
        add(f"  D net removed  {_human(plan.net_bytes):>10}   "
            "(removed less the pointers that replace it)")
        add(f"  S suffix       {_human(plan.suffix_bytes):>10}")
        add(f"  S/D            {plan.suffix_bytes / plan.net_bytes:>10.1f}")
        add(f"  T* = 19·(S/D) − 20 = {turns:,.0f} further turns to pay for itself")
        add(f"  ({plan.report.usage.turns:,} assistant turns in this session so far)")
        verdict = plan.pays_within(max_break_even)
        if verdict is not None:
            add(f"  against a budget of {max_break_even:,} further turns "
                f"(--max-break-even): {'PAYS' if verdict else 'DOES NOT PAY'}")

    if explain:
        add("")
        add(f"explain ({len(plan.strips):,} results)")
        add(f"  {EXPLAIN_WARNING}")
        for strip in plan.strips:
            add(f"  {strip.pointer_id:<8} {strip.rule}  {strip.tool:<10} "
                f"{strip.result_size:>10,} B  {strip.arguments}")
    return "\n".join(out)


def plan_command(
    session: str,
    tier: str = "CB",
    rule: list[str] | None = None,
    no_rule: list[str] | None = None,
    keep_last: int | None = None,
    min_bytes: int | None = None,
    i_know: bool = False,
    as_json: bool = False,
    explain: bool = False,
    max_break_even: int | None = DEFAULT_MAX_BREAK_EVEN,
    filter_ledger: Path | None = None,
) -> tuple[int, str]:
    """`(exit code, output)`. SPEC §8: 0 success, 1 usage error, 2 nothing to do.

    Never 3. Exit 3 is "refused — session too warm, session live, G5 would be
    violated", and all three are properties of writing a file. `plan` writes
    nothing, so it has nothing to refuse; its guards produce an outcome rather
    than a refusal, and the outcome is exit 2 when they leave nothing to do.

    `--max-break-even` is on the same footing: `plan` **reports** the verdict the
    gate would reach and does not change its exit code for it, because a dry run
    that exited non-zero on an economic judgement would be indistinguishable from
    one that found nothing to strip. The number it prints is the number `fork`
    refuses on, computed by `Plan.pays_within` in both — the same reason the rule
    engine has one home.
    """
    try:
        selection = resolve_selection(tier, rule, no_rule, i_know)
    except PlanError as exc:
        return 1, f"winnow: {exc}"
    try:
        path = resolve_session(session)
    except LookupError as exc:
        return 1, f"winnow: {exc}"
    try:
        plan = build_plan(path, tier=tier, rules=selection,
                          keep_last=keep_last, min_bytes=min_bytes,
                          filter_ledger=filter_ledger)
    except PlanError as exc:
        return 1, f"winnow: {exc}"
    # Set here rather than derived inside `build_plan`, which is handed a resolved
    # rule set and cannot tell a rule the operator switched off from one the
    # defaults did. The names were validated by `resolve_selection` above.
    plan.suppressed = suppressed_by_default(tier, rule or (), no_rule or ())

    if max_break_even is not None and max_break_even < 0:
        return 1, ("winnow: --max-break-even is a number of further turns and must "
                   f"not be negative, got {max_break_even}")

    payload = (
        json.dumps(to_dict(plan, explain, max_break_even), indent=2)
        if as_json
        else render(plan, explain, max_break_even)
    )
    if plan.strips:
        return 0, payload
    # Exit 2 is "nothing to do — no result met a rule". The readout still prints,
    # for the same reason `inspect`'s does, and the line below names what refused
    # rather than leaving the operator to infer it from a table of zeroes: SPEC §8
    # asks a refusal to be loud and to name the guard.
    return 2, payload + "\n\n" + _nothing_to_do(plan)


def _nothing_to_do(plan: Plan) -> str:
    """Why this plan is empty, in one line that names the guard or the selection.

    Ordered by how actionable the answer is, not by guard number: an operator who
    reads "G2 refused 900 results" can lower `--min-bytes`, and one who reads
    "nothing matched" cannot do anything but widen the tier.
    """
    if not plan.rules:
        return ("winnow: nothing to do — the selection enables no rule at all. "
                "Check --no-rule against --tier.")
    if plan.inflated:
        return (f"winnow: nothing to do — guard G4 refused all "
                f"{len(plan.inflated):,} candidates: the pointer would be longer "
                "than the result it replaces, so the result stays.")
    blocked = {k: v for k, v in plan.report.guard_blocked.items() if v}
    if blocked and not plan.report.tool_calls - sum(blocked.values()):
        named = ", ".join(f"{name} {count:,}" for name, count in blocked.items())
        return (f"winnow: nothing to do — the guards took every candidate: {named}. "
                "G1 is --keep-last, G2 is --min-bytes; G3 and G5 are not "
                "configurable.")
    return (f"winnow: nothing to do — no result met a rule at tier {plan.tier} "
            f"({', '.join(sorted(plan.rules))}). The session is carrying "
            f"{_human(plan.report.wire_content_bytes)} of message content that "
            "these rules cannot classify as once-only.")
