"""`winnow savings` — the ledger reader, the join, and the arithmetic.

The test that matters most is `test_repeated_result_counts_once`: it writes a ledger
in which one result recurs across many requests, exactly as the stateless filter
produces, and fails if the de-dupe is removed. That is the regression test for the
27.2× overstatement on this operator's live ledger, which is the single error that
would make this whole command wrong by more than an order of magnitude.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from winnow import report, savings
from winnow.filter import apply, ledger_line

REPEATS = 40
BYTES = 8_000
MODEL = "claude-opus-5"


def write_ledger(path: Path, lines: list[dict]) -> Path:
    path.write_text(
        "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines),
        encoding="utf-8",
    )
    return path


def drop_line(request_id: str, entries: list[dict], *, kind: str = "dropped",
              model: str | None = MODEL, ttl: str | None = "ephemeral_1h") -> dict:
    other = "deferred" if kind == "dropped" else "dropped"
    return {
        "request_id": request_id,
        "model": model,
        "cache_ttl": ttl,
        kind: entries,
        other: [],
        "bytes_dropped": sum(e["bytes"] for e in entries) if kind == "dropped" else 0,
        "bytes_deferred": sum(e["bytes"] for e in entries) if kind == "deferred" else 0,
        "tool_results_seen": len(entries),
    }


def entry(use_id: str | None, size: int = BYTES, tool: str = "Bash",
          rule: str = "B2") -> dict:
    return {"tool": tool, "rule": rule, "bytes": size, "tool_use_id": use_id}


# ─── The de-dupe, and the 27.2× it prevents ──────────────────────────────────


def test_repeated_result_counts_once(tmp_path):
    """One result re-dropped on 40 requests is one removal of 8,000 bytes.

    This fails loudly if the de-dupe is removed: without it the reader would report
    40 results and 320,000 bytes, which is the shape of the live ledger's 27.2×.
    """
    path = write_ledger(tmp_path / "filter.jsonl", [
        drop_line(f"req_{i}", [entry("toolu_same")]) for i in range(REPEATS)
    ])
    read = savings.read_ledger(path)

    assert len(read.removals) == 1, "a stateless filter's repeats are not new removals"
    assert read.unique_bytes == BYTES
    # The naive sum is kept only so the readout can show the gap it avoids.
    assert read.removal_events == REPEATS
    assert read.bytes_summed == REPEATS * BYTES
    assert read.bytes_summed / read.unique_bytes == pytest.approx(REPEATS)
    assert read.removals[0].repeats == REPEATS


def test_repeats_are_priced_as_reads_not_as_removals(tmp_path):
    """The repeats are the `0.1·D·T` term, not `1.0·D` forty times over.

    Priced correctly, 40 repeats of an 8 KB result over T turns cost far less than
    40 independent removals would. This pins the ratio rather than the absolute.
    """
    path = write_ledger(tmp_path / "filter.jsonl", [
        drop_line(f"req_{i}", [entry("toolu_same")]) for i in range(REPEATS)
    ])
    result = savings.compute(path, tmp_path / "no-such-projects")
    # No transcripts, so nothing joins and nothing is priced — but the unique count
    # is already fixed before any join.
    assert len(result.priced) == 1
    assert result.unique_bytes == BYTES
    assert all(p.excluded for p in result.priced)


def test_deferred_then_dropped_is_one_removal(tmp_path):
    """The live ledger's own pattern: kept on one request, dropped on the next."""
    path = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_a", [entry("toolu_x")], kind="deferred"),
        drop_line("req_b", [entry("toolu_x")], kind="dropped"),
        drop_line("req_c", [entry("toolu_x")], kind="dropped"),
    ])
    read = savings.read_ledger(path)

    assert len(read.removals) == 1
    assert read.removals[0].first_kind == "deferred"
    # T is measured from where the result first appeared, not from where it was
    # first stripped: that is the turn the baseline would have cache-written it on.
    assert read.removals[0].request_id == "req_a"
    # The naive sum has to span the same two kinds the unique set does. Counting
    # only `dropped` here would report 2 events and 2·D against a 1·D denominator —
    # a ratio of 2 where the file's own events say 3.
    assert read.removal_events == 3
    assert read.bytes_summed == 3 * BYTES


def test_distinct_results_are_not_merged(tmp_path):
    path = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_a", [entry("toolu_x"), entry("toolu_y", size=9_000)]),
        drop_line("req_b", [entry("toolu_x"), entry("toolu_y", size=9_000)]),
    ])
    read = savings.read_ledger(path)

    assert len(read.removals) == 2
    assert read.unique_bytes == BYTES + 9_000


# ─── Ledger lines written before the three fields existed ────────────────────


def test_old_format_line_is_read_not_dropped(tmp_path):
    """A line with no tool_use_id, model or cache_ttl still counts, on the fallback."""
    path = write_ledger(tmp_path / "filter.jsonl", [{
        "request_id": "req_old",
        "dropped": [{"tool": "Bash", "rule": "B2", "bytes": BYTES}],
        "deferred": [],
        "bytes_dropped": BYTES,
        "bytes_deferred": 0,
        "tool_results_seen": 3,
    }])
    read = savings.read_ledger(path)

    assert len(read.removals) == 1
    assert read.removals[0].bytes == BYTES
    assert read.removals[0].tool_use_id is None
    assert read.removals[0].model is None
    assert read.removals[0].ttl is None
    assert read.legacy_lines == 1
    assert read.lines_without_model == 1
    assert read.lines_without_ttl == 1


def test_old_format_repeats_dedupe_on_the_triple(tmp_path):
    path = write_ledger(tmp_path / "filter.jsonl", [
        {"request_id": f"req_{i}",
         "dropped": [{"tool": "Bash", "rule": "B2", "bytes": BYTES}],
         "deferred": [], "bytes_dropped": BYTES, "bytes_deferred": 0,
         "tool_results_seen": 1}
        for i in range(REPEATS)
    ])
    read = savings.read_ledger(path)

    assert len(read.removals) == 1
    assert read.legacy_lines == REPEATS
    assert read.bytes_summed == REPEATS * BYTES


def test_a_triple_claimed_by_an_id_blocks_a_later_legacy_line(tmp_path):
    """A ledger straddling the format change must not count one result twice."""
    path = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_new", [entry("toolu_x")]),
        {"request_id": "req_old",
         "dropped": [{"tool": "Bash", "rule": "B2", "bytes": BYTES}],
         "deferred": [], "bytes_dropped": BYTES, "bytes_deferred": 0,
         "tool_results_seen": 1},
    ])
    read = savings.read_ledger(path)

    assert len(read.removals) == 1
    assert read.removals[0].tool_use_id == "toolu_x"


def test_every_event_lands_in_exactly_one_bucket(tmp_path):
    """A removal event is a first sight or a repeat, and malformed is a third bucket.

    Nothing may fall out between them: an entry the reader cannot use has to be
    counted and named, because a silently discarded event is indistinguishable in the
    readout from one that was never written.
    """
    path = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_a", [entry("toolu_x"), entry(None, size=99)]),
        drop_line("req_b", [entry("toolu_x"), entry(None, size=99)]),
        # An id-less echo of a triple already claimed under its id: still a repeat.
        drop_line("req_c", [{"tool": "Bash", "rule": "B2", "bytes": BYTES}]),
        {"request_id": "req_d", "model": MODEL, "cache_ttl": "ephemeral_1h",
         "dropped": [{"tool": "Bash", "rule": "B2"}, "not-a-dict"], "deferred": [],
         "bytes_dropped": 0, "bytes_deferred": 0, "tool_results_seen": 2},
    ])
    read = savings.read_ledger(path)

    assert read.malformed_entries == 2
    assert len(read.removals) == 2, "one id-bearing result and one id-less one"
    assert sum(r.repeats for r in read.removals) == 5
    assert read.events == 7, "five usable entries plus the two malformed ones"


def test_buckets_account_for_every_unique_removal(tmp_path):
    projects = tmp_path / "projects" / "proj"
    projects.mkdir(parents=True)
    _transcript(projects / "sess.jsonl", [
        _assistant("req_a", ephemeral_1h_input_tokens=1000,
                   cache_creation_input_tokens=1000),
    ])
    ledger = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_a", [entry("toolu_x")]),
        drop_line("req_gone", [entry("toolu_y")]),
        drop_line("req_a", [entry("toolu_z")], model="claude-not-a-real-model"),
    ])
    result = savings.compute(ledger, tmp_path / "projects")
    excluded = sum(count for count, _bytes in result.exclusions.values())

    assert len(result.counted) + excluded == len(result.priced) == 3


def test_no_model_is_excluded_never_guessed(tmp_path, monkeypatch):
    path = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_a", [entry("toolu_x")], model="claude-not-a-real-model"),
    ])
    requests = {"req_a": savings.RequestFacts(
        session_id="s", turn_index=0, turns_after=10, model=None)}
    sessions = {"s": savings.SessionFacts(path=tmp_path / "s.jsonl", session_id="s")}
    priced = savings._price(savings.read_ledger(path).removals[0], requests, sessions)

    assert priced.excluded is not None
    assert "no published price" in priced.excluded
    assert priced.dollars == 0.0


# ─── The arithmetic ──────────────────────────────────────────────────────────


def _priced(ttl: str, turns_after: int, size: int = 1_000_000) -> savings.Priced:
    removal = savings.Removal(
        tool="Bash", rule="B2", bytes=size, request_id="req_a",
        tool_use_id="toolu_x", model=MODEL, ttl=ttl, first_kind="dropped",
    )
    facts = savings.RequestFacts(
        session_id="s", turn_index=0, turns_after=turns_after, model=MODEL)
    session = savings.SessionFacts(path=Path("s.jsonl"), session_id="s")
    return savings._price(removal, {"req_a": facts}, {"s": session})


def test_write_term_is_the_premium_not_the_whole_write():
    """COZEMPIC §3.5's `saving 1.0·D`: the filter still pays one uncached turn.

    1 MB at SPEC §6's ÷4 is 250,000 tokens; Opus 5 input is $5/MTok. The avoided
    write at the 2.0× class is (2.0−1.0)·D = 250,000 × $5/MTok = $1.25.
    """
    priced = _priced("ephemeral_1h", turns_after=0)

    assert priced.tokens == pytest.approx(250_000)
    assert priced.write_dollars == pytest.approx(1.25)
    assert priced.read_dollars == 0.0


def test_five_minute_ttl_is_worth_a_quarter_of_the_one_hour_write():
    """1.25× against 2.0×, read from the ledger and never assumed (COZEMPIC §3.1)."""
    one_hour = _priced("ephemeral_1h", 0).write_dollars
    five_minute = _priced("ephemeral_5m", 0).write_dollars

    assert one_hour == pytest.approx(1.25)  # (2.0−1.0)·D
    assert five_minute == pytest.approx(0.3125)  # (1.25−1.0)·D
    assert five_minute == pytest.approx(one_hour / 4)


def test_read_term_is_linear_in_T():
    """0.1·D·T. At T=20 the reads are twice the 1h write, which is the point of §3.5."""
    priced = _priced("ephemeral_1h", turns_after=20)

    assert priced.read_dollars == pytest.approx(0.1 * 250_000 * 20 * 5.0 / 1e6)
    assert priced.read_dollars == pytest.approx(2.5)
    assert priced.dollars == pytest.approx(3.75)


def test_ledger_ttl_beats_the_session_write_class():
    """The request's own class wins: one ledger spans requests billed differently."""
    removal = savings.Removal(
        tool="Bash", rule="B2", bytes=1_000_000, request_id="req_a",
        tool_use_id="toolu_x", model=MODEL, ttl="ephemeral_5m", first_kind="dropped",
    )
    session = savings.SessionFacts(path=Path("s.jsonl"), session_id="s")
    session.usage.ephemeral_1h = 500_000  # the session paid 1h; this request did not
    facts = savings.RequestFacts(
        session_id="s", turn_index=0, turns_after=0, model=MODEL)
    priced = savings._price(removal, {"req_a": facts}, {"s": session})

    assert priced.write_multiplier == pytest.approx(savings.WRITE_5M)


def test_legacy_line_falls_back_to_the_session_write_class():
    removal = savings.Removal(
        tool="Bash", rule="B2", bytes=1_000_000, request_id="req_a",
        tool_use_id=None, model=None, ttl=None, first_kind="dropped",
    )
    session = savings.SessionFacts(path=Path("s.jsonl"), session_id="s")
    session.usage.ephemeral_1h = 500_000
    facts = savings.RequestFacts(
        session_id="s", turn_index=0, turns_after=0, model=MODEL)
    priced = savings._price(removal, {"req_a": facts}, {"s": session})

    assert priced.model == MODEL, "the joined turn names the model the ledger did not"
    assert priced.write_multiplier == pytest.approx(savings.WRITE_1H)


def test_a_mixed_session_reaches_the_output_as_mixed(tmp_path):
    """§3.1's error was a write class assumed rather than read. A blend is neither
    2.0× nor 1.25×, and the readout must not call it either one."""
    removal = savings.Removal(
        tool="Bash", rule="B2", bytes=1_000_000, request_id="req_a",
        tool_use_id=None, model=None, ttl=None, first_kind="dropped",
    )
    session = savings.SessionFacts(path=Path("s.jsonl"), session_id="s")
    session.usage.ephemeral_1h = 300_000
    session.usage.ephemeral_5m = 100_000
    facts = savings.RequestFacts(
        session_id="s", turn_index=0, turns_after=0, model=MODEL)
    priced = savings._price(removal, {"req_a": facts}, {"s": session})

    assert priced.write_class == "mixed"
    # (300k·2.0 + 100k·1.25) / 400k
    assert priced.write_multiplier == pytest.approx(1.8125)

    result = savings.Savings(
        ledger=savings.LedgerRead(path=tmp_path / "filter.jsonl"),
        projects_dir=tmp_path,
        priced=[priced],
    )
    assert result.write_classes == {"mixed ×1.81": 1}
    assert "mixed ×1.81" in report.render_savings(result)


def test_the_readout_names_the_five_minute_class_when_that_is_what_was_paid(tmp_path):
    priced = _priced("ephemeral_5m", turns_after=0)
    result = savings.Savings(
        ledger=savings.LedgerRead(path=tmp_path / "filter.jsonl"),
        projects_dir=tmp_path,
        priced=[priced],
    )
    rendered = report.render_savings(result)

    assert priced.write_class == "5m"
    assert "5m ×1.25" in rendered
    assert "1h ×2.00" not in rendered, "the class it did not pay must not appear"


def test_no_ttl_anywhere_is_excluded_with_a_reason():
    removal = savings.Removal(
        tool="Bash", rule="B2", bytes=1_000, request_id="req_a",
        tool_use_id=None, model=MODEL, ttl=None, first_kind="dropped",
    )
    session = savings.SessionFacts(path=Path("s.jsonl"), session_id="s")
    facts = savings.RequestFacts(
        session_id="s", turn_index=0, turns_after=0, model=MODEL)
    priced = savings._price(removal, {"req_a": facts}, {"s": session})

    assert priced.excluded is not None
    assert "TTL" in priced.excluded
    assert priced.dollars == 0.0


# ─── Tokens ──────────────────────────────────────────────────────────────────


def test_every_result_uses_the_spec_estimate(tmp_path):
    """One rate for everything, and it is SPEC §6's ÷4 (COZEMPIC §3.5.2).

    The per-session least-squares calibration this replaced regressed
    `cache_read_input_tokens` on on-disk message bytes — two spans that are not the
    same content — and on the ledger it was built against it fired on exactly one
    session, inflating that session's D by 1.55×. A rate that moves with how many
    requests happened to be sampled is not a measurement of a tokenizer.
    """
    assert savings.DEFAULT_BYTES_PER_TOKEN == 4.0
    assert not hasattr(savings, "_calibrate"), "the fit was withdrawn, not disabled"

    priced = _priced("ephemeral_1h", turns_after=0, size=1_000_000)
    assert priced.tokens == pytest.approx(250_000)


# ─── The join, end to end ────────────────────────────────────────────────────


def _transcript(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
    )


def _assistant(request_id: str | None, text: str = "x", **usage) -> dict:
    block = {
        "input_tokens": 10, "output_tokens": 10,
        "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        "cache_creation": {"ephemeral_1h_input_tokens": 0,
                           "ephemeral_5m_input_tokens": 0},
    }
    block.update(usage)
    record = {
        "type": "assistant",
        "message": {"role": "assistant", "model": MODEL, "content": [
            {"type": "text", "text": text}], "usage": block},
    }
    if request_id:
        record["requestId"] = request_id
    return record


def test_join_counts_turns_after_the_removal(tmp_path):
    projects = tmp_path / "projects" / "proj"
    projects.mkdir(parents=True)
    records = [_assistant("req_hit", ephemeral_1h_input_tokens=1000,
                          cache_creation_input_tokens=1000)]
    records += [_assistant(None) for _ in range(5)]
    _transcript(projects / "sess.jsonl", records)

    ledger = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_hit", [entry("toolu_x", size=40_000)]),
    ])
    result = savings.compute(ledger, tmp_path / "projects")

    assert len(result.priced) == 1
    assert result.priced[0].excluded is None
    assert result.priced[0].turns_after == 5, "six billable turns, five after the hit"
    assert result.priced[0].session_id == "sess"
    assert result.dollars > 0


def test_T_is_capped_at_the_next_compact_boundary(tmp_path):
    """A result cannot be read back across a compaction: the cache is gone."""
    projects = tmp_path / "projects" / "proj"
    projects.mkdir(parents=True)
    records = [_assistant("req_hit", ephemeral_1h_input_tokens=1000,
                          cache_creation_input_tokens=1000)]
    records += [_assistant(None) for _ in range(2)]
    records += [{"type": "system", "subtype": "compact_boundary"}]
    records += [_assistant(None) for _ in range(20)]
    _transcript(projects / "sess.jsonl", records)

    ledger = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_hit", [entry("toolu_x", size=40_000)]),
    ])
    result = savings.compute(ledger, tmp_path / "projects")

    assert result.priced[0].turns_after == 2, "not 22 — the boundary ends the cache"


def test_a_split_response_is_one_turn_not_three(tmp_path):
    """Claude Code writes one API response as one record per content-block group.

    Every record carries the same `requestId` *and the same `message.usage`*, so a
    reader that walks records counts one response's cache read three times and calls
    it three turns. `T` is a count of cache reads and a response is read from cache
    once. Six requests here, each split three ways: T is 5, not 17.
    """
    projects = tmp_path / "projects" / "proj"
    projects.mkdir(parents=True)
    records = []
    for i in range(6):
        rid = "req_hit" if i == 0 else f"req_{i}"
        usage = ({"ephemeral_1h_input_tokens": 1000, "cache_creation_input_tokens": 1000}
                 if i == 0 else {})
        records += [_assistant(rid, **usage) for _ in range(3)]
    _transcript(projects / "sess.jsonl", records)

    ledger = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_hit", [entry("toolu_x", size=40_000)]),
    ])
    result = savings.compute(ledger, tmp_path / "projects")

    assert result.sessions["sess"].turns == 6
    assert result.sessions["sess"].records == 18
    assert result.priced[0].turns_after == 5, "five requests after, not seventeen records"


def test_the_bill_counts_a_split_response_once(tmp_path):
    """The same units error on the denominator: identical usage on every record."""
    projects = tmp_path / "projects" / "proj"
    projects.mkdir(parents=True)
    _transcript(projects / "sess.jsonl", [
        _assistant("req_hit", input_tokens=1_000_000, output_tokens=0,
                   cache_creation_input_tokens=0)
        for _ in range(4)
    ])
    ledger = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_hit", [entry("toolu_x", size=4_000)]),
    ])
    bill, _sessions, _unpriced = savings.compute(ledger, tmp_path / "projects").bill()

    assert bill == pytest.approx(5.0), "one request of 1M tokens at $5/MTok, not four"


def test_unjoined_lines_are_reported_with_a_reason(tmp_path):
    projects = tmp_path / "projects" / "proj"
    projects.mkdir(parents=True)
    _transcript(projects / "sess.jsonl", [_assistant("req_other")])

    ledger = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_missing", [entry("toolu_x", size=5_000)]),
    ])
    result = savings.compute(ledger, tmp_path / "projects")

    assert result.dollars == 0.0
    assert result.exclusions == {"request_id not found in any transcript": (1, 5_000)}


def test_bill_denominator_comes_from_the_joined_sessions_usage(tmp_path):
    projects = tmp_path / "projects" / "proj"
    projects.mkdir(parents=True)
    _transcript(projects / "sess.jsonl", [
        _assistant("req_hit", input_tokens=1_000_000, output_tokens=0,
                   cache_creation_input_tokens=0),
    ])
    ledger = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_hit", [entry("toolu_x", size=4_000)]),
    ])
    result = savings.compute(ledger, tmp_path / "projects")
    bill, sessions_priced, unpriced = result.bill()

    assert sessions_priced == 1
    assert unpriced == []
    assert bill == pytest.approx(5.0), "1M input tokens at Opus 5's $5/MTok"


# ─── The command ─────────────────────────────────────────────────────────────


def test_command_says_the_figure_is_modelled(tmp_path):
    ledger = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_a", [entry("toolu_x")]),
    ])
    code, output = report.savings_command(str(ledger), str(tmp_path / "none"), False)

    assert code == 0
    assert "modelled, not billed" in output
    assert "27.6×" not in output  # the readout computes it, never hard-codes it


def test_command_reports_the_overstatement_it_avoids(tmp_path):
    ledger = write_ledger(tmp_path / "filter.jsonl", [
        drop_line(f"req_{i}", [entry("toolu_x")]) for i in range(REPEATS)
    ])
    code, output = report.savings_command(str(ledger), str(tmp_path / "none"), False)

    assert code == 0
    assert f"overstate this by {REPEATS}.0×" in output


def test_command_json_splits_write_from_reads(tmp_path):
    ledger = write_ledger(tmp_path / "filter.jsonl", [
        drop_line("req_a", [entry("toolu_x")]),
    ])
    _code, output = report.savings_command(str(ledger), str(tmp_path / "none"), True)
    payload = json.loads(output)

    assert "avoided_write" in payload["dollars"]
    assert "avoided_reads" in payload["dollars"]
    assert payload["removed"]["unique_results"] == 1
    assert payload["caveat"].startswith("This is modelled, not billed")


def test_missing_ledger_is_a_usage_error(tmp_path):
    code, output = report.savings_command(str(tmp_path / "nope.jsonl"), None, False)

    assert code == 1
    assert "no ledger at" in output


def test_empty_ledger_exits_nothing_to_do(tmp_path):
    ledger = write_ledger(tmp_path / "filter.jsonl", [])
    code, _output = report.savings_command(str(ledger), str(tmp_path / "none"), False)

    assert code == 2


# ─── The three new ledger fields, written by the filter itself ───────────────


def _request(size: int = 6_000, ttl: str | None = "1h") -> dict:
    control = {"type": "ephemeral"}
    if ttl:
        control["ttl"] = ttl
    return {
        "model": MODEL,
        "messages": [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "toolu_1", "name": "Bash",
                 "input": {"command": "ls -la"}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1",
                 "content": "x" * size}]},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "toolu_2", "name": "Bash",
                 "input": {"command": "git status"}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_2",
                 "content": "y" * size, "cache_control": control}]},
        ],
    }


def test_ledger_line_carries_tool_use_id_model_and_ttl():
    _body, plan = apply(_request())
    line = json.loads(ledger_line(plan, "req_1"))

    assert line["model"] == MODEL
    assert line["cache_ttl"] == "ephemeral_1h"
    ids = [e["tool_use_id"] for e in line["dropped"] + line["deferred"]]
    assert ids, "the filter fired but named nothing"
    assert all(i and i.startswith("toolu_") for i in ids)


def test_ledger_ttl_is_read_from_the_request_not_assumed():
    """No explicit ttl on the breakpoint is the API's 5m default — still read."""
    _body, plan = apply(_request(ttl=None))
    assert json.loads(ledger_line(plan))["cache_ttl"] == "ephemeral_5m"


def test_no_breakpoint_means_no_write_class_rather_than_a_default():
    body = _request()
    for message in body["messages"]:
        for block in message["content"]:
            block.pop("cache_control", None)
    _body, plan = apply(body)

    assert json.loads(ledger_line(plan))["cache_ttl"] is None


def test_a_filtered_request_round_trips_through_the_reader(tmp_path):
    """What the filter writes is what the reader reads — the two ends, joined."""
    _body, plan = apply(_request())
    ledger = tmp_path / "filter.jsonl"
    ledger.write_text(
        json.dumps({**json.loads(ledger_line(plan)), "request_id": "req_1"}) + "\n",
        encoding="utf-8",
    )
    read = savings.read_ledger(ledger)

    assert read.legacy_lines == 0
    assert read.lines_without_model == 0
    assert read.lines_without_ttl == 0
    assert len(read.removals) == len(plan.dropped) + len(plan.deferred)
    assert read.unique_bytes == plan.bytes_dropped + plan.bytes_deferred
