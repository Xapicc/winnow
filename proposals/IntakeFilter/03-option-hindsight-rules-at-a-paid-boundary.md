# Option A — fire C2, B1 and A1 at a boundary where the invalidation is already paid

**Verdict: rejected.** Not because the moment does not exist, but because it is not visible
from inside the proxy, and because even a perfect oracle for it would leave the filter holding
state whose loss is itself an invalidation.

## What it is

C2, B1 and A1 are inadmissible under [01-constraints.md](01-constraints.md) §K1 for one
reason: they turn on partway through a session, so firing one rewrites bytes the cache already
holds. [docs/SPEC.md](../../docs/SPEC.md) §7 names the exception — *"[t]here is exactly one
moment where an edit is free… the work-cycle handover, where the suffix is re-written anyway.
There `S = D` and `T* = −1`"* — and `winnow fork` is built on it, with `--min-cold-age`
(default 3,600 s) refusing anything younger.

The proposal is to give the filter the same exception. On a request the proxy can identify as
one that will pay a full cache write regardless, run `rules._first_matching_rule`
(`rules.py:453-520`) instead of `filter.rule_for` and strip everything all six rules claim.
The cost term the pruner pays, `1.9·S`, is refunded at that moment, so the filter would inherit
the pruner's reach without the pruner's break-even.

## What it would reach

**Measured here, 2026-08-27**, over the 866 main-session transcripts on this container, with
the pruner's own guards (`keep_last=6`, `min_bytes=2048`) and `rules.classify` at
first-match-wins:

| Rule | Bytes | Share of message content |
| --- | ---: | ---: |
| C1 | 70,729 | 0.03% |
| C2 | 5,654,936 | 2.07% |
| C3 | 780,482 | 0.29% |
| B1 | 176,744 | 0.06% |
| B2 | 21,066,655 | 7.70% |
| A1 | 20,583,784 | 7.52% |
| tier CB | 27,749,546 | 10.14% |
| tier CBA | 48,333,330 | 17.66% |

**C2 + B1 + A1 is 26,415,464 bytes, 9.65% of message content** — slightly more than everything
the filter reaches today (8.49%). At §3.5's model that is roughly a doubling of the filter's
+3.76%, so the prize is real and worth about $280 on this corpus's $7,426.47 bill if it could
be had for nothing. It cannot.

(The same run reproduces [docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.4 closely on a
different population — tier CB 10.14% here against 10.17% there, C2 2.07% against 2.09%, B2
7.70% against 7.75%. The two that move are A1, 7.52% against 8.69%, and B1, 0.06% against
1.16%; §3.4 already records B1 firing in only 9 of 174 sessions, which is too few to be stable
between populations.)

## Is there such a moment, visible from inside the proxy?

Four candidates, and none of them survives.

**A resume after the cache has expired.** This is the pruner's moment and it is the one that
matters, because it is where the whole transcript arrives in one body. Nothing in the request
body marks it. There is no field, no header, no `cache_control` arrangement that distinguishes
"the client just resumed a two-hour-old session" from "the client is on turn 40 of a session
that started ten minutes ago". The message list is long in both cases.

**The proxy's own memory of the conversation.** "I have not seen this prefix before" would be
the signal, and it fails on the first request after any proxy restart, which is exactly the
case where it is most confidently wrong: a proxy started mid-session sees a long unfamiliar
prefix and concludes it is a cold resume, on a cache that is warm.

**The wall clock.** "No request relayed for more than an hour" is a real signal about the
TTL, and it is forbidden twice over: §K10's determinism (two requests over the same
conversation would render differently depending on when the proxy started) and §K1 explicitly
(a verdict that depended on the clock fails monotonicity for the same reason a verdict that
depends on the future does).

**The response.** `usage.cache_read_input_tokens` near zero says the cache was cold — on the
request that has already been sent. It is evidence after the fact, it requires
[11-option-read-the-response.md](11-option-read-the-response.md), and it arrives one request
too late to decide the request it describes.

The honest answer to the brief's question is **no**. The one moment the proxy can identify
with certainty is a conversation whose message list is empty, and there is nothing there to
strip.

## The argument that kills it even given a perfect oracle

Suppose the proxy were told, out of band and correctly, that request *t*₀ is a cold resume. It
fires all six rules and strips 17.66% of the prefix. That request is free, exactly as SPEC §7
says.

Then the session continues, and the rules do not stay put. At *t*₀+1 a new tool call arrives;
at *t*₀+5 it duplicates an earlier one, or supersedes an earlier read, or edits a file
something read at *t*₀−200. **Every one of those makes a rule newly true about a result now
sitting in a warm prefix.** Two ways out, and both are worse than not doing it:

**Fire again.** Each newly-true result is an invalidation at its own position, and the earlier
the result the larger the suffix behind it. This is `1.9·S` paid not once at a cold boundary
but repeatedly, mid-session, on a hot cache — strictly the arithmetic the pruner's
`--max-break-even` gate exists to refuse. [README.md](../../README.md#the-break-even-gate)
measures what happens when a cut is taken whenever a rule fires and the gate is off: 396 cuts,
30% of them actually paid, **−$10.85** net. That is the ungated pruner at *one* boundary. The
filter doing it on every request is that arithmetic per turn.

**Freeze the decision.** Apply exactly the set decided at *t*₀ and nothing more. This requires
remembering the set, and it cannot be re-derived: a later body is the resume prefix plus new
turns, and **the filter has no marker in it**, because Claude Code builds every request from
its own memory of the original bytes. The pointers the filter wrote at *t*₀ never come back —
that is the same fact that makes the filter re-drop the same result on every later request and
puts 1,283 removal events against 49 distinct results on a real ledger
([docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5.1). So the frozen set has to live in the
proxy.

And then losing it is not a degradation, it is a bill. If the proxy restarts mid-session and
forgets which results it had pointered, the next request carries those results in full again;
the prefix stops matching at the earliest of them, on a warm cache, and the session pays
`1.9·S`. **A crash in a component whose first design principle is "it must never be the thing
that breaks a run" (§K6) would cost the operator money in proportion to how well the session
had been going.** There is no passthrough for that: forwarding the original bytes, which is
what every other failure in `_rewrite` does, *is* the failure.

## Which constraints it strains

- **§K1** — it is the constraint. The option is an attempt to buy an exception to it, and the
  exception is not purchasable from where the proxy stands.
- **§K5** — the frozen set is a store the tool reads back to decide, which is the reading of
  "no fourth store" that survives.
- **§K6** — the failure mode is not passthrough. It is an invalidation.
- **§K10** — every candidate signal for "the cache is cold" is a clock, a counter or a
  process-lifetime fact, and each breaks determinism.

## What it breaks

Statelessness, which is not an implementation convenience here but the property that makes the
K1 argument hold at all (`filter.py:18-22`). Once the filter has memory, "the same conversation
always renders to the same bytes" becomes "the same conversation renders to the same bytes as
long as this process stays up", and nothing in the design survives that substitution.

## The strongest case *for* it, stated fairly

The prize is the largest in this proposal set — 9.65% of message content, more than the
filter's entire present reach — and the argument against is not that the arithmetic is wrong.
At a genuinely cold boundary it is right, and SPEC §7 says so.

The case is answered by pointing at where that capability already lives. **`winnow fork` is
this option, built, tested, and placed at the one moment it works.** It runs between sessions,
it takes the decision on a transcript rather than on a wire, it has `--min-cold-age` to check
that the boundary really is cold and `--max-break-even` to refuse a cut that is paid for and
never earned back, and it writes a file that can be inspected before it is resumed. Everything
this option would have to invent, that command already has.

The one thing the pair does badly is overlap, and
[docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5 already prices it: the filter takes C1, C3 and
B2 first because it sees the request before the transcript is written, so what is left for the
pruner is C2 plus B1 — 2.2% of message content — against an unchanged `S`, which raises `S/D`
by about 4.6× and clears break-even almost nowhere. **That is an argument for choosing between
them, not for moving one inside the other.** On this corpus the leftover is larger than §3.5's
2.2% because A1 is unclaimed by the filter as well: C2 + B1 + A1 = 9.65%, and a `fork` run
against a filtered session with `--rule A1` is the shape that combination actually wants.
Whether it clears its break-even is a `winnow plan` away and nobody has run it.

## What it would take to reopen this

One thing, and it is not code. **A signal in the request body that says the prefix is cold.**
If the vendor ever exposed the cache state to the client, or if Claude Code marked a resumed
request in a way a proxy could read, the first paragraph of the rejection falls away — and the
second and third do not, because the frozen-set problem is a property of the filter being on
the wire rather than of the signal being absent.
