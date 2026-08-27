# Implementation sketch

For the twelve items [25-recommendation.md](25-recommendation.md) recommends and nothing else.
Each entry gives the files, the shape of the change, the tests that would have to exist, and why
it sits where it does in the order. Nothing here is written; this is a sketch of what writing it
would involve, and the line numbers are this checkout's.

**One landing rule throughout.** Every item below is a separate commit and every one leaves the
suite green. Three of them change behaviour at a non-default flag and none changes behaviour at
the defaults except items 6 and 9, which are the two the readout has to announce.

---

## 1. The deferral boundary — `newest_candidate` becomes the earliest

**Files:** `src/winnow/filter.py`, `tests/test_filter.py`.

**Shape.** `filter.py:278-286`, one guard:

```python
     for m_index, b_index, block, rule, size in candidates:
         name = uses.get(block.get("tool_use_id", ""), ("", {}))[0]
         if id(block) in exempt_ids:
-            newest_candidate = (m_index, b_index)
+            if newest_candidate is None:          # the *earliest* deferred candidate:
+                newest_candidate = (m_index, b_index)   # every deferral must sit after the boundary
```

and rename the variable to `boundary_before` or `oldest_deferred`, because `newest_candidate` is
how the defect reads as correct.

**Tests.** One that fails on the current code:

- `test_a_deferred_result_is_never_inside_the_write_region` — three `Bash` turns, all
  candidates, `keep_newest=2`; assert every position in `plan.deferred` is strictly greater than
  the last breakpoint position. Today `b` at (3,0) sits before the only breakpoint at (4,0).
- `test_keep_newest_can_be_raised` (`:188-194`) keeps its existing assertions —
  `plan.bytes_dropped == len(BIG)` and `len(plan.deferred) == 2` are both unaffected — and gains
  the breakpoint position.

**Why first.** It is the only item that costs money today, it is one word, and item 10's
generator should be written against code where it already passes.

---

## 2. G4, and a floor under `--min-bytes`

**Files:** `src/winnow/filter.py`, `src/winnow/cli.py`, `tests/test_filter.py`.

**Shape.** In `apply`'s drop branch (`filter.py:288-291`), build the pointer first and refuse if
it does not shrink the result, using the pruner's own comparison so there is one G4 in the tree:

```python
text = pointer(name or "tool", rule, size)
if rules.inflates(text, size):        # rules.py:638-647 — strictly longer
    plan.guard_blocked_g4 += 1
    continue
block["content"] = text
```

`Plan` gains `guard_blocked_g4: int = 0`; `ledger_line` emits it only when non-zero, or not at
all until item 8 gives the line a version. In `cli.py:662-663`, `--min-bytes` gets a validating
type — the same shape as `_break_even_budget` (`cli.py:406`) — refusing anything below the
longest pointer the current rule set can produce (**118 bytes, checked**, for `Bash`/`B2` and an
eight-digit size) with exit 1, which is SPEC §8's usage-error code.

**Tests.**

- `test_a_pointer_that_would_inflate_is_refused` — `min_bytes=10`, a 30-byte result, assert the
  content is unchanged and the refusal is counted.
- `test_min_bytes_below_the_pointer_is_a_usage_error` — through the CLI parser, exit 1.

**Why second.** It changes nothing at the default and it is a precondition for item 9.

---

## 3. Count every breakpoint, not only the ones in `messages`

**Files:** `src/winnow/filter.py`, `tests/test_filter.py`.

**Shape.** `_count_breakpoints` (`filter.py:164-171`) takes the whole body rather than
`messages`, and adds the two places a `cache_control` can legally sit outside the conversation:
`body["system"]` when it is a list of blocks, and each entry of `body["tools"]`. `apply`'s call
site (`filter.py:296`) passes `body`. `_ttl_in_force` (`filter.py:207`) calls it too and its
meaning is unchanged — a request whose only breakpoint is on `tools` does have a write class.

**Tests.**

- `test_a_breakpoint_on_tools_counts_against_the_cap` — three breakpoints in `messages`, one on
  a tool definition, one candidate; assert the filter does not place a fifth.
- `test_a_breakpoint_on_system_gives_the_request_a_write_class` — `plan.cache_ttl` is not `None`
  when the only `cache_control` is on `system`.

**Why third.** It is the one defect in the list whose failure mode is a 400 rather than a bill,
and item 10's property test needs the corrected counter to assert the cap.

---

## 4. One meaning for `bytes_dropped`, and a glob that can see a sub-agent

**Files:** `src/winnow/inspect.py`, `src/winnow/savings.py`, `tests/test_inspect.py`,
`tests/test_savings.py`.

**Shape.** `read_filter_ledger` (`inspect.py:236-271`) collapses on `tool_use_id` before summing,
with the same two-key fallback `savings.read_ledger` documents (`savings.py:164-174`): an entry
with an id is exact, one without falls back to `(tool, rule, bytes)`, and a triple already
claimed by an id-bearing entry blocks a later id-less one. The two readers should share that
collapse rather than each carrying it — a `savings.collapse_removals(lines)` both import is the
smaller change and the one `rules.py`'s docstring argues for by analogy.

`find_transcripts` (`savings.py:295`) globs `**/*.jsonl` instead of `*/*.jsonl`, so a request
made by a sub-agent can join. **This is a measurement as much as a fix**: COZEMPIC §3.5.2
reports 34 priced against 15 unjoinable on the one real ledger, and
[08-option-mcp-and-subagent-output.md](08-option-mcp-and-subagent-output.md) names the glob as a
candidate cause nobody has checked. Land the glob change and re-run `winnow savings` against the
same ledger; if the unjoinable count does not move, the cause is elsewhere and that is worth
knowing.

**Tests.**

- `test_the_ledger_is_joined_on_request_id` (`tests/test_inspect.py:517-540`) currently uses one
  line per session and must gain a repeat: the same `tool_use_id` on forty lines, asserting
  `FilterLedger.bytes_dropped` counts it once.
- `test_two_readers_agree_on_one_ledger` — build one ledger, read it with both, assert the byte
  totals match. This is the test whose absence let the two diverge.
- A sub-agent transcript fixture under `*/*/subagents/`, joined.

**Why fourth.** Item 7 wires this number into a refusal.

---

## 5. Rule selection reaches the filter

**Files:** `src/winnow/filter.py`, `src/winnow/proxy.py`, `src/winnow/cli.py`,
`tests/test_filter.py`.

**Shape, in two steps, and the split matters.**

*5a — the parameter.* `rule_for(name, tool_input, is_error, enabled=STATELESS_RULES)` returns
`None` for a rule not in `enabled`; `apply` grows `enabled: frozenset[str] = STATELESS_RULES`
and threads it. `proxy.Config` grows `rules: frozenset[str]`; `config_from_env` resolves it
once; `cmd_filter` grows `--tier`, `--rule`, `--no-rule` with the help text `plan` already
carries, including the `$WINNOW_RULES_OFF` pointer (`cli.py:382-391`). Resolution calls
`rules.resolve_rules(tier, enable, disable)` **intersected with the prefix-determined set**, so
naming `C2` is a loud usage error rather than a silent no-op.

*5b — the shared engine.* `rules.stateless_rule_for(name, tool_input, is_error, enabled)` holds
the C1/C3/B2 chain; `filter.rule_for` becomes a call that applies G3 and delegates;
`_first_matching_rule`'s C1/C3/B2 branches delegate to the same function without G3, because its
contract is a guard-filtered call. A `PREFIX_DETERMINED` dict sits beside `RULE_TIER`
(`rules.py:89`).

**Resolution is at startup and never per request.** `default_disabled()` reads `os.environ` at
call time (`rules.py:141-142`); calling it inside `apply` would let a shell export change what a
live conversation renders to, which is a §K1 break of the worst kind.

**Tests.**

- `test_a_disabled_rule_does_not_fire_on_the_wire` — `WINNOW_RULES_OFF=B2` in the environment,
  a 3,000-byte `git status` result, assert it comes out whole.
- `test_the_filter_refuses_a_rule_it_cannot_fire` — `--rule C2`, exit 1, and the message names
  the reason.
- `test_the_two_engines_agree_on_every_non_error_input` — the cross-product of `LOCATOR_TOOLS`,
  `LOCATOR_GREP_MODES`, `VERIFICATION_RE`'s alternatives and `INSPECTION_HEADS` ∪
  `INSPECTION_GIT_SUBCOMMANDS`, asserting `filter.rule_for(...) == stateless_rule_for(...)`.
  **This is the test whose absence made the duplication invisible** — on this corpus the two
  agree on all 63,931 non-error results and disagree on all 753 error ones.
- The startup banner asserts what it printed, including `suppressed_by_default`'s sentence.

**Why fifth, and why split.** 5a is the urgent half and 5b is the tidy half; shipping 5a alone
leaves a duplicated chain with an `enabled` parameter, which is worse than today by one
argument and better by the whole of the switch. If only one lands, it must be 5a.

---

## 6. Defer by turn

**Files:** `src/winnow/filter.py`, `tests/test_filter.py`.

**Shape.** `_index_tool_uses` (`filter.py:128-142`) records the message index of the `tool_use`
block as well as its name and input: `id → (name, input, m_index)`. The exemption then groups:

```python
turn_of = {}                                  # result position → the turn it answers
for m_index, b_index, block, rule, size in results:
    use = uses.get(block.get("tool_use_id", ""))
    turn_of[(m_index, b_index)] = use[2] if use else (m_index, b_index)
order = list(dict.fromkeys(turn_of[p] for p in positions_in_wire_order))
exempt_turns = set(order[-keep_newest:])
```

and a result is exempt when its turn is in `exempt_turns`. `boundary_before` is the earliest
exempt *candidate* — which is item 1's change, now doing the work it was always meant to do.

**Group on the `tool_use`'s message, not on the result's own.** §04 words the change as
grouping by *"the message they sit in"*, and that is right only if Claude Code puts *N*
`tool_result` blocks in one user message. **Every user record in this corpus carries exactly one
`tool_result` — 64,651 of 64,651 [measured here]** — so the wire layout is not observable from
disk and the grouping must be robust to both. The `tool_use` index is the key that is correct
either way, and `_index_tool_uses` already walks every block to build it.

**Tests.**

- `test_a_parallel_batch_is_exempt_as_one_turn` — one assistant message with three `tool_use`
  blocks, their three results, all candidates; assert all three are deferred and none is
  pointered. **No test in the file constructs this shape today**, which is why the defect is
  there.
- The same body split across three user messages, asserting the same outcome — the layout
  robustness.
- `test_the_boundary_lands_in_front_of_the_whole_batch` — assert the breakpoint precedes the
  first result of the batch, and that a non-candidate result inside the batch is therefore also
  outside the write region, which is the 1,471,491 bytes §04 prices.
- Grow the conversation one turn and assert all three are then pointered.

**Why sixth.** It changes default behaviour, so it wants item 1's boundary fix and item 5's
tests already in place.

---

## 7. `plan` and `fork` can be told

**Files:** `src/winnow/cli.py`, `src/winnow/plan.py`, `src/winnow/fork.py`,
`src/winnow/report.py`, `tests/test_plan.py`, `tests/test_fork.py`.

**Shape.** `--filter-ledger` on both parsers, copying `inspect`'s help text verbatim
(`cli.py:330-335`); `plan_command` and `fork_command` grow `filter_ledger: Path | None = None`
and pass it to `inspect_session`, which already accepts it (`inspect.py:278`). `build_plan`
(`plan.py`) takes the report it is given, so the plumbing is the parameter and the call site.

Then two readout changes and no arithmetic change yet: `plan` prints `inspect`'s
*"the API saw …"* block (`report.py:186-193`) when a ledger was supplied, and states in words
that `S` is still measured from disk. `fork` prints the same and, when the ledger joins, says how
many of this session's requests it covers.

**Leave the positional `S` correction out of this commit.** Subtracting the filter's removals
from the suffix needs per-result positions, and `FilterLedger` keeps `bytes_dropped` and
`by_rule`, not positions. It is a second change with its own test, and shipping the denominator
first is what makes the second one checkable.

**Tests.**

- `test_plan_uses_the_wire_denominator_when_given_a_ledger` — a fixture session plus a ledger
  covering some of its requests; assert the share moves and the readout says which denominator
  it used.
- `test_fork_says_the_session_was_filtered` — the join reported, not silently applied.
- **A session fixture representing a filtered session, which this repository does not have.**
  `tests/fixtures/sessions/` holds seven and none of them has a ledger beside it.

**Why seventh.** It depends on item 4 and on nothing else, and it is the only recommended change
whose whole implementation is outside the credential path.

---

## 8. The ledger grows a version, a kind, and a heartbeat

**Files:** `src/winnow/filter.py`, `src/winnow/proxy.py`, `src/winnow/savings.py`,
`src/winnow/inspect.py`, `src/winnow/report.py`, `tests/test_savings.py`,
`tests/test_filter.py`.

**Shape.** `ledger_line` emits `"v": 1, "kind": "filter"` alongside the existing keys. Both
readers skip a line whose `kind` is present and not `"filter"`, treat a missing `v` as 0, and
count `lines_without_version` beside the three counters `report.py:319-321` already prints.

`Stats` gains `tool_results_seen` and `candidates` and splits `errors` into `unreadable` and
`filter_errors`; `_rewrite` feeds them from the plan it already holds; `Stats.line` renders all
of it. `_relay` emits a `{"kind": "heartbeat", …}` line every *N* requests through
`_append_ledger`, which is already best effort and already catches `OSError`.

**Tests.**

- `test_a_heartbeat_line_is_skipped_by_both_readers` — the failure this ordering prevents is a
  heartbeat arriving in `savings.read_ledger` as `malformed_entries` and in
  `read_filter_ledger` as a `request_id` matching nothing.
- `test_stats_counts_what_it_looked_at` — a request with results and no candidates leaves
  `filtered` at 0 and `tool_results_seen` above it.
- `test_stats_line_reports_passthrough_on_error` (`:401-408`) updates.

**Why eighth.** `v` and `kind` have to exist before item 12 puts a second record type in the
file, and the heartbeat is the reason `kind` is not ceremony.

---

## 9. The floor moves to 256

**Files:** `src/winnow/filter.py`, `src/winnow/proxy.py`, `src/winnow/cli.py`, `docs/`.

**Shape.** `DEFAULT_MIN_BYTES = 2048` becomes `FILTER_MIN_BYTES = 256` with the arithmetic in
the comment — `D > P·(2.0 + 0.1T)/(1.0 + 0.1T)`, bounded between *P* and 2*P*, so 230 bytes at
*T* = 0 and 120 at *T* = 224 — replacing the sentence at `filter.py:46-48` that asserts sameness
with the pruner. `Config.min_bytes` and `config_from_env`'s default follow. The startup banner
already prints the value; it should also print that it differs from `plan`'s deliberately.

**Tests.**

- `test_the_filter_and_the_pruner_disagree_about_the_floor_on_purpose` — assert
  `FILTER_MIN_BYTES != rules.DEFAULT_MIN_BYTES` with the reason in the docstring, so closing the
  gap requires deleting a test that says why not.
- A result between 256 and 2,048 is claimed; one below 256 is not.

**Why ninth.** It needs item 2 — at 256 the headroom over a 118-byte pointer is 2.2×.

---

## 10. The property test

**Files:** new `tests/test_filter_properties.py`.

**Shape.** A `random.Random(seed)` generator over a fixed seed list, building bodies from a
grid: 1–8 turns, 1–4 results per turn, rules drawn from {C1, C3, B2, none}, sizes straddling the
floor, `is_error` sometimes true, 0–4 client breakpoints including on the newest block, and the
awkward shapes — a non-dict block, string-valued message `content`, a missing `tool_use_id`, a
list-form `tool_result`. Four assertions:

- **W1** every position in `plan.deferred` is strictly after the last breakpoint in `messages`.
- **W2** replay a growing conversation, rebuilding the body from the client's original bytes plus
  one turn each time; no block's rendering changes after the first request in which it was at or
  before the last breakpoint.
- **cap** total `cache_control` across `messages`, `system` and `tools` never exceeds
  `MAX_BREAKPOINTS`.
- **G5** the multiset of `tool_use` ids equals the multiset of `tool_use_id`s, before and after.

Stdlib only — §K3 rules out Hypothesis, so there is no shrinking and a failure prints the seed
and the body. A fixed seed list makes it a regression pin rather than a flaky test.

**Why tenth.** W1 fails on the pre-item-1 code, which is how the test earns its place.

---

## 11. The golden

**Files:** new `tests/fixtures/filter/*.json` (eight request bodies), new
`tests/fixtures/filter_golden.json`, new `tests/test_filter_golden.py`.

**Shape.** `test_inspect_golden.py` copied, including `WINNOW_REGEN_GOLDEN=1` and the sentence
*"[r]egenerate deliberately, never to make this pass"*. Per fixture the golden records the
emitted body as `json.dumps(body)` — **not** sorted, because sorting would pin something the
wire never carries — plus `ledger_line(plan)` and `plan` as a dict. The eight fixtures are the
branch table in [23-option-golden-wire-fixture.md](23-option-golden-wire-fixture.md), two of
which are shapes no existing test constructs.

**Why eleventh.** It should be generated from code that has items 1–9 in it, or the first commit
after it is a regeneration.

---

## 12. The prefix readout — a separate release

**Files:** `src/winnow/proxy.py`, `src/winnow/filter.py`, `src/winnow/savings.py`,
`src/winnow/report.py`.

**Shape.** `filter.prefix_digest(body)` returns sizes, per-tool names and byte counts, and a
sha256 of `system` and of `tools`; `_rewrite` compares against the previous request's hashes held
in memory and returns a `{"kind": "prefix", …}` ledger line only on a change. **Sizes, names and
hashes, never content** — a content dump belongs behind a flag carrying `--explain`'s warning,
and §K2's objection in that option's own file is the serious one in this whole set.

**Why last, and in its own release.** It is the only recommended item that adds a reporting
subsystem to a process in the credential path, and it should not land in the same release that is
making the filter correct. It depends on item 8's `kind` tag and it repays item 3, whose defect
it found.

---

## What the whole sketch touches

| File | Items |
| --- | --- |
| `src/winnow/filter.py` | 1, 2, 3, 5, 6, 8, 9, 12 |
| `src/winnow/proxy.py` | 5, 8, 9, 12 |
| `src/winnow/rules.py` | 5b |
| `src/winnow/cli.py` | 2, 5, 7, 9 |
| `src/winnow/inspect.py` | 4, 8 |
| `src/winnow/savings.py` | 4, 8, 12 |
| `src/winnow/plan.py`, `fork.py`, `report.py` | 7, 8, 12 |
| `tests/` | every item; three new files and one new fixture directory |

Eight of the twelve touch `filter.py`, which is 347 lines and sits in front of an API key. That
is the argument for landing them as twelve commits rather than as one change, and for items 10
and 11 existing at all.
