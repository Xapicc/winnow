# What the tool may not do

*Thirteen constraints, derived from `01-what-is-knowable.md` rather than from taste. Each one
names the measurement that forces it and the thing it forbids concretely enough to test. The
option files cite them by number as `§C4`; `04-comparison.md` scores against them. Nothing
here is a preference — every constraint exists because breaking it produces a number that is
wrong, and this instrument's only asset is that its numbers are not.*

---

## One correction to the floor, and it changes what these constraints have to protect

`00-problem.md` §4 says the missing 42.5% "is a floor that no amount of parsing removes", and
`01-` §3.2 states it as "a treemap built from a transcript alone under-reports a mature
context window by something between a third and a half". **The first sentence is wrong and
the second is right about the wrong quantity.** The material is indeed not in the file. It
does not follow that it cannot be priced, and this run measured that it can be —
`scratch/thinking_price.py`, added by this run.

**On the two runs below.** The script was run twice on 2026-09-02, hours apart, over the same
200-file even sweep of `~/.claude/projects`. It returned 168 qualifying sessions the first time
and 160 the second, because this run is writing transcripts into the corpus it measures and
sessions cross the "no compaction, ≥5 requests" filter in both directions while it does so.
Both runs are given, because the difference between them is the honest error bar and quoting
one would hide it. **The figures that matter are stable across the two; the one that is not is
named as such.**

`01-` §3.3 prices retained reasoning at ~670 tokens per thinking block by regressing a whole
session's unexplained remainder on its thinking-block count, and states the confound honestly:
the regression cannot separate a thinking block's cost from the cost of the hard turn that
produced it. There is a local instrument it did not use. **`usage.output_tokens` is exact and
covers everything the model emitted in one response — thinking, text and `tool_use` — and two
of those three are on disk verbatim.** So

```
retained_reasoning(response) ≈ output_tokens − est(text chars) − est(tool_use JSON)
```

which is one exact number minus two small estimates, per response, offline. The control is
the responses with no thinking block, where the same subtraction must come out near zero:

| responses | p10 | p25 | **median** | p75 | p90 |
|---|---:|---:|---:|---:|---:|
| no thinking block — run 1 (n=6,235) / run 2 (n=4,862) | 4 / −9 | 56 / 55 | **80 / 79** | 114 / 110 | 177 / 177 |
| with a thinking block — run 1 (n=6,236) / run 2 (n=5,153) | 138 / 138 | 215 / 220 | **391 / 388** | 776 / 766 | 1,576 / 1,598 |

The control holds, and it holds identically across both runs — a response that emitted no
reasoning is explained to within ~80 tokens by its own visible output. The per-block figure is
**~390**, not 670, and the difference is exactly what the confound in `01-` §3.3 predicted: the
regression was charging the thinking block for the hard turn around it. Net of the ~80-token
control, a thinking block is worth roughly **310 tokens**, less than half the corpus constant.

Feed the per-session sum back into `01-` §3.2's arithmetic and the floor stops being a floor:

| what is subtracted from the exact window | p25 | **median unexplained** | p75 |
|---|---:|---:|---:|
| visible transcript only — run 1 | 32.0% | **39.7%** | 51.9% |
| visible transcript only — run 2 | 33.5% | **45.2%** | 57.8% |
| …and the prefix, per session — run 1 / run 2 | 8.7% / 8.8% | **13.9% / 14.5%** | 22.2% / 20.9% |
| …and retained reasoning, per response — run 1 / run 2 | −2.5% / −1.1% | **0.6% / 0.5%** | 3.4% / 4.2% |

**The first row is the unstable one**, and it is unstable because it is dominated by which
sessions happen to be in the sample rather than by any property of the method: 39.7% against
45.2% hours apart, with `01-` §3.2's 42.5% sitting between them. Read it as "roughly 40%", as
`01-` §3.2 itself instructs. Everything below it is stable to within a point. 154 of 168 (run
1) and 149 of 160 (run 2) land within ±15% of their own exact window; 77 of 168 and 67 of 160
over-explain, which is what an unbiased estimator looks like. Of the median window, the prefix
is 23.7% / 24.3% and retained reasoning 14.4% / 14.0%.

**One session, worked end to end**, because a distribution is not a demonstration. Session
`e698739e` — `01-` §2.6 column C, and the session `00-` §6 names for carrying 98,453 tokens on
its *first* request:

| | tokens | share | kind |
|---|---:|---:|---|
| window at request 66 | **219,485** | 100% | exact, from `usage` |
| visible in the transcript — 50,905 tool results, 18,087 `tool_use` inputs, 6,852 attachments, 2,293 conversation | 78,137 | 35.6% | estimated |
| prefix — 98,453 at request 1 less 4,553 visible before it | 93,900 | 42.8% | derived |
| retained reasoning — 28 thinking blocks, 626 median tok/block | 46,557 | 21.2% | derived |
| **unattributed** | **891** | **0.4%** | residual |

`01-` §2.6 puts this session's invisible share at 64%; prefix plus retained reasoning is
140,457, which is 64.0% of the window. Two methods, one number.

Two things follow, and they are the reason this section is in the constraints file rather than
in a footnote.

**First, the honest picture is not one grey block.** `00-` §5.3 offers the choice between
silently omitting 42.5% and drawing it as one grey block labelled *not in the file*. There is a
third option and it is better than both: draw four blocks — prefix, retained reasoning, visible
material, and a residual whose median is under 1% rather than ~40%. The two invisible ones are
**derived** (an exact number minus an estimate) rather than estimated, and they are as
defensible as anything on the screen.

**Second, the accounting is a calibration, and that is a trap.** Sweep the chars-per-token
constant and the residual is monotone in it, crossing zero between 2.4 and 2.6 (run 1's
snapshot, n=168):

| chars/token | visible-only unexplained | **unexplained, fully decomposed** | within ±15% |
|---:|---:|---:|---:|
| 2.2 | 28.7% | **−7.0%** | 137/168 |
| 2.4 | 34.6% | **−3.0%** | 153/168 |
| 2.6 | 39.7% | **+0.6%** | 154/168 |
| 3.0 | 47.7% | **+5.5%** | 155/168 |

Solving per session for the constant that zeroes each session's own books gives median
**2.57**, p25 2.41, p75 2.75, p05 1.98, p95 3.32 (n=158). That is a fourth independent
estimate of `01-` §2.3's constant, it agrees with the adopted 2.6 to within 1.2%, and it is the
tightest of the four because the residual is monotone and crosses zero once.

It is also the most dangerous number in this proposal. See §C10.

*Reproduce: `scratch/thinking_price.py [n_files]` for the distributions,
`scratch/compose_one.py <session-id>` for the worked example. Same corpus caveat as `01-` —
one operator, one machine, almost all `claude-opus-5`.*

---

## §C1 — It reads a session and never writes one

No write, of any kind, anywhere under `~/.claude/projects` — not the transcript, not the
`tool-results/` sidecars, not the `subagents/` directory, not a cache file placed beside them.
Nor to `~/.winnow`, whose stores belong to a different tool with a different lifetime.

The grounds are not squeamishness. The tool will be pointed at sessions that are being
appended to by the CLI right now (`01-` §4), against a file with no lock and a writer that
assumes it is alone; and this repository is already the thing that rewrites tool results
before the model sees them (`01-` §7 item 4, 182 of 1,985 transcripts carry a `winnow: …
removed` marker). A reader must not join that. Anything the tool wants to persist — a
calibration, a cached parse, a diary — goes somewhere the operator named.

**Testable as written:** the command exits 0 with `~/.claude` mounted read-only.

## §C2 — Every number carries its provenance, and there are exactly three kinds

`01-` §3.4 sorts the claims into exact, derived, estimated and not-knowable. That table is a
type system and the renderer should treat it as one.

- **exact** — lifted from a number the CLI wrote down: `usage`, `compactMetadata`, a
  `read_truncation_notice` banner. Never computed.
- **derived** — an exact number minus an estimate: the prefix (§3.1's subtraction), retained
  reasoning (the correction above). Robust, and not exact.
- **estimated** — characters ÷ a constant. Everything visible.

There is one further label and it is not a fourth kind of number: **residual**, reserved for
the single unattributed node, which is by definition what no kind accounts for. Every other
node is exact, derived or estimated, and **no number renders without one of the three.** An
aggregate of mixed kinds takes the weakest of its parts: a percentage whose numerator is
estimated and whose denominator is exact is estimated. The point of the rule is that the
operator can tell, at a glance, which figures survive the chars-per-token argument and which do
not — and per the correction above, the two biggest non-visible blocks survive it well.

## §C3 — The total is exact; the parts are apportioned into it

`01-` §2.2 states the architecture and it is a constraint, not a suggestion. The tool takes
`input_tokens + cache_creation_input_tokens + cache_read_input_tokens` from the anchoring
request and apportions the estimate inside it. It may never sum estimates to produce a total.

The consequence worth stating: the shares always sum to 100% of a number that is correct by
construction, so the error lives entirely in *where* the tokens are attributed, never in *how
many* there are. That is the difference between an instrument and a chart, and it is why the
residual node (§C10) is load-bearing rather than decorative.

## §C4 — Nothing that is not context may be sized

The exclusion list is closed and each entry has a measurement behind it:

| excluded | why | `01-` |
|---|---|---|
| `toolUseResult` | a local convenience field; the API never sees it. 32.6–45.6% of file bytes on three sessions | §1.4 |
| thinking `signature` | 1.4–2.7 KB of opaque blob per block, zero tokens. 15.7% of one 2 MB file | §1.3 |
| the 15 bookkeeping record types | 19.9% of records, 2.7% of bytes, zero tokens | §1.1 |
| `queue-operation` specifically | it carries a copy of the user's prompt, so it *looks* like context and is not. 1.96 MB on 530 records | §1.1 |
| `tool-results/*.txt` sidecars | 204,906,775 bytes across 220 sessions that never entered any context | §1.4 |
| attachment JSON keys and structure | the CLI renders attachments into prose; only the payload strings are on the wire | §2.4 |
| `block.id`, `is_error`, envelopes | scaffolding | §2.4 |
| a sub-agent's own transcript | a separate context, §C11 | §4.5 |

A treemap that counts records draws the third row — 19.9% of them — and `queue-operation` inside
it. A treemap that counts bytes draws the second as the third-largest thing in the session. Both
are wrong in a way the operator cannot see, which is the worst kind.

## §C5 — Bytes are never an area

The unit is tokens, at every level, and the readout says so. Two measurements make this a rule
rather than a preference: a thinking block is 2,784 bytes on disk for zero tokens (`01-` §1.3)
and an image is over-reported **14×** by its base64 length (`01-` §2.5, four images at 1518×784
priced 1,586 tokens by `w·h/750` against 20,717–24,008 by `bytes/4`).

Where a size cannot be turned into tokens, the node is sized **zero and labelled**, not guessed.
For images that means reading the JPEG SOF or PNG IHDR out of the first ~3 KB of the decoded
base64; if the header does not parse, the block is zero with a reason, and never `len(data)/4`.

## §C6 — The accumulator resets at every compaction boundary

`01-` §4.6: 867 boundaries across 210 files. Session `2551cd0c` sums to 416,774 estimated
tokens cumulatively and its real final window is 116,030 — a **3.6× over-report** for a tool
that walks from the top and adds.

Positively: `compactMetadata` gives `preTokens`, `postTokens` and `cumulativeDroppedTokens`
exactly, and the pre-compaction composition is still in the file. Showing what compaction ate
is a capability `/context` does not have, and it costs nothing beyond honouring this rule.

## §C7 — No hardcoded prefix, and no percentage without a stated denominator

The prefix runs from 21,520 at p10 to 82,689 at p90 (`01-` §3.1). This repository's two
attempts at a constant — `SYSTEM_OVERHEAD_TOKENS = 21_000` (`legacy/tokens.py:20`) and
`BASE_PREFIX_TOKENS = 15_903` (`inspect.py:67`) — are low by a third to a half, and the second
is dead code whose cited source no longer contains the number. The tool measures the prefix per
session or does not claim one.

The window size is worse: **nothing in a transcript states it** (`01-` §7 item 9). Session
`72acbacd` reports 512,133 tokens on a model whose nominal window is 200,000, because it is a
`[1m]` session and the `[1m]` is attached to the model id by a beta flag no record carries. A
tool that hardcodes 200,000 reports that session as 256% full.

So: **the readout carries no "% of window" figure unless the operator supplies the
denominator.** Composition shares — this block as a fraction of the window that exists — need
no denominator beyond `usage` and are always available. Fullness is a different claim and it
is not available.

## §C8 — Deduplicate on `message.id` before touching `usage`, and split on `\n`

Two inherited defects, both cheap, both fatal, both already solved in this tree.

One API response is written as several JSONL lines, one per content block, each repeating the
same `usage` object. Summing per line inflates by **1.7–2.4×** (`01-` §2.1).
`/workspace/gh-layer10` `eval/harness/usage.py` ships this bug today, which is the evidence
that the warning is needed. `winnow/savings.py:357 read_session` already de-dupes on
`requestId`; read it before writing a fourth version.

And the parser: split physical lines on `\n` and never `str.splitlines()`, because U+2028,
U+2029 and U+0085 are legal unescaped inside JSON strings and `splitlines()` breaks on them
(`legacy/session.py:825`); read with `errors="surrogateescape"`, because a JSON-escaped lone
surrogate from a sliced emoji will otherwise crash the byte count; buffer an incomplete
trailing fragment rather than advancing past it (`01-` §4.3 — zero torn lines in 400,548
records and 59,100 live polls, and a `repair_torn_trailing_line` in this tree that suggests
somebody has seen one).

`01-` §6.1's closing observation is the operative one: the value in `legacy/` is not the code,
it is the dated postmortems on top of it. A new parser without those comments will re-earn
each of these bugs in the order they were originally found.

## §C9 — The tool says when what it read is not what the model saw

Two cases, both measured, both correctly sized at what the model saw, both requiring a label:

- **`<persisted-output>` spills.** The block on the wire is a ~2.3 KB wrapper with a 2 KB
  preview; the full output is in a sidecar. On session `c91dc0a7` the model saw 2,331
  characters where the record holds 45,085 (`01-` §1.4). 343 transcripts contain the wrapper.
  Size the preview. Say that the node is a pointer, and how big the thing pointed at was.
- **Hook-rewritten results.** 182 of 1,985 transcripts carry a `winnow: … removed` marker.
  Whether the transcript ever records the original is unsettled (`01-` §7 item 4). Sizing the
  rewritten result is arguably the *correct* answer — it is what the model saw — but a
  readout that does not say so is measuring a hooked install and calling it a conversation.

The general rule: where the transcript and the wire differ, the tool follows the wire and
prints the divergence. It never silently follows either.

## §C10 — Calibrate or check. Never both with the same number

The tool can solve for the chars-per-token constant that makes a session's books balance
(median 2.57, IQR 2.41–2.75, above). It must not apply it.

If the constant is fitted to zero the residual, the residual is zero by construction and the
tool has destroyed its only self-check. Worse, the fitted constant silently absorbs any
systematic term the decomposition is missing — a category not counted, an attachment class
not walked — and reports perfect books over a wrong model. **A residual that cannot be
non-zero is not evidence.**

So: ship a fixed constant, render the residual as its own node, and offer the solved constant
as a diagnostic that says out loud it was not applied. The residual node is the tool's
confession and the single most useful number for anyone auditing it.

## §C11 — A sub-agent's context is not the parent's context

`01-` §4.5: 962 sub-agent transcripts under 115 session directories, `isSidechain` false on
parent records, joined by `toolUseId` → the parent's `Agent` `tool_use` id. On this run's own
session, nine sub-agents totalling 3.8 MB against the parent's 0.4 MB.

What is in the parent's window is the sub-agent's **return** — the `tool_result` for that
`Agent` call — and nothing else. Adding a sub-agent's own tokens to the parent's total
produces a number that is not the size of any window that ever existed. The sub-agent gets one
block in the parent, sized by its return, and its own tree is a *separate budget* reached
sideways. Rendering them as two totals joined by an id is not a limitation; it is the shape of
the operator's actual question — "it spent 230,000 and gave me back 4,000; was that a trade?"
— and both halves are on disk.

## §C12 — Live mode's exactness lags one request behind, and the readout says how far

The file lag is not the problem. `01-` §4.2 measures it at a median **102 ms** over 59,100
polls, with records landing as they happen rather than at end of turn.

The lag that matters is the **pricing** lag. The exact window total is stamped only when an
assistant record lands, i.e. once per API request. Between requests the tool has watched
`tool_use` and `tool_result` blocks arrive that it can estimate and cannot anchor — and on a
long tool call that gap is minutes, not milliseconds. There is no instrument that closes it,
because the number does not exist yet.

Therefore a live readout must state three things or it is lying: **the request its exact total
came from, how long ago that was, and how many estimated tokens have been appended since.** A
live single number with no anchor age is the failure mode this whole proposal exists to
replace, reintroduced.

Two subsidiary facts from the same section: one record of 438 appeared **21 seconds** after its
own timestamp, so a live reader must not assume timestamp ordering within a window of tens of
seconds; and a `tool_use` with no `tool_result` is the normal state of an in-flight tool, not a
parse error.

## §C13 — No claim about attention, necessity, or reclaimable space

The last row of `01-` §3.4: *"you could save X by not re-reading `orchestrator.ts`" — not
knowable. The transcript records what was sent, never whether the model attended to it.*

This forbids the affordance TreeSize is named for. It goes further than "we cannot measure
usefulness", because of `01-` §5's third broken analogy: **removing a block from a context
invalidates the prompt cache for everything after it, so the saving from deleting an early
block can be negative.** This repository's entire `T* = 19·(S/D) − 20` break-even arithmetic
exists because of that. A "reclaimable space" column would be wrong in sign, not just in
magnitude.

What the tool may say instead is what is *there*, how much of it, how many times the same
artefact appears, and what compaction has already dropped. Every one of those is a fact. The
inference from a fact to an action is the operator's, and the tool's job is to make it cheap,
not to make it for them.

---

## What these do not constrain

Stated because a constraints file that reads as a prohibition list invites the reader to think
everything is forbidden.

Nothing here constrains **how it renders** — terminal, TUI or browser are all admissible and
that is the argument of `03-option-a` through `03-option-c`. Nothing constrains **where the
code lives** (`03-option-d`). Nothing constrains the **hierarchy**; `01-` §5 offers three and
`05-recommendation.md` picks one. Nothing forbids a **network mode** later — an `--exact` that
calls `count_tokens` with a credential would settle `01-` §7 item 1 outright — only shipping
one that *needs* it, because `01-` §2.2 establishes that no tokenizer is installable offline
and this sandbox binds `.credentials.json` to `/dev/null`.

And nothing here constrains **being wrong**. Every estimated figure in the tool will be wrong
by some amount. §C2, §C3 and §C10 exist so that it is wrong in a way the operator can see,
bound and argue with — which is the only kind of wrong an instrument is allowed to be.
