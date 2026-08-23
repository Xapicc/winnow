# Running this under UsageFoundry

Written 2026-08-23. UsageFoundry is the orchestrator at `/workspace/UsageFoundry`: it spawns
`claude -p` in a loop, owns the session identity, sets the compaction point, enforces the budget,
and bills every run from the transcripts. This repository contains a tool that also does four of
those five things. This document is the integration spec, and its scope is the overlap.

**It is a specification, not a change.** Nothing in `src/cozempic/`, `plugin/`, `npm/` or
`packaging/` was modified to produce it, and `/workspace/UsageFoundry` is read-only here: every
citation into it is a read. The implementation is the next run's job, and this is what it should
read first.

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
${CLAUDE_PLUGIN_ROOT}/servers/cozempic_mcp.py`. Three consequences: it needs `uv`, which is not
installed in this container; it needs network at spawn; and `--with cozempic` **fetches Cozempic from
PyPI**, so `--plugin-dir plugin/` would run a downloaded copy rather than `src/cozempic/`. Anyone
measuring the vendored tree through the plugin would be measuring something else. `fastmcp` is
therefore a real dependency of the plugin, though not of the runtime
([COZEMPIC.md](COZEMPIC.md) §1.1).

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

---

## 4. Off by default under an orchestrator

Everything here is off unless an operator turns it on for a named reason. The last column says what
happens if it is left on, in one line, so the list can be argued with item by item.

| Feature | Switch | If left on |
| --- | --- | --- |
| Global init into `~/.claude/settings.json` | `COZEMPIC_NO_GLOBAL_INIT=1` (`cli.py:2076`) | Writes hooks onto the operator's host machine, silently, because headless skips the prompt. §1.7 |
| Project init into `./.claude/settings.json` | `COZEMPIC_NO_AUTO_INIT=1` (`cli.py:2269`) | A settings file appears in the agent's worktree. Inert today: this repository has no `.claude/`, which is its own bail-out |
| PyPI self-upgrade, both paths | `COZEMPIC_NO_AUTO_UPDATE=1`, or `COZEMPIC_PIN=1.8.39` to hold a reviewed version | The measured artefact changes between runs and no result can name its version. §1.8 |
| Telemetry counters | `COZEMPIC_NO_TELEMETRY=1` (`helpers.py:236`) | Three outbound requests per prune to a third party's Cloudflare Worker. Counters only, but SPEC §10 says no network |
| Receipts into `~/.cozempic` | `COZEMPIC_NO_RECEIPTS=1` | Container-local, so this is hygiene rather than a collision. On by default in the tool's own test suite for the same reason |
| **The guard daemon** | **no environment variable exists.** The only way off is not to install the hook: exclude `SessionStart` from any registered `--plugin-dir`, and keep `COZEMPIC_NO_GLOBAL_INIT=1` so nothing wires it globally | The session can be `SIGKILL`ed mid-cycle, the harness files it as exit -1, and in this container it is not resumed. §1.1, §1.2, §1.3 |
| **`metadata-strip`** | **no environment variable exists**, and it is gentle-tier so every prescription includes it. Requires a config-file strategy exclusion, or a patch | Spend accounting silently under-reports, killed cycles bill as zero, and the budget ceiling rises to match. §1.4 |

The two bold rows are the finding of this section: **the two features with the largest blast radius
are the two with no off switch.** Both need a mechanism that does not exist yet, which makes them the
first implementation task rather than a configuration note. The tool has 28 `COZEMPIC_*` variables
and none of them is `COZEMPIC_NO_GUARD`.

Turning that around: adding `COZEMPIC_NO_GUARD` and a strategy-exclusion list is a small,
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

Short, because the temptations are specific.

Do not patch `src/cozempic/` to fix §1.4 or the guard. [DECISIONS.md](DECISIONS.md) §0 makes that
tree read-only, and a local edit to a self-updating package is the worst of both. New code goes in
`src/winnow/`; changes wanted in the tool go upstream.

Do not modify `/workspace/UsageFoundry`. §1.4's harness-side suggestion is a proposal, and the place
for it is a document beside `proposals/ContextControl/`, written and left for the operator.

Do not enable the guard to see what happens. §1.2's exposure is a live editor process and §1.3's
consequence is a run recorded as an unexplained crash. If it must be observed, it should be observed
against a throwaway session in a container with nothing else in it.

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
