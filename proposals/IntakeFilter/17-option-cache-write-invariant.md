# Option O — assert the cache-write invariant over grown conversations, not over examples

**Verdict: take it, and treat the first thing it finds as a defect rather than a proposal.**
Writing the property down was enough to break the mechanism: at `--keep-newest 2`, a documented
flag, a deferred result is cache-written in full and then replaced by a pointer on the next
request. That is `1.9·S` on a warm cache, once per turn, in the component built to avoid paying
it once. `test_keep_newest_can_be_raised` passes while it happens.

## The property

Everything in this design rests on one sentence, and it is not written anywhere in the code as
a checkable statement:

> **No result whose rendering the filter will later change may sit at or before the last
> `cache_control` breakpoint in the request it emits.**

Unpack it into the two halves that are actually tested for, because they are checked at
different times:

- **W1, per request.** In the body `apply` returns, every *deferred* candidate is strictly after
  the last breakpoint in `messages`. A deferred candidate is the only kind of block whose
  rendering is going to change.
- **W2, across a conversation.** Replay a growing message list request by request. For each
  block, once it has been at or before the last breakpoint on some request, its rendering never
  changes on any later one.

W2 is the property that matters and W1 is how the code buys it. `filter.py:18-22` states the
consequence of losing it — *"a policy whose output varied between two requests over the same
conversation would change the prefix under the cache and destroy the thing it exists to
protect"* — and [01-constraints.md](01-constraints.md) §K1(b) states the licence precisely:
*"[t]he rule is not 'the bytes never change'; it is 'the bytes never change once they have been
cache-written', and the filter buys its one exception by controlling where the prefix ends."*

## What is tested today

`tests/test_filter.py` has 39 tests and four of them touch the breakpoint:

| Test | Asserts |
| --- | --- |
| `test_the_newest_candidate_is_pushed_out_of_the_cached_prefix` (`:116`) | on one two-turn body, the newest position is not a breakpoint and every breakpoint is before it |
| `test_a_result_no_rule_claims_keeps_its_breakpoint` (`:128`) | no candidate, no intervention |
| `test_the_filter_never_pushes_a_request_over_the_breakpoint_cap` (`:209`) | four client breakpoints, `len(breakpoints) <= 4`, `not plan.breakpoint_moved` |
| `test_a_breakpoint_on_the_candidate_is_removed_which_frees_a_slot` (`:222`) | three client breakpoints plus one on the candidate; moved, and still ≤ 4 |

Every one is a hand-built body of two to five turns with one result per message, `keep_newest`
at its default, and one call to `apply`. `test_the_policy_is_idempotent_so_the_prefix_never_flaps`
(`:158`) is the closest thing to W2 and it re-applies `apply` to the *same* body rather than to a
grown one — which is invariant I8, a different property, and the one `POINTER_RE` exists for.

**Nothing replays a conversation.** `test_growing_the_conversation_drops_what_left_the_newest_slot`
(`:177`) grows a body by one turn, which is the only test in the file that models what the proxy
actually sees, and it asserts on the drop rather than on the prefix.

## What the property finds

**Checked by running it.** Three `Bash` turns, all three results 3,000 bytes and all three
claimed by B2, `keep_newest = 2`:

```
t0  deferred = [b, c]   dropped = [a]
    breakpoints  = [(4, 0)]
    renderings   = (1,0) pointer   (3,0) full   (5,0) full
```

Result `b` is deferred — sent in full, `plan.bytes_deferred` counts it — and it sits at (3,0),
**before** the only breakpoint at (4,0). It is inside the write region. The API caches it.

Then the client appends a fourth turn and sends the conversation again, built from its own
memory, so `b` arrives in full:

```
t1  deferred = [c, d]   dropped = [a, b]
    renderings   = (1,0) pointer   (3,0) pointer   (5,0) full   (7,0) full
    breakpoints  = [(6, 0)]
```

`b`'s rendering changed from 3,000 bytes to a 115-byte pointer, at a position the cache already
held. The prefix match breaks at (3,0) and everything behind it is re-written at 2.0×.

And it does not happen once. At t₁, `c` is deferred at (5,0) with the breakpoint at (6,0), so
`c` is now cache-written; at t₂ it becomes a pointer and breaks the prefix again. **At
`keep_newest ≥ 2` the cache breaks on every request from the third onward**, and `S` is the whole
conversation behind the second-newest result, which is nearly all of it.

## Why the code does it

`filter.py:278-286`:

```python
newest_candidate: tuple[int, int] | None = None
for m_index, b_index, block, rule, size in candidates:
    if id(block) in exempt_ids:
        newest_candidate = (m_index, b_index)      # overwritten on each exempt candidate
```

The loop keeps the **last** exempt candidate, and `_place_breakpoint_before` puts the boundary
immediately in front of it. Every *earlier* exempt candidate is therefore behind the boundary.
At `keep_newest = 1` the exempt set has one member and the two coincide, which is why the
mechanism is sound at its default and only at its default.

[02-what-runs-today.md](02-what-runs-today.md) records the adjacent fact — that above 1 the
breakpoint lands in front of the latest exempt candidate and *"everything after it — including
results no rule claims — falls out of the cached prefix"* — and prices that as a cost in 1.0×
sends. **That is the outward half. The inward half is this one, and it is not a cost, it is the
invalidation.** Invariant I7 in the same document names the assumption (*"nothing between the
new breakpoint and the candidate needed caching"*) and says it is not true above 1; what neither
document says is that the thing sitting between them is a result the filter is about to rewrite.

**The fix is one word.** `newest_candidate` must be the *earliest* exempt candidate, so that
every deferred result is after the boundary:

```python
if id(block) in exempt_ids:
    if newest_candidate is None:
        newest_candidate = (m_index, b_index)
```

That is the same line [04-option-defer-by-turn-not-by-result.md](04-option-defer-by-turn-not-by-result.md)
already proposes for an unrelated reason — *"`newest_candidate` becomes the earliest exempt
candidate rather than the latest, so `_place_breakpoint_before` puts the boundary in front of
the whole batch"* — so the two changes are one change, and option B's version is the more
general of the two because it groups by turn rather than by result. The variable's name should
change with it; it is the *oldest* deferred candidate, and calling it `newest_candidate` is how
the bug reads as correct.

## A correction to §K4

[01-constraints.md](01-constraints.md) §K4 says of the breakpoint cap:

> When there is not [room], it drops the older candidates and leaves the newest one where it is
> — so on a full request the deferred result is cache-written after all, and the saving on that
> one result is lost rather than the request being broken.

**The second clause is wrong.** `_strip_breakpoints_from` runs unconditionally, before the count
(`filter.py:293-297`), and it removes every breakpoint at or after the candidate. So when the
cap check then declines to place a new one, the candidate is still strictly after every
breakpoint that remains, and is not cache-written. Checked: four client breakpoints at messages
1, 3, 5, 7 with the candidate at message 9 gives `breakpoint_moved = False`, breakpoints
unchanged at `[(1,0),(3,0),(5,0),(7,0)]`, and the candidate strictly after all of them.

The stronger statement is that **the cap branch cannot fire harmfully at all against a client
that respects the same cap.** If any of the client's four breakpoints is at or after the
candidate, the strip removes it and the count falls below four, so placement proceeds. The
branch is reached only when all four are already strictly before the candidate — in which case
the candidate was already outside the prefix and there was nothing to move, which is the same
situation as `_place_breakpoint_before`'s *"already the boundary; nothing to move"* early
return. Both of the seed's "interesting paths" turn out to be the safe one, and the interesting
path is the one nobody was looking at.

That leaves the cap check's real defect where option J found it:
[12-option-prefix-readout.md](12-option-prefix-readout.md) records that `_count_breakpoints`
(`filter.py:164-171`) counts only breakpoints in `messages`, so a client placing them on
`system` or `tools` makes the count an undercount and the filter can push the request to five.
**That is a 400, and W1 is not the property that catches it** — it needs its own assertion,
`total breakpoints ≤ MAX_BREAKPOINTS` over all three places a `cache_control` can sit.

## What the test looks like

Stdlib only, deterministic, no dependency. A generator over bodies and a replay loop.

**Generator.** `random.Random(seed)` with a fixed seed list, building a message list from a
grid: 1–8 turns; 1–4 `tool_result` blocks per user message; each result claimed by C1, C3, B2 or
nothing; sizes drawn to straddle `min_bytes`; `is_error` occasionally true; client breakpoints
placed on 0–4 blocks including the newest; occasional non-dict blocks, string-valued message
content, missing `tool_use_id`, and list-form content
([19-option-content-shapes.md](19-option-content-shapes.md)). A fixed seed makes it a regression
pin rather than a flaky test, and SPEC §10's determinism applies to tests as much as to output.

**W1, one call.** For each generated body: `apply`, then assert every position in
`plan.deferred` is strictly greater than the last breakpoint position in `messages`. This is the
assertion that fails today at `keep_newest = 2`, and it is three lines.

**W2, the replay.** Start with one turn. For `t` in 1…N: apply to a *fresh* copy built from the
client's original bytes plus `t` turns — which is what Claude Code sends, and the reason the
existing idempotence test does not model it. After each call, record for every `tool_use_id` its
rendering and whether it was at or before the last breakpoint. Assert: **no rendering changes
after the first request in which that block was inside the write region.** This is W2 and it is
the property the whole design is.

**Two more that cost nothing once the generator exists.** Total `cache_control` count across
`messages`, `system` and `tools` never exceeds `MAX_BREAKPOINTS`. And G5: the multiset of
`tool_use` ids equals the multiset of `tool_use_id`s, before and after.

**What it must not do.** Assert on exact byte output — that is
[23-option-golden-wire-fixture.md](23-option-golden-wire-fixture.md), and it is a different
instrument. A property test that pinned bytes would fail on every deliberate change and teach
people to regenerate it.

## Which constraints it strains

- **§K1** — the option is K1's enforcement. Today K1 is a paragraph in a docstring and four
  examples.
- **§K3** — stdlib only, so no Hypothesis. That is a real limitation: a hand-rolled generator
  explores a grid the author thought of, and the shrinking that makes property testing pleasant
  is absent. It found this defect anyway, because the defect is at `keep_newest = 2` and any
  grid over that parameter reaches it.
- **§K10** — determinism. The seed is fixed and listed, and a failure names the seed and the
  body.

## What it breaks

The one-word fix changes behaviour only at `keep_newest > 1`, which is not the default and which
`test_keep_newest_can_be_raised` covers with assertions that survive it (`plan.bytes_dropped`
and `len(plan.deferred)` are unchanged; only the breakpoint's position moves). Combined with
option B, the change is larger and is argued there.

The honest cost is that a property test over a generator is a new kind of test for this suite,
and the suite's own style is stated in `tests/test_filter.py:1-8`: *"[t]he policy tests assert
on request bodies, because the request body is the cache key."* A generator is that same
principle applied to bodies nobody wrote by hand, which is the only way to reach the bodies
nobody thought of. The five hand-built breakpoint tests should stay: they document the intent,
and a property test documents nothing.

## The strongest case against

**That the defect is at a non-default setting nobody uses, and the general machinery is
disproportionate to it.** `keep_newest = 1` is *"the design and not a tuning parameter"*
(`filter.py:50-55`), option E rejects raising it on arithmetic, and the one-word fix costs
nothing and needs no generator. On that reading the correct change is the fix plus a fifth
hand-built test, and the property test is a hundred lines of scaffolding bought for a bug
already found.

The reply has two parts. The first is that the defect was found *by writing the property down*,
which is what the option is; the fix is the easy half and the reason nobody had it is that the
invariant existed only in prose. The second is that the seed for this file asked about the two
paths that looked dangerous — the cap branch and the early return — and both turned out to be
safe, while the path nobody suspected was not. **That is the argument for a generator over an
example: the examples in the file are the cases somebody already reasoned about correctly.**

The residual objection stands and should be recorded: this option produces no bytes and no
dollars. It is insurance, and it is priced at the cost of one invalidation. On this corpus a
single cache break at the median session position is worth about `1.9·S` where `S` is most of a
conversation, against a mechanism whose entire yield is +3.76% of the bill — so one break undoes
a good many turns of saving, and the version of the filter that ships with `--keep-newest` and
no property test is one flag away from being a net cost.
