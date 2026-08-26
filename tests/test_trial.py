"""`winnow trial` — the arm ledger, the attribution and the billed arithmetic.

The test that matters most is `test_predates_the_first_arm_is_not_attributed`.
Everything else here is arithmetic that would be visibly wrong; that one is the
failure that would look completely normal. Sessions from before the trial started
are the majority of any real corpus — 296 of 1,197 on this operator's own machine
at the time this was written — and folding them into whichever arm happened to be
declared first would hand that arm hundreds of sessions it never ran, in a column
an operator is reading precisely to choose between them.

`test_unpriced_session_counts_turns_but_not_dollars` is the other one worth
keeping: it holds the report to reporting a *different population* in two columns
rather than quietly pricing an unknown model at zero, which is `savings.py`'s
rule and the reason a total here can be reconciled against an invoice.
"""

from __future__ import annotations

import json
from pathlib import Path

from winnow import report, trial

MODEL = "claude-opus-5"


def usage_record(
    *,
    ts: str,
    model: str | None = MODEL,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_read: int = 0,
    cache_creation: int = 0,
    ttl: str | None = "ephemeral_1h",
) -> dict:
    inner: dict = {
        "role": "assistant",
        "model": model,
        "content": "hi",
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_creation,
        },
    }
    if ttl and cache_creation:
        inner["usage"]["cache_creation"] = {f"{ttl}_input_tokens": cache_creation}
    return {"type": "assistant", "timestamp": ts, "message": inner}


def tool_record(ts: str, name: str, tool_input: dict) -> dict:
    return {
        "type": "assistant",
        "timestamp": ts,
        "message": {
            "role": "assistant",
            "model": MODEL,
            "content": [
                {"type": "tool_use", "id": "t1", "name": name, "input": tool_input}
            ],
        },
    }


def write_transcript(path: Path, records: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def at(day: int, hour: int = 12) -> str:
    return f"2026-08-{day:02d}T{hour:02d}:00:00.000Z"


def epoch(day: int, hour: int = 12) -> float:
    from datetime import datetime

    return datetime.fromisoformat(
        f"2026-08-{day:02d}T{hour:02d}:00:00+00:00"
    ).timestamp()


# ─── The arm ledger ──────────────────────────────────────────────────────────


def test_arm_round_trips_through_the_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "arms.jsonl"
    trial.record_arm(ledger, "pruner-only", "rx standard", now=epoch(10))
    trial.record_arm(ledger, "filter-only", "proxy on", now=epoch(17))
    arms = trial.read_arms(ledger)
    assert [a.label for a in arms] == ["pruner-only", "filter-only"]
    assert arms[0].note == "rx standard"


def test_a_malformed_line_is_skipped_rather_than_fatal(tmp_path: Path) -> None:
    # The ledger is append-only and hand-editable, and a trial that refused to
    # report because one line was truncated would lose the whole record over the
    # cheapest possible fault.
    ledger = tmp_path / "arms.jsonl"
    trial.record_arm(ledger, "a", now=epoch(10))
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
        handle.write(json.dumps({"label": "no timestamp"}) + "\n")
    assert [a.label for a in trial.read_arms(ledger)] == ["a"]


def test_arms_are_ordered_by_time_not_by_file_order(tmp_path: Path) -> None:
    ledger = tmp_path / "arms.jsonl"
    trial.record_arm(ledger, "second", now=epoch(20))
    trial.record_arm(ledger, "first", now=epoch(10))
    assert [a.label for a in trial.read_arms(ledger)] == ["first", "second"]


def test_arm_for_picks_the_one_in_force() -> None:
    arms = [trial.Arm(epoch(10), "a"), trial.Arm(epoch(20), "b")]
    assert trial.arm_for(arms, epoch(15)) == "a"
    assert trial.arm_for(arms, epoch(25)) == "b"
    # Exactly on the switch belongs to the arm being switched *to*: the operator
    # runs `trial arm` when the configuration changes, so the mark is the start
    # of the new one rather than the end of the old.
    assert trial.arm_for(arms, epoch(20)) == "b"


def test_arm_for_answers_none_before_the_first_arm() -> None:
    arms = [trial.Arm(epoch(10), "a")]
    assert trial.arm_for(arms, epoch(5)) is None


# ─── Reading a session ───────────────────────────────────────────────────────


def test_a_session_with_no_billed_turn_is_not_a_data_point(tmp_path: Path) -> None:
    # A transcript that never reached the API says nothing about what an arm
    # costs. Counted, it would drag every per-session figure toward zero in
    # whichever arm happened to collect more of them.
    path = write_transcript(
        tmp_path / "empty.jsonl",
        [
            {
                "type": "user",
                "timestamp": at(11),
                "message": {"role": "user", "content": "go"},
            }
        ],
    )
    assert trial.read_session(path) is None


def test_billed_input_counts_every_class(tmp_path: Path) -> None:
    # A cached token is still a token the model read. Counting only the uncached
    # part would credit an arm for the caching it happened to get rather than for
    # the context it carried — and pruning changes exactly that split, so this is
    # the one place the measure could flatter the thing under test.
    path = write_transcript(
        tmp_path / "s.jsonl",
        [
            usage_record(
                ts=at(11), input_tokens=100, cache_read=9_000, cache_creation=900
            )
        ],
    )
    cost = trial.read_session(path)
    assert cost is not None
    assert cost.billed_input == 10_000


def test_repeat_tool_calls_are_counted_once_per_repeat(tmp_path: Path) -> None:
    path = write_transcript(
        tmp_path / "s.jsonl",
        [
            usage_record(ts=at(11)),
            tool_record(at(11), "Bash", {"command": "ls"}),
            tool_record(at(11), "Bash", {"command": "ls"}),
            tool_record(at(11), "Bash", {"command": "ls"}),
            tool_record(at(11), "Bash", {"command": "pwd"}),
        ],
    )
    cost = trial.read_session(path)
    assert cost is not None
    assert cost.tool_calls == 4
    assert cost.repeat_tool_calls == 2


def test_argument_order_does_not_make_two_identical_calls_distinct(
    tmp_path: Path,
) -> None:
    # The same key rule C2 uses. Without the sort a repeat rate would depend on
    # how the model happened to serialise its arguments.
    path = write_transcript(
        tmp_path / "s.jsonl",
        [
            usage_record(ts=at(11)),
            tool_record(at(11), "Read", {"a": 1, "b": 2}),
            tool_record(at(11), "Read", {"b": 2, "a": 1}),
        ],
    )
    cost = trial.read_session(path)
    assert cost is not None
    assert cost.repeat_tool_calls == 1


# ─── Pricing ─────────────────────────────────────────────────────────────────


def test_an_unknown_model_is_not_priced_at_a_neighbours_rate(tmp_path: Path) -> None:
    path = write_transcript(
        tmp_path / "s.jsonl", [usage_record(ts=at(11), model="some-other-model")]
    )
    cost = trial.read_session(path)
    assert cost is not None
    assert trial.price_session(cost) is None


def test_the_write_class_is_read_back_rather_than_assumed(tmp_path: Path) -> None:
    # COZEMPIC §3.1's correction: pricing a one-hour write at the documented
    # 1.25× understates it by about 40%. The two sessions below are identical
    # except for the class the install actually paid.
    one_hour = trial.read_session(
        write_transcript(
            tmp_path / "1h.jsonl",
            [usage_record(ts=at(11), cache_creation=100_000, ttl="ephemeral_1h")],
        )
    )
    five_min = trial.read_session(
        write_transcript(
            tmp_path / "5m.jsonl",
            [usage_record(ts=at(11), cache_creation=100_000, ttl="ephemeral_5m")],
        )
    )
    assert one_hour is not None and five_min is not None
    assert trial.price_session(one_hour) > trial.price_session(five_min)


# ─── The arithmetic ──────────────────────────────────────────────────────────


def make_cost(
    day: int,
    *,
    last_day: int | None = None,
    model: str | None = MODEL,
    turns: int = 1,
    input_tokens: int = 1_000_000,
) -> trial.SessionCost:
    cost = trial.SessionCost(session=f"s{day}", model=model)
    cost.first_ts = epoch(day)
    cost.last_ts = epoch(last_day if last_day is not None else day)
    cost.turns = turns
    cost.input_tokens = input_tokens
    return cost


def test_sessions_land_in_the_arm_that_was_in_force() -> None:
    arms = [trial.Arm(epoch(10), "a"), trial.Arm(epoch(20), "b")]
    result = trial.build_trial([make_cost(12), make_cost(22), make_cost(23)], arms)
    by_label = {arm.label: arm for arm in result.arms}
    assert by_label["a"].sessions == 1
    assert by_label["b"].sessions == 2


def test_predates_the_first_arm_is_not_attributed() -> None:
    # The failure that would look normal, and the reason this file exists. On a
    # real corpus most sessions predate the trial; folding them into the earliest
    # arm hands it hundreds of sessions it never ran.
    arms = [trial.Arm(epoch(10), "a")]
    result = trial.build_trial([make_cost(5), make_cost(12)], arms)
    assert result.unattributed_sessions == 1
    assert result.arms[0].sessions == 1


def test_a_session_running_across_a_switch_is_flagged() -> None:
    # Counted under the arm it started in, because that is where most of it ran —
    # but counted in `straddling_sessions` too, so the reader can judge how much
    # of the total carries both configurations rather than being handed a clean
    # looking number.
    arms = [trial.Arm(epoch(10), "a"), trial.Arm(epoch(20), "b")]
    result = trial.build_trial([make_cost(15, last_day=25)], arms)
    assert result.straddling_sessions == 1
    assert result.arms[0].sessions == 1


def test_unpriced_session_counts_turns_but_not_dollars() -> None:
    arms = [trial.Arm(epoch(10), "a")]
    result = trial.build_trial(
        [make_cost(12), make_cost(13, model="some-other-model")], arms
    )
    arm = result.arms[0]
    assert result.unpriced_sessions == 1
    assert arm.sessions == 2
    assert arm.priced_sessions == 1
    # $/session divides by the priced ones. Dividing by all of them would report a
    # figure lower than any session actually cost.
    assert arm.dollars_per_session == arm.dollars


def test_dollars_per_task_needs_the_operator_to_supply_the_count() -> None:
    arms = [trial.Arm(epoch(10), "a")]
    without = trial.build_trial([make_cost(12)], arms)
    assert without.arms[0].dollars_per_task is None
    with_count = trial.build_trial([make_cost(12)], arms, {"a": 4})
    assert with_count.arms[0].dollars_per_task == with_count.arms[0].dollars / 4


def test_median_sits_beside_the_mean_because_one_long_session_dominates() -> None:
    arms = [trial.Arm(epoch(10), "a")]
    costs = [make_cost(11), make_cost(12), make_cost(13, input_tokens=100_000_000)]
    arm = trial.build_trial(costs, arms).arms[0]
    assert arm.median_session_dollars < arm.dollars_per_session


def test_an_arm_with_no_priced_session_reports_no_rate() -> None:
    arms = [trial.Arm(epoch(10), "a")]
    arm = trial.build_trial([make_cost(12, model="some-other-model")], arms).arms[0]
    assert arm.dollars_per_session is None
    assert arm.median_session_dollars is None


# ─── The command ─────────────────────────────────────────────────────────────


def test_corpus_is_required_and_has_no_default() -> None:
    code, output = report.trial_command(
        corpus=None, arms=None, tasks=None, as_json=False
    )
    assert code == 1
    assert "--corpus is required" in output


def test_a_missing_corpus_is_a_usage_error(tmp_path: Path) -> None:
    code, _ = report.trial_command(
        corpus=str(tmp_path / "nope"), arms=None, tasks=None, as_json=False
    )
    assert code == 1


def test_tasks_naming_an_undeclared_arm_is_refused(tmp_path: Path) -> None:
    # Refused rather than ignored. A task count silently attached to nothing
    # produces a report whose most important column is empty for a reason the
    # operator has no way to see.
    ledger = tmp_path / "arms.jsonl"
    trial.record_arm(ledger, "a", now=epoch(10))
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    code, output = report.trial_command(
        corpus=str(corpus), arms=str(ledger), tasks=["typo=4"], as_json=False
    )
    assert code == 1
    assert "typo" in output


def test_a_malformed_tasks_pair_is_refused(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    code, output = report.trial_command(
        corpus=str(corpus), arms=None, tasks=["nocount"], as_json=False
    )
    assert code == 1
    assert "<arm>=<count>" in output


def test_no_arms_declared_is_exit_two_and_says_what_to_do(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    code, output = report.trial_command(
        corpus=str(corpus), arms=str(tmp_path / "none.jsonl"), tasks=None, as_json=False
    )
    assert code == 2
    assert "winnow trial arm" in output


def test_report_says_the_figures_are_billed_not_modelled(tmp_path: Path) -> None:
    # The claim the whole module exists to be able to make, and the one a later
    # edit could quietly drop while every number stayed the same.
    ledger = tmp_path / "arms.jsonl"
    trial.record_arm(ledger, "a", now=epoch(10))
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    write_transcript(corpus / "s.jsonl", [usage_record(ts=at(12))])
    code, output = report.trial_command(
        corpus=str(corpus), arms=str(ledger), tasks=None, as_json=False
    )
    assert code == 0
    assert "billed figures" in output
    assert "nothing here is a saving" in output


def test_json_carries_the_same_numbers(tmp_path: Path) -> None:
    ledger = tmp_path / "arms.jsonl"
    trial.record_arm(ledger, "a", now=epoch(10))
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    write_transcript(corpus / "s.jsonl", [usage_record(ts=at(12))])
    code, output = report.trial_command(
        corpus=str(corpus), arms=str(ledger), tasks=["a=2"], as_json=True
    )
    assert code == 0
    payload = json.loads(output)
    assert payload["billed_not_modelled"] is True
    assert payload["arms"][0]["tasks"] == 2
