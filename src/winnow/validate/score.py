"""Reading the filled sheet back, and turning it into the two numbers that decide.

Aggregate precision against the 90% bar, and each rule's own precision against the
same bar separately — because MILESTONES milestone 2 disables a rule that misses on
its own strength even when the aggregate passes, and an aggregate is exactly the
statistic that hides one bad rule behind four good ones.

Everything this module refuses to do is as deliberate as what it does. It will not
score a sheet with a blank item, will not score a sheet against a key from a
different draw, and will not score a sheet whose schema version it does not know.
Each of those would produce a number, and a number produced from a sheet that does
not match its key is worse than no number, because it looks like one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..rules import RULE_ORDER, TIER_RULES
from .schema import (
    KILL_BELOW,
    LABELS,
    NEEDED_AGAIN,
    ONCE_ONLY,
    PRECISION_BAR,
    SCHEMA_VERSION,
    UNSURE,
)

_ITEM = re.compile(r"^<!--\s*winnow:item\s+(\S+)\s*-->\s*$")
_END = re.compile(r"^<!--\s*winnow:end\s+(\S+)\s*-->\s*$")
_LABEL = re.compile(r"^label:(.*)$")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# Below this, a rule's point estimate is wide enough to be worth saying so next
# to. It does not change the call — MILESTONES is mechanical about below-90% —
# it tells the reader what a re-label would be for.
MIN_CONFIDENT_N = 20

# Spellings of the three labels that mean the same thing. Forgiving about
# formatting, strict about meaning: a labeller who typed `Once Only` meant
# once-only, and failing their whole sheet over a capital letter would be
# pedantry with a real cost. Anything not in here is still an error.
_ALIASES = {
    "once only": ONCE_ONLY,
    "once_only": ONCE_ONLY,
    "onceonly": ONCE_ONLY,
    "needed again": NEEDED_AGAIN,
    "needed_again": NEEDED_AGAIN,
    "neededagain": NEEDED_AGAIN,
    "not sure": UNSURE,
    "unsure": UNSURE,
}


class SheetError(ValueError):
    """A sheet or key that cannot be scored. The message is the whole explanation."""


def normalise_label(raw: str) -> str | None:
    """One written label as one of `LABELS`, or `None` when the line is blank."""
    text = _COMMENT.sub("", raw)
    text = " ".join(text.split()).strip().lower()
    if not text:
        return None
    if text in LABELS:
        return text
    if text in _ALIASES:
        return _ALIASES[text]
    raise SheetError(
        f"{text!r} is not a label; expected one of {', '.join(LABELS)}"
    )


def parse_sheet(text: str) -> dict[str, str | None]:
    """`{item id: label or None}` for every item in the sheet, in sheet order.

    Every line of quoted transcript content is written blockquoted, so no content
    line begins at column zero and none of it can forge an item marker or a label
    line. That is why the markers can be matched anchored rather than searched for.
    """
    labels: dict[str, str | None] = {}
    current: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        opened = _ITEM.match(line)
        if opened:
            if current is not None:
                raise SheetError(
                    f"line {number}: item {opened.group(1)} opens inside item {current}"
                )
            current = opened.group(1)
            if current in labels:
                raise SheetError(f"line {number}: item {current} appears twice")
            labels[current] = None
            continue
        closed = _END.match(line)
        if closed:
            if current != closed.group(1):
                raise SheetError(
                    f"line {number}: end of item {closed.group(1)} while "
                    f"{'item ' + current if current else 'no item'} is open"
                )
            current = None
            continue
        written = _LABEL.match(line)
        if written:
            if current is None:
                raise SheetError(f"line {number}: a label outside any item")
            try:
                value = normalise_label(written.group(1))
            except SheetError as exc:
                raise SheetError(f"line {number}, item {current}: {exc}") from exc
            if labels[current] is not None and value is not None:
                raise SheetError(f"line {number}: item {current} is labelled twice")
            if value is not None:
                labels[current] = value
    if current is not None:
        raise SheetError(f"item {current} is never closed")
    if not labels:
        raise SheetError("no items in this sheet — is it the right file?")
    return labels


def parse_key(text: str) -> tuple[dict, dict[str, dict]]:
    """`(meta, {item id: key record})` from the key file."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise SheetError("the key file is empty")
    try:
        head = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise SheetError(f"key line 1 is not JSON: {exc}") from exc
    meta = head.get("meta")
    if not isinstance(meta, dict):
        raise SheetError("the key file's first line must be its metadata")
    version = meta.get("schema_version")
    if version != SCHEMA_VERSION:
        raise SheetError(
            f"this key was written under schema version {version!r}; this scorer "
            f"knows version {SCHEMA_VERSION}. The scoring rule may have changed "
            "since the sheet was filled in, and scoring it under a different one "
            "is how a bar moves after the fact."
        )
    items: dict[str, dict] = {}
    for number, line in enumerate(lines[1:], start=2):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SheetError(f"key line {number} is not JSON: {exc}") from exc
        identifier = record.get("item")
        if not identifier:
            raise SheetError(f"key line {number} has no item id")
        if identifier in items:
            raise SheetError(f"key line {number}: item {identifier} appears twice")
        items[identifier] = record
    if not items:
        raise SheetError("the key file has metadata but no items")
    return meta, items


def precision(counts: dict[str, int]) -> float | None:
    """Confirmed once-only over everything labelled, or `None` when nothing was.

    `None` rather than 0.0, and the distinction is the point: a rule nobody drew
    a sample for has no precision, and reporting it as 0% would disable a rule on
    the strength of never having been measured.
    """
    total = sum(counts.get(label, 0) for label in LABELS)
    if total == 0:
        return None
    return counts.get(ONCE_ONLY, 0) / total


def score(labels: dict[str, str | None], key: dict[str, dict], meta: dict) -> dict:
    """The aggregate, the per-rule breakdown, and the verdict."""
    missing = sorted(identifier for identifier, value in labels.items() if value is None)
    if missing:
        raise SheetError(
            f"{len(missing)} item(s) have no label: {', '.join(missing[:10])}"
            + ("…" if len(missing) > 10 else "")
            + ". A sheet with a blank item is refused rather than scored over the "
            "rest of it — the items people leave blank are the hard ones, and "
            "dropping them would score the easy sample."
        )
    unknown = sorted(set(labels) - set(key))
    if unknown:
        raise SheetError(
            f"the sheet has item(s) the key does not: {', '.join(unknown[:10])}"
            + ("…" if len(unknown) > 10 else "")
            + ". Sheet and key must come from the same draw."
        )
    unlabelled = sorted(set(key) - set(labels))
    if unlabelled:
        raise SheetError(
            f"the key has item(s) the sheet does not: {', '.join(unlabelled[:10])}"
            + ("…" if len(unlabelled) > 10 else "")
            + ". Sheet and key must come from the same draw."
        )

    by_rule: dict[str, dict[str, int]] = {}
    overall = dict.fromkeys(LABELS, 0)
    for identifier, label in labels.items():
        rule = key[identifier].get("rule", "?")
        counts = by_rule.setdefault(rule, dict.fromkeys(LABELS, 0))
        counts[label] += 1
        overall[label] += 1

    aggregate = precision(overall)
    rules = {}
    for rule in [*RULE_ORDER, *sorted(set(by_rule) - set(RULE_ORDER))]:
        if rule not in by_rule:
            continue
        counts = by_rule[rule]
        n = sum(counts.values())
        value = precision(counts)
        rules[rule] = {
            "n": n,
            **counts,
            "precision": None if value is None else round(value, 4),
            "below_bar": value is not None and value < PRECISION_BAR,
            "thin": n < MIN_CONFIDENT_N,
        }

    below = [rule for rule, row in rules.items() if row["below_bar"]]
    # Only rules the sampled tier could have produced. A1 sitting under "not
    # sampled" after a tier-CB draw would read as a gap in the corpus, when it is
    # the tier doing exactly what SPEC §8 says it does.
    expected = TIER_RULES.get(str(meta.get("tier", "")), RULE_ORDER)
    if aggregate is None:
        verdict = "unscored"
    elif aggregate < KILL_BELOW:
        verdict = "kill"
    elif aggregate < PRECISION_BAR:
        verdict = "revise"
    else:
        verdict = "pass"

    return {
        "schema_version": SCHEMA_VERSION,
        "meta": meta,
        "n": sum(overall.values()),
        "aggregate": {
            **overall,
            "precision": None if aggregate is None else round(aggregate, 4),
            "meets_bar": aggregate is not None and aggregate >= PRECISION_BAR,
        },
        "by_rule": rules,
        "rules_below_bar": below,
        "not_sampled": [rule for rule in expected if rule not in rules],
        "verdict": verdict,
        "rules_off_setting": ",".join(below),
    }


def render(scoring: dict) -> str:
    """The readout. States the verdict in words, then what to do about it."""
    out: list[str] = []
    add = out.append
    aggregate = scoring["aggregate"]
    value = aggregate["precision"]
    shown = "n/a" if value is None else f"{value * 100:.1f}%"
    add(f"labelled          {scoring['n']:,} items from {scoring['meta'].get('corpus')}")
    add(f"aggregate         {shown} confirmed once-only  "
        f"(bar {PRECISION_BAR * 100:.0f}%)")
    add(f"                  {aggregate[ONCE_ONLY]:,} once-only, "
        f"{aggregate[NEEDED_AGAIN]:,} needed-again, {aggregate[UNSURE]:,} unsure")
    add("")
    add(f"{'rule':<6}{'n':>6}{'once':>7}{'again':>7}{'unsure':>8}"
        f"{'precision':>12}")
    for rule, row in scoring["by_rule"].items():
        rule_value = row["precision"]
        rule_shown = "n/a" if rule_value is None else f"{rule_value * 100:.1f}%"
        flag = "  BELOW BAR" if row["below_bar"] else ""
        thin = "  (thin)" if row["thin"] and not row["below_bar"] else ""
        add(f"{rule:<6}{row['n']:>6,}{row[ONCE_ONLY]:>7,}{row[NEEDED_AGAIN]:>7,}"
            f"{row[UNSURE]:>8,}{rule_shown:>12}{flag}{thin}")
    for rule in scoring["not_sampled"]:
        add(f"{rule:<6}{'—':>6}{'':>7}{'':>7}{'':>8}{'not sampled':>12}")
    add("")

    verdict = scoring["verdict"]
    if verdict == "pass":
        add(f"AGGREGATE PASSES — {shown} is at or above the {PRECISION_BAR:.0%} bar.")
    elif verdict == "revise":
        add(f"AGGREGATE BETWEEN THE BARS — {shown} is under {PRECISION_BAR:.0%} and "
            f"at or above {KILL_BELOW:.0%}. MILESTONES allows exactly one revision "
            "pass over the rules and one re-label. Not two.")
    elif verdict == "kill":
        add(f"AGGREGATE BELOW {KILL_BELOW:.0%} — {shown}. MILESTONES: this stops "
            "milestone 2. Do not revise and re-label; that allowance is for the "
            "80–90% band.")
    else:
        add("NOTHING SCORED.")

    if scoring["rules_below_bar"]:
        add("")
        add(f"BELOW BAR ON THEIR OWN: {', '.join(scoring['rules_below_bar'])} — "
            "disabled by default even though the aggregate may pass "
            "(MILESTONES milestone 2). To act on this now:")
        add(f"  export WINNOW_RULES_OFF={scoring['rules_off_setting']}")
        add("  and set winnow.rules.DISABLED_BY_DEFAULT to the same, with this "
            "score in the commit message.")
    thin = [rule for rule, row in scoring["by_rule"].items() if row["thin"]]
    if thin:
        add("")
        add(f"Thin samples (n < {MIN_CONFIDENT_N}): {', '.join(thin)}. The point "
            "estimate is still what the rule says to act on; a wider interval is "
            "a reason for another label, not for another reading of this one.")
    return "\n".join(out)


def score_files(sheet_path: Path, key_path: Path) -> dict:
    """Read both files and score them. Every failure names the file it is about."""
    labels = parse_sheet(sheet_path.read_text("utf-8"))
    meta, key = parse_key(key_path.read_text("utf-8"))
    return score(labels, key, meta)
