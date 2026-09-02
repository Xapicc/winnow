# Option A — one command, one screen, no interaction

`winnow context <session-id>` walks the transcript once, prints a sized tree biggest-first to
stdout, and exits. No cursor, no server, no state, no second surface. `--depth` controls how
far down it goes and `--json` emits the same tree for anything else to consume. Text.

*This file and `03-option-b` / `03-option-c` answer the same ten headings, so
`04-comparison.md` is a table over a fixed set rather than over three arguments.
`03-option-d` is on a different axis and does not take them.*

## The strongest case

**It is the option whose only output can be pasted, and that is a stronger claim than it
sounds.** Every question in `00-` §2 is asked at least as often *about a session that is over*
as about one that is running — "this session cost four times what the last one cost, what is
different about it" is asked the next morning, into a chat window, to a colleague or to a
model. A one-shot readout's answer is forty lines of text that go straight into the thing that
asked the question, and its `--json` goes into the next tool without a parser.

B and C can print too — they contain this printer, and `04-comparison.md` scores all three
alike on it for exactly that reason. What they cannot do is make it the *default*. An operator
who has a TUI reaches for the TUI, gets the answer inside it, and then has to leave and re-run
the thing in a second mode to have anything to paste; the readout that already exists in a
scrollback buffer costs nothing to quote. A capability table cannot see that difference, and on
this machine — where the most frequent reader of any output is a model that was handed a
transcript — it is worth more than the two points the table gives B.

Second, and less obvious: **the operator's question is a ranking question, and a ranking is a
list.** `01-` §2.6 measured six sessions and in every one `tool-result` + `tool-use` is 62–91%
of everything the file can see, with the top three tools accounting for nearly all of that.
"What is the biggest thing in here" has, empirically on this corpus, a three-line answer. A
sorted list with a bar is the best possible instrument for a three-line answer, and a
drillable rectangle diagram is a worse one dressed up.

Third: it is the only option that is honest about cost. `01-` §6.1 establishes that the walk
already exists (`inspect.py:330 inspect_session`), the resolution already exists
(`report.py:47 resolve_session`), and the tolerant parser already exists with its postmortems
attached (`legacy/session.py:722–1037`). What Option A adds is arithmetic and a printer. The
other two options add arithmetic, a printer, and an application.

## Shape

One pass over the records. Dedupe assistant responses on `message.id` (§C8). Take the exact
window from the anchoring request's `usage` (§C3), resetting at every `compact_boundary`
(§C6). Classify every surviving content block into the provenance hierarchy — `01-` §5's H1 —
counting payload characters per `01-` §2.4 and nothing else (§C4). Measure the prefix by
first-request subtraction and retained reasoning by the `output_tokens` subtraction
(`02-constraints.md`, the correction). Apportion. Sort. Print.

The tree is a plain nested dataclass with four fields — label, tokens, provenance, children —
and the printer is a recursive walk over it with a depth cap. `--json` dumps the same
structure. There is no other state in the program.

## What the operator sees

Every number below is real and reproduces: `scratch/compose_one.py e698739e`, added by this
run. The layout is the only invented thing in the block.

```
session e698739e-…  ·  66 requests  ·  no compaction  ·  claude-opus-5
window at request 66                             219,485        exact

  ████████████████  prefix (not in the file)       93,900  42.8%  derived
  ███████████       tool traffic                   68,992  31.4%  est
       ███████        Bash results                 42,609  19.4%  est
       ███            tool_use inputs              18,087   8.2%  est
       █              Read results                  7,650   3.5%  est
       ▏              Edit results                    646   0.3%  est
  ████████          retained reasoning             46,557  21.2%  derived
                      28 thinking blocks · 626 tok/block median
  █                 standing configuration          6,852   3.1%  est
  ▏                 conversation                    2,293   1.0%  est
  ▏                 unattributed                      891   0.4%  residual

exact 219,485 · derived 140,457 (64.0%) · estimated 78,137 (35.6%) · residual 891 (0.4%)
```

At `--depth 3` each tool opens further — Bash by command head, `Read` and `Edit` by path with a
repeat count, `mcp__*` by server then tool. On session `f6ea2591` that level is 37 distinct
`Read`/`Edit` paths of which the ones touched more than once are 34% of the output (`01-` §5).

Four things that readout does which nothing on this machine does today. It states an exact
window total and makes every other row add up to it. It prices the two blocks that are not in
the file — here 64.0% of the window, which is exactly the "invisible to the file" share `01-`
§2.6 measures for this session by a different route — and labels them `derived` rather than
hiding them or greying them out. It names the biggest visible thing and it is a *tool*, not a
category. And the last line lets the operator see, without reading a manual, how much of the
picture survives an argument about the chars-per-token constant: 64.0% is derived from exact
anchors, and only the 35.6% marked `est` moves.

This particular session is also the argument against reading any single readout as typical. Its
prefix is 42.8% where the corpus median is ~24%, because its first request already carried
98,453 tokens — the number `00-` §6 uses to name the way this whole proposal might be wrong.

## The floor, drawn

As two rows and a residual, per `02-constraints.md`'s correction: `prefix` and `retained
reasoning` are first-class nodes marked `derived`, and `unattributed` is what is left after
both — a median ~0.5% of the window rather than the ~40% a visible-only tool would have to
confess.

Option A's specific advantage here is that a `derived` label in a text column is exactly as
legible as an `exact` one. The three provenance kinds are three words in a column, aligned,
sortable, greppable. Neither of the other options can make the distinction that cheaply: a TUI
has to spend a colour or a glyph on it, a treemap has to spend a fill pattern, and both are
weaker signals than the word.

Its specific disadvantage is that a sorted list gives the top row to whatever is biggest, and
on a great many sessions that is the prefix — 42.8% on the worked example above, 80% on `01-`
§2.6 column A, a corpus median of ~24%. The operator opens the tool and the first thing they
see is a row they cannot act on without being told why, and a printed line has no room to tell
them beyond the six words in its label. `--explain prefix` fixes it and costs a flag; nothing
fixes the fact that they have to know to ask.

## When the data is missing, partial or lying

- **No `usage` anywhere** (a session that only ever errored): there is no exact anchor, so
  §C3's architecture does not apply. It prints the estimated tree, prints **no percentages**,
  exits non-zero, and names the missing anchor in one line.
- **Ambiguous or unknown session id**: `report.py:47 resolve_session` already raises rather
  than exiting, and takes an unambiguous prefix. Inherit it.
- **Compaction present**: reset per §C6, and print `cumulativeDroppedTokens` as an exact line
  above the tree. This is a feature, not a degradation — it is a number `/context` cannot show.
- **`<persisted-output>` spill**: sized at the preview, labelled as a pointer, with the sidecar
  size in the label (§C9).
- **Hook-rewritten result**: a one-line banner if any `winnow: … removed` marker is present,
  because the readout is then measuring a hooked install (§C9).
- **Unparseable image header**: node sized zero, labelled, never guessed from base64 (§C5).
- **Torn trailing line**: buffered, not advanced past; the tree renders without it (§C8).
- **Unknown window size**: no fullness figure at all unless `--window` is given (§C7).

The pattern is: a static readout can afford to *print the reason on the line where the number
would have been*, because it has a whole line and no layout to preserve. That is its best
degradation property and neither other option matches it.

## Live mode

`--watch` re-runs the walk on an interval and redraws the block. Against a ~102 ms median file
lag (`01-` §4.2) a 250 ms interval is indistinguishable from instant, and the readout is short
enough that a full redraw with a cursor-home is simpler and more robust than any incremental
scheme. The incremental byte-offset read (`legacy/session.py load_messages_incremental`) is
available if the p99.5 session's 8 MB makes a full re-walk too slow, and it probably will
past a few hundred requests.

§C12 is honoured with two lines under the header:

```
exact as of request 66, 4m 12s ago   ·   +18,400 est tokens appended since
in flight: Bash (no result yet, 4m 06s)
```

That is the whole of live mode in Option A, and it is genuinely adequate: the operator running
`winnow context <id> --watch` in a second pane gets the composition updating beside their work,
with the honest statement that the total is a request behind.

What it cannot do is keep a place. Every redraw is the whole tree from the root, so an operator
who has drilled into `Bash` by passing `--depth 3` sees the whole tree again, re-sorted, and
has to find their row. On a fast-moving session the rows move under the eye.

## Where this render wants the code to live

Here, as a subcommand. It adds no dependency — the whole render is `str.ljust` and a block
glyph — so it does not strain `pyproject.toml`'s single runtime dependency on `psutil`, and it
does not force the extras question that `03-option-b` and `03-option-c` both force. It also
sits naturally beside `winnow inspect`, which it supersedes: `inspect` reports byte share
against a file-bytes denominator and prints `cache_read_input_tokens 18,378,780` for a session
whose window was 219,485 (`01-` §6.1). Shipping the right instrument next to the wrong one, in
the same binary, is the cheapest possible way to retire the wrong one.

## What it costs to build

**What already exists**, verified by `01-` §6.1 rather than assumed: the tolerant JSONL parser
with byte-offset incremental reads (`legacy/session.py:722–1037`); the one-pass block walk that
already pairs `tool_use`↔`tool_result` by id (`inspect.py:330`); session resolution from an id
or an unambiguous prefix (`report.py:47`); the exact-window extraction (`legacy/tokens.py:297
extract_usage_tokens`); Bash command-head normalisation and read-range primitives
(`winnow/rules.py`); the record and block accessors (`legacy/helpers.py`, ~120 useful lines
inside 1,011).

**What is new.** The payload-character counter per `01-` §2.4 — the existing ones count file
bytes and are wrong for this. The compaction-aware accumulator (§C6). The `message.id` dedupe
in front of `usage` (§C8) — `savings.py:357` has the idea but inside a cost model. The
apportionment (§C3). The two derived blocks. The classifier into H1. The printer. The
`--json` shape. Call it 600–900 lines of new Python and two days of argument about the
classifier's category boundaries, which is the part that will actually take the time.

**What must not be imported**: the rule engine, the guard, the proxy, `team.py`, anything that
touches `~/.winnow` at import. This is a testable claim, not an intention — see
`05-recommendation.md`'s guardrail on `sys.modules`.

## How it fails, and whether loudly

**Loud, and this is its best property.** Every failure mode above ends in a printed line: a
missing anchor prints a reason and exits non-zero; a divergence between file and wire prints a
label; an unparseable header prints a zero with a cause. There is no layout to preserve and no
frame budget to hit, so the tool is never tempted to drop a caveat to make room.

The one silent failure is misclassification. If a block lands in the wrong category the total
is still exactly right (§C3) and the readout is confidently, invisibly wrong about *where* the
window went — which is the only kind of error this instrument can make that the operator
cannot catch. The residual node does not catch it either, because misattribution conserves the
sum. The only defence is the golden fixture, and `05-recommendation.md` treats it as
mandatory rather than nice.

## What would have to be true

**That the answer is usually visible at depth two or three.** The evidence is favourable — `01-`
§2.6's six sessions all have a three-node answer, and `01-` §5's H3 measurement on session
`f6ea2591` found 37 distinct `Read`/`Edit` paths of which the repeats are 34% of that output,
which is a list of five rows, not a tree to navigate. If instead the operator's real pattern is
"open it, look, descend, look, descend", then re-running a command with a different `--depth` is
a bad cursor and `03-option-b` wins on the same tree model.

**That a static picture of a live session is worth having.** §C12 says the exact number is a
request behind no matter what renders it, so the question is only whether a redrawing block of
text is a usable live instrument. It is, for watching; it is not, for exploring.

---

**And the fact that most weakens it, stated plainly:** it cannot answer the second question.
The readout says `Bash 42,609`, the operator immediately asks *which* Bash, and Option A's
answer is to type another command with a bigger `--depth` and read a longer wall of text with
the same rows at the top. Every session, every time. `00-` §6 names "nobody acts on it" as the
most likely way this whole proposal dies, and the distance between seeing a number and acting
on it is measured in exactly these follow-up steps. A tool that makes the first question free
and the second question cost a full re-render and a re-read has not made the loop cheap; it
has moved where the expense sits.
