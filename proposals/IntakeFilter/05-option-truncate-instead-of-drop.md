# Option C — head/tail elision instead of an all-or-nothing drop

**Verdict: reject as a softening of the three rules the filter already fires. Adopt as the
substitution discipline for anything the filter reaches on size alone**, which is
[06-option-per-tool-byte-cap.md](06-option-per-tool-byte-cap.md). The two readings have
opposite answers and they are usually run together.

## What it is

Today the strip is total: `block["content"]` becomes a 115-byte pointer and every byte of the
result is gone (`filter.py:288`). The proposal is a third rendering — keep the first *H* bytes
and the last *T* bytes of the result, replace the middle with a marker saying how much went,
and leave the block otherwise as it was.

The idea has prior art on both sides of this repository. The inherited tree already ships a
truncation strategy, `mega-block-trim` (`src/winnow/legacy/registry.py:64`), in its aggressive
tier. `ContextControl/02-` measured Claude Code's own file-read cap doing the same thing
in-client: an 84,000-byte `Read` returned **93,401 → 32,226 characters** with an appended
paging instruction. And [DECISIONS.md](../../docs/DECISIONS.md) §Q3 records the underlying
question as open — empty `content` versus a placeholder, with nobody having published a
comparison — so a third point in that space is a legitimate thing to propose rather than a
settled one.

It passes [01-constraints.md](01-constraints.md) §K1 without an argument. Where the elision
boundary falls is a function of the result's own bytes and two constants, so it is the same on
every request that carries the result. §K8 holds too: the block, its type and its
`tool_use_id` survive, and the rendering is strictly shorter than what it replaced.

## The arithmetic, and it is the whole of the case against reading (i)

Let *D* be the result in tokens, *T* the turns that follow, *k* the fraction retained. At the
one-hour write class ([docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.4 measured
`ephemeral_5m_input_tokens` at 0 across the corpus; 188.9 M one-hour write tokens and no
five-minute ones **[measured here]** on this one):

```
baseline    2.0·D            + 0.1·D·T          = D·(2.0 + 0.1T)
drop        1.0·D                               (sent once, uncached, then gone)
truncate    1.0·D + 2.0·k·D  + 0.1·k·D·T        (sent once in full, then the retained part lives forever)
```

so

```
saving(drop)      = D·(1.0 + 0.1T)
saving(truncate)  = D·(1.0 + 0.1T)  −  k·D·(2.0 + 0.1T)
```

**Retaining a fraction *k* gives back *k* of the entire baseline, not *k* of the saving.**
The retained head and tail are not a discount on the removal; they are a full-price result of
their own, cache-written once and read on every turn thereafter. This is the "price the tail"
the brief asks for, and it is the reason truncation is much more expensive than it looks: the
elided middle still costs 1.0× on the one request it survives, *and* the retained ends cost
2.0× plus `0.1·T`.

At §3.4's median of 224 following turns, `0.1T = 22.4`, so the baseline is `24.4·D` and the
drop saves `23.4·D`. Retaining a quarter of the result leaves `23.4 − 6.1 = 17.3·D`, a **26%
cut in the saving for a quarter of the bytes**.

## Reading (i): soften the three rules the filter already fires

Apply a head/tail cap to C1, C3 and B2 results instead of removing them, so a `git status` or
a passing `pytest` leaves its first and last lines behind.

**What it costs, measured here, 2026-08-27**, over the 4,709 filter-claimed results
(23,229,292 bytes, mean 4,933) on this container's 866 main sessions:

| Combined head+tail cap | Bytes retained | *k* | Bytes still elided |
| ---: | ---: | ---: | ---: |
| 512 | 2,411,008 | 0.104 | 20,818,284 |
| 1,024 | 4,822,016 | 0.208 | 18,407,276 |
| 2,048 | 9,644,032 | 0.415 | 13,585,260 |
| 4,096 | 16,041,042 | 0.691 | 7,188,250 |

A cap equal to the current `min_bytes` floor — 2,048 bytes, a plausible first choice —
**retains 41.5% of everything the filter removes, and by the arithmetic above gives back 41.5%
of its whole saving.** The filter's +3.76% of the bill becomes about +2.2%. Even a 512-byte
cap, which is two dozen lines of `git status` and not much use, costs a tenth.

**What it buys is unmeasurable from here.** The claim would be that the model does better with
the head of a `git status` than with a pointer to it. Nothing in this repository can settle
that: it is DECISIONS §Q3 with a third arm, and Q3's own note is that *"nobody has published a
comparison"* and that two independent searches found none on 2026-08-23. SPEC §9 puts the
answer in milestone 3, which has not started.

**Reject.** A 41.5% cut in the one number this component has is not a price to pay for a
hypothesis, and the hypothesis is testable later at no cost to the current design: milestone
3 can carry a truncated arm alongside the dropped one, and if it wins, the change is a
constant.

There is one narrower version worth naming so that part 2 can dismiss it deliberately rather
than by omission: **elide only C1 results**, on the grounds that a truncated file list is
still a file list. C1 is 70,729 bytes on this corpus — 0.03% of message content, 0.3% of the
filter's reach. It is not worth a code path in the credential path.

## Reading (ii): elision as the only admissible removal for results no rule claims

This is the one that matters, and the arithmetic that condemns reading (i) is what recommends
it here.

The filter refuses a `Read` of a 400 KB file, an `Agent` transcript and an MCP browser
snapshot because no rule claims them and no rule should — dropping a file the session is
working on is exactly the once-only judgement SPEC §5 says the transcript cannot support.
**Elision is the only removal available on that class**, because the decision is not "was this
needed" but "was *all* of it needed", and a head and a tail leave the model something to
recognise.

The reach is large. **Measured here**, a flat head+tail cap applied to every `tool_result` on
the corpus, counting only the bytes above the cap:

| Cap | Bytes elidable | Share of message content | Results affected |
| ---: | ---: | ---: | ---: |
| 2,048 | 137,738,868 | **50.32%** | 15,836 (24.5%) |
| 4,096 | 113,536,046 | 41.48% | 8,860 (13.7%) |
| 8,192 | 88,057,187 | **32.17%** | 4,410 (6.8%) |
| 16,384 | 64,996,711 | 23.75% | 1,725 (2.7%) |
| 32,768 | 47,072,860 | 17.20% | 733 (1.1%) |

An 8,192-byte cap reaches **3.8× everything the filter reaches today**, from 6.8% of results.
That is the shape SPEC §4 G2 already relies on from the other end — the largest decile of
results carries **71.8% of tool-result bytes [measured here]**, against `ContextControl/08-`'s
72.2% — and it is why a size-triggered mechanism is worth arguing about at all.

Which cap, on which tools, with what evidence, is
[06-option-per-tool-byte-cap.md](06-option-per-tool-byte-cap.md). This file's contribution is
that **the substitution has to be an elision and not a pointer**, and that it must be priced
as `k` of the whole baseline rather than as a discount.

## What the marker has to say, and the one thing it cannot say

The pruner's pointer names the rule "so the operator can argue with the rule rather than with
the tool" (SPEC §4) and carries a `winnow recover` command. The filter's carries neither a
digest nor a recovery command, deliberately, because it keeps no copy (`filter.py:85-96`).

An elision marker inherits that limit and one more: **it cannot offer paging.** The CLI's own
truncation notice says *"Call Read with `offset=388 limit=387` for the next page"*
(`ContextControl/02-`, quoted in `ContextControl/15-`), and `ContextControl/15-` is blunt
about what that is worth — the saving *"is repaid in full, plus a fresh tool-call round trip,
the moment the model asks for page two — which is precisely what that instruction tells it to
do."* The filter is in the better position here and should say so: it holds nothing, so its
marker can only point at SPEC §7 route 1, re-running the call, which for a `Read` the model
can do with an `offset` it constructs itself from the `tool_use` input it can still see.

Two things the marker must contain for §K1 and §K10: **the elided byte count** (so the ledger
and the model agree on what went) and **nothing variable** (no timestamp, no digest of
anything the filter would have to re-derive, or the rendering moves between requests).

And one hazard §K10 names: the marker is where transcript content meets generated text.
`filter.pointer` interpolates a tool name unbounded and is safe only because `rule_for` fires
on four literal names ([01-constraints.md](01-constraints.md) §K10). **An elision marker for a
size-triggered rule has no such closure** and must route the tool name through
`rules._safe_tool_name`, or repeat its logic.

## Which constraints it strains

- **§K8** — it is a change to the substitution discipline, and the one constraint it must keep
  is that the rendering is strictly shorter than what it replaced. Trivially true above a cap;
  worth a guard anyway, because G4 exists for exactly this and the filter does not currently
  implement it (it relies on `min_bytes` being far above the pointer's 115 bytes).
- **§K7** — the ledger's `bytes` field currently means "the whole result went". Under elision
  it has to mean "this many bytes went", and `savings._price` prices `1.0·D` for a removal
  that is now `1.0·D_elided` against a retained remainder that is a *cost*. The ledger needs a
  retained-bytes field or the pricing is wrong in the flattering direction, which is the
  direction [docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.1, §3.4 and §3.5.2 each record an
  error in.
- **§K10** — the marker is generated text carrying transcript content, per above.

## What it breaks

`POINTER_RE` (`filter.py:61`) matches a pointer at the *start* of a string. An elided result
does not start with one — the marker is in the middle — so the re-entry guard
([02-what-runs-today.md](02-what-runs-today.md)) does not recognise an already-elided result,
and `apply` would re-measure it, re-elide it (idempotently, since it is already short enough,
unless the retained ends alone still exceed the cap) and re-count its bytes into the ledger at
the *new*, smaller size. That is a second de-duplication problem on top of §K7's, and it is
the concrete reason this option is not a small change.

## The strongest case against

**That it is the CLI's job and the CLI already does it.** `ContextControl/02-` established
`CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS` works, measured it, and `ContextControl/15-` costs
the alternative at a compose key and no code. Everything reading (ii) proposes for `Read`
results — by far the largest class, 52.04% of tool-result bytes **[measured here]** — is
available today by setting an environment variable, with the CLI generating a better notice
than the filter can (it pages), and with none of it running beside a credential.

That objection is answered in [06](06-option-per-tool-byte-cap.md), where it belongs, and it
is not answered easily. It is the reason this file's verdict on reading (ii) is "adopt as the
substitution discipline" rather than "adopt".
