"""`python -m winnow safe …` — the orchestrator-safe mode's surface.

Exit codes follow SPEC §8: 0 success, 1 usage error, 2 nothing to do, 3 refused.
A refusal is loud and names what refused, because a mode that silently declines
to protect anything is indistinguishable from one that is not on.

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
        print(reason, file=sys.stderr)
        return EXIT_REFUSED
    source = Path(args.source) if args.source else _REPO_ROOT / "plugin"
    dest = Path(args.out) if args.out else safe.data_dir() / "plugin"
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
        print(reason, file=sys.stderr)
        return EXIT_REFUSED
    # argparse.REMAINDER keeps the `--` that separated our flags from cozempic's,
    # and cozempic's own prescan would carry it into argparse as a token.
    argv = args.argv[1:] if args.argv[:1] == ["--"] else list(args.argv)
    if not argv:
        print("winnow safe run needs a cozempic command: "
              "winnow safe run -- diagnose <session>", file=sys.stderr)
        return EXIT_USAGE

    refusal = safe.refusal_for(argv, live_pid=safe.live_claude_pid())
    if refusal:
        print(f"winnow: {refusal}", file=sys.stderr)
        return EXIT_REFUSED
    return safe.run_cozempic(argv)


def cmd_checkpoint(args: argparse.Namespace) -> int:
    reason = _require_mode()
    if reason:
        print(reason, file=sys.stderr)
        return EXIT_REFUSED
    payload = safe.hook_payload("" if sys.stdin.isatty() else sys.stdin.read())
    session_path = safe.resolve_session_path(payload, args.cwd)
    if session_path is None:
        print("winnow: no session to checkpoint", file=sys.stderr)
        return EXIT_NOTHING
    written = safe.write_checkpoint(session_path, safe.data_dir())
    if written is None:
        return EXIT_NOTHING
    print(f"winnow: team state checkpointed to {written}", file=sys.stderr)
    return EXIT_OK


def cmd_post_compact(args: argparse.Namespace) -> int:
    reason = _require_mode()
    if reason:
        print(reason, file=sys.stderr)
        return EXIT_REFUSED
    content = safe.read_checkpoint(safe.data_dir())
    if not content:
        return EXIT_NOTHING
    print(content)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="winnow",
        description="winnow — see docs/SPEC.md. Only the orchestrator-safe "
                    "mode is implemented.",
    )
    sub = parser.add_subparsers(dest="group", required=True)
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
    p_plugin.add_argument("--out", help="destination (default: <data dir>/plugin)")
    p_plugin.add_argument("--source", help="source plugin directory (default: ./plugin)")
    p_plugin.add_argument("--json", action="store_true")
    p_plugin.set_defaults(func=cmd_plugin_dir)

    p_run = actions.add_parser(
        "run", help="run the vendored cozempic CLI under the mode"
    )
    p_run.add_argument("argv", nargs=argparse.REMAINDER)
    p_run.set_defaults(func=cmd_run)

    p_cp = actions.add_parser(
        "checkpoint",
        help="PreCompact: write team state into winnow's data directory",
    )
    p_cp.add_argument("--cwd", help="working directory (default: current)")
    p_cp.set_defaults(func=cmd_checkpoint)

    p_pc = actions.add_parser(
        "post-compact", help="PostCompact: print the checkpoint back"
    )
    p_pc.set_defaults(func=cmd_post_compact)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
