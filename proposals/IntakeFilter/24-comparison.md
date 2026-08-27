# The whole set on one table

Twenty-one options. Each file argues one on its own terms and reaches its own verdict in
isolation; this is the first document that puts them beside each other. The table is the
document. Everything after it is either an interaction the table cannot show or a number that
would be misread without its caveat.

**Reading the columns.** *Reaches* is bytes on this corpus where the option removes or reports
content, and "—" where it removes nothing. Every byte figure is **[measured here], 2026-08-27**,
over the 867 main-session transcripts under `~/.claude/projects/*/*.jsonl` on this container,
against **273,722,399 bytes of message content** for figures inherited from
[00-problem.md](00-problem.md) and **280,679,191** for figures taken in this half of the set —
the corpus is live and gained a session between the two runs, and the method note in §00 governs
both. *Costs* is what it spends: bytes, dollars, credential-path surface, or a commitment.
*Risks* is the way it goes wrong. *Has to be true* is the condition the option's own file names
as decisive.

## Capability options — what the filter reaches

| | Option | Own verdict | Reaches | Costs | Risks | Has to be true |
| --- | --- | --- | ---: | --- | --- | --- |
| **A** | [Fire C2/B1/A1 at a paid boundary](03-option-hindsight-rules-at-a-paid-boundary.md) | reject | 26,415,464 B · **9.65%** | statelessness; a frozen decision set held in the proxy | a proxy restart mid-session forgets the set and costs `1.9·S` — a crash that bills the operator in proportion to how well the session was going | a signal *in the request body* that the prefix is cold. There is none, and the frozen-set problem survives even if there were |
| **B** | [Defer by turn, not by result](04-option-defer-by-turn-not-by-result.md) | **take** | returns 3,516,979 B to the model · **15.14% of the filter's reach** | 4,988,470 B of one-request 1.0× sends · **$6.24** | a turn that fires 8 tools sends 8 results uncached for one request; batches ≥ 5 are 0.28% of requests | nothing. It pays in money above a ~6% re-fetch rate and in correctness at any rate |
| **C** | [Head/tail elision instead of a drop](05-option-truncate-instead-of-drop.md) | reject (i) · adopt (ii) as discipline | (i) softens the current rules; (ii) 88,057,187 B above an 8 KB cap · **32.17%** | (i) gives back *k* of the whole baseline: a 2,048 cap retains 41.5% and costs 41.5% of the saving | `POINTER_RE` does not match an elided result, so it is re-measured and re-counted every request | (i) that the model does better with a head than a pointer — DECISIONS §Q3, unmeasured by anyone |
| **D** | [Per-tool byte cap on the wire](06-option-per-tool-byte-cap.md) | adopt narrowly | 88,057,187 B at 8 KB, of which **21.97% belongs to a compose key**, 9.29% to variables nobody has made fire, **0.90% wire-only** | a per-tool table (crosses DECISIONS §D6), a ledger field, `_safe_tool_name`, a seventh rule `inspect` cannot see | it is the capability bet SPEC §5.1 refuses, with the threshold moved from semantics to size | that `CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS`, `BASH_MAX_OUTPUT_LENGTH` and `MAX_MCP_OUTPUT_TOKENS` cannot be made to cover it |
| **E** | [Per-tool `min_bytes`/`keep_newest`](07-option-per-tool-thresholds.md) | reject per-tool · **take the global floor at 256** | 31,371,506 B · **11.46%**, against 8.49% today — **+31% net at *T*=224** | 13,552 pointers instead of 4,709; 1.56 MB of receipt text; the filter's G2 stops matching the pruner's | pointer density is a thing nobody has measured; `[[Context Rot]]` is in SPEC §11 and unread here | that a 300-byte `git status` is no likelier to be needed again than a 30 KB one — one extra column in the labelling sheet |
| **F** | [MCP and delegated-agent output](08-option-mcp-and-subagent-output.md) | adopt (b) for plain strings · reject (a) | MCP 25,458,137 B · 9.30%, but **78% of it is screenshots overstated 27.7×**; plain-string MCP results are **49 of 1,860** | a name-pattern rule fires on servers it has never seen; `_safe_tool_name` becomes mandatory | an `mcp__*__list_*` rule asserts a precision nobody measured, in the expensive direction | that a naming convention carries a contract. It does not — the name is chosen by whoever wrote the server |
| **G** | [Rewrite `tool_use` inputs](09-option-tool-use-inputs.md) | reject | `Write` inputs 22,832,251 B · **8.34%** — nearly a doubling | SPEC §4's first sentence and DECISIONS §D3; the pointer's legibility; A1's own rationale | eliding `Bash.command` moves `rule_for`'s verdict on a *different* block, silently, losing reach nothing reports | that the file on disk recovers what the write intended. **41.0% of `Write` mass is paths the session comes back to** |
| **H** | [Content-addressed recall store](10-option-recall-store.md) | reject · **build the reader** | — | a fourth store read back to decide; verbatim tool output made durable beside a credential | the model cannot reach it without an MCP server, priced at **$8.14–$8.26/week** against $0.14 a use | that route 1 fails for the filter's rules. It does not — all three are re-runnable inspections of local state |
| **I** | [Read `usage` off the response](11-option-read-the-response.md) | reject the claim · adopt the narrow version | — | an SSE parser in the credential path; the sentence *"it does not … inspect a response body"* stops being simply true | a "measured" figure that is exactly as counterfactual as the modelled one, and harder to see | that the per-request double-count matters more than the surface. It is live in one reader and a test could also catch it |
| **J** | [A readout of the fixed prefix](12-option-prefix-readout.md) | **take, and take it first** | reports the bytes behind **$39,677 of avoided cost against a $7,426.47 bill — 5.3×** | nothing on the request path; one in-memory hash; a real §K2 exposure if it ever prints content | a system prompt is the operator's `CLAUDE.md` and their MCP configuration | nothing. **Zero of 866 transcripts carry a system prompt or a tool definition** — the proxy is the only process that has ever held them |
| **K** | [Filter `count_tokens` too](13-option-count-tokens-parity.md) | **keep the exclusion**, correct the docstring | — | nothing to keep it; the docstring's reason is inverted and is quoted approvingly in COZEMPIC §3.5 | if Claude Code decides when to compact from the *unfiltered* count, the filter brings compaction forward invisibly while reporting a saving | that compaction is triggered from the response's `usage` rather than from a `count_tokens` answer. **Not establishable from this repository** |

## Structural options — what the mechanism as built should become

| | Option | Own verdict | Reaches | Costs | Risks | Has to be true |
| --- | --- | --- | --- | --- | --- | --- |
| **L** | [One rule engine, or two](14-option-one-rule-engine.md) | **take**, as `stateless_rule_for` + a `PREFIX_DETERMINED` flag | — (no bytes) | ~30 lines; one more imported name | **the obvious refactor is a regression**: calling `_first_matching_rule` directly newly claims 753 error results, 19 above the floor | that the copy stays faithful. It is faithful on all 63,931 non-error results today and nothing checks it |
| **M** | [Honour rule selection](15-option-honour-rule-selection.md) | **take, before the labelling study** | protects **96.07%** of the filter's reach from firing after B2 is disabled | one tier flag and two repeatable flags; resolution must be at startup | resolving per request would make a shell export break a live cache | that the labelling study will be run. It is written, harnessed, and its scorer prints the export line |
| **N** | [Name the guards; implement G4](16-option-guards-by-name.md) | **take G4**; rename G2's constant; comment G1 | — | three lines and a counter | `--min-bytes 10` replaces 30 bytes with a 112-byte pointer and the ledger reports 30 saved | nothing. It is reachable from a documented flag today, and **E removes most of the headroom** |
| **O** | [Assert the cache-write invariant](17-option-cache-write-invariant.md) | **take**, and treat the first finding as a defect | — | a stdlib generator, ~100 lines | **at `--keep-newest 2` a deferred result is cache-written and then pointered — `1.9·S` on a warm cache, every turn from the third** | nothing. Checked by running it; `test_keep_newest_can_be_raised` passes while it happens |
| **P** | [Price the breakpoint move](18-option-price-the-breakpoint-move.md) | **reject the ledger field** | collateral is **651 bytes across the corpus** | — | the real dependency is `[[Prompt Caching]]`'s 20-block lookback; the worst turn here is **15 blocks** | that the transcript's trailing position reflects the wire's. Not establishable without capturing one body |
| **Q** | [The shapes a result comes in](19-option-content-shapes.md) | nothing today · a **precondition** for any widening | 2,759 list-form results · 61,893,116 B; **zero candidates are structured** | one line: `str`-only | replacing a list with a string takes 19,954,267 B of un-re-runnable screenshots with it | that the four rule-firing tools keep returning strings. They do; the safety is scope, not design |
| **R** | [The ledger as an artefact](20-option-ledger-as-artefact.md) | **take `v` and `kind`** · reject rotation | 4.7 MB simulated over the whole corpus; echo factor **8.6×** | two keys, ten lines of reader | three queued migrations change what an existing key *means*, which every reader parses successfully and prices wrongly | that another migration is coming. Three are, in this set alone |
| **S** | [The smallest honest health signal](21-option-health-signal.md) | **take two fields + a heartbeat** · reject an endpoint | — | two ints and one ledger line per *N* requests | four distinct failures all look like `filtered = 0`, and `savings` is blind to every one because the ledger only records successes | nothing. The number is already computed on every request and thrown away |
| **T** | [Tell the pruner](22-option-tell-the-pruner.md) | **take** | corrects a denominator understated by up to **8.49%**; **79.0%** of tier CB overlaps the filter | one parameter through two commands; the positional `S` correction is larger | `wire_content_bytes` clamps at zero, so wiring the un-de-duplicated reader into a gate produces a share of nothing | that the two are ever run together. §03's closing question needs exactly this and nobody has run it |
| **U** | [Pin the emitted body](23-option-golden-wire-fixture.md) | **take**, eight fixtures | — | one fixture file and the regeneration discipline | rewording the pointer, moving the breakpoint one block, or dropping the `cache_control` pop all pass the suite today | that byte-level output is a contract. It is — with a cache the process cannot observe |

## Six things the table gets wrong on its own

**1. B, O and the `keep_newest` defect are one change.** Option B proposes making
`newest_candidate` the *earliest* exempt candidate so the breakpoint lands in front of a whole
parallel batch. Option O finds that the *latest* is a cache-breaking bug at `keep_newest ≥ 2`.
They are the same line, arrived at from opposite directions, and the table shows them as two
rows costing two changes. They cost one.

**2. E is gated on N.** Lowering the floor to 256 leaves 2.2 pointer-lengths of headroom on a
guard that is not implemented. Doing E without N is doing the one change that makes the missing
guard matter.

**3. T is gated on the §K7 de-duplication fix, which is nobody's option.**
`inspect.read_filter_ledger` sums `bytes_dropped` with no `tool_use_id` collapse. That is a
defect §K7 records rather than proposes, and threading it into `plan`'s break-even gate turns a
wrong readout into a wrong refusal. Order: fix the reader, then thread the parameter.

**4. The reach column is not additive and three rows overlap heavily.** A + the filter's present
reach is *not* 18.1%, because A is the pruner's rules and the pruner's guards. C(ii), D and F
are one mechanism seen three ways — elision, its trigger, and the class it is pointed at — and
their 32.17% is the same 88,057,187 bytes counted once in each row. E's 11.46% *contains* the
current 8.49%. Only B, J, and the structural rows are disjoint from everything else.

**5. Every share in both tables is low by about a quarter, not by the twelfth §00 states.**
[19-option-content-shapes.md](19-option-content-shapes.md) finds 475 base64 image blocks
carrying 54,533,135 bytes — **19.4% of message content** — against §00's 276 blocks and 19.9 MB,
because §00 counted MCP results and a `Read` of an image file also returns an image block (199
blocks, 34,578,868 B). On a denominator with all of them removed the filter reaches **10.28%**,
not 8.49% and not §00's partially-corrected 9.15%. The direction §00 names is right; the
magnitude is 2.7× larger. Every "share of message content" in both tables above is stated
against the full denominator, consistently and conservatively, exactly as §00 chose.

**6. Two rows are worth nothing on the bill and are the two with the largest downside
avoided.** O and N reach no bytes. O's finding is a mechanism that pays `1.9·S` per turn; N's is
a flag that inflates the request while reporting a saving. Against a component whose whole yield
is **+3.76% of a bill**, a single mid-session invalidation at the median position undoes many
turns of it — so the rows with a dash in the *Reaches* column are not the cheap ones to skip.

## What the set does not contain

No option here reaches SPEC §5's mass — the 39.5% of `Read` bytes belonging to files a run never
mentions again — and none claims to. Nothing here measures whether a model does worse with a
pointer where an answer was; that is invariant I10, every option inherits it, and none improves
it. And nothing here is milestone 3: the only instrument that answers "does this configuration
cost less per *successful* task" is `winnow trial`, which is built, documented, and has never
had a single arm recorded against it.
