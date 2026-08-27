# What to do, and what to refuse

**The position, in three sentences.** The intake filter is one rule with a rounding error
attached, it is currently a cache-breaker at a documented flag, and it has no milestone, no
definition of done and no kill criterion anywhere in this repository — so the next work is to
make what exists correct and legible, not to make it reach further. Eight of the eleven
capability options ask `rule_for` to claim more content; **none should be taken**, because the
one measurement that would license any of them is the 200-sample precision label, it is written,
harnessed and unrun, and on the day it runs the filter will not hear the result. Everything
recommended below is either a defect, a switch the filter is missing, or an instrument that
produces a number rather than spending one.

**Checked, because it decides the shape of this document:** `docs/MILESTONES.md` mentions the
words *filter*, *proxy*, *savings*, *trial* and `ANTHROPIC_BASE_URL` **zero times**. Milestones
1, 2, 3a and 3 are `inspect`, `fork`/`recover`, the frozen task set and `bench`. The intake
filter was built outside that plan, is argued only in COZEMPIC §3.5, and has never been given a
bar it could fail.

---

## Do these first, because they are wrong now

Not options. Each is a defect found at a file and a line, and three of them are reachable from a
flag the CLI documents.

**1. `newest_candidate` must be the earliest exempt candidate, not the latest.**
`filter.py:278-286`. At `--keep-newest 2` the breakpoint lands in front of the *last* exempt
candidate, so every earlier one is cache-written in full and replaced by a pointer on the next
request — `1.9·S` on a warm prefix, on every request from the third onward, in the component
built to avoid paying it once ([17](17-option-cache-write-invariant.md), verified by running
it). One word. It is first because it is the only defect in the set that costs money in
proportion to how well a session is going.

**2. Implement G4, and give `--min-bytes` a floor.** `winnow filter --min-bytes 10` replaces 30
bytes with a 112-byte pointer and records 30 bytes saved ([16](16-option-guards-by-name.md),
verified). Use `rules.inflates` so the filter does not acquire a fourth opinion about a guard,
and make a `--min-bytes` below the longest producible pointer a usage error at parse time.

**3. De-duplicate `inspect.read_filter_ledger` on `tool_use_id`.** §K7 records it;
`savings.read_ledger` already does it; the two readers of one file disagree by the echo factor,
**8.6× on this corpus and 27.2× on the one real ledger**. This is a precondition for
recommendation 8 and doing them in the other order would put a known error inside a refusal.

**4. Count `system` and `tools` breakpoints.** `_count_breakpoints` (`filter.py:164-171`) counts
only `messages`, so a client placing a `cache_control` on either makes the cap check an
undercount and the filter can push a working request to five breakpoints, which is a 400
([12](12-option-prefix-readout.md) found it; [17](17-option-cache-write-invariant.md) confirms
the property test does not catch it and it needs its own assertion).

**5. Two smaller ones, recorded by part 1 and repeated here so the list is one list.**
`savings.find_transcripts` globs `*/*.jsonl` so a sub-agent's ledger line can never join
([08](08-option-mcp-and-subagent-output.md)); `filter.py:46-48` justifies its floor with a
sentence that is checkably wrong for this component ([07](07-option-per-tool-thresholds.md),
[16](16-option-guards-by-name.md)).

---

## Then, in this order

**6. Honour rule selection — [M](15-option-honour-rule-selection.md).** `--tier`, `--rule`,
`--no-rule`, `DISABLED_BY_DEFAULT` and `$WINNOW_RULES_OFF` resolved once at startup and held in
`Config`. This is first among the non-defects because it is the only item in the set with a
scheduled failure date: `docs/MILESTONE-2-VALIDATION.md` is written for someone with no memory
of this discussion, its scorer prints `export WINNOW_RULES_OFF=B2` as the remediation, and B2 is
**96.07% of what the filter removes**. Everything else here can wait for a quiet week. This
cannot wait for the labelling study, because it is what makes the labelling study's result
reach half the tool.

**7. Defer by turn, not by result — [B](04-option-defer-by-turn-not-by-result.md).** Group the
exemption by the assistant turn the results answer, not by the message they sit in and not by
their position in a flat list. **One byte in seven that the filter removes is currently removed
before the model has read it** — 3,516,979 bytes across 332 sessions — and the docstring, the
constant's comment and §3.5's cost model all describe the other behaviour. It costs $6.24 across
the corpus and it subsumes defect 1 above, because the same line fixes both.

One correction to that option's proposed change, from a measurement it did not take. **Every
user record in this corpus carries exactly one `tool_result` [measured here] — 64,651 of
64,651** — so a parallel batch is several records on disk and the wire layout is not observable
from there. Grouping "by the message they sit in", as §04 words it, is right if Claude Code
sends one user message with *N* `tool_result` blocks and wrong if it sends *N* messages. **Group
by the `tool_use` block's message index instead**, looked up through the index `_index_tool_uses`
already builds, and the fix is correct under either layout.

**8. Tell the pruner — [T](22-option-tell-the-pruner.md).** `--filter-ledger` on `plan` and
`fork`. This is the only recommendation whose entire implementation is outside the credential
path, and it closes the loop `ledger_line`'s own docstring opens: *"[t]his line is what lets the
pruner know"* — and `plan` and `fork` have no way to be told. **79.0% of what `winnow plan
--tier CB` proposes to remove is content the filter claims too.** Do the denominator and the
readout; leave the positional `S` correction for later and say in the readout that it is not
applied.

**9. One rule engine — [L](14-option-one-rule-engine.md).** `stateless_rule_for` in `rules.py`,
a `PREFIX_DETERMINED` map beside `RULE_TIER`, and the cross-check test. After 6, because M is
the change that makes the shared signature carry an `enabled` set; before 10, because E is a
change to a constant that two files claim to own.

**10. The floor at 256 — [E](07-option-per-tool-thresholds.md)'s global half, and only its
global half.** **+32% on the filter's net at *T* = 224 and +31% at *T* = 20**, reach from 8.49%
to 11.46% of message content, every admitted result net-positive at every *T* because 256 is
above the *T* = 0 break-even of 230. Reject the per-tool map: all four `(tool, rule)` classes
want a floor in the same place, so a table captures nothing a constant does not. **Do not do
this before 2** — at 256 the headroom over the pointer is 2.2×, and the guard that would catch
the mistake does not exist yet.

**11. The instruments, as one change to one file — [S](21-option-health-signal.md) +
[R](20-option-ledger-as-artefact.md).** `v` and `kind` on the ledger line, `tool_results_seen`
and `candidates` on `Stats`, a heartbeat line every *N* requests. They land together because a
heartbeat without a `kind` tag arrives in `savings.read_ledger` as a malformed entry. The
baseline an operator compares against is on this corpus: **7.29% of results claimed, 6.5% of
turns producing a line, 67.4% of sessions containing at least one candidate.**

**12. The prefix readout — [J](12-option-prefix-readout.md).** Its own file says take it first
and I am putting it eleventh, which needs defending. The argument for first is that it is the
only instrument in the set and the only capability nothing else in the world can provide: **zero
of 866 transcripts carry a system prompt or a tool definition**, and the bytes it would report
stand behind **$39,677 of avoided cost against a $7,426.47 bill**. All of that is right. It is
eleventh because §K2 charges an option for surface beside a credential, the readout's own §K2
paragraph concedes that a system prompt is the operator's `CLAUDE.md` and their MCP
configuration, and a component that is currently a cache-breaker at `--keep-newest 2` should not
gain a new reporting subsystem in the same release it is being made correct. **Nothing about it
gets worse by waiting a release, and the one part of it that is urgent — the `_count_breakpoints`
undercount — is defect 4 above and is being done first.**

**13. The pins — [O](17-option-cache-write-invariant.md)'s property test and
[U](23-option-golden-wire-fixture.md)'s golden.** Last, and not optional. The property test is
what makes defect 1 stay fixed; the golden is what makes a reworded pointer or a moved
breakpoint a decision somebody took. Both are test-only. Write O's generator when defect 1 is
fixed, so the first thing it does is fail on the old code.

**Deferred rather than refused.** [Q](19-option-content-shapes.md)'s one-line `str`-only refusal
lands with the first widening, not before — it is a no-op on 100% of current candidates.
[I](11-option-read-the-response.md)'s narrow `message_start` read is real and small and is the
lowest value per unit of credential-path surface in the set; take it if and when the double-count
it immunises against actually bites. [K](13-option-count-tokens-parity.md)'s two-run compaction
measurement is a measurement, is in [27-validation.md](27-validation.md), and needs no code.

---

## What to refuse, and the one measurement that reverses each

**The standing refusal, above all the individual ones: do not widen `rule_for` past `Glob`,
`LS`, `Grep` and `Bash` until the filter has a precision number and a kill criterion.** SPEC §9's
bar is *"≥90% of stripped results confirmed once-only by a human reading the surrounding turns"*
and MILESTONES' kill is aggregate precision below 80%. Neither has been measured for the six
rules that *do* have a vendor contract behind them, let alone for a new one. Four separate
closures in this code — `filter.pointer`'s unbounded tool name (§K10), `POINTER_RE`'s `str`-only
test (I9), route 1 covering every rule ([10](10-option-recall-store.md)), and every candidate
having string content ([19](19-option-content-shapes.md)) — hold **only** because four literal
names return strings and are re-runnable. A widening opens all four at once.

*The measurement that reverses it:* `uv run python -m winnow.validate sample … --target 200`,
labelled blind, scored, at ≥90% aggregate and per rule — **and** the same sampler pointed at the
filter's own position, because a `git status` from forty turns ago and one from the turn before
last are not the same question ([15](15-option-honour-rule-selection.md)).

| Refused | Why | The single measurement that would change my mind |
| --- | --- | --- |
| **A** — hindsight rules at a paid boundary | the cold moment is not visible from the request body, and a frozen decision set makes a proxy restart cost `1.9·S` | a field *in the request body* marking a cold prefix. Nothing else: the frozen-set problem survives a perfect oracle |
| **G** — rewrite `tool_use` inputs | 41.0% of `Write` input mass is paths the session comes back to; eliding `Bash.command` silently moves `rule_for`'s verdict on a different block | a milestone 3 arm that elides `Write.content` and lands inside SPEC §9's ±5-point equivalence bound |
| **H** — a recall store | the bytes are already in the transcript, and the model cannot reach a store without an MCP server priced at $8.14–$8.26/week | a `savings`-side check showing ledger `tool_use_id`s no longer resolve to full content in transcripts — i.e. the vendor stopped writing what it holds |
| **C(i)** — elide the three rules instead of dropping them | retaining a fraction *k* gives back *k* of the whole baseline; a 2,048 cap costs 41.5% of the saving | a milestone 3 truncated arm beating the dropped arm on task success at equal or lower cost |
| **D** — a per-tool byte cap | 21.97% of the 32.17% belongs to a compose key an operator already has; a cap is SPEC §5.1's refused bet with the threshold moved to size | `BASH_MAX_OUTPUT_LENGTH` and `MAX_MCP_OUTPUT_TOKENS` run against the pinned binary and shown not to fire — `ContextControl/02-` could not establish either |
| **F(a)** — an `mcp__*__list_*` rule | 1.67% of message content, on a naming convention rather than a contract, firing on servers it has never seen | that convention labelled at ≥90% on its own, stratified, with the servers named — and re-labelled whenever a server is added |
| **E**'s per-tool map | all four `(tool, rule)` classes want a floor near 256; the map captures nothing the constant does not | a labelling sheet stratified by *size* as well as rule, showing the classes diverge |
| **P**'s ledger field | the collateral is 651 bytes across the whole corpus | option B landing — at which point the field is required, not optional, and §04 already prices it at 1,471,491 bytes |
| **S**'s status endpoint | a second route returning internal state from a process whose access log is silenced on purpose | nothing. The ledger heartbeat covers the same failure with no new surface |
| **R**'s rotation | 4.7 MB for 867 sessions, 20% the size of what it records | a real install's ledger past ~50 MB, or a session past ~89 candidates against the 54 seen |
| **K** — filter `count_tokens` | zero saving available, and the two bodies differ by construction anyway | the compaction measurement in §27 showing the CLI decides from the stale count **and** that filtering it delays compaction more than it misleads |
| **I**'s headline claim | reading the response does not make `winnow savings` measured; the counterfactual is on the other side of the subtraction | none. It is a category error, not a missing number. The narrow version stands on its own small merits |

---

## What this adds up to

Nine changes to shipped code, of which five are defects, three are switches or parameters that
already exist elsewhere in the tree, and one is a constant. Two test artefacts. One measurement
with no code at all. **Net effect on the filter's reach: 8.49% → 11.46% of message content**,
entirely from moving one number from 2,048 to 256, plus 15.14% of its existing reach handed back
to the model instead of taken from it.

That is a modest result and it should be stated as one. The filter is worth **+3.76% of a
$7,426.47 bill** on §3.5's model, this raises it by about a third, and the change that raises it
is three characters. Everything else on the list is there because a component sitting in front of
an API key with no milestone, no kill criterion, an unimplemented guard, an unreachable rule
switch and a cache-breaking flag should be made honest before it is made bigger.

The single largest number in this whole proposal set belongs to none of the options: **the
prompt cache is worth 5.3× this corpus's entire bill**, and the second-largest belongs to
`winnow trial`, which would settle what any of this is worth per successful task and has never
had an arm recorded. If there is capacity for one thing beyond the defect list, it is not on
this page — it is running the labelling study and recording a trial arm.
