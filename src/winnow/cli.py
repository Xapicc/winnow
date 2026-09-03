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
from . import plan as plan_mod
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


def _break_even_budget(value: str) -> int | None:
    """`--max-break-even`: further turns, or `none` to not gate at all.

    `none` is not `0`, and the difference is the reason this parser exists. Zero
    admits only a cut that has already paid for itself at the moment it is made;
    `none` says the question does not arise. A caller that knows the invalidation
    is refunded — an orchestrator forking at a cycle boundary, where `--resume`
    was going to rewrite the prefix regardless — wants the second, and expressing
    it as a very large number would be the same instruction written as a lie.
    """
    if value.strip().lower() in ("none", "off"):
        return None
    try:
        turns = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a number of further turns or 'none', got {value!r}"
        ) from None
    if turns < 0:
        raise argparse.ArgumentTypeError(
            f"a number of further turns must not be negative, got {turns}"
        )
    return turns


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
        _say("safe run needs a subcommand: "
             "winnow safe run -- diagnose <session>")
        return EXIT_USAGE

    # `run_under_mode` dispatches through this module's own `main`, which routes
    # `safe` straight back to this function. Refused rather than guarded further
    # in, because the only thing a nested `safe` could mean is a mistake, and an
    # unbounded one: each round would re-apply the environment overlay and the
    # strategy exclusion before recursing.
    if argv[0] == "safe":
        _say("`winnow safe run -- safe …` is refused: the mode does not nest, "
             "and a nested run would recurse rather than do anything.")
        return EXIT_USAGE

    refusal = safe.refusal_for(argv, live_pid=safe.live_claude_pid())
    if refusal:
        _say(refusal)
        return EXIT_REFUSED
    return safe.run_under_mode(argv)


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
        max_break_even=args.max_break_even,
        filter_ledger=Path(args.filter_ledger) if args.filter_ledger else None,
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
        help="enable one rule on top of the tier, repeatable (C1 C2 C3 B1 B2 A1). "
             "Also how a rule that is off by default is switched back on; "
             f"${rules_mod.RULES_OFF_ENV} sets that default list",
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
    p.add_argument(
        "--max-break-even", type=_break_even_budget,
        default=plan_mod.DEFAULT_MAX_BREAK_EVEN, metavar="T",
        help="how many further turns this session is expected to run. A cut needs "
             "T* = 19·(S/D) − 20 of them before it has paid for the cache "
             "invalidation it causes (SPEC §7); above T that is a cut which is "
             f"never earned back (default {plan_mod.DEFAULT_MAX_BREAK_EVEN}). "
             "`none` does not gate at all, for a caller that knows the "
             "invalidation is refunded",
    )
    p.add_argument(
        "--filter-ledger", default=None, metavar="PATH",
        help="a `winnow filter --ledger` file. Joined on requestId, it says what "
             "the intake filter already kept off the wire for this session — "
             "which the transcript still contains and every share here otherwise "
             "counts. 79%% of what tier CB proposes to remove is content the "
             "filter claims too, so on a filtered session this is not a rounding "
             "correction",
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
        max_break_even=args.max_break_even,
        i_know=args.i_know,
        write=args.write,
        out=args.out,
        force=args.force,
        as_json=args.json,
        explain=args.explain,
        filter_ledger=Path(args.filter_ledger) if args.filter_ledger else None,
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
        help="enable one rule on top of the tier, repeatable (C1 C2 C3 B1 B2 A1). "
             "Also how a rule that is off by default is switched back on; "
             f"${rules_mod.RULES_OFF_ENV} sets that default list",
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
        "--max-break-even", type=_break_even_budget,
        default=plan_mod.DEFAULT_MAX_BREAK_EVEN, metavar="T",
        help="how many further turns this session is expected to run. A cut needs "
             "T* = 19·(S/D) − 20 of them before it has paid for the cache "
             "invalidation it causes (SPEC §7); above T that is a cut which is "
             f"never earned back (default {plan_mod.DEFAULT_MAX_BREAK_EVEN}). "
             "`none` does not gate at all, for a caller that knows the "
             "invalidation is refunded",
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
        help="proceed past a soft refusal — cold age, break-even, an "
             "already-compacted session, a malformed source record, or "
             "whole-fork G4. Never past G5",
    )
    p.add_argument(
        "--filter-ledger", default=None, metavar="PATH",
        help="a `winnow filter --ledger` file. Joined on requestId, it says what "
             "the intake filter already kept off the wire for this session — "
             "which the transcript still contains and every share here otherwise "
             "counts. 79%% of what tier CB proposes to remove is content the "
             "filter claims too, so on a filtered session this is not a rounding "
             "correction",
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


def _filter_rules(args: argparse.Namespace) -> tuple[frozenset[str], tuple[str, ...]]:
    """SPEC §8's rule selection, restricted to what the filter can decide.

    Returns `(enabled, suppressed by a default)`. The restriction is an
    intersection with `rules.STATELESS_RULES`, so `--tier CBA` on the filter means
    the three rules it can answer rather than six — but naming one of the other
    three with `--rule` is a **usage error**, because an operator who types
    `--rule C2` is asking for something this component cannot do and silence
    would leave them believing it was doing it.

    `--no-rule C2` is not an error. It asks for strictly less than the filter
    already does, and an operator who shares one set of rule flags across `plan`
    and `filter` should not be stopped by it.
    """
    for rule in args.rule:
        normalised = rule.strip().upper()
        if normalised in rules_mod.ALL_RULES and normalised not in rules_mod.STATELESS_RULES:
            raise rules_mod.RuleSelectionError(
                f"--rule {normalised} cannot be enabled on the intake filter: its "
                f"verdict depends on a later turn, so firing it would change what "
                f"an already-cached request renders to. It is the pruner's — see "
                f"`winnow plan --rule {normalised}`."
            )
    selected = rules_mod.resolve_rules(args.tier, args.rule, args.no_rule)
    suppressed = tuple(
        rule
        for rule in rules_mod.suppressed_by_default(args.tier, args.rule, args.no_rule)
        if rule in rules_mod.STATELESS_RULES
    )
    return selected & rules_mod.STATELESS_RULES, suppressed


def cmd_filter(args: argparse.Namespace) -> int:
    from . import filter as filter_mod

    if not proxy_mod.is_enabled() and not args.force:
        _say("intake filter is off. Set WINNOW_FILTER=1, or pass --force to run "
             "it once without the toggle.")
        return EXIT_REFUSED

    # Rule selection, resolved exactly once. See `proxy.Config.rules` for why it
    # may not be resolved per request, and option M for why the filter must be
    # reachable by the same switch the pruner is.
    try:
        selected, suppressed = _filter_rules(args)
    except rules_mod.RuleSelectionError as exc:
        _say(str(exc))
        return EXIT_USAGE

    config = proxy_mod.config_from_env(
        port=args.port,
        upstream=args.upstream,
        min_bytes=args.min_bytes,
        keep_newest=args.keep_newest,
        ledger=Path(args.ledger) if args.ledger else None,
        off_file=Path(args.off_file) if args.off_file else None,
        verbose=args.verbose or None,
        rules=selected,
        heartbeat_every=args.heartbeat,
        prefix_readout=False if args.no_prefix_readout else None,
    )
    if suppressed:
        # The same sentence `plan` prints, for the same reason: a tier that
        # quietly means fewer rules than its own name lists is the silent
        # fallback SPEC §10 forbids, and the operator who most needs to be told
        # is the one whose saving came in lower than last week's.
        _say(f"tier {args.tier} names {', '.join(suppressed)}, which a default "
             f"turns off. Pass --rule to switch back on.")
    # Checked here rather than by argparse so that the environment variable is
    # held to the same bar as the flag: `WINNOW_FILTER_MIN_BYTES=10` is the same
    # mistake typed somewhere quieter. Below the floor, guard G4 refuses every
    # result the floor admits, so the setting reads as "strip more" and strips
    # less — SPEC §10's silent fallback, in the direction that reports a saving.
    floor = filter_mod.smallest_safe_min_bytes()
    if config.min_bytes < floor:
        _say(f"--min-bytes {config.min_bytes} is below the longest pointer this "
             f"filter can produce ({floor} bytes). Every result it admitted would "
             f"be refused by guard G4, so it would strip less, not more. "
             f"Use {floor} or higher.")
        return EXIT_USAGE
    return proxy_mod.serve(config)


def add_filter_subparser(sub) -> None:
    """Register `winnow filter` — the intake filter's proxy.

    A separate group from `inspect` because it is the only thing in this tree
    that sits in the request path of a live session. It refuses to start unless
    `WINNOW_FILTER=1`, for the same reason orchestrator-safe mode refuses: a
    process that quietly inserted itself between a session and its credentials
    would be indistinguishable from one that was asked to.
    """
    from . import filter as filter_mod

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
                   help=f"guard G2: never drop a result under N bytes (default "
                        f"{filter_mod.FILTER_MIN_BYTES}). Deliberately not the "
                        f"pruner's {rules_mod.DEFAULT_MIN_BYTES}: the filter sends a "
                        f"candidate once in full and the pointer then lives in the "
                        f"cached prefix, so its break-even is between one and two "
                        f"pointer lengths, not two thousand")
    p.add_argument("--keep-newest", type=int, default=None, metavar="N",
                   help="exempt the newest N tool results (default 1)")
    p.add_argument(
        "--tier", choices=("C", "CB", "CBA"), default="CB",
        help="which rule tiers may fire (default: CB). The filter can only "
             "decide C1, C3 and B2 — the rules whose verdict does not depend on "
             "a later turn — so a tier is intersected with those three",
    )
    p.add_argument(
        "--rule", action="append", default=[], metavar="ID",
        help="enable one rule on top of the tier, repeatable (C1 C3 B2). Also "
             "how a rule that is off by default is switched back on; "
             f"${rules_mod.RULES_OFF_ENV} sets that default list, and is read "
             "once at startup — a change to it needs a restart",
    )
    p.add_argument(
        "--no-rule", action="append", default=[], metavar="ID",
        help="disable one rule the tier enabled, repeatable. Applied after --rule",
    )
    p.add_argument("--ledger", default=None, metavar="PATH",
                   help="append one JSON line per filtered request, so `inspect` "
                        "can be told what the transcript no longer reflects")
    p.add_argument("--off-file", default=None, metavar="PATH",
                   help="kill switch: while this file exists the proxy keeps "
                        "relaying but stops rewriting (default "
                        f"{proxy_mod.DEFAULT_OFF_FILE})")
    p.add_argument("--no-prefix-readout", action="store_true",
                   help="stop reporting the size, shape and stability of `system` "
                        "and `tools` to the ledger. The readout writes sizes, names "
                        "and hashes and never content, and it is the only way to "
                        "see a fixed prefix that is silently invalidating on every "
                        "request — which is the most expensive thing that can "
                        "happen to an install and has no other symptom than a bill")
    p.add_argument("--heartbeat", type=int, default=None, metavar="N",
                   help="write a ledger line every N requests, whether or not "
                        "anything was removed; 0 turns it off (default 200). "
                        "Without it the ledger records only successes, and a "
                        "filter that has stopped filtering looks exactly like a "
                        "quiet week")
    p.add_argument("--verbose", action="store_true",
                   help="one stderr line per filtered request")
    p.add_argument("--force", action="store_true",
                   help="run without WINNOW_FILTER=1")
    p.set_defaults(func=cmd_filter)


def cmd_trial(args: argparse.Namespace) -> int:
    """`winnow trial` — the A/B, priced from the bill rather than from the model."""
    from . import trial as trial_mod

    if args.trial_action == "arm":
        path = Path(args.ledger).expanduser() if args.ledger else trial_mod.DEFAULT_ARMS
        arm = trial_mod.record_arm(path, args.label, args.note or "")
        print(f"arm '{arm.label}' in force from now. Sessions whose first billed turn "
              f"lands after this are attributed to it.")
        print(f"  {path}")
        return 0

    from .report import trial_command

    code, output = trial_command(
        corpus=args.corpus,
        arms=args.ledger,
        tasks=args.tasks,
        as_json=args.json,
    )
    print(output, file=sys.stderr if code == EXIT_USAGE else sys.stdout)
    return code


def add_trial_subparser(sub) -> None:
    """Register `winnow trial` — which configuration actually costs less here.

    Its own group because it answers a question neither `inspect` nor `savings`
    can. Those two price a cut against COZEMPIC §3.5's cost model: one prices a
    cut that has not happened, the other the cuts that have, and both report a
    counterfactual because the bytes were never sent. That is the right shape for
    "what would this have saved" and the wrong shape for "which of these should I
    run", because both candidates are scored by the same model and a model cannot
    referee itself — the two figures it separates differ by 1.1×.

    So this one models nothing. It reads `message.usage` off the transcripts,
    attributes each session to whichever arm was switched on at the time, and
    divides. It writes only its own arm ledger and never touches a transcript.
    """
    p = sub.add_parser(
        "trial",
        help="compare configurations on what they were actually billed",
        description="Mark which configuration is live, then compare arms on "
                    "billed usage rather than on the cost model. Nothing here is "
                    "modelled and nothing here is a saving: it is what each arm "
                    "cost. Interleave the arms — day on, day off — so the "
                    "difference between them is noise rather than the week.",
    )
    trial_sub = p.add_subparsers(dest="trial_action", required=True)

    arm = trial_sub.add_parser(
        "arm",
        help="record that a configuration went live now",
        description="Append one line to the arm ledger. A session is attributed "
                    "to whichever arm was in force when its first turn was "
                    "billed, so this has to be run when the configuration "
                    "changes — a transcript does not carry the configuration "
                    "that produced it, and nothing can reconstruct it later.",
    )
    arm.add_argument("--label", required=True, metavar="NAME",
                     help="what is running now, e.g. pruner-only, filter-only, "
                          "fork, none")
    arm.add_argument("--note", default=None,
                     help="the exact settings, for when you read this back")
    arm.add_argument("--ledger", default=None, metavar="PATH",
                     help=f"arm ledger (default {trial_mod_default()})")
    arm.set_defaults(func=cmd_trial)

    rep = trial_sub.add_parser(
        "report",
        help="what each arm cost, per session, per turn and per task",
        description="Read every transcript under --corpus, attribute each to an "
                    "arm, and report billed tokens and dollars. $/task is the "
                    "only column that decides anything and the only one a "
                    "transcript cannot supply, so pass --tasks.",
    )
    rep.add_argument("--corpus", required=True, metavar="DIR",
                     help="a projects directory, a directory of transcripts, or "
                          "one file. No default: a trial that silently pointed at "
                          "the wrong tree would produce numbers that look right.")
    rep.add_argument("--ledger", default=None, metavar="PATH",
                     help=f"arm ledger (default {trial_mod_default()})")
    rep.add_argument("--tasks", action="append", metavar="ARM=N",
                     help="how many tasks that arm actually finished. Repeatable. "
                          "Without it $/task is blank and the report says why.")
    rep.add_argument("--json", action="store_true")
    rep.set_defaults(func=cmd_trial)


def trial_mod_default() -> str:
    from . import trial as trial_mod

    return str(trial_mod.DEFAULT_ARMS)


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
    add_trial_subparser(sub)
    return parser


# Groups this tree owns. Everything else falls through to the inherited CLI.
_OWN_GROUPS = ("safe", "inspect", "plan", "fork", "recover", "filter", "savings",
               "trial")


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
