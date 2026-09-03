# winnow

A long Claude Code session is mostly tool output: across 563 transcripts, 175.6 MB of message
content, `tool_result` and `tool_use` inputs are **91.6%** of the bytes and human plus assistant text
is 8.4% ([docs/SPEC.md](docs/SPEC.md) §1). Several tools will strip that for you. **None of them can
tell you whether stripping it saved you anything**, because the conversation sits in the cached
prefix at 0.1× and every edit to it forces a full-price rewrite of everything after the cut.

winnow is an attempt to answer that question and, if the answer comes back the right way, a pruner
that only fires when the arithmetic says it pays.

> [!IMPORTANT]
> **The pruner exists. Whether it is safe to use is not yet known.** `winnow inspect` runs, and
> milestone
> 1's number has been produced: **tier CB strips 10.2% of message content pooled, 8.8% at the median**
> — against the 22.6% / 21.6% [docs/SPEC.md](docs/SPEC.md) §6 recorded and the ±3 points §9 asked it
> to reproduce within. It misses by 12.4, and 8.7 of those are one rule whose measured number was
> taken with a looser definition than the same document specifies
> ([docs/COZEMPIC.md](docs/COZEMPIC.md) §3.4). Netted against the cache — `0.1·D` earned on each turn
> that followed the cut, `1.9·S − 2·D` paid once — a tier-CB cut **pays off in 58% of sessions and is
> worth +3.27% of the bill**, on an optimistic bound, against the 15% SPEC §9 set as the target.
> `winnow plan`, `winnow fork --write` and `winnow recover` are built — milestone 2 — but **three of
> that milestone's definition-of-done items have not been answered**: whether 100 real forks all
> resume, whether ≥90% of what the rules strip was genuinely needed once, and what a week of
> accumulated forks costs on disk. Each needs production data, a person, or elapsed time rather than
> more code, and until they land the milestone is built and not passed — the commands that answer them
> are in [docs/MILESTONE-2-VALIDATION.md](docs/MILESTONE-2-VALIDATION.md). There
> is still no `winnow bench`. What there is instead is
> [`winnow filter`](#the-intake-filter): the same rules applied *before* the cache write, which never
> pays the invalidation and is worth **+3.76%** — 1.1× the pruner, and positive in every session
> rather than 58% of them.
> The other thing that runs is not the pruner either: `src/winnow/` is
> [orchestrator-safe mode](#orchestrator-safe-mode), the harness around the vendored tool that makes
> running it inside an unattended session survivable.

---

## The question

Removing half your conversation does not halve your bill. It is not obvious that it lowers it at all.

Cache reads bill at 0.1× and writes at 1.25× (five-minute) or 2× (one hour). Matching is exact and
prefix-ordered, so an edit invalidates everything after the cut point. Let *S* be the suffix after
the cut and *D* the bytes removed from it. The edit pays `1.9·S − 2·D` once, and earns `0.1·D` back on
every later turn, so it breaks even after

```
T* = 19·(S/D) − 20   further turns
```

Cut half the suffix and it pays for itself in 18 turns. Cut a tenth and it needs 170 more turns than
the session has had, and in the corpus that was measured only 807 turns out of 11,422 sat past index
160 at all. The 2.0× figure is not the
list-price assumption: it is a measurement over 26,194 turns of one install where every main-thread
turn wrote at the one-hour class, and it is recorded outside this repository in
`UsageFoundry/proposals/ContextControl/01-constraints.md`.

Three things follow, and they are the whole design:

- **`S/D` decides, not the size of the session.** The formula is model-independent and absolute size cancels. A big session is not automatically worth pruning.
- **There is exactly one moment when the edit is free.** Immediately before a handover that was going to rewrite the suffix anyway, the `2·D` term is refunded. winnow acts at resume boundaries for this reason, not out of caution ([docs/SPEC.md](docs/SPEC.md) §7).
- **The deliverable is a comparison, not a saving.** Every existing tool reports bytes or tokens removed. None reports the netted cost, and none has ever been measured against task quality ([docs/SPEC.md](docs/SPEC.md) §2).

I got this arithmetic wrong myself, once, by assuming the 1.25× multiplier from the documentation
instead of reading the measurement: that version understated invalidation by about 40 percent.
[docs/COZEMPIC.md](docs/COZEMPIC.md) §3.1 keeps the error on the record, because it is exactly the
mistake the measurement exists to catch.

## What is here today

| | |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | The specification. Content split by class, the classification rules and what they cannot decide, the six universal guards, the retrieval path, the CLI surface, and success criteria whose primary metric is deliberately not token reduction. **Not yet reconciled against the vendored code**; [docs/COZEMPIC.md](docs/COZEMPIC.md) is that reconciliation |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Eight decisions with the alternatives rejected and the cost of being wrong, plus §0, which decides what Cozempic is doing in this repository |
| [docs/MILESTONES.md](docs/MILESTONES.md) | Ten working days in three milestones, and the kill criteria, decided in advance while nobody is attached to the outcome |
| [docs/MILESTONE-2-VALIDATION.md](docs/MILESTONE-2-VALIDATION.md) | The procedure for milestone 2's three unanswered criteria, written for a session with no memory of the one that built the harnesses: the commands in order, the corpus each needs, the bar each has to clear, and the kill criteria restated where the person running them will see them |
| [docs/COZEMPIC.md](docs/COZEMPIC.md) | The vendored tool against the spec, decision by decision: six questions its code already answers, eight places the two disagree with a verdict and a reason on each, and what is still open |
| [docs/USAGEFOUNDRY.md](docs/USAGEFOUNDRY.md) | Eleven collisions between the vendored tool and the orchestrator that would run it, with evidence on both sides; §8 is orchestrator-safe mode as built, including what it does not yet prove |
| [docs/behavioral-digest-design.md](docs/behavioral-digest-design.md) | Cozempic's own design note, arrived with the merge |
| `src/winnow/filter.py`, `proxy.py` | `winnow filter` — the intake filter and the local proxy that carries it. Stdlib only, about 1,350 lines with 804 tests, of which a property test over generated conversations asserts the cache-write invariant and a golden pins the emitted bytes |
| `src/winnow/savings.py` | `winnow savings` — prices the filter's own ledger against the transcripts, de-duped on `tool_use_id` so a stateless filter's repeats are not counted as removals. Stdlib only, about 575 lines with 34 tests |
| `src/winnow/rules.py` | SPEC §4 itself: the six rules, the guards, the pointer and its ID scheme. Imported by `inspect`, by `plan` and by `fork` — one engine, so the three cannot disagree about what B1 means |
| `src/winnow/inspect.py`, `report.py` | `winnow inspect` — the reading, the byte accounting, the cache readout and `T*`. About 600 lines with 54 tests. Its `--json` output is pinned byte-for-byte in `tests/fixtures/inspect_golden.json`, because milestone 1's deliverable is a number and a number should not move by accident |
| `src/winnow/plan.py` | `winnow plan` — the dry run: which results a fork would replace, the pointer that would replace each, what the pointers cost, the net, and `T*` for the cut. Guard G4 is decided here rather than at write time, so `plan` and `fork` agree. About 450 lines with 53 tests |
| `src/winnow/fork.py` | `winnow fork` and `winnow recover` — the writer and the round trip. Consumes `plan`'s list rather than reclassifying, so the dry run is the fork you get. About 700 lines with 66 tests |
| `src/winnow/context.py` | `winnow context` — what is actually in one session's context window, by provenance, with the total taken exactly from `usage` and the parts apportioned inside it. Milestone M1 of [proposals/ContextTreemap](proposals/ContextTreemap/05-recommendation.md): the walking skeleton, six rows and a residual. About 500 lines with 30 tests |
| `src/winnow/cli.py`, `orchestrator_safe.py` | The `safe`, `inspect`, `context`, `plan`, `fork` and `recover` groups, and orchestrator-safe mode, about 1,450 lines with its tests |
| `src/winnow/validate/` | The harnesses for milestone 2's three unanswered criteria: the 100-fork resume test, the stratified blind label with its sampler and scorer, and the disk-cost series. Not imported by any `winnow` command — a measurement that could change what it measures is not a measurement — and none of it runs in the suite except through its own fixtures. About 1,900 lines with 76 tests |
| `src/winnow/legacy/`, `plugin/`, `tests/` | The tree inherited from Cozempic 1.8.39, about 21,700 lines. Renamed into winnow by [docs/FORK.md](docs/FORK.md) phase 1; still not installed and not started |
| `packaging/README.md` | The record of the six package channels, the npm shim and the PyPI release workflow that phase 2 deleted. **Winnow publishes to no channel**; installing means a checkout |
| [web/README.md](web/README.md) | The site: four static routes over what this document says, checked against its own contract in [web/docs/design-language.md](web/docs/design-language.md). Not deployed anywhere yet, and it imports nothing from this tree |

**No `winnow bench`.** Milestone 2 — `plan`, `fork` and `recover` — is here; milestone 3 is not,
so nothing in this tree has yet run a model against a forked session. **Three of milestone 2's own
acceptance criteria are also outstanding**, and none of them is short of code:

- **The 100-fork resume test.** Fork 100 real sessions, `claude --resume` each, 0 failures
  ([docs/SPEC.md](docs/SPEC.md) §9). Needs production transcripts and real model calls.
- **The 200-sample blind label.** ≥90% of stripped results confirmed once-only, per-rule precision
  reported separately. Needs production transcripts and a person reading turns.
- **A week of accumulated disk cost**, measured rather than estimated. Needs a week.

Nothing in the test suite reads `~/.claude/projects/` or shells out to `claude`, deliberately, so
that a green suite cannot be mistaken for a passed milestone. What is committed instead is a harness
for each, and [docs/MILESTONE-2-VALIDATION.md](docs/MILESTONE-2-VALIDATION.md) as the procedure:

```sh
uv run python -m winnow.validate resume --corpus ~/.claude/projects \
  --ledger resume.jsonl --results resume.json --forks 100
uv run python -m winnow.validate sample --corpus ~/.claude/projects \
  --sheet sheet.md --key key.jsonl --target 200 --seed 0   # then fill sheet.md in blind
uv run python -m winnow.validate score --sheet sheet.md --key key.jsonl \
  --results label-score.json
uv run python -m winnow.validate disk --corpus ~/.claude/projects \
  --series disk-series.jsonl --results disk.json           # and again in seven days
```

`resume` has a `--dry-run` that forks, writes and records exactly as the real run does and
substitutes only the model call. The labelling sheet's schema and its scoring rule are committed in
`src/winnow/validate/schema.py` **before any labelling**, so the bar cannot be settled after the
numbers are in. **No disk-cost figure appears anywhere in this repository**, because the first
observation and the second are a week apart and only the second one is a measurement.

`inspect` is milestone 1. Its
*population* lands where SPEC §6's method says it should — 174 sessions over 400 KB of message
content, 129.6 MB pooled, against a recorded 161 and 120.1 MB one day earlier — so the denominator is
not the disagreement. Its *rule shares* come in 12.4 points under at tier CB, and milestone 1 was
built to be allowed to say that ([docs/COZEMPIC.md](docs/COZEMPIC.md) §3.4). Every other number the
documents cite as measured still comes from analysis scripts in earlier work.

```sh
python -m winnow inspect <session-id>            # composition readout, writes nothing
python -m winnow inspect <session-id> --json     # machine-readable, for a corpus sweep
python -m winnow inspect <session-id> --tier CBA # include the opt-in tier in the arithmetic

python -m winnow plan <session-id>               # what a fork would strip, and the arithmetic
python -m winnow plan <session-id> --explain     # one line per result: rule, tool, arguments, bytes
python -m winnow plan <session-id> --no-rule B1  # override the tier, one rule at a time

python -m winnow fork <session-id>               # dry run: everything --write would do
python -m winnow fork <session-id> --write       # write the fork. The original is not touched
python -m winnow fork <session-id> --write --out f.jsonl   # somewhere other than beside the source
python -m winnow recover <session-id> b7         # the original bytes pointer b7 stands in for
```

**A rule can also be off by default**, on the strength of its own measured precision rather than one
operator's choice on one run. `winnow.rules.DISABLED_BY_DEFAULT` is that list and
`WINNOW_RULES_OFF=B2,A1` replaces it without a code change, which is how the 200-sample label above
gets acted on the hour it lands. It **ships empty**: a rule switched off with no number behind it
would be the tool asserting a precision nobody measured. A default-off rule is subtracted from the
tier before `--rule` is applied, so naming it explicitly turns it back on, and `plan` and `fork` both
say in their readout which rules the default took away and print the `--rule` that restores them — a
tier that quietly means fewer rules than its own name lists is the silent fallback
[docs/SPEC.md](docs/SPEC.md) §10 forbids. `inspect` ignores the list entirely, because SPEC §6's
per-rule table is the ceiling of the mechanism and a rule switched off for precision has not stopped
being part of that ceiling.

`inspect` reports the ceiling of the mechanism — every rule, no pointer overhead. `plan` reports one
operator's actual selection with the pointers priced in, so its `T*` is the longer and the honest of
the two. `fork` prints the same arithmetic under its own heading, because it consumes `plan`'s list
rather than reclassifying: the dry run is the fork you get.

### `winnow context` — what is in the window, and how much of it is not in the file

`inspect` answers "what is this transcript carrying and would pruning it pay". `context` answers a
different question: **what is in the context window right now, and where did it come from.** The
total is not estimated — it is `input_tokens + cache_creation + cache_read` from the last priced
request, read out of `usage` — and the estimate is apportioned *inside* that total, so the shares
always sum to a number that is correct by construction and the error lives entirely in where the
tokens were attributed rather than in how many there are.

```sh
python -m winnow context <session-id>            # the readout, writes nothing
python -m winnow context <session-id> --json     # the same tree; this is the real interface
python -m winnow context <session-id> --window 200000   # …and then a "% full" figure
python -m winnow context <session-id> --depth 1  # provenance only; 2 adds the tool, 3 the artefact
python -m winnow context <session-id> --by-path  # one node per file, pooled across the tools
python -m winnow context <session-id> --audit    # the reconciliation, and the constant it will not apply
python -m winnow context <session-id> --explain prefix   # the arithmetic behind one node
```

**The five modes, and they compose.** The default is the provenance tree. `--by-path` re-keys its
`tool traffic` subtree artefact-first. `--audit` appends the full reconciliation beneath the tree and
changes no number in it. `--explain <node>` prints one node's arithmetic *instead of* the tree.
`--json` serialises whichever of those you asked for, and carries the audit document too when
`--audit` is given. `--depth` and `--window` are modifiers rather than modes and apply throughout.

The drill-down is the reason the command exists. Three levels: who put this here, then which tool
or attachment class, then **which artefact** — the file path with the number of times it landed in
the window, the Bash command head, the MCP tool, the memory file, one sub-agent's return. Sorted
biggest-first at every level, with no "17 more, each smaller" bin, so the terminal tree and `--json`
carry exactly the same nodes.

`--by-path` re-keys the `tool traffic` subtree artefact-first, so a file read twice and edited once
is one row marked `×3 (Read ×2, Edit)` rather than two rows in two subtrees. That is not cosmetic:
on session `f6ea2591` the share of `Read`/`Edit`/`Write` output coming from paths touched more than
once is **33.5%** pooled and **16.8%** keyed tool-first, over the same 211,557 characters. A result
with no path — Bash output is the largest such node in most sessions — keeps its command head as its
own key and is never binned as "other".

Two things it shows and never adds up. A sub-agent's return is sized at **what came back**, with the
sub-agent's own window printed beside it as a separate figure: adding them produces a number that is
not the size of any window that ever existed. A `<persisted-output>` node is sized at the ~2 KB
preview the model actually saw, with the size of the sidecar behind it named in the row.

Every figure carries one of four labels and a test walks `--json` to enforce it: `exact` is lifted
from something the CLI wrote down, `derived` is an exact number minus an estimate, `estimated` is
payload characters over 2.6, and `residual` is reserved for the single `unattributed` node.

**Two of the largest rows are in no transcript and neither is a guess.** The `prefix` — the system
prompt and the tool definitions, a median 25% of the window — is the first priced request of the
window minus what the transcript holds before it. `retained reasoning`, a median 14%, is
`output_tokens − est(text + tool_use)` summed per response, which is one exact number minus two small
estimates; the control is the responses that emitted no reasoning, where the same subtraction has to
come out near zero and does. Both are `derived` rather than `estimated`, and `--explain prefix` is
three numbers and a subtraction rather than a paragraph. Over an even 200-file sweep of
`~/.claude/projects` on 2026-09-03 (163 qualifying sessions) this leaves a **median `unattributed` of
0.6%**, against 43.9% for the same tree with only the visible material priced.

`--audit` reconciles the whole window row by row and then solves for the chars-per-token constant
that *would* zero this session's residual — and prints, beside it, that it was **not applied**. There
is no flag that applies it. A residual fitted to zero is zero by construction, which destroys the
only self-check the tool has and silently absorbs whatever category the classifier missed. The
residual is also allowed to be **negative** and is drawn with its sign: over-explaining the window is
what an unbiased estimator does, on 67 of those 163 sessions.

Three things it refuses to do. It prints **no "% of window full"** unless you supply the denominator
with `--window`: nothing in a transcript states the window size, and session `72acbacd` reports
512,133 tokens on a nominally 200,000-token model because it is a `[1m]` session. It prints **no
percentages at all**, and exits non-zero, when no assistant record carries a `usage` block — there is
no anchor, and a share of an estimated total is not a measurement. And it never sums a compacted
session from the top: the accumulator resets at the last `compact_boundary`, so `2551cd0c` reports
its real 116,030-token window rather than the 416,774 a walk from record zero produces, and states
the 444,326 tokens compaction has dropped as a separate exact figure above the tree.

**This is milestones M1 through M3.** M4 — `--watch` and `--by-turn` — is not built and is gated on
a usage diary rather than on effort. `proposals/ContextTreemap/05-recommendation.md` is the plan and
its non-goals bind: no "reclaimable space" figure, no cross-session view, no writes of any kind, and
no claim of parity with `/context`.

**`--explain` prints tool arguments verbatim, on `plan` and on `fork` alike, and a transcript
routinely contains credentials pasted into a Bash command** ([docs/SPEC.md](docs/SPEC.md) §10).
Treat that output as sensitive: do not paste it into an issue, a chat, or a CI log. Winnow writes no
log file of its own, so the only copy is the one you make. The flag also names the rule, the tool
and the byte count of each stripped result, and `--json --explain` carries the same fields
machine-readably along with the warning itself.

### `fork` — the writer

`--write` is the opt-in and there is no `--dry-run`: without `--write` the command reports exactly
what it would do and touches nothing. **The source transcript is opened read-only and is never
modified** — its bytes and its mtime are the same after a fork as before, which is what makes
`recover` worth having. The fork goes to a temporary file in the destination directory and is
renamed into place, so a crash leaves either nothing or a complete file.

The fork's session ID is **derived from the input, not drawn from a clock or a random source**: a
UUIDv5 over the source session ID, the source file's sha256, the resolved rule selection, and one
line per strip. The same session and the same flags therefore produce a byte-identical fork twice,
filename included ([docs/SPEC.md](docs/SPEC.md) §10) — and two forks that differ in content get
different names rather than silently overwriting one another.

Five things refuse, with exit code 3:

| Guard | What it means | `--force`? |
|---|---|---|
| **G5 pairing preserved** | The fork's `tool_use` ↔ `tool_result` pairing must be identical to the source's. Re-derived from the bytes about to be written and compared | **Never.** A hard failure, and nothing was written |
| `--min-cold-age S` (default 3600) | The last request finished less than `S` seconds ago, so the prefix may still be cached and the cut is not free ([docs/SPEC.md](docs/SPEC.md) §7) | Yes |
| `--max-break-even T` (default 60) | The cut needs more than `T` further turns before it has earned back the invalidation it causes — `T* = 19·(S/D) − 20` above the turns the session has left. `--max-break-even none` does not gate at all, for a caller that knows the invalidation is refunded. See [the break-even gate](#the-break-even-gate) | Yes |
| **G4 no net inflation** | The fork would remove fewer bytes than the pointers it adds, or would leave a larger file than it started with | Yes |
| `compacted` | The session has already compacted, so a resume starts from the summary and the pre-boundary bytes this fork prices are not in the prefix it would be cutting ([docs/DECISIONS.md](docs/DECISIONS.md) §Q4) | Yes |

### The break-even gate

A rule firing says a result *can* go. It says nothing about whether removing it is worth the cache
invalidation, and the two come apart badly: **a cut's cost is set by where its earliest strippable
result sits, not by how much it removes.** Four kilobytes removed from behind a 90 KB suffix needs
423 further turns to pay for itself; forty kilobytes removed from behind a 60 KB one needs 9.

`--max-break-even` is the operator saying how many further turns the session has in it. Anything
whose `T*` is above that is a cut that gets paid for and never earned back, and `fork` refuses it —
softly, so `--force` still writes it, and `plan` reports the same verdict without refusing on it.

Measured, on 396 local sessions truncated at the moment they first pass 150k of context, forked
through the real code path, and scored against the API requests each session actually went on to
make:

| | Cuts taken | Of those, actually paid | Net, at Opus base input |
|---|---:|---:|---:|
| Fork whenever a rule fires | 396 | 30% | **−$10.85** |
| `--max-break-even 60` | 114 | 64% | **+$56.06** |

The ungated column is the one worth staring at: **it is negative**. The worst single session it
takes costs 1.16M tokens — `T*` of 4,941 against 82 turns of session left. The gate refuses it. The
choice of 60 is flat between 40 and 100 (+$55.95, +$56.06, +$58.46) and the sign is what matters, not
the value.

Exit 2 is the different thing: no result met a rule, so there was nothing to do. Exit 1 is a usage
error.

`winnow recover <session> <pointer-id>` takes the **original** session — the one the pointer names —
and prints the exact bytes that pointer replaced, which hash to the sha256 the pointer records. It
reads the source and not the fork, so a recovery works even after the fork has been deleted.

## The intake filter

The pruner edits a conversation that is already cached, so it pays `1.9·S − 2·D` once. **The only way
not to pay that is to never let the bytes into the cached prefix.** `winnow filter` is a local
pass-through proxy that does exactly that: a tool result a rule would strip is sent in full on the one
request where the model acts on it, placed *after* the last `cache_control` breakpoint so the API
never writes it to cache, and dropped on the next request.

```sh
export WINNOW_FILTER=1                          # the toggle, and the whole of it
python -m winnow filter --ledger ~/.winnow/filter.jsonl
export ANTHROPIC_BASE_URL=http://127.0.0.1:8789 # what it prints
```

Per result of *D* tokens over *T* following turns, the baseline is a 2.0× cache write plus a 0.1×
read on every later turn; this pays 1.0× once and nothing after. **There is no break-even term** —
it is cheaper from the first request, at every `S/D`, which is the one thing the pruner cannot say.

| | Reaches | Netted | Share of the bill | Sessions where it pays |
| --- | ---: | ---: | ---: | ---: |
| Intake filter | 8.21% | $246.14 | **+3.76%** | 175 of 175 |
| Pruner, tier CB | 10.17% | $214.46 | +3.27% | 97 of 168 |

**That table was computed at `--min-bytes 2048` and the floor is now 256.** The 2,048 was inherited
from the pruner, whose comparison really is file bytes against a 163-byte pointer with a session's
`S` behind it. The filter's is different: it sends a candidate once in full and the pointer then
lives in the cached prefix, so the strip pays whenever `D > P·(2 + 0.1T)/(1 + 0.1T)` — bounded
between one and two pointer lengths at every `T`, never near two thousand. Re-measured over this
install's 869 transcripts, moving the floor to 256 takes the reach from **8.03% to 10.82%** of
message content and the net up **31%** at *T* = 224. The dollar column above has not been recomputed
and still describes the old floor. The arithmetic and the full table are in `src/winnow/filter.py`.

It reaches less than the pruner, because only the rules needing no hindsight can fire (C1, C3, B2 —
C2, B1 and A1 all need to see the conversation's future, and a policy that did would change the
prefix under the cache).
**The ratio is 1.1×.** What separates them is variance rather than size: the filter cannot be
negative. Running both is possible and nearly pointless — the filter takes the shared mass first,
leaving the pruner 2.2% against an unchanged `S`. Details, and the ledger that stops the two
double-counting, in [docs/COZEMPIC.md](docs/COZEMPIC.md) §3.5.

**That table is a simulation. `winnow savings` is the instrument.** The 8.21% and the $246.14 come
from replaying the three no-hindsight rules over 175 historical sessions — what the filter *would*
have done. Once it is running, the ledger records what it *did*, and the command prices that:

```sh
python -m winnow savings                        # or --json
```

It reads `~/.winnow/filter.jsonl`, joins each line to the Claude Code transcript on `request_id` to
recover which session it belongs to and how many API turns followed it, and applies §3.5's cost model
per result. The two numbers are not comparable and the command does not try: the simulation is a
corpus average, this is one install's ledger over however long it has been on.

**The one thing it must get right is that the filter is stateless.** It re-drops the same result on
every later request that still carries it, so a ledger of 1,283 removal events on this install holds
49 distinct results — summing `bytes_dropped` over lines would report **27× what was removed**. The
repeats are not removals; they *are* the `0.1·D·T` term, and are priced at 0.1×. De-duplication is on
`tool_use_id`, with a conservative `(tool, rule, bytes)` fallback for lines written before that field
existed. The readout splits the avoided write from the avoided reads rather than blending them, and
names the lines it could not join or could not price.

**The second thing is that one API request is one turn**, however many records it left on disk. Claude
Code writes a response as one record per content-block group — the text, then each `tool_use` — and
stamps every one of them with the same `requestId` and the same `message.usage`. Counting records
instead of requests inflates both *T* and the bill it is compared against, by 1.7 to 2.4× on this
install's transcripts. [docs/COZEMPIC.md](docs/COZEMPIC.md) §3.5.2 is the record.

**The figure is modelled, not billed**, and the command says so in its own output. The bytes were
never sent, so no invoice line corresponds to them; *D* and *T* are measured and the prices are
published, but the counterfactual is §3.5's model rather than an observation.

**Turning it off, and the two ways are not equivalent.** Set the toggle blank and restart for the
full off. On a *running* install, what can be turned off is the rewriting and not the proxy —
`touch ~/.winnow/filter-off` and the next request is relayed untouched; remove the file to resume.
Killing the process is not the off switch: `ANTHROPIC_BASE_URL` is fixed in a client's environment
when it starts, so a listener that goes away takes every request with it.

**It is in your credential path.** It relays your auth headers upstream, holds none of its own, logs
none — but an operator running it has put a process of their own in front of their own key. It
refuses to start without `WINNOW_FILTER=1` for that reason, and forwards the original bytes unchanged
on any failure to parse or rewrite: it must not be the thing that breaks a run.

## Orchestrator-safe mode

The vendored tool assumes an interactive user: it can defer a prune until you quit, ask you to run
`init`, and start a daemon that will `SIGKILL` a session it judges too large. Under an unattended
harness there is nobody to defer to and the session the daemon would kill is the one the tool is
running inside. `src/winnow/` is the mode that makes that combination survivable, and it is one
switch:

```sh
export WINNOW_ORCHESTRATOR=1
python -m winnow safe check                       # what would be refused, and why
python -m winnow safe plugin-dir --out ./out      # a --plugin-dir with SessionStart removed
python -m winnow safe run -- list                 # a vendored command, through the gate
```

Six things it guarantees, each argued and evidenced in
[docs/USAGEFOUNDRY.md](docs/USAGEFOUNDRY.md) §8:

- **It never terminates the session it runs inside.** The guard daemon cannot be started and `guard-watchdog --fix`, which signals, is refused. Not deferred: the harness spawns headless, so there is no interactive quit to defer to.
- **It never resumes a session.** `--resume` and session identity belong to the harness, so `reload`, which spawns a `claude --resume` watcher, is refused.
- **No auto-update, no PyPI check, no version drift.** Not switched off — removed. There is no updater module, no `self-update` subcommand and no upgrade step in the SessionStart hook, so no code path installs a package.
- **No writes to `~/.claude`.** That directory is a bind mount shared with the host. No global hook installation, no `settings.json` the mode does not own; loading happens through `--plugin-dir`, and the checkpoint the vendored tool would write inside the mount goes to winnow's own data directory instead.
- **It does not compete with the harness's context and cost controls.** The harness owns `--autocompact` and the per-cycle budget, so a mutating prune is refused while a Claude process is live and belongs between cycles.
- **Nothing is written into the model's memory.** `digest inject` writes to `~/.claude/projects/*/memory/`; it is refused, and the plugin directory drops the skills and the MCP server.

Nothing in `src/winnow/legacy/` was modified to do any of it. That tree is winnow's own code now
([docs/DECISIONS.md](docs/DECISIONS.md) §0) and the rename has since rewritten every name in it, but
every closure above is still held from outside it — which is the more honest test: a wrapper that has
to patch the thing it wraps has not shown the thing is safe to run.

**What it has not shown.** The mode has never run inside a real orchestrated cycle — everything was
exercised by hand in a container. No network call was proved absent, only switched off. The guard was
never enabled, deliberately.
[docs/USAGEFOUNDRY.md](docs/USAGEFOUNDRY.md) §8.9 lists each gap with the command that would close it.

## The inherited tool

`src/winnow/legacy/` is [Cozempic](https://github.com/Ruya-AI/cozempic) 1.8.39 by Ruya AI, forked
into this repository and renamed. It is real, working software: 20 pruning strategies in three tiers (18 inherited, two added here),
a nine-invariant validator that refuses any prune leaving a `tool_use` without its result, a floor
pass that re-adds the last 10 turns, a guard daemon, five hooks and a doctor with 15 checks. Its test
suite passes here (see below).

It arrived as **one arm of a measurement**, and [docs/DECISIONS.md](docs/DECISIONS.md) §0 argues that
choice against four alternatives — then reverses the read-only half of it. Two consequences worth
stating on the front page:

**It is winnow's code, and changes to it belong here.** §0 was reversed on 2026-08-23, on the
operator's instruction: winnow is a fork of the tool rather than a measurement of a read-only copy of
it. What that costs — custody of a 4,300-line daemon that can `SIGKILL` a live session, no clean diff
against upstream, nothing to send back — §0.1 sets out cost by cost, and it keeps the read-only
decision beside the reversal because none of its reasoning was refuted.
[docs/FORK.md](docs/FORK.md) is the map the rename executed against.

**It is not installed, and that is deliberate.** Installing it starts a daemon that can `SIGKILL` a
live editor, writes hooks into `~/.claude/settings.json`, and, in its default tier, strips the
`usage` fields that any cost measurement is computed from. A session Cozempic has pruned cannot be
used to evaluate whether Cozempic's pruning paid.
[docs/USAGEFOUNDRY.md](docs/USAGEFOUNDRY.md) §4 lists what has to be off first, including the two
features that had no off switch. Both now have one, out of tree:
[orchestrator-safe mode](#orchestrator-safe-mode) refuses the argv that starts the daemon and removes
the `usage`-stripping strategy from the prescriptions in process. That makes the tool runnable under a
harness. It does not make it installed, and `~/.claude/settings.json` is still never touched.

**This repository makes none of Cozempic's claims.** Its README advertises "85-95% savings" on one
strategy. That figure is *file bytes removed*, which is not tokens and is not money, and it is stated
without the cache write it costs. Working out what it would have to be measured against is
[docs/COZEMPIC.md](docs/COZEMPIC.md) §3.1; the honest summary there is that the measurement can
falsify a one-armed claim but cannot prove one tool superior to another without the quality arm that
nobody has run.

## Running the tests

Two suites: the inherited one, and winnow's own tests for the mode.

> [!WARNING]
> **The inherited suite writes into your home directory.** Running it added seven hooks to
> `~/.claude/settings.json`, wrote `~/.winnow_global_initialized`, and left fixture content in
> `~/.winnow/behavioral-digest.md`. Those paths were `~/.cozempic*` when this was observed and are
> the renamed ones now ([docs/FORK.md](docs/FORK.md) §6.1); the writes are the same writes. It
> leaves a `settings.<timestamp>.bak` beside the file it
> edited, which is how it was caught. `WINNOW_ORCHESTRATOR=1 python -m winnow safe check` before and
> after will tell you. Evidence and the exact diff: [docs/USAGEFOUNDRY.md](docs/USAGEFOUNDRY.md) §7.

```sh
uv sync
uv run pytest
uv run ruff check .
```

`uv sync` installs pytest and ruff, which it did not until recently: they were an *optional* extra
and a nothing respectively, so `uv sync` on a bare checkout actively removed pytest and the other two
commands could only fail. Both are now a dependency group, which `uv sync` installs without being
asked. The venv-and-pip recipe still works if you prefer it:

```sh
python3 -m venv .venv && .venv/bin/pip install -q pytest
.venv/bin/python -m pytest -q -p no:cacheprovider
```

Measured on this tree, 2026-08-25: **2,344 passed, 8 failed, 25 skipped, 283 subtests passed**, in
about 50 seconds. The failure count moves between 8 and 9 run to run, for the reason in the first row
below. (2026-08-23, after the rename and before milestone 2: 1978 passed, 1 failed, 17 skipped.)

**Every failure is pre-existing.** Running the same four files on `18d3123`, the commit milestone 2
branched from, gives nine failures and the same nine test names — the only difference is which member
of the `TestG4_PidfileWriteIsAtomic` pair happens to be the one that fails. None of the four files,
and none of `src/winnow/legacy/`, is touched by this branch. Every one of them is in the inherited
suite, reading process state this container does not provide the way the tests assume:

| Where | Why it fails here |
|---|---|
| `test_guard_hardening.py::TestG4_PidfileWriteIsAtomic` | Documented before the rename, and the one that moves the count. **Which of that class's two tests fails alternates between runs on an unchanged tree, and some runs neither does**; the same race reproduced outside pytest behaves correctly, and the guard's pidfile path is hardcoded to `/tmp` where it cannot be redirected |
| `test_guard_pid_recycling.py` (5) | Reads a process's start time out of `/proc`, which returns nothing usable here |
| `test_guard_reload_watcher_poll.py` (1) | Asserts a `pgrep` pattern matches no unrelated process. In a container running several agents at once it matches theirs |
| `test_digest.py::TestPurgePersistsToDisk` | Intermittent; present and absent across runs of the same tree |

The honest pass criterion is: at most one of the `TestG4_PidfileWriteIsAtomic` pair failing, and
nothing failing outside that table. Everything in `tests/test_inspect*.py`, `test_plan.py`,
`test_fork.py` and `test_validate_*.py` passes.

`uv run ruff check .` reports **883 findings**, and that is exactly the count before milestone 2 as
well. 869 are in `src/winnow/legacy/`, `plugin/` and the inherited test files — 295 unsorted imports,
100 blind excepts, 88 unused imports and a long tail. The other 14 are 11 in
`src/winnow/orchestrator_safe.py` and 3 in its tests, and predate this work too. **Everything
milestone 1 and 2 wrote is clean** — `rules.py`, `inspect.py`, `report.py`, `plan.py`, `fork.py`,
`cli.py`, `filter.py`, `proxy.py`, `savings.py`, `src/winnow/validate/`, and every test file that
goes with them — and nothing has been silenced with a `noqa` to make that true. The inherited
findings are a [docs/FORK.md](docs/FORK.md) phase-1 item and are not fixed piecemeal: an 869-finding
reformat of code nobody has read is a change with no reviewer.

winnow's own tests are `unittest.TestCase` classes rather than pytest functions, against the usual
preference and for one reason: they have to run where the mode runs. The harness container has no
`pip`, no `venv` and no pytest, so

```sh
PYTHONPATH=src python3 -m unittest tests.test_orchestrator_safe
```

is the whole recipe, stdlib only, no network. pytest collects the same file unchanged.

Some sandboxes ship `python3` without `pip` or `venv`, in which case the venv recipe fails at line
one; [docs/USAGEFOUNDRY.md](docs/USAGEFOUNDRY.md) §7 has a bootstrap for the full suite that needs
neither, and the one-line fix to the image that makes it unnecessary.

## What it is not

- **Not a wrapper around `claude`.** winnow will print the `claude --resume <new-id>` line; the operator runs it. Staying out of the spawn path means it cannot break a run and has no opinion about flags, budgets or permissions.
- **Not a daemon, and it never touches a live session.** The vendor's own hooks reference says the transcript "is written asynchronously and may lag the in-memory conversation": editing the file mid-session is not merely unsafe, it does not change what gets sent.
- **Not destructive.** Copy-on-write only. The original transcript is opened read-only and is both the archive and the recovery source; winnow adds files and never removes them.
- **No model call, no network, no MCP server.** Not a style preference: a summariser would put the thing being measured inside the instrument, and one added tool definition sits at the top of the invalidation cascade and was priced at $8.14 to $8.26 a week against $0.14 of benefit per use.
- **Not a rebuild of what it inherited.** The pruning tool now in `src/winnow/legacy/` and the tool this specification describes are for two shapes of session, and [docs/COZEMPIC.md](docs/COZEMPIC.md) §2.1 says which shape each one is right for. The fork renamed the first; it did not merge them.

Full list with reasons: [docs/SPEC.md](docs/SPEC.md) §3.

## Status

| | |
|---|---|
| Specification, decisions, milestone plan and kill criteria | **written** |
| Content-composition measurement, 563 transcripts | **done**, in earlier analysis; not reproducible from this checkout |
| Orchestrator-safe mode | **built and tested**; never run inside a real orchestrated cycle |
| Milestone 1, `winnow inspect` and the cache readout | **built, and it answered.** Tier CB reproduces at 10.2% pooled against SPEC §6's 22.6% — **12.4 points under**, of which 8.7 are one rule whose recorded number used a looser definition than the same document specifies ([docs/COZEMPIC.md](docs/COZEMPIC.md) §3.4). Above the 10% kill line, and not by much |
| Milestone 2, the rules, the guards, `winnow fork` and `winnow recover` | **built; every acceptance criterion a test suite can settle is met and checked.** G5 with `--force` unable to reach it, the cold-age refusal at exit 3, G4, byte-identical determinism including the filename, the original's bytes and mtime unchanged, the fork → recover round trip digest-checked on every pointer. Q4 decided ([docs/DECISIONS.md](docs/DECISIONS.md) §Q4) and `--explain` documented with its secrets warning |
| — the 100-fork resume test | **not validated.** Harness committed, `--dry-run` tested. Needs production transcripts and real model calls |
| — the 200-sample blind label, ≥90% once-only | **not validated.** Sampler, sheet, scorer and the scoring rule committed; **no result has been labelled**. Needs production transcripts and a person |
| — the week of accumulated disk cost | **not measured.** Script committed; the series has no observations. Needs a week |
| Per-rule precision defaults (`rules.DISABLED_BY_DEFAULT`) | **mechanism built, set empty** — and it stays empty until the label above fills it |
| Milestone 3, `winnow bench` and the quality arm | **not started** |
| Any claim that pruning a Claude Code session saves money | **unmade, by anyone** |

The three `not validated` rows are the honest state of milestone 2: the code exists and the criteria
that could still kill it are the ones nobody has run. Each is one command, and they are in
[docs/MILESTONE-2-VALIDATION.md](docs/MILESTONE-2-VALIDATION.md) with the corpus each needs, the bar
each has to clear, and what to do when one is missed. **No row above is marked met on the strength of
code existing.**

The last row is the project. The kill criteria in [docs/MILESTONES.md](docs/MILESTONES.md) are what
those three rows are measured against — aggregate rule precision under 80% stops milestone 2
outright, one unresumable fork stops it unless a same-day G5 change fixes it, and loosening
`--min-cold-age` to get a population is itself a kill condition. Stopping on any of them is the
intended outcome rather than a failure of it.

## Licence and attribution

[`LICENSE`](LICENSE) is **MIT**, and it carries two copyright lines: Ruya AI's, which arrived with
the inherited tree, and winnow's. One permission notice covers both and the whole repository:
[docs/DECISIONS.md](docs/DECISIONS.md) §0.6 settled on MIT throughout and no second licence for
winnow's own additions, rather than restating upstream's contribution under terms its authors did not
pick. [`NOTICE`](NOTICE) records what was derived from what, and
[`CONTRIBUTORS.md`](CONTRIBUTORS.md) credits the people who wrote the inherited code: that
attribution was never conditional on the code staying unmodified, which makes it more load-bearing
after the fork rather than less.
