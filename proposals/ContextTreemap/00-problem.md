# The operator cannot see what is in the window

*Research run, 2026-09-02. Branch `uf/winnow-f1c01ae726fd-1-ae96c68b`. This file states the
problem and what an answer would have to look like; `01-what-is-knowable.md` is the ground
truth — every number below is measured there and cited back to the script that produced it.
Nothing here designs a tool, picks a language or writes a spec. That is a later run's job,
and this is what it should read first.*

---

## 1. The situation

A Claude Code session is a window that fills up, and the operator watches it fill from
behind a single number. The statusline says `47% context used`. The autocompact warning
says `Context low (12% remaining)`. Then the session compacts, or it does not and the
session dies, and either way the operator has learned nothing about *what* filled it.

That number is not wrong. It is complete for cost and useless for cause. `/context` does
better — it draws eleven flat categories over a grid of block glyphs — but it is live-only,
one level deep, and its machine-readable export drops the two biggest rows. Nothing on this
machine, and nothing this run could find in the wild, shows an operator the composition of
a context window the way TreeSize shows them a disk: every block sized by what it costs,
biggest first, and drillable until you reach the thing you can actually delete.

The proposition under investigation is a command-line tool pointed at one session id that
does exactly that, in two modes — a finished transcript on disk, and a session still being
appended to.

## 2. Why the operator wants it

Because the money is in the carrying, not the generating. This machine's own measured cost
structure is **60.7% cache read, 26.3% cache write, 12.9% output** — 87% of the bill is
paid to keep material in the window rather than to produce anything.[^1] Whatever went in
early is re-read on every turn until the session ends. A 40 KB file read in turn 3 that was
never needed again is not a 40 KB mistake; it is a 40 KB mistake multiplied by every
remaining turn.

So the operator's real questions are all shaped the same way:

- **What is the biggest thing in here, and did I need it?**
- **How much of this window is one tool? one file? one sub-agent's return?**
- **Am I about to compact, and if I am, what is about to be thrown away?**
- **This session cost four times what the last one cost. What is different about it?**

None of these is answerable from a percentage. All of them are answerable from a
composition, and a composition is a tree.

## 3. What exists today, and exactly where each thing stops

| | what it shows | why it is not this |
|---|---|---|
| statusline | one scalar, `used_percentage` | the statusline JSON contract exposes `context_window.{total_input_tokens, output_tokens, context_window_size, current_usage, used_percentage, remaining_percentage}` and no category split at all, so every third-party statusline is structurally capped at one number |
| `/context` | eleven categories plus three per-item tables | see below |
| `ccusage`, session-report, receipts, Dash0/OTel | tokens and dollars per day / session / billing block | cross-session **cost**, never single-session **composition**; the OTel `type` attribute splits cache class, not context category |
| transcript→HTML viewers | the conversation, readably | they render messages; they do not price or bucket them |
| `winnow inspect` (this repo) | byte share by content class and by pruning rule | denominator is file bytes, not window tokens; its `cache_read_input_tokens` is a lifetime sum over every assistant record, not the window — 18,378,780 on a session whose window was 219,485 |
| `/workspace/VibeHub` `research/census/token_spend.py` | where read-spend goes, first-read vs re-read | ASCII tables, offline, research one-off |
| `/workspace/WinnowWeb` `CompositionDemo.tsx` | a two-bar stacked split over 563 transcripts | a marketing figure, not an instrument, and not per-session |

`/context` deserves its own paragraph, because it is both the closest prior art and the
clearest statement of the gap. Its eleven category labels, read out of the 2.1.226 binary on
this machine, are: `System prompt`, `System tools`, `MCP tools`, `MCP tools (deferred)`,
`System tools (deferred)`, `Custom agents`, `Memory files`, `Skills`, `Messages`,
`Autocompact buffer` (or `Compact buffer`), `Free space`.

It is more than a flat bar, and the earlier draft of this file was unfair to it. Running
`claude -p "/context"` on this machine emits, beneath the category table, **three per-item
drill-downs**: `Custom Agents` (agent type, source, tokens), `Memory Files` (type, path,
tokens — `User`, `Project` and `AutoMem`), and `Skills` (skill, source, tokens — e.g.
`dataviz  Built-in  ~380`). So one level of hierarchy already exists, for three of the eleven
categories, and per-skill token costs that the operator's own knowledge vault records as
"not published anywhere" are simply printed.

What has no drill-down at all is the row that is 60–90% of a working session: `Messages`.
That is where the operator's questions live, and it is a single number.

And the CLI already computes the drill-down. The same code path builds a `messageBreakdown`
object carrying `toolCallTokens`, `toolResultTokens`, `attachmentTokens`,
`assistantMessageTokens`, `userMessageTokens`, `redirectedContextTokens`,
`unattributedTokens`, and — this is the one that matters —
`toolCallsByType: {<toolName>: {callTokens, resultTokens}}`. That is the first level of a
treemap, computed exactly, and it is discarded at the render boundary. It surfaces only
indirectly, through five hardcoded suggestion rules whose savings estimates are literals
(`Math.floor(tokens * 0.2)`, `* 0.3`) rather than measurements.

**The gap in one sentence: the harness computes the composition, drills into the three
categories that matter least, discards the drill-down for the one that matters most, and
hands downstream tools a single scalar.**

## 4. What a tool would have to be honest about

This is the part a design run will want to argue with, so it is stated flatly and the
evidence is in `01-what-is-knowable.md`.

**The transcript is not the window.** Across 161 uncompacted sessions, the median context at
the last request was 163,545 tokens, of which the transcript could account for a median
85,664. The missing **42.5%** is a floor that no amount of parsing removes (§3 of `01-`).
Roughly 31,000
tokens of it is the system prompt and tool definitions, which appear in no record of any
transcript; most of the rest is retained reasoning, measured at ~670 tokens per thinking
block against blocks whose text is stripped to zero on disk.

**The file is bigger than the window and differently shaped.** A `toolUseResult` envelope
sits beside every tool result carrying the *full* output; the block the model actually saw
may be a 2 KB preview pointing at a sidecar file. There are 565 such sidecars on this
machine holding 204.9 MB that never entered any context. A TreeSize over file bytes would
draw a picture dominated by things the API never saw.

**Bytes are not tokens, and the usual fudge is wrong by a third.** Three independent methods
put this corpus at **≈2.6 characters per token**, not the folkloric 4. And no tokenizer is
installable here — no network, nothing cached, and Anthropic's tokenizer is not public — so
the only exact numbers available offline are the ones the CLI already wrote into `usage`.

**Some of it is exact and free.** `usage.input_tokens + cache_creation_input_tokens +
cache_read_input_tokens` is the true size of the window at that request, written down, on
disk, for every API call. Compaction boundaries carry exact `preTokens`, `postTokens` and
`cumulativeDroppedTokens`. The right architecture is therefore not "estimate everything" but
"take the exact total from `usage` and use the estimate only to apportion it" — which turns
a 30% sizing error into a much smaller *relative* error inside a known total.

## 5. The shape of an answer

A later design run has to settle three things, and `01-what-is-knowable.md` §5 lays out the
candidates rather than choosing:

1. **What the tree is.** A filesystem has one obvious hierarchy; a context has at least
   three defensible ones (by provenance, by chronology, by artefact) and they answer
   different questions. Picking one is the central design decision, and picking wrong makes
   the tool a chart.
2. **What the tool claims.** "This window is 219,485 tokens" is exact. "Bash output is 65% of
   it" is an estimate of a share of a number that excludes the prefix. Those two sentences
   cannot sit in the same readout without a label, and the readout has to say which question
   it is answering — the same discipline `04-option-see-it.md` imposed on its own card.
3. **Whether the floor is acceptable.** A treemap that silently omits 42.5% of the window is
   a lie by omission. A treemap that draws the missing 42.5% as one grey block labelled
   *system prompt, tool definitions and retained reasoning — not in the file* is honest, and
   is arguably the most useful block on the screen, because it is the one the operator can
   act on by changing configuration rather than by working differently.

## 6. What would kill it

Stated up front so nobody has to discover it late. In descending order of how likely each is
to be fatal:

- **The invisible half is the interesting half.** If the operator's real question is "why is
  my prefix 98,000 tokens" — and on one of the six sessions measured here the *first request*
  already carried 98,453 tokens before any work happened — then a transcript-only tool cannot
  answer it, and the honest instrument is a proxy sitting on the request body. This repo
  already built one (`src/winnow/filter.py:728 prefix_facts`).
- **`/context` is good enough.** Eleven flat categories, live, built in, zero install. The
  treemap has to beat that on the drill-down, and the drill-down is precisely the part built
  on estimates.
- **Nobody acts on it.** `04-option-see-it.md` put this best about its own proposal: *"If
  nobody would act on it, it is a chart."* The actions available to an operator who sees a
  giant `Read` block are narrow — read less, read with `offset`/`limit`, prune, restart. A
  tool that only produces regret is a toy.

---

[^1]: `~/.claude/projects/-Users-hendrikkuehnel-Documents-GIT-UsageFoundry/memory/usagefoundry-cost-structure.md`, this machine, not re-measured by this run.
