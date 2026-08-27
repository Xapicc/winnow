# Option E — per-tool `min_bytes` and `keep_newest`

**Verdict: reject the per-tool refinement. Take the thing it uncovers instead — the single
`min_bytes` constant is set eight times too high for this component, and lowering it is worth
about a third more than the filter currently produces.**

The option as posed dies on the measurement, and what killed it is worth more than it was.

## What it is

`filter.apply` takes two constants and applies them to everything: `min_bytes = 2048`
(`filter.py:48`) and `keep_newest = 1` (`filter.py:55`). The proposal is a map from tool name
— or from rule — to a pair, so that a `git status` and a `Glob` are not governed by the same
floor.

## Where the floor came from, and why it does not belong to this component

`filter.py:46-48`:

> SPEC §4 G2. The same floor the pruner uses, for the same reason: below it the pointer costs
> more than the content and G4 would refuse the strip anyway.

Both halves of that are inherited and neither survives inspection here.

**"The pointer costs more than the content" is a different comparison for the filter.** For the
pruner, a strip removes *D* bytes from a file and adds a pointer; guard G4 (`rules.inflates`,
`rules.py:638-647`) refuses when `len(pointer) > size`, and the pruner's pointer is 163 bytes.
For the filter, the result is sent once in full and the pointer then lives in the cached prefix
forever, so with *P* the pointer's length and *T* the turns that follow:

```
baseline  D·(2.0 + 0.1T)
filtered  1.0·D  +  P·(2.0 + 0.1T)
saving    D·(1.0 + 0.1T)  −  P·(2.0 + 0.1T)
```

which is positive when

```
D  >  P · (2.0 + 0.1T) / (1.0 + 0.1T)
```

The filter's own pointer is **115 bytes** (checked: `len(pointer("Bash","B2",41208))`). So the
break-even result size is:

| *T* | break-even *D* |
| ---: | ---: |
| 0 | 230 bytes |
| 10 | 172 bytes |
| 50 | 134 bytes |
| 224 | 120 bytes |
| 1,000 | 116 bytes |

It is bounded between *P* and 2*P* at every *T*, so **no session length makes 2,048 the right
number.** The floor is set eight to seventeen times above where the arithmetic puts it.

**"G4 would refuse the strip anyway" is not true either.** G4 refuses only when the pointer is
strictly longer than the content — under 115 bytes. And the filter does not implement G4 at
all: `apply` never compares the pointer against the result. `min_bytes` is doing G4's job by
being far enough above it that the question never arises.

## What the floor costs, measured

**Measured here, 2026-08-27**, over every rule-claimed result on this container's 866
main-session transcripts, at any size: 19,498 results, 32,034,204 bytes. "Net" is
`D·(1 + 0.1T) − n·P·(2 + 0.1T)` summed over the results above the floor, in
byte-multiples — the unit does not matter because only the ratio between rows does.

| `min_bytes` | Results | Gross bytes | Share of content | Pointer bytes added | Net at *T*=224 | Net at *T*=20 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 19,498 | 32,034,204 | 11.70% | 2,242,270 | 694.9 M | 87.1 M |
| 128 | 16,082 | 31,828,753 | 11.63% | 1,849,430 | **699.7 M** | **88.1 M** |
| 256 | 13,552 | 31,371,506 | 11.46% | 1,558,480 | 696.1 M | 87.9 M |
| 512 | 11,059 | 30,442,676 | 11.12% | 1,271,785 | 681.3 M | 86.2 M |
| 1,024 | 8,049 | 28,187,839 | 10.30% | 925,635 | 637.0 M | 80.9 M |
| **2,048 (today)** | **4,709** | **23,229,292** | **8.49%** | 541,535 | **530.4 M** | **67.5 M** |
| 4,096 | 2,008 | 15,413,018 | 5.63% | 230,920 | 355.0 M | 45.3 M |

**The optimum is flat between 128 and 512 and the current setting is 32% below it at *T*=224
and 31% below at *T*=20.** The reach in bytes goes from 8.49% to 11.46% of message content at
a floor of 256 — the filter's headline number rises by a third — and every result admitted at
that floor is net-positive at every *T*, because 256 is above the *T*=0 break-even of 230.

256 is the number to take rather than 128: 128 wins at *T*=224 by half a percent and admits
results between 128 and 230 bytes that are negative for a session with a short tail, and
DECISIONS §D8's whole discipline is not to pick a constant that is right on the median and
wrong on the distribution.

## What the per-tool version buys on top of that, which is almost nothing

**Measured here**, the claimed results split by `(tool, rule)`:

| Tool | Rule | Results | Bytes | Median | p90 | Below 2,048 | Bytes below 2,048 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Bash` | B2 | 14,728 | 29,405,650 | 1,024 | 4,889 | 69.7% | 7,088,235 |
| `Bash` | C3 | 4,686 | 2,522,946 | 221 | 1,341 | 95.0% | 1,681,798 |
| `Glob` | C1 | 38 | 74,911 | 874 | 5,691 | 65.8% | 13,425 |
| `Grep` | C1 | 46 | 30,697 | 306 | 1,267 | 95.7% | 21,454 |

The shapes do differ — a passing `pytest` has a median result of 221 bytes and a `cat` has
1,024 — and that is exactly the case a per-tool floor is meant to serve. But **the direction is
the same for every one of them: lower.** All four classes want a floor near 256, so one
constant set correctly captures the whole of the gain and a map captures nothing beyond it.
The largest per-class residue is `Bash` C3, whose 1,681,798 sub-2,048 bytes are 0.61% of
message content and are already collected by the global change.

The other direction — *raising* a floor for a tool whose rule is imprecise — has nothing to
set it from. `rules.DISABLED_BY_DEFAULT` ships empty for precisely this reason and stays empty
*"until the 200-sample blind label has been scored"* (`rules.py:106-118`), and a per-tool floor
chosen without that measurement would be the same failure in a different variable: the tool
asserting a precision nobody measured.

## `keep_newest`, per tool

**Reject, and there is nothing to argue with.** The three rules the filter can fire are C1, C3
and B2, and all three are answers the model consumes on the turn they arrive — a file list
feeding the next call, a passing test, a `git status`. There is no candidate for a longer
exemption among them, and no evidence in this repository that would identify one if there
were.

The cost of raising it is exact and worth recording so that the constant is not raised
casually. At `keep_newest = n` the result is sent in full on *n* requests instead of one, so
the saving is `D·(2.0 + 0.1T − n)` against `D·(1.0 + 0.1T)` at `n = 1`. **Each extra request
costs `1/(1 + 0.1T)` of the saving** — 4.3% at *T* = 224, 16.7% at *T* = 50, and **50% at
*T* = 10**. The filter is cheap on long sessions and `keep_newest = 2` is half the value of a
short one. In absolute terms on this corpus, raising it to 2 costs one extra `1.0·D` send over
all 4,709 claimed results: 23,229,292 bytes, **$29.04** at bytes ÷ 4 and Opus base $5/M.

And it is not free structurally either. [02-what-runs-today.md](02-what-runs-today.md) records
that above `keep_newest = 1` the breakpoint lands in front of the *latest* exempt candidate,
so results after it that no rule claims fall out of the cached prefix as well — invariant I7,
and a cost the constant's own comment does not mention.

## Which constraints it strains

- **§K1** — none. A floor is a static property of the result.
- **§K3/§D6** — a per-tool map is not a flag. DECISIONS §D6 rejected a config file on the
  grounds that *"two call sites is not a pattern; flags are enough until they are not"*, and a
  table keyed by tool name is where that stops being true. **The global change needs no such
  argument**, which is a second reason to prefer it.
- **§K8** — lowering the floor puts the filter within sight of G4 for the first time. At 256
  bytes against a 115-byte pointer there is still headroom, but the guard should be
  implemented rather than implied, because the pointer's length is not a constant: it
  interpolates a tool name and a comma-free integer, so a 60-character MCP tool name makes it
  ~170 bytes and any option that widens `rule_for` moves it further.

## What it breaks

**The filter stops agreeing with the pruner about G2.** `rules.DEFAULT_MIN_BYTES` is 2,048 and
SPEC §8 lists `--min-bytes 2048` as the default for `plan` and `fork`. A filter running at 256
and a `plan` running at 2,048 are two different selections over the same session, and
[docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5's ledger reconciliation assumes they overlap
in a known way. The floors should diverge *deliberately*, with the divergence documented where
`filter.py:46-48` currently asserts the opposite — the pruner's floor is right for the pruner,
because its comparison really is file bytes against a 163-byte pointer.

**Nearly three times as many pointers reach the model.** 13,552 removals against 4,709.

## The strongest case against

**That the arithmetic above prices bytes and the real cost of a small strip is not bytes.**
SPEC §4 G2's own words are *"stripping small results buys nothing and costs pointer
overhead"*, and the first half of that is a claim about usefulness, not about size. Nine
thousand additional pointers on this corpus is 1.56 MB of `[winnow: … removed …]` text that
the model reads instead of content, spread thinly across every session rather than
concentrated in the few large results the filter takes today. A conversation in which one
result in five is a receipt is a different conversation from one in which one in twenty is,
and nothing here measures what that does. `[[Context Rot]]` is in SPEC §11's source list and
this proposal set has not read it; if there is evidence about the density of placeholder text,
that is where it would be.

The reply is that the objection applies with equal force to the current setting and nobody
applied it there — 2,048 was inherited from a component with a different arithmetic, not
chosen against this risk — and that **the cost is measurable in the same experiment that has
to be run anyway.** SPEC §9's 200-sample blind label samples stripped results stratified by
rule; sampling them stratified by *size* as well answers whether a 300-byte `git status` was
needed more often than a 30 KB one, and that is one column in a sheet that has not been filled
in yet. Until it is, the honest position is that the floor should move to where the arithmetic
puts it and the readout should say what moved, rather than staying at a number whose stated
justification is checkably wrong for this component.
