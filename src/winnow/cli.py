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

from . import fork as fork_mod
from . import orchestrator_safe as safe
from . import proxy as proxy_mod
from . import rules as rules_mod
from . import savings as savings_mod

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


def cmd_inspect(args: argparse.Namespace) -> int:
    from .report import inspect_command

    code, output = inspect_command(
        session=args.session,
        tier=args.tier,
        keep_last=args.keep_last,
        min_bytes=args.min_bytes,
        as_json=args.json,
        filter_ledger=Path(args.filter_ledger) if args.filter_ledger else None,
    )
    print(output, file=sys.stderr if code == EXIT_USAGE else sys.stdout)
    return code


def add_inspect_subparser(sub) -> None:
    """Register `winnow inspect` (SPEC §8).

    Its own group rather than a member of `safe`, because it is not part of
    orchestrator-safe mode: it has no write path at all, so there is nothing for
    that mode to withhold and no reason to make an operator set an environment
    variable to read their own transcript.
    """
    p = sub.add_parser(
        "inspect",
        help="composition readout for one session; writes nothing",
        description="Read a session transcript and report what it is carrying, "
                    "what SPEC §4's rules would replace, and whether the cache "
                    "arithmetic says replacing it pays. Writes nothing, anywhere.",
    )
    p.add_argument("session", help="session ID, path, or unambiguous ID prefix")
    p.add_argument(
        "--tier", choices=("C", "CB", "CBA"), default="CB",
        help="which rule tiers the arithmetic is computed for (default: CB)",
    )
    p.add_argument(
        "--keep-last", type=int, default=rules_mod.DEFAULT_KEEP_LAST,
        metavar="N", help="guard G1: never strip the last N tool results",
    )
    p.add_argument(
        "--min-bytes", type=int, default=rules_mod.DEFAULT_MIN_BYTES,
        metavar="N", help="guard G2: never strip a result under N bytes",
    )
    p.add_argument(
        "--filter-ledger", default=None, metavar="PATH",
        help="a `winnow filter --ledger` file. Joined on requestId, it says what "
             "the intake filter kept off the wire for this session — which the "
             "transcript still contains and every figure here otherwise counts",
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_inspect)


def cmd_plan(args: argparse.Namespace) -> int:
    from .plan import plan_command

    code, output = plan_command(
        session=args.session,
        tier=args.tier,
        rule=args.rule,
        no_rule=args.no_rule,
        keep_last=args.keep_last,
        min_bytes=args.min_bytes,
        i_know=args.i_know,
        as_json=args.json,
        explain=args.explain,
    )
    print(output, file=sys.stderr if code == EXIT_USAGE else sys.stdout)
    return code


def add_plan_subparser(sub) -> None:
    """Register `winnow plan` (SPEC §8) — the dry run, in its own group.

    Next to `inspect` rather than under `safe`, and for the same reason: it has
    no write path, so orchestrator-safe mode has nothing to withhold from it.
    `--write`, `--out`, `--force` and `--min-cold-age` are absent because they
    belong to `fork`, which does not exist yet; a flag parsed here that does
    nothing would be worse than one that is missing.
    """
    p = sub.add_parser(
        "plan",
        help="dry run: what a fork would strip from one session, and the arithmetic",
        description="Classify one session under SPEC §4's rules and report exactly "
                    "which tool results a fork would replace with pointers, what "
                    "the pointers cost, what the net is, and how many further "
                    "turns the cut needs to pay for its cache invalidation. "
                    "Writes nothing, anywhere.",
    )
    p.add_argument("session", help="session ID, path, or unambiguous ID prefix")
    p.add_argument(
        "--tier", choices=("C", "CB", "CBA"), default="CB",
        help="which rule tiers may fire (default: CB; CBA requires --i-know)",
    )
    p.add_argument(
        "--rule", action="append", default=[], metavar="ID",
        help="enable one rule on top of the tier, repeatable (C1 C2 C3 B1 B2 A1)",
    )
    p.add_argument(
        "--no-rule", action="append", default=[], metavar="ID",
        help="disable one rule the tier enabled, repeatable. Applied after --rule",
    )
    p.add_argument(
        "--keep-last", type=int, default=rules_mod.DEFAULT_KEEP_LAST,
        metavar="N", help="guard G1: never strip the last N tool results",
    )
    p.add_argument(
        "--min-bytes", type=int, default=rules_mod.DEFAULT_MIN_BYTES,
        metavar="N", help="guard G2: never strip a result under N bytes",
    )
    p.add_argument(
        "--i-know", action="store_true",
        help="acknowledge that tier A strips reads the session may still need; "
             "required by any selection containing A1 (SPEC §4, §8)",
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument(
        "--explain", action="store_true",
        help="one line per stripped result: rule, tool, arguments, bytes. "
             "Prints tool arguments verbatim, which routinely contain "
             "credentials (SPEC §10) — treat the output as sensitive",
    )
    p.set_defaults(func=cmd_plan)


def cmd_fork(args: argparse.Namespace) -> int:
    from .fork import fork_command

    code, output = fork_command(
        session=args.session,
        tier=args.tier,
        rule=args.rule,
        no_rule=args.no_rule,
        keep_last=args.keep_last,
        min_bytes=args.min_bytes,
        min_cold_age=args.min_cold_age,
        i_know=args.i_know,
        write=args.write,
        out=args.out,
        force=args.force,
        as_json=args.json,
        explain=args.explain,
    )
    print(output, file=sys.stdout if code in (EXIT_OK, EXIT_NOTHING) else sys.stderr)
    return code


def add_fork_subparser(sub) -> None:
    """Register `winnow fork` (SPEC §8) — the writer.

    `--write` is the opt-in and there is no `--dry-run`: SPEC §8 makes dry the
    default, so the flag that writes is the one an operator has to type. `--force`
    is here rather than on `plan` for the same reason `--min-cold-age` is: a
    refusal only exists where there is a file to refuse to write.
    """
    p = sub.add_parser(
        "fork",
        help="write a forked transcript with once-only tool results replaced by "
             "pointers (needs --write)",
        description="Classify one session under SPEC §4's rules and write a new "
                    "transcript under a new session ID with the selected tool "
                    "results replaced by recoverable pointers. The original is "
                    "opened read-only and is never modified. Without --write this "
                    "is a dry run; there is no --dry-run.",
    )
    p.add_argument("session", help="session ID, path, or unambiguous ID prefix")
    p.add_argument(
        "--tier", choices=("C", "CB", "CBA"), default="CB",
        help="which rule tiers may fire (default: CB; CBA requires --i-know)",
    )
    p.add_argument(
        "--rule", action="append", default=[], metavar="ID",
        help="enable one rule on top of the tier, repeatable (C1 C2 C3 B1 B2 A1)",
    )
    p.add_argument(
        "--no-rule", action="append", default=[], metavar="ID",
        help="disable one rule the tier enabled, repeatable. Applied after --rule",
    )
    p.add_argument(
        "--keep-last", type=int, default=rules_mod.DEFAULT_KEEP_LAST,
        metavar="N", help="guard G1: never strip the last N tool results",
    )
    p.add_argument(
        "--min-bytes", type=int, default=rules_mod.DEFAULT_MIN_BYTES,
        metavar="N", help="guard G2: never strip a result under N bytes",
    )
    p.add_argument(
        "--min-cold-age", type=int, default=fork_mod.DEFAULT_MIN_COLD_AGE,
        metavar="S",
        help="refuse a session whose last request finished less than S seconds "
             f"ago (default {fork_mod.DEFAULT_MIN_COLD_AGE}); below it the prefix "
             "may still be cached and the cut is not free (SPEC §7)",
    )
    p.add_argument(
        "--i-know", action="store_true",
        help="acknowledge that tier A strips reads the session may still need; "
             "required by any selection containing A1 (SPEC §4, §8)",
    )
    p.add_argument(
        "--write", action="store_true",
        help="actually write the fork. Without it this is a dry run",
    )
    p.add_argument(
        "--out", default=None, metavar="PATH",
        help="where the fork goes (default: a new session ID in the same project "
             "directory)",
    )
    p.add_argument(
        "--force", action="store_true",
        help="proceed past a soft refusal — cold age, an already-compacted "
             "session, a malformed source record, or whole-fork G4. Never past G5",
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument(
        "--explain", action="store_true",
        help="one line per stripped result: rule, tool, arguments, bytes. "
             "Prints tool arguments verbatim, which routinely contain "
             "credentials (SPEC §10) — treat the output as sensitive",
    )
    p.set_defaults(func=cmd_fork)


def cmd_recover(args: argparse.Namespace) -> int:
    from .fork import recover_command

    code, output = recover_command(
        session=args.session, identifier=args.pointer_id, as_json=args.json
    )
    if code != EXIT_OK:
        print(output, file=sys.stderr)
        return code
    # Written rather than printed: the contract is "the exact original bytes", and
    # `print` would append a newline the digest in the pointer does not cover.
    sys.stdout.buffer.write(output.encode("utf-8", "surrogateescape"))
    sys.stdout.buffer.flush()
    return code


def add_recover_subparser(sub) -> None:
    """Register `winnow recover` (SPEC §8) — the other half of the round trip.

    Reads the *original* transcript, which is the session the pointer quotes: the
    bytes were never removed from it, and that is what makes a strip reversible in
    the sense SPEC §7 requires.
    """
    p = sub.add_parser(
        "recover",
        help="print the original bytes a pointer stands in for, from the "
             "untouched source transcript",
        description="Print the exact bytes a winnow pointer replaced, read back "
                    "from the original transcript — which winnow never wrote to. "
                    "The bytes hash to the sha256 the pointer records. Writes "
                    "nothing, anywhere.",
    )
    p.add_argument(
        "session",
        help="the ORIGINAL session the pointer names, as an ID, a path, or an "
             "unambiguous prefix",
    )
    p.add_argument("pointer_id", metavar="pointer-id",
                   help="the id from the pointer, as in `b7`")
    p.add_argument(
        "--json", action="store_true",
        help="wrap the bytes in a record carrying the sha256 and the tool name",
    )
    p.set_defaults(func=cmd_recover)


def cmd_savings(args: argparse.Namespace) -> int:
    from .report import savings_command

    code, output = savings_command(
        ledger=args.ledger,
        projects=args.projects,
        as_json=args.json,
        filter_ledger=Path(args.filter_ledger) if args.filter_ledger else None,
    )
    print(output, file=sys.stderr if code == EXIT_USAGE else sys.stdout)
    return code


def add_savings_subparser(sub) -> None:
    """Register `winnow savings` — what the filter has done, not what it would do.

    Its own group next to `inspect` and for the same reason: it has no write path,
    reading only the filter's ledger and the transcripts the ledger points at. It is
    the counterpart to `inspect`, which prices a cut that has not happened; this
    prices the cuts that have.
    """
    p = sub.add_parser(
        "savings",
        help="price what the intake filter has removed on this install",
        description="Read the intake filter's ledger, join it to Claude Code's "
                    "transcripts on request_id, and price what it removed using "
                    "COZEMPIC.md §3.5's model. Each removed result is counted once, "
                    "however many later requests the stateless filter re-dropped it "
                    "from. The figure is modelled, not billed. Writes nothing.",
    )
    p.add_argument(
        "--ledger", metavar="PATH",
        help=f"the filter's ledger (default: {savings_mod.DEFAULT_LEDGER})",
    )
    p.add_argument(
        "--projects", metavar="PATH",
        help="Claude Code's transcript root, joined on requestId "
             f"(default: {savings_mod.DEFAULT_PROJECTS})",
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_savings)


def cmd_filter(args: argparse.Namespace) -> int:
    if not proxy_mod.is_enabled() and not args.force:
        _say("intake filter is off. Set WINNOW_FILTER=1, or pass --force to run "
             "it once without the toggle.")
        return EXIT_REFUSED
    config = proxy_mod.config_from_env(
        port=args.port,
        upstream=args.upstream,
        min_bytes=args.min_bytes,
        keep_newest=args.keep_newest,
        ledger=Path(args.ledger) if args.ledger else None,
        off_file=Path(args.off_file) if args.off_file else None,
        verbose=args.verbose or None,
    )
    return proxy_mod.serve(config)


def add_filter_subparser(sub) -> None:
    """Register `winnow filter` — the intake filter's proxy.

    A separate group from `inspect` because it is the only thing in this tree
    that sits in the request path of a live session. It refuses to start unless
    `WINNOW_FILTER=1`, for the same reason orchestrator-safe mode refuses: a
    process that quietly inserted itself between a session and its credentials
    would be indistinguishable from one that was asked to.
    """
    p = sub.add_parser(
        "filter",
        help="run the intake filter proxy (needs WINNOW_FILTER=1)",
        description="A local pass-through proxy that drops a tool result before "
                    "it is ever written to the prompt cache. Point Claude Code "
                    "at it with ANTHROPIC_BASE_URL. See docs/COZEMPIC.md §3.5.",
    )
    p.add_argument("--port", type=int, default=None,
                   help=f"listen port (default {proxy_mod.DEFAULT_PORT})")
    p.add_argument("--upstream", default=None,
                   help=f"where to forward (default {proxy_mod.DEFAULT_UPSTREAM})")
    p.add_argument("--min-bytes", type=int, default=None, metavar="N",
                   help="guard G2: never drop a result under N bytes")
    p.add_argument("--keep-newest", type=int, default=None, metavar="N",
                   help="exempt the newest N tool results (default 1)")
    p.add_argument("--ledger", default=None, metavar="PATH",
                   help="append one JSON line per filtered request, so `inspect` "
                        "can be told what the transcript no longer reflects")
    p.add_argument("--off-file", default=None, metavar="PATH",
                   help="kill switch: while this file exists the proxy keeps "
                        "relaying but stops rewriting (default "
                        f"{proxy_mod.DEFAULT_OFF_FILE})")
    p.add_argument("--verbose", action="store_true",
                   help="one stderr line per filtered request")
    p.add_argument("--force", action="store_true",
                   help="run without WINNOW_FILTER=1")
    p.set_defaults(func=cmd_filter)


def build_parser() -> argparse.ArgumentParser:
    """A parser for the groups implemented in this tree.

    `winnow`'s full parser is `winnow.legacy.cli.build_parser`, which registers
    the safe group as well. This one exists so that dispatching `safe` or
    `inspect` never has to build the inherited parser, whose construction is not
    the problem but whose `main()` does an update ping and an auto-init before it
    parses — and an auto-init writes to `~/.claude`, which a read-only command
    has no business triggering.
    """
    parser = argparse.ArgumentParser(
        prog="winnow",
        description="winnow — see docs/SPEC.md. Implemented: the "
                    "orchestrator-safe mode, `inspect`, `plan`, `fork` and "
                    "`recover`.",
    )
    sub = parser.add_subparsers(dest="group", required=True)
    add_safe_subparser(sub)
    add_inspect_subparser(sub)
    add_plan_subparser(sub)
    add_fork_subparser(sub)
    add_recover_subparser(sub)
    add_filter_subparser(sub)
    add_savings_subparser(sub)
    return parser


# Groups this tree owns. Everything else falls through to the inherited CLI.
_OWN_GROUPS = ("safe", "inspect", "plan", "fork", "recover", "filter", "savings")


def main(argv: list[str] | None = None) -> int:
    """The `winnow` entry point: this tree's groups here, everything else inherited."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] and argv[0] in _OWN_GROUPS:
        args = build_parser().parse_args(argv)
        return args.func(args)
    from .legacy.cli import main as legacy_main

    return legacy_main(argv)


if __name__ == "__main__":
    sys.exit(main())
