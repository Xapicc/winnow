# Milestone 2 — results

What happened when [MILESTONE-2-VALIDATION.md](MILESTONE-2-VALIDATION.md) was actually run.
One section per criterion, added as each is attempted. A criterion that was attempted and
could not be measured is recorded here too, because "we tried and were stopped" and "we have
not tried" are different states and only one of them tells you what to fix.

---

## 1. The resume test — 100 forks, 0 failures

**Attempted 2026-09-07. Outcome: not measured — the environment cannot run it.**
Not a pass, not a fail, and **not a shortfall**: the corpus has the population. The harness
could not write a fork and the spawned `claude` could not reach a model, so no fork was ever
put to the test.

### What stopped it

**Forks cannot be written.** `write_fork` writes the fork next to its source, inside the
corpus. In the sandbox this run had, `~/.claude/projects` is mounted read-only, and every
one of the 212 forkable sessions failed identically:

```
OSError: [Errno 30] Read-only file system:
  '/home/node/.claude/projects/-workspace2/696bb20e-…-5f707586ef.jsonl.winnow-tmp'
```

There is no writable substitute. `claude --resume <id>` resolves a session id inside
`~/.claude/projects/<encoded-cwd>/`, so a fork written anywhere else is unresumable by
construction — a copied corpus would not relocate the measurement, it would abolish it.

**The spawned `claude` cannot call a model.** This is the more dangerous of the two and the
reason the real run was not attempted anyway:

```
$ claude -p 'reply OK'
Not logged in · Please run /login          # exit 1
```

`~/.claude/.credentials.json` is masked to `/dev/null` (`crw-rw-rw- 1 nobody nogroup 1, 3`)
for sandboxed child processes, and the model proxy on `$ANTHROPIC_BASE_URL`
(`127.0.0.1:8789`) refuses connections from inside the sandbox — `curl` gets `000`, and
`claude` given a placeholder key gets `Connection refused`. Every resume attempt would
therefore exit non-zero, and `resume.py` records a non-zero exit as `fail`, which is to say
as **an unresumable fork**. Running the prescribed command in this environment would not
have failed to produce a number; it would have produced 100 false failures and, read
literally, a false milestone-2 kill condition. That is worse than not running it.

Neither blocker is fixable from inside the run: sandbox escape is disabled by policy, and
the settings files that define the sandbox are themselves write-denied.

### What the dry run did establish

The dry run is not wasted. Refusals are decided by `build_fork` *before* the write step, so
the guard census below is real measurement against real production transcripts — only the
model call was stubbed, and no fork survived to need one. Because the run never reached its
5-fork target it never stopped early: it walked the **entire** population, and
875 + 212 = 1,087 accounts for every session. This is a complete census, not a sample.

The readout, verbatim, from `resume-dry.json`:

```
resume test       0 passed, 0 failed of 0 forks (target 5)
population        1,087 source transcript(s), 107 excluded as winnow's own forks
refused           875 session(s) produced no fork
                  break-even: 527
                  cold-age: 5
                  compacted: 56
                  nothing-to-do: 287
harness errors    212 — the harness broke, not the fork

GUARDRAIL NOT MET.
  5 fork(s) short of the target. Do not reach for --min-cold-age: MILESTONES makes
  loosening the guard to get results a kill condition in its own right.
  212 session(s) the harness could not process at all; these are bugs in winnow or
  in this script.
```

*(followed by the 212 `ERROR … Read-only file system` lines, one per session, elided.)*

Read that last sentence with the environment in mind: the harness attributes an `error` to a
bug in winnow or in itself, and here all 212 are neither. The 212 are the number that
matters — a session only reaches `write_fork` after clearing every guard with a non-empty
strip list, so **each error is a session winnow would have forked**. The "5 short of target"
line is likewise an artefact of the dry run's `--forks 5`, not a statement about the corpus.

Corpus: `~/.claude/projects`, 2,195 `.jsonl` in total. The harness reads the 1,194 that sit
one level down, which are the resumable top-level sessions; the other 1,001 are subagent and
workflow transcripts nested *below* a session id, which `claude --resume` does not address
and which are correctly out of scope.

**The trap in [MILESTONE-2-VALIDATION.md](MILESTONE-2-VALIDATION.md) §1 did not spring.**
`cold-age` refused **5 of 1,087** — 0.5%, not "nearly every real resume". The binding
refusals are `break-even` (527) and `nothing-to-do` (287), which are winnow declining to
fork sessions it would not usefully shrink: correct behaviour, not an obstacle. **212
sessions were forkable against a target of 100**, so the population is comfortably there and
`--min-cold-age` is not the reason this run produced no number. Nobody attempting this next
needs to go near that flag, and MILESTONES' third kill criterion — "the refusal path proves
unusable in practice" — is, on this corpus, not met.

### Side effects

**None.** No file was created anywhere under `$CORPUS`: all 212 writes failed at the
temporary file, and `find ~/.claude/projects -name '*.winnow-tmp'` returns 0. Nothing needs
deleting, and nothing was left behind for criterion 3 to count.

### Artefacts

Written to `~/.claude/winnow-validation/` — `~/winnow-validation` as specified is on the
read-only mount, and `$OUT` had to move somewhere writable outside the repository.

| File | What it holds |
| --- | --- |
| `resume-dry.jsonl` | the ledger: 1,087 attempts, one line each |
| `resume-dry.json` | the summary rendered above |

`uv run pytest`: 3,423–3,430 passed, 4–11 failed across runs, 25 skipped. The failures are
flaky and environmental — `tests/test_guard_pid_recycling.py`,
`tests/test_guard_hardening.py`, `tests/test_spawn_lock.py`, `tests/test_digest.py`,
`tests/test_orchestrator_safe.py`, `tests/test_guard_reload_watcher_poll.py` — process
identity, procfs and concurrency tests in the legacy guard subsystem, which want a writable
`/home/node` and a procfs this container does not give them. Nothing in `winnow.validate`,
`fork`, `plan` or `rules` fails: those three files' 204 tests all pass. `uv sync` needs
`UV_CACHE_DIR` redirected, `~/.cache` being read-only too.

### To actually run this

An environment that grants two things, both of which are the sandbox's to give:

1. **write access to `~/.claude/projects`**, so forks land where `--resume` looks for them;
2. **a `claude` child process that can authenticate and reach the API** — unmasked
   credentials, or a reachable `ANTHROPIC_BASE_URL`.

Verify the second before spending money on the first: `claude -p 'reply OK'` must exit 0
from the same shell that will run the harness. If it does not, the harness will report
failures that belong to the environment and attribute them to winnow.

The ledger makes the retry cheap, but **start it from a fresh ledger path**. The 1,087
attempts in `resume-dry.jsonl` are all `error` and `refused`, and `Ledger.attempted` skips
any source path already tried in *any* outcome — so re-running against that ledger would
skip the entire corpus and fork nothing.

### One artefact to read carefully

`resume-dry.json` says `"dry_run": false` despite being produced by `--dry-run`.
`summarise` derives that flag from `any(a.dry_run …)` over `pass`/`fail` attempts only
(`resume.py:320`), and this run had none of either. The flag is right about what it is
actually asserting — no dry stub was counted towards a guardrail — but a reader taking it as
"this was a real run" would be misled. Left as found rather than fixed under a validation
run; noted so the next person does not trust it.

---

## 2. The blind label — 200 results, ≥90% once-only

Not attempted.

## 3. The disk cost — measured over a week

Not attempted. No fork was written, so there is nothing yet to accumulate.
