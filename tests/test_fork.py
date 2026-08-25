"""Tests for `winnow fork` and `winnow recover` — milestone 2's acceptance criteria.

Synthetic transcripts and the checked-in fixtures, for the reason
`test_inspect.py` gives: a real transcript cannot state what the right answer is.
**Nothing here reads `~/.claude/projects/` or runs the `claude` CLI.** The two
validations that need both — the 100-fork resume test and the 200-sample rule
label — are a separate run, and a test that quietly depended on a machine's real
session directory would fail on every other machine rather than reporting that.

The clock is injected through `now=` rather than slept past. `fork` takes it as a
parameter for exactly this reason: the cold-age guard is arithmetic on two
numbers, and a test that proved it by waiting an hour would prove it once.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from winnow.fork import (
    DEFAULT_MIN_COLD_AGE,
    ForkError,
    build_fork,
    derive_session_id,
    fork_command,
    pairing,
    recover_command,
    source_lines,
    write_fork,
)
from winnow.plan import build_plan
from winnow.rules import content_digest

from .test_inspect import BIG
from .test_plan import SESSION, write_session

FIXTURES = Path(__file__).parent / "fixtures" / "sessions"

# Far enough past the source's mtime that the cold-age guard is satisfied without
# any test having to say so. A day, because SPEC §8's default is an hour.
A_DAY = 86_400


def use(uid: str, name: str, tool_input: dict) -> dict:
    """A `tool_use`, carrying `sessionId` so the retitling path is exercised."""
    return {
        "type": "assistant",
        "uuid": f"u-{uid}",
        "sessionId": SESSION,
        "message": {
            "role": "assistant",
            "model": "claude-opus-5",
            "content": [{"type": "tool_use", "id": uid, "name": name, "input": tool_input}],
        },
    }


def result(uid: str, content=BIG, *, is_error: bool = False) -> dict:
    return {
        "type": "user",
        "uuid": f"r-{uid}",
        "sessionId": SESSION,
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": uid,
                    "content": content,
                    "is_error": is_error,
                }
            ],
        },
    }


def call(uid: str, name: str, tool_input: dict, content=BIG, **kw) -> list[dict]:
    return [use(uid, name, tool_input), result(uid, content, **kw)]


def padding(n: int, start: int = 0) -> list[dict]:
    """`n` small trailing calls, so guard G1's --keep-last protects these rather
    than the calls a test is actually about."""
    out: list[dict] = []
    for i in range(n):
        out += call(f"pad{start + i}", "Bash", {"command": f"pytest -k case{i}"}, "ok\n")
    return out


def strippable() -> list[dict]:
    """Two results a CB fork replaces, plus enough padding to clear G1."""
    return (
        call("a", "Bash", {"command": "ls -la /repo"})
        + call("b", "Glob", {"pattern": "**/*.py"})
        + padding(8)
    )


def session_at(directory, records) -> Path:
    """The transcript in its own directory, so a test can watch that directory for
    the one file a `--write` is allowed to add."""
    directory.mkdir(parents=True, exist_ok=True)
    return write_session(directory, records)


def fork_of(tmp_path, records, **kw):
    """`(result, refusals)` for a session that is comfortably cold."""
    path = session_at(tmp_path, records)
    plan = build_plan(path, tier=kw.pop("tier", "CB"), **kw.pop("plan_kw", {}))
    return build_fork(plan, now=path.stat().st_mtime + A_DAY, **kw)


def fingerprint(path: Path) -> tuple[int, str]:
    """What "the original is never touched" means, as two numbers."""
    return path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()


# ─── The original is never touched ───────────────────────────────────────────


def test_the_original_keeps_its_bytes_and_its_mtime_across_a_write(tmp_path):
    """Milestone 2's first acceptance criterion, checked directly rather than by
    reading the code that promises it."""
    path = session_at(tmp_path, strippable())
    before = fingerprint(path)

    code, _ = fork_command(str(path), write=True, now=path.stat().st_mtime + A_DAY)

    assert code == 0
    assert fingerprint(path) == before


def test_a_write_leaves_the_source_directory_holding_exactly_one_more_file(tmp_path):
    path = session_at(tmp_path, strippable())
    fork_command(str(path), write=True, now=path.stat().st_mtime + A_DAY)

    written = sorted(p.name for p in path.parent.iterdir())
    assert len(written) == 2
    assert path.name in written
    # No temporary left behind: SPEC §10's rename is atomic, not a two-file state.
    assert not any(name.endswith(".winnow-tmp") for name in written)


def test_a_refused_fork_writes_nothing_at_all(tmp_path):
    """Warm, so the cold-age guard refuses. The directory must be untouched."""
    path = session_at(tmp_path, strippable())
    code, output = fork_command(str(path), write=True, now=path.stat().st_mtime + 60)

    assert code == 3
    assert "cold-age" in output
    assert [p.name for p in path.parent.iterdir()] == [path.name]


# ─── Guard G5, on every fixture and on a writer that would break it ──────────


@pytest.mark.parametrize("fixture", sorted(p.name for p in FIXTURES.glob("*.jsonl")))
def test_g5_holds_on_every_checked_in_fixture(tmp_path, fixture):
    """`orphaned_tool_results.jsonl` and `corrupted_tool_use.jsonl` exist to break
    a naive writer: one has a `tool_result` whose `tool_use` is not in the file,
    the other a `tool_use` whose name is a quoting attack. Neither may change the
    pairing, and neither may make the writer invent or drop a block."""
    path = tmp_path / fixture
    shutil.copy(FIXTURES / fixture, path)

    plan = build_plan(path, tier="CBA")
    result, refusals = build_fork(plan, now=path.stat().st_mtime + A_DAY)

    source_records = _records(source_lines(path)[0])
    assert pairing(source_records) == pairing(_records(result.lines))
    assert not [r for r in refusals if r.guard == "G5"]


def _records(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            record = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            out.append(record)
    return out


@pytest.mark.parametrize("fixture", sorted(p.name for p in FIXTURES.glob("*.jsonl")))
def test_every_answered_call_is_still_answered_exactly_once(tmp_path, fixture):
    """SPEC §4's own wording of G5, restricted to the calls the source answered.

    A `tool_use` the source never answered stays unanswered — SPEC §3 forbids
    winnow to delete it and it cannot invent a result for it — but no call that
    *had* a result may lose it, gain a second one, or have someone else's.
    """
    path = tmp_path / fixture
    shutil.copy(FIXTURES / fixture, path)

    plan = build_plan(path, tier="CBA")
    result, _ = build_fork(plan, now=path.stat().st_mtime + A_DAY)

    source_uses, source_results = pairing(_records(source_lines(path)[0]))
    fork_uses, fork_results = pairing(_records(result.lines))

    answered = [uid for uid in source_uses if uid in source_results]
    for use_id in answered:
        assert fork_results.count(use_id) == 1
        assert use_id in fork_uses


def test_an_orphaned_tool_result_is_carried_across_rather_than_repaired(tmp_path):
    """SPEC §3 forbids winnow to delete anything, and the orphan is not winnow's
    defect. Preserving the pairing means preserving it as it was found."""
    path = tmp_path / "orphaned_tool_results.jsonl"
    shutil.copy(FIXTURES / "orphaned_tool_results.jsonl", path)

    plan = build_plan(path, tier="CB")
    result, refusals = build_fork(plan, now=path.stat().st_mtime + A_DAY)

    uses, results = pairing(_records(result.lines))
    assert uses == ()
    assert results == ("missing-tool-use-id",)
    assert not refusals


def test_g5_aborts_with_exit_3_and_writes_no_file(tmp_path, monkeypatch):
    """The refusal path itself, forced by a writer that drops a block.

    Patched rather than provoked with a transcript, because a correct writer has
    no input that makes it violate G5 — which is the point of the guard. What is
    under test is that the check catches a broken writer and that the catch
    happens before anything reaches disk.
    """
    from winnow import fork as fork_mod

    real = fork_mod._rewrite

    def drop_a_result(lines, plan, new_session_id):
        rewritten, applied, mismatched = real(lines, plan, new_session_id)
        victim = plan.strips[0].line
        rewritten[victim] = json.dumps({"type": "user", "uuid": "gone",
                                        "message": {"role": "user", "content": "…"}})
        return rewritten, applied, mismatched

    monkeypatch.setattr(fork_mod, "_rewrite", drop_a_result)

    path = session_at(tmp_path, strippable())
    code, output = fork_command(str(path), write=True, now=path.stat().st_mtime + A_DAY)

    assert code == 3
    assert "G5" in output
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_force_never_gets_past_g5(tmp_path, monkeypatch):
    """SPEC §4: G5 is a hard failure. `--force` reaches the soft guards and stops."""
    from winnow import fork as fork_mod

    real = fork_mod._rewrite

    def invent_a_result(lines, plan, new_session_id):
        rewritten, applied, mismatched = real(lines, plan, new_session_id)
        rewritten.insert(0, json.dumps({
            "type": "user", "uuid": "extra",
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "not-in-the-source",
                 "content": "x"}]},
        }))
        return rewritten, applied, mismatched

    monkeypatch.setattr(fork_mod, "_rewrite", invent_a_result)

    path = session_at(tmp_path, strippable())
    code, output = fork_command(str(path), write=True, force=True,
                                now=path.stat().st_mtime + A_DAY)

    assert code == 3
    assert "G5" in output
    assert "--force does not reach" in output
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_a_plan_that_names_bytes_the_transcript_does_not_have_is_refused(tmp_path):
    """The pointer records a sha256 of what it replaced. If the line no longer
    holds those bytes, the pointer would be a lie and the strip irreversible."""
    path = session_at(tmp_path, strippable())
    plan = build_plan(path, tier="CB")

    # Rewrite the source under the plan's feet, as a concurrent session would.
    lines = path.read_text().split("\n")
    victim = plan.strips[0].line
    record = json.loads(lines[victim])
    record["message"]["content"][0]["content"] = "something else entirely"
    lines[victim] = json.dumps(record)
    path.write_text("\n".join(lines))

    _, refusals = build_fork(plan, now=path.stat().st_mtime + A_DAY)

    assert [r.guard for r in refusals] == ["G5"]
    assert not refusals[0].forceable
    assert "sha256" in refusals[0].reason


# ─── --min-cold-age ──────────────────────────────────────────────────────────


def test_a_session_inside_the_window_is_refused_with_exit_3(tmp_path):
    """SPEC §7: the cold-cache argument is the economic case, and this guard is
    what enforces it. MILESTONES.md makes loosening it a kill condition, so it is
    a refusal rather than a warning."""
    path = session_at(tmp_path, strippable())
    code, output = fork_command(str(path), write=True,
                                now=path.stat().st_mtime + DEFAULT_MIN_COLD_AGE - 1)

    assert code == 3
    assert "cold-age" in output
    assert "may still be cached" in output
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_a_session_past_the_window_proceeds(tmp_path):
    path = session_at(tmp_path, strippable())
    code, _ = fork_command(str(path), write=True,
                           now=path.stat().st_mtime + DEFAULT_MIN_COLD_AGE + 1)

    assert code == 0
    assert len(list(path.parent.iterdir())) == 2


def test_the_threshold_moves_with_the_flag(tmp_path):
    path = session_at(tmp_path, strippable())
    warm = path.stat().st_mtime + 120

    assert fork_command(str(path), now=warm, min_cold_age=3600)[0] == 3
    assert fork_command(str(path), now=warm, min_cold_age=60)[0] == 0


def test_force_proceeds_past_a_warm_session_and_says_so(tmp_path):
    path = session_at(tmp_path, strippable())
    code, output = fork_command(str(path), write=True, force=True,
                                now=path.stat().st_mtime + 60)

    assert code == 0
    assert "forced past" in output
    assert "cold-age" in output


def test_a_negative_threshold_is_a_usage_error(tmp_path):
    path = session_at(tmp_path, strippable())
    code, output = fork_command(str(path), min_cold_age=-1)

    assert code == 1
    assert "--min-cold-age" in output


def test_the_age_comes_from_the_newest_record_timestamp_when_there_is_one(tmp_path):
    """A transcript that carries timestamps knows better than its own mtime,
    which a copy or a backup would have reset."""
    records = strippable()
    records[-1]["timestamp"] = "2026-08-25T12:00:00.000Z"
    path = session_at(tmp_path, records)

    plan = build_plan(path, tier="CB")
    result, _ = build_fork(plan, now=1_756_123_200.0)

    assert result.last_activity == pytest.approx(1_787_659_200.0)
    assert "timestamp" in result.last_activity_source


# ─── Guard G4, at the whole-fork level ───────────────────────────────────────


def test_a_fork_that_would_not_shrink_the_file_is_refused(tmp_path):
    """A tool asked to shrink a context must not grow it, checked on the file.

    Driven through a constructed `ForkResult` rather than a transcript, and
    deliberately: no input reaches this branch. Per-result G4 already guarantees
    every strip nets positive, and the writer re-serialises a touched line more
    compactly than `json.dumps`' default spacing, so a real fork's file always
    shrinks — the searched transcripts all came out between −90 and −2,592 bytes.
    The check stays because "the file got bigger" is the failure an operator would
    actually notice, and a guard nothing can currently trip is still worth having
    the day the pointer template or the writer changes. What is under test is that
    it fires, that it names G4, and that `--force` can pass it.
    """
    path = session_at(tmp_path, strippable())
    plan = build_plan(path, tier="CB")
    result, refusals = build_fork(plan, now=path.stat().st_mtime + A_DAY)
    assert not refusals

    from winnow.fork import _refusals

    result.fork_bytes = result.source_bytes + 1
    inflated = _refusals(result, ((), ()), ((), ()),
                         {s.pointer_id for s in plan.strips}, [], A_DAY,
                         DEFAULT_MIN_COLD_AGE)

    assert [r.guard for r in inflated] == ["G4"]
    assert inflated[0].forceable
    assert "must not grow it" in inflated[0].reason


def test_a_fork_whose_pointers_cost_exactly_what_they_remove_is_refused(tmp_path):
    """The literal requirement: a fork that removes fewer bytes than its pointers
    add refuses. Reached at the exact size where per-result G4 stops firing —
    `inflates` is strictly-greater, so a result the same length as its pointer
    survives the per-result check and nets zero."""
    from .test_plan import BOUNDARY

    records = (
        call("a", "Glob", {"pattern": "**/*.py"}, "z" * BOUNDARY)
        + padding(8)
    )
    path = session_at(tmp_path, records)
    plan = build_plan(path, tier="CB", min_bytes=1)

    assert plan.strips, "the boundary result must survive per-result G4"
    assert plan.net_bytes == 0

    code, output = fork_command(str(path), min_bytes=1, write=True,
                                now=path.stat().st_mtime + A_DAY)

    assert code == 3
    assert "G4" in output
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_g4_refuses_when_every_candidate_costs_more_than_it_saves(tmp_path):
    """`--min-bytes 1` lets G2 through, so the only thing between a 30-byte
    result and a 160-byte pointer is G4."""
    records = call("a", "Bash", {"command": "ls -la"}, "tiny output\n") + padding(8)
    path = session_at(tmp_path, records)
    code, output = fork_command(str(path), min_bytes=1, write=True,
                                now=path.stat().st_mtime + A_DAY)

    assert code == 3
    assert "G4" in output
    assert "no net inflation" in output
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_force_proceeds_past_g4(tmp_path):
    records = call("a", "Bash", {"command": "ls -la"}, "tiny output\n") + padding(8)
    path = session_at(tmp_path, records)
    code, output = fork_command(str(path), min_bytes=1, write=True, force=True,
                                now=path.stat().st_mtime + A_DAY)

    assert code in (0, 2)
    if code == 0:
        assert "forced past" in output


def test_a_session_with_nothing_to_strip_exits_2_rather_than_refusing(tmp_path):
    """SPEC §8 separates "no result met a rule" from "a rule met a result and the
    swap was not worth taking". Only the second is a refusal."""
    path = session_at(tmp_path, padding(4))
    code, output = fork_command(str(path), write=True, now=path.stat().st_mtime + A_DAY)

    assert code == 2
    assert "nothing to do" in output
    assert [p.name for p in path.parent.iterdir()] == [path.name]


# ─── Determinism ─────────────────────────────────────────────────────────────


def test_two_runs_with_the_same_flags_produce_byte_identical_forks(tmp_path):
    """SPEC §10. Including the new session ID, which is why it cannot come from a
    clock or a random source."""
    path = session_at(tmp_path, strippable())
    cold = path.stat().st_mtime + A_DAY

    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    assert fork_command(str(path), write=True, out=str(first), now=cold)[0] == 0
    assert fork_command(str(path), write=True, out=str(second), now=cold + 999)[0] == 0

    assert first.read_bytes() == second.read_bytes()


def test_the_new_session_id_is_the_same_on_both_runs(tmp_path):
    path = session_at(tmp_path, strippable())
    cold = path.stat().st_mtime + A_DAY

    first, _ = build_fork(build_plan(path, tier="CB"), now=cold)
    second, _ = build_fork(build_plan(path, tier="CB"), now=cold + 12_345)

    assert first.new_session_id == second.new_session_id
    assert first.out_path == second.out_path


def test_the_id_is_a_well_formed_uuid(tmp_path):
    """`claude --resume` expects to find a UUID as the filename stem."""
    import uuid

    path = session_at(tmp_path, strippable())
    result, _ = build_fork(build_plan(path, tier="CB"), now=path.stat().st_mtime + A_DAY)

    parsed = uuid.UUID(result.new_session_id)
    assert parsed.version == 5


def test_a_different_selection_gets_a_different_id(tmp_path):
    """Two forks that differ in content must not land on the same filename, or one
    silently overwrites the other."""
    path = session_at(tmp_path, strippable())
    cold = path.stat().st_mtime + A_DAY

    cb, _ = build_fork(build_plan(path, tier="CB"), now=cold)
    c_only, _ = build_fork(build_plan(path, tier="C"), now=cold)

    assert cb.new_session_id != c_only.new_session_id


def test_a_different_source_gets_a_different_id(tmp_path):
    """The source's sha256 is in the derivation, so an edited transcript forks to
    a different name even under identical flags."""
    first = session_at(tmp_path / "one", strippable())
    second = session_at(tmp_path / "two", strippable() + padding(1, start=99))

    a, _ = build_fork(build_plan(first, tier="CB"), now=first.stat().st_mtime + A_DAY)
    b, _ = build_fork(build_plan(second, tier="CB"), now=second.stat().st_mtime + A_DAY)

    assert a.new_session_id != b.new_session_id


def test_the_derivation_does_not_depend_on_where_the_file_sits(tmp_path):
    """Same bytes, same session ID, same flags — the fork's name is a property of
    the session, not of the directory it was found in."""
    here = session_at(tmp_path / "here", strippable())
    there = tmp_path / "there" / here.name
    there.parent.mkdir()
    shutil.copy(here, there)

    a = derive_session_id(SESSION, source_lines(here)[1], build_plan(here, tier="CB"))
    b = derive_session_id(SESSION, source_lines(there)[1], build_plan(there, tier="CB"))

    assert a == b


# ─── --out, --write and the opt-in ───────────────────────────────────────────


def test_without_write_nothing_reaches_disk(tmp_path):
    """SPEC §8 gives `fork` no `--dry-run` because dry is the default."""
    path = session_at(tmp_path, strippable())
    code, output = fork_command(str(path), now=path.stat().st_mtime + A_DAY)

    assert code == 0
    assert "would write" in output
    assert "pass --write" in output
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_out_overrides_the_destination(tmp_path):
    path = session_at(tmp_path / "project", strippable())
    destination = tmp_path / "elsewhere" / "fork.jsonl"

    code, _ = fork_command(str(path), write=True, out=str(destination),
                           now=path.stat().st_mtime + A_DAY)

    assert code == 0
    assert destination.exists()
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_the_default_destination_is_the_new_id_beside_the_source(tmp_path):
    path = session_at(tmp_path, strippable())
    result, _ = build_fork(build_plan(path, tier="CB"), now=path.stat().st_mtime + A_DAY)

    assert result.out_path.parent == path.parent
    assert result.out_path.name == f"{result.new_session_id}.jsonl"


def test_rewriting_the_same_fork_is_allowed_because_the_bytes_agree(tmp_path):
    path = session_at(tmp_path, strippable())
    cold = path.stat().st_mtime + A_DAY

    assert fork_command(str(path), write=True, now=cold)[0] == 0
    assert fork_command(str(path), write=True, now=cold)[0] == 0


def test_a_taken_destination_is_a_usage_error_rather_than_a_refusal(tmp_path):
    """SPEC §8's exit-3 list is the guards. "The name you chose is taken" is a bad
    argument, and `--out` or `--force` fixes it."""
    path = session_at(tmp_path / "project", strippable())
    destination = tmp_path / "taken.jsonl"
    destination.write_text("somebody else's file\n")

    code, output = fork_command(str(path), write=True, out=str(destination),
                                now=path.stat().st_mtime + A_DAY)

    assert code == 1
    assert "already exists" in output
    assert destination.read_text() == "somebody else's file\n"


def test_a_destination_holding_other_bytes_is_not_overwritten(tmp_path):
    path = session_at(tmp_path, strippable())
    destination = tmp_path / "taken.jsonl"
    destination.write_text("somebody else's file\n")

    result, _ = build_fork(build_plan(path, tier="CB"), out=destination,
                           now=path.stat().st_mtime + A_DAY)
    with pytest.raises(ForkError, match="already exists"):
        write_fork(result)

    assert destination.read_text() == "somebody else's file\n"


def test_force_overwrites_a_destination_holding_other_bytes(tmp_path):
    path = session_at(tmp_path, strippable())
    destination = tmp_path / "taken.jsonl"
    destination.write_text("somebody else's file\n")

    result, _ = build_fork(build_plan(path, tier="CB"), out=destination,
                           now=path.stat().st_mtime + A_DAY)
    write_fork(result, force=True)

    assert destination.read_text() != "somebody else's file\n"


# ─── What the fork contains ──────────────────────────────────────────────────


def test_every_stripped_result_holds_its_pointer_and_nothing_else(tmp_path):
    path = session_at(tmp_path, strippable())
    plan = build_plan(path, tier="CB")
    result, _ = build_fork(plan, now=path.stat().st_mtime + A_DAY)

    forked = {}
    for record in _records(result.lines):
        content = record.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                forked[block["tool_use_id"]] = block["content"]

    for strip in plan.strips:
        assert forked[strip.use_id] == strip.pointer


def test_the_pointer_is_a_plain_string_so_g4_priced_what_was_written(tmp_path):
    """Wrapping it in a one-element block list would add JSON scaffolding `plan`
    never counted, and the fork would remove less than the dry run promised."""
    path = session_at(tmp_path, strippable())
    plan = build_plan(path, tier="CB")
    result, _ = build_fork(plan, now=path.stat().st_mtime + A_DAY)

    for record in _records(result.lines):
        content = record.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                assert isinstance(block["content"], str)


def test_the_fork_carries_the_new_session_id_and_not_the_old_one(tmp_path):
    path = session_at(tmp_path, strippable())
    result, _ = build_fork(build_plan(path, tier="CB"), now=path.stat().st_mtime + A_DAY)

    text = "\n".join(result.lines)
    assert SESSION not in text
    assert result.new_session_id in text


def test_a_record_naming_another_session_is_left_alone(tmp_path):
    """DECISIONS §4: winnow passes a record type it does not understand through
    unchanged, and never "cleans up" one."""
    other = "11111111-2222-3333-4444-555555555555"
    records = strippable() + [
        {"type": "bridge-session", "uuid": "bridge", "sessionId": other}
    ]
    path = session_at(tmp_path, records)
    result, _ = build_fork(build_plan(path, tier="CB"), now=path.stat().st_mtime + A_DAY)

    assert other in "\n".join(result.lines)


def test_untouched_lines_are_copied_across_byte_for_byte(tmp_path):
    """A line winnow has no reason to rewrite must not be re-serialised: JSON
    round-tripping would reorder nothing but could still change spacing, and an
    unrecognised record deserves to leave exactly as it arrived."""
    path = session_at(tmp_path, strippable())
    plan = build_plan(path, tier="CB")
    result, _ = build_fork(plan, now=path.stat().st_mtime + A_DAY)

    original = path.read_text().split("\n")
    touched = {s.line for s in plan.strips}
    for index, line in enumerate(original):
        if index in touched or '"sessionId"' in line:
            continue
        assert result.lines[index] == line


def test_a_non_utf8_byte_survives_the_round_trip(tmp_path):
    """A binary or truncated-multibyte tool result must reach the fork as the
    bytes it was, not as U+FFFD. `surrogateescape` on both ends is what does it."""
    path = session_at(tmp_path, strippable())
    raw = path.read_bytes() + b'{"type":"attachment","blob":"\xff\xfe"}\n'
    path.write_bytes(raw)

    result, _ = build_fork(build_plan(path, tier="CB"), now=path.stat().st_mtime + A_DAY)
    write_fork(result)

    assert b"\xff\xfe" in result.out_path.read_bytes()


# ─── The round trip: fork → recover ──────────────────────────────────────────


@pytest.mark.parametrize("fixture", ["plan_demo.jsonl", "compacted.jsonl"])
def test_every_pointer_in_a_fork_recovers_to_its_recorded_digest(tmp_path, fixture):
    """Milestone 2's acceptance test for both commands, on a fixture rich enough
    to hit several rules. The bytes come back from the *original*, which is the
    file winnow never wrote to — that is what makes the strip reversible."""
    path = tmp_path / fixture
    shutil.copy(FIXTURES / fixture, path)

    plan = build_plan(path, tier="CBA")
    result, _ = build_fork(plan, now=path.stat().st_mtime + A_DAY)
    write_fork(result)

    assert plan.strips, "the fixture must have something to recover"
    for strip in plan.strips:
        code, payload = recover_command(str(path), strip.pointer_id)
        assert code == 0, payload
        digest = hashlib.sha256(payload.encode("utf-8", "surrogateescape")).hexdigest()
        assert digest == strip.digest
        assert len(payload) == strip.result_size


def test_recover_reads_the_original_even_after_the_fork_is_deleted(tmp_path):
    path = session_at(tmp_path, strippable())
    plan = build_plan(path, tier="CB")
    result, _ = build_fork(plan, now=path.stat().st_mtime + A_DAY)
    write_fork(result)
    result.out_path.unlink()

    code, payload = recover_command(str(path), plan.strips[0].pointer_id)

    assert code == 0
    assert payload == BIG


def test_the_digest_the_pointer_quotes_is_the_digest_of_what_comes_back(tmp_path):
    path = session_at(tmp_path, strippable())
    plan = build_plan(path, tier="CB")

    for strip in plan.strips:
        assert strip.digest in strip.pointer[:200] or strip.digest in strip.pointer
        code, payload = recover_command(str(path), strip.pointer_id)
        assert code == 0
        assert content_digest(payload) == strip.digest


def test_recover_json_carries_the_digest_and_the_tool(tmp_path):
    path = session_at(tmp_path, strippable())
    plan = build_plan(path, tier="CB")
    strip = plan.strips[0]

    code, payload = recover_command(str(path), strip.pointer_id, as_json=True)

    assert code == 0
    body = json.loads(payload)
    assert body["sha256"] == strip.digest
    assert body["tool"] == strip.tool
    assert body["content"] == BIG


def test_a_pointer_id_that_names_no_call_is_a_usage_error(tmp_path):
    path = session_at(tmp_path, strippable())
    code, output = recover_command(str(path), "c9999")

    assert code == 1
    assert "no tool call at position" in output


def test_a_malformed_pointer_id_is_a_usage_error(tmp_path):
    path = session_at(tmp_path, strippable())
    code, output = recover_command(str(path), "not-a-pointer")

    assert code == 1
    assert "not-a-pointer" in output


# ─── Q4: a session that has already compacted ────────────────────────────────


def test_a_compacted_session_is_refused_by_default(tmp_path):
    """DECISIONS §Q4, decided in milestone 2: refuse, with `--force` as the escape.

    A resume starts from the summary the compaction wrote, so the pre-boundary
    results a plan prices are not in the prefix the fork would be cutting — the
    saving `plan` reported is not the saving the resume gets."""
    path = tmp_path / "compacted.jsonl"
    shutil.copy(FIXTURES / "compacted.jsonl", path)

    code, output = fork_command(str(path), write=True, now=path.stat().st_mtime + A_DAY)

    assert code == 3
    assert "compacted" in output
    assert "Q4" in output
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_force_forks_a_compacted_session_and_records_that_it_was_forced(tmp_path):
    path = tmp_path / "compacted.jsonl"
    shutil.copy(FIXTURES / "compacted.jsonl", path)

    code, output = fork_command(str(path), write=True, force=True,
                                now=path.stat().st_mtime + A_DAY)

    assert code == 0
    assert "forced past" in output
    assert "compacted" in output
    assert len(list(path.parent.iterdir())) == 2


def test_the_compacted_refusal_names_where_the_boundary_is(tmp_path):
    """An operator told "refused" is owed the line, because deciding whether to
    force is a judgement about what is on the far side of it."""
    path = tmp_path / "compacted.jsonl"
    shutil.copy(FIXTURES / "compacted.jsonl", path)

    result, refusals = build_fork(build_plan(path, tier="CB"),
                                  now=path.stat().st_mtime + A_DAY)

    compacted = [r for r in refusals if r.guard == "compacted"]
    assert len(compacted) == 1
    assert compacted[0].forceable
    assert str(result.compact_boundaries[0]) in compacted[0].reason


def test_a_forced_compacted_fork_still_recovers(tmp_path):
    """Forcing past Q4 must not cost the round trip."""
    path = tmp_path / "compacted.jsonl"
    shutil.copy(FIXTURES / "compacted.jsonl", path)

    plan = build_plan(path, tier="CB")
    fork_command(str(path), write=True, force=True, now=path.stat().st_mtime + A_DAY)

    for strip in plan.strips:
        code, payload = recover_command(str(path), strip.pointer_id)
        assert code == 0
        assert content_digest(payload) == strip.digest


# ─── The malformed-record refusal ────────────────────────────────────────────


def test_a_malformed_record_refuses_and_force_carries_it_across(tmp_path):
    """SPEC §10 fails loudly on a record it could not read. Forcing past it means
    copying the line verbatim rather than guessing at what it meant."""
    path = session_at(tmp_path, strippable())
    path.write_text(path.read_text() + "{not json at all\n")

    refused, output = fork_command(str(path), write=True, now=path.stat().st_mtime + A_DAY)
    assert refused == 3
    assert "malformed" in output

    forced, _ = fork_command(str(path), write=True, force=True,
                             now=path.stat().st_mtime + A_DAY)
    assert forced == 0
    written = next(p for p in path.parent.iterdir() if p != path)
    assert "{not json at all" in written.read_text()


# ─── Output shape ────────────────────────────────────────────────────────────


def test_the_readout_names_the_source_digest_and_the_resume_command(tmp_path):
    path = session_at(tmp_path, strippable())
    code, output = fork_command(str(path), write=True, now=path.stat().st_mtime + A_DAY)

    result, _ = build_fork(build_plan(path, tier="CB"), now=path.stat().st_mtime + A_DAY)
    assert code == 0
    assert result.source_sha256 in output
    assert f"claude --resume {result.new_session_id}" in output


def test_the_json_shape_nests_the_plan_whole(tmp_path):
    """A consumer that already reads a plan should not learn a second vocabulary
    for the same numbers."""
    path = session_at(tmp_path, strippable())
    code, output = fork_command(str(path), as_json=True, now=path.stat().st_mtime + A_DAY)

    body = json.loads(output)
    assert code == 0
    assert body["pairing"]["preserved"] is True
    assert body["written"] is False
    assert body["source"]["sha256"] == source_lines(path)[1]
    assert body["plan"]["bytes"]["net"] > 0
    assert body["cold_age"]["threshold"] == DEFAULT_MIN_COLD_AGE


def test_the_json_refusal_list_says_which_guards_are_forceable(tmp_path):
    path = session_at(tmp_path, strippable())
    code, output = fork_command(str(path), as_json=True, now=path.stat().st_mtime + 60)

    body = json.loads(output)
    assert code == 3
    assert [(r["guard"], r["forceable"]) for r in body["refusals"]] == [("cold-age", True)]


def test_explain_carries_its_secrets_warning_into_the_fork_readout(tmp_path):
    """MILESTONES.md requires `--explain` documented with the warning, and the
    warning belongs next to the output rather than only in the README."""
    path = session_at(tmp_path, strippable())
    code, output = fork_command(str(path), explain=True, now=path.stat().st_mtime + A_DAY)

    assert code == 0
    assert "credentials" in output
    assert "Treat this output as sensitive" in output


def test_explain_is_off_by_default(tmp_path):
    path = session_at(tmp_path, strippable())
    _, output = fork_command(str(path), now=path.stat().st_mtime + A_DAY)

    assert "credentials" not in output


# ─── Usage errors ────────────────────────────────────────────────────────────


def test_tier_cba_without_i_know_is_refused_before_anything_is_read(tmp_path):
    code, output = fork_command("nowhere-at-all", tier="CBA")

    assert code == 1
    assert "--i-know" in output


def test_an_unresolvable_session_is_a_usage_error(tmp_path):
    code, output = fork_command(str(tmp_path / "missing.jsonl"))

    assert code == 1
    assert "no session matches" in output or "no projects directory" in output


def test_an_unwritable_destination_is_a_usage_error_not_a_traceback(tmp_path):
    path = session_at(tmp_path, strippable())
    blocked = tmp_path / "a-file"
    blocked.write_text("not a directory\n")

    code, output = fork_command(str(path), write=True, out=str(blocked / "fork.jsonl"),
                                now=path.stat().st_mtime + A_DAY)

    assert code == 1
    assert "cannot write" in output


# ─── The CLI surface ─────────────────────────────────────────────────────────


def test_the_cli_exposes_fork_and_recover(tmp_path, capsys):
    from winnow.cli import main

    path = session_at(tmp_path, strippable())
    assert main(["fork", str(path), "--min-cold-age", "0"]) == 0
    assert "would write" in capsys.readouterr().out


def test_recover_writes_the_bytes_without_adding_a_newline(tmp_path, capsys):
    """`print` would append one, and the pointer's digest does not cover it."""
    from winnow.cli import main

    path = session_at(tmp_path, strippable())
    strip = build_plan(path, tier="CB").strips[0]

    assert main(["recover", str(path), strip.pointer_id]) == 0
    assert capsys.readouterr().out == BIG


def test_the_fork_subcommand_has_no_dry_run_flag():
    """SPEC §8: dry is the default, so the flag that writes is the one to type."""
    from winnow.cli import build_parser

    fork_parser = build_parser()._subparsers._group_actions[0].choices["fork"]
    flags = {option for action in fork_parser._actions for option in action.option_strings}

    assert "--write" in flags
    assert "--dry-run" not in flags
    assert {"--force", "--out", "--min-cold-age", "--explain"} <= flags
