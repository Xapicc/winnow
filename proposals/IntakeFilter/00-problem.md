# The intake filter, and what it does not reach

`winnow filter` is a local pass-through proxy on `ANTHROPIC_BASE_URL`. It rewrites one
Messages API request body on its way out, and the rewrite is a single idea: a tool result
that a rule would strip is sent **in full** on the one request where the model acts on it,
placed *after* the last `cache_control` breakpoint so the API never writes it to cache, and
replaced by a pointer on every request after that. Per result of *D* tokens over *T*
following turns, the baseline is a 2.0× cache write plus a 0.1× read on every later turn;
this pays 1.0× once and nothing after ([docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5).
There is no break-even term. It is cheaper from the first request, at every `S/D`, which is
the one thing the pruner cannot say.

That is the whole of it. About 350 lines in `src/winnow/filter.py` and `src/winnow/proxy.py`,
stdlib only, 39 tests. This document is about the boundary of that mechanism: what it
reaches, what it does not, and what would have to be true before more logic goes into a
process that sits between a session and its credentials.

## What it reaches today

Two figures, from two populations, and they are not the same measurement.

**Modelled, over the corpus.** [docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5 replays the
three no-hindsight rules over the 175 sessions carrying more than 400 KB of message content:
**8.21% of message content**, **$246.14** netted, **+3.76% of the bill**, positive in **175 of
175 sessions** — by construction, because nothing already cached is ever edited. The pruner
at tier CB reaches more (10.17%) and nets less ($214.46, +3.27%), and pays off in 97 of 168.
The ratio is 1.1×. Both are dominated by the `0.1·D·T` read term; what separates them is
variance, not size.

**Measured here, 2026-08-27.** The same three rules, evaluated by importing
`winnow.filter.rule_for` and `winnow.rules.result_size` directly, over all 866 main-session
transcripts under `~/.claude/projects/` on this container — every session, with no 400 KB
floor, so a different and larger population than §3.5's:

| | Bytes | Share of message content |
| --- | ---: | ---: |
| C1 locator | 70,729 | 0.03% |
| C3 passing verification | 841,148 | 0.31% |
| B2 Bash inspection | 22,317,415 | 8.15% |
| **All three, at `min_bytes` 2,048** | **23,229,292** | **8.49%** |

against 273,722,399 bytes of message content over 48,835 distinct API requests. That is a
cross-check on §3.5's 8.21%, not a reproduction of it: the population differs, and the
agreement to a third of a point is worth exactly as much as that caveat allows. It does
establish the shape. **The intake filter is rule B2 and a rounding error.** C1 and C3 between
them are 0.34% of message content — 4.0% of what the filter removes.

The same corpus's bill, from `message.usage`, one record per `requestId` per
[docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5.2, priced at `savings.PRICES` list prices:
**$7,426.47**, of which 8.82 billion cache-read tokens and 188.9 million one-hour cache-write
tokens. Not one 5-minute write in the corpus, which is §3.4's finding holding on a larger
sample. That $7,426.47 is the denominator every figure in this proposal set is a share of.

## What it cannot reach, in three separate senses

These get run together, and they should not be. Each has a different fix, or no fix.

**1. Three of the six rules may not fire.** C2 (exact duplicate), B1 (superseded read) and
A1 (read then written) are the pruner's and stay there.
`src/winnow/filter.py:24` says they need "hindsight"; they do not, and
[01-constraints.md](01-constraints.md) argues that the real disqualifier is different and
stricter. The consequence is the same either way: on this corpus C2, B1 and A1 are the rules
that reach the *file* content, and the filter reaches almost none of it.

**2. Whole content classes are out of scope by construction.** `tool_result` is 70.30% of
message content on this corpus and `tool_use` inputs are 24.59% **[measured here]** — against
SPEC §1's 65.8% and 25.8% over its own 563 transcripts. `winnow` touches only the first, per
SPEC §4's opening sentence and DECISIONS §D3. That leaves 24.59% untouched by design, and
`Write` inputs alone are 33.92% of it — **8.34% of message content, almost exactly the size of
everything the filter reaches**. `Agent` results are 0.65% of content and MCP results are
**9.30%**, larger than the filter's whole reach, and `rule_for` matches neither.

**3. A mass no rule can decide.** SPEC §5 is the honest statement of it and it has not moved:
39.5% of `Read` bytes belong to files a run never mentions again, and nothing in a transcript
distinguishes "wasted" from "read and understood" because the thinking text is stripped
before it reaches disk — 3,903 bytes of thinking across all 866 sessions **[measured here]**,
which is the same nothing SPEC §3 found. No refinement of the rules reaches this. It is
named here so that no option below can quietly promise it.

## What the filter's own arithmetic does and does not depend on

Worth stating before any option is judged, because two of the options below turn on it.

The saving per result is `1.0·D + 0.1·D·T` at the one-hour write class. On this corpus the
median session's tail is long — [docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.4 puts the
median turns following a cut at 224 — so `0.1·D·T` is roughly `22·D` and the avoided write is
a twentieth of the saving. **Nearly all of the filter's value is that a removed result is not
re-read on every later turn.** Two consequences:

- **Reaching more bytes is worth almost exactly proportionally more.** There is no threshold
  effect and no break-even to clear. An option that reaches twice the bytes is worth twice as
  much, minus its own costs.
- **Delaying a removal by one request costs `1.0·D` and nothing else.** That is the price
  `keep_newest=1` already pays on every result it drops, and it is the currency every
  correctness option below is denominated in.

## What "more" would have to mean

The filter is in the credential path. It relays the client's auth headers upstream, holds
none of its own, logs none, and refuses to start without `WINNOW_FILTER=1` for that reason
(`src/winnow/cli.py:626`). An operator running it has put a process of their own in front of
their own key, and every line added to `filter.py` is a line running there. So "more" is not
free even when it is correct, and the bar is not "does this reach more bytes".

Three things an option has to clear:

**It has to survive [01-constraints.md](01-constraints.md) §K1.** The same conversation must
render to the same bytes on every request that carries it, or the rewrite destroys the prefix
it exists to protect. This is not one constraint among several. It is the one that decides
most of the option set, and getting the statement of it right is the first job of the next
document.

**It has to be worth a named number.** `8.49%` of message content is the whole of the
filter's present reach and it is worth `+3.76%` of the bill on §3.5's model. An option that
adds a fifth of that is adding about three quarters of a point, against a $7,426 corpus bill:
roughly $55 across 866 sessions and however many months they span. That is small enough that
"it also adds a failure mode" is a serious objection rather than a formality, and each option
below states its reach in bytes or says why it cannot.

**It has to fail the way the rest of this tree fails.** SPEC §10's discipline: fail loudly,
never silently keep or silently strip, never write to the original, and — the one this
component adds — forward the original bytes unchanged on any failure to parse or rewrite. A
capability that cannot be given up on mid-request does not belong in this process.
