# Option N — name SPEC §4's guards in the filter, and implement the one that is missing

**Verdict: take the G4 half — it is a defect, not a preference, and it is reachable from a
documented flag. Take the naming for G1 and G2 as comments and a renamed constant. Leave G5
structural.** The filter satisfies three of the five guards, satisfies one by an accident of
its default, and replaces one with something else that has the same job and a different unit.
None of that is written down where the code is.

## The five guards, and where each one is

SPEC §4's "universal guards, applied before any rule" are G1 keep the tail, G2 size floor, G3
errors survive, G4 no net inflation, G5 pairing preserved. `rules.classify`
(`rules.py:397-417`) implements G1, G2, G3 and G5 and counts each refusal into `guard_blocked`;
`rules.inflates` (`rules.py:638-647`) is G4 and is applied by `plan` and `fork` rather than by
`classify`, because it needs a pointer and a pointer needs a rule.

In `filter.py`:

| Guard | In the filter | How |
| --- | --- | --- |
| **G1** keep the tail | **replaced, not implemented** | `keep_newest = 1` (`filter.py:50-55`, `:275-276`) — a different unit, see below |
| **G2** size floor | implemented | `min_bytes = 2048` (`filter.py:48`, `:268`) |
| **G3** errors survive | implemented | `rule_for`'s first line (`filter.py:108-109`) |
| **G4** no net inflation | **not implemented** | nothing compares the pointer against the result |
| **G5** pairing preserved | structural | `block["content"]` is replaced, never removed (`filter.py:288`) |

No occurrence of the strings `G1`, `G4` or `G5` appears in `filter.py`. `G2` appears once, in
the comment above `DEFAULT_MIN_BYTES`, and `G3` once, in the comment on `rule_for`'s error
check.

## G4 is missing and it is reachable

`winnow filter --min-bytes N` is a documented flag (`cli.py:662-663`) with `type=int` and no
lower bound; `WINNOW_FILTER_MIN_BYTES` (`proxy.py:319`) is the same value from the environment,
likewise unbounded. Nothing between that flag and `apply` checks the pointer against what it
replaces.

**Checked, by running it.** `apply(body, min_bytes=10)` over two `Bash ls` results of 30 bytes
each:

```
content after apply: [winnow: Bash result removed, rule B2, 30 bytes. Not cached, not
                      stored. Re-run the call if it is needed again.]
30 bytes replaced by 112 bytes; plan.bytes_dropped = 30
```

The request got 82 bytes *larger* and the ledger recorded 30 bytes saved. That is both halves of
SPEC §4 G4 — *"if the pointer is longer than the content it replaces, the content stays"* — and
SPEC §10's *"no fallback that silently keeps a result the operator asked to strip, and none that
silently strips one they did not"*, failing at once, on a flag an operator is invited to set.

`filter.py:46-48` says the guard is not needed:

> SPEC §4 G2. The same floor the pruner uses, for the same reason: below it the pointer costs
> more than the content and G4 would refuse the strip anyway.

[07-option-per-tool-thresholds.md](07-option-per-tool-thresholds.md) has already shown the
first clause is wrong for this component — the filter's break-even is between one and two
pointer lengths, 116 to 230 bytes, not 2,048. This file adds the second: **"G4 would refuse the
strip anyway" is not true, because there is no G4 to refuse it.** `min_bytes` is doing G4's job
by standing seventeen pointer-lengths above it, which works exactly as long as nobody moves it —
and option E's whole recommendation is to move it, to 256.

At 256 the headroom is 2.2×, still fine and no longer comfortable. The pointer's length is not
a constant: `pointer()` (`filter.py:93-96`) interpolates a tool name and an integer, so it is
115 bytes for `Bash`/`B2`/five digits and **118 for eight digits (checked)**, and any option
that widens `rule_for` past four literal names moves it further —
[08-option-mcp-and-subagent-output.md](08-option-mcp-and-subagent-output.md) notes a
60-character MCP name puts it near 170.

**The change is three lines** — `if len(text) >= size: continue`, using `rules.inflates` so the
comparison is the pruner's and the filter does not acquire a fourth opinion about G4 — and a
counter, so the refusal is a number rather than a silence. `rules.classify` already counts
`G1_keep_last`, `G2_min_bytes`, `G3_errors`, `G5_unpaired`; `plan.Plan.inflated` already keeps
G4's refusals rather than counting them, on the argument at `plan.py:136-139` that *"an
operator's reaction should be to lower `--min-bytes`' opposite — and they cannot react to a
number"*. The filter's version can be a count, because the filter has no `--explain`.

## G2 exists twice and the second copy asserts something false

`filter.DEFAULT_MIN_BYTES = 2048` (`filter.py:48`) sits beside `rules.DEFAULT_MIN_BYTES = 2048`
(`rules.py:104`). Two names, one value, two owners, and a comment claiming they are the same
number for the same reason.

They should not be the same number — option E's arithmetic puts the filter's optimum near 256
and the pruner's at 2,048 remains right, because the pruner's comparison really is file bytes
against a 163-byte pointer with a session's worth of `S` behind it. **So the duplication is
correct and the comment is not.** The change is to rename the constant to say what it is —
`FILTER_MIN_BYTES`, with the divergence and its arithmetic in the comment instead of an
assertion of sameness — so that the next person to reconcile the two numbers does not close the
gap in the wrong direction.

Worth stating alongside it: **the filter reports gross bytes where the pruner reports net.**
`plan.Plan.net_bytes` (`plan.py:154-158`) is *"the content removed, less the pointers that
replace it. The number SPEC §8 calls 'the net'"*. `filter.Plan` has `bytes_dropped` and no net,
and `ledger_line` emits the gross figure, which `savings` then prices. At the present floor the
gap is small — **4,715 pointers is about 542 KB against 23,249,313 bytes removed, 2.3%
[measured here]**, and option E's own table puts it at 541,535 bytes — but at a floor of 256 it
is 1,558,480 against 31,371,506, **5.0%**, and every dollar figure the filter reports would be
overstated by that much. Whether the ledger should carry `pointer_bytes` is the same question
[05-option-truncate-instead-of-drop.md](05-option-truncate-instead-of-drop.md) raises for
elision, and the answer should be the same field.

## G1 is replaced rather than implemented, and that is right

`keep_last = 6` protects the last six tool results *of the session*. `keep_newest = 1` exempts
the newest result *of the request*. These are not the same guard in different units; they are
guards against different things.

G1 exists because the pruner rewrites a transcript that is about to be resumed, and the tail of
that transcript is the context the resumed session starts from. The filter has no session and
no tail: on a live wire the newest results *are* the tail, and every result is the newest
exactly once. `keep_newest` is not a weakened G1, it is the deferral — the mechanism itself —
and [02-what-runs-today.md](02-what-runs-today.md) records that raising it is a cost rather
than a safety margin.

But the aggressiveness is worth naming where the code can see it. **At `keep_newest = 1` the
filter drops a result the pruner's G1 would still be protecting five turns later**, and
COZEMPIC §3.5 says so in words that belong in `filter.py` rather than only in a corpus
document: *"`keep_newest` defaults to 1, which is the most aggressive setting the design
admits."* Option E prices raising it at `1/(1 + 0.1T)` of the saving — 4.3% at *T* = 224 and
50% at *T* = 10 — so the constant is cheap to raise on a long session and expensive on a short
one, which is the opposite of the intuition.

**This is a comment, not an assertion.** There is nothing to check: the exemption is computed
from `len(results)` and cannot be violated.

## G5 is structural and should stay that way

The Messages API requires every `tool_use` to be answered. `apply` replaces `block["content"]`
and never removes a block, so the pairing cannot be broken by anything `apply` does —
`test_pairing_is_preserved_because_content_is_replaced_not_removed` (`tests/test_filter.py:146`)
asserts it on one body. An assertion inside `apply` would be checking that a line two lines
above it did what it says.

What is *not* structural is the assumption underneath: **`_index_tool_uses` never checks that a
`tool_use_id` is unique**, and a repeated id would silently overwrite (invariant I2,
[02-what-runs-today.md](02-what-runs-today.md)). The filter's exposure to that is small and
real: with `uses` keyed by id, a later `tool_use` carrying an earlier one's id changes the
`(name, input)` a rule is computed from, and the verdict on an already-cached result moves —
a §K1 break arriving from malformed input rather than from policy. On this corpus it does not
happen; **3 of 64,654 results have no matching `tool_use` at all [measured here]**, and those
take the safe path (`uses.get(...)` yields `("", {})`, `rule_for` returns `None`, the result is
kept). A collision counter in `_index_tool_uses` is the honest version of G5 for this component
and it is one `if use_id in index` away.

## Which constraints it strains

- **§K8** — G4 is §K8's own corollary: *"[a]ny option that changes what replaces a result has to
  keep the block, keep the pairing, and stay under the size of what it replaced."* The filter
  does not currently check the third.
- **§K10** — a strip that inflates is a silent fallback in both directions at once, and the
  ledger reports it as a saving.
- **§K1** — none. Every guard here is a function of the result's own bytes and its own call.

## What it breaks

Nothing that passes today. `min_bytes = 2048` is 17× the pointer, so implementing G4 changes no
behaviour at the default; the tests that would newly exist are the ones that set `min_bytes`
low and assert the content survives, and that the refusal is counted rather than silent.

The one visible change is that `winnow filter --min-bytes 50` stops doing what it says. That is
the point, and the failure should be at parse time as well as at strip time: a `--min-bytes`
below the longest pointer the current rule set can produce is a usage error, and SPEC §8's exit
code for that is 1.

## The strongest case against

**That this is inventing work to have some.** Four of the five guards are satisfied; the fifth
is unreachable at every setting anyone ships or documents an example of; the corpus contains no
instance of any of it going wrong, because the filter has not run over the corpus at all. A
change to a process in the credential path that fixes nothing observable, in service of a
symmetry with a component that does a different job, is the kind of change §K2 says is charged
for its surface area rather than its behaviour.

The reply is that G4's absence is not a symmetry argument. `--min-bytes` is a documented flag on
a shipped command; the value that breaks it is any integer below about 230; the failure is
silent, self-reporting as a saving, and inside the one process that is not allowed to be the
thing that breaks a run. And the option that this proposal set is most likely to recommend —
option E's floor at 256 — is the one that removes most of the headroom. **Implementing G4 is
cheap now and is a precondition for the change that is worth money.** The rest of this file is
comments, and comments are what the next reader of `filter.py:46-48` will get instead of the
sentence that is currently there and is wrong.
