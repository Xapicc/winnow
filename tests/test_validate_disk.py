"""Tests for the disk-cost accounting, and for what it refuses to say from one point.

The measurement milestone 2's definition of done asks for takes a week. What can
be tested in a run is the arithmetic of one observation, the pairing of a fork to
its source, and the thing that matters most: that a single observation does not
turn into a rate.
"""

from __future__ import annotations

import json
import time

import pytest

from winnow.fork import build_fork, write_fork
from winnow.plan import build_plan, resolve_selection
from winnow.validate import corpus, disk

from .test_inspect import BIG, call, padding, write

LATER = 86_400
DAY = 86_400


def session(root, name: str):
    records = [
        *call("b0", "Bash", {"command": "cat notes.md"}, BIG),
        *call("b1", "Bash", {"command": "cat other.md"}, BIG),
        *padding(8),
    ]
    return write(root, records, f"{name}.jsonl")


def fork_of(path, out=None):
    plan = build_plan(path, tier="CB", rules=resolve_selection("CB"))
    result, refusals = build_fork(plan, out=out, now=time.time() + LATER)
    assert not refusals, refusals
    write_fork(result)
    return result


def corpus_with_forks(tmp_path, sessions: int = 2, fork_each: bool = True):
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    sources = [
        session(root, f"0000000{i}-1111-2222-3333-44445555666{i}")
        for i in range(sessions)
    ]
    forks = [fork_of(path) for path in sources] if fork_each else []
    return root.parent, sources, forks


# ─── Telling a fork from what it was forked out of ───────────────────────────


def test_a_real_fork_is_recognised_and_its_source_is_not(tmp_path):
    root, sources, forks = corpus_with_forks(tmp_path, 2)
    found = {t.path: t.is_fork for t in corpus.transcripts(root)}
    for path in sources:
        assert found[path] is False
    for result in forks:
        assert found[result.out_path] is True
    assert [p.name for p in corpus.sources(root)] == sorted(p.name for p in sources)


def test_a_single_file_is_a_corpus_of_one(tmp_path):
    _, sources, _ = corpus_with_forks(tmp_path, 1, fork_each=False)
    assert corpus.sources(sources[0]) == [sources[0]]


def test_a_missing_corpus_fails_loudly(tmp_path):
    with pytest.raises(FileNotFoundError, match="no corpus"):
        corpus.transcripts(tmp_path / "nowhere")


# ─── One observation ─────────────────────────────────────────────────────────


def test_the_pooled_figure_is_fork_bytes_over_original_bytes(tmp_path):
    root, sources, forks = corpus_with_forks(tmp_path, 2)
    record = disk.measure(root, now=1_000_000.0)

    source_bytes = sum(p.stat().st_size for p in sources)
    fork_bytes = sum(r.out_path.stat().st_size for r in forks)
    assert record["sources"] == 2
    assert record["forks"] == 2
    assert record["source_bytes"] == source_bytes
    assert record["fork_bytes"] == fork_bytes
    assert record["total_bytes"] == source_bytes + fork_bytes
    assert record["overhead_share"] == round(fork_bytes / source_bytes, 6)
    assert record["observed_at"] == 1_000_000.0


def test_a_fork_with_no_ledger_is_counted_but_reported_as_unpaired(tmp_path):
    """A fork whose parent is unknown still occupies the disk.

    Dropping it would understate the pooled cost, which is the number the
    definition of done asks for; claiming a parent for it would invent a pairing
    a UUIDv5 cannot be run backwards to produce.
    """
    root, _, forks = corpus_with_forks(tmp_path, 2)
    record = disk.measure(root)
    assert record["unpaired_forks"] == 2
    assert record["unpaired_fork_bytes"] == sum(
        r.out_path.stat().st_size for r in forks
    )
    assert record["per_session"] == []
    assert "Pass --ledger" in disk.render(record, [record])


def test_a_ledger_pairs_each_fork_to_the_session_it_came_out_of(tmp_path):
    root, sources, forks = corpus_with_forks(tmp_path, 2)
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(
        "".join(
            json.dumps(
                {
                    "source_session": path.stem,
                    "source_path": str(path),
                    "outcome": "pass",
                    "fork_session": result.new_session_id,
                    "fork_path": str(result.out_path),
                }
            )
            + "\n"
            for path, result in zip(sources, forks, strict=True)
        )
    )
    record = disk.measure(root, [ledger_path])
    assert record["unpaired_forks"] == 0
    assert len(record["per_session"]) == 2
    for row, path, result in zip(record["per_session"], sources, forks, strict=True):
        assert row["source_session"] == path.stem
        assert row["source_bytes"] == path.stat().st_size
        assert row["forks"] == 1
        assert row["fork_bytes"] == result.out_path.stat().st_size
        assert row["overhead_share"] == round(
            row["fork_bytes"] / row["source_bytes"], 6
        )


def test_several_forks_of_one_session_accumulate_against_it(tmp_path):
    """The word in the definition of done is *accumulated*.

    Two forks of the same session at different settings is the ordinary case —
    that is what re-running the tool does — and the per-session cost is their
    sum, not the last one.
    """
    root, sources, _ = corpus_with_forks(tmp_path, 1, fork_each=False)
    first = fork_of(sources[0])
    second = fork_of(sources[0], out=sources[0].parent / "second-fork.jsonl")
    ledger = tmp_path / "l.jsonl"
    ledger.write_text(
        "".join(
            json.dumps({"source_session": sources[0].stem,
                        "source_path": str(sources[0]), "outcome": "pass",
                        "fork_path": str(result.out_path)}) + "\n"
            for result in (first, second)
        )
    )
    record = disk.measure(root, [ledger])
    assert record["per_session"][0]["forks"] == 2
    assert record["per_session"][0]["fork_bytes"] == (
        first.out_path.stat().st_size + second.out_path.stat().st_size
    )


def test_a_corpus_with_no_forks_reports_zero_rather_than_dividing_by_it(tmp_path):
    root, _, _ = corpus_with_forks(tmp_path, 2, fork_each=False)
    record = disk.measure(root)
    assert record["forks"] == 0
    assert record["fork_bytes"] == 0
    assert record["overhead_share"] == 0.0


# ─── The series, and the rate it will not state ──────────────────────────────


def test_one_observation_is_not_a_rate():
    assert disk.growth([{"observed_at": 1.0, "fork_bytes": 100}]) is None
    assert disk.growth([]) is None
    # Two observations at the same instant divide by roughly zero, and a large
    # number produced that way is not weak evidence — it is none, stated
    # confidently.
    assert disk.growth([
        {"observed_at": 5.0, "fork_bytes": 1},
        {"observed_at": 5.0, "fork_bytes": 900},
    ]) is None


def test_the_readout_says_a_week_is_pending_when_it_is(tmp_path):
    root, _, _ = corpus_with_forks(tmp_path, 1)
    record = disk.measure(root, now=0.0)
    text = disk.render(record, [record])
    assert "one observation" in text
    assert "week" in text


def test_two_observations_a_week_apart_are_the_measurement():
    series = [
        {"observed_at": 0.0, "fork_bytes": 1_000},
        {"observed_at": 7 * DAY, "fork_bytes": 8_000},
    ]
    rate = disk.growth(series)
    assert rate["fork_bytes_added"] == 7_000
    assert rate["fork_bytes_per_day"] == 1_000.0
    assert rate["span_days"] == 7.0
    assert rate["is_a_week"] is True


def test_a_span_short_of_a_week_says_so_rather_than_claiming_the_criterion():
    series = [
        {"observed_at": 0.0, "fork_bytes": 0},
        {"observed_at": 2 * DAY, "fork_bytes": 2_000},
    ]
    assert disk.growth(series)["is_a_week"] is False
    text = disk.render({"corpus": "/c", "sources": 1, "forks": 1, "source_bytes": 10,
                        "fork_bytes": 5, "total_bytes": 15, "overhead_share": 0.5,
                        "unpaired_forks": 0, "unpaired_fork_bytes": 0,
                        "per_session": []}, series)
    assert "Short of the week" in text


def test_the_series_is_append_only_and_reads_back_oldest_first(tmp_path):
    path = tmp_path / "series.jsonl"
    disk.append_series(path, {"observed_at": 20.0, "fork_bytes": 2})
    disk.append_series(path, {"observed_at": 10.0, "fork_bytes": 1})
    assert [r["observed_at"] for r in disk.read_series(path)] == [10.0, 20.0]
    assert len(path.read_text().splitlines()) == 2


def test_an_unreadable_series_line_is_refused_rather_than_skipped(tmp_path):
    path = tmp_path / "series.jsonl"
    path.write_text('{"observed_at": 1.0}\nnot json\n')
    with pytest.raises(ValueError, match="unreadable series line"):
        disk.read_series(path)
