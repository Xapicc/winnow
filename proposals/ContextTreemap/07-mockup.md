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

---

## Postscript, 2026-09-03 — `05-` §M1's "no colour" was overridden

**The operator overrode it.** `05-recommendation.md` §M1 says "no colour" and
`render()`'s docstring used to repeat it; item 1 above lists the picture itself
as this mockup's invention on exactly that ground. Having looked at the mockup,
the operator asked for its grammar in the terminal, as ANSI. `05-` is left as
written — it is the record of what was decided then — and this is the record of
what replaced it. A future session that finds the two disagreeing should read
the disagreement as dated rather than as a bug.

What shipped, in `src/winnow/context.py`:

- **Item 4 above, and only item 4.** Colour means provenance, never category:
  the four kinds in honesty order, `unknown` given no mark. Two things per row
  carry it — the bar glyph and the kind word — and the numbers stay plain so the
  columns still read as a table. The ledger strip (item 3) and the empty states
  (item 7) are not in this slice.
- **The mockup's own hues**, mapped to the nearest slot in the fixed part of the
  xterm 256-colour cube: `exact` 68, `derived` 166, `estimated` 36, `residual`
  172. Three of the four land on the same slot from either the light or the dark
  palette. `residual` is the one that splits — light wants 214, dark wants 172 —
  and a terminal does not say what its background is, so 172 is taken: it holds
  2.9:1 against white where 214 falls to 1.8:1, and still sits 22.9 ΔE from
  `derived`, well clear of the 9.1 worst-adjacent the palette validator accepted.
  A terminal that claims no 256-colour support gets four SGR hues from its own
  theme instead.
- **The key as a row of the readout**, printed once under the session header,
  because the mockup makes it part of the page rather than a footnote. It is
  printed only when there is colour to key; the `how each kind was derived` block
  at the foot is unconditional and unchanged. The key says which colour, the
  footer says how the number was got.
- **`--color auto|always|never`**, defaulting to `auto`: colour only when stdout
  is a terminal, `NO_COLOR` is unset and `TERM` is not `dumb`. `--color always`
  is the NO_COLOR spec's own exception and overrides it. `--json` is the same
  bytes under all three.

**What did not change, and is the reason the override is safe.** Every row still
prints its own provenance word beside the colour, so the hue never carries a
claim alone — which is also what discharges the light palette's contrast warning
noted above. `winnow context <id> | cat` is byte-for-byte the readout M1 shipped.

**Also in the same slice, and not from `05-`:** the readout now takes its width
from `shutil.get_terminal_size()` rather than the hardcoded 22 and 54, clamped
so it never goes below those two together and never past a 32-column bar or a
72-column label. With no terminal and no `COLUMNS` it is exactly 22 and 54, which
is why the piped output is unchanged.

---

## Postscript, 2026-09-03 — items 2 and 3 shipped, and what drawing them settled

**Items 2 and 3 above are now in `src/winnow/context.py`.** The colour slice
above shipped item 4 alone and said so; this one adds the two marks that carry
the shape of the readout. Both were flagged there as decisions nobody had
reviewed, and both are now decided by having been built and looked at rather
than by argument. Item 1's remaining scope — the page, the caption strips, the
empty states — is still not in the terminal.

**The ledger strip (item 3), as shipped.** `derived` and `estimated` stacked
proportionally above the tree against a `┃` rule at the exact window, with a
`└──┘` bracket under the overhang in the residual colour and one line naming the
overrun in tokens. The rule sits at the window's share of `max(window, parts)`,
so on a session that fits it lands at the right-hand end and on one that does
not it moves left and there is an outside to it. That is the mockup's refusal to
normalise, kept: nothing is rescaled to fit inside the window.

It is built from `audit_rows()` rather than from the tree. That is the only
condition it exists under — `--audit` prints the window less every claim leaving
the residual, and a strip that could disagree with those rows would be a second
opinion about a subtraction with one answer. A test asserts the two equal on
every fixture.

**The diverging track (item 2), as shipped.** One scale for every row, a `│`
zero line, a quarter of the bar column for the deficit and the rest for the
positive side — the mockup's 60px against 180px, in columns.

*The hatch is dropped.* `bar()` led a negative with `-` and drew it in `▒`;
that was standing in for an axis, and once there is one it works against the
mark. The same glyph on both sides is what makes them read as one quantity
pointing two ways, where a hatched left side reads as a different quantity. The
sign is carried four other ways: the side of the zero line, the printed number,
the `residual` word and the hue.

*The quarter is measured rather than guessed.* Sweeping the 1,052 transcripts in
`~/.claude/projects`, 922 have an exact anchor and **423 of those — 46% — have a
negative residual**, which settles `02-`'s "roughly a third" upwards on a larger
corpus. Their median is **−2.6%**, the 95th percentile **−27.4%**, the worst
**−51.6%**. A quarter of 22 columns holds everything out to −31%, so 16 of the
423 clip; they are drawn to the edge, marked `«`, and a footer note says only the
drawing was shortened. Half the column would hold all 423 and spend the other
half of every row on a direction 54% of sessions never go.

**What looking at it changed, again.** Three things.

- **The strip is capped at the terminal, and the tree row is not.** A tree row
  that wraps at `COLUMNS=80` is ugly; a *proportion* that wraps is not a
  proportion. So the strip takes the tree row's width or the terminal's,
  whichever is smaller, and at 80 columns it is visibly shorter than the rows
  beneath it. That mismatch is the price of the mark staying a mark.
- **A sub-column overrun still gets a column.** 90% of negative residuals are
  smaller than 0.4% of their window and round to nothing at any width. One
  column of the strip is drawn on the wrong side of the rule anyway, because the
  fact the mark exists to state is that there *is* an outside to the rule; the
  sentence beneath says it was one token when it was one token.
- **`░` for the positive residual is the faintest thing on the page, and that
  is right.** The four glyphs are a density ramp down the honesty ladder —
  `█ ▓ ▒ ░` for exact, derived, estimated, residual — so `--color never` tells
  the segments apart by ink as well as by hue. Room left over in the window
  drawn as the palest block reads as what it is. It is also never the mark that
  has to shout: when the residual is the thing that matters it is negative, and
  then it is the bracket and the sentence, both in solid ink.

**One line of the postscript above is now dated.** `winnow context <id> | cat` is
no longer byte-for-byte M1's readout: it has the strip in it. Everything that
claim was protecting still holds — no escape byte, every row still printing its
own provenance word, `--json` identical under all three `--color` choices, and
`--audit`'s reconciliation unchanged.
