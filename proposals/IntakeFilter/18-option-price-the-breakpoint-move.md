# Option P — price the breakpoint move

**Verdict: reject the ledger field. The collateral is 651 bytes across the corpus and the
+3.76% is not an overstatement on this account.** But the move has a cost nobody has looked at,
it is not the one the question assumes, and it is measurable: the filter's cache *write* lands
at a position no later request ever marks again, so the whole mechanism reads through the
20-block lookback window. On this corpus the worst turn is 15 blocks. That is five blocks of
headroom, and it is the first time anyone has counted.

## The question as posed

`_strip_breakpoints_from` removes the breakpoint the client placed on the newest block;
`_place_breakpoint_before` puts a new one in front of the candidate (`filter.py:293-297`). The
bytes between the two positions therefore fall outside the write region on that request, and
the ledger records `bytes_dropped` and `bytes_deferred` and nothing about them. If those bytes
are large, the filter's headline saving is overstated.

**The arithmetic.** Let *X* be the content strictly after the newest candidate that the client's
breakpoint would have covered.

```
baseline   request t:   2.0·X  (inside the write region)     t+1 onward:  0.1·X per request
filtered   request t:   1.0·X  (after the last breakpoint)   t+1:  2.0·X   t+2 onward: 0.1·X
```

The whole difference is one request's worth: `(1.0 + 2.0) − (2.0 + 0.1)` = **+0.9·X, once per
deferral**. It does not compound and it does not scale with *T*. The candidate's own bytes are
not in *X* — displacing those is the mechanism, and §3.5 already prices them.

## What *X* is

**Measured here, 2026-08-27**, over the 867 main-session transcripts on this container. For
every run of consecutive user records answering one assistant turn, take the last `tool_result`
in the run; if it is a filter candidate (`rule_for` non-`None`, `result_size ≥ 2048`), sum every
block after it in that run:

| | |
| --- | ---: |
| candidate-terminated runs | 4,622 |
| …with any block at all after the candidate | **10** |
| total bytes in those blocks | **651** |
| block types found | `text` × 11 |

And over *all* 64,651 user records carrying a `tool_result`, whether a candidate or not: **2
records have anything after the last one, totalling 228 bytes.** Every user record in this
corpus carries exactly one `tool_result`.

So `0.9 · X` over the whole corpus is **about 586 byte-multiples — 146 tokens at SPEC §6's
÷ 4, $0.0007 at `savings.PRICES` Opus base input.** Against 23,249,313 bytes removed it is
0.0025%. **It is a rounding error, and a ledger field for it would cost more to explain than it
would ever report.**

Two caveats, and the first is the one that could change the answer.

**The transcript is not the wire.** This measures what Claude Code wrote to disk, and a block
injected into the request at send time and never persisted would be invisible here. Content of
that kind demonstrably exists in this corpus — `<system-reminder>` text appears **3,510,600
bytes across the first 300 files [measured here]** — but where it lands is checkable and it
lands inside `tool_result` content, not after it: of the reminder-carrying blocks found, all but
13 were in a record that also carries a `tool_result`. Nothing here can rule out a trailing
block that exists only on the wire. What it can say is that the transcript, which is the only
observation available, shows the position empty.

**It is not a rounding error under two of the options in this set.**
[04-option-defer-by-turn-not-by-result.md](04-option-defer-by-turn-not-by-result.md) moves the
breakpoint in front of the *whole batch* rather than in front of its last member, which puts
every non-candidate result of a parallel batch into *X* — and that file already prices it, at
**1,471,491 bytes**, 2,500× the figure above, and calls it *"the reason the option is not
free"*. [07-option-per-tool-thresholds.md](07-option-per-tool-thresholds.md) records the same
term for `keep_newest > 1`. **The collateral is zero at the current settings and material under
the change most likely to be recommended**, which is the useful form of the answer: the ledger
field is not needed today and becomes needed the moment option B lands.

## The cost that is not in the ledger and is not bytes

The question assumes the move's cost is content displaced. The interesting cost is *where the
write lands*, and it needs a fact from the vault that this proposal set has not used.

`[[Prompt Caching]]` (**high**, `/workspace2/3 Resources/AI Context and Memory/`, cited by
SPEC §7 and §11):

> **Writes happen only at breakpoints.** … **Reads look backward for prior writes.** On each
> request the system hashes the prefix at the breakpoint and, failing a match, walks backward
> looking for entries *earlier requests actually wrote*. It is not searching for stable
> content. … **The lookback window is 20 blocks.** Beyond that it stops.

Follow the filter through that.

At request *t* the filter writes at *P*ₜ — the last block before the newest candidate, which is
almost always the assistant `tool_use` block. **The client never marks that position.** It
built the request from its own memory, it does not see the rewrite, and at *t*+1 it places its
breakpoints wherever its own scheme puts them. So *P*ₜ is not a breakpoint in the *t*+1 request
and its entry can never be found by an exact hash match.

**It is found only by the backward walk, and only if it is within 20 blocks.** That is not a
detail of the implementation; it is the read half of the mechanism. If the walk misses, the
request falls back to whichever of the client's older breakpoints was written, which is further
back than the client's own newest — the one the filter stripped and did not let be written. So
a miss is not a cache *break* (nothing is rewritten that was already cached, W1 in
[17-option-cache-write-invariant.md](17-option-cache-write-invariant.md) holds) but it is worse
than baseline for that request: a chunk of prefix re-written at 2.0× that the unfiltered client
would have read at 0.1×.

**Measured here**, the distance between one turn's breakpoint position and the next — content
blocks in one assistant request plus every block of the user records answering it, over 63,149
turns:

| Blocks in a turn | Turns |
| ---: | ---: |
| 1 | 556 |
| 2 | 29,540 |
| 3 | 26,907 |
| 4 | 3,995 |
| 5 | 1,659 |
| 6–10 | 479 |
| 11–15 | 13 |
| **over 20** | **0** |

**89.5% of turns are two or three blocks and the largest in the corpus is 15.** The lookback has
five blocks of headroom in the worst case observed and seventeen in the ordinary one. The
mechanism's read path is sound here, and the condition under which it would stop being sound is
now a number rather than a hope: **a turn of more than 20 content blocks.** That is a parallel
tool-call batch of ten or more — option B measured 8 requests on this corpus issuing ten calls —
combined with a multi-block assistant message. It does not occur. It is one more reason the
per-turn deferral in option B is the right shape, since batching more results behind one
breakpoint does not change the block count of the turn.

## The same note endorses the mechanism, and that is worth recording

The vault's account of the commonest caching failure is:

> A large static system context in blocks 1–5, then block 6 containing a timestamp plus the
> user message. Put `cache_control` on block 6 and the hash differs every request. The lookback
> walks back through blocks 5 to 1 — but nothing was ever written at those positions, because
> writes only happen at breakpoints. Result: a fresh cache write every single request, and never
> a read.

The prescribed fix is to move the breakpoint back to the last block that is identical across
requests. **That is exactly what `_place_breakpoint_before` does**, automatically, every
request, for a client that does not do it — and the block it lands on is a `tool_use` block,
which invariant I3 ([02-what-runs-today.md](02-what-runs-today.md)) says nobody rewrites. The
filter is the vault's own remedy applied on the wire, and neither `filter.py` nor COZEMPIC §3.5
says so. It should, because it is a second argument for the component that does not depend on
the +3.76% at all.

## Which constraints it strains

- **§K7** — the option as posed would add a ledger field, and a field that reports 651 bytes
  across a corpus is a field that will be misread as significant. Reject it now, and require it
  as part of option B rather than as a change of its own.
- **§K4** — the lookback and the four-breakpoint cap are the same budget seen from two sides.
  An option wanting a second cut point is also lengthening the walk.
- **§K1, §K6, §K9** — none. Nothing here changes a byte.

## What it breaks

Nothing. The measurement is the deliverable; the only code change worth taking from this file is
a comment on `_place_breakpoint_before` naming the 20-block lookback as the reason the placed
breakpoint has to be *near* the candidate rather than merely before it — which is not obvious
from the function, and is the constraint that would be violated first by anyone "simplifying" it
to place the breakpoint at a fixed earlier position.

## The strongest case against

**That measuring *X* on transcripts answers a question about the wire, and the answer is
therefore worth less than it looks.** The whole finding is that a position is empty in a file
that is not the artefact under discussion. A single captured request body — the proxy already
parses one on every call — would settle it directly, and until someone captures one the honest
statement is "no evidence of collateral" rather than "no collateral".

That is fair, and the answer is that the capture is cheap and belongs in
[27-validation.md](27-validation.md) rather than in a ledger field: run `winnow filter
--verbose` for one session with a one-line addition that reports `len(json.dumps(body))` before
and after, and the difference against `bytes_dropped` is the whole accounting, measured on the
thing itself. **The reason to reject the ledger field is not that the number is unknowable; it
is that a permanent field in a durable artefact is the wrong instrument for a quantity that is
either zero or belongs to a change that has not been made.**
