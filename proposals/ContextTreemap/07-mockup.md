# The mockup, and what drawing it forced somebody to decide

*Mockup run, 2026-09-02, same branch. `mockup/index.html` is one self-contained file that opens
from `file://` with no build step, no package manager and no network. It renders three real
sessions, a live mode, a treemap comparison and four empty states. It reads nothing, parses
nothing and resolves nothing: every number in it is hard-coded from `06-spike-findings.md`. It
does not amend `00-` through `06-`; where it goes beyond them it says so below.*

---

## Which design this draws, and why it is not the one `05-recommendation.md` names

**It draws the shape `06-spike-findings.md` amended the recommendation into, not the shape
`05-recommendation.md` still names.** The spike's verdict is explicit — *"This is not a treemap.
It is a five-row receipt with a drill on one row and three exact facts above it"* — and it carries
three amendments that change what a picture of this tool looks like: the third level is demoted to
a `--depth 3` opt-in and re-keyed **artefact above tool** rather than tool above artefact; a new
**exact** block goes above the tree for context that left the window with no compaction boundary;
and the days `05-` §M2 budgeted for the drill go to the classifier. So the mockup draws a ranked
receipt, keeps H1-by-provenance as the only tree, defaults every figure to level two, and puts the
third level behind a button that says what the spike found about it. The hierarchy is unchanged
from `05-` — provenance at the root, artefact under `tool traffic` — because the spike did not
dispute it; only the level-three key and the ordering of the work were disputed. Figure 5 draws
the treemap the proposal is named after, on real numbers, so the operator can see the decision
rather than be told it: five rectangles totalling **505,127** against a window of **487,584**,
because a negative residual is not a rectangle.

---

## What is in the file

| # | Figure | Session | What it is for |
|---|---|---|---|
| — | provenance key | — | `exact` / `derived` / `est` / `residual` / `unknown`, as a permanent part of the page rather than a footnote |
| 1 | ended session | `b66837ed` | the readout at its best: one auto-invoked skill body at **54.4%** of a 487,584-token window |
| 2 | ended session | `939a04dc` | the readout at its worst: residual **−25.6%**, and two exact `shed` lines above the tree that say why |
| 3 | ended session | `e268d6c5` | **50.7%** of the window is `derived` — material that is in the window and not in the file |
| 4 | live session | `b66837ed` | the same picture, anchored one request behind, with an in-flight call and a torn trailing line |
| 5 | the design choice | `b66837ed` | the same five nodes as a treemap, and the four things its rectangles cannot hold |
| 6 | empty states | — | four ways of having nothing, as four different screens |

Figures 1–3 have a `--depth 3` button; figure 2's drilled state also carries the artefact-first
re-key panel. `?depth=3` in the URL pre-renders all of them drilled, so a state is linkable and
screenshottable without a click. A theme control offers auto / light / dark, and both palettes
were run through the `dataviz` skill's validator (`scripts/validate_palette.js`) — **ALL CHECKS
PASS** in both modes, worst adjacent CVD ΔE 9.1 light / 8.4 dark. The light-mode contrast WARN on
two slots obliges visible labels; that is satisfied by construction, because every row prints its
own provenance word beside the colour chip and the readout is already a table.

### Rendering was verified

Chromium is on this machine. Every state was rendered and looked at, and six screenshots are
committed beside the file: `01-full-light.png`, `02-full-dark.png`, `03-full-light-depth3.png`,
`04-live-dark.png`, `05-empty-states-light.png`, `06-half-unseeable-dark.png`. Five layout faults
were found by looking rather than by reasoning and fixed: notes hanging off the wrong margin, a
treemap cell clipping its own label, `word-break: break-all` shattering the torn-line sample
mid-word, the empty-state cards too narrow to hold an aligned numeric column, and a caveat about
the stale prefix rendered as a pseudo-node with an `unknown` chip when it is a caveat.

---

## What is real and what is not

**Real, and traceable to a printed number.** Every token count, every percentage, every node
label, every session header line, every derivation note, every `chars/token that would zero this
session's residual` figure, the image arithmetic (49 images at 66,318 tokens against 939,317 for
`len/4`), the sub-agent ratios (3 sub-agents, 369,134 tokens of their own windows, 8,427
returned), the two `shed` lines and their causes, and the `f6ea2591` re-key table (29 nodes /
33.2% pooled by path against 32 / 16.8% keyed by tool-then-path). All of it is transcribed from
`06-spike-findings.md`.

**Arithmetic over printed rows, computed by hand for this mockup and marked as such in the
figure.** Two things:

- **Figure 2's artefact-first panel.** Pooling `05-recommendation.md` at 4,134 tokens across
  `Read ×5` and `Edit ×20` is addition over two rows the spike printed in two different subtrees.
  It is not a re-run, and it **under-counts**: a path can only be pooled here when every one of
  its appearances was printed rather than folded into a "N more nodes, each smaller" bin. The
  panel says so beneath itself.
- **Figure 5's treemap.** The five rectangle areas and the 505,127 total are addition over
  figure 1's own level-one rows.

**Invented, because nothing in `00-` through `06-` settles it.** This is the list the operator
most needs to react to, because each item is a decision somebody made in an afternoon that nobody
has argued about.

1. **That there is a picture at all.** Every earlier file specifies a terminal readout, and `05-`
   §M1 explicitly says "no colour". The information architecture here is the spike's; the page,
   the proportional bars, the ledger strip and the caption strips are this run's.
2. **How a negative residual is drawn.** The spike found the residual must be allowed to go
   negative and noted that `03-option-a`'s mock readout does not contemplate it. Two of the three
   sessions drawn here are negative. The answer taken: a **diverging track with a zero line**,
   60 px of deficit room to the left and 180 px of positive room to the right, one scale for every
   row. Nobody has reviewed that choice.
3. **The ledger strip** — `derived` and `est` stacked against a black rule at the exact window,
   with a yellow bracket under the overhang when they overrun it. `06-` prints the same
   information as four lines of arithmetic under the heading `audit`. Turning it into a mark is
   new, and it is the thing that makes a −25.6% session look wrong at a glance.
4. **Colour means provenance, never category.** Four categorical slots assigned in fixed order
   along the honesty ladder: exact, derived, est, residual — with `unknown` deliberately given no
   mark at all, because a thing with no size has no length to draw. This is the whole visual
   grammar and it is one run's decision.
5. **The entirety of live mode.** M4 was never built and the spike reads ended sessions only, so
   figure 4's anchor age (`1m 12s`), its `+4,480` estimated-since, the `41 s` elapsed on the
   in-flight `Bash`, and the torn 214-byte trailing fragment are all fabricated. The `+4,480` is
   this session's own per-call averages — one `Write` input at 66,947/16 = 4,184 and one `Bash`
   input at 28,686/97 = 296 — which is a plausible number, not a measured one. What *is* measured
   is the lag: 102 ms median file lag over 59,100 polls, and the record that appeared 21 s after
   its own timestamp, both from `01-` §4.2 by way of §C12.
6. **The rule that a pending row carries no percentage.** Figure 4 prints `—` in the share column
   for arriving material, on the reasoning that the denominator is a window that does not exist
   yet. It follows from §C7 but no file states it.
7. **All four empty states, including their exit codes.** `05-` §M1 gives one acceptance criterion
   — no `usage` anchor means the estimated tree, no percentages at all, and a non-zero exit — and
   the definition of done names "six degenerate sessions" as a fixture set without listing them.
   Everything else on figure 6 is invented: the ambiguous-prefix screen and its two-match listing,
   the not-a-transcript screen and its `type`-field check, the too-thin screen, and the exit codes
   2 / 2 / 1 / 0. **The session ids `b6683f10`, `9f2c1a4e` and `0c4d9a11`, the file
   `~/scratch/dump.jsonl`, and all of their record counts are fabricated** — these and figure 4's
   live deltas are the only fabricated numbers anywhere in the mockup, and they are confined to
   those two figures.
8. **A `--at-request N` flag**, used once in the too-thin screen so a one-request window could be
   shown. No earlier file proposes it.
9. **A "fewer than ten requests, print three numbers and no tree" threshold.** Ten is a guess.
10. **Annotating the tool's own known faults on the rows themselves.** `$ cd ×34` carries a
    warning that `bash_head` splits on `&&` and files every `cd X && …` there; `edited_text_file`
    carries one saying it is a CLI attachment class rather than a provenance. The spike states
    both in prose. Putting them on the row is arguable in both directions — a readout that
    confesses on every render is either the most honest thing here or the noisiest.
11. **`?depth=3` as a URL parameter.** A mockup affordance for linking and screenshotting states.
    Not a proposed flag.

---

## What is deliberately not drawn

- **What the tree does when the window sheds mid-watch.** Figure 2 shows that shedding is a
  10.4%-of-sessions event and figure 4 shows a live readout, and the two are never combined
  because nobody has designed it. Figure 4's caption says so.
- **The compacted session.** `2551cd0c`'s three exact lines above the tree — window 116,030,
  444,326 cumulative dropped, last boundary 170,229 → 23,301 — are a *fourth* kind of above-tree
  fact and the only one `/context` cannot approach. Three sessions was the brief's ceiling and
  the shed variant was the newer finding, so compaction went undrawn. It is the first thing to
  add if this gets a second pass.
- **`--by-turn`, `--explain <node>`, `--audit` as a screen, and the sideways drill into a
  sub-agent's own tree.** All named in `05-`; none has a picture.
- **The M1 skeleton as its own screen.** Figure 1's caption says in one line what M1 alone would
  print — rows 1, 4, 5 and a ~40% residual — rather than drawing a deliberately worse version.

---

## What looking at it changed

Three things, and the first is the one worth arguing with.

**The unknown block is three different things and only one of them looks like an unknown.**
`05-` treats "what the transcript cannot see" as a single grey block. Drawn, it splits exactly as
`06-` said it would, and the three read completely differently on screen: the **derived** rows
(prefix, retained reasoning) are the largest thing on figure 3 at 50.7% and they look like
measurements, because they are — they are exact numbers minus estimates. The **unsized** rows
carry no mark at all and read as a refusal. The **residual** is a single row that can point the
wrong way. A design that had merged them would have been reassuring in exactly the wrong place,
and a design that drew all three as one grey block would have thrown away the best part of the
readout to protect the worst part.

**A negative residual is the strongest graphic on the page and it is an accident.** Figure 2's
ledger overruns its own window rule by a quarter of its width. Nothing was designed to make that
happen; it falls out of drawing the parts against an exact total and refusing to normalise. It is
also the figure that most obviously needs the `shed` lines above it, because without them the
overrun looks like an estimator that cannot count.

**The third level is worse on screen than it reads in the spike.** `06-` demotes it on the
evidence that it added nothing. Drawn, it also *costs* something: figure 1 at `--depth 3` is
roughly twice as tall and the extra rows are `$ cd ×34`, `$ sed -n ×6` and four `/tmp` paths. The
demotion is right, and the button is possibly one affordance too many for something that pays this
rarely.

---

## Opening it

```
proposals/ContextTreemap/mockup/index.html
```

No server, no build, no network. `?depth=3` opens every figure drilled.
