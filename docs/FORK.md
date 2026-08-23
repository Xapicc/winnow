# The fork: what gets renamed to what

Written 2026-08-23. [DECISIONS.md](DECISIONS.md) §0 decides *that* winnow forks Cozempic and what
that costs. This document decides *what everything is called afterwards*, and is the map the next
four runs execute against.

It is written for an agent with no memory of the run that wrote it. Every decision states the name,
the reason, and a check the run can apply to itself. Where a claim about the code carries a
`file:line`, it was verified on 2026-08-23 against the tree at `d646ee4`; where it is a judgement,
it says so.

**Before you change anything, read [DECISIONS.md](DECISIONS.md) §0.2.** The fork reverses who owns
the code. It does not reverse D2, D7 or §2, and the single most likely way for these phases to go
wrong is a run that reads "the tree is ours" as "the guard, the in-place writer and the
token-threshold trigger are now winnow's design". They are not. They are inherited code winnow
intends to replace, which is why the package path below has the word `legacy` in it.

---

## 0. The phases at a glance

| Phase | What | Blocking output for the next phase |
| --- | --- | --- |
| 0 | This document, [DECISIONS.md](DECISIONS.md) §0, `LICENSE`, `NOTICE` | Done, 2026-08-23 |
| 1 | The rename. Tree moves, imports rewrite, one CLI, one distribution, licence applied, CI stood up | An importable `winnow` with no `cozempic` module in it |
| 2 | Delete what is not being maintained: telemetry, self-update and personal scripts. Declare the dependencies. Done, less the packaging channels, `npm/` and the release process, which the run's brief moved to their own run (§3, §9) | A tree with no network egress and no undeclared imports |
| 3 | Runtime surface: `COZEMPIC_*` to `WINNOW_*`, `/tmp` and `$HOME` state paths, the hook schema marker, `winnow migrate` | Nothing on disk named `cozempic` |
| 4 | The MCP server, self-hosted in its own container | An image that serves the tools without fetching anything |

Phases 1 to 4 are ordered by what breaks if you reorder them, not by size. Phase 2 before phase 3
because deleting a feature is cheaper than renaming its environment variable and then deleting it.
Phase 3 before phase 4 because the container's entrypoint reads the variables phase 3 renames.

---

## 1. Package path

**Decision: `src/cozempic/` moves to `src/winnow/legacy/`. One installable distribution, one import
root, one console script.**

`src/winnow/` already exists and holds four files, 1,312 lines: `__init__.py`, `__main__.py`,
`cli.py` (246 lines, `prog="winnow"`, the `safe` subcommand group) and `orchestrator_safe.py`
(1,053 lines). The inherited tree is 21,700 lines across roughly 25 modules plus `data/` and
`dashboard/`.

Three options were live. Merging the inherited modules flat into `src/winnow/` collides on `cli.py`,
`__init__.py` and `__main__.py`, and buries `orchestrator_safe.py` among twenty-five strangers.
Leaving the tree beside `src/winnow/` under some third top-level name keeps two packages, which is
the state the fork exists to end. A sub-package resolves both.

Why `legacy` and not a neutral word:

- It is accurate. [DECISIONS.md](DECISIONS.md) §0.2 records that the guard, the writer and the
  trigger are inherited as code winnow intends to replace. `legacy` is what that is.
- It is a tripwire in the import path. `from winnow.legacy.guard import ...` cannot be typed by
  accident, and the failure mode §0.2 exists to prevent is silent adoption. A neutral name would let
  it happen quietly.
- It is not a judgement on the code or its authors. The people who wrote it are credited in
  `CONTRIBUTORS.md` and `NOTICE`, and the fork keeps the eighteen strategies rather than rewriting
  them (§8). `legacy` describes winnow's plan for the tree, not its quality.

Two top-level packages under `src/` was never a design in any case. `pyproject.toml:38-39` is
`[tool.setuptools.packages.find] where = ["src"]`, which globs both `cozempic` and `winnow` into one
distribution already. The fork makes the layout match what the packaging has been doing since the
merge.

**Concretely.**

| From | To |
| --- | --- |
| `src/cozempic/` | `src/winnow/legacy/` |
| `src/cozempic/data/` | `src/winnow/legacy/data/` |
| `src/cozempic/dashboard/` | `src/winnow/legacy/dashboard/` |
| `import cozempic.X` / `from cozempic.X import` | `from winnow.legacy.X import` |
| `from . import X` inside the tree | unchanged, relative imports survive the move |
| `src/winnow/cli.py`, `orchestrator_safe.py`, `__init__.py`, `__main__.py` | unchanged in place |
| `src/cozempic.egg-info/` | delete, build artefact |

`pyproject.toml` (phase 1 edits it; phase 0 may not): `name = "winnow"`, `version = "0.1.0"`,
console script `winnow = "winnow.cli:main"` replacing `cozempic = "cozempic.cli:main"`, and the
package-data key `cozempic = ["data/*.md", "data/*.json"]` becomes
`"winnow.legacy" = ["data/*.md", "data/*.json"]`. `uv.lock` currently records
`name = "cozempic"` and regenerates.

**Check yourself.**

```sh
# must print nothing
grep -rn '^\s*\(from\|import\) cozempic' src/ tests/
test -d src/cozempic && echo FAIL: tree not moved
python3 -c "import winnow.legacy.cli"      # must import
python3 -c "import cozempic"               # must fail with ModuleNotFoundError
```

---

## 2. CLI layout

**Decision: one program, `winnow`. The twenty inherited subcommands keep their names at the top
level, except the two that collide, which move under a `team` group. `winnow safe ...` is untouched.**

`src/cozempic/cli.py:1764` is `prog="cozempic"` with twenty subcommands registered at
`:1777-1907`, no aliases. `src/winnow/cli.py:181` is `prog="winnow"` with one required group, `safe`,
and six actions under it.

The good news first, because it removes a worry a later run would otherwise have to resolve:
**winnow's own five spec'd commands do not collide with any of the twenty.** [SPEC.md](SPEC.md)
§8 names `inspect`, `plan`, `fork`, `recover` and `bench` (`SPEC.md:277-283`); none of those five is
among `list current diagnose treat strategy reload checkpoint post-compact guard init uninstall
doctor guard-watchdog formulary completions self-update remind nudge digest dashboard`. The nearest
overlaps are semantic, not lexical: `diagnose` against `inspect`, `treat` against `fork`. Resolving
those is a later run's problem and is out of scope here. One naming hazard worth stating so nobody
trips on it: `winnow fork` is the copy-on-write actuator from SPEC §8, and has nothing to do with
this document. The command is named for forking a session, not for forking a project.

### 2.1 The `checkpoint` / `post-compact` collision

Both names exist in both CLIs and do different things.

| Command | What it does | Where it writes |
| --- | --- | --- |
| inherited `checkpoint` (`cli.py:1829`, `cmd_checkpoint` at `:985`) | "Save team/agent state from the current session (no pruning)", via `checkpoint_team()` | `~/.claude/team-checkpoint.md` (`team.py:1344`) |
| inherited `post-compact` (`cli.py:1834`, `cmd_post_compact` at `:995`) | "Output team state after compaction (for PostCompact hook)" | reads the same file, prints to stdout |
| `winnow safe checkpoint` (`src/winnow/cli.py:225`) | the same operation, redirected | `WINNOW_DATA_DIR` (`orchestrator_safe.py:173`), never `~/.claude` |
| `winnow safe post-compact` (`src/winnow/cli.py:232`) | reads it back from there | |

**Decision: the inherited pair becomes `winnow team checkpoint` and `winnow team post-compact`.
`winnow safe checkpoint` and `winnow safe post-compact` keep their names and their behaviour.**

The inherited pair is a team-state operation implemented entirely in `team.py` (1,542 lines), and
`team` is simply its truthful namespace. It was only ever at the top level because Cozempic's parser
is flat. The `safe` pair is winnow's own code and is named for the mode it belongs to, not for what
it writes, so it does not move.

Rejected: namespacing the whole inherited tree under `winnow legacy ...`. It reads badly for the
commands that are the actual product (`winnow legacy list`), it puts the word `legacy` in the
operator's muscle memory for commands winnow intends to keep, and it would have to be undone later.
The `legacy` name belongs in the import path, where agents read it, not in the CLI, where operators
type it.

Also rejected: deleting the inherited pair and keeping only `winnow safe`. The `safe` pair only
functions with `WINNOW_ORCHESTRATOR=1` set: `is_enabled()` (`orchestrator_safe.py:72`) returns false
without it and every `safe` command then exits `EXIT_REFUSED = 3` through `_require_mode()`
(`src/winnow/cli.py:27`, `:55-66`). It cannot serve a plain interactive install.

Knock-on: the inherited `checkpoint` and `post-compact` are named in seven hook commands in
`src/cozempic/data/hooks.json` and its byte-identical twin `plugin/hooks/hooks.json` (kept in sync by
`tests/test_hooks_sync.py`). Both files change in the same commit. The argv gate's refusal list
(`orchestrator_safe.py`, and [USAGEFOUNDRY.md](USAGEFOUNDRY.md) §8.3) refuses `checkpoint` by name
and must refuse `team checkpoint` after the move, or invariant 4 silently opens.

### 2.2 One inherited bug not to preserve

`src/cozempic/cli.py:1915-1919` defines a module constant `_SUBCOMMANDS` listing nineteen names. The
parser registers twenty. The missing one is `nudge`, and `nudge` is the subcommand that writes into
`~/.claude/cozempic-metrics/` (`cli.py:1482`). `_SUBCOMMANDS` gates `_maybe_global_init` (`:2085`)
and `_maybe_auto_init`, so `nudge` is invisible to both. Winnow already documents and works around
this from outside (`orchestrator_safe.py:213-222`, with the comment "Mirrors the parser, not
`cli._SUBCOMMANDS`: the two disagree"). Phase 1 owns the tree and should fix the constant at source
rather than keep mirroring it. If it does, `orchestrator_safe.py`'s mirror and the test that compares
it against the live parser both simplify; if it does not, say so, because a silently-preserved
upstream bug in code you now own is indistinguishable from one you introduced.

**Check yourself.**

```sh
python3 -m winnow --help                    # one program, no "cozempic" in the output
python3 -m winnow team checkpoint --help
python3 -m winnow safe checkpoint --help    # both exist, different destinations
grep -rn 'prog="cozempic"' src/             # must print nothing
grep -c 'cozempic' src/winnow/legacy/data/hooks.json plugin/hooks/hooks.json   # both 0 after phase 3
```

---

## 3. Distribution

**Decision: winnow publishes to no package channel. All six inherited channels and `npm/` are
deleted in phase 2. The only supported install is from source, plus the container image from
phase 4.**

This is not a preference. Three findings, in descending order of how conclusive they are.

**The name is not available.** Checked against the live registries on 2026-08-23, not recalled:
PyPI `winnow` is taken (0.1.4, "a JSON-schema based library for publishing and manipulating families
of products", Paul Harter / opendesk). npm `winnow` is taken (2.6.0, "Apply sql-like filters to
GeoJSON"). Winnow cannot have its own name on either of the two channels that matter.

**The inherited channels are already broken as Cozempic's.** Every one pins a sha256 of an upstream
sdist that winnow will never produce, and they do not even agree with each other:

| Channel | File | Declares |
| --- | --- | --- |
| Homebrew | `packaging/homebrew/cozempic.rb:6-7` | 1.8.39, sha256 of the PyPI tarball |
| AUR | `packaging/aur/PKGBUILD:3` | `pkgver=1.8.19` |
| AUR | `packaging/aur/.SRCINFO:3,13` | `pkgver = 1.8.18`, source line pinning **1.7.1** |
| MacPorts | `packaging/macports/Portfile:7` | 1.8.34 |
| Nix | `packaging/nix/default.nix:9` | 1.8.34 |
| PyPI CI | `packaging/ci/publish.yml:54-67`, setup documented at `:9-17` | uploads as a PyPI trusted publisher registered to owner `Ruya-AI`, repository `cozempic` |

The last row is the decisive one: the release workflow uploads under a trusted-publisher registration
held by a GitHub repository winnow does not control, and takes the project name from
`pyproject.toml` (read at `:45`), which phase 1 changes to a name PyPI has already given to somebody
else. It cannot run here and could not be made to.

**`npm/` is a liability rather than a channel.** `npm/install.js` is a postinstall hook that
pip-installs `cozempic` through a five-way ladder (`:41-47`), pings
`https://api.counterapi.dev/v1/cozempic/installs/up` (`:65`), writes a global SessionStart hook into
`~/.claude/settings.json` (`:71-95`), and runs `cozempic init --quiet` (`:101-109`). That is a
package manager silently installing a different package manager's package, phoning home, and editing
the operator's global configuration. [USAGEFOUNDRY.md](USAGEFOUNDRY.md) §1.7 objects to the last of
those on its own.

**Also deleted in phase 2**, for the same reason and not separately argued: `scripts/`. All three
files are upstream's author's personal tooling, with hardcoded paths into
`~/.claude/projects/-Users-ruya-Documents-Advisor-Cozempic/memory` and a different person's GitHub
account. Done: `scripts/` is gone, and `stats-summary.sh` was reading the same Cloudflare counters
phase 2 stopped writing, so it was dead on arrival either way.

`packaging/` and `npm/` are **not** gone. Phase 2's brief moved the six channels, `npm/` and the
publish workflow to their own run, on the grounds that they are a distribution decision rather than a
dependency one. They still contain the only remaining outbound calls in the tree
(`npm/install.js` pip-installs `cozempic` and pings `api.counterapi.dev`; `packaging/ci/publish.yml`
uploads to PyPI under Ruya-AI's trusted-publisher registration), and none of it is reachable from
`winnow` — no import, no subprocess, no hook.

**If a later run reverses this**, it needs a distribution name that is free, and these were free on
2026-08-23: `winnow-cli`, `winnowctl`, `winnow-context`, `winnow-claude`, `nms-winnow`. (`winnowing`
is taken.) The import name can stay `winnow` regardless, since PyPI distribution names and Python
import names are independent, but note the hazard: a machine with both this project and Paul Harter's
`winnow` installed gets one `winnow` package and a broken one. Reversing this decision means
accepting that.

---

## 4. Version

**Decision: winnow versions itself, from `0.1.0`, semver, starting at the phase 1 commit. Upstream's
`1.8.39` is recorded as provenance and never as winnow's version.**

[USAGEFOUNDRY.md](USAGEFOUNDRY.md) §8.5 refused to invent a version for the generated plugin manifest,
on the grounds that "upstream's `1.8.39` names a release of a different program, so an invented number
would be the same false claim in another font". That reasoning is correct and is not overturned. What
changed is the premise: a fork with a container image to tag has to have a version, because an
untagged image is not operable, and "no version" stops being the honest answer once the thing has
releases.

Why `0.1.0` and not `1.8.40`:

- `1.8.40` claims continuity with a release history winnow did not produce and cannot support. It is
  the same false claim §8.5 refused, only worse, because it would also imply thirty-nine prior
  winnow releases.
- `0.x` is a true statement: no stability promise, and the CLI surface changes under phases 2 and 3.
- No reader can mistake `0.1.0` for a Cozempic release.

Five places carry `1.8.39` today and split three ways at phase 1:

| Location | Becomes |
| --- | --- |
| `pyproject.toml:7` | `0.1.0` |
| `src/cozempic/__init__.py:3` `__version__` | deleted; `src/winnow/__init__.py` gains `__version__ = "0.1.0"` |
| `src/cozempic/cli.py:1767` (a hardcoded literal in the `--version` action, not read from `__init__`) | read from `winnow.__version__`, not re-hardcoded |
| `plugin/.claude-plugin/plugin.json:3`, `npm/package.json:3` | deleted with `npm/` and rewritten with the plugin at phase 4 |
| `src/winnow/orchestrator_safe.py:90` `VENDORED_COZEMPIC_VERSION = "1.8.39"` | **stays**, renamed to `UPSTREAM_VERSION`. It is provenance, and `winnow-safe-manifest.json`'s `derived_from` block is the right home for it |

The generated plugin manifest gains a `version` key at phase 1, and the string in
`upstream_provenance()` (`orchestrator_safe.py:571-575`) that says winnow "has not versioned itself
and so declares no version" goes with it. [USAGEFOUNDRY.md](USAGEFOUNDRY.md) §8.5 carries the same
note.

Container image tags: `winnow:0.1.0` and `winnow:<git-sha>`, both pushed for every build, so a
running container can always be traced to a commit. No `latest`.

---

## 5. Environment variables

**Decision: the `COZEMPIC_*` prefix becomes `WINNOW_*`. Four of the variables are deleted with the
feature they switch off rather than renamed. The remaining twenty-three are honoured under their old
names for one release, with a warning on stderr, and never silently.**

First, a correction to the list this work was briefed from. **Two of the eleven names given are not
environment variables at all**, and a run that greps for them in `os.environ` will find nothing and
may conclude the grep is broken:

- `COZEMPIC_SUBCOMMANDS` is a Python `frozenset` in winnow's own code
  (`src/winnow/orchestrator_safe.py:217`, used at `:313`). It is the argv gate's mirror of the
  parser. It renames as an identifier, not as a variable.
- `COZEMPIC_VERSION` does not exist under that name either. The nearest thing is
  `VENDORED_COZEMPIC_VERSION` (`orchestrator_safe.py:90`), covered in §4 above.

Second, the real list is **twenty-seven**, not nine. The sixteen tuning variables the brief did not
name are in the table below, and a rename that misses them leaves half the surface behind.

### 5.1 Deleted, not renamed

An opt-out for a feature that no longer exists implies the feature might still be there. These four
go in phase 2, in the same commit as the code they switch off.

| Variable | Read at | Goes with |
| --- | --- | --- |
| `COZEMPIC_NO_TELEMETRY` | `helpers.py:236`, `updater.py:187`, `:278` | the three Cloudflare Worker counters (`helpers.py:240-261`) and the install ping |
| `COZEMPIC_NO_AUTO_UPDATE` | `updater.py:239` | both self-update paths |
| `COZEMPIC_PIN` | `updater.py:217` (also `:206`, `:214`, `:236`, `:245`) | ditto. Pinning is meaningless once nothing updates itself |
| `COZEMPIC_NO_RECEIPTS` | `receipts.py:34`, `:64` | the receipts writer, if phase 2 removes it. **Open: see §9 Q2** |

Knock-on, and it is load-bearing: `_SAFE_ENV_SPEC` (`orchestrator_safe.py:92-152`) forces nine
variables, four of which are these. The overlay shrinks in the same commit, and the tests that assert
on it shrink with it. A phase 2 that deletes the features without shrinking the overlay leaves winnow
setting variables nothing reads, which is the quiet kind of wrong.

**Done, phase 2, with one correction to the arithmetic above.** Three went, not four: §10 Q2's
default keeps receipts, so `WINNOW_NO_RECEIPTS` survives and the overlay shrank to **six**, not five.
Each was deleted in the same commit as its last reader, as planned.

**Removed, not accepted-and-ignored.** The alternative was to keep parsing the three names and do
nothing with them, so an operator's existing `WINNOW_NO_AUTO_UPDATE=1` would not become an error.
Rejected: a tool that accepts `WINNOW_NO_TELEMETRY` is a tool that has telemetry to switch off, and
the point of the phase is that it does not. Nothing errors on an unknown `WINNOW_*` variable, so
setting one that is gone is inert rather than fatal — an operator who has it set loses nothing but the
belief that it is doing something. The reachable consumers are this repository's own overlay and
[USAGEFOUNDRY.md](USAGEFOUNDRY.md) §4, both updated in the same commits.

### 5.2 Renamed

`COZEMPIC_X` becomes `WINNOW_X` with the rest of the name unchanged. Twenty-three of them.

| Old name | New name | Read at |
| --- | --- | --- |
| `COZEMPIC_NO_AUTO_INIT` | `WINNOW_NO_AUTO_INIT` | `cli.py:2269`; set at `:1938`; in all seven hook commands |
| `COZEMPIC_NO_GLOBAL_INIT` | `WINNOW_NO_GLOBAL_INIT` | `cli.py:2076`; set at `:1942` |
| `COZEMPIC_INTERACTIVE` | `WINNOW_INTERACTIVE` | `guard.py:1410`, default `"auto"` |
| `COZEMPIC_NUDGE_OFF` | `WINNOW_NUDGE_OFF` | `cli.py:1429`, `:1544` |
| `COZEMPIC_FORCE_RELOAD_PCT` | `WINNOW_FORCE_RELOAD_PCT` | `guard.py:1479`, default `"0.88"` |
| `COZEMPIC_CONTEXT_WINDOW` | `WINNOW_CONTEXT_WINDOW` | `tokens.py:91` |
| `COZEMPIC_SYSTEM_OVERHEAD_TOKENS` | `WINNOW_SYSTEM_OVERHEAD_TOKENS` | `tokens.py:52` |
| `COZEMPIC_CHARS_PER_TOKEN` | `WINNOW_CHARS_PER_TOKEN` | `tokens.py:142` |
| `COZEMPIC_DEBUG` | `WINNOW_DEBUG` | `digest.py:49`, `:53` |
| `COZEMPIC_NUDGE_PCTS` | `WINNOW_NUDGE_PCTS` | `cli.py:1467` |
| `COZEMPIC_MIN_PRUNE_RATIO` | `WINNOW_MIN_PRUNE_RATIO` | `guard.py:130` |
| `COZEMPIC_GUARD_HARD_EXIT_K` | `WINNOW_GUARD_HARD_EXIT_K` | `guard.py:90` only; `spawn_lock.py:115` names it in a docstring and does not read it |
| `COZEMPIC_PIDFILE_FRESH_SECONDS` | `WINNOW_PIDFILE_FRESH_SECONDS` | `spawn_lock.py:124` only; `guard.py:82` names it in a comment and does not read it |
| `COZEMPIC_SESSION_WAIT_SECONDS` | `WINNOW_SESSION_WAIT_SECONDS` | `guard.py:306` |
| `COZEMPIC_IDLE_BACKOFF_CYCLES` | `WINNOW_IDLE_BACKOFF_CYCLES` | `guard.py:1431` |
| `COZEMPIC_IDLE_RELOAD_CYCLES` | `WINNOW_IDLE_RELOAD_CYCLES` | `guard.py:1446` |
| `COZEMPIC_RELOAD_WARN_GRACE` | `WINNOW_RELOAD_WARN_GRACE` | `guard.py:1460` |
| `COZEMPIC_RELOAD_WINDOW_S` | `WINNOW_RELOAD_WINDOW_S` | `guard.py:2671` |
| `COZEMPIC_RELOAD_MAX` | `WINNOW_RELOAD_MAX` | `guard.py:2681` |
| `COZEMPIC_PROTECT_MATCH_SECONDS` | `WINNOW_PROTECT_MATCH_SECONDS` | `helpers.py:532` |
| `COZEMPIC_FLOOR_MAX_DROP_PCT` | `WINNOW_FLOOR_MAX_DROP_PCT` | `config.py:181` |
| `COZEMPIC_FLOOR_PRESERVE_LAST_K` | `WINNOW_FLOOR_PRESERVE_LAST_K` | `config.py:196` |
| `COZEMPIC_FLOOR_PRESERVE_FIRST` | `WINNOW_FLOOR_PRESERVE_FIRST` | `config.py:216` |

Already `WINNOW_*` and unchanged: `WINNOW_ORCHESTRATOR` (`orchestrator_safe.py:59`) and
`WINNOW_DATA_DIR` (`:173`).

### 5.3 The one-release shim

Old names are read, once, in one place, and never in the module that wants the value:

- A single resolver at the boundary. If `WINNOW_X` is set it wins. If only `COZEMPIC_X` is set, the
  value is used **and** one line goes to stderr: `winnow: COZEMPIC_X is deprecated, use WINNOW_X`.
  If both are set and disagree, that is an error and exits non-zero rather than picking one.
- No module reads `COZEMPIC_*` directly. One resolver, one deprecation table, one place to delete.
- The shim is removed at `0.2.0`. Put the removal version in the warning text so the operator does
  not have to look it up.

This is the only backwards-compatibility mechanism in the whole fork, and it exists because these
variables appear inside hook commands already written into somebody's `~/.claude/settings.json`,
where the fork cannot reach them. Everything else breaks cleanly. A silent fallback would violate the
project's own rule against defaults that mask a missing configuration; a loud one does not.

---

## 6. On-disk state

**Decision: every path renames. It is a hard break, the migration is a one-shot `winnow migrate`
plus one deliberate exception, and phase 3 must not run while a guard daemon is live.**

### 6.1 The map

`/tmp`, keyed by `SLUG`, the first 12 characters of the session id:

| Now | Becomes | Written by |
| --- | --- | --- |
| `/tmp/cozempic_guard_${SLUG}.pid` | `/tmp/winnow_guard_${SLUG}.pid` | `guard.py:3303` (`_pid_file_for_session`), `:3310` (a legacy cwd-hash variant, rename it too), `:3601` (daemon spawn), and the SessionStart hook. `spawn_lock.py:224` rebuilds the same name from `tempfile.gettempdir()` for diagnostics |
| `/tmp/cozempic_guard_${SLUG}.startup-lock` | `/tmp/winnow_guard_${SLUG}.startup-lock` | hook only |
| `/tmp/cozempic_hook_${SLUG}.lock` | `/tmp/winnow_hook_${SLUG}.lock` | hook only, `flock` fd 9 |
| `/tmp/cozempic_reload_${SLUG}.in-flight` | `/tmp/winnow_reload_${SLUG}.in-flight` | `guard.py:2467`, `reload_lock.py:375` |
| `/tmp/cozempic_reload_${SLUG}.status` | `/tmp/winnow_reload_${SLUG}.status` | `guard.py:2468`; read and deleted by the hook |
| `/tmp/cozempic_reload_armed_*` | `/tmp/winnow_reload_armed_*` | `guard.py:3151` |
| `/tmp/cozempic_breaker_${SLUG}.json` | `/tmp/winnow_breaker_${SLUG}.json` | `overflow.py:41` |
| `/tmp/cozempic_guard.log`, `/tmp/cozempic_guard_<pid>.log`, `/tmp/cozempic_reload.log` | `winnow_` equivalents | `guard.py:2487`, `:2582`, `:2589`, `:3596`, `:3600`, `cli.py:962` |

`$HOME`:

| Now | Becomes |
| --- | --- |
| `~/.cozempic/` (`config.json`, `receipts/`, `dashboard.html`) | `~/.winnow/` |
| `~/.cozempic_savings.json` | `~/.winnow_savings.json` |
| `~/.cozempic_global_initialized` | `~/.winnow_global_initialized` |
| `~/.cozempic_remind_counter` | `~/.winnow_remind_counter` |
| `~/.cozempic_update_check`, `~/.cozempic_installed` | deleted in phase 2 with the updater |
| `~/.claude/cozempic-sessions.json` | `~/.claude/winnow-sessions.json` (`session.py:506`) |
| `~/.claude/cozempic-metrics/nudge-state.json` | `~/.claude/winnow-metrics/nudge-state.json` (`cli.py:1482`) |
| `.cozempic-init.lock`, `.cozempic-settings-*.tmp` beside `settings.json` | `.winnow-` equivalents (`init.py:241`, `:198-200`) |

Not renamed, because they are not ours: `~/.claude/team-checkpoint.md` and `~/.claude/teams/` carry
no product name.

`guard.py:2636-2650` hardcodes `Path("/tmp")` with a comment that it must stay byte-identical to the
shell hook, which cannot call `tempfile.gettempdir()`. That constraint survives the rename and is why
every `/tmp` path above changes in the same commit as `hooks.json`, in both copies of it.

### 6.2 The hook schema marker

`# cozempic-hook-schema=v14` appears fourteen times, seven each in `src/cozempic/data/hooks.json` and
`plugin/hooks/hooks.json`. **Decision: `# winnow-hook-schema=v1`.** Not `v15`: the schema version
counts winnow's own hook shape, and phase 3 changes that shape.

Two string tests read it, and they behave differently under a rename:

- `init.py:114`, `_is_cozempic_command`: substring `"cozempic-hook-schema="`, any version. This is
  the **ownership** test, answering "is this hook ours, so may `init` replace it and may `uninstall`
  remove it".
- `init.py:126`, `_is_current_cozempic_command`: `HOOK_SCHEMA_MARKER in command`
  (`init.py:46-47`), containment of the whole versioned marker rather than of its prefix. This is
  the **currency** test. Note it is not an ordering comparison, so a newer marker also reads as
  stale: `...=v15` does not contain `...=v14`.

**The one deliberate exception to the clean break lives here.** The currency test moves to
`winnow-hook-schema=v1` outright. The ownership test must keep recognising `cozempic-hook-schema=`
**in addition to** `winnow-hook-schema=`. Without that, `winnow init` does not see an installed
Cozempic hook as ours, appends winnow's hooks beside it, and the operator gets both tools' SessionStart
hooks firing: two guard daemons, two auto-update attempts, two banner lines. And `winnow uninstall`
becomes unable to remove the thing `winnow init` installed under its old name. This shim exists to
*remove* the old hooks, not to keep them working, which is what makes it the right kind of shim.

### 6.3 Is the rename a hard break, and for whom

Yes, and the honest scoping matters. The population is one operator and this container's unattended
runs, not the 100,000 users the merged README used to claim. `README.md:130` already records that this
repository makes none of Cozempic's claims. Nobody installs winnow from a package channel (§3), so
there is no fleet mid-upgrade.

Within that population, three breaks, ordered by how much they can hurt:

1. **Two guard daemons on one session.** The SessionStart hook decides whether to spawn by testing
   `/tmp/cozempic_guard_${SLUG}.pid` and `kill -0` on its contents. Rename the path while a daemon is
   running under the old one and the new hook sees nothing and spawns a second. Two daemons, both
   eligible to `SIGTERM` then `SIGKILL` the same editor process (`guard.py:2377-2400`). This is the
   only break that can cost somebody work.
2. **Hook lock bypass.** `/tmp/cozempic_hook_${SLUG}.lock` is a `flock` file. An old and a new hook
   body hold locks on different names and therefore do not exclude each other.
3. **State loss, cosmetic.** Savings history, the global-init marker, the sessions sidecar and the
   nudge counter all reset. The tool recreates them. The global-init marker resetting means one extra
   `init` on the next invocation, which is noise, not damage.

### 6.4 The migration

- **`winnow migrate`, one shot, idempotent, no automatic invocation.** Moves `~/.cozempic/` to
  `~/.winnow/` and each `~/.cozempic_*` dotfile to its `~/.winnow_*` name; moves
  `~/.claude/cozempic-sessions.json` and `~/.claude/cozempic-metrics/`; rewrites any
  `cozempic-hook-schema=` hook in every `settings.json` it can find, via the existing ownership test.
  It refuses and exits non-zero if any destination already exists. It never touches `/tmp`.
- **`/tmp` is not migrated, it is fenced.** Phase 3 adds a startup check: if a live
  `/tmp/cozempic_guard_*.pid` exists for this session slug, refuse to start and print how to clear it.
  A stale pid file whose process is gone is removed and the guard proceeds. Copying a pid file to a
  new name would leave two names for one lock, which is worse than either.
- **Phase 3 does not run while a guard is live anywhere in this container.** Stated as a
  precondition on the phase, not as something the code defends against, because break 1 above is
  between two processes started under different rules and no single process can see both.
- Everything else breaks cleanly and loudly. There is no read-old-write-new layer.

---

## 7. The MCP server, self-hosted

Phase 4. The target is the operator's, from [DECISIONS.md](DECISIONS.md) §0.3: the server runs
winnow's own code, from an image winnow builds, fetching nothing at spawn.

Today, `plugin/.mcp.json` is `uv run --with fastmcp --with cozempic python
${CLAUDE_PLUGIN_ROOT}/servers/cozempic_mcp.py`. `--with cozempic` fetches from PyPI at spawn, so the
server runs a downloaded copy and not this tree at all ([USAGEFOUNDRY.md](USAGEFOUNDRY.md) §1.9).
`plugin/servers/cozempic_mcp.py` exposes five tools (`diagnose_current`, `estimate_tokens`,
`list_sessions`, `treat_session`, `list_strategies`). It also started a daemon thread at import that
called `ping_install_if_new()` and `maybe_auto_update(force=True, silent=True)`; phase 2 deleted that
thread along with the module it called, rather than leaving the file importing something that no
longer exists.

What phase 4 does:

- `plugin/servers/cozempic_mcp.py` becomes `plugin/servers/winnow_mcp.py` and `FastMCP("Cozempic")`
  becomes `FastMCP("winnow")`. The `_startup_maintenance` thread was to be **deleted, not disabled**;
  phase 2 did it early, because leaving a file importing a module that same phase deleted is a defect
  rather than a deferral.
- A `Dockerfile` at the repository root: the image contains the winnow package and `fastmcp`, and
  nothing resolves at runtime. Pinned base image by digest, non-root user, no network in the final
  stage.
- `.mcp.json` invokes the container. Transport defaults to **stdio over `docker run --rm -i`**,
  matching today's behaviour exactly, because HTTP means a listening port, an authentication story
  and a decision about who may reach it, and no document in this repository has a position on any of
  those. HTTP is Q3 in §9.
- The container needs to see the transcripts it diagnoses. `~/.claude` is a bind mount already
  ([USAGEFOUNDRY.md](USAGEFOUNDRY.md), preamble), so mount it **read-only** by default and require an
  explicit flag for the one tool that writes (`treat_session(execute=True)`). A pruner with write
  access to the operator's session directory by default is the same class of decision
  [USAGEFOUNDRY.md](USAGEFOUNDRY.md) §5 reserves to the operator.
- `fastmcp` becomes a declared dependency of the image, not of the package. It is not a runtime
  dependency of the CLI (`COZEMPIC.md` §1.1). Phase 2 declared it as the `mcp` extra in
  `pyproject.toml` as an interim, so the import is not undeclared while the image does not exist;
  phase 4 moves it.

---

## 8. Non-goals

Things a reader would reasonably expect to be in scope and which are deliberately not.

- **Reversing D2, D7 or §2.** Restated here because it is the most important line in the document.
  The fork changes custody, not design. [DECISIONS.md](DECISIONS.md) §0.2.
- **Enabling the guard by default, or enabling it to observe it.**
  [USAGEFOUNDRY.md](USAGEFOUNDRY.md) §6's third prohibition stands and the fork makes it more
  pressing, not less.
- **Rewriting the eighteen strategies.** [DECISIONS.md](DECISIONS.md) §1 records that the rules are
  the cheap part and the harness is the deliverable (`DECISIONS.md:265`). Until the harness exists a
  rewrite cannot be judged, so the fork carries the rules across unchanged.
- **Any upstream relationship.** No cherry-picks, no rebase, no patches sent, no tracking branch.
  Upstream's 1.8.39 is a fixed point in `NOTICE` and nothing more.
- **Preserving `cozempic`'s published behaviour or being a drop-in replacement for it.** Winnow does
  not hold the PyPI name and does not claim to be an upgrade path from it.
- **Building `winnow inspect`, `plan`, `fork`, `recover` or `bench`.** Those are
  [MILESTONES.md](MILESTONES.md)'s work and are untouched by these four phases. Not because they are
  unrelated: the fork spends the appetite MILESTONES budgeted for them, which
  [DECISIONS.md](DECISIONS.md) §0.5 records as an accepted cost rather than a solved problem.
- **Keeping a byte-stable Cozempic baseline in the working tree.** The fork removes it. The bench arm
  comes from `git show 210b026:src/cozempic` or `pip install cozempic==1.8.39`, and
  [DECISIONS.md](DECISIONS.md) §0.4 already warns that an arm reachable only by `git show` is an arm
  that quietly does not get run. Named here so it is a known cost rather than a discovery.
- **Rewriting the four inherited documents.** `docs/behavioral-digest-design.md`, `docs/qa-fleet.md`,
  `plugin/README.md` and `packaging/README.md` are upstream's prose. Phases 2 and 4 delete two of
  them along with their directories; the other two get a provenance header, not a rewrite.

---

## 9. Phases, with acceptance criteria

Each criterion is written so a later run can tick it without asking anybody what was meant.

### Phase 1: the rename

The whole tree moves and nothing changes behaviour. Large diff, no new logic.

- [ ] Given a clean checkout, when `grep -rn '^\s*\(from\|import\) cozempic' src/ tests/` runs, then
      it prints nothing and exits 1.
- [ ] Given a clean checkout, when `python3 -c "import cozempic"` runs, then it raises
      `ModuleNotFoundError`; and `python3 -c "import winnow.legacy.cli"` succeeds.
- [ ] Given the package installed, when `winnow --help` runs, then it prints `winnow` as the program
      name, lists the twenty inherited subcommands plus `safe`, and the string `cozempic` does not
      appear in the output.
- [ ] Given the package installed, when `winnow team checkpoint --help` and
      `winnow safe checkpoint --help` both run, then both succeed and their help text names different
      destinations.
- [ ] Given the test suite, when it runs, then it passes at no worse than the recorded baseline:
      1,960 passed, 1 failed, 17 skipped ([USAGEFOUNDRY.md](USAGEFOUNDRY.md) §7, its last run; the
      39-second figure earlier in that section is a different and earlier run). A new failure is a
      phase-1 defect; the pre-existing one may stay, named, in the commit message.
- [ ] **CI exists and runs the suite.** A checked-in script that runs it in this container without
      network, plus a workflow for a runner that has network. This is phase 1's exit condition and not
      a nice-to-have: a 21,700-line mechanical rename with nothing watching it is the exact shape of
      change that CI is for.
- [ ] `pyproject.toml` says `name = "winnow"`, `version = "0.1.0"`, console script
      `winnow = "winnow.cli:main"`.
- [ ] `CONTRIBUTORS.md`'s header pointer changes `src/cozempic/` to `src/winnow/legacy/` and
      **nothing else in that file is touched**. Given the file after the commit, when it is diffed
      against the previous version, then exactly one path string differs.
- [ ] `LICENSE` still contains the substrings `2026 Ruya AI` and `MIT License`, so
      `tests/test_orchestrator_safe.py:503` still passes; `NOTICE` exists at the root; both are
      referenced from `README.md`.
- [ ] `orchestrator_safe.py`'s `upstream_provenance()` notice string no longer says "vendored prior
      art" or "retained verbatim" or "has not versioned itself", and the generated manifest carries a
      `version` key ([USAGEFOUNDRY.md](USAGEFOUNDRY.md) §8.5).
- [ ] `README.md`'s false-after-the-fork sentences are corrected: `:64` ("vendored unmodified. Not
      winnow, not installed, not started"), `:95` ("Nothing in `src/cozempic/` was modified"),
      `:106-107` ("in-tree at a pinned upstream commit"), `:112` ("one arm of a measurement"),
      `:115-118` (the "**It is read-only.**" paragraph), `:180` ("**Not a competitor to Cozempic.**"),
      `:203-207` (the licence paragraph, now settled by [DECISIONS.md](DECISIONS.md) §0.6).
- [ ] `MILESTONES.md:14-15` ("nothing in this container can run the test suite") is corrected; it is
      contradicted by [USAGEFOUNDRY.md](USAGEFOUNDRY.md) §7, which it cites.
- [ ] `cli._SUBCOMMANDS` either lists all twenty or the commit message says why it still does not
      (§2.2).

### Phase 2: delete what is not being maintained

- [x] Given the tree, when `grep -rn 'workers\.dev\|counterapi' src/ plugin/` runs, then it prints
      nothing.
- [x] Given the tree, when `grep -rn 'pip install --upgrade\|uv tool upgrade' src/ plugin/` runs, then
      it prints nothing. `updater.py` is deleted, not neutered.
- [~] `packaging/`, `npm/` and `scripts/` are deleted. `README.md` says the only supported install is
      from source. **`scripts/` only.** The run's brief moved the six channels, `npm/` and the publish
      workflow to their own run (§3).
- [x] `pyproject.toml` declares `psutil` and a `dev` extra containing `pytest`. Given a fresh
      environment built from those declarations only, when the suite runs, then it collects with no
      `ModuleNotFoundError`.
- [x] `guard.py`'s PID-identity check **fails closed**: given `psutil` unavailable, when
      `_pid_identity_match` is called, then it returns false and the terminate path is skipped. A test
      simulates the absence and asserts no signal is sent. This is the single highest-value change in
      the phase and the only one that touches the kill path.
- [x] `_SAFE_ENV_SPEC` has shrunk to the surviving variables, and the tests that verify the overlay
      have shrunk with it. Six, not five — see §5.1.
- [~] Given the tree, when a run greps for any outbound network call outside `winnow bench`, then the
      only hits are in the MCP server's own transport. **`src/` and `plugin/` are clean**; the
      remaining hits are in `npm/` and `packaging/`, deferred with the row above, plus
      `plugin/.mcp.json`'s `--with cozempic`, which is the MCP transport and is phase 4's.

Two decisions the criteria above did not fix, settled here.

**The self-update is deleted, not replaced with a report-only version check.** A check that only
reports still has to ask pypi.org what version exists, which is a third party's endpoint on a session
start, and nothing in the tool consumes the answer: there is no notification surface, no changelog
command, and §0's reproducibility argument wants the measured artefact to be the tree in `src/` and
not a moving comparison against a release of somebody else's program. The version is already recorded
as provenance (`UPSTREAM_VERSION`, §4); a network call cannot add to that.

**`psutil` is both declared and made fail-closed, not one or the other.** The brief allowed either.
Declaring alone leaves the kill path licensed by a library that a broken install can be missing.
Failing closed alone makes the abnormal path the normal one on any machine that did not happen to
have psutil, which would mean a guard that never reloads and never says why. Together they are
coherent: the check has a backend on every supported install, and the case where it does not is
treated as the unknown it is (§9's kill-path criterion above, `guard.py:_pid_identity_match`).

### Phase 3: the runtime surface

- [ ] Given the tree, when `grep -rni 'cozempic' src/ plugin/ docs/ README.md` runs, then every
      remaining hit is provenance (`NOTICE`, `CONTRIBUTORS.md`, `derived_from`,
      [DECISIONS.md](DECISIONS.md) §0.4's quoted block, this document) and none is a path, a variable,
      a marker or a command.
- [ ] Given a hook command in a `settings.json` carrying `# cozempic-hook-schema=v14`, when
      `winnow init` runs, then it **replaces** that hook rather than adding a second one, and the
      result carries `# winnow-hook-schema=v1` (§6.2).
- [ ] Given the same file, when `winnow uninstall` runs, then the old hook is removed.
- [ ] Given `COZEMPIC_CONTEXT_WINDOW=200000` in the environment and `WINNOW_CONTEXT_WINDOW` unset,
      when any command runs, then the value is used and exactly one deprecation line naming both names
      and the removal version goes to stderr.
- [ ] Given both names set to different values, when any command runs, then it exits non-zero with a
      message naming both.
- [ ] Given a live `/tmp/cozempic_guard_${SLUG}.pid` for this session, when the guard is asked to
      start, then it refuses and prints how to clear it (§6.4).
- [ ] `winnow migrate` is idempotent: running it twice leaves the same state and the second run says
      there was nothing to do.
- [ ] `src/winnow/legacy/data/hooks.json` and `plugin/hooks/hooks.json` are still byte-identical and
      `tests/test_hooks_sync.py:24` still passes. Note that test compares
      `json.loads(...)["hooks"]`, not bytes, so it catches neither formatting drift nor drift in any
      key outside `hooks`. The two files match today and nothing enforces that they keep matching; if
      byte-identity is wanted, phase 3 is where the assertion gets added.

### Phase 4: the container

- [ ] Given a machine with no network, when the image is run, then the MCP server starts and answers
      a `tools/list` with the five tools. Nothing is fetched at spawn.
- [ ] Given the image, when it is inspected, then it contains no `_startup_maintenance` thread and
      makes no outbound request on startup.
- [ ] `.mcp.json` invokes the container and contains no `--with` argument.
- [ ] Given the default mount, when `treat_session(execute=True)` is called, then it fails because the
      session directory is mounted read-only, and the error names the flag that would allow it.
- [ ] The image is tagged `winnow:0.1.0` and `winnow:<git-sha>`, and `winnow --version` inside it
      prints `0.1.0`.

---

## 10. Decisions I need

Five, each with a default. "Defaults are fine" is a complete answer.

**Q1. Is `legacy` the right word in the import path?** It is the tripwire that makes silent adoption
of the guard hard, and it is also a word that invites a future run to delete the tree before the
replacement exists. *Default: keep `legacy`, and rely on §8's non-goal list to stop premature
deletion.*

**Q2. Do receipts survive phase 2?** `receipts.py` writes to `~/.cozempic/receipts/` and feeds
`winnow dashboard`. It is local-only, so it is not telemetry, but it is state nobody has asked for and
the dashboard is not on any milestone. *Default: keep receipts, rename the path, and revisit when the
dashboard is next touched. If they go, `COZEMPIC_NO_RECEIPTS` goes with them (§5.1).*

**Q3. stdio or HTTP for the MCP container?** stdio matches today's behaviour and needs no
authentication. HTTP is what "self-hostable" usually means and would let one server serve several
clients, at the cost of a port, an auth story and a threat model this repository has never written
down. *Default: stdio, and treat HTTP as a separate decision with its own security section.*

**Q4. Does the fork keep the guard at all, in the medium term?** §0.2 keeps it, off by default, as
code intended to be replaced. The alternative is deleting it now and losing `treat`, `reload`,
`digest` and the doctor's guard checks with it. *Default: keep it, off, and let milestone 1's number
decide. If the number says the class of tool does not pay, deleting 4,314 lines becomes easy.*

**Q5. Does anything actually depend on cozempic's on-disk state today?** §6.3 scopes the break to one
operator and this container, from the absence of a distribution channel. If there is a real install
on the operator's own machine with savings history worth keeping, `winnow migrate` needs testing
against it rather than against a fixture. *Default: assume not, and write `winnow migrate` to refuse
loudly rather than to merge.*
