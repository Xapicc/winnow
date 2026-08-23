"""Orchestrator-safe mode — what this repository may do when the process that
owns the Claude Code session is an unattended harness rather than a person.

One switch turns the whole mode on: ``WINNOW_ORCHESTRATOR=1`` in the
environment. There is no second mechanism and no per-feature flag, because the
features this constrains fail silently and independently, and a mode assembled
from seven switches is a mode nobody can confirm is on. `check()` answers that
question in one call.

The mode holds six invariants. Each one is here because of something read in
the harness's own source; the citations are `docs/USAGEFOUNDRY.md`, which
carries the evidence tables.

1. **It never terminates the session it is running inside.** The guard daemon
   is never started (its ``SessionStart`` hook is not in the plugin directory
   this module materialises) and ``winnow guard`` / ``winnow reload`` are
   refused. There is no environment variable that turns the daemon off
   (USAGEFOUNDRY §4), so the mechanism has to be non-installation rather than
   restraint, and the harness's own ``--disallowedTools`` cannot help: the kill
   is an ``os.kill`` inside a detached daemon, not a tool call (§1.2).
2. **It never resumes a session.** Session identity and ``--resume`` belong to
   the harness, which adopts the id off the stream, persists it and re-passes it
   (§1.3). ``winnow reload`` spawns a watcher that runs ``claude --resume``;
   it is refused for that reason as much as for the kill.
3. **No auto-update and no PyPI check while a run is in flight.** Both paths
   off, not overridable-off (§1.8).
4. **Nothing is written into ``~/.claude``.** That directory is a bind mount
   onto the operator's machine (§1.7), and the harness deliberately never writes
   there. Team checkpoints go to winnow's own data directory instead.
5. **It does not compete with the harness's context and cost controls.** The
   harness's ``--autocompact`` is authoritative: the tool may not act to prevent
   compaction, may not act because of it, and may not act while a session is
   live (USAGEFOUNDRY §2). A prune is refused while a Claude ancestor process
   exists.
6. **Nothing is written into the model's memory to be recalled later.**
   ``winnow digest inject`` writes into ``~/.claude/projects/<slug>/memory/``
   and edits that directory's ``MEMORY.md``, which is loaded into every
   session's context (§1.7). It is refused. Retrieval is by lookup, not recall
   (SPEC §7).

Nothing in ``src/winnow/legacy/`` is edited to achieve any of this. It is
winnow's own code now (DECISIONS §0) and may be changed, but this mode is the
one place where not changing it is the point: every invariant above is held
from outside, so it holds for a tree nobody has audited line by line. Where the
inherited tree offers no switch, this module supplies the mechanism from
outside: an argv gate, an in-process prescription exclusion, and a filtered
plugin directory.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# ── The one switch ────────────────────────────────────────────────────────────

ENV_SWITCH = "WINNOW_ORCHESTRATOR"

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSEY = frozenset({"", "0", "false", "no", "off"})


def is_enabled(env: dict[str, str] | None = None) -> bool:
    """Is orchestrator-safe mode on?

    Raises on an unrecognised value rather than reading it as off. This switch
    decides whether a daemon that can ``SIGKILL`` the session may be started, so
    a typo must stop the invocation, not silently disarm the mode.
    """
    raw = (os.environ if env is None else env).get(ENV_SWITCH, "")
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSEY:
        return False
    accepted = sorted((_TRUTHY | _FALSEY) - {""})
    raise ValueError(
        f"{ENV_SWITCH}={raw!r} is not a boolean. Expected one of "
        f"{accepted}, or unset."
    )


# ── The environment the mode runs the vendored tree under ────────────────────

# What this tree was inherited from, and at which release. Provenance only: it
# is what `derived_from` in the generated plugin manifest records. UPSTREAM_VERSION
# used to be the value this mode forced into WINNOW_PIN, to stop an upgrade moving
# the measured artefact mid-cycle; the upgrade path is gone, so the pin is too
# (FORK.md §5.1). All three mirror NOTICE, which is the record, and a test fails if
# they drift from it.
UPSTREAM_NAME = "cozempic"
UPSTREAM_VERSION = "1.8.39"
UPSTREAM_LICENSE = "MIT"

_SAFE_ENV_SPEC: tuple[tuple[str, str, str], ...] = (
    (
        "WINNOW_NO_GLOBAL_INIT",
        "1",
        "cli.py:2076 — without it a single invocation writes hooks into the "
        "bind-mounted ~/.claude/settings.json, and headless skips the "
        "confirmation that would have stopped it. USAGEFOUNDRY §1.7",
    ),
    (
        "WINNOW_NO_AUTO_INIT",
        "1",
        "cli.py:2269 — keeps a settings.json out of the agent's worktree. "
        "USAGEFOUNDRY §4",
    ),
    (
        "WINNOW_NO_RECEIPTS",
        "1",
        "receipts.py:34 — container-local, so hygiene rather than a "
        "collision. USAGEFOUNDRY §4",
    ),
    (
        "WINNOW_NUDGE_OFF",
        "1",
        "cli.py:1429 — the Stop-hook nudge writes "
        "~/.claude/winnow-metrics/nudge-state.json. USAGEFOUNDRY §1.7",
    ),
    (
        "WINNOW_INTERACTIVE",
        "on",
        "guard.py:1410 — narrows, and does not close, the kill path of a "
        "daemon started by something other than this mode: an interactive "
        "guard defers mid-turn instead of reloading. Auto-detection returns "
        "headless under `claude -p`, so the deferral only fires if it is "
        "forced. USAGEFOUNDRY §1.1",
    ),
    (
        "WINNOW_FORCE_RELOAD_PCT",
        "0",
        "guard.py:1479 — 0 disables the mid-turn force line that overrides "
        "the deferral above. Same narrowing, same caveat: the closure is that "
        "the daemon is never started",
    ),
)

SAFE_ENV: dict[str, str] = {name: value for name, value, _ in _SAFE_ENV_SPEC}
SAFE_ENV_REASONS: dict[str, str] = {name: why for name, _, why in _SAFE_ENV_SPEC}


def safe_environment(env: dict[str, str] | None = None) -> dict[str, str]:
    """`env` with the overlay applied. The overlay wins; nothing is removed."""
    base = dict(os.environ if env is None else env)
    base.update(SAFE_ENV)
    return base


def apply_safe_environment() -> dict[str, str]:
    """Put the overlay into this process's environment. Returns what it set."""
    os.environ.update(SAFE_ENV)
    return dict(SAFE_ENV)


# ── Winnow's own data directory ──────────────────────────────────────────────

DATA_DIR_ENV = "WINNOW_DATA_DIR"


def claude_config_dir(env: dict[str, str] | None = None) -> Path:
    """Where the bind mount is. Mirrors winnow's session.get_claude_dir()."""
    environ = os.environ if env is None else env
    configured = environ.get("CLAUDE_CONFIG_DIR")
    if configured:
        return Path(configured)
    return Path.home() / ".claude"


def data_dir(env: dict[str, str] | None = None) -> Path:
    """Winnow's own state directory. Never inside the Claude config directory.

    Container-local by default: only /home/node/.claude, /home/node/go and
    /home/node/.local/share/gh are bind mounts (USAGEFOUNDRY §1.7), so a
    directory under $HOME crosses nothing. Since the rename this is also where
    the inherited tree's own config and receipts go (FORK.md §6.1) — one
    program, one state directory — which is why `_check_home_state` excludes it.
    """
    environ = os.environ if env is None else env
    configured = environ.get(DATA_DIR_ENV)
    path = Path(configured).expanduser() if configured else Path.home() / ".winnow"
    resolved = path.resolve()
    claude = claude_config_dir(env).resolve()
    if resolved == claude or claude in resolved.parents:
        raise ValueError(
            f"{DATA_DIR_ENV}={path} is inside the Claude config directory "
            f"({claude}), which is a bind mount onto the operator's machine. "
            "Invariant 4 forbids writing there."
        )
    return resolved


# ── The argv gate ────────────────────────────────────────────────────────────

# A frozen mirror of the inherited subcommands winnow's argparse parser accepts.
# Frozen rather than imported so that the policy does not depend on importing
# the CLI to make a decision, and so that a new subcommand fails a test here
# instead of silently defaulting to allowed.
#
# Mirrors the parser, not cli._SUBCOMMANDS: the two disagree, and the parser is
# the set that can actually be invoked. `nudge` is in the parser and not in
# _SUBCOMMANDS, so a gate built on that constant would not see the one command
# that writes into ~/.claude/winnow-metrics/.
#
# `safe` is deliberately absent. It is winnow's own group and is dispatched by
# winnow.cli before the inherited main() runs, so it never arrives here as an
# argv to classify.
LEGACY_SUBCOMMANDS = frozenset({
    "list", "current", "diagnose", "treat", "strategy", "reload",
    "team", "guard", "init", "doctor", "formulary",
    "completions", "digest", "remind", "guard-watchdog",
    "dashboard", "uninstall", "nudge",
})

# Refused whatever the arguments, keyed by subcommand.
_REFUSED_SUBCOMMANDS: dict[str, str] = {
    "guard": (
        "the daemon SIGTERMs then SIGKILLs the Claude process holding this "
        "session (guard.py:2377-2400), the harness records that as "
        "'exited with code -1' with nothing pointing at the guard, and in this "
        "container the resume is best-effort and does not fire. "
        "USAGEFOUNDRY §1.1-§1.3"
    ),
    "reload": (
        "prunes, then spawns a watcher that runs `claude --resume` "
        "(cli.py:927-931). Session identity and --resume belong to the "
        "harness, which persists the id and re-passes it. USAGEFOUNDRY §1.3"
    ),
    "init": (
        "writes hooks into a settings.json — ~/.claude/settings.json with "
        "--global, the worktree's without. USAGEFOUNDRY §1.7"
    ),
    "uninstall": (
        "mutates a settings.json this mode does not own, in the same "
        "bind-mounted directory. USAGEFOUNDRY §1.7"
    ),
    # The two commands that build a home-directory path inside the function
    # rather than at module level, so `redirect_home_writes` cannot reach them.
    "nudge": (
        "writes ~/.claude/winnow-metrics/nudge-state.json (cli.py:1482), "
        "inside the bind mount. It is the Stop hook's command and this mode "
        "does not install the Stop hook. USAGEFOUNDRY §1.7"
    ),
    "remind": (
        "writes ~/.winnow_remind_counter (cli.py:1567) to decide when to "
        "ask an interactive user to run init. There is no interactive user "
        "and init is refused. USAGEFOUNDRY §1.7"
    ),
}

# Refused only in a particular shape: (subcommand, token that must be present).
_REFUSED_ARGV: tuple[tuple[str, str, str], ...] = (
    (
        "guard-watchdog",
        "--fix",
        "sends SIGTERM to a running daemon (cli.py:1129). Report-only without "
        "--fix, which is allowed",
    ),
    (
        "digest",
        "inject",
        "writes winnow_digest.md into ~/.claude/projects/<slug>/memory/ and "
        "edits that directory's MEMORY.md, which is loaded into every "
        "session's context (digest.py:954-996). USAGEFOUNDRY §1.7"
    ),
    # Keyed on the group rather than the subcommand because `team` also carries
    # `post-compact`, which only reads. Before the fork this was a whole-command
    # refusal on `checkpoint`; the command moved under `team` (docs/FORK.md
    # §2.1) and the refusal has to move with it or invariant 4 opens silently.
    (
        "team",
        "checkpoint",
        "writes team-checkpoint.md into ~/.claude/projects/<slug>/ "
        "(guard.py:389-390). Use `winnow safe checkpoint`, which writes the "
        "same file into winnow's data directory. USAGEFOUNDRY §1.7"
    ),
)

# Refused only while a session is live, because they rewrite a transcript.
_MUTATING_ARGV: tuple[tuple[str, str], ...] = (
    ("treat", "--execute"),
    ("strategy", "--execute"),
    ("digest", "update"),
    ("digest", "clear"),
    ("digest", "flush"),
    ("digest", "recover"),
)

_LIVE_SESSION_REASON = (
    "a live Claude process (pid {pid}) holds a session in this process tree, "
    "and the harness's autocompaction is authoritative: the tool may not act "
    "to prevent compaction, may not act because of it, and may not act while "
    "a session is live. Prune between cycles. USAGEFOUNDRY §2"
)


def subcommand_of(argv: list[str]) -> str | None:
    """The inherited subcommand in `argv`, by the same rule the CLI uses.

    cli.py:1945 takes the first token that is a known subcommand, so a value
    that happens to read like one (`--protect-pattern init`) is only mistaken
    for the subcommand if it precedes the real one, which argparse would reject
    anyway.
    """
    for token in argv:
        if token in LEGACY_SUBCOMMANDS:
            return token
    return None


def live_claude_pid() -> int | None:
    """The pid of a Claude Code process above this one, or None.

    Delegates to the vendored walk (session.py:300), which matches `comm`
    against "node" and "claude" for ten generations. In this container the tree
    is tini → next-server (v → claude → bash, and "next-server (v" matches
    neither string, so the walk stops at the session's own process
    (USAGEFOUNDRY §1.2).
    """
    from winnow.legacy.session import find_claude_pid

    return find_claude_pid()


def refusal_for(argv: list[str], *, live_pid: int | None) -> str | None:
    """Why this mode will not run `argv`, or None if it will.

    `live_pid` is the caller's answer to "is a Claude session live in this
    process tree" — passed in rather than probed here so the gate is testable
    without a process tree to arrange.
    """
    subcommand = subcommand_of(argv)
    if subcommand is None:
        return None

    refused = _REFUSED_SUBCOMMANDS.get(subcommand)
    if refused:
        return f"`winnow {subcommand}` is refused under orchestrator-safe mode: {refused}."

    for name, token, why in _REFUSED_ARGV:
        if subcommand == name and token in argv:
            return (
                f"`winnow {name} {token}` is refused under orchestrator-safe "
                f"mode: {why}."
            )

    if live_pid is None:
        return None
    for name, token in _MUTATING_ARGV:
        if subcommand == name and token in argv:
            return (
                f"`winnow {name} {token}` is refused right now: "
                + _LIVE_SESSION_REASON.format(pid=live_pid)
                + "."
            )
    return None


# ── The prescription exclusion ───────────────────────────────────────────────

EXCLUDED_STRATEGIES = ("metadata-strip",)

EXCLUSION_REASON = (
    "metadata-strip deletes `usage`, `costUSD`, `duration` and `apiDuration` "
    "(strategies/gentle.py:237-241). The harness bills every run by scanning "
    "those fields and drops a record that has none without a warning "
    "(transcripts.ts:335-336); a killed cycle then reconciles to zero, and "
    "because the remaining budget is the ceiling minus observed spend, "
    "under-observed spend raises the ceiling handed to the next cycle. "
    "USAGEFOUNDRY §1.4"
)


def prescriptions_without(
    prescriptions: dict[str, list[str]],
    excluded: tuple[str, ...] = EXCLUDED_STRATEGIES,
) -> dict[str, list[str]]:
    """A copy of `prescriptions` with `excluded` strategies removed."""
    return {
        name: [s for s in strategies if s not in excluded]
        for name, strategies in prescriptions.items()
    }


def apply_strategy_exclusions(
    prescriptions: dict[str, list[str]] | None = None,
    excluded: tuple[str, ...] = EXCLUDED_STRATEGIES,
) -> dict[str, list[str]]:
    """Remove `excluded` from the vendored prescriptions. Returns what it took.

    Mutates the lists in place: cli.py:24 and guard.py:203 bind
    `registry.PRESCRIPTIONS` at import time, so rebinding the module attribute
    would leave both holding the original dict and the exclusion would apply to
    nothing.
    """
    if prescriptions is None:
        from winnow.legacy.registry import PRESCRIPTIONS

        prescriptions = PRESCRIPTIONS

    removed: dict[str, list[str]] = {}
    for name, strategies in prescriptions.items():
        taken = [s for s in strategies if s in excluded]
        if not taken:
            continue
        strategies[:] = [s for s in strategies if s not in excluded]
        removed[name] = taken
    return removed


# ── The plugin directory ─────────────────────────────────────────────────────

# `--plugin-dir` is the whole of the integration path: the harness passes it on
# every spawn and never writes into ~/.claude (USAGEFOUNDRY §3). What it does
# not do is make the plugin's contents safe, which is what this section is for.

DROPPED_HOOK_EVENTS: dict[str, str] = {
    "SessionStart": (
        "upgrades this package from PyPI and then spawns the guard daemon. "
        "Both "
        "are invariants 1 and 3, and the daemon has no off switch other than "
        "this one. USAGEFOUNDRY §1.8, §4"
    ),
    "PostToolUse": (
        "`winnow team checkpoint` writes into ~/.claude/projects/<slug>/ and "
        "`winnow remind` reinforces digest rules. Invariants 4 and 6"
    ),
    "Stop": (
        "checkpoint, `digest flush` and `nudge` — the first writes into "
        "~/.claude, the last writes ~/.claude/winnow-metrics/. Invariant 4"
    ),
}

KEPT_HOOK_EVENTS = ("PreCompact", "PostCompact")

KEPT_HOOK_REASON = (
    "PreCompact writes a checkpoint before the summariser runs, which is "
    "reversible-loss insurance against an irreversible operation, and "
    "PostCompact reads it back. Neither changes the transcript the model is "
    "holding, so both are compatible with the harness owning compaction "
    "(USAGEFOUNDRY §2). The commands are `winnow safe`'s, not `winnow "
    "team`'s, because `winnow team checkpoint` writes into ~/.claude"
)

DROPPED_PLUGIN_PATHS: dict[str, str] = {
    ".mcp.json": (
        "the server it starts now runs this tree and fetches no package at "
        "spawn, so USAGEFOUNDRY §1.9's PyPI-copy objection no longer applies. "
        "Dropped for three that still do: `treat_session(execute=True)` "
        "rewrites the live transcript, an MCP tool call never passes the argv "
        "gate that refuses `treat`, and the server is a separate process that "
        "gets neither the environment overlay nor `redirect_home_writes()`, so "
        "its session sidecar lands in the bind mount. Invariants 4 and 5, "
        "USAGEFOUNDRY §8.5"
    ),
    "servers": "only reachable from the .mcp.json above",
    "skills": (
        "every skill declares `allowed-tools: Bash(winnow *)` and calls the "
        "binary directly, which bypasses this mode's gate and its environment "
        "overlay. Two of them (guard, reload) instruct the agent to run "
        "exactly the refused commands"
    ),
    "README.md": "describes the plugin that was not materialised here",
}

_SAFE_PLUGIN_NAME = "winnow"

# One line, because UsageFoundry's plugin list shows `name` and `description`
# straight out of this manifest (plugins.ts:107-114) and that is the only
# sentence an operator reads before enabling the directory. It says what the
# directory holds and not what winnow is for: there is no pruning here.
_SAFE_PLUGIN_DESCRIPTION = (
    "The PreCompact and PostCompact hooks of winnow's orchestrator-safe mode: "
    "before the harness compacts, the session's agent-team state is written "
    "into winnow's own data directory; after, it is read back. The directory "
    "holds nothing else: no other hooks, no MCP server, no skills, and it "
    "changes no transcript."
)

# No `version` key. Winnow has not versioned itself, and upstream's 1.8.39
# names a release of a different program; an invented number would be the same
# false claim in a different font. The version that *is* known — the vendored
# tree's — is recorded as provenance instead.
_UPSTREAM_COPYRIGHT = "2026 Ruya AI"

# The directory has to sit inside one of UsageFoundry's workspace mounts to be
# discoverable at all: `discoverPlugins` walks the mounts and nothing else
# (plugins.ts:244-315), so a directory under $HOME can be built and never
# enabled. The walk skips any path component starting with `.` and the names in
# plugins.ts:48-58 (node_modules, .git, .uf-worktrees, .next, dist, build,
# vendor, target, __pycache__), which is why this is a plain name beside the
# vendored `plugin/` rather than something tidier like `.winnow/plugin`.
PLUGIN_DEST_DIRNAME = "winnow-plugin"


def safe_hooks_manifest(winnow_command: str) -> dict:
    """The hooks.json for the materialised directory.

    `winnow_command` is the prefix that runs this package — the plugin
    directory is not a Python package and nothing here is pip-installed, so the
    interpreter and the import path are baked in, as winnow's own installer
    bakes its path (init.py:413).

    The switch is baked in rather than inherited: this directory only exists
    because the mode materialised it, so a hook inside it is running under the
    mode by construction, and a hook that silently did nothing because compose
    forgot a variable is the failure the harness names at
    orchestrator.ts:5051-5057.

    `|| true` for the reason the vendored hooks have it: a non-zero exit from a
    hook is fed back to the model, and a checkpoint that found no team state is
    not something to tell the model about.
    """
    prefix = f"{ENV_SWITCH}=1 {winnow_command}"
    return {
        "hooks": {
            "PreCompact": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{prefix} safe checkpoint || true",
                        }
                    ],
                }
            ],
            "PostCompact": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{prefix} safe post-compact || true",
                        }
                    ],
                }
            ],
        }
    }


def winnow_command(python: str | None = None, source_root: Path | None = None) -> str:
    """The shell prefix that runs this package from an uninstalled checkout."""
    interpreter = python or sys.executable or "python3"
    root = source_root or Path(__file__).resolve().parent.parent
    return f"PYTHONPATH={root} {interpreter} -m winnow"


def upstream_provenance() -> dict:
    """What the materialised directory was derived from.

    The generated directory carries no upstream bytes — both JSON files in it
    are written here — so MIT's notice requirement is not triggered by a copy.
    The derivation is still real: the classification of which hook events are
    safe was read off upstream's manifest, and the checkpoint calls into the
    inherited tree. So the provenance is recorded rather than dropped, next to
    what was dropped and why, and the notice it points at is the repository's
    own ``LICENSE`` and ``NOTICE``.

    These four values used to be read out of ``plugin/.claude-plugin/plugin.json``,
    on the grounds that a vendored tree moved to another release should say so
    here without an edit. That stopped being true when the fork rewrote that
    manifest as winnow's own (FORK.md §4, USAGEFOUNDRY §8.5): reading it now
    would record winnow as its own upstream. There is no vendored tree to move
    any more, so the provenance is a fixed fact about the import at 210b026 and
    lives beside the ``NOTICE`` that states it.
    """
    return {
        "name": UPSTREAM_NAME,
        "version": UPSTREAM_VERSION,
        "license": UPSTREAM_LICENSE,
        "copyright": _UPSTREAM_COPYRIGHT,
        "notice": (
            "Derived from the named upstream under the MIT licence, whose "
            "terms and copyright are at the root of the winnow repository as "
            "LICENSE and NOTICE (DECISIONS.md §0). Neither file in this "
            "directory is a copy of upstream's: both are generated by winnow."
        ),
    }


def dropped_hook_events(manifest: dict) -> list[str]:
    """Which of a plugin manifest's hook events this mode does not carry over.

    Every event is dropped except `KEPT_HOOK_EVENTS`, and those two are
    re-declared with winnow's own commands rather than copied, so an unclassified
    event upstream adds is dropped rather than run.
    """
    events = manifest.get("hooks", {})
    if not isinstance(events, dict):
        raise ValueError(f"hooks manifest has no 'hooks' object: {manifest!r}")
    return [name for name in events if name not in KEPT_HOOK_EVENTS]


def materialise_plugin_dir(
    source: Path,
    dest: Path,
    *,
    command: str | None = None,
) -> dict:
    """Write an orchestrator-safe copy of `source` to `dest`. Returns a report.

    `dest` is replaced if it exists. The output is deterministic: same source
    and same command in, byte-identical directory out (SPEC §10).
    """
    source = Path(source)
    dest = Path(dest)
    manifest_path = source / "hooks" / "hooks.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no hooks manifest at {manifest_path}")
    source_hooks = json.loads(manifest_path.read_text(encoding="utf-8"))
    dropped_events = dropped_hook_events(source_hooks)

    plugin_json_path = source / ".claude-plugin" / "plugin.json"
    if not plugin_json_path.is_file():
        raise FileNotFoundError(f"no plugin manifest at {plugin_json_path}")
    # The source manifest is required but not read: a directory without one is
    # not a plugin directory, and generating from it would produce something the
    # app cannot discover. Its *contents* are deliberately ignored — written from
    # scratch rather than copied and overwritten, for the reason the hooks
    # manifest is: a field the source adds is then absent by default instead of
    # by classification. It also settles the identity question — a copy carried
    # the source's description, version, author and repository under winnow's
    # name, and UsageFoundry displayed them (plugins.ts:107-114).
    plugin = {
        "name": _SAFE_PLUGIN_NAME,
        "description": _SAFE_PLUGIN_DESCRIPTION,
    }
    provenance = upstream_provenance()

    if dest.exists():
        shutil.rmtree(dest)
    (dest / ".claude-plugin").mkdir(parents=True)
    (dest / "hooks").mkdir()

    _write_json(dest / ".claude-plugin" / "plugin.json", plugin)
    _write_json(
        dest / "hooks" / "hooks.json",
        safe_hooks_manifest(command or winnow_command()),
    )

    dropped_paths = sorted(
        name for name in DROPPED_PLUGIN_PATHS if (source / name).exists()
    )
    report = {
        "source": str(source),
        "dest": str(dest),
        "plugin_name": _SAFE_PLUGIN_NAME,
        "plugin_description": _SAFE_PLUGIN_DESCRIPTION,
        "derived_from": provenance,
        "kept_hook_events": list(KEPT_HOOK_EVENTS),
        "dropped_hook_events": dropped_events,
        "dropped_paths": dropped_paths,
        "reasons": {
            **{name: DROPPED_HOOK_EVENTS.get(name, "not classified by this mode")
               for name in dropped_events},
            **{name: DROPPED_PLUGIN_PATHS[name] for name in dropped_paths},
        },
    }
    # `dest` is left out of the written copy: a file that records its own
    # location is both redundant and the one field that would make two
    # directories generated from the same source differ byte for byte.
    _write_json(
        dest / "winnow-safe-manifest.json",
        {name: value for name, value in report.items() if name != "dest"},
    )
    return report


def _write_json(path: Path, payload: dict) -> None:
    """Sorted keys and a trailing newline, so the output is byte-stable."""
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


# ── The redirected team checkpoint ───────────────────────────────────────────


def write_checkpoint(session_path: Path, target_dir: Path) -> Path | None:
    """Write the team checkpoint for `session_path` into `target_dir`.

    The vendored writer takes a directory (team.py:1334) but the vendored
    caller always hands it `session_path.parent`, which is inside the bind
    mount (guard.py:389-390). This composes the same three vendored steps with
    a directory that is not.

    Returns the path written, or None when there is no team state to write.
    """
    from winnow.legacy.session import load_messages_incremental
    from winnow.legacy.team import extract_team_state, write_team_checkpoint

    # Created first and checked, not assumed: write_team_checkpoint falls back
    # to get_claude_dir()/team-checkpoint.md when the directory it is given does
    # not exist, and that fallback is the bind-mount write this exists to avoid.
    target_dir.mkdir(parents=True, exist_ok=True)
    if not target_dir.is_dir():
        raise NotADirectoryError(f"checkpoint target is not a directory: {target_dir}")

    state = extract_team_state(load_messages_incremental(Path(session_path)))
    if state.is_empty():
        return None

    written = write_team_checkpoint(state, target_dir)
    if target_dir.resolve() not in Path(written).resolve().parents:
        raise RuntimeError(
            f"checkpoint went to {written}, outside {target_dir}. Refusing to "
            "continue: invariant 4 forbids a write outside winnow's own data "
            "directory."
        )
    return written


def read_checkpoint(target_dir: Path) -> str | None:
    """Read back what write_checkpoint wrote, or None.

    include_global=False: the ~/.claude/team-checkpoint.md fallback holds the
    last-written checkpoint of any project, which cli.py:1014 calls a
    cross-project read vector, and it is in the bind mount besides.
    """
    from winnow.legacy.team import read_team_checkpoint

    return read_team_checkpoint(Path(target_dir), include_global=False)


# ── The report ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    """One thing `check` looked at."""

    name: str
    ok: bool
    detail: str


def check(env: dict[str, str] | None = None) -> list[Finding]:
    """Everything about the mode that can be established by reading.

    Writes nothing and probes no process it does not own. A False `ok` is a
    statement that an invariant does not hold here, not a suggestion.
    """
    environ = dict(os.environ if env is None else env)
    findings: list[Finding] = []

    try:
        enabled = is_enabled(environ)
    except ValueError as exc:
        return [Finding("mode", False, str(exc))]
    findings.append(
        Finding(
            "mode",
            enabled,
            f"{ENV_SWITCH}={environ.get(ENV_SWITCH, '<unset>')!r}"
            + ("" if enabled else " — orchestrator-safe mode is off"),
        )
    )

    findings.extend(_check_env(environ))

    findings.append(_check_guard_daemons())
    findings.append(_check_global_hooks(environ))
    findings.append(_check_digest_memories(environ))
    findings.append(_check_strategy_exclusion())
    findings.append(_check_home_state())
    findings.append(_check_live_session())
    return findings


def _check_env(env: dict[str, str]) -> list[Finding]:
    """One finding per overlay variable.

    Unset is not a violation: `safe_environment` supplies the whole overlay to
    every `winnow safe run`, and that is the only path this mode opens to the
    vendored tree. What a set value tells you is whether a winnow invocation
    that bypassed winnow entirely would also be covered.

    A conflicting value is a violation, because somebody configured something
    this mode is about to override and will not otherwise be told.
    """
    findings = []
    for name, expected in SAFE_ENV.items():
        actual = env.get(name)
        if actual == expected:
            detail = f"{actual!r}, set in this environment"
        elif actual is None:
            detail = f"unset here; the overlay supplies {expected!r} to every run"
        else:
            detail = (
                f"{actual!r} conflicts with the overlay's {expected!r}, which "
                "wins. Remove it, or the harness is configuring something that "
                "has no effect"
            )
        findings.append(Finding(f"env:{name}", actual is None or actual == expected, detail))
    return findings


def _check_guard_daemons() -> Finding:
    """Is a guard daemon running for any session in this container?

    The pidfile path is hardcoded to /tmp and cannot be redirected
    (guard.py:2636-2650), and /tmp is shared with every other agent here, so
    this sees any of them.
    """
    live: list[str] = []
    stale: list[str] = []
    for pidfile in sorted(Path("/tmp").glob("winnow_guard_*.pid")):
        try:
            pid = int(pidfile.read_text(encoding="utf-8").splitlines()[0].strip())
        except (OSError, ValueError, IndexError):
            stale.append(pidfile.name)
            continue
        try:
            os.kill(pid, 0)
        except OSError:
            stale.append(pidfile.name)
        else:
            live.append(f"{pidfile.name} (pid {pid})")
    if live:
        return Finding(
            "guard-daemon",
            False,
            "a guard daemon is running and can SIGKILL the session it watches: "
            + ", ".join(live),
        )
    detail = "no live guard daemon pidfile in /tmp"
    if stale:
        detail += f"; {len(stale)} stale pidfile(s) ignored"
    return Finding("guard-daemon", True, detail)


def _check_global_hooks(env: dict[str, str] | None) -> Finding:
    """Is anything already wired into the bind-mounted settings.json?"""
    settings = claude_config_dir(env) / "settings.json"
    if not settings.is_file():
        return Finding("global-hooks", True, f"{settings} does not exist")
    try:
        text = settings.read_text(encoding="utf-8")
    except OSError as exc:
        return Finding("global-hooks", False, f"cannot read {settings}: {exc}")
    if "winnow" in text:
        return Finding(
            "global-hooks",
            False,
            f"{settings} names winnow — hooks are wired into the bind mount, "
            "so they run whatever this mode does. `winnow init "
            "--uninstall-global` on the host removes them",
        )
    return Finding("global-hooks", True, f"{settings} does not name winnow")


def _check_digest_memories(env: dict[str, str] | None) -> Finding:
    """Has a digest been written into a project's memory directory?"""
    projects = claude_config_dir(env) / "projects"
    found = sorted(str(p) for p in projects.glob("*/memory/winnow_digest.md"))
    if found:
        return Finding(
            "digest-memory",
            False,
            "a digest is in the operator's memory index, where it is loaded "
            "into every session's context: " + ", ".join(found),
        )
    return Finding("digest-memory", True, f"no winnow_digest.md under {projects}")


def _check_strategy_exclusion() -> Finding:
    """What `winnow safe run` will take out of the vendored prescriptions.

    Not a violation either way: the vendored tree ships metadata-strip in every
    prescription and is not edited, so the finding is a statement of what the
    exclusion will do when the pruner is next run through this mode.
    """
    try:
        from winnow.legacy.registry import PRESCRIPTIONS
    except ImportError as exc:
        return Finding(
            "strategy-exclusion", False, f"cannot import the vendored tree: {exc}"
        )
    carrying = sorted(
        name
        for name, strategies in PRESCRIPTIONS.items()
        if any(s in EXCLUDED_STRATEGIES for s in strategies)
    )
    excluded = ", ".join(EXCLUDED_STRATEGIES)
    if carrying:
        return Finding(
            "strategy-exclusion",
            True,
            f"{excluded} will be removed from {', '.join(carrying)} on every "
            "`winnow safe run`; nothing else may run the pruner under this mode",
        )
    return Finding(
        "strategy-exclusion", True, f"no prescription carries {excluded}"
    )


def _check_home_state(home: Path | None = None) -> Finding:
    """Has the inherited tree left state in $HOME, outside any redirect?

    A violation, and a useful one: these files can only have been written by a
    winnow run that did not go through this mode, so the finding says the
    mode was bypassed rather than that it failed.

    Both prefixes, because an install that predates the rename left state under
    the old one — including the two dotfiles the deleted updater wrote,
    ``~/.cozempic_installed`` and ``~/.cozempic_update_check``, which nothing
    writes any more but which this container may still be holding. ``~/.winnow``
    itself is excluded — since the rename it is `data_dir()`, which is where
    `redirect_home_writes` sends this state on purpose, so finding it is the
    mode working rather than being bypassed.
    """
    root = Path.home() if home is None else Path(home)
    try:
        own_state = data_dir().resolve()
    except ValueError:  # a misconfigured data dir is _check_data_dir's finding
        own_state = None
    found = sorted(
        entry.name
        for entry in root.iterdir()
        if (entry.name.startswith(".winnow") or entry.name.startswith(".cozempic"))
        and entry.resolve() != own_state
    )
    if found:
        return Finding(
            "home-state",
            False,
            "the inherited tree has state in $HOME, so something ran it "
            "outside this mode: " + ", ".join(found),
        )
    return Finding("home-state", True, f"no stray winnow state in {root}")


def _check_live_session() -> Finding:
    """Is a prune allowed at this moment?"""
    try:
        pid = live_claude_pid()
    except Exception as exc:  # the walk shells out to `ps`; a missing ps is not fatal
        return Finding("live-session", False, f"cannot read the process tree: {exc}")
    if pid is None:
        return Finding(
            "live-session", True, "no Claude ancestor process; a prune is between cycles"
        )
    return Finding(
        "live-session",
        True,
        f"a Claude process (pid {pid}) is above this one, so a prune is "
        "refused until it is not. USAGEFOUNDRY §2",
    )


def hook_payload(stdin: str) -> dict:
    """Parse a Claude Code hook payload, or {} if there is not one.

    Hooks are handed JSON on stdin. An empty or unparseable stdin means this was
    run by hand, which is not an error — the caller falls back to detecting the
    session from the working directory.
    """
    text = stdin.strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_session_path(payload: dict, cwd: str | None = None) -> Path | None:
    """The transcript this invocation is about: the hook's, or the current one."""
    transcript = payload.get("transcript_path")
    if isinstance(transcript, str) and transcript:
        return Path(transcript)

    from winnow.legacy.session import find_current_session

    # strict=True refuses the global most-recent fallback, which would checkpoint
    # another project's session (guard.py:367-371 makes the same argument).
    session = find_current_session(cwd or os.getcwd(), strict=True)
    return Path(session["path"]) if session else None


# ── The home-directory state ─────────────────────────────────────────────────

# Where the vendored tree keeps state outside ~/.claude, and where this mode
# keeps it instead. Every entry is a module-level constant computed from
# `Path.home()` at import time and read only through its own module's global, so
# rebinding it here reaches every use. Checked by a test, because a constant
# that a second module imported by value would silently keep the old path.
#
# The reason for redirecting rather than refusing: none of this state is
# dangerous, it is just in the wrong place. A cycle's savings tally belongs to
# the cycle, and $HOME in this container outlives it.
_HOME_WRITE_REDIRECTS: tuple[tuple[str, str, str], ...] = (
    ("winnow.legacy.config", "_CONFIG_FILE_PATH", "winnow/config.json"),
    ("winnow.legacy.digest", "DIGEST_DIR", "winnow"),
    ("winnow.legacy.digest", "DIGEST_FILE", "winnow/behavioral-digest.json"),
    ("winnow.legacy.digest", "DIGEST_MD_FILE", "winnow/behavioral-digest.md"),
    ("winnow.legacy.helpers", "_SAVINGS_FILE", "winnow-savings.json"),
    ("winnow.legacy.cli", "_GLOBAL_INIT_MARKER", "winnow-global-initialized"),
    ("winnow.legacy.init", "_GLOBAL_INIT_MARKER", "winnow-global-initialized"),
    ("winnow.legacy.init", "_REMIND_COUNTER", "winnow-remind-counter"),
)


def home_write_targets(target_dir: Path) -> dict[tuple[str, str], Path]:
    """The redirect table resolved against `target_dir`. Pure."""
    return {
        (module, attribute): Path(target_dir) / relative
        for module, attribute, relative in _HOME_WRITE_REDIRECTS
    }


def redirect_home_writes(target_dir: Path) -> dict[str, Path]:
    """Point the inherited tree's home-directory state at `target_dir`.

    None of the state below has an environment switch in front of it, so
    neither the refusal table nor the overlay can reach it: the only lever is
    the path itself (USAGEFOUNDRY §8.6). This used to be a stronger claim —
    `main()` wrote ~/.cozempic_installed before it parsed argv, one line ahead
    of the only switch that could have stopped it — and that write is gone with
    the updater. The remaining entries are ordinary state in the wrong place.

    Returns the redirects applied, keyed `module.attribute`.
    """
    applied: dict[str, Path] = {}
    for (module_name, attribute), destination in home_write_targets(target_dir).items():
        module = importlib.import_module(module_name)
        if not hasattr(module, attribute):
            raise AttributeError(
                f"{module_name}.{attribute} is gone from the vendored tree. It "
                "held a $HOME path this mode redirects; find where that state "
                "goes now before assuming it is safe."
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        setattr(module, attribute, destination)
        applied[f"{module_name}.{attribute}"] = destination
    return applied


def run_legacy(argv: list[str]) -> int:
    """Run the inherited CLI in this process, under the mode.

    Named for what it runs, not for the program it belongs to: `winnow safe
    run --` hands argv to `winnow.legacy.cli`, and `run_winnow` inside winnow
    would name everything and distinguish nothing.

    In-process because the exclusion in `apply_strategy_exclusions` is an
    in-memory edit to a module-level dict — a subprocess would import a fresh,
    unexcluded copy. The environment overlay is applied before `main()` because
    `_maybe_global_init` reads os.environ at call time (cli.py:2076).
    """
    apply_safe_environment()
    apply_strategy_exclusions()
    redirect_home_writes(data_dir())

    from winnow.legacy.cli import main as legacy_main

    saved = sys.argv
    sys.argv = ["winnow", *argv]
    try:
        legacy_main()
    except SystemExit as exc:
        if exc.code is None:
            return 0
        if isinstance(exc.code, int):
            return exc.code
        print(exc.code, file=sys.stderr)
        return 1
    finally:
        sys.argv = saved
    return 0
