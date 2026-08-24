# winnow

A long Claude Code session is mostly tool output: across 563 transcripts, 175.6 MB of message
content, `tool_result` and `tool_use` inputs are **91.6%** of the bytes and human plus assistant text
is 8.4% ([docs/SPEC.md](docs/SPEC.md) §1). Several tools will strip that for you. **None of them can
tell you whether stripping it saved you anything**, because the conversation sits in the cached
prefix at 0.1× and every edit to it forces a full-price rewrite of everything after the cut.

winnow is an attempt to answer that question and, if the answer comes back the right way, a pruner
that only fires when the arithmetic says it pays.

> [!IMPORTANT]
> **The pruner does not exist yet.** There is no `winnow inspect`, no cache readout, no measurement.
> The deliverable of the first milestone is a number, not a binary, and the number has not been
> produced. What does run is one thing, and it is not the pruner: `src/winnow/` is
> [orchestrator-safe mode](#orchestrator-safe-mode), the harness around the vendored tool that makes
> running it inside an unattended session survivable.
> [What is here today](#what-is-here-today) is the inventory, and it is still short.

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
| `src/winnow/` | `cli.py` and orchestrator-safe mode, about 1,200 lines with its tests |
| `src/winnow/legacy/`, `plugin/`, `tests/` | The tree inherited from Cozempic 1.8.39, about 21,700 lines. Renamed into winnow by [docs/FORK.md](docs/FORK.md) phase 1; still not installed and not started |
| `packaging/README.md` | The record of the six package channels, the npm shim and the PyPI release workflow that phase 2 deleted. **Winnow publishes to no channel**; installing means a checkout |

**No `winnow inspect`, no cache readout, no `winnow bench`.** The numbers the documents cite as
measured were produced by analysis scripts in earlier work and are recorded with their sample sizes;
nothing in this checkout reproduces them yet.

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
| Milestone 1, `winnow inspect` and the cache readout | **not started** |
| Milestone 2, the rules, the guards and `winnow fork` | **not started** |
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
