# Option M — the filter honours no rule selection, and one is coming

**Verdict: take it, and take it before the labelling study runs.** This is the only item in
this proposal set where doing nothing has a scheduled failure date. `docs/MILESTONE-2-VALIDATION.md`
exists to produce a number that switches a rule off; on the day it does, `plan` and `fork` stop
firing that rule and the filter goes on firing it, on **96.07% of what it removes**, with
nothing anywhere saying so.

## What exists in `rules.py` and what the filter reads of it

SPEC §8 defines rule selection: `--tier C|CB|CBA`, `--rule <id>`, `--no-rule <id>`.
`rules.py` implements the whole of it and more:

| Mechanism | `rules.py` | Read by |
| --- | --- | --- |
| `TIER_RULES`, `resolve_rules(tier, enable, disable, …)` | `:90-191` | `plan`, `fork`, `inspect` |
| `DISABLED_BY_DEFAULT` — rules off until a measurement says otherwise | `:118` | `resolve_rules` |
| `$WINNOW_RULES_OFF` — the same list, settable without a release | `:125-149` | `default_disabled()` |
| `suppressed_by_default()` — so a readout can say what a tier quietly lost | `:194-229` | `plan` (`plan.py:140-144`) |

`filter.apply` takes `min_bytes` and `keep_newest` (`filter.py:226-230`) and nothing else.
`filter.rule_for` takes no `enabled` set. `proxy.Config` (`proxy.py:109-117`) has fields for
upstream, port, min_bytes, keep_newest, ledger, verbose and off_file. `proxy.config_from_env`
(`proxy.py:310-330`) reads `WINNOW_FILTER_UPSTREAM`, `_PORT`, `_MIN_BYTES`, `_KEEP_NEWEST`,
`_VERBOSE`, `_LEDGER`, `_OFF_FILE`. `winnow filter`'s parser (`cli.py:640-678`) offers
`--port`, `--upstream`, `--min-bytes`, `--keep-newest`, `--ledger`, `--off-file`, `--verbose`,
`--force`.

**Checked: the strings `resolve_rules`, `default_disabled`, `DISABLED_BY_DEFAULT`,
`RULES_OFF_ENV`, `--rule` and `--no-rule` appear nowhere in `filter.py`, `proxy.py` or
`cmd_filter`.** The filter's rule set is three literals in an `if` chain and there is no way to
change it short of editing the file.

## Why that is not merely an omission

`DISABLED_BY_DEFAULT` ships empty and `rules.py:114-117` says exactly why:

> **Empty, and it stays empty until the 200-sample blind label has been scored.** A rule turned
> off here without a number behind it would be the tool asserting a precision nobody measured,
> which is the failure mode this whole milestone exists to avoid. `docs/MILESTONE-2-VALIDATION.md`
> is the procedure that fills it.

That procedure is written, the harness is committed (`src/winnow/validate/`), and its scorer
already prints the remediation verbatim (`validate/score.py:305-312`):

> BELOW BAR ON THEIR OWN: … — disabled by default even though the aggregate may pass. To act on
> this now:
>   `export WINNOW_RULES_OFF=B2`
>   and set `winnow.rules.DISABLED_BY_DEFAULT` to the same, with this score in the commit
> message.

MILESTONES' rule is *"a rule below 90% on its own is disabled by default even if the aggregate
passes"*. So the sequence is designed, documented and one command away: someone labels 200
results, a rule comes in under 90%, they export a variable, and from that moment the pruner and
the filter disagree about what winnow believes.

**The disagreement is not symmetric.** The filter is the aggressive half — it removes bytes
from a live request that the model is about to read — and it is the half the switch does not
reach.

## What is at stake, by rule

**Measured here, 2026-08-27**, over the 867 main-session transcripts on this container, at
`min_bytes = 2048`:

| Rule | Results | Bytes | Share of the filter's reach |
| --- | ---: | ---: | ---: |
| B2 Bash inspection | 4,466 | 22,335,194 | **96.07%** |
| C3 passing verification | 234 | 843,390 | 3.63% |
| C1 locator | 15 | 70,729 | 0.30% |
| **total** | **4,715** | **23,249,313** | 100% |

(Consistent with [00-problem.md](00-problem.md)'s 8.15% / 0.31% / 0.03% of message content; the
corpus gained a session between the two runs and the drift is the tenth of a percent that
document's method note records.)

**`WINNOW_RULES_OFF=B2` takes 96% of the filter's reach away from the pruner and none of it
away from the filter.** `WINNOW_RULES_OFF=C3` takes 3.6%, `=C1` takes 0.3%. The three cases are
not equally serious and only one of them is likely: B2 is the rule with the largest mass, the
loosest semantics (`bash_head` over a 29-name allowlist, first token of the first segment) and
therefore the one a labeller is most likely to find imprecise.

And note which direction the error runs. A rule disabled for measured imprecision is one whose
removals a human judged *needed again*. The filter would go on making exactly those removals,
on the request where the model was about to read the result, with no `winnow recover` behind it
([10-option-recall-store.md](10-option-recall-store.md)) — while `winnow plan`, run over the
same session, reported that it would remove nothing.

## The second half: the filter has no tier at all

Rule selection is not only a kill switch. `--tier CB` is the default everywhere else in the
tool and `--tier C` is the conservative setting SPEC §8 offers an operator who does not trust
tier B. **There is no way to run the filter at tier C.** The operator who reads SPEC §4, decides
B2 is too loose for their work, and runs `winnow plan --tier C` gets what they asked for; the
same operator running `winnow filter` gets B2 on 96% of the mass and no flag that says so.

That is the same class of defect as the one `suppressed_by_default` exists to prevent
(`rules.py:200-209`): *"[a] tier that quietly means fewer rules than its own name lists is the
silent-fallback SPEC §10 forbids"*. Here it is the mirror image — a component that quietly
means *more* rules than the operator selected, because it never asked.

## What the change is

Four pieces, none of them large.

1. **`apply` takes an `enabled: frozenset[str]` and passes it to `rule_for`**, which returns
   `None` for a rule not in the set. With [14-option-one-rule-engine.md](14-option-one-rule-engine.md)
   taken, this is already the shared function's signature and the change is one argument.
2. **`Config` grows `rules: frozenset[str]`**, resolved once at startup by
   `rules.resolve_rules(tier, enable, disable)` restricted to the prefix-determined set, so an
   operator naming C2 gets a usage error rather than silence.
3. **`winnow filter` grows `--tier`, `--rule`, `--no-rule`**, with the same help text `plan` and
   `fork` carry — including the pointer to `$WINNOW_RULES_OFF`, which is the whole point.
4. **The startup banner says what is on.** `proxy.serve` already prints
   `keep_newest=… min_bytes=…` (`proxy.py:286-287`); it should print the rule set and, when
   `suppressed_by_default` is non-empty, the sentence `plan` prints — that a default took a rule
   away and which `--rule` puts it back.

**Resolution has to happen once, at startup, and never per request.** `default_disabled()` reads
`os.environ` at call time (`rules.py:141-142`); calling it inside `apply` would make the filter's
verdict depend on a value that could change while the process runs, which is a §K10 determinism
break and a §K1 break in the worst way — the same conversation rendering two ways because
someone exported a variable in another shell. Resolve at startup, hold the frozenset in
`Config`, and a change needs a restart. That is the correct trade: the kill switch that works
without a restart is `~/.winnow/filter-off`, and it already exists.

## Which constraints it strains

- **§K1** — none if resolution is at startup, fatal if it is per request. The constraint is not
  "the filter must never change its rule set"; it is that it must not change it *within one
  conversation*. A restart between two requests of a live session would do exactly that, and it
  is worth saying plainly that this option makes a mid-session restart with a changed selection
  a way to break a cache. So does changing `--min-bytes` between restarts, today, and nothing
  says so either.
- **§K3** — a tier and two repeatable flags are flags. DECISIONS §D6's line — *"two call sites
  is not a pattern; flags are enough until they are not"* — is not crossed; this is the third
  call site of an existing flag set, not a new configuration language.
- **§K10** — the option exists to satisfy it. A tool that fires a rule the operator disabled is
  *"a fallback that silently strips one they did not"* in the plainest possible sense.

## What it breaks

**Nothing in the suite.** `apply`'s new parameter defaults to the current set, so the 39 tests
in `tests/test_filter.py` pass unchanged. The test it owes is the one that would have caught
this: `WINNOW_RULES_OFF=B2` in the environment, `winnow filter` started, a `git status` result
of 3,000 bytes on the wire, and an assertion that it comes out whole.

**It makes one number worse before it makes it better.** The filter's headline is 8.49% of
message content and 96% of it is B2. An operator who reads this option, runs the label, and
finds B2 under the bar is left with a component worth 0.33% — and that is the correct outcome,
because the alternative is a component worth 8.49% of bytes and an unknown amount of damage.
[00-problem.md](00-problem.md) already says the shape of it: *"[t]he intake filter is rule B2
and a rounding error."* This option is the argument that a mechanism resting that heavily on one
rule must be wired to the one switch that can turn that rule off.

## The strongest case against

**That the filter is a different instrument and inherits the selection wrongly.** The argument:
`DISABLED_BY_DEFAULT` is filled from a study whose subject is *the pruner's* strips — 200
results sampled by `winnow.validate sample` at tier CB from transcripts, labelled against *"the
surrounding turns"*. The question a labeller answers is "was the content of this tool result
needed again after the point it was produced?" For the pruner that question is asked about a
result far back in a cold session. For the filter it is asked about a result one request old,
on a live conversation, with the model still mid-task. **The same rule can be right in one
position and wrong in the other**, and B2 is exactly where they would come apart: a `git status`
from forty turns ago is plainly once-only, and the one from the turn before last may be what the
model is reasoning from.

That objection is right and it argues for *more* wiring, not less. If the two positions need
two precisions, then the filter needs its own selection **and its own default set** — a
`FILTER_DISABLED_BY_DEFAULT`, filled by a labelling study that samples the filter's removals in
the filter's position. What it cannot justify is the present arrangement, where the filter has
no selection at all and therefore silently inherits *no* measurement rather than the wrong one.

The weaker objection — that nobody has run the label, so the failure is hypothetical — answers
itself. `docs/MILESTONE-2-VALIDATION.md` is a document written *"[f]or a session with no memory
of the one that built the harnesses"*, with the commands in order and the bars quoted from
MILESTONES. It is designed to be run by someone who has not read this. When they run it and
export the variable the scorer tells them to export, nothing will warn them that half the tool
did not hear.
