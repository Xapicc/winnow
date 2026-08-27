# Option D — a per-tool byte cap, enforced on the wire

**Verdict: adopt, narrowly — for the tools the CLI's own caps do not demonstrably reach.**
The largest single class, `Read`, is already covered by a compose key and no code, and a
version of this option that takes credit for it is taking credit for something an operator
can have for free.

The mechanism is [05-option-truncate-instead-of-drop.md](05-option-truncate-instead-of-drop.md)'s
head/tail elision. This file is about the trigger: a map from tool name to a byte cap, applied
to every `tool_result` over it, with no rule behind the decision at all.

## What it is

`rule_for` is unchanged. A second, independent pass over the same `results` list: if a
result's `result_size` exceeds `CAPS.get(name, default)`, replace its middle with an elision
marker. The result is still sent whole once — the deferral, [02](02-what-runs-today.md) — and
capped from the request after.

Under [01-constraints.md](01-constraints.md) §K1 it is trivially admissible: the cap is a
constant and the size is the result's own, so the verdict is fixed at the moment the result
first appears and never moves. It needs no breakpoint of its own (§K4), because the deferral's
breakpoint is already in front of the newest turn.

## What it reaches

**Measured here, 2026-08-27**, over the 64,540 `tool_result` blocks in this container's 866
main-session transcripts, counting the bytes above the cap and grouping every `mcp__*` tool
together:

| Tool | Results | Bytes | Elidable at 8 KB | Share of message content | Results over 8 KB | Elidable at 16 KB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Read` | 8,309 | 100,143,158 | 60,148,930 | **21.97%** | 2,608 | 45,528,237 |
| any MCP tool | 1,860 | 25,458,137 | 19,859,186 | **7.26%** | 536 | 16,878,175 |
| `Bash` | 34,703 | 54,523,136 | 5,549,046 | 2.03% | 1,078 | 1,182,100 |
| `WebFetch` | 1,418 | 3,505,730 | 1,100,719 | 0.40% | 65 | 668,761 |
| `Agent` | 342 | 1,790,572 | 853,484 | 0.31% | 69 | 451,142 |
| `TaskOutput` | 46 | 487,849 | 360,530 | 0.13% | 15 | 237,650 |
| `ExitPlanMode` | 25 | 267,568 | 142,168 | 0.05% | 15 | 50,646 |
| `Grep` | 420 | 797,195 | 32,582 | 0.01% | 15 | 0 |
| `Edit` | 12,849 | 2,297,250 | 0 | 0.00% | 0 | 0 |
| `Write` | 2,738 | 477,665 | 0 | 0.00% | 0 | 0 |
| **all tools** | **64,540** | **192,456,088** | **88,057,187** | **32.17%** | 4,410 | 64,996,711 |

Three things worth reading off it before any argument.

**32.17% of message content sits above an 8 KB cap, from 6.8% of results.** That is 3.8× the
filter's entire present reach, and it is the same concentration SPEC §4 G2 relies on from the
other side: the largest decile of results carries **71.8% of tool-result bytes [measured
here]**, against `ContextControl/08-`'s 72.2%.

**`Edit` and `Write` results have no member over 8 KB at all**, across 15,587 of them. Whatever
a cap is for, it is not for those, and a flat default cap over every tool would be doing
nothing on a quarter of all results while carrying the risk of doing something wrong on one.

**`Bash` is 34,703 results and 2.03%.** It is the largest class by count and nearly the
smallest by elidable mass, because `bash_head`-matching inspection output is short. The
filter's own reach is B2 and a rounding error ([00-problem.md](00-problem.md)); a byte cap's
reach is `Read` and MCP. **The two mechanisms barely overlap**, which is the strongest
structural argument for having both.

## The alternative that costs nothing, and what is actually left after it

Claude Code caps tool output itself, from the child's environment.
`ContextControl/02-` established three of these by running them on the pinned binary and could
not establish three more:

| Variable | `02-`'s verdict | Observed |
| --- | --- | --- |
| `CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS` | **exists** | a `Read` of an 84,000-byte file: 93,401 → 32,226 chars, plus a paging instruction. Enforced against a `/v1/messages/count_tokens` answer, not a local count |
| `MAX_THINKING_TOKENS` | exists | not a tool cap |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | exists | caps replies, and drags `thinking.budget_tokens` down with it — `ContextControl/15-` calls it a trap rather than a lever |
| `BASH_MAX_OUTPUT_LENGTH` | **could not establish** | in the binary; `Bash` could not run in the probing agent's sandbox |
| `MAX_MCP_OUTPUT_TOKENS` | **could not establish** | in the binary; no MCP server was on the probed argv |
| `CLAUDE_CODE_MAX_CONTEXT_TOKENS` | could not establish | in the binary; needs a long live conversation |

So the honest partition of the 32.17%:

| | Share of message content | Status |
| --- | ---: | --- |
| `Read` — an established in-client cap covers it | **21.97%** | zero-build alternative, measured working |
| MCP + `Bash` — a variable exists and nobody has made it fire | **9.29%** | unestablished either way |
| `WebFetch`, `Agent`, `TaskOutput`, `ExitPlanMode`, `Grep` — no variable named | **0.90%** | only reachable on the wire |

**Two thirds of the prize belongs to a compose key.** A proposal that reports 32.17% and does
not say this is misreporting, and this file says it in the same paragraph as the number for
that reason.

What the wire version has that the environment variable does not, and it is not nothing:

- **It is observable.** `ContextControl/15-` names the environment cap's *defining* failure:
  *"a typo does nothing and says nothing… there is no `enabledPluginDirs()`-style check that
  could prove the lever landed, because nothing in the response says a cap was applied."* The
  filter writes a ledger line per changed request and `winnow savings` prices it. An operator
  can tell whether it fired.
- **It does not need a round trip.** The file-read cap is enforced against a
  `/v1/messages/count_tokens` answer rather than a local count — *"with a stub count it never
  fires"* — so it costs an extra request per large read and silently stops applying when that
  endpoint is slow or refused. A byte count taken on the wire needs nothing.
- **It is one mechanism for every tool**, including tools that arrive after the CLI ships and
  MCP servers the operator adds this afternoon.

What it does **not** have, and this is the honest cost: **the CLI's notice pages and the
filter's cannot.** `ContextControl/15-` quotes it — *"Call Read with `offset=388 limit=387`
for the next page, or Grep to find a specific section. Do NOT answer from this page alone if
the answer may be further in the file."* That instruction is why `ContextControl/15-` refuses
to claim the 65% reduction it measured: *"the saving is real on the turn it happens and is
repaid in full, plus a fresh tool-call round trip, the moment the model asks for page two —
which is precisely what that instruction tells it to do."* The filter can tell the model how
many bytes went and that it holds no copy; for a `Read` the model can construct the `offset`
itself from the `tool_use` input it can still see; for a `Bash` result there is no page two,
only re-running the command.

## Cap on first sight, or cap after the deferral

Two variants, and the arithmetic separates them cleanly. With *k* the retained fraction:

```
cap from first sight   2.0·k·D + 0.1·k·D·T          saving = D·(2.0 + 0.1T)·(1 − k)
cap after the deferral 1.0·D + 2.0·k·D + 0.1·k·D·T  saving = D·(2.0 + 0.1T)·(1 − k) − 1.0·D
```

The difference is exactly `1.0·D` — one uncached send of the whole result — however large *T*
is and whatever *k* is. At [docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.4's median of 224
following turns, `1.0·D` against the drop's `23.4·D` is **4.3%**.

**Letting the model read the whole result once costs 4.3% of what removing it is worth.** Take
the deferral. It is also the only variant that keeps the filter's own guarantee intact —
[04](04-option-defer-by-turn-not-by-result.md) is an argument that the model must see every
result once, and a cap that fired on first sight would reintroduce the same failure by
another route, on the class of results most likely to matter.

## Which constraints it strains

- **§K1** — none, and this is the option's real strength. Size is a static property.
- **§K7** — the ledger has to distinguish "removed" from "elided", and record retained bytes,
  or `savings` prices a partial removal as a whole one. Same requirement as
  [05](05-option-truncate-instead-of-drop.md) §K7.
- **§K10** — the tool name reaching an elision marker is now *any* name from the wire,
  including an MCP tool name the operator configured. `rules._safe_tool_name` becomes load
  bearing rather than decorative, per [01-constraints.md](01-constraints.md) §K10.
- **§K3** — the caps are a table. The moment they become a config file with a schema, the
  "flags are enough until they are not" line in DECISIONS §D6 has been crossed, and this
  option is what crosses it: a per-tool map is not a flag.

## What it breaks

**The `min_bytes` floor stops being a floor.** G2 exists because below 2,048 bytes the pointer
costs more than the content (`filter.py:46-48`). A cap is a *ceiling* on the same axis and the
two need to be reconciled explicitly, or a session ends up with a policy that removes results
between 2 KB and the cap wholesale and preserves the head of a 400 KB one.

**`plan` and `fork` stop describing the same mechanism.** SPEC §4 is six rules and five guards,
and `rules.py`'s module docstring exists because *"[i]f any two of those disagreed about what
rule B1 means, the number milestone 1 published would not describe the file milestone 2
writes."* A size cap that lives only in `filter.py` is a seventh rule that `inspect` cannot
see and `plan` cannot price — so either it goes into `rules.py` as a rule the whole tree
knows about, or the tree acquires exactly the disagreement that docstring was written to
prevent.

## The strongest case against

**That a cap is a capability decision dressed as a context decision, and this project has
already refused the claim underneath it.** `ContextControl/15-` puts it in `02-`'s words and
they are the right words: *"[a]n option built on this is betting that the model does not need
the rest, and `00-problem.md` already refuses the equivalent claim about file reads generally:
its own proxy 'cannot distinguish wasted from read and understood'."* SPEC §5.1 says the same
thing about the same 39.5% and adds that winnow *"does not ship that rule"*.

A per-tool cap is that bet with the threshold moved from semantics to size. Every rule in SPEC
§4 answers "was this result once-only" with a structural fact about the call — a locator, a
passing test, an inspection command. A cap answers a different question, "was the second half
of this needed", with no fact about the call at all, and nothing in a transcript can settle it
for the same reason nothing can settle the first: the thinking is stripped before it reaches
disk (SPEC §5.3, and **3,903 bytes of thinking across all 866 sessions [measured here]**).

The reply that makes this option adoptable rather than refused is narrow, and it should be
stated as narrowly as it is true. **Elision is not the same bet as removal.** The model keeps
the head and the tail, it is told the byte count, and the tool call and its arguments are
untouched, so a `Read` of a 400 KB file leaves the path, the first pages and the last — which
is enough for the model to know what it is missing and to ask again with an `offset`. That is
SPEC §7's retrieval discipline holding, not being suspended. And the class the option is
adopted for — MCP output, `Agent` transcripts, `WebFetch` pages, 9.29% + 0.90% of message
content — is the class where **no rule exists at all**, so the alternative is not a better
mechanism but no mechanism.
