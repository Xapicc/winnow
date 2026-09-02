# Option B — a cursor on the tree

A full-screen terminal application over the same tree Option A prints. Arrow keys descend and
ascend, `/` filters, `s` re-sorts, `d` opens a detail pane on the node under the cursor, `a`
drills sideways into a sub-agent's own budget. Live mode is not a flag; it is the default
behaviour of a program that is already redrawing.

*Same ten headings as `03-option-a` and `03-option-c`.*

## The strongest case

**It is the only option where the second question is free.** `03-option-a` ends by naming its
own worst property: the readout says `Bash 42,609` and the operator's next thought is *which
Bash*, and answering that costs another command, another full render and another read. In a
TUI it costs one keypress and the answer appears where the eye already is. That difference
sounds cosmetic and is not — `00-` §6's most likely cause of death is "nobody acts on it", and
what stands between seeing a number and acting on it is precisely a sequence of second
questions. An instrument that charges for each of them gets used once.

**And it is the only option that can make the floor drillable rather than merely labelled.**
`02-constraints.md`'s correction turns the invisible ~40% into two derived blocks — prefix at a
median ~24% of the window and retained reasoning at ~14%. A row in a static readout can say
`derived`. A node under a cursor can, when the operator descends into it, show the actual
arithmetic: *this session's first request was priced at 98,453 tokens; the transcript can see
4,553 tokens before it; the difference is the system prompt and the tool definitions, and it is
42.8% of your window before you typed anything.* That is the sentence that changes behaviour,
because unlike everything else on the screen it points at a configuration file rather than at a
working habit. Option A has nowhere to put it. Option C can put it in a tooltip, which is where
explanations go to die.

**Third, it is the only option whose live behaviour is not a compromise.** §C12's anchor lag
is a permanent property of the data, but a program that owns the screen can render it as a
*shape* — the priced tree solid, the un-anchored material appended since the last request
drawn as a distinct growing node at the bottom — rather than as a sentence under a header that
the operator stops reading on the fourth redraw.

## Shape

The tree model, the classifier, the apportionment and the two derived blocks are Option A's,
unchanged and shared. What is added is an application: a screen buffer, a cursor with a path
into the tree, a key map, a resize handler, and a live loop that re-walks from a byte offset
and *merges* into the existing tree rather than rebuilding it, so the cursor keeps its place
across updates.

Rendering is `curses` from the standard library, or `rich`/`textual` as an optional extra.
This is a live question rather than a detail: `pyproject.toml` declares exactly one runtime
dependency (`psutil`) and already carries the extras pattern with the right rationale attached
— the `mcp` extra exists so that `winnow list` does not pull an MCP framework. A TUI library
is the same argument in the same shape, and it belongs in the same place. `curses` avoids the
question entirely at the cost of writing the layout by hand and being useless on Windows,
which this corpus does not contain.

## What the operator sees

The same numbers as Option A — same session, same `scratch/compose_one.py` output — at a
cursor, with a status line and a detail pane. Everything in the pane below its first line is
illustrative, because no such pane has been built.

```
 e698739e  219,485 tok exact  ·  req 66  ·  no compaction        [d]etail [/]filter [q]uit
 ┌ window ─────────────────────────────────────────────────────────────────────────────┐
 │ ▸ prefix (not in the file)      93,900  42.8%  derived                              │
 │ ▾ tool traffic                  68,992  31.4%  est      ┌ detail ──────────────────┐│
 │   ▸ Bash results                42,609  19.4%  est      │ Bash results             ││
 │   ▸ tool_use inputs             18,087   8.2%  est      │ 42,609 est tok, 19.4%    ││
 │   ▸ Read results                 7,650   3.5%  est      │ estimate: chars ÷ 2.6,   ││
 │   ▸ Edit results                   646   0.3%  est      │   ±20% relative          ││
 │ ▸ retained reasoning            46,557  21.2%  derived  │ spilled results are sized││
 │ ▸ standing configuration         6,852   3.1%  est      │   at the 2 KB preview    ││
 │ ▸ conversation                   2,293   1.0%  est      │   the model actually saw ││
 │   unattributed                     891   0.4%  residual └──────────────────────────┘│
 └─────────────────────────────────────────────────────────────────────────────────────┘
```

The detail pane is the point. It is where the provenance stops being a one-word column and
becomes a sentence with the derivation in it, and it is the only place in any of the three
options where there is room to say what a number means without spending a line of the tree on
it.

## The floor, drawn

Best of the three, and by a clear margin. `prefix` and `retained reasoning` are nodes like any
other, so they sort into position by size — on a young session (`01-` §2.6 column A, 80%
prefix) they sort to the top and the operator descends into them, which is the correct
behaviour, whereas Option A's sorted list puts an unexplained unactionable row at the top and
Option C draws a rectangle covering four fifths of the screen with no way to ask why.

Under `retained reasoning` the tree continues: per-response cost from the `output_tokens`
subtraction, the thinking-block count, the median per block for *this* session rather than the
corpus's ~390 — on the worked session, 626. Under `prefix`, the first-request arithmetic and the
honest statement that the tool cannot separate the system prompt from the tool definitions
because neither is in any record (`01-` §1.2). Under `unattributed`, the residual and — per §C10
— the chars-per-token constant that would zero it, printed with the words "not applied" beside
it.

## When the data is missing, partial or lying

Every case from `03-option-a` behaves the same way, because the tree model is the same. The
difference is where the explanation goes: into the detail pane rather than onto the row. That
is better when the operator asks and worse when they do not, and a caveat nobody opens is a
caveat that was not delivered.

Two failure modes are Option B's alone:

- **No TTY.** Piped, redirected, run from a script, run in CI, run by an agent — and on this
  machine the last of those is the common case. A TUI must detect it and fall back to Option
  A's printer, which means Option A gets built either way and B is strictly additive.
- **A terminal too small for the layout.** The pane and the tree each want a few dozen columns
  — this run's guess is 30 and 60, and it is a guess about a layout nobody has drawn. Below
  whatever the real threshold is, the pane goes, and with it the only place the provenance
  explanation lives.

## Live mode

The best of the three, and the only one where "best" is worth something.

The live loop reads from a byte offset (`legacy/session.py load_messages_incremental`, which
already handles inode change, file shrink and mtime invalidation) at 250 ms against a 102 ms
median write lag. New records are classified and merged into the tree in place; the cursor's
path is preserved; a node whose size changed flashes once. `01-` §4.4's finding — poll, do not
watch, because `inotify` buys nothing against a cheap seek-to-offset on an append-only file —
applies unchanged, and the 141-line `legacy/watcher.py` is available if the tool ever needs to
notice *new* sessions appearing rather than one session growing.

§C12 is rendered as structure rather than prose. The tree is drawn from the last priced
request; everything appended since is a single node at the bottom labelled `since request 66
(4m 12s)`, growing, marked `est`, and visually separated from the anchored tree above it. When
the next assistant record lands, that node dissolves into the tree and the anchor line moves.
The operator learns the rhythm of the instrument in about two turns, and after that the
distinction between "priced" and "not yet priced" is legible without reading anything.

The in-flight `tool_use` with no `tool_result` (`01-` §4.2) is a node with a spinner and an
elapsed time, which is more useful than it sounds: it is the only place on this machine that
shows how long the tool you are waiting on has been running *and* what it is about to cost.

## Where this render wants the code to live

Either, with a shove towards its own project. As a subcommand it needs the extras question
answered (`curses`, or `textual` behind `winnow[tui]`), and the honest objection is that a
package which runs in the `PreToolUse` path should not grow an interactive application, even
one behind an extra — not because the import is expensive but because the test surface and the
release risk are now shared. As its own project it needs `03-option-d`'s copy, and the copy is
what that file argues about.

The deciding fact is that Option B is Option A plus a cursor over an identical tree model. If A
lives here, B lives here, because splitting the model across two repositories to put the cursor
somewhere else is the worst available arrangement.

## What it costs to build

Option A's cost, plus an application. The shared part — parser, walk, classifier,
apportionment, derived blocks, `--json` — is not rebuilt.

**New**, and every line count here is this run's guess about code that does not exist — read
them as an ordering, not as an estimate: the screen and layout (~300 lines of `curses`, or ~150
of `textual` plus a dependency); the cursor and key map (~150); the resize and small-terminal
paths (~80); the incremental merge that preserves cursor identity across a re-walk (~150, and
this is the part that will be fiddly, because a node's identity has to survive its parent's
re-sort); the detail pane and its per-node explanations (~200, mostly prose). Plus the no-TTY
fallback, which is Option A.

**1.6–2× Option A's build** — i.e. 0.6–1× more on top of A, which is built either way — and a
permanently larger maintenance surface: every new node kind now needs a detail-pane sentence as
well as a label, and the terminal-size and no-TTY paths need testing on every change. Against
that, the incremental live merge is the piece Option A's `--watch` fakes by redrawing
everything, so some of the cost is deferred work rather than new work.

## How it fails, and whether loudly

**Silently, and that is the objection.** The characteristic TUI failure is a number that is
correct and off-screen: the tree is scrolled, the pane is closed, the terminal is 70 columns,
the provenance column was dropped to make the layout fit — and the operator reads a figure
with none of the caveats §C2 exists to attach to it. Option A cannot do this, because it has no
layout to sacrifice.

The second silent failure is that a TUI's numbers do not leave. There is no paste, no pipe, no
`--json` unless one is built anyway, and no record of what the readout said when the decision
was taken. For an operator who works by writing things down — and this proposal set exists
because that operator does — that is a real loss, and it means `--json` and the static printer
are not optional extras of Option B, they are prerequisites of it.

## What would have to be true

**That the operator drills more than once per session.** If the answer is usually on the first
screen, the cursor is 0.6–1× more build for a keypress nobody presses. `01-` §2.6 is mildly
against B here: the six measured sessions have three-node answers. `01-` §5's H3 measurement is
mildly for it: 37 distinct `Read`/`Edit` paths on one session, with the repeats 34% of that combined
output, is a list worth navigating rather than dumping.

**That live watching is a thing the operator actually does**, rather than a thing that sounds
good. There is no measurement on this machine either way; `00-` §2 lists "am I about to
compact, and if I am, what is about to be thrown away" as one of four driving questions, which
is a live question, and `01-` §4.6's `cumulativeDroppedTokens` answers the second half of it
after the fact rather than before.

**That a terminal application in this repository is acceptable**, given that the repository's
own dependency discipline is one runtime dependency and an extras pattern justified on exactly
this ground.

---

**And the fact that most weakens it, stated plainly:** every line of Option B is spent on
navigation, and not one on knowing anything new. The tree it draws, the totals it anchors, the
floor it prices and the residual it confesses are all Option A's, computed by Option A's code,
correct to the same tolerance. What B adds is the ability to move around them faster — which
is worth having, costs another 0.6–1× of A on top of A, and is the first thing that should be cut
when the appetite runs out. `00-` §6's second killer is that `/context` is good enough; B does
not beat `/context` on anything A does not already beat it on, and it is the option most likely
to be built because it is the most fun to build.
