"""The 100-fork resume test: SPEC §9's guardrail of **100 forks, 0 failures**.

Fork each session in a corpus, ask `claude --resume <new-id> -p 'reply OK'` to
resume the fork, and count. The criterion is not "most of them work": one
unresumable fork is a milestone 2 kill condition unless a same-day change to
guard G5 fixes it (MILESTONES), so the harness's job is to make a single failure
findable rather than to produce a percentage.

Three properties the run needs and this file provides:

**Interruptible.** Every attempt is appended to a ledger the moment it finishes.
Re-running with the same ledger skips what is already in it, so a run killed at
attempt 60 resumes at 61 rather than re-spawning sixty models.

**Every fork is recorded.** The ledger holds the source path, the fork path and
the fork's session id for every attempt, passed or failed. A failure is
inspectable afterwards because the file that failed is still on disk and named —
winnow adds files and never removes them (SPEC §3).

**The count is of forks, not of sessions.** A session winnow refuses to fork
produced no fork and cannot pass or fail a resume; it shrinks the population.
The harness keeps drawing until it has `--forks` actual forks or the corpus runs
out, and says which. A refusal is reported under the guard that raised it,
because the guard that most often will is `cold-age`, and MILESTONES makes
loosening `--min-cold-age` to get results *itself* a kill condition — a run that
came up short must be visible as a run that came up short.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..fork import DEFAULT_MIN_COLD_AGE, build_fork, write_fork
from ..plan import build_plan, resolve_selection
from . import corpus

# What the resumed session is asked to do. Deliberately the smallest prompt that
# still forces a full turn: the fork resumes, the whole conversation is re-sent,
# and the model answers. Anything more would be testing the model rather than
# whether the transcript winnow wrote is one the CLI can load.
RESUME_PROMPT = "reply OK"

# Long enough for a large transcript to be uploaded and a short turn taken, short
# enough that one hung resume does not stall a hundred-fork run overnight. A
# timeout is recorded as a failure, not skipped: from the outside, a fork that
# never comes back is not resumable.
DEFAULT_TIMEOUT = 300

# How much of the resumed session's output the ledger keeps per attempt. Enough
# to see the error that ended a failed resume, bounded because a transcript's own
# content can come back through it and the ledger is a file on disk (SPEC §10).
STDOUT_TAIL_CHARS = 2000

PASS = "pass"
FAIL = "fail"
REFUSED = "refused"
ERROR = "error"


@dataclass(frozen=True)
class Attempt:
    """One session: what winnow did with it, and what happened when it resumed."""

    source_session: str
    source_path: str
    outcome: str
    reason: str = ""
    fork_session: str = ""
    fork_path: str = ""
    guard: str = ""
    exit_code: int | None = None
    duration_seconds: float | None = None
    stdout_tail: str = ""
    argv: list[str] = field(default_factory=list)
    dry_run: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


class Ledger:
    """The append-only record of every attempt, and what makes a run resumable."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.attempts: list[Attempt] = []
        if path.exists():
            self.attempts = list(_read_ledger(path))

    @property
    def attempted(self) -> set[str]:
        """Source paths already tried, in any outcome.

        Keyed by path rather than by session id because a corpus can hold two
        projects with the same transcript name, and re-forking one of them
        because the other was done would silently drop a session from the count.
        """
        return {a.source_path for a in self.attempts}

    @property
    def forks(self) -> int:
        return sum(1 for a in self.attempts if a.outcome in (PASS, FAIL))

    def record(self, attempt: Attempt) -> None:
        """Append one attempt and flush it.

        Written and flushed per attempt rather than at the end, because the whole
        point of the ledger is to survive the run being killed, and a buffered
        ledger loses exactly the attempts a crash makes interesting.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(attempt.to_json() + "\n")
            handle.flush()
        self.attempts.append(attempt)


def _read_ledger(path: Path):
    """Parse a ledger, refusing a line it cannot read rather than skipping it.

    A ledger with an unreadable line has an unknown number of attempts in it, and
    a resumed run that guessed would re-fork sessions it had already forked or
    skip ones it had not. Both corrupt the count the guardrail is about.
    """
    for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number}: unreadable ledger line: {exc}") from exc
        known = {f for f in Attempt.__dataclass_fields__}
        unknown = set(payload) - known
        if unknown:
            raise ValueError(
                f"{path}:{number}: ledger written by a different version — "
                f"unknown field(s) {', '.join(sorted(unknown))}"
            )
        yield Attempt(**payload)


def _spawn(argv: list[str], timeout: int) -> tuple[int, str]:
    """Run the resume and return `(exit code, combined output)`.

    The one place in winnow that starts a process. It is here, in a harness the
    tool itself never imports, rather than behind a subcommand: SPEC §3 keeps
    winnow out of the spawn path so it cannot break a run, and a measurement of
    whether forks resume is not the tool.
    """
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, f"{exc}"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def _dry_spawn(argv: list[str], timeout: int) -> tuple[int, str]:
    """The `--dry-run` stand-in: report the command, spawn nothing.

    Exit 0 so the plumbing either side of the spawn — fork, write, ledger,
    summary — runs the same code it will on the day. The summary knows the run
    was dry and refuses to call the guardrail met, so the zero is never mistaken
    for a measurement.
    """
    return 0, f"dry run: would have run {' '.join(argv)} (timeout {timeout}s)"


def resume_argv(fork_session: str, prompt: str = RESUME_PROMPT) -> list[str]:
    """The command the guardrail is about."""
    return ["claude", "--resume", fork_session, "-p", prompt]


def attempt_one(
    path: Path,
    *,
    tier: str = "CB",
    min_cold_age: int = DEFAULT_MIN_COLD_AGE,
    timeout: int = DEFAULT_TIMEOUT,
    prompt: str = RESUME_PROMPT,
    dry_run: bool = False,
    spawn=None,
    now: float | None = None,
) -> Attempt:
    """Fork one session and try to resume the fork.

    Never raises: a corpus of real transcripts contains malformed ones, and a
    hundred-fork run that dies on the fourteenth has measured nothing. Anything
    that goes wrong becomes an `error` attempt carrying its reason, which is a
    result the ledger can hold and a person can read.
    """
    spawn = (_dry_spawn if dry_run else _spawn) if spawn is None else spawn
    session = path.stem
    try:
        selection = resolve_selection(tier)
        plan = build_plan(path, tier=tier, rules=selection)
        result, refusals = build_fork(plan, now=now, min_cold_age=min_cold_age)
    except (ValueError, OSError) as exc:
        return Attempt(session, str(path), ERROR, reason=f"{type(exc).__name__}: {exc}")

    if refusals:
        first = refusals[0]
        return Attempt(
            session, str(path), REFUSED, reason=first.reason, guard=first.guard,
            fork_session=result.new_session_id, dry_run=dry_run,
        )
    if not plan.strips:
        return Attempt(
            session, str(path), REFUSED,
            reason=f"nothing to do — no result met a rule at tier {tier}",
            guard="nothing-to-do", fork_session=result.new_session_id,
            dry_run=dry_run,
        )

    try:
        write_fork(result)
    except (ValueError, OSError) as exc:
        return Attempt(
            session, str(path), ERROR, reason=f"{type(exc).__name__}: {exc}",
            fork_session=result.new_session_id, fork_path=str(result.out_path),
            dry_run=dry_run,
        )

    argv = resume_argv(result.new_session_id, prompt)
    started = time.monotonic()
    code, output = spawn(argv, timeout)
    elapsed = round(time.monotonic() - started, 3)
    return Attempt(
        source_session=session,
        source_path=str(path),
        outcome=PASS if code == 0 else FAIL,
        reason="" if code == 0 else f"`claude --resume` exited {code}",
        fork_session=result.new_session_id,
        fork_path=str(result.out_path),
        exit_code=code,
        duration_seconds=elapsed,
        stdout_tail=output[-STDOUT_TAIL_CHARS:],
        argv=argv,
        dry_run=dry_run,
    )


def run(
    root: Path,
    ledger_path: Path,
    *,
    forks: int = 100,
    tier: str = "CB",
    min_cold_age: int = DEFAULT_MIN_COLD_AGE,
    timeout: int = DEFAULT_TIMEOUT,
    prompt: str = RESUME_PROMPT,
    dry_run: bool = False,
    spawn=None,
    now: float | None = None,
    on_attempt=None,
) -> tuple[Ledger, dict]:
    """Work through the corpus until `forks` forks have been resumed, or it runs out.

    Returns the ledger and the summary. `on_attempt` is called with each attempt
    as it lands, which is how the CLI prints progress without this function
    knowing what a terminal is.
    """
    ledger = Ledger(ledger_path)
    done = ledger.attempted
    found = corpus.transcripts(root)
    population = [t.path for t in found if not t.is_fork]
    for path in population:
        if ledger.forks >= forks:
            break
        if str(path) in done:
            continue
        attempt = attempt_one(
            path, tier=tier, min_cold_age=min_cold_age, timeout=timeout,
            prompt=prompt, dry_run=dry_run, spawn=spawn, now=now,
        )
        ledger.record(attempt)
        if on_attempt is not None:
            on_attempt(attempt)
    return ledger, summarise(
        ledger.attempts,
        target=forks,
        population=len(population),
        excluded_as_forks=len(found) - len(population),
    )


def summarise(
    attempts: list[Attempt],
    target: int = 100,
    population: int | None = None,
    excluded_as_forks: int = 0,
) -> dict:
    """The pass/fail count, the failures named, and whether the guardrail is met.

    `met` is three conditions and not one. It needs zero failures, it needs the
    full `target` forks — SPEC §9 says 100, and 40 forks with no failure is a
    smaller claim wearing the same words — and it needs the run not to have been
    dry. A dry run's zero failures are a fact about a stub.

    `excluded_as_forks` is reported because `corpus.is_fork` is a heuristic whose
    false positives are silent: a source transcript mistaken for a fork drops out
    of the population without anything saying so. A session that once printed a
    winnow pointer to its terminal is the case that would do it. An exclusion
    count that looks too large is the only warning available.
    """
    outcomes = Counter(a.outcome for a in attempts)
    forks = outcomes[PASS] + outcomes[FAIL]
    dry = any(a.dry_run for a in attempts if a.outcome in (PASS, FAIL))
    shortfall = max(0, target - forks)
    return {
        "target_forks": target,
        "population": population,
        "excluded_as_forks": excluded_as_forks,
        "forks_attempted": forks,
        "passed": outcomes[PASS],
        "failed": outcomes[FAIL],
        "refused": outcomes[REFUSED],
        "errors": outcomes[ERROR],
        "shortfall": shortfall,
        "dry_run": dry,
        "guardrail_met": (
            not dry and outcomes[FAIL] == 0 and outcomes[ERROR] == 0 and shortfall == 0
        ),
        "refused_by_guard": dict(
            sorted(Counter(a.guard for a in attempts if a.outcome == REFUSED).items())
        ),
        "failures": [
            {
                "source_session": a.source_session,
                "source_path": a.source_path,
                "fork_session": a.fork_session,
                "fork_path": a.fork_path,
                "exit_code": a.exit_code,
                "reason": a.reason,
                "stdout_tail": a.stdout_tail,
            }
            for a in attempts
            if a.outcome == FAIL
        ],
        "harness_errors": [
            {
                "source_session": a.source_session,
                "source_path": a.source_path,
                "reason": a.reason,
            }
            for a in attempts
            if a.outcome == ERROR
        ],
    }


def render(summary: dict) -> str:
    """The readout. Leads with the verdict, because that is the whole output."""
    out: list[str] = []
    add = out.append
    add(f"resume test       {summary['passed']:,} passed, {summary['failed']:,} failed "
        f"of {summary['forks_attempted']:,} forks (target {summary['target_forks']:,})")
    if summary.get("population") is not None:
        add(f"population        {summary['population']:,} source transcript(s)"
            + (f", {summary['excluded_as_forks']:,} excluded as winnow's own forks"
               if summary["excluded_as_forks"] else ""))
    add(f"refused           {summary['refused']:,} session(s) produced no fork")
    for guard, count in summary["refused_by_guard"].items():
        add(f"                  {guard}: {count:,}")
    if summary["errors"]:
        add(f"harness errors    {summary['errors']:,} — the harness broke, not the fork")

    add("")
    if summary["dry_run"]:
        add("DRY RUN — no model was called. This proves the plumbing and nothing "
            "about whether a fork resumes.")
    elif summary["guardrail_met"]:
        add(f"GUARDRAIL MET — {summary['target_forks']:,} forks, 0 failures (SPEC §9).")
    else:
        add("GUARDRAIL NOT MET.")
        if summary["failed"]:
            add(f"  {summary['failed']:,} fork(s) did not resume. MILESTONES: an "
                "unresumable fork stops milestone 2 unless a same-day change to "
                "G5 fixes it.")
        if summary["shortfall"]:
            add(f"  {summary['shortfall']:,} fork(s) short of the target. Do not "
                "reach for --min-cold-age: MILESTONES makes loosening the guard "
                "to get results a kill condition in its own right.")
        if summary["errors"]:
            add(f"  {summary['errors']:,} session(s) the harness could not process "
                "at all; these are bugs in winnow or in this script.")

    for failure in summary["failures"]:
        add("")
        add(f"FAILED {failure['source_session']}")
        add(f"  source {failure['source_path']}")
        add(f"  fork   {failure['fork_path']}  ({failure['fork_session']})")
        add(f"  {failure['reason']}")
        for line in failure["stdout_tail"].splitlines()[-10:]:
            add(f"  | {line}")
    for broken in summary["harness_errors"]:
        add("")
        add(f"ERROR  {broken['source_session']}: {broken['reason']}")
    return "\n".join(out)
