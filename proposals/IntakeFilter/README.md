# IntakeFilter — a design proposal set for `winnow filter`

Twenty-one options for the intake filter — the local pass-through proxy on
`ANTHROPIC_BASE_URL` that drops a tool result before the API writes it to cache — followed by a
comparison, a recommendation, an implementation sketch and a validation register. Documentation
only. Nothing in `src/`, `tests/`, `plugin/` or `packaging/` was changed to write it, and no
option here has been implemented.

**The state of the argument, in three sentences.** The filter reaches 8.49% of message content
and is worth +3.76% of a $7,426.47 corpus bill on COZEMPIC §3.5's model, of which **96.07% is
rule B2 alone**; eleven capability options ask it to reach further and the recommendation takes
none of them, because the measurement that would license any widening is a 200-sample precision
label that is written, harnessed, unrun, and — on the day it runs — unable to reach the filter at
all, which has no `--tier`, no `--rule` and no `$WINNOW_RULES_OFF`. Ten structural options ask
instead what the mechanism as built should become, and writing one of them down was enough to
find that at `--keep-newest 2` the filter cache-writes a result and then rewrites it, paying
`1.9·S` on a warm prefix every turn from the third — the exact cost the component exists to
avoid. The recommendation is therefore five defects, three switches that already exist elsewhere
in the tree, one constant moved from 2,048 to 256, and two test artefacts: **reach 8.49% →
11.46%, and 15.14% of the filter's existing reach handed back to the model instead of taken from
it.**

## The files

### Frame

| | |
| --- | --- |
| [00-problem.md](00-problem.md) | What the filter reaches, what it does not, in three separate senses, and what "more" would have to mean |
| [01-constraints.md](01-constraints.md) | Ten constraints, K1 through K10. K1 decides most of the set and is restated as prefix-determinism rather than "no hindsight" |
| [02-what-runs-today.md](02-what-runs-today.md) | The mechanism as built, at file and line, and the ten invariants the code relies on without naming |

### Capability options — what the filter reaches

| | | Verdict |
| --- | --- | --- |
| **A** | [03 — hindsight rules at a paid boundary](03-option-hindsight-rules-at-a-paid-boundary.md) | reject |
| **B** | [04 — defer by turn, not by result](04-option-defer-by-turn-not-by-result.md) | **take** |
| **C** | [05 — head/tail elision instead of a drop](05-option-truncate-instead-of-drop.md) | reject as softening · adopt as discipline |
| **D** | [06 — a per-tool byte cap on the wire](06-option-per-tool-byte-cap.md) | adopt narrowly · **refused here** |
| **E** | [07 — per-tool `min_bytes` and `keep_newest`](07-option-per-tool-thresholds.md) | reject per-tool · **take the floor at 256** |
| **F** | [08 — MCP and delegated-agent output](08-option-mcp-and-subagent-output.md) | reject the rule · **refused here** |
| **G** | [09 — rewrite `tool_use` inputs](09-option-tool-use-inputs.md) | reject |
| **H** | [10 — a content-addressed recall store](10-option-recall-store.md) | reject · build the reader |
| **I** | [11 — read `usage` off the response](11-option-read-the-response.md) | reject the claim · defer the narrow version |
| **J** | [12 — a readout of the fixed prefix](12-option-prefix-readout.md) | **take**, in its own release |
| **K** | [13 — filter `count_tokens` too](13-option-count-tokens-parity.md) | **keep the exclusion**, correct the docstring, run the measurement |

### Structural options — what the mechanism as built should become

| | | Verdict |
| --- | --- | --- |
| **L** | [14 — one rule engine, or two](14-option-one-rule-engine.md) | **take**, as a shared function, not by calling `_first_matching_rule` |
| **M** | [15 — the filter honours no rule selection](15-option-honour-rule-selection.md) | **take, before the labelling study** |
| **N** | [16 — name the guards; implement G4](16-option-guards-by-name.md) | **take G4** |
| **O** | [17 — assert the cache-write invariant](17-option-cache-write-invariant.md) | **take**, and its first finding is a defect |
| **P** | [18 — price the breakpoint move](18-option-price-the-breakpoint-move.md) | **reject the ledger field** — 651 bytes |
| **Q** | [19 — the shapes a `tool_result` comes in](19-option-content-shapes.md) | a precondition, not a change |
| **R** | [20 — the ledger as a durable artefact](20-option-ledger-as-artefact.md) | **take `v` and `kind`** · reject rotation |
| **S** | [21 — the smallest honest health signal](21-option-health-signal.md) | **take two fields and a heartbeat** · reject an endpoint |
| **T** | [22 — `plan` and `fork` cannot be told](22-option-tell-the-pruner.md) | **take** |
| **U** | [23 — pin the emitted request body](23-option-golden-wire-fixture.md) | **take**, eight fixtures |

### The decision

| | |
| --- | --- |
| [24-comparison.md](24-comparison.md) | All twenty-one on one table: reach, cost, risk, and what has to be true. Plus six things the table gets wrong on its own |
| [25-recommendation.md](25-recommendation.md) | What to do, in order; what to refuse, with the single measurement that reverses each |
| [26-implementation-sketch.md](26-implementation-sketch.md) | Twelve commits: files, shape, tests, and why each sits where it does |
| [27-validation.md](27-validation.md) | Eight registers, each with its corpus, its bar and its kill criterion, fixed before any number is in |

## Two corrections inside the set

Stated here rather than left for a reader to trip over, because the earlier files are the ones
most likely to be quoted.

**[00-problem.md](00-problem.md)'s image caveat is 2.7× larger than it says.** §00 records 276
base64 image blocks carrying 19,954,267 bytes inside MCP tool results, and that figure is exactly
right for MCP. **A `Read` of an image file also returns an image block** — 199 more, 34,578,868
bytes — so the whole class is 475 blocks and 54,533,135 bytes, **19.4% of message content**
whose token cost `bytes ÷ 4` overstates by roughly 27.7×. On a denominator with all of them
removed the filter reaches **10.28%**, not the 9.15% §00 gives for its partial correction. The
direction §00 names is right and every share in the set is low by about a quarter rather than a
twelfth. Working in [19-option-content-shapes.md](19-option-content-shapes.md).

**[01-constraints.md](01-constraints.md) §K4's account of the breakpoint cap is wrong in one
clause.** §K4 says that when the cap is full *"the deferred result is cache-written after all"*.
It is not: `_strip_breakpoints_from` runs unconditionally before the count
(`filter.py:293-297`), so the candidate is strictly after every breakpoint that survives. The
cap branch cannot fire harmfully against a client respecting the same cap, and the real defect in
that code is the one [12-option-prefix-readout.md](12-option-prefix-readout.md) found —
`_count_breakpoints` ignores `system` and `tools`. Working in
[17-option-cache-write-invariant.md](17-option-cache-write-invariant.md).

## Where the numbers come from

Every figure marked **[measured here]** was taken on this container on 2026-08-27 by importing
`winnow.filter.rule_for`, `winnow.rules.classify` and `winnow.rules.result_size` directly and
replaying them over `~/.claude/projects/*/*.jsonl` — main sessions only, matching
`savings.find_transcripts`'s own glob. Sizes are SPEC §6's `len()` of the string or of
`json.dumps()` of a structure; requests are grouped on `requestId` per COZEMPIC §3.5.2; tokens
are bytes ÷ 4 and dollars use `savings.PRICES`. **The corpus is live and was being written to
while it was measured** — it holds 866 sessions in §00's run and 867 in the later ones, and §00's
method note puts the reproduction tolerance at about a tenth of a percent. The same drift is why
the `tool_result` count appears as 64,540 in §06, 64,651 in §18, 64,654 in §19 and 64,685 in §21:
four passes minutes to hours apart over a tree other sessions were writing to, spanning 0.2%.
Each figure is used only with the others from its own pass. Nothing was computed by hand and no
measurement script is committed; the method note is the recipe.

**Four defects are recorded rather than proposed** in the part-1 files —
`inspect.read_filter_ledger`'s missing de-duplication, `savings.find_transcripts`'s glob,
`filter._count_breakpoints` ignoring `system` and `tools`, and `filter.py:46-48`'s justification
— and [25-recommendation.md](25-recommendation.md) puts them at the top of the order together
with the two found here: the `--keep-newest 2` invalidation and the unimplemented G4.
