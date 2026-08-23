# Running this under UsageFoundry

Written 2026-08-23. UsageFoundry is the orchestrator at `/workspace/UsageFoundry`: it spawns
`claude -p` in a loop, owns the session identity, sets the compaction point, enforces the budget,
and bills every run from the transcripts. This repository contains a tool that also does four of
those five things. This document is the integration spec, and its scope is the overlap.

**§1 to §7 are a specification, not a change.** Nothing in `src/cozempic/`, `plugin/`, `npm/` or
`packaging/` was modified to produce them, and `/workspace/UsageFoundry` is read-only here: every
citation into it is a read.

**§8 is the implementation**, added by a later run against the sections above. It is orchestrator-safe
mode: one switch, `WINNOW_ORCHESTRATOR=1`, and `src/winnow/orchestrator_safe.py` behind it. Read §8
last, and read it as a record of what was built and what was verified rather than as further design.
Where §8 and an earlier section disagree, §8 is what the code does and the earlier section is what
was intended; both readings are kept because the difference is usually the interesting part.

Two facts to hold throughout, because most of §1 follows from them. **Every orchestrated session is
headless**, spawned as `claude -p --output-format stream-json --verbose`
(`orchestrator.ts:5118`), with no controlling terminal and pipes for stdin and stderr. And
**`~/.claude` is a bind mount**: `plugins.ts:15-23` records that compose binds the operator's
`~/.claude` onto `/home/node/.claude`, so anything written there from inside the container lands on
the operator's machine. Both are verifiable from inside a running session. `ls
/home/node/.claude/projects/` in this container lists
`-Users-hendrikkuehnel-Documents-GIT-UsageFoundry`, a slug of a host path that does not exist here.

One correction to the brief that commissioned this document, so nobody re-derives it: the
`--plugin-dir` rationale comment is at `orchestrator.ts:5051-5057`, not 5085-5098. The latter range
is the `readGuardDir` documentation.

---

## 1. The collisions

Eleven. Six were named in the brief and all six are real; §1.3 needed the question it asked
answering, and §1.4 through §1.11 were not on the list. Ordered by blast radius, not by severity of
the code.

### 1.1 The tool assumes a terminal. There is never one.

| Side | Evidence |
| --- | --- |
| Harness | `orchestrator.ts:5118`, headless `-p` spawn. No tty, stdin and stderr are pipes |
| Tool | `cli.py:2108-2113`: `interactive = sys.stdin.isatty() and sys.stderr.isatty()`, with the comment "Fall back to silent auto-install for non-interactive contexts (CI, pipelines, Claude Code subprocess invocations)" |
| Tool | `guard.py:2177` `_detect_terminal_env()` returns `tmux`, `screen`, `ssh` or `plain`. `guard.py:2481-2487`, the `plain` resume path, requires `gnome-terminal` or `xterm` |

**What changes, and on which side: nothing on the harness's side, and this is not a bug to fix.**
Cozempic's non-interactive branch is deliberate and correctly reasoned for CI. The consequence is
what matters and it is stated in §1.7: in the one context where a human cannot be asked, the tool
proceeds without asking. Under an orchestrator that is not a fallback, it is the only path ever
taken.

The second row has its own consequence. In this container `gnome-terminal`, `xterm` and `osascript`
are all absent and there is no `TMUX`, `STY` or `SSH_*`, so `_detect_terminal_env()` returns `plain`
and the resume branch logs `No terminal emulator found` to `/tmp/cozempic_guard.log` and returns.
**The kill is unconditional; the resume is best-effort.** See §1.2 and §1.3 for what the harness then
sees.

### 1.2 Terminating the session is the one thing the harness forbids, and the tool's kill is invisible to the mechanism that forbids it.

| Side | Evidence |
| --- | --- |
| Harness | `orchestrator.ts:5145` `args.push("--disallowedTools", ...PROCESS_KILLERS)`, with `orchestrator.ts:4818` `const PROCESS_KILLERS = ["Bash(pkill:*)", "Bash(killall:*)"]` and the rationale at 4820-4823 |
| Tool | `guard.py:2377-2400`: `os.kill(claude_pid, signal.SIGTERM)`, `_wait_for_exit(claude_pid, timeout=5.0)`, then `os.kill(claude_pid, signal.SIGKILL)` |

**What changes: nothing on either side, and that is the finding.** `--disallowedTools` filters the
agent's *tool calls*. The guard's kill is an `os.kill` inside a detached Python daemon, so it is not
a tool call and no `disallowedTools` pattern can reach it. This is a category difference, not an
evasion: the harness's control surface is the agent, and the guard is not the agent.

What follows is a rule rather than a patch. **The harness's protection against session termination
does not extend to anything the session installs**, so a tool that can kill the session must be kept
from starting rather than restrained once running. §4 is that list. It is also why §5 keeps the
decision with the operator: no flag inside the container can make this safe from the outside.

Two mitigations that are real and that narrow the exposure, both worth recording so §4 is a flag
rather than a patch:

- `guard.py:1084`, `# Headless sessions are unchanged (reload immediately).` The kill-and-resume path is for terminals; an orchestrated session takes the headless branch.
- Three identity gates run before the kill: liveness (`guard.py:2261`), a start-time comparison against the pid recorded at guard startup (`guard.py:2269`), and an argv check (`guard.py:2274`). The start-time gate works in this container without `psutil` because `/proc/<pid>/stat` is readable (`guard.py:3943-3964`), which I confirmed. It fails **open** only when all three backends fail (`guard.py:3953`).

A claim in an earlier draft of my own analysis that must not be repeated: I expected
`session.py:300` `find_claude_pid()`, which walks up ten generations matching `comm` for "node" or
"claude", to be able to reach the supervising server and get it killed. The actual tree here is
`tini` → `next-server (v` → `claude` → `bash`, and `"next-server (v"` contains neither string, so
the walk stops at the right process. **The alarming version of that finding is false.**

### 1.3 The harness owns session identity, and a kill mid-cycle is recorded as an unexplained exit.

| Side | Evidence |
| --- | --- |
| Harness | adopts the session id off the stream (`orchestrator.ts:6536-6546`), persists it (`:7107` `UPDATE runs SET session_id = ?`), and re-passes it next cycle (`:5174` `--resume`) |
| Tool | rewrites the transcript in place under that same id (`session.py:1040`), and may end the process holding it (§1.2) |

The brief asked what the harness observes when its child dies mid-cycle and what it records. The
answer, traced end to end:

1. `orchestrator.ts:6250` `result.exitCode = code ?? -1`. A signal-killed child gives Node `code === null`, so a `SIGKILL` becomes exit code **-1**.
2. `orchestrator.ts:8026` `if (res.exitCode !== 0 || res.isError)` takes the failure branch. Unless this was the opening cycle of a resumed segment that produced no output at all, `looksLikeResumeFailure` is false (`:8043-8046` requires `usedResume && cyclesThisSegment === 1 && !res.sawResult && res.finalText === ""`).
3. So `stopReason` becomes the generic `` `Claude Code exited with code ${res.exitCode}.` `` (`:8065`) and `finalStatus` becomes `failed`. **The run's recorded reason for stopping is "Claude Code exited with code -1", and nothing in it points at the guard.**
4. The spend for the dead cycle is then recovered by `reconcileKilledCycle` (`orchestrator.ts:6972-6996`), which re-scans the transcript. §1.4 is why that recovery can silently return nothing.

There is a second-order interaction worth naming because the harness already anticipated it in
prose. `orchestrator.ts:8027-8031` says a resumed session can be rejected outright because "an
assistant turn holding a `tool_use` with no matching result is not a message list the API will
accept". A prune that broke pairing would produce exactly that, and the harness's answer is one
retry then a stop naming the manual command. Cozempic guards against it from the other side:
`safety.py:179` invariant C8 refuses any prune that leaves a `tool_use` without its result. **The two
systems independently defend the same failure**, which is the strongest single argument that
integrating them is tractable.

**What changes, and on which side.** Nothing in the harness. On the tool's side, the requirement is
that the guard never terminate an orchestrated session, because the harness cannot distinguish that
from a crash and will file it as one. §4.

### 1.4 `metadata-strip` deletes the harness's accounting, and the loss compounds into the budget. Not in the brief.

```python
@strategy("metadata-strip", "Strip token usage stats, signatures, stop_reason", "gentle", "1-3%")
    strip_inner = {"usage", "stop_reason", "stop_sequence"}
    strip_outer = {"costUSD", "duration", "apiDuration"}
```
`strategies/gentle.py:237-241`. Tier **gentle**, so on at every prescription level including the
default, for a claimed 1 to 3 percent of file bytes.

| Side | Evidence |
| --- | --- |
| Harness | `transcripts.ts:335-336`: `const usage = message?.usage …; if (!message || !usage) return null;`. A record with no `usage` is not an error and not a warning: it is dropped from the scan |
| Harness | `transcripts.ts:313-315` reads `input_tokens`, `output_tokens`, `cache_read_input_tokens`; `:303` reads `cache_creation_input_tokens` |
| Harness | `orchestrator.ts:6972-6996` `reconcileKilledCycle` sums those same entries, and returns `null` when the total is zero |
| Harness | `orchestrator.ts:5199-5201`: `--max-budget-usd` is passed as `maxRunCostUSD - spentGuardUSD`, and `spentGuardUSD` comes from the same scan |

**This is the collision with the largest blast radius, and the compounding is the reason.** Three
effects, each worse than the last:

1. A pruned session's cost reads as lower than it was, silently, with no error anywhere.
2. For a cycle the guard killed, the transcript is the *only* record, so `reconcileKilledCycle` returns `null` and the cycle bills as **zero**.
3. Because remaining budget is computed as ceiling minus observed spend, under-observed spend **raises** the ceiling handed to the next cycle. The mechanism that deletes the accounting also loosens the guard that the accounting feeds.

Effect 3 is the one to state plainly: a budget enforced from a mutable record is not enforced. It
does not require malice or a bug, only `-rx gentle`.

**What changes, and on which side.** Two things, and they are independent so both should happen.

*On the tool's side:* `metadata-strip` must be off in any session an orchestrator bills. There is no
environment variable for a single strategy, so this is a configuration-file exclusion or a patch,
and §4 marks it as the one item on that list which cannot be switched off by environment alone.

*On the harness's side:* nothing is required, but one thing is cheap and worth proposing separately.
`transcripts.ts:336` treats a record with no `usage` identically to a record that is not a turn.
Counting those separately would turn a silent undercount into an observable one. That is a change to
UsageFoundry and therefore not this repository's to make; it belongs in a proposal beside
`proposals/ContextControl/`.

Note the third-party consequence too, because it is the reason [COZEMPIC.md](COZEMPIC.md) §3.1 has
an obstacle section: these are the same fields the caching measurement needs. A session Cozempic has
pruned cannot be used to evaluate whether Cozempic's pruning paid.

### 1.5 Autocompaction is already set by the harness. Precedence has to be decided, not discovered.

| Side | Evidence |
| --- | --- |
| Harness | `orchestrator.ts:5193` `args.push("--autocompact", String(AUTOCOMPACT_WINDOW_TOKENS))`, `:4922` `const AUTOCOMPACT_WINDOW_TOKENS = 200_000`, and the note at 4910-4920 |
| Harness | `orchestrator.ts:5190-5192`: passed per cycle, because `--resume` does not restore it, "and a later cycle running under the default window behaves exactly like one that was never given a ceiling" |
| Tool | `guard.py:1290`, a soft threshold at 25% of the token window; `guard.py:648` a hard threshold in megabytes; `plugin/hooks/hooks.json` registers `PreCompact` and `PostCompact` hooks |

The harness's note at 4915-4920 is the part that decides the rule: the summariser's own call "carries
no usage block in any of the 42 boundaries, so roughly 168,000 in and 6,300 out per compaction is
billed and invisible to `scanUsage()`". **Compaction on this install has a cost the harness cannot
see.** That is not an argument for compacting less by pruning more, and §2 works out why.

### 1.6 The budget is enforced by the CLI, per invocation.

| Side | Evidence |
| --- | --- |
| Harness | `orchestrator.ts:5201` `args.push("--max-budget-usd", String(remaining))`, with `remaining = max(0, maxRunCostUSD - spentGuardUSD)`, described at `:5194-5198` as "a hard stop inside the CLI … Per invocation, so a resumed session is bounded by what is left *now*" |
| Tool | no budget concept. `helpers.py:11` `~/.cozempic_savings.json` counts claimed savings, in bytes |

**What changes: nothing, except that §1.4 must be fixed first.** The two mechanisms do not overlap
in function; they overlap in their input. This entry exists to record that the budget is not an
independent check on §1.4's failure mode, it is downstream of it.

### 1.7 The tool installs itself into the bind-mounted `~/.claude`, silently, *because* the session is headless.

| Side | Evidence |
| --- | --- |
| Harness | `plugins.ts:7-28`. The CLI plugin registry "records **absolute** paths … Whichever side installs last breaks the other, silently: the CLI logs a skip and exits 0, so every session afterwards runs with no plugin, no error and entirely normal-looking output." The app therefore "stores directory paths and passes `--plugin-dir` per spawn, which needs no writes into `~/.claude` at all" |
| Tool | `cli.py:2060-2076` `_maybe_global_init`, reached on almost any invocation, writes hooks into `~/.claude/settings.json` via `run_init(str(Path.home()))` at `cli.py:2142` |
| Tool | `cli.py:2108-2113`: the confirmation prompt is shown only when both stdin and stderr are ttys. Headless, `interactive` is `False` and control falls straight through to `run_init` |

Read those three rows together. The harness went out of its way to never write into `~/.claude`,
having verified what happens when host and container disagree about absolute paths. The tool writes
into `~/.claude/settings.json` on first use, and the confirmation that would have stopped it is
skipped in exactly the context the harness provides. **A single `cozempic --version` inside an
orchestrated session modifies the operator's host Claude Code configuration**, and prints one line
to stderr about it (`cli.py:2195`).

It is not only `settings.json`. Under the bind mount these all land on the host:
`~/.claude/settings.json`; `~/.claude/cozempic-metrics/nudge-state.json` (`cli.py:1482`);
`~/.claude/projects/<slug>/team-checkpoint.md` (`guard.py:389-390`, where `project_dir =
session_path.parent`); the `~/.claude/team-checkpoint.md` fallback, which `cli.py:1014` itself calls
"a cross-project read vector"; and `~/.claude/projects/<slug>/memory/cozempic_digest.md` plus an
edit to that directory's `MEMORY.md` index (`digest.py:954-996`). The last one is worth its own
sentence: `MEMORY.md` is loaded into every session's context, so the digest writes into the
operator's own memory index. It is conditional, since `_get_memdir` returns `None` unless Claude Code
has already created the directory (`digest.py:944-951`), and on this machine two such directories
exist, one of them the operator's host UsageFoundry checkout.

What does **not** happen, correcting another of my own earlier findings: `~/.cozempic/`,
`~/.cozempic_savings.json` and the marker files are container-local, since only `/home/node/.claude`,
`/home/node/go` and `/home/node/.local/share/gh` are mounts. And the guard's `team-checkpoint.md`
goes to `session_path.parent`, which is `~/.claude/projects/<slug>/`, **not** the git worktree, so
there is no path by which an agent commits it. `cozempic init` without `--global` would write a
project `.claude/settings.json` into the worktree, but nothing invokes that automatically, and this
repository has no `.claude/` directory today, which is bail-out 2 of `_maybe_auto_init`
(`cli.py:2269-2273`).

### 1.8 The tool upgrades itself from PyPI, by two independent paths.

| Side | Evidence |
| --- | --- |
| Tool | `plugin/hooks/hooks.json`, SessionStart: under `flock -n`, `uv pip install --upgrade cozempic` falling back to `pip install --upgrade cozempic`, then `cozempic guard --reload-self` if the version changed, then the guard daemon, with the whole subshell backgrounded |
| Tool | `cli.py:2399` into `updater.py:225`, the CLI's own periodic check, running `pip install --upgrade` (`updater.py:92`) or `uv tool upgrade` (`:109`) as a subprocess |
| Harness | nothing. The harness has no opinion about the container's Python environment |

**What changes: both paths off.** Two reasons, and the second is the one that matters here. A
session start that mutates its own runtime is not reproducible, so no run's result can be attributed
to a version. And [DECISIONS.md](DECISIONS.md) §0 turns on this: it is why the tree is vendored at a
recorded sha rather than pinned as a dependency. `COZEMPIC_NO_AUTO_UPDATE=1` or
`COZEMPIC_PIN=1.8.39` stops both (`updater.py:239`, `:217`, and the hook's own
`[ -z "$COZEMPIC_NO_AUTO_UPDATE" ] && [ -z "$COZEMPIC_PIN" ]` guard).

### 1.9 The plugin's MCP server does not run the vendored tree. Not in the brief.

`plugin/.mcp.json` starts the server as `uv run --with fastmcp --with cozempic python
${CLAUDE_PLUGIN_ROOT}/servers/cozempic_mcp.py`. Three consequences: it needs `uv`; it needs network
at spawn; and `--with cozempic` **fetches Cozempic from PyPI**, so `--plugin-dir plugin/` would run a
downloaded copy rather than `src/cozempic/`. Anyone measuring the vendored tree through the plugin
would be measuring something else. `fastmcp` is therefore a real dependency of the plugin, though not
of the runtime ([COZEMPIC.md](COZEMPIC.md) §1.1).

Two corrections to that paragraph, neither of them the fork's doing.

The first consequence used to read "it needs `uv`, **which is not installed in this container**".
That was true when §1.9 was written and is not true now: `uv 0.12.5` is at `/usr/local/bin/uv`, and
there is a `.venv` with a `cozempic` console script in it. The image changed under the document,
which §7 warns about in the other direction; §7's own "`pip`, `pip3`, `uv` and `pytest` all absent"
is stale for the same reason and by the same commit. Nothing else in §1.9 moves: network at spawn and
the PyPI fetch are unchanged, and `uv` being present makes the fetch *more* likely to happen, not
less.

The second is that the third consequence is the one thing here the fork actually resolves rather than
renames. The server cannot be made to run this repository's code from outside the tree, because the
fix is that it runs winnow's own code out of an image winnow builds:
[DECISIONS.md](DECISIONS.md) §0.3, phase 4 of [FORK.md](FORK.md). Until that phase lands, this
paragraph stands as written and the answer is still "do not enable the vendored `plugin/`".

### 1.10 Global state is shared across concurrent runs and with the host. Not in the brief.

`helpers.py:105` names the lock over `cozempic-sessions.json` and `.cozempic_savings.json`, both
single files. The savings file is container-local; `~/.claude/cozempic-sessions.json` is not, and a
container running several runs at once has several writers into one host file.

The guard's own runtime state is keyed per session and hardcoded to `/tmp`: `_pid_file_for_session`
returns `_guard_tmp_root() / f"cozempic_guard_{session_id[:12]}.pid"` (`guard.py:3282-3303`), and
`_guard_tmp_root()` returns a literal `Path("/tmp")` on POSIX with a comment explaining that it must
stay byte-identical to the shell hook, which cannot call `tempfile.gettempdir()`
(`guard.py:2636-2650`). Session ids are uuids, so per-session collisions are not the risk. The risk
is that `/tmp` is shared between every agent in the container and cannot be redirected, which §7 ran
into for real.

### 1.11 The harness's transcript reader detects a rewrite only by shrink. Narrow, and stated as narrow.

`transcripts.ts:396`: `const rotated = prev !== undefined && stat.size < prev.size`, and
`:397` `const start = prev && !rotated ? prev.offset : 0`. A prune shrinks the file, so the next scan
normally sees `size < prev.size`, re-reads from zero, and is correct. The failure needs both halves
of a race: a prune **and** enough appended output to bring the file back above its previous size,
between two scans, which happen roughly once per work cycle. `start` then points at a byte offset
into shifted content, the fragment there does not parse, and `transcripts.ts:462-463`
(`if (!entry) continue`) skips it without a word.

I have not observed this and I am not claiming it happens. It is here because it is a second silent
undercount on the same path as §1.4, it is cheap to rule out, and the condition is precise enough to
test.

---

## 2. Precedence: autocompaction versus pruning

The rule, and then why.

> **The harness's autocompaction is authoritative. The tool may not act to prevent it, may not act
> because of it, and may not act while a session is live. Pruning happens between cycles, on a
> transcript nobody is holding, or it does not happen.**

Three reasons, in the order they bind.

**Compaction is not the tool's business under an orchestrator.** `--autocompact 200000` is passed on
every cycle (`orchestrator.ts:5193`), deliberately per cycle because `--resume` does not restore it.
The harness has decided where the boundary is. Cozempic's soft threshold at 25% of the window
(`guard.py:1290`) is a *different* decision about the same event, made by a component that does not
know the run's budget, its deadline or its cycle count. Two independent controllers on one variable
is not a tuning problem, it is an ownership problem, and the harness owns it.

**The arithmetic points the same way.** [COZEMPIC.md](COZEMPIC.md) §3.1 works it out: a cut inside a
live conversation pays `1.9·S − 2·D` once and earns `0.1·D` a turn back, so it needs
`T* = 19·(S/D) − 20` further turns to pay for itself, and there is exactly one moment where the edit
is free, namely immediately before a handover that was going to rewrite the suffix anyway
(`ContextControl/01-constraints.md:66-74`). A cycle boundary in this harness *is* that moment. A
25%-of-window threshold cannot find it, because occupancy and position-in-cycle are unrelated.
Pruning between cycles is both the safe rule and the profitable one, which is rare enough to be
worth saying out loud.

**The one argument on the other side, and why it loses here.** Compaction is irreversible: prose
replaces records, and `01-constraints.md`'s framing plus the harness's own note at 4915-4920 mean it
also costs about 168,000 input and 6,300 output tokens that `scanUsage()` never sees. Pruning to
delay compaction is therefore not a foolish trade in general. It loses under this harness for a
reason specific to it: **the harness's cycles are short and its handovers are frequent**, so a
between-cycles prune is available every few minutes and there is no long-lived conversation to
protect that a cycle boundary will not reach first. On a desktop session that runs for six hours
without a handover, Cozempic's trade is the better one. That is the same conclusion
[COZEMPIC.md](COZEMPIC.md) §2.1 reaches: this is two tools for two shapes of session, not a right
answer and a wrong one.

**The corollary for the `PreCompact` hook.** It should stay, and it is the one hook worth keeping. It
does not prune; it writes a team checkpoint before the summariser runs
(`plugin/hooks/hooks.json`, PreCompact → `cozempic checkpoint`), which is reversible-loss insurance
against an irreversible operation and costs one file write. `PostCompact` reads it back. Those two
are compatible with the rule above, because neither changes the transcript the model is holding.

§8.3 implements the rule as an argv gate — a mutating prune is refused while any Claude process is
live — and §8.7 keeps both hooks, pointed at a checkpoint that does not land in the bind mount.

---

## 3. The integration path

`--plugin-dir` per spawn, and nothing else.

`orchestrator.ts:5051-5057` states the property to preserve: `--plugin-dir` "is **not** restored by
`--resume`, so a version of this that only sent it on the opening cycle would leave every later cycle
of the same run without the plugins — silently, since a session missing a hook behaves exactly like
one that never had it." `buildArgs` rebuilds the argv per cycle, so re-passing is the default shape
and a test asserts the flag survives a `resumeSessionId`. `--autocompact` is passed per cycle for the
same reason (`:5190-5192`).

So the shape is: the plugin directory is registered with the app, the app passes it on every spawn,
and nothing is ever installed into `~/.claude`. That is the whole of §1.7's mitigation and it already
exists. What it does *not* do is make the plugin's contents safe: the `SessionStart` hook inside
`plugin/hooks/hooks.json` still upgrades from PyPI and still spawns the guard daemon. §4 is that
list, and §4 is a precondition of using `--plugin-dir` at all rather than an optimisation of it.

Note also §1.9: the plugin's MCP server would run a PyPI copy of Cozempic, not the vendored tree. If
the point of the exercise is to measure the vendored tree, the MCP server must be excluded from the
plugin directory that gets registered.

`winnow safe plugin-dir` is that directory, and §8.5 is what it contains. It is built rather than
filtered, which is the difference that matters here: an upstream release adding a sixth hook is
excluded by default instead of needing to be noticed.

---

## 4. Off by default under an orchestrator

Everything here is off unless an operator turns it on for a named reason. The last column says what
happens if it is left on, in one line, so the list can be argued with item by item.

The switches were `COZEMPIC_*` when this section was measured and are `WINNOW_*` since the rename
([FORK.md](FORK.md) §5.1). The names below are the ones this tree reads; an upstream Cozempic
installed beside it still reads the old ones, and neither reads the other's.

| Feature | Switch | If left on |
| --- | --- | --- |
| Global init into `~/.claude/settings.json` | `WINNOW_NO_GLOBAL_INIT=1` (`cli.py:2076`) | Writes hooks onto the operator's host machine, silently, because headless skips the prompt. §1.7 |
| Project init into `./.claude/settings.json` | `WINNOW_NO_AUTO_INIT=1` (`cli.py:2269`) | A settings file appears in the agent's worktree. Inert today: this repository has no `.claude/`, which is its own bail-out |
| PyPI self-upgrade, both paths | `WINNOW_NO_AUTO_UPDATE=1`, or `WINNOW_PIN=1.8.39` to hold a reviewed version | The measured artefact changes between runs and no result can name its version. §1.8 |
| Telemetry counters | `WINNOW_NO_TELEMETRY=1` (`helpers.py:236`) | Three outbound requests per prune to a third party's Cloudflare Worker. Counters only, but SPEC §10 says no network |
| Receipts into `~/.winnow` | `WINNOW_NO_RECEIPTS=1` | Container-local, so this is hygiene rather than a collision. On by default in the tool's own test suite for the same reason |
| **The guard daemon** | **no environment variable exists.** The only way off is not to install the hook: exclude `SessionStart` from any registered `--plugin-dir`, and keep `WINNOW_NO_GLOBAL_INIT=1` so nothing wires it globally | The session can be `SIGKILL`ed mid-cycle, the harness files it as exit -1, and in this container it is not resumed. §1.1, §1.2, §1.3 |
| **`metadata-strip`** | **no environment variable exists**, and it is gentle-tier so every prescription includes it. Requires a config-file strategy exclusion, or a patch | Spend accounting silently under-reports, killed cycles bill as zero, and the budget ceiling rises to match. §1.4 |

The two bold rows are the finding of this section: **the two features with the largest blast radius
are the two with no off switch.** Both need a mechanism that does not exist yet, which makes them the
first implementation task rather than a configuration note. The tool has 28 `WINNOW_*` variables
and none of them is `WINNOW_NO_GUARD`.

Both now have one, out of tree, and neither is an environment variable. §8.3 refuses the argv that
starts the daemon and §8.4 removes `metadata-strip` from the prescription dict both importers already
hold. One row of this table also turned out to be incomplete: `WINNOW_NO_TELEMETRY=1` stops the
outbound counter requests but not the file the same function writes one line earlier, which is §8.6.

Turning that around: adding `WINNOW_NO_GUARD` and a strategy-exclusion list is a small,
self-contained contribution upstream, and it is the shape of contribution
[DECISIONS.md](DECISIONS.md) §1 already named as the project's fallback. It would be worth doing even
if winnow is abandoned.

---

## 5. What stays the operator's decision

Not the tool's, and not an agent's. Each of these is a judgement about consequences outside the
container, which is precisely what nothing inside it can see.

- **Whether any of this runs against real sessions at all.** The tool rewrites transcripts in place and can end a live session. The decision to point that at a working install belongs to the person who owns the install.
- **Whether `~/.claude` may be written to.** §1.7's writes are not dangerous in themselves. They cross a boundary the harness deliberately never crosses, and only the operator knows what is on the other side of it.
- **Which tier, if any.** `-rx aggressive` is a plain argument with no confirmation (`cli.py:1794`) and the tier ladder is cumulative (`cli.py:400-411`). [DECISIONS.md](DECISIONS.md) D5's `--i-know` exists because this is a risk appetite question, and risk appetite is not a default.
- **Whether a measurement may run at all**, given that measuring requires `metadata-strip` off and therefore a configuration nobody runs by default. Choosing to measure a non-default configuration is a decision about what the result will mean.
- **What happens to a run the guard killed.** The harness records "exited with code -1" and stops. Whether that is retried, investigated or written off is an operator's call, and this document's contribution is only that the reason will not be in the record.
- **Whether the vendored tree is ever unpinned.** [DECISIONS.md](DECISIONS.md) §0 pins it; unpinning is reversible but it ends replayability, so it should be a decision rather than a drift.

---

## 6. What the next run should not do

Short, because the temptations are specific. There were three. **The first was lifted on 2026-08-23**
and two stand.

> **Lifted: "do not patch `src/cozempic/`."** [DECISIONS.md](DECISIONS.md) §0 was reversed on the
> operator's instruction and winnow is now a fork. What this section forbade until then is quoted at
> the end of it, because §8 was built under it and reads as nonsense otherwise.
>
> **What replaces it.** The tree is winnow's own code: editable, renamed, and no longer a
> third-party tree. A fix to the guard is winnow's work and belongs inline. Nothing in it goes
> upstream, because there is no upstream relationship left to send it to.
> [FORK.md](FORK.md) is the naming map: the tree moves to `src/winnow/legacy/`, and the word
> `legacy` in the import path is deliberate. It is inherited code that
> [DECISIONS.md](DECISIONS.md) §0.2 intends to replace, and D2, D7 and §2 are **not** reversed with
> §0. Editing the guard is now allowed; adopting its design is still not, and §0.2 says what a run
> has to amend, by name, before it may.

Do not modify `/workspace/UsageFoundry`. §1.4's harness-side suggestion is a proposal, and the place
for it is a document beside `proposals/ContextControl/`, written and left for the operator. §1.2 and
§1.3 are unaffected by the fork: the harness's ownership of session identity has nothing to do with
who owns the tool's source.

Do not enable the guard to see what happens. §1.2's exposure is a live editor process and §1.3's
consequence is a run recorded as an unexplained crash. If it must be observed, it should be observed
against a throwaway session in a container with nothing else in it. **The fork makes this more
pressing, not less.** Ownership of the code that sends the `SIGKILL` is not evidence about what the
`SIGKILL` does, and a run that reads "the tree is ours now" as licence to try it has confused the
two. It stays off by default; [DECISIONS.md](DECISIONS.md) §0.2 keeps it off.

All three held in the run that produced §8, under the rules as they then were. The tree is untouched
as of that run, `/workspace/UsageFoundry` was only read, and the guard was never started, which is
why "the daemon would have killed this session" is still an inference there rather than an
observation (§8.9). Anything §8 says about the tree being unmodified is a record of that run, not a
rule for the next one.

<details>
<summary>The prohibition as it stood, 2026-08-23, before the fork</summary>

> Do not patch `src/cozempic/` to fix §1.4 or the guard. [DECISIONS.md](DECISIONS.md) §0 makes that
> tree read-only, and a local edit to a self-updating package is the worst of both. New code goes in
> `src/winnow/`; changes wanted in the tool go upstream.

The self-updating half of that argument is dissolved rather than overruled: phase 2 of
[FORK.md](FORK.md) deletes both update paths, so there is no package updating underneath a local
edit any more.

</details>

---

## 7. Verification

The brief expected this section to say that verification is impossible here and to propose how to fix
it. That is not what I found, so the recommendation is different and better: **the suite runs in this
container today, and it takes 39 seconds.** What was missing was not a capability but five wheels.

### What is actually missing

Confirmed by running it: Python 3.11.2; `pip`, `pip3`, `uv` and `pytest` all absent;
`import ensurepip` raises `ModuleNotFoundError`; `python3 -m venv` fails. The harness's image
installs `python3` without `python3-pip` or `python3-venv` (`Dockerfile:108-113`). So the standard
route in is closed.

But PyPI is reachable from this container (`https://pypi.org/simple/pytest/` returns 200), and pytest
and its dependencies are pure-Python wheels, which are zip files that need no installer. Fetching
five of them with `urllib` and unzipping them onto `PYTHONPATH` gives a working pytest with no `pip`,
no `venv` and nothing written outside a scratch directory:

```
# pytest, pluggy, iniconfig, packaging, pygments -> unzip into $S/site
PYTHONPATH=$S/site python3 -m pytest -q -p no:cacheprovider
```

### The measured baseline

Run on `210b026` plus this pass's documentation commits, which touch no code:

```
2 failed, 1879 passed, 17 skipped, 1 warning, 281 subtests passed in 39.08s
```

plus `tests/test_hook_idempotency_shell.py`, which I ran separately for the reason below: **3
passed**. So the whole suite is **1882 passed, 2 failed, 17 skipped**.

Both failures are in `tests/test_guard_hardening.py::TestG4_PidfileWriteIsAtomic`
(`test_concurrent_starts_only_one_spawn_wins` and
`test_final_pidfile_contains_only_winning_pid`). What I established about them, and no more:

- Run as a class on their own, the first passes and the second fails. So at least one is order-dependent.
- Reproducing the same two-thread race outside pytest gives the correct result: exactly one thread reports `started: True` and the pidfile exists. So the race logic itself works here.
- The guard's pidfile path is hardcoded to `/tmp` and cannot be redirected (`guard.py:2636-2650`), and `/tmp` is shared with every other agent in this container. My run left 25 `cozempic_*` files there, which I removed.

**Shared, non-redirectable `/tmp` is the prime suspect and I did not confirm it.** The honest
statement for the next run is: these two failures are pre-existing on `210b026` in this environment,
they are the only two, and a change that leaves the count at two has not broken anything the suite
covers.

The separate run of `test_hook_idempotency_shell.py` was caution, not necessity. It is the one file
containing an unconditional `os.kill(pid, 9)` (`tests/test_hook_idempotency_shell.py:155`), and in a
container that supervises other agents that deserved reading before running. It reads the pid from a
pidfile the test itself created for a sleeper it spawned, and it stubs `cozempic` on `PATH` so the
hook cannot reach a real install. It is safe, and it passes.

### The recommendation

**One option, not three: bake it into the harness's image.** Add `python3-pip` and `python3-venv` to
the runtime apt list at `Dockerfile:108-113`, beside `python3 make g++`. The Dockerfile's own comment
two lines above already makes the argument better than I can: a compiler in the runtime image is
"a deliberate trade: the alternative is an agent that cannot install dependencies, and a run that
fails at step one is worth less than the layer" (`Dockerfile:105-107`). Two apt packages are a
smaller layer than `g++` by an order of magnitude, and they convert every future Python run in this
harness from unverifiable to verifiable.

Then a run's verification step is three lines with no network improvisation:

```
python3 -m venv .venv && .venv/bin/pip install -q pytest
.venv/bin/python -m pytest -q -p no:cacheprovider
# expect: 2 failed, 1882 passed, 17 skipped
```

`.venv/` is already covered by this repository's `.gitignore`.

Why not the alternatives. Pre-installing `pytest` itself in the image ties the harness's image to one
Python project's test framework, and the next project needs a different one; pip is the general
answer. Requiring a human on the host to run the suite is the status quo and it means a fix landed by
an agent is unverified until someone gets to it, which is the specific failure this section exists to
prevent. And leaving the wheel-fetching recipe as the standing method works, as demonstrated above,
but it depends on outbound network from a container whose network posture is not this repository's to
assume, and it re-derives an installer every run.

### Until the image changes

Two things a run in this container can honestly do with the standard library alone, and one it
cannot.

Can: the wheel bootstrap above, which is the full suite and is what produced the baseline. And, with
no network at all, `python3 -m compileall -q src/cozempic` plus direct `unittest` invocation of the
85 test files that do not import pytest, remembering `tests/conftest.py:35-38`, which says the
hermeticity fixture holds only under pytest, so a bare `unittest` run may write into a real
`~/.cozempic`. Set `COZEMPIC_NO_RECEIPTS=1` first.

Cannot: claim the suite passes without running it. A documentation pass such as this one touches no
code and needs no run; the next run changes behaviour and does need one. That asymmetry is the reason
this section is here.

### What the §8 run measured

The wheel bootstrap works exactly as described above. pytest 9.1.1, pluggy 1.6.0, iniconfig 2.3.0,
packaging 26.3 and pygments 2.21.0 fetched as `py3-none-any` wheels and unzipped into a scratch
directory:

```
COZEMPIC_NO_RECEIPTS=1 PYTHONPATH=$S/site:src python3 -m pytest -q -p no:cacheprovider \
    --ignore=tests/test_hook_idempotency_shell.py
# 1 failed, 1957 passed, 17 skipped, 1 warning, 281 subtests passed in 35.38s
COZEMPIC_NO_RECEIPTS=1 PYTHONPATH=$S/site:src python3 -m pytest -q -p no:cacheprovider \
    tests/test_hook_idempotency_shell.py
# 3 passed
```

So **1960 passed, 1 failed, 17 skipped**, against the baseline's 1882 passed, 2 failed, 17 skipped.
The 78 extra passes are the 77 tests in `tests/test_orchestrator_safe.py` plus one of the two
pre-existing failures, which passed this time. Confirmed by running the suite with the new file
excluded: **1 failed, 1880 passed, 17 skipped** — the same 1881 non-skipped tests as the baseline's
1879 + 2, with one flake flipped.

The flake is the pair this section already flagged, and the §8 run has one more piece of evidence
about it: **which of the two fails alternates between runs.** The full run failed
`test_concurrent_starts_only_one_spawn_wins`; the run with the new file excluded, minutes later on
the same tree, failed `test_final_pidfile_contains_only_winning_pid` instead. That is consistent with
the shared-`/tmp` suspicion and it rules out anything about the change: neither test imports
`src/winnow/`. It also means the honest pass criterion is **at most one of that pair fails**, not
"exactly these two fail".

The run left 23 `cozempic_*` files in the shared `/tmp` and they were removed.

### Running the suite installs the tool

This is the part of §7 that was wrong, and it was wrong in the direction that matters. **The vendored
suite writes into the real `$HOME` and into the bind-mounted `~/.claude/settings.json`.** Not the
mode: the suite, run by the recipe above.

Observed rather than inferred. `/home/node/.claude/settings.20260823_135444.bak` is cozempic's own
backup naming, written at 13:54:44, and the live file next to it differed from that backup by
**exactly one key**: `hooks`, holding all seven of cozempic's hook entries across `SessionStart`,
`PostToolUse`, `Stop`, `PreCompact` and `PostCompact`. Also written: `~/.cozempic_global_initialized`
at the same second, and `~/.cozempic/behavioral-digest.md` a minute later containing
`Project: /test`, five `noise 0`-style pending rules and one active rule reading "Do not add
Co-Authored-By to commits" — fixture content, in the file a real digest would be read back from.

So §1.7's install path fires from the test suite, and the state it leaves outlives the container's
session: the `SessionStart` hook it installed is the one that upgrades from PyPI and spawns the guard
daemon, and it fired on the next compaction of the session that ran the suite. `cozempic` was not on
`PATH` and not importable outside the tree, so both fallbacks were no-ops and no daemon started —
which is luck, not isolation.

The `hooks` key was removed and the three `$HOME` paths deleted, restoring the file to the backup's
content byte for byte. `winnow safe check` reports clean afterwards, and it is what found this: its
`global-hooks` and `home-state` findings both fired, which is the first time either has been
observed doing something other than passing.

**Anyone running §7's recipe on a host they care about should expect their `~/.claude/settings.json`
to gain cozempic's hooks**, and should check for `settings.<timestamp>.bak` beside it afterwards. A
test suite that installs the software it is testing into the developer's home directory is an
upstream defect, not a local one; the fix belongs there. Meanwhile `winnow safe check` before and
after the suite is the cheap detection.

---

## 8. The mode, as implemented

One switch, one module, no edit to `src/cozempic/`.

```
WINNOW_ORCHESTRATOR=1        # the only mechanism. Nothing is auto-detected
WINNOW_DATA_DIR=<path>       # optional; default ~/.winnow
python -m winnow safe {check,env,plugin-dir,run,checkpoint,post-compact}
```

`check` and `env` read state and work with the mode off. The other four exit 3 without the switch,
because a mode that silently declines to protect anything cannot be told apart from one that is off.

### 8.1 Why one variable and not detection

There is no harness marker to detect. `childEnv()` (`orchestrator.ts:5902-5917`) strips `UF_*`,
`OTEL_*`, `ANTHROPIC_ADMIN_KEY`, `CLAUDE_CODE_ENABLE_TELEMETRY`, `DATA_DIR` and `NODE_OPTIONS` from
the child, so nothing inside the session can see that a harness spawned it. Any other variable set on
the server does reach the agent, so `WINNOW_ORCHESTRATOR=1` passes through — and it is the operator's
statement of intent rather than an inference, which is the right shape for a switch that decides
whether a daemon may `SIGKILL` the session.

`is_enabled` raises on a value it does not recognise instead of reading it as off. A typo in the
compose file should stop the invocation, not silently disarm the mode.

### 8.2 Where the mode lives, and why not in the vendored tree

§6 rules out patching `src/cozempic/`, so every closure is reachable from outside it:

| Invariant | Closure | Where |
| --- | --- | --- |
| 1. Never terminate this session | refuse the argv that starts the daemon or signals one | §8.3 |
| 2. Never resume a session | refuse `reload`, which spawns a `claude --resume` watcher | §8.3 |
| 3. No update, no PyPI check, no drift | `WINNOW_NO_AUTO_UPDATE=1` + `WINNOW_PIN=1.8.39`, refuse `self-update`, and relocate the sentinel the switches do not cover | §8.6 |
| 4. No writes to `~/.claude`, no global hooks, no foreign `settings.json` | refuse `init`/`uninstall`/`nudge`, a `--plugin-dir` built from scratch, a redirected checkpoint | §8.5, §8.7 |
| 5. Do not compete with the harness's context and cost controls | refuse a mutating prune while a Claude process is live | §8.3 |
| 6. Nothing important written into the model's memory | refuse `digest inject`, drop the skills and the MCP server | §8.3, §8.5 |

### 8.3 The argv gate

`refusal_for(argv, live_pid=...)` returns the reason a command will not run, or None. Three classes:

- **Refused whatever the arguments**: `guard`, `reload`, `self-update`, `init`, `uninstall`, `checkpoint`, `nudge`, `remind`.
- **Refused in a particular shape**: `guard-watchdog --fix` (sends `SIGTERM`, `cli.py:1129`), `digest inject` (writes into `~/.claude/projects/*/memory/` and edits `MEMORY.md`, `digest.py:954-996`). Both commands are allowed without those arguments.
- **Refused only while a session is live**: `treat --execute`, `strategy --execute`, `digest update|clear|flush|recover`. This is §2's precedence rule and nothing else: the harness's autocompaction is authoritative, so the tool may not act to prevent compaction, may not act because of it, and may not act while a session is live. `live_claude_pid()` answers "is one live" by delegating to the vendored `find_claude_pid`; it is passed in rather than probed inside the gate so the decision is testable without arranging a process tree.

Every reason names what refused and cites the section it comes from, on stderr, which the orchestrator
already records per cycle. Nothing writes a log file (SPEC §10).

One thing the gate had to get right that the spec did not anticipate: **it mirrors cozempic's argparse
parser, not `cli._SUBCOMMANDS`.** The two disagree. `nudge` is in the parser and not in that constant,
and `nudge` is the one subcommand that writes into `~/.claude/cozempic-metrics/` (`cli.py:1482`). A
gate built on `_SUBCOMMANDS` would not have seen it. The mirror is frozen in winnow's own source and a
test compares it against the live parser, so an upstream tree with a new subcommand fails a test here
instead of defaulting that subcommand to allowed.

### 8.4 The `metadata-strip` exclusion

`apply_strategy_exclusions()` removes it from every prescription **in place**: `cli.py:24` and
`guard.py:203` bind `registry.PRESCRIPTIONS` at import time, so rebinding the module attribute would
leave both holding the original dict. This is also why `winnow safe run` calls `cozempic.cli.main()`
in this process rather than spawning it — a subprocess would import a fresh, unexcluded copy.

### 8.5 The plugin directory

`winnow safe plugin-dir` writes a directory to pass to `--plugin-dir`. It is **built from scratch, not
copied and filtered**, so anything upstream adds is excluded by default rather than by classification.

Kept: `PreCompact` and `PostCompact`, pointed at `winnow safe checkpoint` and `winnow safe
post-compact`. Dropped: `SessionStart` (upgrades from PyPI and starts the guard), `PostToolUse`,
`Stop`, and the `.mcp.json`, `servers/` and `skills/` paths — §1.9's MCP server would run a PyPI copy
of the tool rather than the vendored tree, and the skills are instructions to the model.

The generated hook commands **bake `WINNOW_ORCHESTRATOR=1` in** rather than inheriting it. The
directory only exists because the mode materialised it, so a hook inside it is running under the mode
by construction, and a hook that silently did nothing because compose forgot a variable is exactly the
failure `orchestrator.ts:5051-5057` describes. The commands end in `|| true` for the reason the
vendored hooks do: a non-zero exit is fed back to the model, and "no team state to checkpoint" is not
something to tell the model about.

The output is byte-deterministic given the same source and command, so a diff between two runs is
empty and any difference in it is a difference somebody made. A `winnow-safe-manifest.json` records
what was dropped and why, and what the directory was derived from.

**The directory says it is winnow's.** The first version of this copied the vendored
`plugin/.claude-plugin/plugin.json` and overwrote `name`, which left the generated manifest carrying
cozempic's `description`, `version` `1.8.39`, `author` and `repository`. That is the manifest
UsageFoundry reads and displays: `plugins.ts:107-114` takes `name` and `description` straight out of it
for the plugin list, so the directory an operator would enable presented itself as Cozempic's, under
Cozempic's name, describing pruning — which is the one thing this mode does not do. The manifest is now
written from scratch like the hooks manifest, and holds two keys:

```json
{
  "description": "The PreCompact and PostCompact hooks of winnow's orchestrator-safe mode: before the harness compacts, the session's agent-team state is written into winnow's own data directory; after, it is read back. The directory holds nothing else: no other hooks, no MCP server, no skills, and it changes no transcript.",
  "name": "winnow"
}
```

No `version` key. Winnow has not versioned itself and upstream's `1.8.39` names a release of a
different program, so an invented number would be the same false claim in another font;
`plugins.ts:107-114` reads a missing version as `null` and the list renders without one. The
provenance is not deleted with it — it moves to `winnow-safe-manifest.json`, which already records
what was dropped and why, as a `derived_from` object naming upstream's `name`, `version` and
`license`, the copyright holder, and where the notice lives:

```json
"derived_from": {
  "copyright": "2026 Ruya AI",
  "license": "MIT",
  "name": "cozempic",
  "notice": "Vendored prior art, MIT, retained verbatim as LICENSE at the root of the winnow repository (DECISIONS.md §0). Neither file in this directory is a copy of it: both are generated by winnow, which has not versioned itself and so declares no version.",
  "version": "1.8.39"
}
```

Those three fields are read out of the source manifest rather than hardcoded, so a vendored tree moved
to another release says so here without an edit. MIT's notice requirement is met by the repository's
own `LICENSE`, which DECISIONS §0 keeps verbatim: the generated directory contains no upstream bytes at
all, because both files in it are written by winnow. A test reads that `LICENSE` and fails if the
recorded copyright line is no longer in it, so the attribution cannot drift away from the file it
names. (Verified 2026-08-23: `tests/test_orchestrator_safe.py:503`,
`test_the_recorded_notice_matches_the_licence_it_points_at`, asserting the substrings `2026 Ruya AI`
and `MIT License`.)

> **Two sentences here the fork falsifies, 2026-08-23.** Both are prose *and* strings baked into
> `src/winnow/orchestrator_safe.py`, so the code has to move with the document and the test at :503
> will not catch either of them: it checks that the copyright line is still in `LICENSE`, which it
> is, not that the claim about `LICENSE` is still true.
>
> **"which DECISIONS §0 keeps verbatim"** is no longer true. §0.6 adds a second copyright line, so
> `LICENSE` becomes winnow's MIT with both notices over one unmodified permission notice. The
> requirement is still met, by both notices being present rather than by the file being untouched.
> The same claim is a literal in `upstream_provenance()` (`orchestrator_safe.py:571-575`): "Vendored
> prior art, MIT, retained verbatim as LICENSE at the root of the winnow repository (DECISIONS.md
> §0)". That string is wrong in two ways after the fork, "vendored prior art" and "retained
> verbatim", and phase 1 of [FORK.md](FORK.md) rewrites it to point at `NOTICE`.
>
> **"Winnow has not versioned itself"** stops being true at phase 1. §8.5 was right to refuse to
> invent a number and the refusal is not being overturned: what changed is that a fork with a
> container image to tag has to have a version, so [FORK.md](FORK.md) gives winnow **`0.1.0`**,
> chosen precisely so it cannot be mistaken for a continuation of `1.8.39`. The manifest gains a
> `version` key at phase 1, and the sentence in `upstream_provenance()`'s notice string, "both are
> generated by winnow, which has not versioned itself and so declares no version", goes with it. The
> `derived_from` block is unaffected: upstream's `1.8.39` stays exactly where it is, as provenance.

**Where to write it.** `--out` defaults to `<repository root>/winnow-plugin`, which is gitignored.
It used to default to `~/.winnow/plugin`, and that path can never be enabled: `discoverPlugins`
(`plugins.ts:244-315`) walks UsageFoundry's workspace mounts and nothing else, so a plugin directory
under `$HOME` is invisible to the app no matter how correct it is. That is what made §8.9's "the mode
has never run inside a real orchestrated cycle" unverifiable rather than merely unverified.

The destination has to survive that walk, which constrains the name: it is `MAX_DEPTH`-bounded at 3
below the mount root, it skips any component starting with `.` (so `.winnow/plugin` would not be
found, and neither would anything under `.uf-worktrees`, which is a worktree of this repository), it
skips the names at `plugins.ts:48-58` (`node_modules`, `dist`, `build`, `vendor`, `target`, …), and it
stops descending at the first plugin it finds, so the destination must not sit inside the vendored
`plugin/`. `<mount>/winnow/winnow-plugin` is at depth 2 and clears all four. To register it, generate
it in the checkout the app has mounted and enable it from the plugin list; pass `--out` for anywhere
else.

Two consequences worth stating rather than discovering. The vendored `plugin/` is itself a plugin
directory inside the mount, so the app already lists it as `cozempic` with upstream's description —
enabling *that* is the thing this mode exists to prevent, and the two are now told apart by name in
the list rather than by path. And a directory generated inside a `.uf-worktrees/` worktree is not
discoverable, by the same rule that skips dot-directories; the file is still written, and `--out` or a
generate-in-the-checkout step is the answer.

**Every hook action says one line.** `checkpoint` used to print `winnow: team state checkpointed to
<path>` when there was team state and exit 2 in silence when there was none, and `post-compact` either
printed the checkpoint or said nothing at all. So a cycle where nothing needed checkpointing was
byte-identical, in the run's log, to a cycle where the plugin was never loaded — the failure the
paragraph above quotes `orchestrator.ts:5051-5057` for, reintroduced one level down. Each action now
ends in exactly one bounded `winnow: ` line on stderr whatever the outcome, with the exit codes
unchanged:

| Outcome | Line | Exit |
| --- | --- | --- |
| checkpoint wrote one | `winnow: team state checkpointed to <path>` | 0 |
| no team state in the session | `winnow: nothing to checkpoint: no team state in <file>` | 2 |
| no session found at all | `winnow: no session to checkpoint` | 2 |
| post-compact restored one | `winnow: checkpoint restored, <n> characters` | 0 |
| nothing stored to restore | `winnow: no checkpoint to restore` | 2 |
| the mode is off or garbled | the reason, naming `WINNOW_ORCHESTRATOR` | 3 |

Bounded at 500 characters, whitespace collapsed to one line, and truncated with an ASCII ellipsis:
the orchestrator stores every stderr line as a database row (`logLine.ts`, `MAX_LOG_CHARS` 8,000, and
the comment there explains why unbounded stderr costs real money), and a session filename or a path
arriving from outside cannot be trusted for length. 500 is above the longest refusal reason the gate
can emit — 272 characters, held by a test — so no citation is ever cut. Still no log file: SPEC §10
forbids one and stderr is already recorded per cycle. `post-compact` keeps the checkpoint itself on
stdout, which is the hook's output to the model; only the fact of it goes to stderr.

### 8.6 The state the environment overlay could not reach

Found while snapshotting the filesystem for §8.8, not by reading: this container already held
`~/.cozempic_installed`, `~/.cozempic_update_check` and `~/.cozempic/behavioral-digest.md`. §7's
"Running the suite installs the tool" is where they came from and it is worth reading first — the
point here is only that they existed, and that no environment variable would have stopped the first
of them.

`cozempic.cli.main` calls `ping_install_if_new()` before it parses argv (`cli.py:2398`), and that
function writes `~/.cozempic_installed` at `updater.py:186` and consults `COZEMPIC_NO_TELEMETRY` at
`updater.py:187`. **The switch stops the network ping, not the write one line before it.** No
environment variable covers this, and §6 rules out the patch, so the mode works on the path instead:
`redirect_home_writes()` rebinds the ten module-level constants in the vendored tree that are computed
from `Path.home()` at import time, pointing them into winnow's data directory.

That only works because every one of those constants is read through its own module's global. A
`from .digest import DIGEST_DIR` somewhere else would keep the old path silently, so a test asserts
the absence of any such import rather than trusting it, and a second asserts the constants still exist
and still point at `$HOME` before the redirect.

`nudge` and `remind` build their `$HOME` paths inside the function, out of the redirect's reach. They
are refused instead.

`winnow safe check` reports leftover `.cozempic*` state in `$HOME` as a violation, because the only
thing that can write it is a cozempic run that did not go through this mode.

### 8.7 The checkpoint

`PreCompact` is the one hook worth keeping (§2), but the vendored `checkpoint` writes
`team-checkpoint.md` into `~/.claude/projects/<slug>/` (`guard.py:389-390`), inside the bind mount. So
`winnow safe checkpoint` composes the same three vendored steps — `load_messages_incremental`,
`extract_team_state`, `write_team_checkpoint` — with a directory that is not.

`write_team_checkpoint` falls back to `get_claude_dir()/team-checkpoint.md` when the directory it is
handed does not exist (`team.py:1339-1344`), and that fallback is the bind-mount write this exists to
avoid, so the target is created and checked first and the returned path is asserted to be inside it.
`read_checkpoint` passes `include_global=False`: the `~/.claude/team-checkpoint.md` fallback holds the
last-written checkpoint of any project, which `cli.py:1014` calls a cross-project read vector.

`data_dir()` refuses a `WINNOW_DATA_DIR` inside the Claude config directory outright.

### 8.8 What was verified, and how

**The suite**: above. 1960 passed, 1 failed, 17 skipped; the one failure is the pre-existing flake and
neither test in that pair imports `src/winnow/`. The pass that rewrote the plugin identity, the hook
lines and the destination re-ran it on the same recipe and measured **1974 passed, 1 failed, 17
skipped** — the 14 extra passes are that pass's own tests, and the one failure is the same flake,
`test_final_pidfile_contains_only_winning_pid` this time. It removed the 23 `cozempic_*` files the run
left in the shared `/tmp`, restored `~/.claude/settings.json` to its pre-run bytes and deleted the four
`~/.cozempic*` paths the suite writes (§7's "Running the suite installs the tool"); `winnow safe check`
is clean either side.

**The new logic, both directions.** `tests/test_orchestrator_safe.py` is 91 `unittest.TestCase` tests
that run under `PYTHONPATH=src python3 -m unittest tests.test_orchestrator_safe` with no pytest, and
under pytest unchanged. Twenty targeted mutations were applied to
`src/winnow/orchestrator_safe.py` one at a time — the switch reading a typo as off, the gate ignoring
the live session, the exclusion rebinding instead of mutating in place, `SessionStart` treated as an
event worth keeping, the checkpoint's target directory not created, the redirect dropping the install
sentinel, and fifteen more. **All 20 were caught**, and the suite passed again after each revert. Both
directions are confirmed for every behaviour the tests claim.

The 14 tests the identity, hook-line and destination pass added were mutation-checked the same way,
with ten mutations one at a time: the checkpoint going quiet when there is no team state, `post-compact`
going quiet in either direction, the bound cut to 100 characters so a refusal reason is truncated, the
line no longer collapsed to one line, the plugin taking its old name back, the manifest copied and
overwritten again instead of written from scratch, the provenance dropped, the upstream version
hardcoded, and the destination moved back under a dot-directory. **All 10 were caught**, and the file
passed again after each revert.

**End to end.** Every action the mode offers was run between two full filesystem snapshots of `$HOME`
(including the `~/.claude` bind mount) and `/tmp`, with the process table captured either side. All
eleven refusals exited 3 with a reason naming the section; `list`, `doctor`, `digest show`,
`guard-watchdog`, `diagnose` and a dry-run `treat` exited 0; `treat --execute` was refused because a
live Claude process (pid 6977) was above it; the mode off, everything that acts exited 3.

Between the two snapshots, **nothing under `/home/node` changed at all** — not `~/.claude`, not
`~/.cozempic*`. That is a claim about the mode's actions and not about the container: running the
vendored *test suite* does change both, which is §7's "Running the suite installs the tool" and is
the reason the end-to-end pass is bracketed by its own snapshots rather than compared against the
state at the start of the day. Everything that changed was winnow's own data directory, the scratch directory holding
the snapshots, and `/tmp/claude-1000/.../tasks/*.output`, which is Claude Code's own scratch. A
control pair of snapshots with winnow doing nothing changes the same task-output file and the session
transcript, which is how those two were attributed rather than assumed. The process table differed
only by the snapshot's own transient `sh`/`ps`/`sort`; the `claude` process the session runs inside
(pid 6977, started 13:25:52) was alive before and after, and no guard pidfile appeared in `/tmp`.

`~/.claude` being a bind mount was confirmed directly rather than taken from `plugins.ts`:
`findmnt -T /home/node/.claude` reports source
`/run/host_mark/Users[/hendrikkuehnel/.claude]`, and it is a different device from `/home/node`
(44 against 63), which is also why a naive `find -xdev` snapshot misses it.

### 8.9 What is still unverified

Named individually, with what would settle each.

- **The mode has never run inside a real orchestrated cycle.** Everything above was run by hand in this container. What is untested is the composition: `--plugin-dir <winnow's directory>` passed by `buildArgs`, the `PreCompact` hook firing during the harness's own autocompaction, and the checkpoint surviving into the next cycle. Settled by one run of the harness against this branch with `WINNOW_ORCHESTRATOR=1` in the child environment, then reading the cycle's stderr for winnow lines. Two things that stood in the way of that run are now gone (§8.5): the directory can be generated somewhere the app's plugin scan will find it, so it can be enabled from the list rather than only passed by hand, and every hook action says one line whatever happens, so "reading the cycle's stderr for winnow lines" distinguishes a loaded plugin with nothing to do from a plugin that never loaded. Neither has been observed in a real cycle, which is why this bullet stays here.
- **No network call was proved absent.** `COZEMPIC_NO_TELEMETRY=1` and `COZEMPIC_NO_AUTO_UPDATE=1` are in the overlay and `self-update` is refused, but nothing here observed the syscalls. No packet-level tool is available in this container. Settled by `strace -f -e trace=connect` or an egress-denied network namespace around the same end-to-end run.
- **The guard was never enabled**, deliberately: §6 forbids it. So "the daemon would have killed this session" is read from `guard.py:2377-2400` and from the harness's exit handling, not observed. Settled only in a throwaway container with nothing else in it, and it is not worth doing.
- **The `/tmp` flake was not root-caused.** The alternation between the two tests is new evidence for the shared-`/tmp` theory and still not proof. Settled by running that one class with `TMPDIR` pointed somewhere private, which the guard's hardcoded path (`guard.py:2636-2650`) currently prevents.
- **`prescriptions_without` is not exercised through a real prune.** The exclusion is asserted on the dict, and a dry-run `treat` was run, but no `--execute` prune has been run under the mode, because a live session refuses one and that is the correct behaviour. Settled between cycles, where the mode is designed to allow it.
