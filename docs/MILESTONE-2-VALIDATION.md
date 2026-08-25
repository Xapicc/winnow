# Milestone 2 — the three criteria that need production data

> **Written for a session with no memory of the one that built the harnesses.**
> Everything you need is below: the commands, in order, with the corpus each needs, the
> bar each has to clear, where the results go, and what to do when one is missed. You
> should not have to read the code to run it, and you should not have to guess at a
> threshold — every number here is quoted from
> [MILESTONES.md](MILESTONES.md) or [SPEC.md](SPEC.md) §9 and not from anybody's
> recollection of them.

Milestone 2 is **built but not passed**. Every acceptance criterion a test suite can settle is
checked in `uv run pytest`. Three of its definition-of-done items cannot be settled that way, and
this document is how they get answered:

| # | Criterion | Needs | Bar |
| - | --------- | ----- | --- |
| 1 | Every fork resumes | real transcripts, real model calls | **100 forks, 0 failures** |
| 2 | Stripped results are once-only | real transcripts, a human labeller | **≥90% aggregate**, and per rule |
| 3 | Accumulated forks' disk cost | seven days of elapsed time | measured, not estimated |

Nothing in `uv run pytest` reads `~/.claude/projects/` or spawns `claude`, deliberately.
A green suite is not one of these three answered, and was never meant to look like it.

---

## Before you start

```sh
uv sync
uv run pytest          # the criteria that are already settled; none of the three below
```

Then decide **one corpus** and use it for all three. `~/.claude/projects` is the obvious
choice on the operator's machine. Everything below takes it as `--corpus`; nothing has a
default, because a validation run that silently pointed at the wrong tree would produce
numbers that look exactly like the right ones.

Put the outputs somewhere outside the repository. One of them — the labelling sheet —
carries transcript content verbatim, and [SPEC.md](SPEC.md) §10 records that transcripts
routinely contain credentials pasted into a Bash command. **Do not commit the sheet.** The
sheet says this at the top of itself as well.

```sh
export CORPUS=~/.claude/projects
export OUT=~/winnow-validation        # not inside this repository
mkdir -p "$OUT"
```

---

## 1. The resume test — 100 forks, 0 failures

**Criterion.** *Given a forked session, when `claude --resume <new-id> -p 'reply OK'` runs,
then it exits 0.* SPEC §9's guardrail is **100 forks, 0 failures**. Not a percentage: one
unresumable fork is a kill condition unless a same-day change to guard G5 fixes it.

**Prove the plumbing first.** This forks and writes exactly as the real run does and
substitutes only the model call, so it is the cheap way to find out that your corpus is
wrong or that everything refuses:

```sh
uv run python -m winnow.validate resume \
  --corpus "$CORPUS" \
  --ledger "$OUT/resume-dry.jsonl" \
  --results "$OUT/resume-dry.json" \
  --forks 5 --dry-run
```

A dry run still writes forks — that is the plumbing being proved. They are ordinary files
in the same project directory as their sources; delete them by hand afterwards, or leave
them and let step 3 count them.

**Then the real thing.** This spawns a model per fork and costs real money:

```sh
uv run python -m winnow.validate resume \
  --corpus "$CORPUS" \
  --ledger "$OUT/resume.jsonl" \
  --results "$OUT/resume.json" \
  --forks 100
```

- **Results** land in `$OUT/resume.json`, and the readout goes to stdout.
- **Every attempt** is appended to `$OUT/resume.jsonl` as it happens. Re-running the same
  command with the same ledger picks up where it stopped, so an interrupted run costs you
  nothing but the attempt it was in the middle of.
- **Exit code 0** means the guardrail was met. **Exit 4** means it ran and the bar was
  missed. Exit 1 is a usage error.

**Reading the result.**

- *Failures.* Each is named with its source path, its fork path and the tail of what
  `claude` printed. The fork is still on disk — winnow adds files and never removes them —
  so `winnow inspect <fork-path>` and a diff against the source are both available.
- *Refusals.* A session winnow would not fork produced no fork, so it neither passed nor
  failed; it shrank the population. The readout breaks refusals down by guard.
- *Shortfall.* If refusals leave you under 100 forks, the guardrail is **not met**, and the
  summary says so. See the next paragraph before you reach for a flag.

**The trap.** The guard that will refuse most often is `cold-age`, because a corpus of a
machine in daily use is full of sessions that were touched recently.
[MILESTONES.md](MILESTONES.md) is explicit:

> The refusal path proves unusable in practice — if `--min-cold-age` blocks nearly every
> real resume, the tool has no population and should be abandoned rather than have its
> guard loosened. **Loosening the guard to get results is itself a kill condition**,
> because it discards the only argument that answers the caching objection.

So `--min-cold-age` exists on the command and you must not lower it to make the number.
If the corpus cannot supply 100 cold sessions, the correct outputs are a wider corpus or a
report that the population is not there — not a smaller threshold.

---

## 2. The blind label — 200 results, ≥90% once-only

**Criterion.** *Given 200 stripped results sampled stratified by rule, when the operator
labels them blind against the surrounding turns, then ≥90% are confirmed once-only.*
Per-rule precision is reported separately, and **a rule below 90% on its own is disabled by
default even if the aggregate passes**.

**The schema and the scoring rule are already committed**, in
`src/winnow/validate/schema.py`, and were committed before this sheet existed so that the
bar cannot move once the numbers are in. Read it before you label. The three parts that
decide things:

- `unsure` is in the **denominator and not the numerator**. The claim under test is that
  the result was safe to remove; an item nobody could confirm has not been confirmed.
- A **blank item refuses the whole sheet**. The items people leave blank are the hard ones.
- Below 90% is a **mechanical call**, whatever `n` is. A thin sample is flagged, and the
  way to change the call is another label, not another reading of this one.

**Draw the sample.**

```sh
uv run python -m winnow.validate sample \
  --corpus "$CORPUS" \
  --sheet "$OUT/sheet.md" \
  --key "$OUT/key.jsonl" \
  --target 200 --seed 0
```

Tier CB by default, because that is the tier every number in this project is quoted at. The
draw is deterministic for a given corpus and seed, so the same sheet can be regenerated.

If it comes up short of 200, it says so and by how much. **Widen the corpus rather than the
tier**: a sample topped up with tier-A hits is not a sample of what tier CB does.

**Label it.** Open `$OUT/sheet.md` in an editor. **Do not open `$OUT/key.jsonl`** — it holds
the rule that fired for each item, and a label that has seen it is not blind. For each item,
write one of `once-only`, `needed-again` or `unsure` after `label:`. The question is on the
sheet, and it is: *was the content of this tool result needed again after the point it was
produced?*

**Score it.**

```sh
uv run python -m winnow.validate score \
  --sheet "$OUT/sheet.md" \
  --key "$OUT/key.jsonl" \
  --results "$OUT/label-score.json"
```

Exit 0 if the aggregate is at or above 90% **and** no individual rule is below it; exit 4
otherwise. The readout gives the aggregate, a per-rule table, and the verdict in words.

**Acting on the result.** If any rule is below the bar, the scorer prints the exact setting:

```sh
export WINNOW_RULES_OFF=B2      # for example
```

That switches the rule off by default for `plan` and `fork`, which then say so in their
readout and print the `--rule` that turns it back on. Make it permanent by setting
`winnow.rules.DISABLED_BY_DEFAULT` to the same set — it ships empty, and the commit that
changes it should carry the measured precision in its message, because a rule disabled
without a number behind it is the tool asserting something nobody measured.

**Then commit the results.** [MILESTONES.md](MILESTONES.md)'s definition of done asks for
"the labelling sheet and its results committed". Commit `label-score.json` and the key.
**Do not commit the sheet itself** — it is the one artefact holding verbatim transcript
content, and the definition of done does not outrank SPEC §10. Say in the commit message
that the sheet was withheld and why, so the omission is a decision on the record rather
than a gap.

---

## 3. The disk cost — measured over a week

**Criterion.** From the definition of done: *the disk cost of accumulated forks measured
over a week rather than estimated.*

One observation is not a week, and the script will not pretend otherwise — it reports a
rate only once the series spans seven days or more. Take the first observation now:

```sh
uv run python -m winnow.validate disk \
  --corpus "$CORPUS" \
  --series "$OUT/disk-series.jsonl" \
  --ledger "$OUT/resume.jsonl" \
  --results "$OUT/disk.json"
```

`--ledger` is optional and is what pairs each fork to the session it came out of; a fork's
session id is a UUIDv5 and cannot be run backwards. Without it the pooled figure is still
right and the per-session breakdown is empty.

Then run the identical command again **at least seven days later**, against the same series
file. The difference between the first and last observation is the number the definition of
done asks for. Run it in between as often as you like; more points make the series better
and none of them are load-bearing on their own.

Nothing in this repository should carry a disk-cost figure until that second run has
happened. If you find one, it was fabricated.

---

## The kill criteria, so you do not have to go looking

Verbatim from [MILESTONES.md](MILESTONES.md), "Stop at milestone 2 if":

> - Aggregate rule precision on the 200-sample label is **below 80%**. Between 80% and 90%
>   the rules get one revision pass and one re-label, no more.
> - Any fork produces an unresumable session that is not fixed by a same-day change to G5.
> - The refusal path proves unusable in practice — if `--min-cold-age` blocks nearly every
>   real resume, the tool has no population and should be abandoned rather than have its
>   guard loosened. **Loosening the guard to get results is itself a kill condition**,
>   because it discards the only argument that answers the caching objection.

What that means at each of the three bars:

| What happened | What to do |
| --- | --- |
| Aggregate precision **< 80%** | **Stop.** Milestone 2 is killed. Do not revise and re-label; that allowance is for the 80–90% band only. Write up the number and what it says about the rule set. |
| Aggregate **80–90%** | One revision pass over the rules, one re-label with a fresh seed. Not two. If the second label is still under 90%, that is the stop. |
| Aggregate **≥90%**, one rule under | Not a kill. Disable that rule by default, record the number, carry on. |
| A fork does not resume | One same-day attempt at a G5 fix. If G5 cannot be made to cover it that day, **stop**. |
| Under 100 forks because of `cold-age` | **Do not lower `--min-cold-age`.** Widen the corpus. If a wider corpus still has no population, the refusal path is unusable and that is a stop in its own right. |
| A harness error rather than a fork failure | A bug in winnow or in `winnow.validate`, not a milestone result. Fix it and re-run; the ledger means you only re-run what broke. |

Whatever the outcome, the two documents to amend are [MILESTONES.md](MILESTONES.md)'s
"Where this stands" note and [README.md](../README.md)'s status table. Both currently say
these three are unvalidated, and both should say what they turned out to be — including,
and especially, if the answer stops the project. The project's own definition of done says
the documents "are still true, or have been amended where the measurements contradicted
them", and adds: *a definition that survives contact with data unchanged usually means
nobody checked.*

---

## Command summary

```sh
export CORPUS=~/.claude/projects
export OUT=~/winnow-validation && mkdir -p "$OUT"

uv sync && uv run pytest

# 1. resume — plumbing first, then the real run
uv run python -m winnow.validate resume --corpus "$CORPUS" \
  --ledger "$OUT/resume-dry.jsonl" --results "$OUT/resume-dry.json" \
  --forks 5 --dry-run
uv run python -m winnow.validate resume --corpus "$CORPUS" \
  --ledger "$OUT/resume.jsonl" --results "$OUT/resume.json" --forks 100

# 2. label — draw, fill in $OUT/sheet.md blind, score
uv run python -m winnow.validate sample --corpus "$CORPUS" \
  --sheet "$OUT/sheet.md" --key "$OUT/key.jsonl" --target 200 --seed 0
uv run python -m winnow.validate score --sheet "$OUT/sheet.md" \
  --key "$OUT/key.jsonl" --results "$OUT/label-score.json"

# 3. disk — now, and again in seven days against the same series
uv run python -m winnow.validate disk --corpus "$CORPUS" \
  --series "$OUT/disk-series.jsonl" --ledger "$OUT/resume.jsonl" \
  --results "$OUT/disk.json"
```

Exit codes: **0** success, **1** usage error, **4** the measurement ran and the bar was
missed. Exit 4 rather than 0 so that a failed guardrail is not one `&&` away from reading
as a pass.
