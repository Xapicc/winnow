"""`python -m winnow safe …` — the orchestrator-safe mode's surface.

Exit codes follow SPEC §8: 0 success, 1 usage error, 2 nothing to do, 3 refused.
A refusal is loud and names what refused, because a mode that silently declines
to protect anything is indistinguishable from one that is not on. So is every
other outcome: each action a hook can invoke ends in exactly one bounded
``winnow: `` line on stderr, including "nothing to checkpoint", which is a
result and not an absence.

Nothing here writes a log file. SPEC §10 forbids one by default, and under this
harness stderr is a pipe the orchestrator already records per cycle, so a
refusal's reason lands in the run's own log without a file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import orchestrator_safe as safe

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOTHING = 2
EXIT_REFUSED = 3

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Long enough that no refusal reason is ever cut — the longest is 272 characters
# and a test holds that — and far below the 8,000 the orchestrator stores per
# stderr line (logLine.ts). The bound exists so that a path or a session name
# arriving from outside cannot turn one hook line into a large database row.
_MAX_LINE_CHARS = 500


def _say(message: str) -> None:
    """Emit one bounded ``winnow: `` line on stderr.

    Every action a hook can invoke ends in exactly one of these, whatever the
    outcome, because stderr is the only channel a hook has and the orchestrator
    records it per cycle. A cycle where there was nothing to checkpoint has to
    be distinguishable from one where the plugin never loaded, and silence
    cannot do that (docs/USAGEFOUNDRY.md §8.5).
    """
    line = " ".join(message.split())
    if len(line) > _MAX_LINE_CHARS:
        # ASCII, because a hook's stderr may be an ASCII-only stream and a
        # UnicodeEncodeError here would lose the line the bound exists to keep.
        line = line[: _MAX_LINE_CHARS - 3] + "..."
    print(f"winnow: {line}", file=sys.stderr)


def _require_mode() -> str | None:
    """The reason the mode is not on, or None."""
    try:
        if safe.is_enabled():
            return None
    except ValueError as exc:
        return str(exc)
    return (
        f"orchestrator-safe mode is off. Set {safe.ENV_SWITCH}=1 in the "
        "environment the harness spawns Claude Code in; see docs/USAGEFOUNDRY.md."
    )


def cmd_check(args: argparse.Namespace) -> int:
    findings = safe.check()
    violations = [f for f in findings if not f.ok]
    if args.json:
        print(json.dumps(
            {
                "ok": not violations,
                "findings": [
                    {"name": f.name, "ok": f.ok, "detail": f.detail} for f in findings
                ],
            },
            indent=2,
        ))
    else:
        for finding in findings:
            print(f"{'ok  ' if finding.ok else 'FAIL'}  {finding.name}: {finding.detail}")
    return EXIT_REFUSED if violations else EXIT_OK


def cmd_env(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(
            {
                name: {"value": value, "why": safe.SAFE_ENV_REASONS[name]}
                for name, value in safe.SAFE_ENV.items()
            },
            indent=2,
        ))
        return EXIT_OK
    for name, value in safe.SAFE_ENV.items():
        print(f"export {name}={value}")
    return EXIT_OK


def cmd_plugin_dir(args: argparse.Namespace) -> int:
    reason = _require_mode()
    if reason:
        _say(reason)
        return EXIT_REFUSED
    source = Path(args.source) if args.source else _REPO_ROOT / "plugin"
    dest = Path(args.out) if args.out else _REPO_ROOT / safe.PLUGIN_DEST_DIRNAME
    report = safe.materialise_plugin_dir(source, dest)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return EXIT_OK
    print(f"{report['dest']}  ({report['plugin_name']})")
    print(f"  kept:    {', '.join(report['kept_hook_events'])}")
    for name in report["dropped_hook_events"] + report["dropped_paths"]:
        print(f"  dropped: {name} — {report['reasons'][name]}")
    print(f"\nPass it to the harness with --plugin-dir {report['dest']}")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    reason = _require_mode()
    if reason:
        _say(reason)
        return EXIT_REFUSED
    # argparse.REMAINDER keeps the `--` that separated our flags from the
    # inherited CLI's, whose own prescan would carry it into argparse as a token.
    argv = args.argv[1:] if args.argv[:1] == ["--"] else list(args.argv)
    if not argv:
        _say("safe run needs an inherited subcommand: "
             "winnow safe run -- diagnose <session>")
        return EXIT_USAGE

    refusal = safe.refusal_for(argv, live_pid=safe.live_claude_pid())
    if refusal:
        _say(refusal)
        return EXIT_REFUSED
    return safe.run_legacy(argv)


def cmd_checkpoint(args: argparse.Namespace) -> int:
    reason = _require_mode()
    if reason:
        _say(reason)
        return EXIT_REFUSED
    payload = safe.hook_payload("" if sys.stdin.isatty() else sys.stdin.read())
    session_path = safe.resolve_session_path(payload, args.cwd)
    if session_path is None:
        _say("no session to checkpoint")
        return EXIT_NOTHING
    written = safe.write_checkpoint(session_path, safe.data_dir())
    if written is None:
        # A result, not an absence: this is the outcome on every cycle of a
        # session that never spawned a subagent, and it is the one the old
        # silence made indistinguishable from an unloaded plugin.
        _say(f"nothing to checkpoint: no team state in {session_path.name}")
        return EXIT_NOTHING
    _say(f"team state checkpointed to {written}")
    return EXIT_OK


def cmd_post_compact(args: argparse.Namespace) -> int:
    reason = _require_mode()
    if reason:
        _say(reason)
        return EXIT_REFUSED
    content = safe.read_checkpoint(safe.data_dir())
    if not content:
        _say("no checkpoint to restore")
        return EXIT_NOTHING
    # stdout is the hook's output and goes to the model; the line about it goes
    # to stderr, which is the run's log. Its length rather than its content,
    # because the content is the transcript's and can be any size.
    print(content)
    _say(f"checkpoint restored, {len(content)} characters")
    return EXIT_OK


def add_safe_subparser(sub: argparse._SubParsersAction) -> None:
    """Register the `safe` group onto an existing subparsers action.

    Split out from `build_parser` because winnow is one program: the inherited
    parser in `winnow.legacy.cli` owns `prog` and the global flags, and calls
    this so that `winnow --help` lists the safe group alongside the inherited
    subcommands (docs/FORK.md §2).
    """
    safe_group = sub.add_parser(
        "safe",
        help="orchestrator-safe mode: the behaviour required when an unattended "
             "harness owns the Claude Code process",
    )
    actions = safe_group.add_subparsers(dest="action", required=True)

    p_check = actions.add_parser(
        "check", help="report the mode's state and every invariant readable here"
    )
    p_check.add_argument("--json", action="store_true")
    p_check.set_defaults(func=cmd_check)

    p_env = actions.add_parser(
        "env", help="the environment overlay, as shell exports or JSON with reasons"
    )
    p_env.add_argument("--json", action="store_true")
    p_env.set_defaults(func=cmd_env)

    p_plugin = actions.add_parser(
        "plugin-dir",
        help="materialise a plugin directory safe to pass to --plugin-dir",
    )
    p_plugin.add_argument(
        "--out",
        help="destination (default: <repository root>/"
             f"{safe.PLUGIN_DEST_DIRNAME}, which is where UsageFoundry's "
             "plugin scan can see it)",
    )
    p_plugin.add_argument("--source", help="source plugin directory (default: ./plugin)")
    p_plugin.add_argument("--json", action="store_true")
    p_plugin.set_defaults(func=cmd_plugin_dir)

    p_run = actions.add_parser(
        "run", help="run an inherited subcommand under the mode"
    )
    p_run.add_argument("argv", nargs=argparse.REMAINDER)
    p_run.set_defaults(func=cmd_run)

    p_cp = actions.add_parser(
        "checkpoint",
        help="PreCompact: write team state into winnow's data directory",
        description="Write the current session's team state into winnow's data "
                    f"directory ({safe.DATA_DIR_ENV}), never into ~/.claude, which "
                    "is a bind mount this mode may not write to. `winnow team "
                    "checkpoint` is the same operation writing into ~/.claude.",
    )
    p_cp.add_argument("--cwd", help="working directory (default: current)")
    p_cp.set_defaults(func=cmd_checkpoint)

    p_pc = actions.add_parser(
        "post-compact",
        help="PostCompact: print the checkpoint back",
        description="Print back the checkpoint `winnow safe checkpoint` wrote into "
                    f"winnow's data directory ({safe.DATA_DIR_ENV}). Never reads "
                    "~/.claude, so it cannot restore another project's state.",
    )
    p_pc.set_defaults(func=cmd_post_compact)


def build_parser() -> argparse.ArgumentParser:
    """A parser for `winnow safe ...` alone.

    `winnow`'s full parser is `winnow.legacy.cli.build_parser`, which registers
    this group as well. This one exists so that dispatching `safe` never has to
    build the inherited parser, whose construction is not the problem but whose
    `main()` does an update ping and an auto-init before it parses.
    """
    parser = argparse.ArgumentParser(
        prog="winnow",
        description="winnow — see docs/SPEC.md. Only the orchestrator-safe "
                    "mode is implemented.",
    )
    add_safe_subparser(parser.add_subparsers(dest="group", required=True))
    return parser


def main(argv: list[str] | None = None) -> int:
    """The `winnow` entry point: the safe group here, everything else inherited."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] != ["safe"]:
        from .legacy.cli import main as legacy_main

        return legacy_main(argv)
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
