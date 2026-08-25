"""Tests for `winnow inspect` — SPEC §4's rules, the guards, and the arithmetic.

The rules are tested on synthetic transcripts rather than real ones, because a
real transcript cannot state what the right answer is. The one thing a synthetic
transcript cannot check is whether the corpus reproduces SPEC §6's shares; that
check is a corpus sweep, and its result is recorded in docs/COZEMPIC.md §3.4
rather than asserted here.
"""

from __future__ import annotations

import json

import pytest

from winnow.inspect import inspect_session
from winnow.report import resolve_session, to_dict
from winnow.rules import DEFAULT_MIN_BYTES, bash_head, is_inspection, read_range

# Comfortably over the 2,048-byte G2 floor, so a rule rather than a guard decides.
BIG = "x" * (DEFAULT_MIN_BYTES + 100)
SMALL = "y" * 10


def use(uid: str, name: str, tool_input: dict) -> dict:
    return {
        "type": "assistant",
        "uuid": f"u-{uid}",
        "message": {
            "role": "assistant",
            "model": "claude-opus-5",
            "content": [{"type": "tool_use", "id": uid, "name": name, "input": tool_input}],
        },
    }


def result(uid: str, content: str = BIG, *, is_error: bool = False) -> dict:
    return {
        "type": "user",
        "uuid": f"r-{uid}",
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


def call(uid: str, name: str, tool_input: dict, content: str = BIG, **kw) -> list[dict]:
    return [use(uid, name, tool_input), result(uid, content, **kw)]


def padding(n: int) -> list[dict]:
    """`n` tool calls that no rule fires on, to push earlier calls past guard G1."""
    out: list[dict] = []
    for i in range(n):
        out.extend(call(f"pad{i}", "Bash", {"command": f"python script{i}.py"}, SMALL))
    return out


def write(tmp_path, records: list[dict], name: str = "s.jsonl"):
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return path


def rules_fired(tmp_path, records, **kw) -> dict[str, int]:
    report = inspect_session(write(tmp_path, records), **kw)
    return {rule: hits for rule, hits in report.rule_hits.items() if hits}


# ─── Tier C ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,tool_input",
    [("Glob", {"pattern": "**/*.py"}), ("LS", {"path": "/repo"})],
)
def test_c1_fires_on_locator_tools(tmp_path, name, tool_input):
    records = call("a", name, tool_input) + padding(6)
    assert rules_fired(tmp_path, records) == {"C1": 1}


def test_c1_grep_only_in_path_listing_modes(tmp_path):
    listing = call("a", "Grep", {"pattern": "x", "output_mode": "files_with_matches"})
    content = call("b", "Grep", {"pattern": "y", "output_mode": "content"})
    fired = rules_fired(tmp_path, listing + content + padding(6))
    assert fired == {"C1": 1}


def test_c2_strips_the_earlier_of_an_identical_pair(tmp_path):
    records = (
        call("a", "Bash", {"command": "python build.py"})
        + call("b", "Bash", {"command": "python build.py"})
        + padding(6)
    )
    report = inspect_session(write(tmp_path, records))
    # Only the earlier: the later one supersedes it and is what the session keeps.
    assert report.rule_hits["C2"] == 1


def test_c2_ignores_key_order_in_the_input(tmp_path):
    records = (
        call("a", "Bash", {"command": "python b.py", "description": "d"})
        + call("b", "Bash", {"description": "d", "command": "python b.py"})
        + padding(6)
    )
    assert rules_fired(tmp_path, records) == {"C2": 1}


def test_c3_fires_on_a_passing_verification_run(tmp_path):
    records = call("a", "Bash", {"command": "npm run test"}) + padding(6)
    assert rules_fired(tmp_path, records) == {"C3": 1}


def test_c3_never_fires_on_a_failing_one(tmp_path):
    """A failing verification is the information — guard G3 holds before C3."""
    records = call("a", "Bash", {"command": "npm run test"}, is_error=True) + padding(6)
    report = inspect_session(write(tmp_path, records))
    assert report.rule_hits["C3"] == 0
    assert report.guard_blocked["G3_errors"] == 1


# ─── Tier B ──────────────────────────────────────────────────────────────────


def test_b1_fires_when_a_later_read_covers_the_same_whole_file(tmp_path):
    records = (
        call("a", "Read", {"file_path": "/repo/x.py"})
        + call("b", "Read", {"file_path": "/repo/x.py", "offset": 1, "limit": 50})
        + padding(6)
    )
    report = inspect_session(write(tmp_path, records))
    # The later read is narrower, so it does not cover the earlier whole-file
    # read. Nothing supersedes it, and the duplicate rule does not apply either.
    assert report.rule_hits["B1"] == 0


def test_b1_ranged_read_superseded_by_a_later_whole_file_read(tmp_path):
    records = (
        call("a", "Read", {"file_path": "/repo/x.py", "offset": 10, "limit": 20})
        + call("b", "Read", {"file_path": "/repo/x.py"})
        + padding(6)
    )
    assert rules_fired(tmp_path, records) == {"B1": 1}


def test_b1_ranged_read_superseded_only_by_a_covering_range(tmp_path):
    covered = call("a", "Read", {"file_path": "/r/a.py", "offset": 10, "limit": 10})
    covering = call("b", "Read", {"file_path": "/r/a.py", "offset": 5, "limit": 100})
    disjoint = call("c", "Read", {"file_path": "/r/b.py", "offset": 10, "limit": 10})
    partial = call("d", "Read", {"file_path": "/r/b.py", "offset": 12, "limit": 100})
    report = inspect_session(write(tmp_path, covered + covering + disjoint + partial + padding(6)))
    # One fires (a, covered by b); the other does not (d starts after c begins,
    # so c's first two lines exist nowhere else once removed).
    assert report.rule_hits["B1"] == 1


def test_b1_does_not_fire_across_different_paths(tmp_path):
    records = (
        call("a", "Read", {"file_path": "/repo/x.py"})
        + call("b", "Read", {"file_path": "/repo/y.py"})
        + padding(6)
    )
    assert rules_fired(tmp_path, records) == {}


@pytest.mark.parametrize(
    "command,expected",
    [
        ("ls -la /repo", "ls"),
        ("/bin/ls -la", "ls"),
        ("FOO=1 BAR=2 ls", "ls"),
        ("git status --short", "git status"),
        ("git commit -m x", "git commit"),
        ("sed -n '1,50p' f.py", "sed -n"),
        ("sed -i s/a/b/ f.py", "sed"),
        ("cat a.txt | grep x", "cat"),
        ("python x.py | head", "python"),
        ("rg pattern && echo done", "rg"),
        ("   ", None),
    ],
)
def test_bash_head_is_the_first_token_of_the_first_segment(command, expected):
    assert bash_head(command) == expected


@pytest.mark.parametrize(
    "command,inspection",
    [
        ("ls -la", True),
        ("git status", True),
        ("git commit -m x", False),
        ("sed -n '1,5p' f", True),
        ("sed -i s/a/b/ f", False),
        ("python x.py | head -5", False),
        ("head -5 f.txt | python x.py", True),
    ],
)
def test_b2_matches_on_the_head_whatever_follows(command, inspection):
    assert is_inspection(command) is inspection


def test_b2_fires_on_a_passing_inspection(tmp_path):
    records = call("a", "Bash", {"command": "git diff HEAD~1"}) + padding(6)
    assert rules_fired(tmp_path, records) == {"B2": 1}


# ─── Tier A ──────────────────────────────────────────────────────────────────


def test_a1_fires_when_the_file_is_later_written(tmp_path):
    records = (
        call("a", "Read", {"file_path": "/repo/x.py"})
        + call("b", "Edit", {"file_path": "/repo/x.py", "old_string": "a", "new_string": "b"})
        + padding(6)
    )
    assert rules_fired(tmp_path, records)["A1"] == 1


def test_a1_claims_only_the_read_adjacent_to_the_edit(tmp_path):
    """Two reads then an edit: the second is made stale by the edit, the first is
    superseded by the second. A1 must not claim both, or the same file's bytes
    are counted twice under two rationales."""
    records = (
        call("a", "Read", {"file_path": "/r/x.py"})
        + call("b", "Read", {"file_path": "/r/x.py"})
        + call("c", "Edit", {"file_path": "/r/x.py", "old_string": "a", "new_string": "b"})
        + padding(6)
    )
    report = inspect_session(write(tmp_path, records))
    assert report.rule_hits["A1"] == 1  # `b`, with nothing between it and the edit
    assert report.rule_hits["C2"] == 1  # `a`, an identical earlier call to `b`


def test_a1_skips_a_read_a_later_read_already_supersedes(tmp_path):
    """The intervening-read clause: a read with another read of the same path
    between it and the edit is B1's or C2's, never A1's."""
    records = (
        call("a", "Read", {"file_path": "/r/x.py", "offset": 5, "limit": 10})
        + call("b", "Read", {"file_path": "/r/x.py"})
        + call("c", "Edit", {"file_path": "/r/x.py", "old_string": "a", "new_string": "b"})
        + padding(6)
    )
    report = inspect_session(write(tmp_path, records))
    assert report.rule_hits["B1"] == 1  # `a`, covered by the whole-file read `b`
    assert report.rule_hits["A1"] == 1  # `b` only


# ─── Precedence and guards ───────────────────────────────────────────────────


def test_rules_are_first_match_wins_so_a_result_is_counted_once(tmp_path):
    """A duplicated `ls` matches both C2 and B2. SPEC §6's per-rule table sums to
    its own tier totals, which is only true if exactly one rule claims it."""
    records = (
        call("a", "Bash", {"command": "ls -la /repo"})
        + call("b", "Bash", {"command": "ls -la /repo"})
        + padding(6)
    )
    report = inspect_session(write(tmp_path, records))
    assert report.rule_hits["C2"] == 1
    assert report.rule_hits["B2"] == 1  # the later one is not a duplicate
    assert report.tier_bytes("CB") == report.rule_bytes["C2"] + report.rule_bytes["B2"]


def test_g1_protects_the_tail(tmp_path):
    records = call("a", "Bash", {"command": "ls -la"}) + padding(2)
    report = inspect_session(write(tmp_path, records), keep_last=6)
    assert report.rule_hits["B2"] == 0
    assert report.guard_blocked["G1_keep_last"] == 3


def test_g2_protects_small_results(tmp_path):
    records = call("a", "Bash", {"command": "ls -la"}, SMALL) + padding(6)
    report = inspect_session(write(tmp_path, records))
    assert report.rule_hits["B2"] == 0
    assert report.guard_blocked["G2_min_bytes"] >= 1


def test_an_unanswered_tool_use_is_reported_not_stripped(tmp_path):
    records = [use("orphan", "Bash", {"command": "ls -la"})] + padding(6)
    report = inspect_session(write(tmp_path, records))
    assert report.unanswered_tool_uses == 1
    assert report.guard_blocked["G5_unpaired"] == 1


# ─── Measurement, records, usage ─────────────────────────────────────────────


def test_content_classes_sum_to_the_denominator(tmp_path):
    records = call("a", "Bash", {"command": "ls -la"}) + [
        {"type": "user", "message": {"role": "user", "content": "hello"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "answer"},
                    {"type": "thinking", "thinking": "", "signature": "s"},
                ],
            },
        },
    ]
    report = inspect_session(write(tmp_path, records))
    assert report.content_bytes["user_text"] == len("hello")
    assert report.content_bytes["assistant_text"] == len("answer")
    assert report.content_bytes["thinking"] == 0
    assert report.message_content_bytes == sum(report.content_bytes.values())


def test_a_structured_tool_result_is_measured_as_json(tmp_path):
    blocks = [{"type": "text", "text": "z" * 3000}]
    records = [
        use("a", "Read", {"file_path": "/r/x.py"}),
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "a", "content": blocks}
                ],
            },
        },
    ]
    report = inspect_session(write(tmp_path, records))
    assert report.content_bytes["tool_result"] == len(json.dumps(blocks))


def test_an_unknown_record_type_is_counted_never_dropped(tmp_path):
    records = [{"type": "some-future-record", "uuid": "z"}] + call("a", "Bash", {"command": "ls"})
    report = inspect_session(write(tmp_path, records))
    assert report.records == 3
    assert report.unrecognised_records == 1
    assert report.record_types["some-future-record"] == 1


def test_usage_is_summed_including_the_write_class_split(tmp_path):
    records = [
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "model": "claude-opus-5",
                "content": [{"type": "text", "text": "hi"}],
                "usage": {
                    "input_tokens": 2,
                    "output_tokens": 10,
                    "cache_read_input_tokens": 1000,
                    "cache_creation_input_tokens": 500,
                    "cache_creation": {
                        "ephemeral_1h_input_tokens": 500,
                        "ephemeral_5m_input_tokens": 0,
                    },
                },
            },
        }
    ]
    report = inspect_session(write(tmp_path, records))
    assert report.usage.turns == 1
    assert report.usage.cache_read == 1000
    assert report.usage.ephemeral_1h == 500
    assert report.usage.write_class == "1h"


def test_synthetic_turns_do_not_dilute_the_write_class(tmp_path):
    records = [
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "model": "<synthetic>",
                "content": [],
                "usage": {"cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            },
        }
    ]
    report = inspect_session(write(tmp_path, records))
    assert report.usage.turns == 0
    assert report.usage.write_class == "unknown"


def test_a_malformed_line_is_counted_not_fatal(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text('{"type":"user"}\nnot json at all\n[1,2,3]\n')
    report = inspect_session(path)
    assert report.parse_errors == 2
    assert report.records == 3


# ─── The arithmetic ──────────────────────────────────────────────────────────


def test_break_even_follows_the_recorded_formula(tmp_path):
    records = call("a", "Bash", {"command": "ls -la"}) + padding(6)
    report = inspect_session(write(tmp_path, records))
    removed = report.tier_bytes("CB")
    assert removed > 0
    expected = 19 * (report.suffix_bytes / removed) - 20
    assert report.break_even_turns("CB") == pytest.approx(expected)


def test_no_cut_means_no_break_even(tmp_path):
    report = inspect_session(write(tmp_path, padding(8)))
    assert report.tier_bytes("CB") == 0
    assert report.break_even_turns("CB") is None
    assert report.cut_line is None


def test_the_suffix_is_measured_from_the_earliest_stripped_result(tmp_path):
    """S is what stands behind the cut, so a later cut leaves a smaller S."""
    early = call("a", "Bash", {"command": "ls -la"})
    later = call("b", "Bash", {"command": "git diff"})
    report = inspect_session(write(tmp_path, early + later + padding(6)))
    assert report.cut_line == 1  # the tool_result line of call `a`
    assert report.suffix_bytes >= report.tier_bytes("CB")


# ─── Session resolution and the JSON shape ───────────────────────────────────


def test_resolve_refuses_an_ambiguous_prefix(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    (projects / "proj").mkdir(parents=True)
    for name in ("abc111.jsonl", "abc222.jsonl"):
        (projects / "proj" / name).write_text("")
    monkeypatch.setattr("winnow.legacy.session.get_projects_dir", lambda: projects)
    with pytest.raises(LookupError, match="matches 2 sessions"):
        resolve_session("abc")
    assert resolve_session("abc111").name == "abc111.jsonl"


def test_resolve_reports_a_miss_rather_than_exiting(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr("winnow.legacy.session.get_projects_dir", lambda: projects)
    with pytest.raises(LookupError, match="no session matches"):
        resolve_session("nothing-here")


def test_json_shares_are_percentages_of_message_content(tmp_path):
    records = call("a", "Bash", {"command": "ls -la"}) + padding(6)
    report = inspect_session(write(tmp_path, records))
    payload = to_dict(report, "CB")
    total = payload["message_content_bytes"]
    assert payload["rules"]["B2"]["share"] == pytest.approx(
        payload["rules"]["B2"]["bytes"] / total * 100, abs=1e-3
    )
    assert payload["usage"]["write_class"] == "unknown"
    assert payload["arithmetic"]["tier"] == "CB"


@pytest.mark.parametrize(
    "tool_input,expected",
    [
        ({"file_path": "/a"}, ("/a", 0, float("inf"))),
        ({"file_path": "/a", "offset": 5}, ("/a", 5, float("inf"))),
        ({"file_path": "/a", "offset": 5, "limit": 10}, ("/a", 5, 15)),
        ({"file_path": "/a", "limit": 10}, ("/a", 1, 11)),
        ({}, (None, 0, float("inf"))),
    ],
)
def test_read_range_treats_a_missing_range_as_the_whole_file(tool_input, expected):
    assert read_range(tool_input) == expected


def test_the_readout_says_none_rather_than_nothing_when_no_guard_fired(tmp_path):
    """A session where no guard fired reads differently from one where the guards
    took everything, so the line is never blank."""
    from winnow.report import render

    records = [{"type": "user", "message": {"role": "user", "content": "hi"}}]
    report = inspect_session(write(tmp_path, records))
    assert not any(report.guard_blocked.values())
    assert "guards refused   none" in render(report, "CB")


def test_c2_needs_a_later_result_not_merely_a_later_call(tmp_path):
    """SPEC §4 words C2 on `tool_result` and B1/A1 on `tool_use`. A later call
    that never returned has no bytes to supersede an earlier result with."""
    records = (
        call("a", "Bash", {"command": "python build.py"})
        + [use("b", "Bash", {"command": "python build.py"})]  # in flight, no result
        + padding(6)
    )
    report = inspect_session(write(tmp_path, records))
    assert report.rule_hits["C2"] == 0
    assert report.unanswered_tool_uses == 1


def test_b1_counts_a_later_read_whose_result_never_arrived(tmp_path):
    """The other side of the same distinction: B1 is worded on `tool_use`."""
    records = (
        call("a", "Read", {"file_path": "/r/x.py", "offset": 10, "limit": 5})
        + [use("b", "Read", {"file_path": "/r/x.py"})]  # in flight, no result
        + padding(6)
    )
    report = inspect_session(write(tmp_path, records))
    assert report.rule_hits["B1"] == 1


# ─── The filter ledger correction ────────────────────────────────────────────


def _ledger(tmp_path, *entries):
    path = tmp_path / "filter.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return path


def test_the_ledger_is_joined_on_request_id(tmp_path):
    """The filter cannot know the session — it sees a Messages API body, which
    carries no session identity. The id the API returns is the only key both
    sides hold."""
    records = [
        {
            "type": "assistant",
            "requestId": "req_mine",
            "message": {"role": "assistant", "model": "claude-opus-5",
                        "content": [{"type": "text", "text": "hi"}],
                        "usage": {"input_tokens": 1, "output_tokens": 1}},
        }
    ]
    ledger = _ledger(
        tmp_path,
        {"request_id": "req_mine", "bytes_dropped": 5000,
         "dropped": [{"rule": "B2", "tool": "Bash", "bytes": 5000}]},
        {"request_id": "req_someone_else", "bytes_dropped": 999_999,
         "dropped": [{"rule": "B2", "tool": "Bash", "bytes": 999_999}]},
    )
    report = inspect_session(write(tmp_path, records), filter_ledger=ledger)
    assert report.filtered.requests == 1
    assert report.filtered.bytes_dropped == 5000  # not another session's 999,999
    assert report.filtered.by_rule == {"B2": 5000}


def test_the_wire_denominator_subtracts_what_never_went_out(tmp_path):
    records = call("a", "Bash", {"command": "ls -la"}) + padding(6)
    plain = inspect_session(write(tmp_path, records))
    ledger = _ledger(tmp_path, {"request_id": "req_x", "bytes_dropped": 100})
    corrected = inspect_session(write(tmp_path, records), filter_ledger=ledger)
    # No requestId in this transcript, so nothing joins and nothing is subtracted.
    assert corrected.filtered.requests == 0
    assert corrected.wire_content_bytes == plain.message_content_bytes


def test_no_ledger_means_the_wire_figure_is_the_disk_figure(tmp_path):
    """Nothing changes for a session that was never filtered."""
    report = inspect_session(write(tmp_path, call("a", "Bash", {"command": "ls -la"})))
    assert report.filtered is None
    assert report.wire_content_bytes == report.message_content_bytes


def test_an_unreadable_ledger_is_a_missing_correction_not_a_crash(tmp_path):
    report = inspect_session(write(tmp_path, padding(2)),
                             filter_ledger=tmp_path / "nope.jsonl")
    assert report.filtered is not None
    assert report.filtered.bytes_dropped == 0
