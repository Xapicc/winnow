# Option L — one rule engine, or two

**Verdict: take it, as a shared function in `rules.py` with an explicit admissibility
predicate — and not by having the filter call `_first_matching_rule`.** The two engines agree
on every non-error result in this corpus today, so this is not a bug report. It is an argument
that the agreement is unguarded, that the obvious way to guard it is wrong in a specific and
measurable way, and that the right way costs about thirty lines.

## What is duplicated

`rules.py`'s module docstring is the statement of single ownership:

> `inspect` prices a cut that has not happened, `plan` says exactly what would go, and `fork`
> writes it. If any two of those disagreed about what rule B1 means, the number milestone 1
> published would not describe the file milestone 2 writes. So the rules live here and each
> command imports them.

There is a fourth reader and it is not in that list. `filter.rule_for` (`filter.py:99-120`)
answers C1, C3 and B2 from its own `if` chain:

```python
if is_error:                                                    return None
if name in LOCATOR_TOOLS:                                       return "C1"
if name == "Grep" and tool_input.get("output_mode") in LOCATOR_GREP_MODES:  return "C1"
if name == "Bash":
    command = tool_input.get("command")
    if isinstance(command, str) and VERIFICATION_RE.search(command):        return "C3"
    if is_inspection(command):                                  return "B2"
return None
```

against `rules._first_matching_rule` (`rules.py:453-520`), which answers the same three from
the same constants in the same order. **The patterns are shared and the control flow is
copied.** `LOCATOR_TOOLS`, `LOCATOR_GREP_MODES`, `VERIFICATION_RE` and `is_inspection` are all
imported from `rules` (`filter.py:38-44`), so the *data* has one owner. What has two owners is
the decision procedure: which rule is tested first, what counts as a Bash command, and whether
`is_error` is checked here or somewhere else.

## They agree today, and here is the check

**Measured here, 2026-08-27.** `filter.rule_for(name, input, is_error)` evaluated against
`rules._first_matching_rule` with `enabled = {C1, C3, B2}`, over every `tool_result` in the 867
main-session transcripts under `~/.claude/projects/*/*.jsonl` on this container — 64,684 results
with a resolvable `tool_use`:

| | |
| --- | ---: |
| results compared | 64,684 |
| verdicts identical | 63,931 |
| verdicts differing | **753** |
| …of which `is_error: true` | **753** |

**Every disagreement is an error result and there are no others.** On the 63,931 results where
`is_error` is false the two procedures are indistinguishable on this corpus. That is the
strongest statement available and it is not a proof: it says the copy is currently faithful,
not that it will stay so.

## The disagreement is a contract, and it is the trap

`_first_matching_rule` does not check `is_error`. It cannot, and the code says why at
`rules.py:483-484`: *"C3 passing verification. `is_error` was already excluded by G3, so
reaching here means the run passed."* G3 is applied by `classify` (`rules.py:414-416`) before
the engine is entered, along with G1, G2 and G5. The engine's contract is *"call me with a
guard-filtered call"*.

`filter.rule_for` has the opposite contract: it applies G3 itself, on line 108, and takes
unguarded input. Both are correct in their own component. Called across the boundary, the
mismatch is silent and it strips exactly the results SPEC §4 says must never be stripped:

```
is_error=True, `npm run test`   filter → None    engine → C3
is_error=True, `git status`     filter → None    engine → B2
is_error=True, Glob             filter → None    engine → C1
```

**So the naive version of this option — delete `rule_for`, call `_first_matching_rule` with
`enabled={C1,C3,B2}` — is a regression, not a refactor.** On this corpus it would newly claim
753 error results, **19 of them above the 2,048-byte floor, 54,046 bytes**. Small in bytes and
not small at all in kind: G3 is *"errors survive, at any tier"* (SPEC §4), and C3's whole
rationale is that *"a failing verification is never stripped — the failure is the
information"*. A filter that removed a failed `pytest` from the request before the model read
it would be removing the one result the turn existed to produce.

That is the concrete answer to "what drift is possible today": not a slow divergence over
releases, but a one-commit regression available to the next person who reads `rules.py`'s
docstring and does what it says.

## What drift is possible without anyone making a mistake

Three shapes, in decreasing order of likelihood.

**A rule gains a clause in `rules.py` and the filter does not follow.** C1 is the live example:
SPEC §4 defines it over `Glob`, `LS` and `Grep` in two output modes. If a fourth locator tool
arrives — or if `Grep` gains a mode — the constant changes and both engines follow, because the
constant is shared. But if the *shape* of the test changes — a `Grep` whose `head_limit` is 0
is not a locator, say — that is a new `if`, and it lands in one file. The filter would go on
firing C1 on a call the pruner had stopped claiming, and `winnow inspect`'s per-rule table
would stop describing what the wire does.

**The order changes.** First-match-wins is load-bearing: `rules.py`'s docstring says SPEC §6's
per-rule table *"sums to its own tier totals, which is only true if every result is attributed
to exactly one rule"*. C3 is tested before B2 in both files today, so `Bash` running `pytest`
is C3 and `Bash` running `cat` is B2. Reordering one and not the other moves bytes between
rules in the ledger's `by_rule` breakdown (`inspect.py:118-120`) without moving a single byte
on the wire — a reporting divergence that no test would catch, because no test compares the
two.

**A guard moves.** The `is_error` check is one line in each file. Either could move.

## What the fix is

Not a call into `_first_matching_rule`, and not a copy. A third function in `rules.py`, owned
there, that both callers reach:

```python
# rules.py
STATELESS_RULES = frozenset({"C1", "C3", "B2"})   # verdict fixed by the call and its own result

def stateless_rule_for(name, tool_input, is_error, enabled=STATELESS_RULES) -> str | None:
    """The subset of RULE_ORDER whose verdict cannot move mid-session (K1)."""
```

with `_first_matching_rule` delegating its C1/C3/B2 branches to it and applying its own guard
contract around it, and `filter.rule_for` becoming a call with `is_error` handled at the one
place that owns G3. Then the order, the patterns and the guard placement have one home, and
`STATELESS_RULES` is a declaration a reviewer can check against
[01-constraints.md](01-constraints.md) §K1 rather than a comment.

**The alternative shape — a per-rule admissibility flag declared beside `RULE_ORDER`** — is
better if anything is ever added to the set:

```python
RULE_ORDER = ("C1", "C2", "C3", "B1", "B2", "A1")
PREFIX_DETERMINED = {"C1": True, "C2": False, "C3": True, "B1": False, "B2": True, "A1": False}
```

sitting next to `RULE_TIER` and `TIER_RULES`, which is where every other per-rule property in
this tree lives. It costs one dict and it makes the K1 question a thing a new rule has to
answer at the point it is written, rather than a thing someone remembers to ask when the filter
is next touched. `OPT_IN_RULES` (`rules.py:100`) already establishes the pattern and the reason:
*"the day a second A-tier rule exists is the day a hard-coded `A1` quietly stops gating it."*

Take both. The flag is the declaration; the function is the enforcement.

## Which constraints it strains

- **§K1** — none, and it is the constraint the option serves. `PREFIX_DETERMINED` is K1's test
  written down where a rule is defined.
- **§K2** — the filter's surface area does not grow. `rule_for` becomes a call, and the
  imported surface of `rules` grows by one name. This is the rare option that makes the
  credential path smaller.
- **§K10** — the guard-contract mismatch is precisely SPEC §10's *"no fallback that silently
  strips one they did not [ask to strip]"*. Naming it is half of fixing it.

## What it breaks

`filter.rule_for` is imported by name in `tests/test_filter.py:22` and parametrised over nine
cases (`test_only_the_hindsight_free_rules_fire`). Keeping the name and changing the body keeps
that test meaningful; the new test the change owes is the one nobody has written —
**`filter.rule_for` and `rules._first_matching_rule` agree on every non-error input**, over the
cross-product of the constants rather than over nine hand-picked cases, so the next divergence
fails in CI instead of in a bill.

`filter.py`'s docstring at lines 24-29 says the three rules are the ones "decidable from the
call and its `is_error` alone", and `rule_for`'s own docstring (`filter.py:100-107`) says C2
"needs a later duplicate". [01-constraints.md](01-constraints.md) §K1 has already shown both
sentences give the wrong reason. If the set is going to be named in `rules.py`, the name should
be the reframed one — prefix-determined, not hindsight-free — or the reframing lives only in
this directory while the code goes on asserting the thing that was checked and found wanting.

## The strongest case against

**That two engines is the honest description of two different jobs, and merging them hides a
real difference.** The pruner classifies a *session* held in memory with every call indexed and
every guard applied in one pass; the filter classifies one block on a wire with no session, no
ordinal, no `keep_last` and no G4. `ToolCall` (`rules.py:241-259`) carries `order`, `line` and
`has_result`, none of which exists in the filter's world. A shared function has to take the
intersection of two contexts, and an intersection is where a signature grows optional
parameters until it means nothing.

The reply is that the shared part is already an intersection and it is already written twice.
`stateless_rule_for` takes exactly `(name, tool_input, is_error)` — three values both callers
hold — and the parameters the objection names are the ones it deliberately does not take.
What stays separate is what genuinely differs: the guards, the indices, the ordinals, the
substitution. What merges is the sentence "this call is a locator / a passing verification / an
inspection", which is SPEC §4 and has one right answer.

The weaker version of the objection is better: **this option buys no bytes.** It is worth
nothing on the bill today and its whole value is that a class of future error stops being
possible. Against a component whose entire present worth is +3.76% of a bill, that is a
legitimate thing to defer — and the reason to do it anyway is
[15-option-honour-rule-selection.md](15-option-honour-rule-selection.md), where the same
seam has a consequence that is not hypothetical.
