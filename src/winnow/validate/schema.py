"""The labelling sheet's schema and the scoring rule, fixed before any labelling.

MILESTONES milestone 2 asks for 200 stripped results, sampled stratified by rule,
labelled blind, with **≥90% confirmed once-only** in aggregate and **per-rule
precision reported separately**. Every judgement call that turns a pile of filled-in
labels into a pass or a fail is written down here, in one file, and committed
before a single result is labelled — because each one of them could otherwise be
settled afterwards in whichever direction made the number look better.

Three of them are load-bearing:

**`unsure` counts against precision.** It sits in the denominator and not in the
numerator. The claim under test is "this result was safe to remove", and a
labeller who could not confirm it has not confirmed it. Dropping `unsure` from the
denominator would let a rule reach 90% by being confusing.

**A blank label is not a label.** A sheet with unfilled items is refused rather
than scored over what was filled. Partial completion is not a smaller sample; it
is a sample whose missing entries correlate with how hard the items were.

**Below 90% is a mechanical call, whatever `n` is.** A rule's own precision below
the bar disables it by default (`rules.DISABLED_BY_DEFAULT`). Where `n` is small
the point estimate is wide, and the note saying so is information — the way to
change the call is another label, not another reading of the same one.
"""

from __future__ import annotations

# Bumped when the sheet's shape or the scoring rule changes. The scorer refuses a
# sheet whose version it does not know, so a sheet filled in under one rule can
# never be scored under another.
SCHEMA_VERSION = 1

# The three things a labeller may write. Nothing else parses.
ONCE_ONLY = "once-only"
NEEDED_AGAIN = "needed-again"
UNSURE = "unsure"
LABELS = (ONCE_ONLY, NEEDED_AGAIN, UNSURE)

# MILESTONES milestone 2, and its kill criteria.
PRECISION_BAR = 0.90
KILL_BELOW = 0.80

LABEL_HELP = {
    ONCE_ONLY: (
        "Nothing after this point needed the content of this result. Its being "
        "gone would not have changed what the assistant did next."
    ),
    NEEDED_AGAIN: (
        "Something after this point used this result's content — quoted it, "
        "acted on a detail only it carried, or would plainly have had to re-run "
        "the tool without it."
    ),
    UNSURE: (
        "You cannot tell from the turns shown. Use it freely; it is not a "
        "failure to use, and it counts against the rule rather than for it."
    ),
}

SCORING_RULE = """\
Precision, per rule and in aggregate, is

    confirmed once-only / all labelled items

`unsure` is in the denominator and not the numerator: the claim under test is
that the result was safe to remove, and an item nobody could confirm has not been
confirmed.

The bar is 90%. A rule whose own precision is below it is disabled by default
even when the aggregate passes (MILESTONES milestone 2). Aggregate precision
below 80% stops the project; between 80% and 90% the rules get one revision pass
and one re-label, and no more.

Every item must carry one of once-only / needed-again / unsure. A sheet with a
blank item is refused rather than scored over the rest of it.

A rule that no item was drawn for has no precision — not 0% — and is reported as
not sampled.\
"""

# What the sheet warns about at the top. SPEC §10: transcripts routinely carry
# credentials pasted into a Bash command, and this sheet quotes tool arguments and
# result content verbatim because a labeller cannot judge what they cannot read.
SENSITIVITY_WARNING = """\
This sheet quotes tool arguments and tool output verbatim from real transcripts.
SPEC §10 records that transcripts routinely contain credentials pasted into a Bash
command. Treat this file as sensitive: it is the one artefact in this project that
holds transcript content outside the transcript. Do not commit it, do not paste it
into an issue, and delete it once the run is scored.\
"""
