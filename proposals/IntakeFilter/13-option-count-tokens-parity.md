# Option K — filter `/v1/messages/count_tokens` too

**Verdict: keep the exclusion, and correct the reason given for it.** The decision is right and
the sentence in the code that defends it reads backwards. The consequence it was defending
against is real, it is not closed by either choice, and which way it should be closed turns on
one fact nobody here can establish.

## What is excluded, and how

`proxy._is_filtered` (`proxy.py:66-73`):

```python
def _is_filtered(path: str) -> bool:
    """Exact match on the path, query string discarded.

    Not a prefix test: `/v1/messages/count_tokens` starts with `/v1/messages`,
    and filtering it would make the count disagree with the request it counts —
    the caller would size a body the real request never sends.
    """
    return path.split("?", 1)[0].rstrip("/") in _FILTERED_PATHS
```

with `_FILTERED_PATHS = frozenset({"/v1/messages"})` (`proxy.py:63`).
`test_a_path_that_is_not_messages_is_relayed_verbatim` (`tests/test_filter.py:373-386`) holds
it, and [docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5 lists it as one of four implementation
properties each with a test: *"It was, on the first version, because the path test was a prefix
match — which would have made the count disagree with the request it counted."*

## The reason is inverted

Trace it. The client holds conversation *X*. It asks `count_tokens` about *X* and gets
*N*(*X*). It then sends `/v1/messages` with *X*, the filter rewrites it to *X′*, and the API
bills *N*(*X′*).

So under the current behaviour **the count describes *X*, and the request that goes out is
*X′*.** The docstring's own words — *"the caller would size a body the real request never
sends"* — are a description of what happens *because* `count_tokens` is excluded, and they are
offered as the reason for excluding it. Filtering the count would make it agree with the wire,
not disagree.

The decision is nonetheless correct, on reasons the docstring does not give:

**There is no saving to be had.** The filter exists to keep bytes out of a *cache write*. A
`count_tokens` request writes nothing to any cache and is not billed for input at all. Rewriting
it cannot save a token, so the entire upside of touching it is zero and only the risk remains —
which is §K6's discipline applied before the fact rather than after.

**It is a different endpoint with a different response and a different failure mode.** The
proxy would be rewriting a body whose only purpose is to be measured, in a process whose stated
promise is that it *"must not be the thing that breaks a run"*. `_rewrite`'s passthrough covers
a filter that raises; it does not cover a filter that succeeds and produces an answer the
client then acts on wrongly.

**And the two bodies are not the same body anyway.** The client counts *X* and then sends
*X* plus one more turn. `keep_newest` exempts the newest result, so the filter's decision on the
counted body and on the sent body differ by construction — a result deferred in the count is
dropped in the request. Filtering `count_tokens` would produce a number that is closer to the
wire than today's and still not equal to it, which is the worst of the three positions: an
estimate that looks exact.

**Recommendation: keep the exclusion, rewrite the docstring.** The current one will mislead the
next person who reads it, and it is cited approvingly in COZEMPIC §3.5, so the error has already
propagated once.

## The real consequence, which neither choice closes

**The client's own picture of the conversation is larger than what goes out, by whatever the
filter removed.** On this corpus that is 8.49% of message content — 9.15% against a denominator
with MCP image blocks excluded ([00-problem.md](00-problem.md)). Three things read that
picture, and the filter has no channel to correct any of them.

**1. The context meter.** Cosmetic, and the operator can be told.

**2. Auto-compaction, and this one is serious.** [docs/SPEC.md](../../docs/SPEC.md) §2 puts
compaction at the top of the table of things this project exists to avoid: *"[i]rreversible by
construction… AppWorld full context 85.7%, summary 72.8%; constraint violation 0% → 30% after
one compaction. Costs −66.1 points of cache hit rate."* SPEC §6 measures 12.6% of sessions
carrying a boundary, and DECISIONS §Q4 refuses to fork a compacted session at all because the
transcript and the prefix have stopped describing the same thing.

If Claude Code decides when to compact from a quantity that reflects the *unfiltered*
conversation, then **the intake filter brings compaction forward** — and it does so invisibly,
while reporting a saving. A component that buys +3.76% of the bill and pays for it with an
earlier irreversible summarisation is not obviously ahead, and nothing in
[docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5's cost model prices a compaction at all.

If instead it decides from the response's own `usage` — `input_tokens + cache_read +
cache_creation`, which is what the API actually billed — then the filter's saving extends the
session automatically and this whole worry evaporates.

**Which of those it is, is not establishable from this repository, and it is the highest-value
unanswered question about the filter that is not milestone 3.**

**3. The CLI's own tool caps.** `ContextControl/02-` established that
`CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS` is enforced *"against a `/v1/messages/count_tokens`
answer, not against a count the CLI takes locally — re-run with a recorder returning a fixed
1,000 tokens for every `count_tokens` call, the cap did not fire at 1,000, 2,000 or 8,000."*
That is direct evidence that `count_tokens` answers drive real CLI behaviour rather than only a
display, so the question in (2) is a live one and not a theoretical one. It is not the same
call — that count is of a file's contents, not of the conversation — but it establishes the
mechanism.

## The measurement that would settle it

Two runs, no code:

1. Run `winnow filter --verbose` with a ledger, work a session past 150k of context, and record
   the turn index at which the CLI's context indicator crosses each decile and at which
   auto-compact fires.
2. Run the same task with `touch ~/.winnow/filter-off` — the kill switch keeps the proxy
   relaying and stops the rewriting (`proxy.py:126-156`), so the *only* difference is the
   rewrite.

If the indicator tracks the ledger's `bytes_dropped`, the filter is already extending the
session and the exclusion costs nothing. If it does not, the filter is shortening the session
in the unit that triggers compaction while lengthening it in the unit that gets billed, and
that belongs in every readout the tool produces.

`winnow trial` (`cli.py:704-765`) is the right frame for the second half of it: interleaved
arms, billed usage, and a `--tasks` count so the comparison lands on $/task rather than on
tokens. It has never had an arm recorded.

## If the answer comes back badly

Two responses, and the first is better.

**Report it.** The proxy already knows the divergence exactly — `plan.bytes_dropped` is the
number, per request, and it is already in the ledger (`filter.py:319-347`). A `--verbose` line
saying *"this request went out N bytes smaller than the conversation the client is holding"*
costs nothing and turns an invisible discrepancy into a visible one. Combined with
[12-option-prefix-readout.md](12-option-prefix-readout.md)'s fixed-prefix sizes it would give,
for the first time, the whole request accounted for: system, tools, held conversation, sent
conversation.

**Or filter the count after all**, accepting that it is an estimate. It would move the client's
picture toward the wire, and in the direction that *delays* compaction. Against it: the reasons
above, and one more that is decisive if the mechanism in (3) generalises — a `count_tokens`
answer that the CLI uses to decide whether to truncate a tool result would then be decided by a
body the CLI did not construct, so the filter would be reaching through the count into a
different subsystem's behaviour. That is a long way from "drop a tool result before it is
written to cache".

## Which constraints it strains

- **§K1** — none directly, and one worth naming: filtering `count_tokens` would mean the same
  conversation has two renderings for two purposes, both derived deterministically. That does
  not break cache stability, since nothing about a count is cached, but it doubles the number
  of things that have to be true at once.
- **§K6** — the whole of the case for the exclusion. Zero upside, non-zero downside.
- **§K10** — the docstring is a silent-fallback hazard of the documentation kind: a reader who
  trusts it will draw the wrong conclusion about which body the count describes, and SPEC §10's
  "fail loudly" applies to explanations as much as to code.

## What it breaks

Nothing, in the recommended form. The docstring change is a docstring change; the divergence
line is one `print` behind `--verbose`.

## The strongest case against keeping the exclusion

**That "there is no saving to be had" measures the wrong thing.** The filter's value is not only
the tokens it avoids; it is the turns it buys before a session hits the wall. If compaction is
triggered on a count the filter is deliberately leaving stale, then the exclusion is spending
the filter's entire benefit on a display, and the honest accounting is not +3.76% of the bill
but +3.76% of the bill *and one compaction earlier*, whose cost SPEC §2 puts at 13 points of
task success and 66 points of cache hit rate.

That case cannot be answered from here, and this file does not pretend to answer it. It is
recorded as the reason the recommendation is "keep the exclusion **and run the measurement**"
rather than "keep the exclusion". A decision that is right for reasons nobody has checked is
the thing this repository's own COZEMPIC §3.1 exists to be embarrassed about.
