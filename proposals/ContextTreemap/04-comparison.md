# The four against each other

Three renders and one home. `03-option-a` through `03-option-c` answer the same ten headings,
so the render axis is a table over a fixed set; `03-option-d` is a different question and gets
its own section. **The criteria and their weights are argued before any score is shown**, and
the zero of the capability scale is not "nothing" — it is `/context`, which is built in, live,
free and already better than this proposal's readers assume.

---

## The zero, and why it is `/context` rather than nothing

`00-` §6 names it as the second most likely way this proposal dies: *"`/context` is good
enough. Eleven flat categories, live, built in, zero install."* `01-` §6.3 ran it and found it
is better than that — three per-item drill-downs exist already (`Custom Agents`, `Memory
Files`, `Skills`), and per-skill token costs the operator's own vault records as unpublished
are simply printed.

So an option scoring 0 against `/context` on the capability rows is not neutral. It is dead.
Every score below is *the change from what the operator already has*, and the row that matters
most is the one where `/context` stops: `Messages` is 60–90% of a working session and it is a
single number with nothing beneath it.

## The criteria, and their weights, stated before the scores

| Criterion | Weight | Why that weight |
|---|---:|---|
| **Names the biggest thing in the window** | 4 | It is the request. `/context` cannot: its one undrilled category is the one that is 60–90% of a working session, and the CLI computes the drill-down (`toolCallsByType: {tool: {callTokens, resultTokens}}`) and discards it at the render boundary (`00-` §3). Anything scoring below +2 here has not solved the problem. |
| **Honesty of the floor** | 4 | `02-constraints.md`'s correction makes ~38% of the median window **derived** rather than missing — prefix ~24%, retained reasoning ~14%, residual ~0.5%. Whether the render distinguishes exact from derived from estimated legibly (§C2) is the difference between an instrument and a chart. `/context` scores 0: it labels the whole table "Estimated usage by category" and attaches no provenance to any row. |
| **The numbers can leave the screen** | 3 | The second reader of this readout is a model, and the third is a note written six months from now. `/context -p` already emits text, so a mode that produced no text at all would score negative — but no option here does, and the row turns out not to separate them. It is kept at weight 3 because it would have, had any option been designed without a printer, and dropping it after the fact would be fitting the criteria to the answer. |
| **Degradation when the data is missing, partial or lying** | 3 | Eight named cases (§C7, §C9, §C6, §C5, §C8; enumerated in `03-option-a`) and every one of them is a place where a number is either absent or subtly not what it claims. An option that degrades by dropping the caveat is worse than one that degrades by refusing. |
| **Live-mode lag, honestly shown** | 2 | Two, not four, **and this is the most important weighting judgement in the file.** §C12 establishes that the exact window total is one API request behind in *every* option — the number does not exist between requests, so no render can fix it. What varies is only whether there is room on the screen to say how far behind it is. Weighting this at 4 would be scoring layout as capability. |
| **Resists the reclaimable-space misreading** | 2 | §C13: removing an early block invalidates the prompt cache for everything after it, so a "you could save X" figure can be wrong *in sign*. A render that inherits TreeSize's space-filling metaphor inherits the implication and has to fight it. |
| *Whether the operator acts on it* | **0** | Listed and weighted zero because omitting it would be dishonest. It is the criterion that actually decides whether any of this was worth building (`00-` §6: *"if nobody would act on it, it is a chart"*) and there is no offline instrument for it. `05-recommendation.md` builds the only substitute available, which is a diary, and says plainly that it is not a metric. |

## Scores — capability, against `/context` today

Signed −3…+3. **0 means no change from `/context`.** Weight in the row label.

**The scoring basis, stated first, because a first draft of this table got it wrong.** Each
option is scored as the *complete package it would ship*, not as its headline surface. B and C
both ship A's printer and A's `--json` — B needs the printer for its no-TTY fallback and C
needs the serialiser for its payload (see the cost table below) — so neither can score below A
on a row about what the package can do. Where a row is about what the operator *reads in the
surface the option exists to add*, it is scored on that surface, and the row says so. An
earlier draft scored B at −1 on "the numbers can leave", which is unreachable: an option that
contains A's printer cannot be worse than A at printing.

| | **A** one-shot | **B** TUI | **C** browser |
|---|---:|---:|---:|
| Names the biggest thing (×4) | **+3** | **+3** | **+3** |
| Honesty of the floor (×4) — *read surface* | +2 | **+3** | +2 |
| The numbers can leave (×3) — *package* | **+3** | **+3** | **+3** |
| Degradation (×3) — *read surface* | **+3** | +1 | 0 |
| Live-mode lag, shown (×2) — *read surface* | +1 | **+3** | **+3** |
| Resists reclaimable-space (×2) — *read surface* | +2 | +2 | **−2** |
| **Weighted total** (max 54) | **44** | **46** | **31** |

**B outscores A, and that is the correct result.** B is A plus a cursor over an identical tree
model; it can do everything A can do because it contains A. A capability table comparing them
was always going to say so, and a table that said otherwise was scoring the render as though
the printer would be thrown away. **The consequence is that capability does not decide this
comparison — two points out of fifty-four is noise — and cost and risk do.** That is the honest
shape of the decision and it is why `05-recommendation.md` is argued on the cost table below
rather than on this one.

**The cells worth reading rather than the totals.**

**All three take +3 on the first row, and that row is the request.** Every option answers the
question `/context` cannot; the survey is therefore not about whether to build the thing but
about how much to spend rendering it. That is the single most useful fact in this table and it
is invisible in the totals.

**B: +3 on the floor, the only row where B beats A on the merits rather than on layout.** The
prefix is the one block an operator fixes by editing configuration rather than by changing
habits, and making it actionable requires a sentence — *your first request was 98,453 tokens
and the transcript can see 4,553 of them* — that a detail pane has room for and a printed row
does not. Worth four weighted points and no more, because A can put the same sentence behind an
`--explain` flag for a small fraction of B's build.

**A: +3 on degradation, and the reason is structural rather than clever.** A static readout has
a whole line where a number would have been and no layout to preserve, so it can always print
the reason in place. B has to fit the reason in a pane that closes on a narrow terminal; C has
to attach it to a rectangle whose area is proportional to a node that may be a thousandth of
the window. Scored on the read surface: B's fallback to A's printer is not a defence, because
an operator reading the TUI is not reading the printer.

**C: −2 on the reclaimable-space row, the only negative cell in the table, and it is not a
detail.** A space-filling diagram of a thing that looks like a disk carries TreeSize's entire
implied verb: *delete the big rectangle and get the space back*. §C13 establishes that this is
false here and can be false in sign. A and B inherit no such implication; C inherits it by
construction, because the metaphor is why it was chosen.

**A: +1 on live lag, and this is the cell most likely to be misread.** A `--watch` that
redraws every 250 ms with two lines stating the anchor request, its age and the estimated
tokens since is *adequate* live behaviour, not degraded live behaviour. What A cannot do is
keep the operator's place across a redraw. See the second correction below.

## What each costs, which is not on the same scale and is not scored

| | **A** | **B** | **C** |
|---|---|---|---|
| Build, relative | **1×** — ~600–900 new lines over an existing walk, parser and resolver | ~1.6–2× | ~2–2.5× |
| New runtime dependency | none — the render is `str.ljust` and a block glyph | `curses` (stdlib, hand-written layout) or `textual` behind an extra | none strictly, but a static asset tree that must ship in the wheel |
| New surface to maintain | a printer | screen, cursor, key map, resize, no-TTY fallback, incremental cursor-preserving merge | a page, a layout algorithm, a server, an SSE path, front-end review |
| New risk | none identified | a caveat dropped to make a layout fit | **a loopback port serving transcript content** — memory files, `tool_use` inputs, the environment attachment with the operator's email and git status, and any secret that ever appeared in a tool result |
| Does it require A anyway? | — | **yes** — the no-TTY fallback is A's printer, and this machine's common caller is an agent with no TTY | **yes** — `--json` is A's serialiser |

That last row is the one that changes the shape of the decision, and the next section says how.

---

## The home: `03-option-d` against the two alternatives

A different axis, different criteria, and the reuse argument — the one everybody expects to
decide it — turns out not to.

| | **new repository** | **subcommand here** | **card in UsageFoundry** |
|---|---|---|---|
| What must be copied | ~900–1,000 lines, ~90 rewritten. A week. | nothing | **everything** — it is TypeScript; the whole Python substrate is a rewrite |
| Drift risk on the parser | **two parsers, no test that fails when they diverge, and both produce numbers either way** | none | two, in different languages |
| The postmortems | copied as comments, then diverge | live where they were written | not transferable |
| Install surface for the operator | `uvx contextmap <id>` — the best in the set | winnow's whole distribution — but it is already installed | already deployed, but only knows runs it launched |
| Dependency fit | clean by construction | fine for A; strained for B; wrong for C | a page wants a page |
| `prefix_facts`, the only exact prefix instrument | **left behind, and unreachable across a repo boundary** — it takes a request body, not a file | in the same tree, available as the one cross-check on the derived prefix | left behind |
| What gets retired | **nothing** | `winnow inspect`, by a two-line deprecation on the day the new command lands | nothing |
| Verdict | the honest runner-up | **take it** | reject |

**The subcommand wins on the thing that stays behind rather than on reuse.** `winnow inspect`
ships today and reports `cache_read_input_tokens 18,378,780` for a session whose window at the
last request was 219,485 (`01-` §6.1, verified by running it) — a lifetime sum presented beside
a byte-share breakdown, which is precisely the misreading this proposal exists to prevent. And
`winnow savings`, the only command that renders the prefix readout, is broken on `main`
(`cli.py:609`). A new repository has no reason to touch either, ever.

**And the coupling objection is real but small and fixable in place.** `cli.py:23` and `:25`
eagerly import `orchestrator_safe` and `proxy`, so every subcommand pays for them. Measured on this
tree: `import winnow.inspect` pulls 7 winnow modules in 15 ms and touches neither
`legacy.guard` nor `legacy.team` nor `proxy`; `import winnow.cli` pulls 16 in 27 ms. The
substrate is already factored the way a subcommand needs it; only the front door is not, and
moving two imports into their subparser handlers is an independently good change. The
extraction of a clean `winnow.transcript` package is therefore a **later cleanup, not a
prerequisite** — and it is exactly the change the operator would make first if they ever do
spin this out.

**The card is rejected on the request, not on taste.** The ask is a command taking a session
id; UsageFoundry knows about runs it launched, and the sessions worth understanding include
the ones it did not. Its own proposal set has already allocated that surface to a per-cycle
cost table (`01-` §6.2), so a composition card would put two token estimators disagreeing on
one screen.

---

## Five things the table gets wrong on its own

**1. A, B and C are not three builds; they are one build and two layers on it.** The bottom
row of the cost table is the whole point: B's no-TTY fallback is A's printer, and on this
machine the most frequent caller of anything is an agent with no TTY; C's `--json` is A's
serialiser. The tree model, the classifier, the apportionment and the two derived blocks are
identical in all three. So the totals do not describe a choice between 44, 46 and 31 — they
describe a floor of 44, with an option to spend a further 0.6–1× of A for B's navigation (+2
capability points) or a further 1–1.5× for C's picture (−13). **Read the table as "A, then
maybe", not as "A or B or C".** Two points out of fifty-four is what B's extra build buys,
stated in the units the table uses, and it is the reason not to buy it on day one rather than
a reason never to buy it.

**2. The live-lag row is over-read at any weight.** §C12 is a property of the data: the exact
total is stamped once per API request and does not exist in between, so on a four-minute Bash
call every option is four minutes stale in the only number that is exact. A scores +1 and B
scores +3 on *how much room there is to say so*, not on how stale they are. If the row were
scored on staleness it would be +1/+1/+1 and would drop out of the comparison entirely, which
is the truer picture. It is kept at weight 2 because there is a real difference between a
sentence under a header and a visually separate growing node, and that difference is worth
something on the fourth redraw when nobody reads sentences any more.

**3. The floor row moved under all three options while this file was being written, and the
recommendation is downstream of one measurement taken hours earlier.** Before
`02-constraints.md`'s correction, the tool had to draw a ~40% block it could not decompose, and
a render able to make that block *visually different in kind* — hatching, texture, a fill
pattern — would have been worth a great deal. That is C's one structural advantage, and it was
largely nullified by dropping the residual to ~0.5%. **If `scratch/thinking_price.py` is wrong —
if retained reasoning is not in fact retained on this model class (`01-` §7 item 2 lists it as
unsettled), or if the corpus is unrepresentative — then the floor comes back, C's advantage
comes back with it, and this comparison should be re-run.** `05-recommendation.md` makes that a
kill criterion rather than a footnote.

**4. The criterion that decides it is weighted zero.** Whether anyone acts. There is no
offline proxy for it and there is no honest way to score it, so it sits in the criteria table
at weight 0 and it is the only row that can retire the whole project. Any reading of the totals
that does not carry that row forward is a misreading.

**5. The build multiples, and every per-component line count under them, are the least reliable
numbers in this proposal set.** Every other figure here is measured against a corpus or a
running command. `1×`, `1.6–2×` and `2–2.5×`, and the `~300 lines of curses` / `~120 lines of
JavaScript` estimates the option files break them into, are this run's judgement about code
that does not exist, extrapolated from line counts of code that does. Read them as an ordering,
not as magnitudes, and do not put them in a schedule.

---

## What the set does not contain

Four shapes a reasonable person would look for and will not find, each absent for a reason.

**A statusline mode.** Not an option; a wall. `00-` §3: the statusline JSON contract exposes
`context_window.{total_input_tokens, output_tokens, context_window_size, current_usage,
used_percentage, remaining_percentage}` and no category split at all, so every third-party
statusline is structurally capped at one number regardless of what this tool computes. Nothing
here can be published through that channel.

**A proxy-side instrument on the request body.** The honest answer to "why is my prefix 98,000
tokens" is `filter.py:728 prefix_facts`, which sizes the system block and every tool definition
exactly — and `00-` §6 names *"the invisible half is the interesting half"* as the most likely
way this whole proposal is wrong. It is deliberately absent because it is a different tool with
a different threat model: it has to sit on the wire, it cannot be pointed at a file, and it
cannot answer anything about a session that has ended. `02-constraints.md`'s correction makes
the derived prefix good enough to defer it, and if that correction fails this is the option to
build instead.

**A cross-session view.** `ccusage`, `session-report` and `receipts` occupy it (`01-` §6.4),
the denominator is different — dollars per day against tokens per window — and one id in, one
picture out is the whole shape of the request.

**A "what should I delete" mode.** §C13 forbids it, and the prohibition is the strongest
constraint in the set: the transcript records what was sent, never whether the model attended
to it, and the saving from removing an early block can be negative. Every option in this survey
is an instrument for a decision the operator makes. None of them makes it.
