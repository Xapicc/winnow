# How each recommended change is shown to have worked, or to have failed

Modelled on [docs/MILESTONE-2-VALIDATION.md](../../docs/MILESTONE-2-VALIDATION.md), which is the
right shape and the reason this document exists: **every bar below is fixed here, before any
number is in.** A bar settled after the numbers arrive is not a bar. Where a threshold is quoted
it is quoted from SPEC §9 or MILESTONES and named as such; where it is new to this document it is
argued in the same paragraph, so that a later reader can disagree with the argument rather than
guess at the intent.

> **The gap this fills.** `docs/MILESTONES.md` does not mention the intake filter, the proxy,
> `winnow savings`, `winnow trial` or `ANTHROPIC_BASE_URL` — **checked, zero occurrences**. The
> component was built outside the milestone plan, is argued only in COZEMPIC §3.5, and has never
> been given a criterion it could fail. Six of the seven registers below are the first bars it
> has had.

---

## What a green suite settles, and what it does not

Seven of the twelve items in [26-implementation-sketch.md](26-implementation-sketch.md) are
settled entirely by `uv run pytest` and appear nowhere below:

| Item | Settled by |
| --- | --- |
| 1 the deferral boundary | `test_a_deferred_result_is_never_inside_the_write_region` |
| 2 G4 and the `--min-bytes` floor | `test_a_pointer_that_would_inflate_is_refused` |
| 3 breakpoints on `system` and `tools` | `test_a_breakpoint_on_tools_counts_against_the_cap` |
| 4 (reader half) one meaning for `bytes_dropped` | `test_two_readers_agree_on_one_ledger` |
| 5 rule selection reaches the wire | `test_a_disabled_rule_does_not_fire_on_the_wire` |
| 10 the property test | itself |
| 11 the golden | itself |

`docs/MILESTONE-2-VALIDATION.md` states the discipline and it holds here: *"[n]othing in
`uv run pytest` reads `~/.claude/projects/` or spawns `claude`, deliberately. A green suite is
not one of these three answered, and was never meant to look like it."*

---

## Before you start

```sh
export CORPUS=~/.claude/projects
export OUT=~/winnow-filter-validation        # not inside this repository
mkdir -p "$OUT"

export WINNOW_FILTER=1
python -m winnow filter --ledger "$OUT/filter.jsonl" --verbose
# and in the client's environment:
export ANTHROPIC_BASE_URL=http://127.0.0.1:8789
```

**One ledger for all of it**, and one that is not the operator's normal `~/.winnow/filter.jsonl`,
so a validation run can be thrown away without losing the production record.

**Do not commit any output of register V1.** The labelling sheet carries transcript content
verbatim and SPEC §10 records that transcripts routinely contain credentials pasted into a Bash
command. The sheet says so at the top of itself. The score and the key are committable; the sheet
is not.

---

## The register

| # | Criterion | Needs | Bar | Kill |
| - | --------- | ----- | --- | ---- |
| **V1** | The filter's removals are once-only **in the filter's position** | ≥200 distinct removals in a ledger, a human labeller | **≥90% aggregate and per rule** (SPEC §9) | **<80% aggregate** stops the filter, not only a rule (MILESTONES) |
| **V2** | Deferring by turn does not raise the re-fetch rate | filtered sessions before and after item 6 | **<1 stripped-then-re-read event per session at the median** (SPEC §9) | **>3 at the median** either side: the rule set is wrong, not the deferral |
| **V3** | The floor at 256 is net-positive on a real bill | `winnow trial`, two interleaved arms | **net $/session not lower** at 256 than at 2,048, and per-rule precision on 256–2,048 results within **5 points** of the aggregate | precision on that band **below 85%** → revert to 2,048 |
| **V4** | The filter does not bring auto-compaction forward | two live sessions, the kill switch | the context indicator **tracks `bytes_dropped` within 10%** | it does not track, **and** compaction fires earlier by **>5% of turns** → the exclusion is costing the whole benefit |
| **V5** | The mechanism does what §3.5 says on a real cache | `winnow trial`, filtered and unfiltered arms | `cache_creation_input_tokens` per request **not higher** in the filtered arm | **>10% higher** → the filter is breaking the prefix; kill switch on until understood |
| **V6** | The health signal has a calibrated baseline | one week of heartbeat lines | claimed-result rate within **±50%** of the corpus's 7.29% | none — a deviation is a fault to investigate, not a stop |
| **V7** | The sub-agent glob explains the unjoinable ledger lines | one existing ledger, re-read | the unjoinable count **falls** | none — if it does not move, the cause is elsewhere and that is the result |
| **V8** | The ledger's growth does not need rotation | two observations seven days apart | **under 100 KB/day** | over **1 MB/day** → rotation is back on the table |

---

## V1 — the blind label, in the filter's position

**Criterion.** Given 200 removals sampled stratified by rule from a ledger the running filter
wrote, when the operator labels them blind against the surrounding turns, then ≥90% are
confirmed once-only, and no rule is below 90% on its own.

**Why it is not the milestone 2 label.** `winnow.validate sample` draws from transcripts at tier
CB and asks *"was the content of this tool result needed again after the point it was
produced?"*. For the pruner that question is asked about a result in a session that has already
finished. For the filter it is asked about a result **one request old, on a live conversation,
with the model still mid-task**. The same rule can be right in one position and wrong in the
other, and B2 — 96.07% of the filter's reach — is exactly where they would come apart.

**What has to be built.** `winnow.validate sample` has no ledger mode. The change is a
`--from-ledger PATH` that draws the sample from the `dropped` entries of a real ledger, joins each
to its transcript on `request_id`, and renders the same sheet with the same blind key.
`src/winnow/validate/` already has the sampler, the sheet, the scorer and the schema; the schema
is committed and `validate/schema.py` fixes the scoring rule, so the bar cannot move once the
numbers are in.

**The population is reachable.** **Measured here, 2026-08-27**, over 867 main-session
transcripts: 4,715 candidates across 584 sessions that have any — a median of **5 per session**,
p90 **19**, maximum **54**. So 200 distinct removals is about **40 sessions of ordinary work** at
the median rate — 25 at the mean of 8.1 — with the filter in the path. That is one to two weeks,
not a research programme.

**Acting on the result.** MILESTONES' table applies unchanged: ≥90% with one rule under is not a
kill, it disables that rule by default — **and that remediation only works if
[15-option-honour-rule-selection.md](15-option-honour-rule-selection.md) has landed.** Item 5 of
the sketch is therefore a precondition for this register, not a parallel task. Below 80% stops
the filter: not the milestone, because it has none, but the component. That is a stronger
consequence than the pruner's equivalent and it is the right one, because the filter removes
bytes from a request the model is about to read and keeps no copy.

---

## V2 — the re-fetch rate, before and after the deferral change

**Criterion.** SPEC §9's guardrail, pointed at the filter: *"[s]tripped-then-re-read events < 1
per session at the median"*.

**The measurement**, which needs no new code beyond a script: in the transcripts of sessions the
ledger covers, count calls whose `(name, canonical_input(input))` matches the `(name, input)` of
a `tool_use` whose `tool_use_id` the ledger recorded under `dropped` **on the first request that
carried it**. `rules.canonical_input` (`rules.py:304-310`) is the comparison C2 already uses.

**Run it twice**: once with the filter as it is, once after item 6. The population that should
move is the 711 results §04 measures in a non-final slot of a batch — **15.14% of the filter's
reach, 3,516,979 bytes** — and the prediction is that the rate falls on exactly those.

**The bar is on both runs.** Under 1 per session at the median either way, and the change is
justified by correctness rather than by the rate. Over 3 at the median either way, the problem is
that the rules are removing things the session needs, which is V1's question and not this one.

**What cannot be measured this way, stated so nobody claims it later.** The counterfactual has
never happened — the filter has not run over the historical corpus, so no result was ever taken
away before the model read it and there is no baseline re-fetch to compare against. §04's $107.67
figure is a bound on what the current behaviour could cost, not an observation, and it must not
be restated as one.

---

## V3 — the floor at 256

**Criterion.** The change is net-positive on a real bill, and the results it newly admits are no
less once-only than the ones already taken.

**Two halves and both are required.**

*The money.* `winnow trial` with two arms, interleaved:

```sh
winnow trial arm --label floor-2048 --note "filter --min-bytes 2048"
# ... a period of work ...
winnow trial arm --label floor-256  --note "filter --min-bytes 256"
# ... a period of work ...
winnow trial report --corpus "$CORPUS" \
  --tasks floor-2048=N --tasks floor-256=M
```

`--tasks` is repeatable and takes `ARM=N` (`cli.py:762-764`); without it *"$/task is blank and
the report says why"*, and $/task is the only column SPEC §9 lets decide anything.

Interleaved rather than sequential, because `winnow trial`'s whole design is that *"the
difference between them is noise rather than the week"* (`cli.py:726`, and `trial.py:21`:
*"[i]nterleaving the arms is what makes that noise rather than bias"*). The corpus
prediction is **+31% on net at *T* = 224 and +30% at *T* = 20** (§07's table, 696.1 M against
530.4 M and 87.9 M against 67.5 M); the bar is only that 256 is not
*lower*, because a two-arm trial over a few weeks of one operator's work cannot resolve 32% and
pretending it can is the error COZEMPIC §3.1, §3.4 and §3.5.2 each record.

*The precision.* V1's sheet, stratified by **size** as well as by rule — one extra column in a
sheet that has to be drawn anyway. If results between 256 and 2,048 bytes label below 85%, the
floor goes back to 2,048 and the reason is recorded. This is the column
[07-option-per-tool-thresholds.md](07-option-per-tool-thresholds.md) names as the answer to its
own strongest objection: *"whether a 300-byte `git status` was needed more often than a 30 KB
one"*.

**Do not run V3 before V1.** The size stratification is a column on V1's sheet and drawing two
sheets doubles the labelling cost for nothing.

---

## V4 — does the filter bring auto-compaction forward

The highest-value unanswered question about this component that is not milestone 3, and
[13-option-count-tokens-parity.md](13-option-count-tokens-parity.md) states why: if Claude Code
decides when to compact from a quantity reflecting the *unfiltered* conversation, the filter buys
+3.76% of the bill and pays for it with an earlier irreversible summarisation that §3.5's cost
model does not price at all. SPEC §2 puts one compaction at **13 points of task success and 66
points of cache hit rate**.

**Two runs, no code.**

1. `winnow filter --verbose --ledger "$OUT/compaction-on.jsonl"`, work one session past 150k of
   context, and record the turn index at which the CLI's context indicator crosses each decile
   and at which auto-compact fires.
2. The same task with `touch ~/.winnow/filter-off`. The kill switch keeps the proxy relaying and
   stops the rewriting (`proxy.py:126-156`), **so the only difference between the two runs is the
   rewrite** — same process, same socket, same headers.

**The bar.** If the indicator tracks `bytes_dropped` within 10%, the count is derived from what
the API billed and the exclusion costs nothing; record it and close option K. If it does not
track *and* compaction fires more than 5% of turns earlier in run 1, the filter is shortening the
session in the unit that triggers compaction while lengthening it in the unit that gets billed,
and that belongs in every readout the tool produces — starting with a `--verbose` line saying
*"this request went out N bytes smaller than the conversation the client is holding"*, which
§13 already sketches and which costs one `print`.

**The 5% is new to this document and here is the argument for it.** A session's turn budget is
the quantity at stake; the filter removes 8.49% of message content, so a count-driven trigger
would move compaction by something of that order. A threshold at 5% is below what the mechanism
would produce if the hypothesis is true and above the noise of two hand-run sessions. It is a
weak bar and it is testing a binary, not estimating an effect.

---

## V5 — the mechanism, on a real cache

**Nothing in this repository has ever observed the filter's effect on a cache.** COZEMPIC §3.5
is a corpus simulation, `winnow savings` prices a ledger with the same model, and §3.5.1 says so
in its own words: *"[t]he figure is modelled, not billed."*

**The measurement.** `winnow trial`, filtered and unfiltered arms interleaved, reading
`message.usage` off the transcripts. The quantity that matters is not the saving — that is the
counterfactual nothing can observe — but the **absence of a regression**:
`cache_creation_input_tokens` per request in the filtered arm should not exceed the unfiltered
arm's, because every write the filter causes is a write the baseline was going to pay.

**The bar.** Not higher. **The kill: more than 10% higher, and the kill switch goes on until
somebody understands why.** A rise in cache writes is the signature of a broken prefix, which is
the one failure this component exists to prevent and the one that
[17-option-cache-write-invariant.md](17-option-cache-write-invariant.md) found reachable through
`--keep-newest 2`.

**Two things this register also pins**, because both are assumptions nobody has checked and both
would show up here first:

- **I11 — the cache key is over parsed content, not over the JSON encoding.** On a changed
  request the filter re-serialises the whole body in Python's default style; on an unchanged one
  it forwards the client's bytes verbatim ([23](23-option-golden-wire-fixture.md)). If the key
  were sensitive to encoding, the filtered arm's write tokens would be enormous, not 10% high.
- **The 20-block lookback.** `[[Prompt Caching]]` (high) puts the window at 20 blocks and the
  filter writes at a position no later request ever marks again, so the read runs entirely
  through the walk ([18](18-option-price-the-breakpoint-move.md)). **Measured here**, the largest
  turn in this corpus is **15 content blocks** and 89.5% are two or three, so the headroom is
  five blocks in the worst observed case. A workload that fans out further than this one would
  hit it, and V5 is where it would appear.

---

## V6, V7, V8 — the three that are calibration rather than judgement

**V6 — the health signal's baseline.** After one week of heartbeat lines, compare against the
corpus: **7.29% of `tool_result` blocks claimed, 6.5% of turns producing a ledger line, 67.4% of
sessions with at least one candidate [measured here]**. ±50% is a wide band and deliberately so —
it is a fault detector, not an estimator, and the four failures
[21-option-health-signal.md](21-option-health-signal.md) names all produce **zero**, which no
band contains.

**V7 — the sub-agent glob.** Change `savings.find_transcripts` to `**/*.jsonl` and re-read the
same ledger. COZEMPIC §3.5.2 reports *"34 priced, 15 unjoinable, 0 unpriceable"*; the check is
whether the 15 falls. **This is a measurement, not a bar** — if it does not move, the cause is
the other candidate ([11](11-option-read-the-response.md): a failed request leaves a ledger line
and no assistant record, because the proxy writes the line when the response *headers* arrive,
`proxy.py:228-229`) and that is worth knowing.

**V8 — the ledger's growth.** Two `du -b "$OUT/filter.jsonl"` observations at least seven days
apart, in the shape `docs/MILESTONE-2-VALIDATION.md` §3 already prescribes for forks: *"[o]ne
observation is not a week."* The simulation predicts about **5 KB per changed request** and
**4.7 MB for 867 sessions**; the bar is under 100 KB/day, which is twenty changed requests an
hour sustained, and the kill is over 1 MB/day. Nothing in this repository should carry a
ledger disk-cost figure until the second observation has happened. **If you find one, it was
fabricated.**

---

## What none of this answers

**I10, and every option in this set inherits it.** Whether a model does worse work when a
pointer sits where an answer was. SPEC §9 puts it in milestone 3 — ≥40 held-out tasks × ≥3 runs
per cell, a rubric written before any run, a ±5-point equivalence bound, the task set frozen and
hashed first — and milestone 3 has not started. V1 measures whether a *human* thinks a removal
was safe, which is a different and weaker question, and MILESTONES already treats it as the
best available.

**The 39.5%.** SPEC §5's mass — `Read` bytes belonging to files a run never mentions again —
is not reachable by any register here and not by any option in this set. It is named so that no
number below is read as progress toward it.

---

## Command summary

```sh
export CORPUS=~/.claude/projects
export OUT=~/winnow-filter-validation && mkdir -p "$OUT"
uv sync && uv run pytest                       # items 1,2,3,4,5,10,11 — and nothing below

# run the filter for ~40 sessions to fill the sample
export WINNOW_FILTER=1
python -m winnow filter --ledger "$OUT/filter.jsonl" --verbose

# V1  (needs `winnow.validate sample --from-ledger`, which does not exist yet)
uv run python -m winnow.validate sample --from-ledger "$OUT/filter.jsonl" \
  --corpus "$CORPUS" --sheet "$OUT/sheet.md" --key "$OUT/key.jsonl" --target 200 --seed 0
uv run python -m winnow.validate score --sheet "$OUT/sheet.md" \
  --key "$OUT/key.jsonl" --results "$OUT/label-score.json"

# V3, V5  (interleave the arms; do not run them back to back)
winnow trial arm --label filter-off  --note "kill switch on"
winnow trial arm --label floor-2048  --note "filter --min-bytes 2048"
winnow trial arm --label floor-256   --note "filter --min-bytes 256"
winnow trial report --corpus "$CORPUS" --tasks filter-off=N --tasks floor-256=M

# V4  two live sessions, the second with:  touch ~/.winnow/filter-off
# V7  one line in savings.find_transcripts, then:  winnow savings --ledger "$OUT/filter.jsonl"
# V8  du -b "$OUT/filter.jsonl"   now, and again in seven days
```

Exit codes follow `winnow.validate`: **0** success, **1** usage error, **4** the measurement ran
and the bar was missed — exit 4 rather than 0 *"so that a failed guardrail is not one `&&` away
from reading as a pass"*.
