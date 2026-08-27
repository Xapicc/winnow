# Option T — `plan` and `fork` cannot be told what the filter kept off the wire

**Verdict: take it. It is one parameter threaded through two commands, and without it the
sentence the ledger exists for is only half true.** `winnow inspect` accepts `--filter-ledger`
and applies the correction. `winnow plan` and `winnow fork` do not accept it, do not read it,
and compute every figure they print — including the gate that decides whether a fork is worth
writing — from a transcript that still contains bytes the API never received.

## What the ledger was for

`filter.ledger_line`'s own docstring (`filter.py:319-334`):

> The filter never touches the transcript — Claude Code writes what it holds, which still
> contains every byte the API never saw. So `winnow inspect` read off disk overstates both `D`
> and `S` for any session this filtered, and `winnow fork` would pay `1.9·S` to remove bytes
> that are not in the prefix. **This line is what lets the pruner know**, and it is the reason
> the two can run together at all.

COZEMPIC §3.5 says the same thing and names the recipient: *"[t]he ledger is one JSON line per
filtered request and is what lets milestone 2 know."* Milestone 2 is `winnow fork` and
`winnow recover` (MILESTONES §"Milestone 2 — the actuator").

## What is actually wired

| Command | `--filter-ledger` | Reads the ledger | Where |
| --- | :---: | :---: | --- |
| `inspect` | **yes** | yes | `cli.py:330-335` → `report.inspect_command` → `inspect_session(..., filter_ledger=…)` → `inspect.py:391-392` |
| `savings` | n/a — it *is* the ledger reader | yes | `savings.read_ledger` |
| `plan` | **no** | no | `cmd_plan` (`cli.py:340-356`) passes session, tier, rule, no_rule, keep_last, min_bytes, i_know, as_json, explain, max_break_even |
| `fork` | **no** | no | `cmd_fork` (`cli.py:425-445`) passes the same plus min_cold_age, write, out, force |

`fork` calls `build_plan` (`fork.py:788`) and `inspect_session(path)` with no ledger
(`fork.py:859`), so `Report.filtered` is `None` on both paths and
`Report.wire_content_bytes` — the property whose docstring calls it *"[t]he denominator every
share should use on a filtered session"* — falls back to `message_content_bytes`
(`inspect.py:160-161`). **Checked: `wire_content_bytes` is referenced in exactly one place
outside `inspect.py`, `report.py:105` and `:193`, both of them `inspect`'s own output.**
`plan.py` uses `plan.report.message_content_bytes` at `:353`, `:479` and `:646`.

So the correction exists, is tested, is rendered — *"the API saw …"* (`report.py:186-193`) — and
is reachable only from the command that writes nothing. The two commands that decide and act
cannot see it.

## What it costs

Three figures on `plan`'s readout are computed from the wrong denominator on a filtered session,
and one of them is a gate.

**The share.** `plan` prints removed bytes against `message_content_bytes`. On a filtered
session the true denominator is smaller by whatever the filter took — **up to 8.49% of message
content** ([00-problem.md](00-problem.md)), or 10.28% on a denominator with image blocks
excluded ([19-option-content-shapes.md](19-option-content-shapes.md)). The share is understated
by that factor, in the conservative direction.

**`S/D` and `T*`.** `Plan.break_even_turns` is `19·(S/D) − 20` over `suffix_bytes` and
`net_bytes` (`plan.py:200-214`), both derived from the transcript. `S` counts bytes that are in
the file and were not in the prefix; `D` counts results the filter has *already removed once*,
which the pruner is proposing to remove again from a different artefact. The two errors do not
cancel and their ratio is what the gate turns on.

**`--max-break-even`, which is the actuator's refusal.** `Plan.pays_within(max_break_even)`
(`plan.py:227`) is what stands between an operator and a cut that costs more than it returns,
and [README.md](../../README.md#the-break-even-gate) measures what happens without it: *396
cuts, 30% of them actually paid, −$10.85 net.* **A gate computed from an uncorrected `S/D` is a
gate answering a question about a session that did not happen.**

**How much overlap there is, and it is most of it.** [03-option-hindsight-rules-at-a-paid-boundary.md](03-option-hindsight-rules-at-a-paid-boundary.md)
measures the pruner's own rules over this corpus at `keep_last = 6`, `min_bytes = 2048`: tier CB
is 27,749,546 bytes, of which C1 + C3 + B2 — the three the filter also fires — are 21,917,866.
**79.0% of what `winnow plan --tier CB` proposes to remove is content the intake filter claims
too.** On a session that ran through the filter, four fifths of the plan is about results whose
history on the wire the plan cannot see.

That is the number that makes this worth a change rather than a note. COZEMPIC §3.5's advice
for the pair — *"[w]hat is left for the pruner is C2 plus B1 — 2.2% of message content — against
an unchanged `S`, so `S/D` rises by roughly 4.6× and `T*` with it. On this corpus that
combination clears its break-even almost nowhere"* — is a conclusion an operator can only reach
by running `plan` with the ledger, and `plan` will not take it.

## What the change is

**One parameter, threaded.** `plan_command(..., filter_ledger: Path | None = None)` and
`fork_command(..., filter_ledger=…)`, passed to `inspect_session`, which already takes it. Then:

- `plan`'s denominator becomes `wire_content_bytes` and its readout says which one it used —
  `inspect` already prints *"the API saw"* and `plan` should print the same line, because a
  share that silently changed base is worse than one that is consistently conservative
  ([00-problem.md](00-problem.md) makes the same argument about the image denominator).
- `S` becomes the suffix minus the filter's removals that fall after the cut. That needs the
  ledger's per-result `tool_use_id`s matched against the session's own results, which is a join
  `inspect` does not currently do — it sums `bytes_dropped` per request and keeps `by_rule`, not
  positions. **This is the part that is not one parameter**, and it is the reason to do the
  denominator and the readout first and the positional correction second.
- `fork` refuses, or warns, when the session has ledger lines and no `--filter-ledger` was
  given. It cannot detect that on its own — the ledger is the only place the association exists
  — so the honest version is the opposite: when `--filter-ledger` *is* given and matches, say
  how many requests and how many bytes, so an operator forking a filtered session sees it.

**And fix `read_filter_ledger` first.** §K7 records that it sums `bytes_dropped` over joining
lines with no `tool_use_id` collapse, which is the sum COZEMPIC §3.5.1 says is wrong by 27.2× —
**8.6× on this corpus [measured here], 40,396 entries against 4,716 distinct removals**
([20-option-ledger-as-artefact.md](20-option-ledger-as-artefact.md)). Wiring that number into
`plan` and `fork` before correcting it would spread a known error from a readout into a gate,
and `wire_content_bytes` clamps at zero (`inspect.py:162`), so an overstated correction silently
produces a denominator of 0 and a share of nothing. **The order matters and it is: de-duplicate
the reader, then thread the parameter, then correct `S`.**

## Which constraints it strains

- **§K7** — the option is §K7's other half. §K7 says the ledger exists so the pruner can know
  and records that its reader is wrong; this says the pruner has no way to ask.
- **§K5** — none. The ledger is read by two commands already; a third reader of the same
  append-only record is not a new store.
- **§K1, §K2, §K6, §K9** — none. Nothing in `filter.py` or `proxy.py` changes. **This is the
  only option in the set whose entire implementation is outside the credential path.**

## What it breaks

`plan`'s `--json` output gains a `wire_content_bytes` key and its `message_content_bytes` keeps
its meaning, so the schema is additive. `tests/test_inspect_golden.json` pins `inspect --json`
per fixture per tier and is untouched, because no fixture is a filtered session — which is
itself worth noting: **there is no test fixture anywhere in this repository representing a
session the filter has run over.** `tests/test_inspect.py:517-540` builds a ledger with one line
per session and joins it; nothing exercises a session where the correction is large enough to
move a verdict.

## The strongest case against

**That the two tools should not be run together and the correct fix is a refusal, not a
correction.** COZEMPIC §3.5's own conclusion is that running both is *"possible and nearly
pointless"* and that *"[t]he two are alternatives on the mass that matters, not a stack"*. On
that reading, threading a ledger into `plan` is building careful arithmetic for a configuration
the project has already advised against, and the cheaper honest answer is for `fork` to refuse a
session with ledger lines unless `--force`, in the same voice it refuses a session that is too
warm.

That objection is stronger than it first looks, because a refusal is loud and a correction is
quiet, and SPEC §8's exit-code discipline prefers the loud one — *"[a] refusal is loud and names
the guard"*. It is answered on two grounds. First, `fork` **cannot** refuse without reading the
ledger, so the refusal needs the same parameter the correction does and this option is a
precondition for either. Second, "nearly pointless" was measured on the overlap, and the residue
is not nothing: C2 + B1 + A1 is **9.65% of message content** on this corpus (§03), larger than
everything the filter reaches, and §03's closing line is that *"a `fork` run against a filtered
session with `--rule A1` is the shape that combination actually wants. Whether it clears its
break-even is a `winnow plan` away and nobody has run it."* **Nobody has run it because `plan`
will not take the argument.**
