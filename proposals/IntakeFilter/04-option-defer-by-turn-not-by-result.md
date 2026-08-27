# Option B — count the deferral in turns, not in results

**Verdict: take it.** It is the only option in this set that costs almost nothing, restores a
guarantee the design already claims, and needs no new capability at all.

This one is not on the brief's list of seeds. It came out of running `filter.apply` against a
request shaped the way Claude Code shapes a parallel tool-call batch, which none of the 39
tests in `tests/test_filter.py` does.

## What is wrong

`src/winnow/filter.py:10-16` states the mechanism: *"[a] tool result that a rule would strip is
sent in full on the one request where the model actually acts on it… On the next request it is
gone."* `DEFAULT_KEEP_NEWEST`'s own comment (`filter.py:50-55`) repeats it: *"a candidate is
sent uncached on the request where the model acts on it and dropped on the next."*

The implementation counts results, not requests:

```python
exempt_from = len(results) - keep_newest
exempt_ids = {id(results[i][2]) for i in range(max(0, exempt_from), len(results))}
```
`filter.py:275-276`.

`results` is every `tool_result` in the body in wire order. When the model issues several tool
calls in one turn, the API carries them as several `tool_use` blocks in one assistant message
and several `tool_result` blocks in one user message. With `keep_newest = 1`, **only the last
result of that batch is exempt. The rest are replaced by pointers on the very request that was
carrying them to the model for the first time.**

Confirmed by running it. A body with one assistant message holding `Bash ls -la`,
`Bash git status` and `Glob **/*.py`, and one user message holding their three 3,000-byte
results:

```
a  '[winnow: Bash result removed, rule B2, 3000 bytes. Not cached, not stored…'
b  '[winnow: Bash result removed, rule B2, 3000 bytes. Not cached, not stored…'
c  'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'   (deferred)
```

The model asked three questions and got one answer and two receipts. That is not what the
docstring says the filter does, and it is not what §3.5's cost model prices: the model prices
`1.0·D` for *one* uncached send, and these results are never sent at all.

This is **not** a §K1 violation. Those results render as a pointer from their first request
onwards and never change, so they are perfectly monotone and no cache is harmed. It is an
information failure, and it is invisible in every number the filter reports — the ledger
records them under `dropped` exactly like any other removal, and `winnow savings` prices them
as a saving.

## How often, and how much

**Measured here, 2026-08-27**, over the 866 main-session transcripts on this container.
Requests are reconstructed by grouping `tool_use` blocks on `requestId`, which is what
[docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5.2 established is one API turn however many
records it left on disk.

| | |
| --- | ---: |
| API requests that issued at least one tool call | 54,259 |
| …that issued **two or more** (a parallel batch) | 8,456 — **15.58%** |
| Batch-size distribution | 1: 45,803 · 2: 7,490 · 3: 473 · 4: 340 · 5: 63 · 6: 22 · 7: 43 · 8: 15 · 9: 2 · 10: 8 |

| | Results | Bytes | Share of the filter's reach |
| --- | ---: | ---: | ---: |
| Filter-claimed (C1/C3/B2, ≥ 2,048 B) | 4,709 | 23,229,292 | 100% |
| …in a **non-final slot** of a batch ≥ 2 | 711 | 3,516,979 | **15.14%** |

**One byte in seven that the filter removes is removed before the model has read it**, across
332 of the 866 sessions. On the corpus that is 1.28% of all message content.

## What the change is

Group `results` by the message they sit in, and exempt the last `keep_newest` **groups**
rather than the last `keep_newest` entries. At `keep_newest = 1` that is exactly the
docstring's own sentence, expressed the way the mechanism means it: *a result is exempt on the
request where it first appears.* The rest of `apply` is unchanged — `newest_candidate` becomes
the *earliest* exempt candidate rather than the latest, so `_place_breakpoint_before` puts the
boundary in front of the whole batch instead of in front of its last member.

## What it costs

Two terms, both of them one extra 1.0× send on one request.

**The results that are now deferred instead of dropped:** 3,516,979 bytes.

**Collateral — results in the same batch that no rule claims, and that now fall outside the
cached prefix for that one request** because the breakpoint moved in front of the batch rather
than into the middle of it: **1,471,491 bytes**, 0.54% of message content. This is real and it
is the reason the option is not free.

Together, 4,988,470 bytes. At SPEC §6's bytes ÷ 4 estimate and Opus base input of $5/M
(`savings.PRICES`), **$6.24 across the whole corpus — 0.084% of its $7,426.47 bill.**

The saving those bytes were producing is not lost, only delayed by one request: they are
dropped on the next one, and the `0.1·D·T` term, which is where the filter's value actually
lives ([00-problem.md](00-problem.md)), is untouched.

## What the current behaviour costs, which is the other side of it

Not derivable from this corpus, and the reason is that the counterfactual has never happened:
the filter has not run over these sessions, so no result was ever taken away before the model
read it, and there is no re-fetch to count.

What can be bounded. The pointer's own text is *"Re-run the call if it is needed again"*
(`filter.py:93-96`), and a model that follows it spends one more assistant turn. Mean billed
cost per API request on this corpus is **$0.152** (mean cache read 180,550 tokens per
request). If every one of the 708 affected batches provoked one extra turn, that is
**$107.67** — seventeen times the $6.24 the change costs. **The change pays if more than
about 6% of the affected batches cause a single extra round trip**, and it pays in correctness
whatever the rate is.

The measurement that would settle the rate: run the filter with a ledger, then count, in the
transcripts of filtered sessions, calls whose `(name, canonicalised input)` matches a
`tool_use_id` the ledger recorded as `dropped` on the request that first carried it. That is
SPEC §9's re-fetch guardrail — *"[s]tripped-then-re-read events < 1 per session at the
median"* — pointed at the filter instead of the pruner, and it needs the filter to have been
running, not more code.

## Which constraints it strains

- **§K1** — none. The change makes one more result monotone-with-a-sanctioned-transition
  rather than monotone-and-wrong, and the sanctioned transition is the deferral the filter
  already owns.
- **§K4** — none. It moves one breakpoint to a different position; it does not ask for a
  second.
- **§K7** — the ledger's `deferred` list grows and its `dropped` list shrinks by the same
  results on that one request. `savings.Removal.first_kind` (`savings.py:127`) already records
  *"'deferred' or 'dropped', whichever the result appeared as first"*, so the pricing follows
  without a change.

## What it breaks

`test_keep_newest_can_be_raised` (`tests/test_filter.py:188-194`) asserts on three tool calls
in three separate messages, so it is unaffected. Nothing else in the suite constructs a
multi-result message — which is the reason the defect is there. The change needs its own test
for the batch shape, and that test is the deliverable as much as the change is.

The one real behavioural difference for an operator: on a turn where the model fired eight
tool calls, eight results are now uncached for one request instead of one. On this corpus
batches of 5 or more are 153 of 54,259 requests — 0.28% — so the tail is thin, but a session
that habitually fans out will see a larger uncached tail than it does today, and that is
exactly what `keep_newest`'s comment warns about when the constant is raised.

## The strongest case against it

**That the current behaviour is not a defect but a cheap approximation, and the model copes.**
The argument: a pointer names the tool and the rule and invites a re-run, the model can see
that two of its three calls returned something removed, and it re-runs the one it needs. On
that reading the filter is trading a possible round trip for a certain 2.0× write plus a
`0.1·D·T` read on every later turn, and 15% of its reach is bought at a discount rather than
taken by mistake.

That argument is not absurd and it has one thing going for it: at
`0.1·D·T ≈ 22·D` ([docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.4's median 224 following
turns), the bytes saved are worth much more than a single turn's input, so even a fairly high
re-fetch rate would leave the aggressive version ahead on money.

It is answered on three grounds and not on the money. First, **nothing chose it** — the
docstring, the constant's comment and §3.5's cost model all describe the other behaviour, so
this is a discount nobody priced and nobody knows they are taking. Second, it is **the exact
risk DECISIONS §5 says inverts the sign** — *"[r]e-fetch costs more than the strip saved"* —
and the mitigation named there is `ContextControl/03-`'s 3.9 KB-per-cycle break-even and a
guardrail metric that has never been run. Third, and decisively, **it makes the quality arm
unmeasurable.** Milestone 3 is meant to compare a filtered session against an unfiltered one;
if the filtered arm sometimes withholds an answer the model asked for, the arm is not "the
same session with once-only results removed", and a difference in task success cannot be
attributed. Whichever behaviour is right, the filter should do one of them on purpose.
