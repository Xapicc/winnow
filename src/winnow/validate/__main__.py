"""`python -m winnow.validate …` — the three measurements code cannot make alone.

Deliberately not a `winnow` subcommand. `resume` spawns `claude`, and SPEC §3
keeps winnow out of the spawn path so that the tool cannot break a run it is not
part of; putting a spawn behind `winnow …` would make that untrue the moment
somebody typed it by accident. The other two are here for company: they belong to
the milestone rather than to the tool, and the tool should not grow surface that
only a validation run uses.

Exit codes extend SPEC §8's rather than reinterpreting them: 0 success, 1 usage
error, and **4 for "the measurement ran and the bar was missed"**. A harness that
exits 0 on a failed guardrail is one `&&` away from being read as a pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..fork import DEFAULT_MIN_COLD_AGE
from . import corpus, disk, resume, sample, score

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_BAR_MISSED = 4


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def cmd_resume(args: argparse.Namespace) -> int:
    _, summary = resume.run(
        Path(args.corpus),
        Path(args.ledger),
        forks=args.forks,
        tier=args.tier,
        min_cold_age=args.min_cold_age,
        timeout=args.timeout,
        prompt=args.prompt,
        dry_run=args.dry_run,
        on_attempt=lambda a: print(
            f"  {a.outcome:<8} {a.source_session}"
            + (f"  → {a.fork_session}" if a.fork_session else "")
            + (f"  {a.reason}" if a.reason else ""),
            file=sys.stderr,
            flush=True,
        ),
    )
    _write(Path(args.results), json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(resume.render(summary))
    print(f"\nledger  {args.ledger}\nresults {args.results}")
    if summary["dry_run"]:
        return EXIT_OK
    return EXIT_OK if summary["guardrail_met"] else EXIT_BAR_MISSED


def cmd_sample(args: argparse.Namespace) -> int:
    root = Path(args.corpus)
    paths = corpus.sources(root)
    if not paths:
        print(f"winnow: no transcripts to sample under {root}", file=sys.stderr)
        return EXIT_USAGE
    candidates = sample.collect(
        paths,
        tier=args.tier,
        before=args.context_before,
        after=args.context_after,
        i_know=args.i_know,
        on_error=lambda path, exc: print(
            f"  skipped {path}: {type(exc).__name__}: {exc}", file=sys.stderr
        ),
    )
    if not candidates:
        print(
            f"winnow: no result in {len(paths):,} session(s) met a rule at tier "
            f"{args.tier}; there is nothing to label.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    available: dict[str, int] = {}
    for candidate in candidates:
        available[candidate.rule] = available.get(candidate.rule, 0) + 1
    drawn = sample.draw(candidates, target=args.target, seed=args.seed)
    key_path, sheet_path = Path(args.key), Path(args.sheet)
    meta = sample.build_meta(root, args.tier, args.seed, key_path, args.target,
                             drawn, available)
    _write(sheet_path, sample.render_sheet(drawn, meta))
    _write(key_path, sample.render_key(drawn, meta))

    print(f"drew {len(drawn):,} of {args.target:,} from {len(candidates):,} "
          f"candidate(s) in {len(paths):,} session(s)")
    for rule, count in meta["drawn_by_rule"].items():
        print(f"  {rule}  {count:>4,} of {available[rule]:,} available")
    if len(drawn) < args.target:
        print(f"\nSHORT by {args.target - len(drawn):,}: the corpus does not hold "
              f"{args.target:,} strippable results at tier {args.tier}. Widen the "
              "corpus rather than the tier — a sample topped up from tier A is "
              "not a sample of what tier CB does.")
    print(f"\nsheet {sheet_path}  — fill this in, blind")
    print(f"key   {key_path}  — do not open until the sheet is filled")
    return EXIT_OK


def cmd_score(args: argparse.Namespace) -> int:
    try:
        scoring = score.score_files(Path(args.sheet), Path(args.key))
    except score.SheetError as exc:
        print(f"winnow: {exc}", file=sys.stderr)
        return EXIT_USAGE
    _write(Path(args.results), json.dumps(scoring, indent=2, sort_keys=True) + "\n")
    print(score.render(scoring))
    print(f"\nresults {args.results}")
    if scoring["verdict"] == "pass" and not scoring["rules_below_bar"]:
        return EXIT_OK
    return EXIT_BAR_MISSED


def cmd_disk(args: argparse.Namespace) -> int:
    series_path = Path(args.series)
    record = disk.measure(Path(args.corpus), [Path(p) for p in args.ledger])
    if not args.no_append:
        disk.append_series(series_path, record)
    series = disk.read_series(series_path)
    print(disk.render(record, series))
    if args.results:
        _write(
            Path(args.results),
            json.dumps(
                {"latest": record, "growth": disk.growth(series),
                 "observations": len(series)},
                indent=2, sort_keys=True,
            )
            + "\n",
        )
        print(f"\nresults {args.results}")
    print(f"series  {series_path}  ({len(series):,} observation(s))")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m winnow.validate",
        description="Milestone 2's three unvalidated criteria. See "
                    "docs/MILESTONE-2-VALIDATION.md.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "resume",
        help="fork a corpus and resume each fork — SPEC §9's 100 forks, 0 failures",
    )
    p.add_argument("--corpus", required=True,
                   help="a projects directory, a directory of transcripts, or one file")
    p.add_argument("--ledger", required=True,
                   help="append-only record of every attempt; re-run to resume it")
    p.add_argument("--results", required=True, help="where the JSON summary is written")
    p.add_argument("--forks", type=int, default=100,
                   help="how many forks to resume (default 100, SPEC §9)")
    p.add_argument("--tier", default="CB")
    p.add_argument("--min-cold-age", type=int, default=DEFAULT_MIN_COLD_AGE,
                   help="do not lower this to get results; MILESTONES makes "
                        "loosening it a kill condition in its own right")
    p.add_argument("--timeout", type=int, default=resume.DEFAULT_TIMEOUT)
    p.add_argument("--prompt", default=resume.RESUME_PROMPT)
    p.add_argument("--dry-run", action="store_true",
                   help="fork and write as usual, but record the resume command "
                        "instead of spawning it. Proves the plumbing; proves "
                        "nothing about whether a fork resumes")
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("sample", help="draw the stratified 200 and write a blind sheet")
    p.add_argument("--corpus", required=True)
    p.add_argument("--sheet", required=True, help="the blind sheet, for a human")
    p.add_argument("--key", required=True,
                   help="the answer key; do not open it until the sheet is filled")
    p.add_argument("--target", type=int, default=sample.DEFAULT_TARGET)
    p.add_argument("--seed", type=int, default=0,
                   help="the draw is deterministic for a given seed and corpus")
    p.add_argument("--tier", default="CB")
    p.add_argument("--context-before", type=int, default=sample.DEFAULT_CONTEXT_BEFORE)
    p.add_argument("--context-after", type=int, default=sample.DEFAULT_CONTEXT_AFTER)
    p.add_argument("--i-know", action="store_true",
                   help="required to sample tier A (SPEC §8)")
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("score", help="read the filled sheet back and report precision")
    p.add_argument("--sheet", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--results", required=True)
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("disk", help="one observation of what accumulated forks cost")
    p.add_argument("--corpus", required=True)
    p.add_argument("--series", required=True,
                   help="the series this observation is appended to; the series is "
                        "the measurement, one observation is not")
    p.add_argument("--ledger", action="append", default=[],
                   help="a resume ledger, to pair forks to their sources; repeatable")
    p.add_argument("--results", help="optional JSON summary of the latest observation")
    p.add_argument("--no-append", action="store_true",
                   help="report without adding an observation to the series")
    p.set_defaults(func=cmd_disk)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"winnow: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
