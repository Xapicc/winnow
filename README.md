# winnow

A long Claude Code session is mostly tool output: across 563 transcripts, 175.6 MB of message
content, `tool_result` and `tool_use` inputs are **91.6%** of the bytes and human plus assistant text
is 8.4% ([docs/SPEC.md](docs/SPEC.md) §1). Several tools will strip that for you. **None of them can
tell you whether stripping it saved you anything**, because the conversation sits in the cached
prefix at 0.1× and every edit to it forces a full-price rewrite of everything after the cut.

winnow is an attempt to answer that question and, if the answer comes back the right way, a pruner
that only fires when the arithmetic says it pays.

> [!IMPORTANT]
> **The pruner does not exist yet, but the instrument does.** `winnow inspect` runs, and milestone
> 1's number has been produced: **tier CB strips 10.2% of message content pooled, 8.8% at the median**
> — against the 22.6% / 21.6% [docs/SPEC.md](docs/SPEC.md) §6 recorded and the ±3 points §9 asked it
> to reproduce within. It misses by 12.4, and 8.7 of those are one rule whose measured number was
> taken with a looser definition than the same document specifies
> ([docs/COZEMPIC.md](docs/COZEMPIC.md) §3.4). Netted against the cache — `0.1·D` earned on each turn
> that followed the cut, `1.9·S − 2·D` paid once — a tier-CB cut **pays off in 58% of sessions and is
> worth +3.27% of the bill**, on an optimistic bound, against the 15% SPEC §9 set as the target. There
> is still no `winnow fork` and no `winnow bench`. What there is instead is
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
| [docs/COZEMPIC.md](docs/COZEMPIC.md) | The vendored tool against the spec, decision by decision: six questions its code already answers, eight places the two disagree with a verdict and a reason on each, and what is still open |
| [docs/USAGEFOUNDRY.md](docs/USAGEFOUNDRY.md) | Eleven collisions between the vendored tool and the orchestrator that would run it, with evidence on both sides; §8 is orchestrator-safe mode as built, including what it does not yet prove |
| [docs/behavioral-digest-design.md](docs/behavioral-digest-design.md) | Cozempic's own design note, arrived with the merge |
| `src/winnow/filter.py`, `proxy.py` | `winnow filter` — the intake filter and the local proxy that carries it. Stdlib only, about 450 lines with 39 tests |
| `src/winnow/savings.py` | `winnow savings` — prices the filter's own ledger against the transcripts, de-duped on `tool_use_id` so a stateless filter's repeats are not counted as removals. Stdlib only, about 575 lines with 34 tests |
| `src/winnow/rules.py` | SPEC §4 itself: the six rules, the guards, the pointer and its ID scheme. Imported by `inspect`, by `plan` and by `fork` — one engine, so the three cannot disagree about what B1 means |
| `src/winnow/inspect.py`, `report.py` | `winnow inspect` — the reading, the byte accounting, the cache readout and `T*`. About 600 lines with 54 tests. Its `--json` output is pinned byte-for-byte in `tests/fixtures/inspect_golden.json`, because milestone 1's deliverable is a number and a number should not move by accident |
| `src/winnow/plan.py` | `winnow plan` — the dry run: which results a fork would replace, the pointer that would replace each, what the pointers cost, the net, and `T*` for the cut. Guard G4 is decided here rather than at write time, so `plan` and `fork` agree. About 450 lines with 53 tests |
| `src/winnow/fork.py` | `winnow fork` and `winnow recover` — the writer and the round trip. Consumes `plan`'s list rather than reclassifying, so the dry run is the fork you get. About 700 lines with 66 tests |
| `src/winnow/cli.py`, `orchestrator_safe.py` | The `safe`, `inspect`, `plan`, `fork` and `recover` groups, and orchestrator-safe mode, about 1,450 lines with its tests |
| `src/winnow/legacy/`, `plugin/`, `tests/` | The tree inherited from Cozempic 1.8.39, about 21,700 lines. Renamed into winnow by [docs/FORK.md](docs/FORK.md) phase 1; still not installed and not started |
| `packaging/README.md` | The record of the six package channels, the npm shim and the PyPI release workflow that phase 2 deleted. **Winnow publishes to no channel**; installing means a checkout |
| [web/README.md](web/README.md) | The site: four static routes over what this document says, checked against its own contract in [web/docs/design-language.md](web/docs/design-language.md). Not deployed anywhere yet, and it imports nothing from this tree |

**No `winnow bench`.** Milestone 2 — `plan`, `fork` and `recover` — is here; milestone 3 is not,
so nothing in this tree has yet run a model against a forked session. Two of milestone 2's own
acceptance criteria are also outstanding, and both need real production transcripts rather than
code: **the 100-fork resume test** (fork 100 real sessions, `claude --resume` each, 0 failures) and
**the 200-sample blind label** that puts a number on rule precision. Nothing in the test suite
reads `~/.claude/projects/` or shells out to `claude`, deliberately — those two validations are
run separately and reported separately. `inspect` is milestone 1. Its
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

`inspect` reports the ceiling of the mechanism — every rule, no pointer overhead. `plan` reports one
operator's actual selection with the pointers priced in, so its `T*` is the longer and the honest of
the two. `fork` prints the same arithmetic under its own heading, because it consumes `plan`'s list
rather than reclassifying: the dry run is the fork you get.

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

Four things refuse, with exit code 3:

| Guard | What it means | `--force`? |
|---|---|---|
| **G5 pairing preserved** | The fork's `tool_use` ↔ `tool_result` pairing must be identical to the source's. Re-derived from the bytes about to be written and compared | **Never.** A hard failure, and nothing was written |
| `--min-cold-age S` (default 3600) | The last request finished less than `S` seconds ago, so the prefix may still be cached and the cut is not free ([docs/SPEC.md](docs/SPEC.md) §7) | Yes |
| **G4 no net inflation** | The fork would remove fewer bytes than the pointers it adds, or would leave a larger file than it started with | Yes |
| `compacted` | The session has already compacted, so a resume starts from the summary and the pre-boundary bytes this fork prices are not in the prefix it would be cutting ([docs/DECISIONS.md](docs/DECISIONS.md) §Q4) | Yes |

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

It reaches less, because only the rules needing no hindsight can fire (C1, C3, B2 — C2, B1 and A1 all
need to see the conversation's future, and a policy that did would change the prefix under the cache).
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
python3 -m venv .venv && .venv/bin/pip install -q pytest
.venv/bin/python -m pytest -q -p no:cacheprovider
```

Measured on this tree, 2026-08-23, after the rename: **1978 passed, 1 failed, 17 skipped, 283
subtests passed**, in about 40 seconds. (Before the rename, and before the tests it added, the same
command gave 1960 passed, 1 failed, 17 skipped.) The
failure is in `tests/test_guard_hardening.py::TestG4_PidfileWriteIsAtomic`, it is pre-existing on the
merge commit, and it is not attributable to the code with confidence: **which of that class's two
tests fails alternates between runs on an unchanged tree**, the same race reproduced outside pytest
behaves correctly, and the guard's pidfile path is hardcoded to `/tmp` where it cannot be redirected.
The honest pass criterion is at most one of that pair failing.

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
| Milestone 1, `winnow inspect` and the cache readout | **built**, and it produced its number — 12.4 points under SPEC §6 at tier CB ([docs/COZEMPIC.md](docs/COZEMPIC.md) §3.4) |
| Milestone 2, the rules, the guards and `winnow fork` | **`winnow plan` built**: the rule engine, the pointer, and guard G4 decided at plan time. No writer, no `winnow recover` |
| Milestone 3, `winnow bench` and the quality arm | **not started** |
| Any claim that pruning a Claude Code session saves money | **unmade, by anyone** |

The last row is the project. If the first milestone comes back saying the cache is already warm at a
typical resume, or that the strippable share at tier CB does not reproduce, the kill criteria in
[docs/MILESTONES.md](docs/MILESTONES.md) say to stop, and stopping then is the intended outcome
rather than a failure of it.

## Licence and attribution

[`LICENSE`](LICENSE) is **MIT**, and it carries two copyright lines: Ruya AI's, which arrived with
the inherited tree, and winnow's. One permission notice covers both and the whole repository:
[docs/DECISIONS.md](docs/DECISIONS.md) §0.6 settled on MIT throughout and no second licence for
winnow's own additions, rather than restating upstream's contribution under terms its authors did not
pick. [`NOTICE`](NOTICE) records what was derived from what, and
[`CONTRIBUTORS.md`](CONTRIBUTORS.md) credits the people who wrote the inherited code: that
attribution was never conditional on the code staying unmodified, which makes it more load-bearing
after the fork rather than less.
