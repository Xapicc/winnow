# Option R — the ledger as a durable artefact

**Verdict: take the version field and the type tag. Reject rotation on the measured size, and
say what the threshold would be rather than leaving it unbounded.** `~/.winnow/filter.jsonl` is
the only thing this component leaves behind, two commands read it, it has absorbed three schema
changes by inference, and nothing in it says which schema it is.

## What it is and who reads it

One JSON line per changed request, appended by `proxy._append_ledger` (`proxy.py:265-277`) after
the upstream response headers arrive, stamped with the API's own `request-id`. The shape is
`ledger_line` (`filter.py:319-347`): `request_id`, `model`, `cache_ttl`, `dropped[]`,
`deferred[]`, `bytes_dropped`, `bytes_deferred`, `tool_results_seen`.

Two readers, and they already disagree — `savings.read_ledger` (`savings.py:164`) collapses on
`tool_use_id`, `inspect.read_filter_ledger` (`inspect.py:236-271`) sums `bytes_dropped` over
joining lines with no collapse. [01-constraints.md](01-constraints.md) §K7 records that as a
defect in existing code, and a version field does not fix it. What a version field fixes is the
next one.

## Three schema changes have already happened, and each was absorbed by guessing

COZEMPIC §3.5.1 records the migration in a table: *"[t]hree fields were added to the ledger
line"* — `tool_use_id`, `model`, `cache_ttl`. `savings.read_ledger` handles their absence by
inference and reports it, and `report.to_dict` surfaces three separate counters
(`report.py:319-321`):

```
legacy_lines_without_tool_use_id
lines_without_model
lines_without_cache_ttl
```

Each is a reader deducing the schema from which keys are present. That works and it is not free:
`read_ledger`'s docstring (`savings.py:164-174`) explains that a line without `tool_use_id` falls
back to de-duplicating on `(tool, rule, bytes)`, *"which can merge two genuinely distinct results
that happen to agree on all three"*, and takes the undercount deliberately because *"[b]oth
errors the fallback can make are undercounts, which is the direction a savings claim should err
in."*

That reasoning is sound for a *known* migration. It is unavailable for an unknown one. A line
written by a future filter with a differently-meaning `bytes` field — net rather than gross,
which is exactly what [16-option-guards-by-name.md](16-option-guards-by-name.md) and
[05-option-truncate-instead-of-drop.md](05-option-truncate-instead-of-drop.md) would both need —
is indistinguishable from a current line, because both carry every key the reader checks for.
**The next migration is a silent misreading rather than a counted fallback**, and there are at
least three candidate migrations live in this proposal set: a `pointer_bytes` or `retained_bytes`
field (§05, §06, §16), a discriminator so option J's prefix lines can share the file
([12-option-prefix-readout.md](12-option-prefix-readout.md) §K5), and `usage` integers read off
the response ([11-option-read-the-response.md](11-option-read-the-response.md)).

**The change is two keys and about ten lines of reader.** `{"v": 1, "kind": "filter", …}`, with
both readers treating a missing `v` as 0 and reporting the count exactly as they already report
`lines_without_model`. `kind` is what lets one file carry more than one record type, which
option J needs and which both readers currently cannot do because they key off field presence
rather than off a tag.

## How big it gets, measured

The filter is stateless, so it re-drops every earlier result on every later request, and each
of those is an entry. A session with *n* distinct candidates writes *n* lines whose entry counts
are 1, 2, … *n* — **quadratic in the session's candidate count.**

**Measured here, 2026-08-27.** The three no-hindsight rules replayed over the 867 main-session
transcripts on this container, with `ledger_line` called on the plan each request would have
produced:

| | |
| --- | ---: |
| sessions with at least one candidate | 584 of 867 (67.4%) |
| distinct removals | 4,716 |
| **ledger entries that would have been written** | **40,396** |
| **echo factor** | **8.6×** |
| ledger lines | 4,129 |
| **total ledger bytes** | **4,702,999 (4.7 MB)** |
| longest single line | **5,401 bytes** |
| lines over 4 KiB | 31 |
| lines over 8 KiB | 0 |
| most candidates in one session | 54 |

Two readings.

**4.7 MB is not a rotation problem.** That is the whole history of this operator's machine — 867
sessions over however many months — and it is 20% the size of the 23.2 MB it describes. At that
rate the file reaches 100 MB after roughly twenty times the corpus. Rotation would be code, a
policy, and a second thing for `savings` and `inspect` to know about, bought against a growth
rate of about 5 KB per changed request.

**The 8.6× is the 27.2× again, on disk.** COZEMPIC §3.5.1's headline error was *"1,283 removal
events across 403 lines are 49 distinct results"* — a 26× echo on one real ledger against 8.6×
in this simulation, and the gap is explained by that ledger's sessions being longer-running than
the corpus median. The de-duplication that fixes the arithmetic does not fix the file: **the
echo is what the ledger is made of**, because a stateless filter has no way to know which of the
results it is dropping it has dropped before. Nothing here proposes to change that — the
alternative is state, and [03-option-hindsight-rules-at-a-paid-boundary.md](03-option-hindsight-rules-at-a-paid-boundary.md)
argues at length why state in this process is the expensive kind.

**What a threshold would be, so the absence of rotation is a decision.** The line size is bounded
by about 92 bytes per dropped entry, so 8 KiB is crossed at roughly 89 candidates in one
session — 1.6× the largest seen. A file bound is the honest place to put a limit if one is
wanted: `--ledger-max-bytes`, refusing to append and saying so on stderr, which is the same
best-effort discipline `_append_ledger` already has (*"[a] ledger that cannot be written is
worth a line on stderr and nothing more"*). Milestone 2's third open criterion is *"the disk
cost of accumulated forks measured over a week rather than estimated"*
(`docs/MILESTONE-2-VALIDATION.md` §3); the filter's ledger is a second growing artefact under
the same question and it is not in that document.

## Can concurrent appends interleave

**Within one process, no, and it is checked.** `_LEDGER_LOCK` is a module-level
`threading.Lock` (`proxy.py:262`) and `_append_ledger` holds it across `mkdir`, `open`, `write`
and `close` (`proxy.py:272-275`). `ThreadingHTTPServer` gives each request its own thread and
they all take that lock, so two handlers cannot interleave a line. That is the only concurrency
the shipped configuration has.

**Across processes, there is no lock at all.** Two `winnow filter` instances pointed at the
same `--ledger` — one per project, or an old one that outlived the terminal that started it —
serialise on nothing. Two things then matter and only one is settled.

*Settled.* A line under 8,192 bytes is held in Python's buffer until close and reaches the file
in one flush. **Checked**: writing 5,000 bytes leaves the file at 0 until close; writing 9,000
leaves it at 9,001 *before* close, so the default 8,192-byte buffer has already flushed
mid-write. Whether that flush becomes more than one `write(2)` call — which is what would decide
atomicity under `O_APPEND` — is not establishable from Python and is not claimed here.

*Unsettled and bounded.* Every line in this simulation is under 8 KiB, the largest by 34%. So
the exposure is a bound rather than an observation: **a session with about 89 candidates would
produce the first line that could tear**, against a maximum of 54 seen.

The consequence of a torn line is worth naming because it is asymmetric.
`savings.read_ledger` counts it into `parse_errors` and the readout says so;
`inspect.read_filter_ledger` (`inspect.py:250-253`) does `continue` on a `JSONDecodeError` and
reports nothing, so the correction it exists to apply is silently smaller. That is the same
asymmetry §K7 already records between the two readers, arriving through a different door, and it
is the argument for fixing them together rather than for a lock.

## Which constraints it strains

- **§K5** — the ledger is one of the three artefacts §K5 says survive SPEC §3's refusal, on the
  grounds that they are *"append-only records of what happened"* that *"nothing is queried to
  decide anything"*. A version field keeps that true. A rotation policy starts to make it a
  managed store with a retention horizon, which is the thing §3 refuses — so the argument
  against rotation is not only that 4.7 MB is small.
- **§K6** — writing is already best-effort and must stay so. A version check that could refuse
  to append would make the record a precondition for the request.
- **§K2** — nothing new. No second file, no second handle.

## What it breaks

**Every ledger written before the change becomes a `v: 0` line**, which is exactly what the
three existing counters already describe, so the readers need one more counter and no new
inference path. `tests/test_savings.py` builds ledgers by hand and would need `v` added or,
better, a fixture built by calling `ledger_line` — which is the shape a golden would want
anyway ([23-option-golden-wire-fixture.md](23-option-golden-wire-fixture.md)).

## The strongest case against

**That a version field is ceremony, and the three migrations it was supposed to prevent were all
handled correctly without it.** `tool_use_id`, `model` and `cache_ttl` were each added, each
absorbed by a documented fallback, each counted in the readout, and the arithmetic was fixed by
identity rather than by a schema. A `v` key would have changed none of that, and the project's
own DECISIONS §D6 discipline — *"flags are enough until they are not"* — cuts against adding
structure ahead of a need.

The reply is that all three additions were *additive*, which is the easy kind, and the readers
survived by asking "is this key present". **The migrations queued up in this proposal set are
not additive: they change what an existing key means.** `bytes` becoming net rather than gross
(§16), or per-block rather than per-result (§19), or partial rather than total (§05), each
produces a line that every current reader parses successfully and prices wrongly — in the
flattering direction, which is the direction COZEMPIC §3.1, §3.4 and §3.5.2 each record an error
in. A version field is the cheapest thing that turns those from silent to loud, and it costs two
keys in a file that is already 4.7 MB of echoes.
