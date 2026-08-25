"""Tests for the resume harness — its accounting, and its `--dry-run` plumbing.

Nothing here spawns `claude` or reads `~/.claude/projects/`, and that is the
constraint the harness was written around rather than a concession the tests
make. What cannot be tested here is the only thing that needs a model: whether a
fork actually resumes. docs/MILESTONE-2-VALIDATION.md is how that gets answered,
and a green run of this file is not an answer to it.
"""

from __future__ import annotations

import json
import time

import pytest

from winnow.validate import corpus
from winnow.validate.resume import (
    ERROR,
    FAIL,
    PASS,
    REFUSED,
    Attempt,
    Ledger,
    attempt_one,
    render,
    resume_argv,
    run,
    summarise,
)

from .test_inspect import BIG, call, padding, write

# Far enough ahead that a transcript written this instant is past the default
# cold-age guard. Without it every fixture session refuses, and the harness would
# be tested only on its refusal path.
LATER = 86_400


def corpus_of(tmp_path, count: int = 3):
    """`count` sessions that tier CB has something to strip in."""
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    for index in range(count):
        records = [
            *call("g", "Glob", {"pattern": "**/*.py"}, BIG),
            *call("b0", "Bash", {"command": "cat notes.md"}, BIG),
            *call("b1", "Bash", {"command": "cat other.md"}, BIG),
            *padding(8),
        ]
        write(root, records, f"0000000{index}-1111-2222-3333-44445555666{index}.jsonl")
    return root.parent


def ok(argv, timeout):
    return 0, "OK"


def broken(argv, timeout):
    return 1, "Error: no conversation found with session ID"


# ─── The dry run: everything except the model ────────────────────────────────


def test_dry_run_writes_forks_and_a_ledger_but_spawns_nothing(tmp_path):
    root = corpus_of(tmp_path, 3)
    ledger_path = tmp_path / "ledger.jsonl"
    ledger, summary = run(
        root, ledger_path, forks=100, dry_run=True, now=time.time() + LATER
    )

    assert summary["passed"] == 3
    assert summary["failed"] == 0
    assert summary["dry_run"] is True
    # A dry run's zero failures are a fact about a stub, and the summary has to
    # say so or the number reads as the guardrail SPEC §9 asked for.
    assert summary["guardrail_met"] is False

    forks = [t for t in corpus.transcripts(root) if t.is_fork]
    assert len(forks) == 3, "the fork is plumbing and the dry run should prove it"
    for attempt in ledger.attempts:
        assert attempt.fork_path, "every attempt records the fork it made"
        assert attempt.argv == resume_argv(attempt.fork_session)
        assert "dry run" in attempt.stdout_tail


def test_the_ledger_makes_an_interrupted_run_resumable(tmp_path):
    root = corpus_of(tmp_path, 3)
    ledger_path = tmp_path / "ledger.jsonl"
    first, _ = run(root, ledger_path, forks=1, dry_run=True, now=time.time() + LATER)
    assert len(first.attempts) == 1

    second, summary = run(
        root, ledger_path, forks=3, dry_run=True, now=time.time() + LATER
    )
    assert len(second.attempts) == 3
    assert summary["forks_attempted"] == 3
    sources = [a.source_path for a in second.attempts]
    assert len(set(sources)) == 3, "a resumed run must not re-fork what it already did"

    reread = Ledger(ledger_path)
    assert [a.source_path for a in reread.attempts] == sources


def test_a_run_stops_at_the_fork_count_rather_than_at_the_corpus(tmp_path):
    root = corpus_of(tmp_path, 5)
    _, summary = run(
        root, tmp_path / "ledger.jsonl", forks=2, dry_run=True,
        now=time.time() + LATER,
    )
    assert summary["forks_attempted"] == 2
    assert len(corpus.sources(root)) == 5, "and it left the rest of the corpus alone"


def test_a_ledger_from_another_version_is_refused_rather_than_half_read(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(
        json.dumps({"source_session": "s", "source_path": "p", "outcome": PASS,
                    "invented_field": 1}) + "\n"
    )
    with pytest.raises(ValueError, match="unknown field"):
        Ledger(ledger_path)

    ledger_path.write_text("{not json\n")
    with pytest.raises(ValueError, match="unreadable ledger line"):
        Ledger(ledger_path)


# ─── What a refusal is, and what it is not ───────────────────────────────────


def test_a_refused_session_is_not_a_pass_and_not_a_failure(tmp_path):
    """A session winnow will not fork produced no fork, so it can do neither.

    Counting it either way would be wrong in a different direction: as a pass it
    inflates a guardrail about forks with sessions that were never forked, as a
    failure it reports winnow's own guard working as the tool being broken.
    """
    root = corpus_of(tmp_path, 1)
    # `now` left at the wall clock, so the fixture written a moment ago is warm.
    _, summary = run(root, tmp_path / "ledger.jsonl", forks=100, dry_run=True)
    assert summary["forks_attempted"] == 0
    assert summary["refused"] == 1
    assert summary["passed"] == summary["failed"] == 0
    assert summary["refused_by_guard"] == {"cold-age": 1}
    assert summary["guardrail_met"] is False


def test_a_session_with_nothing_to_strip_is_refused_not_forked(tmp_path):
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    write(root, list(padding(4)), "aaaaaaaa-1111-2222-3333-444455556666.jsonl")
    _, summary = run(
        root.parent, tmp_path / "ledger.jsonl", forks=100, dry_run=True,
        now=time.time() + LATER,
    )
    assert summary["refused_by_guard"] == {"nothing-to-do": 1}


def test_a_malformed_transcript_refuses_under_its_guard_without_ending_the_run(tmp_path):
    """A parse error is winnow's `parse` guard, not the harness falling over.

    Worth pinning because the two look identical from outside — both leave the
    session unforked — and only one of them is a bug. A refusal shrinks the
    population and is reported as such; an error means winnow or this script
    broke on input a real corpus contains.
    """
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    (root / "aaaaaaaa-1111-2222-3333-444455556666.jsonl").write_text("{ not json\n")
    good = [
        *call("b0", "Bash", {"command": "cat notes.md"}, BIG),
        *call("b1", "Bash", {"command": "cat other.md"}, BIG),
        *padding(8),
    ]
    write(root, good, "bbbbbbbb-1111-2222-3333-444455556666.jsonl")

    _, summary = run(
        root.parent, tmp_path / "ledger.jsonl", forks=100, dry_run=True,
        now=time.time() + LATER,
    )
    assert summary["errors"] == 0
    assert summary["refused_by_guard"] == {"parse": 1}
    assert summary["passed"] == 1, "one bad transcript must not cost the others"
    assert summary["guardrail_met"] is False


def test_a_session_the_harness_cannot_read_at_all_is_an_error(tmp_path):
    result = attempt_one(tmp_path / "gone.jsonl", now=time.time() + LATER)
    assert result.outcome == ERROR
    assert "FileNotFoundError" in result.reason
    assert summarise([result], target=1)["guardrail_met"] is False


def test_a_fork_is_never_itself_forked(tmp_path):
    root = corpus_of(tmp_path, 2)
    run(root, tmp_path / "one.jsonl", forks=100, dry_run=True, now=time.time() + LATER)
    _, second = run(
        root, tmp_path / "two.jsonl", forks=100, dry_run=True, now=time.time() + LATER
    )
    # The two forks the first run wrote sit in the same directory. Forking them
    # would measure winnow against its own output: the second pass has almost
    # nothing left to strip, so it would report a resume of a barely-changed file
    # against a guardrail that is about changed ones.
    assert second["forks_attempted"] == 2
    # And it says how many it dropped, because `is_fork` is a heuristic and its
    # false positives shrink the population without anything else noticing.
    assert second["population"] == 2
    assert second["excluded_as_forks"] == 2
    assert "excluded as winnow's own forks" in render(second)


# ─── The arithmetic, over hand-built attempts ────────────────────────────────


def attempt(outcome: str, name: str = "s", **kw) -> Attempt:
    return Attempt(name, f"/c/{name}.jsonl", outcome, **kw)


def test_the_guardrail_needs_the_full_count_and_not_merely_no_failures():
    forty = [attempt(PASS, f"s{i}") for i in range(40)]
    assert summarise(forty, target=100)["guardrail_met"] is False
    assert summarise(forty, target=100)["shortfall"] == 60
    assert summarise(forty, target=40)["guardrail_met"] is True

    hundred = [attempt(PASS, f"s{i}") for i in range(100)]
    assert summarise(hundred, target=100)["guardrail_met"] is True


def test_one_failure_is_enough_to_miss_the_guardrail():
    attempts = [attempt(PASS, f"s{i}") for i in range(99)]
    attempts.append(attempt(FAIL, "bad", exit_code=1, reason="exited 1",
                            fork_path="/c/bad-fork.jsonl", fork_session="bad-fork"))
    summary = summarise(attempts, target=100)
    assert summary["forks_attempted"] == 100
    assert summary["guardrail_met"] is False
    assert summary["failures"] == [
        {
            "source_session": "bad",
            "source_path": "/c/bad.jsonl",
            "fork_session": "bad-fork",
            "fork_path": "/c/bad-fork.jsonl",
            "exit_code": 1,
            "reason": "exited 1",
            "stdout_tail": "",
        }
    ]


def test_refusals_and_harness_errors_do_not_count_towards_the_forks():
    attempts = [
        *[attempt(PASS, f"s{i}") for i in range(3)],
        attempt(REFUSED, "warm", guard="cold-age"),
        attempt(REFUSED, "warm2", guard="cold-age"),
        attempt(REFUSED, "compacted", guard="compacted"),
        attempt(ERROR, "broken", reason="ValueError: bad"),
    ]
    summary = summarise(attempts, target=3)
    assert summary["forks_attempted"] == 3
    assert summary["refused"] == 3
    assert summary["refused_by_guard"] == {"cold-age": 2, "compacted": 1}
    # An error is the harness or winnow breaking, not a guard doing its job, so
    # it blocks the guardrail even when the fork count is met.
    assert summary["guardrail_met"] is False


def test_the_readout_names_the_failing_fork_and_the_kill_criterion():
    attempts = [attempt(FAIL, "bad", exit_code=1, reason="`claude --resume` exited 1",
                        fork_path="/c/bad-fork.jsonl", fork_session="bad-fork",
                        stdout_tail="no conversation found")]
    text = render(summarise(attempts, target=1))
    assert "GUARDRAIL NOT MET" in text
    assert "/c/bad-fork.jsonl" in text
    assert "G5" in text, "the reader has to be told what an unresumable fork means"
    assert "no conversation found" in text


def test_the_readout_refuses_to_suggest_loosening_the_cold_age_guard():
    """MILESTONES makes loosening `--min-cold-age` to get results a kill condition.

    A run that comes up short is exactly when somebody reaches for that flag, so
    the shortfall message is where the warning has to be.
    """
    text = render(summarise([attempt(PASS, f"s{i}") for i in range(4)], target=100))
    assert "kill condition" in text
    assert "--min-cold-age" in text


def test_a_spawn_that_fails_is_recorded_with_its_output(tmp_path):
    root = corpus_of(tmp_path, 1)
    path = corpus.sources(root)[0]
    result = attempt_one(path, spawn=broken, now=time.time() + LATER)
    assert result.outcome == FAIL
    assert result.exit_code == 1
    assert "no conversation found" in result.stdout_tail
    assert result.fork_path, "a failed resume still names the fork to inspect"


def test_a_spawn_that_succeeds_is_a_pass(tmp_path):
    root = corpus_of(tmp_path, 1)
    path = corpus.sources(root)[0]
    result = attempt_one(path, spawn=ok, now=time.time() + LATER)
    assert result.outcome == PASS
    assert result.dry_run is False
    assert result.argv[:2] == ["claude", "--resume"]
