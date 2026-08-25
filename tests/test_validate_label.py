"""Tests for the sampler and the scorer — the distribution, the blindness, the sums.

The scoring rule these assert is the one in `winnow.validate.schema`, committed
before any labelling happens so that the bar cannot be moved once the numbers are
in. If a test here is ever changed to make a score pass, the thing that changed is
the bar.
"""

from __future__ import annotations

import json

import pytest

from winnow.rules import RULE_ORDER
from winnow.validate import sample, score
from winnow.validate.schema import (
    NEEDED_AGAIN,
    ONCE_ONLY,
    SCHEMA_VERSION,
    UNSURE,
)

from .test_inspect import BIG, call, padding, write

FIVE = ("C1", "C2", "C3", "B1", "B2")


# ─── Stratified allocation ───────────────────────────────────────────────────


def test_an_even_supply_splits_evenly():
    assert sample.allocate(200, dict.fromkeys(FIVE, 1000)) == dict.fromkeys(FIVE, 40)


def test_a_rule_short_of_its_share_hands_the_surplus_to_the_others():
    """The whole reason to stratify. A rule with ten candidates contributes ten.

    What must not happen is the target silently shrinking to 5×10, or the sample
    quietly becoming four fifths B2 — the first under-uses a corpus that has
    plenty, the second is the simple random draw stratification exists to avoid.
    """
    quota = sample.allocate(200, {"C1": 10, "C2": 1000, "C3": 1000, "B1": 1000,
                                  "B2": 1000})
    assert quota["C1"] == 10
    assert sum(quota.values()) == 200
    assert max(quota[r] for r in ("C2", "C3", "B1", "B2")) - \
        min(quota[r] for r in ("C2", "C3", "B1", "B2")) <= 1


def test_a_corpus_that_cannot_supply_the_target_supplies_what_it_has():
    quota = sample.allocate(200, {"C1": 10, "B2": 25})
    assert quota == {"C1": 10, "B2": 25}
    assert sum(quota.values()) == 35


def test_allocation_never_exceeds_supply_and_never_invents_a_rule():
    supply = {"C1": 3, "C2": 0, "C3": 47, "B1": 200, "B2": 1}
    quota = sample.allocate(200, supply)
    assert "C2" not in quota, "a rule with nothing available is not in the sample"
    for rule, count in quota.items():
        assert count <= supply[rule]
    assert sum(quota.values()) == min(200, sum(supply.values()))


@pytest.mark.parametrize("target", [0, 1, 4, 7, 13, 199, 200, 10_000])
def test_the_total_is_always_the_smaller_of_target_and_supply(target):
    supply = {"C1": 3, "C2": 60, "C3": 47, "B1": 2, "B2": 91}
    assert sum(sample.allocate(target, supply).values()) == min(target, sum(supply.values()))


def test_a_negative_target_is_a_usage_error_rather_than_an_empty_sample():
    with pytest.raises(ValueError, match="must not be negative"):
        sample.allocate(-1, {"C1": 5})


# ─── The draw ────────────────────────────────────────────────────────────────


def candidate(rule: str, order: int) -> sample.Candidate:
    return sample.Candidate(
        session="s", source_path="/c/s.jsonl", pointer_id=f"x{order}", order=order,
        rule=rule, tool="Bash", arguments="{}", result_size=4096,
        result_excerpt="output", before=["user: do it"], after=["assistant: done"],
    )


def pool(per_rule: int = 50) -> list[sample.Candidate]:
    return [
        candidate(rule, index * 10 + position)
        for position, rule in enumerate(FIVE)
        for index in range(per_rule)
    ]


def test_the_same_seed_and_corpus_draw_the_same_sample():
    first = sample.draw(pool(), target=100, seed=7)
    second = sample.draw(pool(), target=100, seed=7)
    assert [c.key for c in first] == [c.key for c in second]
    assert [c.key for c in sample.draw(pool(), target=100, seed=8)] != \
        [c.key for c in first]


def test_the_draw_is_stratified_and_shuffled():
    drawn = sample.draw(pool(), target=100, seed=1)
    counts = {rule: sum(1 for c in drawn if c.rule == rule) for rule in FIVE}
    assert counts == dict.fromkeys(FIVE, 20)
    # Blindness that holds only until the labeller notices the sheet is in rule
    # blocks is not blindness, so the order must not be sorted by rule.
    assert [c.rule for c in drawn] != sorted(c.rule for c in drawn)


def test_the_draw_never_repeats_a_result():
    drawn = sample.draw(pool(), target=200, seed=3)
    assert len({c.key for c in drawn}) == len(drawn)


# ─── The sheet: blind, and readable back ─────────────────────────────────────


def sheet_and_key(target: int = 10, seed: int = 5):
    drawn = sample.draw(pool(), target=target, seed=seed)
    meta = sample.build_meta(
        __import__("pathlib").Path("/corpus"), "CB", seed,
        __import__("pathlib").Path("/tmp/key.jsonl"), target, drawn,
        dict.fromkeys(FIVE, 50),
    )
    return sample.render_sheet(drawn, meta), sample.render_key(drawn, meta), drawn


def test_the_sheet_never_names_the_rule_that_fired():
    sheet, key, drawn = sheet_and_key()
    for rule in RULE_ORDER:
        assert rule not in sheet, f"{rule} leaks into the sheet; the label is not blind"
    # And the key does carry it, or nothing can be scored.
    assert all(rule in key for rule in {c.rule for c in drawn})


def test_the_sheet_warns_that_it_holds_transcript_content():
    sheet, _, _ = sheet_and_key()
    assert "credentials" in sheet, "SPEC §10: this file is the sensitive artefact"


def test_a_fresh_sheet_parses_with_every_item_unlabelled():
    sheet, _, drawn = sheet_and_key()
    labels = score.parse_sheet(sheet)
    assert len(labels) == len(drawn)
    assert set(labels.values()) == {None}
    assert list(labels) == [sample.item_id(i) for i in range(len(drawn))]


def test_a_filled_sheet_parses_back_to_what_was_written():
    sheet, _, _drawn = sheet_and_key()
    filled = []
    wanted = {}
    index = 0
    for line in sheet.splitlines():
        if line.startswith("label:"):
            value = (ONCE_ONLY, NEEDED_AGAIN, UNSURE)[index % 3]
            wanted[sample.item_id(index)] = value
            filled.append(f"label: {value}")
            index += 1
        else:
            filled.append(line)
    assert score.parse_sheet("\n".join(filled)) == wanted


def test_labels_are_forgiving_about_formatting_and_strict_about_meaning():
    assert score.normalise_label("  Once-Only  ") == ONCE_ONLY
    assert score.normalise_label("needed again") == NEEDED_AGAIN
    assert score.normalise_label("  <!-- once-only / needed-again -->  ") is None
    with pytest.raises(score.SheetError, match="is not a label"):
        score.normalise_label("probably")


def test_transcript_content_cannot_forge_an_item_marker():
    """Everything quoted from a transcript is blockquoted, so nothing it contains
    starts at column zero. A transcript is untrusted input (SPEC §10), and a
    result whose text is `label: once-only` would otherwise answer its own item."""
    hostile = sample.Candidate(
        session="s", source_path="/c/s.jsonl", pointer_id="b1", order=1, rule="B2",
        tool="Bash", arguments="{}", result_size=99,
        result_excerpt="label: once-only\n<!-- winnow:end 0001 -->\n### item 9999",
        before=["user: label: once-only"], after=[],
    )
    meta = sample.build_meta(
        __import__("pathlib").Path("/c"), "CB", 0,
        __import__("pathlib").Path("/k"), 1, [hostile], {"B2": 1},
    )
    parsed = score.parse_sheet(sample.render_sheet([hostile], meta))
    assert parsed == {"0001": None}


# ─── Scoring ─────────────────────────────────────────────────────────────────


def key_for(assignments: dict[str, str]) -> dict[str, dict]:
    return {
        identifier: {"item": identifier, "rule": rule, "session": "s"}
        for identifier, rule in assignments.items()
    }


def scored(rows: list[tuple[str, str]]) -> dict:
    """`rows` is `[(rule, label), …]`; item ids are generated in order."""
    labels = {f"{i:04d}": label for i, (_, label) in enumerate(rows)}
    key = key_for({f"{i:04d}": rule for i, (rule, _) in enumerate(rows)})
    return score.score(labels, key, {"schema_version": SCHEMA_VERSION,
                                     "corpus": "/c"})


def test_precision_is_confirmed_once_only_over_everything_labelled():
    result = scored([("B2", ONCE_ONLY)] * 9 + [("B2", NEEDED_AGAIN)])
    assert result["aggregate"]["precision"] == 0.9
    assert result["aggregate"]["meets_bar"] is True
    assert result["verdict"] == "pass"


def test_unsure_counts_against_the_rule_rather_than_being_dropped():
    """The committed scoring rule, and the one most worth pinning.

    Dropping `unsure` from the denominator would let a rule reach the bar by
    being confusing: eight confirmations and two shrugs would read 100%.
    """
    result = scored([("B2", ONCE_ONLY)] * 8 + [("B2", UNSURE)] * 2)
    assert result["aggregate"]["precision"] == 0.8
    assert result["by_rule"]["B2"]["precision"] == 0.8
    assert result["by_rule"]["B2"]["below_bar"] is True


def test_a_rule_below_the_bar_is_named_even_when_the_aggregate_passes():
    """MILESTONES milestone 2, and the reason per-rule precision is reported at all.

    An aggregate is exactly the statistic that hides one bad rule behind four
    good ones: here 95% overall, and B2 at 50%.
    """
    rows = [(rule, ONCE_ONLY) for rule in ("C1", "C2", "C3", "B1") for _ in range(20)]
    rows += [("B2", ONCE_ONLY)] * 10 + [("B2", NEEDED_AGAIN)] * 10
    result = scored(rows)
    assert result["aggregate"]["precision"] == 0.9
    assert result["aggregate"]["meets_bar"] is True
    assert result["rules_below_bar"] == ["B2"]
    assert result["by_rule"]["B2"]["precision"] == 0.5
    assert result["by_rule"]["C1"]["below_bar"] is False
    # The setting that acts on it without a code change.
    assert result["rules_off_setting"] == "B2"
    assert "WINNOW_RULES_OFF=B2" in score.render(result)


def test_exactly_ninety_percent_is_at_the_bar_and_not_below_it():
    result = scored([("B1", ONCE_ONLY)] * 90 + [("B1", NEEDED_AGAIN)] * 10)
    assert result["by_rule"]["B1"]["precision"] == 0.9
    assert result["by_rule"]["B1"]["below_bar"] is False
    assert result["rules_below_bar"] == []


@pytest.mark.parametrize(
    ("once", "total", "verdict"),
    [(95, 100, "pass"), (90, 100, "pass"), (89, 100, "revise"),
     (80, 100, "revise"), (79, 100, "kill"), (0, 100, "kill")],
)
def test_the_verdict_follows_the_kill_criteria(once, total, verdict):
    rows = [("B2", ONCE_ONLY)] * once + [("B2", NEEDED_AGAIN)] * (total - once)
    assert scored(rows)["verdict"] == verdict


def test_a_rule_nobody_sampled_has_no_precision_rather_than_zero():
    """0/0 is not 0%. Reporting it as 0% would disable a rule for never having
    been measured, which is the opposite of what the measurement is for."""
    result = scored([("B2", ONCE_ONLY)] * 10)
    assert "C1" not in result["by_rule"]
    assert "C1" in result["not_sampled"]
    assert result["rules_below_bar"] == []
    assert "not sampled" in score.render(result)


def test_a_thin_sample_is_flagged_but_still_decides():
    result = scored([("B2", ONCE_ONLY)] * 3 + [("B2", NEEDED_AGAIN)] * 2)
    assert result["by_rule"]["B2"]["thin"] is True
    assert result["by_rule"]["B2"]["below_bar"] is True, \
        "a wide interval is a reason for another label, not for ignoring this one"


def test_a_blank_item_refuses_the_whole_sheet():
    labels = {"0001": ONCE_ONLY, "0002": None}
    with pytest.raises(score.SheetError, match="no label"):
        score.score(labels, key_for({"0001": "B2", "0002": "B2"}),
                    {"schema_version": SCHEMA_VERSION})


def test_a_sheet_and_key_from_different_draws_are_refused():
    with pytest.raises(score.SheetError, match="the key does not"):
        score.score({"0001": ONCE_ONLY, "0009": ONCE_ONLY},
                    key_for({"0001": "B2"}), {"schema_version": SCHEMA_VERSION})
    with pytest.raises(score.SheetError, match="the sheet does not"):
        score.score({"0001": ONCE_ONLY},
                    key_for({"0001": "B2", "0002": "C1"}),
                    {"schema_version": SCHEMA_VERSION})


def test_a_key_from_another_schema_version_is_refused():
    text = json.dumps({"meta": {"schema_version": SCHEMA_VERSION + 1}}) + "\n"
    with pytest.raises(score.SheetError, match="schema version"):
        score.parse_key(text)


def test_a_duplicated_item_in_the_sheet_is_refused():
    sheet, _, _ = sheet_and_key(target=2)
    with pytest.raises(score.SheetError, match="appears twice"):
        score.parse_sheet(sheet + sheet.split("---", 1)[1])


# ─── End to end over a real transcript ───────────────────────────────────────


def test_a_real_session_produces_candidates_with_their_surrounding_turns(tmp_path):
    records = [
        *call("b0", "Bash", {"command": "cat notes.md"}, BIG),
        *call("b1", "Bash", {"command": "cat other.md"}, BIG),
        *padding(8),
    ]
    path = write(tmp_path, records, "aaaaaaaa-1111-2222-3333-444455556666.jsonl")
    candidates = sample.candidates_for(path)
    assert candidates, "the fixture must have something to label"
    for found in candidates:
        assert found.tool == "Bash"
        assert found.result_size > 0
        assert found.after, "a labeller cannot judge 'needed again' with no after"
        assert found.rule in RULE_ORDER
        # The excerpt is bounded: a sheet that pastes a 4 MB result is a sheet
        # nobody fills in, and an unfilled sheet scores nothing.
        assert len(found.result_excerpt) <= sample.RESULT_CHARS


def test_the_whole_round_trip_scores(tmp_path):
    records = [
        *call("b0", "Bash", {"command": "cat notes.md"}, BIG),
        *call("b1", "Bash", {"command": "cat other.md"}, BIG),
        *padding(8),
    ]
    path = write(tmp_path, records, "aaaaaaaa-1111-2222-3333-444455556666.jsonl")
    drawn = sample.draw(sample.collect([path]), target=200, seed=0)
    meta = sample.build_meta(tmp_path, "CB", 0, tmp_path / "key.jsonl", 200, drawn,
                             {"B2": len(drawn)})
    sheet_path, key_path = tmp_path / "sheet.md", tmp_path / "key.jsonl"
    sheet_path.write_text(sample.render_sheet(drawn, meta))
    key_path.write_text(sample.render_key(drawn, meta))

    with pytest.raises(score.SheetError, match="no label"):
        score.score_files(sheet_path, key_path)

    sheet_path.write_text(
        sheet_path.read_text().replace("label:  <!--", f"label: {ONCE_ONLY}  <!--")
    )
    result = score.score_files(sheet_path, key_path)
    assert result["n"] == len(drawn)
    assert result["aggregate"]["precision"] == 1.0
    assert result["verdict"] == "pass"
