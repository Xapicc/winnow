# winnow — milestones, definition of done, kill criteria

> **Status of this document, 2026-08-23.** Restored verbatim after the Cozempic merge (`210b026`)
> deleted it. The plan below is unchanged and still the plan, with one correction it cannot make
> itself: **milestone 1 is now cheaper and milestone 3 is now dearer than it says.** Cheaper,
> because `cozempic diagnose` already reads `usage` off disk, so the instrument has a working
> precedent to copy rather than invent, and because milestone 3's mandatory recency arm exists as
> code (`tool-result-age`, [COZEMPIC.md](COZEMPIC.md) §1) rather than needing to be written.
> Dearer, because the vendored tool supplies an arm the plan did not budget for: a shipped pruner
> to measure against, which is a more informative comparison than a synthetic one and costs
> another cell. Neither changes the kill criteria, and the kill criteria are the part of this
> document that matters.
>
> One acceptance criterion is now blocked outright rather than merely unwritten: nothing in this
> container can run the test suite. See [USAGEFOUNDRY.md](USAGEFOUNDRY.md) §7.

Appetite: **two weeks of one person's work**, taken as ten working days. Fixed time,
variable scope: if the work does not fit, the last milestone is cut, not extended.
[DECISIONS.md](DECISIONS.md) §5 already records that milestone 3 is the part most likely
not to fit, and says so before the fact rather than after.

Milestones are ordered by **risk retired per hour**, not by what is pleasant to build.
Milestone 1 is a measurement that is allowed to end the project on day three.

| # | What it is | Share | Independently useful? |
| - | ---------- | ----- | --------------------- |
| 1 | `winnow inspect` — the instrument | 30% (3 days) | Yes. Answers "what is this session carrying" with no write path at all |
| 2 | `winnow fork` + `winnow recover` — the actuator | 30% (3 days) | Yes. A reversible strip with a recovery path, usable by hand before any A/B exists |
| 3a | The frozen task set and the control arm | 10% (1 day) | Yes. A resume-task benchmark for this install exists nowhere and is reusable by anything else that touches context |
| 3 | `winnow bench` — the live-model A/B | 30% (3 days) | Yes, and it is the only deliverable that answers the question the project was opened for |

---

## Milestone 1 — the walking skeleton: `winnow inspect`

**What runs end to end.** A single command reads one real transcript from
`~/.claude/projects/`, parses every record type it contains, runs the full tier C/B/A rule
set over the `tool_result` blocks, reads the `usage` fields, and prints a composition
readout plus the cache arithmetic. It writes nothing anywhere. Every layer the finished
tool needs — JSONL parsing, record-type dispatch, the tool-call pairing index, the rule
engine, the byte accounting, the cost model — is exercised on the first day, which is the
whole point of doing this first. The only layer it does not touch is the writer, and that
is deliberate: milestone 1 has to be able to say "do not build the writer".

**Acceptance criteria.**

- *Given* any of the 563 transcripts on this machine, *when* `winnow inspect <session>`
  runs, *then* it exits 0, prints a readout, and reports the count of records it did not
  recognise — never crashing on an unknown record type and never silently dropping one.
- *Given* the 161 sessions over 400 KB, *when* `winnow inspect --json` runs over all of
  them, *then* the pooled tier-CB share reproduces **22.6% within ±3 points** and the
  median **21.6% within ±3 points** (SPEC §9). Reproducing the ad-hoc measurement with
  real code is the check that the measurement was not an artefact of the throwaway script
  that produced it.
- *Given* a session whose rules and thresholds were **not** used to write the rules,
  *when* the same run happens on that held-out half, *then* the shares hold to the same
  bound. Split the corpus before looking at the second half.
- *Given* a session that was resumed more than an hour after its previous request, *when*
  `inspect` reports the cache arithmetic, *then* it prints
  `cache_creation_input_tokens` on the first post-resume assistant record and states
  whether the cache was cold. **This is the falsification test for Q1** ([DECISIONS.md](DECISIONS.md) §6)
  and it is the first thing to run, because if resumes are not paying a full write anyway,
  the project's economic case is gone and milestones 2 and 3 should not start.
- *Given* a session containing a `compact_boundary`, *when* `inspect` runs, *then* it says
  so on its own line rather than folding the pre-boundary records into the totals unmarked.
- *Given* the same transcript twice, *when* `inspect --json` runs, *then* the output is
  byte-identical.

**Definition of done for milestone 1** — every line has to be true, and "it printed
something plausible" is not one of them:

- [ ] Runs on all 563 local transcripts with 0 crashes and 0 unrecognised records dropped without a count.
- [ ] Pooled and median tier-CB shares reproduced on a held-out corpus within ±3 points, with the split recorded before the second half was read.
- [ ] The tool-call pairing index confirms the structural facts the design assumes: every `tool_use` matched to a `tool_result` except last-in-flight ones, and 0 orphan `tool_result`s. Numbers printed, not asserted.
- [ ] Q1 answered from disk in writing — cold or not cold, with the token counts that show it.
- [ ] Per-rule byte attribution, so a rule can be argued with individually rather than as part of a tier.
- [ ] `--json` output is stable and documented well enough that milestone 3 can consume it without changes.
- [ ] Tests: rule-level unit tests over hand-built records for each of C1, C2, C3, B1, B2, A1 and each guard G1–G5, plus one end-to-end test over a small fixture transcript committed to the repository. A rule with no test does not ship.
- [ ] The readout, run over this operator's own week, written up as prose — including whatever it says that contradicts this document.
- [ ] A stated go/no-go on milestone 2, with the number that decided it.

**What milestone 1 is allowed to conclude.** That the mass is not there, that the cache is
warm at resume, or that the rules fire on things a human reading the transcript says were
load-bearing. Any of those ends the project at 30% of the appetite, which is the cheapest
possible way to be wrong.

## Milestone 2 — the actuator: `winnow fork` and `winnow recover`

**What runs end to end.** `fork` writes a new transcript under a new session ID with
selected `tool_result` contents replaced by pointers; `recover` prints the original bytes
back from the untouched source; the forked session actually resumes in Claude Code.

**Acceptance criteria.**

- *Given* a session and `--tier CB --write`, *when* `fork` runs, *then* a new transcript
  appears, the original file's mtime and SHA-256 are unchanged, and every `tool_use` in
  the fork still has exactly one matching `tool_result` (G5, hard failure).
- *Given* a forked session, *when* `claude --resume <new-id> -p 'reply OK'` runs, *then*
  it exits 0. **100 forks, 0 failures** (SPEC §9 guardrail).
- *Given* a pointer in a forked transcript, *when* `winnow recover <session> <pointer-id>`
  runs, *then* it prints bytes whose SHA-256 matches the digest in the pointer.
- *Given* a session whose last request finished less than `--min-cold-age` ago, *when*
  `fork --write` runs, *then* it refuses with exit code 3 and names the reason. The
  economic argument is enforced by the tool, not left to the operator's discipline.
- *Given* a fork that would remove fewer bytes than the pointers it adds, *when* `fork`
  runs, *then* it refuses (G4). A tool that inflates the context it was asked to shrink
  must fail rather than proceed.
- *Given* 200 stripped results sampled stratified by rule, *when* the operator labels them
  blind against the surrounding turns, *then* **≥90% are confirmed once-only** (SPEC §9).
  Per-rule precision is reported separately; a rule below 90% on its own is disabled by
  default even if the aggregate passes.
- *Given* the same session and flags, *when* `fork` runs twice, *then* the two outputs are
  byte-identical (SPEC §10, determinism).

**Definition of done.** All of the above, plus: the labelling sheet and its results
committed; `--explain` documented with its secrets warning; a written decision on Q4
(sessions that have already compacted — refuse or proceed); and the disk cost of
accumulated forks measured over a week rather than estimated.

## Milestone 3a — the frozen task set

Separate from milestone 3 because it must be finished, hashed and committed **before any
arm runs**, and because it is worth having whether or not the A/B ever happens.

- ≥40 resume tasks drawn from real sessions on this install, each a real point where work
  stopped and was picked up later.
- A scoring rubric written before any run, scoring task success only — not style, not token
  count.
- Each task recorded with its source session, its cut point, and the state the resume
  starts from.
- The set committed and its SHA-256 recorded in the same commit as the rubric. Anything
  added after the first arm runs is a separate set with a separate hash, and is reported
  separately.

**Acceptance:** *Given* the frozen set, *when* the control arm runs unwinnowed with ≥3
runs per task, *then* a success rate and a cost distribution exist for every task, and the
run-to-run variance is reported. `[[The Cost Shape of an Agent Run]]` (medium) records up
to 30× variance on the same task, so a control arm that reports a mean without a spread is
not a control arm.

## Milestone 3 — `winnow bench`: the measurement the project exists for

**What runs end to end.** The harness spawns `claude -p` across arms — unwinnowed control,
tier C, tier CB, tier CBA, and a **recency-only arm reproducing Lindenbauer et al.'s
masking rule** — over the frozen task set, and reports task success and cache-adjusted
cost per successful task per arm with confidence intervals.

The recency arm is not optional. It is the published baseline the whole premise of
type-aware rules has to beat; without it, a positive result says only "stripping helps",
which is already known.

**Acceptance criteria.**

- *Given* the frozen task set and ≥3 runs per cell, *when* the arms complete, *then* task
  success for winnow-CB falls within the pre-registered **±5-point equivalence bound** of
  control, or the bound is missed and that is the result.
- *Given* the same runs, *when* cost is computed from `usage` × the published multipliers,
  *then* cache-adjusted cost per successful task for winnow-CB is **≥15% below** control,
  reported as a distribution.
- *Given* the same runs, *when* turns to completion are compared, *then* winnow arms are
  **not more than 10% above** control.
- *Given* the forked sessions, *when* reads of previously stripped paths are counted,
  *then* stripped-then-re-read events are **fewer than 1 per session at the median**.
- *Given* all arms, *when* results are reported, *then* the type-aware arms are compared
  against the recency arm explicitly, and the report states whether the classification
  earned its complexity.

**Definition of done.** Pre-registration written before the first arm; every arm's raw
`usage` data committed; results reported whichever way they fall, including "no
difference"; and one paragraph naming what the experiment could not settle. If Q3 (empty
`tool_result` versus placeholder) was affordable as an extra arm, it is reported too; if
not, it is named as skipped.

---

## Kill criteria

Decided now, while nobody is attached to the outcome.

**Stop at milestone 1 if:**

- The cache is **not** cold at a typical resume — Q1 comes back the wrong way. The economic
  case is then arithmetic-negative and no amount of rule quality repairs it.
- Tier CB does not reproduce above **10%** of message content on the held-out corpus. Below
  that, skim's own author's 0–15% estimate is the honest ceiling and the tool is not worth
  two weeks.
- The transcript format on the pinned CLI turns out to be materially different from what
  was measured — for instance, if what reaches the API is reconstructed rather than read
  from the file.

**Stop at milestone 2 if:**

- Aggregate rule precision on the 200-sample label is **below 80%**. Between 80% and 90%
  the rules get one revision pass and one re-label, no more.
- Any fork produces an unresumable session that is not fixed by a same-day change to G5.
- The refusal path proves unusable in practice — if `--min-cold-age` blocks nearly every
  real resume, the tool has no population and should be abandoned rather than have its
  guard loosened. **Loosening the guard to get results is itself a kill condition**,
  because it discards the only argument that answers the caching objection.

**Stop at milestone 3 if:**

- The control arm's run-to-run variance is so large that ≥3 runs per cell cannot separate a
  15% cost difference. Report the required sample size and stop; do not run an underpowered
  experiment and report its point estimate.
- Winnow-CB misses the ±5-point equivalence bound on task success. The tool is then
  measurably harmful and shipping it would be worse than never having built it.
- The type-aware arms do not beat the recency arm. In that case the correct output is a
  short write-up recommending Lindenbauer's rule, and the rule engine is deleted rather
  than kept "in case".

**Stop at any point if** somebody publishes the same head-to-head first. The value here is
the missing measurement, not the code; if the measurement arrives from elsewhere, read it
and stop.

## What "done" means for the project as a whole

- The four documents in this repository are still true, or have been amended where the
  measurements contradicted them. A definition that survives contact with data unchanged
  usually means nobody checked.
- `winnow inspect` runs on this operator's sessions and its readout is somewhere they will
  actually see it.
- A written answer exists to the question nobody has answered: what a deterministic,
  type-aware context strip costs in task quality on a real coding agent — with a number, a
  bound, and a named baseline it was measured against.
- Q1 through Q6 in [DECISIONS.md](DECISIONS.md) §6 are each either answered or restated as
  still open with what was learned. None of them is quietly dropped.
