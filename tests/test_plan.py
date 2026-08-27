"""Tests for `winnow plan` — the selection, the pointer, guard G4, and determinism.

Synthetic transcripts, for the reason `test_inspect.py` gives: a real transcript
cannot state what the right answer is. Nothing here reads `~/.claude/projects/`.

The split against `test_inspect.py` is deliberate. That file tests the rules as
`inspect` sees them — every rule enabled, no pointer, no G4 — which is the ceiling
SPEC §6 published. This file tests them as a *fork* would apply them: one
operator-chosen selection, each hit paired with the pointer that replaces it, and
G4 deciding per result whether the swap is worth taking.
"""

from __future__ import annotations

import json

import pytest

from winnow.plan import (
    PlanError,
    build_plan,
    plan_command,
    render,
    resolve_selection,
    to_dict,
)
from winnow.rules import (
    ALL_RULES,
    DEFAULT_MIN_BYTES,
    DISABLED_BY_DEFAULT,
    RuleSelectionError,
    default_disabled,
    parse_pointer_id,
    pointer_id,
    render_pointer,
    resolve_rules,
    suppressed_by_default,
)

from .test_inspect import BIG, SMALL, call, padding, write

# A realistic session ID, because the pointer quotes eight characters of it and
# the G4 boundary therefore moves with its length. `tmp_path / "s.jsonl"` would
# put the boundary seven bytes lower than any real session's.
SESSION = "5051d73c-1f2e-4a3b-9c8d-0e1f2a3b4c5d"


def pointer_length(size: int, tool: str = "Glob", rule: str = "C1") -> int:
    """The length of the pointer that would replace a `size`-byte result."""
    return len(render_pointer(
        tool=tool, rule=rule, size=size, digest="0" * 64,
        session_id=SESSION, identifier="c0",
    ))


def g4_boundary() -> int:
    """The exact size at which the pointer stops being longer than the result.

    Solved rather than written down. The pointer's own length depends on the
    size it quotes — `41,208 bytes` is four characters longer than `999 bytes` —
    so G4's boundary is a fixed point of `pointer_length`, not a constant, and a
    hard-coded 160 here would silently stop testing the boundary the day the
    template gains a character.
    """
    size = 1
    while pointer_length(size) > size:
        size = pointer_length(size)
    return size


BOUNDARY = g4_boundary()


def write_session(tmp_path, records):
    """The transcript under a realistic session filename. See `SESSION`."""
    return write(tmp_path, records, f"{SESSION}.jsonl")


def plan_for(tmp_path, records, tier="CB", **kw):
    return build_plan(write_session(tmp_path, records), tier=tier, **kw)


def stripped(plan) -> dict[str, int]:
    """Rule → count, for the results this plan would actually replace."""
    out: dict[str, int] = {}
    for strip in plan.strips:
        out[strip.rule] = out.get(strip.rule, 0) + 1
    return out


CB = frozenset({"C1", "C2", "C3", "B1", "B2"})
CBA = ALL_RULES


# ─── The rules, as a fork applies them ───────────────────────────────────────


@pytest.mark.parametrize(
    "rule,records",
    [
        ("C1", call("a", "Glob", {"pattern": "**/*.py"})),
        ("C2", call("a", "Bash", {"command": "python b.py"})
               + call("b", "Bash", {"command": "python b.py"})),
        ("C3", call("a", "Bash", {"command": "npm run test"})),
        # Ranged, then whole-file: a supersession that is not also a C2
        # duplicate, so B1 is what fires rather than the rule ahead of it.
        ("B1", call("a", "Read", {"file_path": "/r/x.py", "offset": 10, "limit": 20})
               + call("b", "Read", {"file_path": "/r/x.py"})),
        ("B2", call("a", "Bash", {"command": "git status"})),
    ],
)
def test_each_cb_rule_produces_one_strip(tmp_path, rule, records):
    plan = plan_for(tmp_path, records + padding(6), rules=CB)
    assert stripped(plan) == {rule: 1}


def test_a1_needs_the_opt_in_and_then_fires(tmp_path):
    records = (
        call("a", "Read", {"file_path": "/r/x.py"})
        + call("b", "Edit", {"file_path": "/r/x.py", "old_string": "p", "new_string": "q"},
               SMALL)
        + padding(6)
    )
    assert stripped(plan_for(tmp_path, records, rules=CB)) == {}
    assert stripped(plan_for(tmp_path, records, tier="CBA", rules=CBA)) == {"A1": 1}


# ─── SPEC §8 rule selection ──────────────────────────────────────────────────


def test_tier_selects_its_own_rules():
    assert resolve_selection("C") == {"C1", "C2", "C3"}
    assert resolve_selection("CB") == CB
    assert resolve_selection("CBA", i_know=True) == CBA


def test_tier_a_is_refused_without_the_acknowledgement():
    with pytest.raises(PlanError, match="opt-in"):
        resolve_selection("CBA")
    # Reaching A1 by name rather than by tier is the same opt-in and needs the
    # same flag; a --i-know that guarded only --tier CBA would guard nothing.
    with pytest.raises(PlanError, match="opt-in"):
        resolve_selection("CB", enable=["A1"])
    assert resolve_selection("CB", enable=["A1"], i_know=True) == CBA


def test_rule_and_no_rule_override_the_tier():
    assert resolve_selection("C", enable=["B2"]) == {"C1", "C2", "C3", "B2"}
    assert resolve_selection("CB", disable=["B1", "B2"]) == {"C1", "C2", "C3"}
    # Disable wins over enable whatever order they were typed in, so the flags
    # cannot produce a selection that depends on argv order.
    assert "B2" not in resolve_selection("C", enable=["B2"], disable=["B2"])


def test_rule_ids_are_case_insensitive_but_must_exist():
    assert resolve_selection("C", disable=["c1"]) == {"C2", "C3"}
    with pytest.raises(PlanError, match="unknown rule"):
        resolve_selection("C", enable=["B9"])
    with pytest.raises(PlanError, match="unknown tier"):
        resolve_selection("D")


# ─── A rule disabled by default on its own precision (MILESTONES milestone 2) ─


def test_nothing_is_disabled_by_default_until_the_label_has_been_scored():
    """The shipped default is empty, and that is a claim about evidence.

    A rule switched off here without a measured precision behind it would be the
    tool asserting a number nobody produced — the exact failure milestone 2 is
    built to catch. When the 200-sample label lands, this test changes with it,
    and the commit that changes it carries the number.
    """
    assert DISABLED_BY_DEFAULT == frozenset()
    assert default_disabled({}) == frozenset()


def test_a_default_off_rule_leaves_the_tier_it_belongs_to():
    assert resolve_rules("CB", disabled_by_default=["B2"]) == {"C1", "C2", "C3", "B1"}
    # Naming it explicitly turns it back on: the default says what the tool
    # believes without instruction, not what it refuses to do.
    assert "B2" in resolve_rules("CB", enable=["B2"], disabled_by_default=["B2"])
    # --no-rule is still applied last, so it wins over the re-enable.
    assert "B2" not in resolve_rules(
        "CB", enable=["B2"], disable=["B2"], disabled_by_default=["B2"]
    )


def test_the_environment_replaces_the_default_list_rather_than_adding_to_it():
    assert default_disabled({"WINNOW_RULES_OFF": "B2,A1"}) == {"B2", "A1"}
    assert default_disabled({"WINNOW_RULES_OFF": " b2   a1 "}) == {"B2", "A1"}
    # An override that could only subtract more would be a switch with no off
    # position: an empty value is how an operator runs every rule the tier names.
    assert default_disabled({"WINNOW_RULES_OFF": ""}) == frozenset()
    with pytest.raises(RuleSelectionError, match="WINNOW_RULES_OFF"):
        default_disabled({"WINNOW_RULES_OFF": "B9"})


def test_a_suppressed_rule_is_named_rather_than_silently_missing():
    """SPEC §10: no fallback that silently keeps a result the operator asked to strip.

    A tier that quietly means fewer rules than its own name lists is that
    fallback wearing a default's clothes, so the readout has to say it.
    """
    assert suppressed_by_default("CB", disabled_by_default=["B2"]) == ("B2",)
    # A rule outside the tier was never going to fire; reporting it as suppressed
    # would tell the operator a tier lost something it never had.
    assert suppressed_by_default("C", disabled_by_default=["B2"]) == ()
    # Neither an explicit --rule nor an explicit --no-rule is the default's doing.
    assert suppressed_by_default("CB", enable=["B2"], disabled_by_default=["B2"]) == ()
    assert suppressed_by_default("CB", disable=["B2"], disabled_by_default=["B2"]) == ()


def test_the_suppression_reaches_the_readout_and_the_json(tmp_path, monkeypatch):
    monkeypatch.setenv("WINNOW_RULES_OFF", "B2")
    records = [
        *call("i0", "Bash", {"command": "cat notes.md"}, BIG),
        *call("i1", "Bash", {"command": "cat other.md"}, BIG),
        *padding(8),
    ]
    path = write(tmp_path, records, f"{SESSION}.jsonl")
    code, output = plan_command(str(path))
    assert code == 2, output  # B2 was the only rule with anything to claim
    assert "off by default: B2" in output
    assert "--rule B2" in output

    code, output = plan_command(str(path), as_json=True)
    payload = json.loads(output.split("\n\nwinnow:")[0])
    assert payload["selection"]["suppressed_by_default"] == ["B2"]
    assert "B2" not in payload["selection"]["rules"]


def test_disabling_a_rule_lets_a_later_one_claim_the_same_result(tmp_path):
    """Selection decides which rules may fire, not which attributions survive.

    A file read twice matches C2 first (identical call) and B1 second (superseded
    read). Filtering attributions after a full-order classification would drop the
    earlier read entirely when C2 is off; skipping C2 in place lets B1 claim it,
    which is what the operator who typed `--no-rule C2` asked for.
    """
    records = (
        call("a", "Read", {"file_path": "/r/x.py"})
        + call("b", "Read", {"file_path": "/r/x.py"})
        + padding(6)
    )
    assert stripped(plan_for(tmp_path, records, rules=CB)) == {"C2": 1}
    without_c2 = plan_for(tmp_path, records, rules=CB - {"C2"})
    assert stripped(without_c2) == {"B1": 1}


# ─── The guards ──────────────────────────────────────────────────────────────


def test_g1_keeps_the_last_n_tool_results(tmp_path):
    records = call("a", "Glob", {"pattern": "*"}) + padding(6)
    assert stripped(plan_for(tmp_path, records, rules=CB, keep_last=6)) == {"C1": 1}
    # With keep-last 7 the Glob is inside the protected tail.
    assert stripped(plan_for(tmp_path, records, rules=CB, keep_last=7)) == {}


def test_g2_never_strips_a_result_under_min_bytes(tmp_path):
    # Above the G4 boundary, so that lowering --min-bytes actually reaches the
    # rule rather than handing the result to the next guard along.
    records = call("a", "Glob", {"pattern": "*"}, "z" * (BOUNDARY + 100)) + padding(6)
    assert stripped(plan_for(tmp_path, records, rules=CB, min_bytes=2048)) == {}
    assert stripped(plan_for(tmp_path, records, rules=CB, min_bytes=50)) == {"C1": 1}


def test_g3_errors_survive_at_every_tier(tmp_path):
    records = call("a", "Glob", {"pattern": "*"}, is_error=True) + padding(6)
    assert stripped(plan_for(tmp_path, records, tier="CBA", rules=CBA)) == {}
    assert plan_for(tmp_path, records, rules=CB).report.guard_blocked["G3_errors"] == 1


def test_g5_counts_an_unpaired_tool_use_and_never_plans_it(tmp_path):
    """G5's read-only form. A `tool_use` with no `tool_result` has nothing to
    strip, so a plan that mentioned it could only produce a broken fork."""
    from .test_inspect import use

    records = [use("orphan", "Glob", {"pattern": "*"})] + padding(6)
    plan = plan_for(tmp_path, records, rules=CB)
    assert plan.report.guard_blocked["G5_unpaired"] == 1
    assert plan.strips == []
    # Every strip a plan does produce names the block a writer must replace.
    real = plan_for(tmp_path, call("a", "Glob", {"pattern": "*"}) + padding(6), rules=CB)
    assert [s.use_id for s in real.strips] == ["a"]


# ─── Guard G4, at the boundary ───────────────────────────────────────────────


def test_the_g4_boundary_is_where_the_pointer_stops_being_longer():
    """The premise the two boundary tests below rest on, checked rather than assumed."""
    assert pointer_length(BOUNDARY - 1) > BOUNDARY - 1
    assert pointer_length(BOUNDARY) == BOUNDARY
    assert pointer_length(BOUNDARY + 1) <= BOUNDARY + 1


@pytest.mark.parametrize(
    "size,expect_strip",
    [
        (BOUNDARY - 1, False),  # pointer is longer: the content stays
        (BOUNDARY, True),       # exactly equal: removes nothing, inflates nothing
        (BOUNDARY + 1, True),   # one byte of saving is still a saving
    ],
)
def test_g4_decides_on_the_pointer_length_not_a_constant(tmp_path, size, expect_strip):
    records = call("a", "Glob", {"pattern": "*"}, "z" * size) + padding(6)
    # min_bytes below the boundary so that G2 cannot decide this instead of G4.
    plan = plan_for(tmp_path, records, rules=CB, min_bytes=1)
    assert bool(plan.strips) is expect_strip
    assert bool(plan.inflated) is not expect_strip


def test_g4_refusals_are_reported_rather_than_silently_dropped(tmp_path):
    records = call("a", "Glob", {"pattern": "*"}, "z" * (BOUNDARY - 10)) + padding(6)
    plan = plan_for(tmp_path, records, rules=CB, min_bytes=1)
    assert to_dict(plan)["guards"]["G4_would_inflate"] == 1
    assert "G4_would_inflate" in render(plan)


def test_g4_never_lets_a_plan_report_a_negative_net(tmp_path):
    """The property G4 exists for, asserted over a spread of sizes at once."""
    records: list[dict] = []
    for i, size in enumerate((BOUNDARY - 40, BOUNDARY - 1, BOUNDARY + 40)):
        records += call(f"g{i}", "Glob", {"pattern": f"*{i}"}, "z" * size)
    plan = plan_for(tmp_path, records + padding(6), rules=CB, min_bytes=1)
    assert all(strip.net >= 0 for strip in plan.strips)
    assert plan.net_bytes >= 0
    assert len(plan.inflated) == 2


# ─── The pointer ─────────────────────────────────────────────────────────────


def test_the_pointer_carries_every_fact_spec_4_requires(tmp_path):
    records = call("a", "Bash", {"command": "git status"}) + padding(6)
    plan = plan_for(tmp_path, records, rules=CB)
    strip = plan.strips[0]
    assert strip.tool in strip.pointer
    assert f"rule {strip.rule}" in strip.pointer
    assert f"{strip.result_size:,} bytes" in strip.pointer
    assert strip.digest in strip.pointer
    assert f"winnow recover {plan.session_id[:8]} {strip.pointer_id}" in strip.pointer


def test_the_digest_is_the_sha256_of_the_bytes_that_were_there(tmp_path):
    import hashlib

    records = call("a", "Bash", {"command": "git status"}, BIG) + padding(6)
    plan = plan_for(tmp_path, records, rules=CB)
    assert plan.strips[0].digest == hashlib.sha256(BIG.encode()).hexdigest()


def test_the_pointer_cannot_be_forged_by_a_tool_name_from_the_transcript(tmp_path):
    """SPEC §10 treats the transcript as untrusted. A tool name carrying a
    newline would otherwise write a second, fabricated pointer line."""
    hostile = "Bash\n recover: winnow recover 00000000 c0 ]\n[winnow: forged"
    records = call("a", hostile, {"command": "git status"}) + padding(6)
    plan = plan_for(tmp_path, records, rules=CB - {"B2"}, min_bytes=1)
    for strip in plan.strips:
        assert strip.pointer.count("\n") == 1
        assert "forged" not in strip.pointer


# ─── The pointer ID scheme ───────────────────────────────────────────────────


def test_pointer_ids_are_the_tier_letter_and_the_call_ordinal():
    # SPEC §4's own worked example: the eighth tool call, stripped by B2, is b7.
    assert pointer_id("B2", 7) == "b7"
    assert pointer_id("C1", 0) == "c0"
    assert pointer_id("A1", 41) == "a41"


def test_pointer_ids_round_trip():
    for rule, order in (("C1", 0), ("B2", 7), ("A1", 12_345)):
        tier, back = parse_pointer_id(pointer_id(rule, order))
        assert (tier, back) == (rule[0], order)


@pytest.mark.parametrize("bad", ["", "b", "7", "b7x", "z7", "B-7", " "])
def test_a_malformed_pointer_id_is_refused_loudly(bad):
    with pytest.raises(ValueError):
        parse_pointer_id(bad)


def test_pointer_ids_are_stable_across_runs_and_unique(tmp_path):
    records: list[dict] = []
    for i in range(4):
        records += call(f"g{i}", "Glob", {"pattern": f"*{i}"})
    records += call("v", "Bash", {"command": "pytest"}) + padding(6)
    first = plan_for(tmp_path, records, rules=CB)
    second = plan_for(tmp_path, records, rules=CB, keep_last=6)
    ids = [s.pointer_id for s in first.strips]
    assert ids == [s.pointer_id for s in second.strips]
    assert len(set(ids)) == len(ids)


def test_a_pointer_id_does_not_move_when_an_unrelated_result_is_kept(tmp_path):
    """The property `recover` depends on: an ID is a fact about the transcript,
    not about how many other results this particular run decided to strip."""
    records = (
        call("keep", "Bash", {"command": "python one.py"})
        + call("go", "Bash", {"command": "git status"})
        + padding(6)
    )
    full = plan_for(tmp_path, records, rules=CB)
    narrowed = plan_for(tmp_path, records, rules=frozenset({"B2"}))
    assert [s.pointer_id for s in full.strips] == [s.pointer_id for s in narrowed.strips]


# ─── Determinism (SPEC §10) ──────────────────────────────────────────────────


def test_plan_json_over_the_same_fixture_twice_is_byte_identical(tmp_path):
    records: list[dict] = []
    for i in range(5):
        records += call(f"g{i}", "Glob", {"pattern": f"*{i}"})
        records += call(f"r{i}", "Read", {"file_path": f"/r/{i}.py"})
    records += call("r0b", "Read", {"file_path": "/r/0.py"}) + padding(6)
    path = write_session(tmp_path, records)
    first = json.dumps(to_dict(build_plan(path, rules=CB), explain=True), indent=2)
    second = json.dumps(to_dict(build_plan(path, rules=CB), explain=True), indent=2)
    assert first == second


def test_the_committed_fixture_plans_identically_twice():
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "sessions" / "plan_demo.jsonl"
    runs = [
        json.dumps(to_dict(build_plan(fixture, rules=CB), explain=True), indent=2)
        for _ in range(2)
    ]
    assert runs[0] == runs[1]


# ─── The arithmetic SPEC §8 asks plan to print ───────────────────────────────


def test_the_net_is_the_removed_bytes_less_the_pointers(tmp_path):
    records: list[dict] = []
    for i in range(3):
        records += call(f"g{i}", "Glob", {"pattern": f"*{i}"})
    plan = plan_for(tmp_path, records + padding(6), rules=CB)
    assert plan.removed_bytes == sum(s.result_size for s in plan.strips)
    assert plan.pointer_bytes == sum(len(s.pointer) for s in plan.strips)
    assert plan.net_bytes == plan.removed_bytes - plan.pointer_bytes
    assert 0 < plan.net_bytes < plan.removed_bytes


def test_break_even_prices_the_net_not_the_gross(tmp_path):
    """`plan`'s T* is the longer of the two, because the pointers stay in the
    prefix and are cache-written with everything else."""
    records = call("a", "Glob", {"pattern": "*"}) + padding(6)
    plan = plan_for(tmp_path, records, rules=CB)
    expected = 19 * (plan.suffix_bytes / plan.net_bytes) - 20
    assert plan.break_even_turns() == pytest.approx(expected)
    gross = 19 * (plan.suffix_bytes / plan.removed_bytes) - 20
    assert plan.break_even_turns() > gross


def test_no_cut_means_no_break_even(tmp_path):
    plan = plan_for(tmp_path, padding(6), rules=CB)
    assert plan.strips == []
    assert plan.break_even_turns() is None
    assert plan.cut_line is None


def test_per_rule_and_per_tier_totals_sum_to_the_whole(tmp_path):
    """SPEC §8 asks for both breakdowns; they describe the same strips, so they
    must agree with each other and with the total."""
    records = (
        call("a", "Glob", {"pattern": "*"})
        + call("b", "Bash", {"command": "git status"})
        + call("c", "Bash", {"command": "pytest"})
        + call("d", "Read", {"file_path": "/r/x.py"})
        + call("e", "Read", {"file_path": "/r/x.py"})
        + padding(6)
    )
    plan = plan_for(tmp_path, records, rules=CB)
    by_rule = plan.by_rule()
    by_tier = plan.by_tier()
    assert sum(v["bytes"] for v in by_rule.values()) == plan.removed_bytes
    assert sum(v["bytes"] for v in by_tier.values()) == plan.removed_bytes
    assert sum(v["hits"] for v in by_rule.values()) == len(plan.strips)
    assert by_tier["C"]["bytes"] == sum(
        v["bytes"] for r, v in by_rule.items() if r.startswith("C")
    )


# ─── The command surface: exit codes and --explain ───────────────────────────


def test_exit_zero_and_the_json_shape_when_something_would_go(tmp_path):
    path = write_session(tmp_path, call("a", "Glob", {"pattern": "*"}) + padding(6))
    code, output = plan_command(str(path), as_json=True)
    assert code == 0
    payload = json.loads(output)
    assert payload["results"]["stripped"] == 1
    assert payload["bytes"]["net"] > 0
    assert payload["pointers"][0]["id"] == "c0"


def test_exit_two_when_no_result_meets_a_rule(tmp_path):
    path = write_session(tmp_path, padding(6))
    code, output = plan_command(str(path))
    assert code == 2
    assert "nothing to do" in output


def test_exit_two_names_the_guard_that_refused(tmp_path):
    """SPEC §8: a refusal is loud and names the guard."""
    path = write_session(tmp_path, call("a", "Glob", {"pattern": "*"}, "z" * 100) + padding(6))
    code, output = plan_command(str(path), min_bytes=DEFAULT_MIN_BYTES)
    assert code == 2
    assert "G2_min_bytes" in output and "--min-bytes" in output


def test_exit_two_names_g4_when_g4_took_everything(tmp_path):
    path = write_session(
        tmp_path, call("a", "Glob", {"pattern": "*"}, "z" * (BOUNDARY - 5)) + padding(6)
    )
    code, output = plan_command(str(path), min_bytes=1)
    assert code == 2
    assert "G4" in output


@pytest.mark.parametrize(
    "kwargs,fragment",
    [
        ({"tier": "CBA"}, "opt-in"),
        ({"rule": ["Z9"]}, "unknown rule"),
        ({"keep_last": -1}, "--keep-last"),
        ({"min_bytes": -1}, "--min-bytes"),
    ],
)
def test_exit_one_on_a_usage_error(tmp_path, kwargs, fragment):
    path = write_session(tmp_path, call("a", "Glob", {"pattern": "*"}) + padding(6))
    code, output = plan_command(str(path), **kwargs)
    assert code == 1
    assert fragment in output


def test_exit_one_when_the_session_cannot_be_resolved(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "winnow.legacy.session.get_projects_dir", lambda: tmp_path / "nope"
    )
    code, output = plan_command("d0e5f1a2")
    assert code == 1
    assert "winnow:" in output


def test_explain_prints_one_line_per_stripped_result(tmp_path):
    records = (
        call("a", "Glob", {"pattern": "**/*.py"})
        + call("b", "Bash", {"command": "git status --short"})
        + padding(6)
    )
    path = write_session(tmp_path, records)
    code, output = plan_command(str(path), explain=True)
    assert code == 0
    lines = [line for line in output.splitlines() if line.startswith(("  c", "  b"))]
    assert len(lines) == 2
    assert "**/*.py" in output and "git status --short" in output
    # SPEC §10: this output is sensitive and has to say so where it is read.
    assert "credentials" in output


def test_explain_bounds_an_enormous_argument(tmp_path):
    from winnow.plan import EXPLAIN_ARGUMENT_CHARS

    records = call("a", "Bash", {"command": "git status " + "-x" * 4000}) + padding(6)
    plan = plan_for(tmp_path, records, rules=CB)
    assert len(plan.strips[0].arguments) <= EXPLAIN_ARGUMENT_CHARS


def test_plan_writes_nothing(tmp_path):
    """SPEC §8's promise for the dry run, asserted rather than assumed."""
    path = write_session(tmp_path, call("a", "Glob", {"pattern": "*"}) + padding(6))
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    plan_command(str(path), explain=True)
    plan_command(str(path), as_json=True)
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert before == after


# ─── The filter ledger reaches the pruner ────────────────────────────────────
#
# There was no fixture anywhere in this repository representing a session the
# intake filter had run over. These are it. 79.0% of what `winnow plan --tier CB`
# proposes to remove is content the filter claims too, so on such a session the
# denominator, the shares and the break-even gate were all answering a question
# about a session that did not happen.


def _filtered_session(tmp_path, dropped_bytes: int):
    """A transcript with a request id, plus a ledger claiming bytes on that request."""
    records = (
        call("g", "Glob", {"pattern": "**/*.py"})
        + [
            {
                "type": "assistant",
                "uuid": "u-req",
                "requestId": "req_filtered",
                "message": {"role": "assistant", "model": "claude-opus-5",
                            "content": [{"type": "text", "text": "ok"}],
                            "usage": {"input_tokens": 1, "output_tokens": 1}},
            }
        ]
        + padding(8)
    )
    ledger = tmp_path / "filter.jsonl"
    ledger.write_text(json.dumps({
        "request_id": "req_filtered",
        "bytes_dropped": dropped_bytes,
        "dropped": [{"rule": "B2", "tool": "Bash", "bytes": dropped_bytes,
                     "tool_use_id": "toolu_gone"}],
    }) + "\n")
    return write_session(tmp_path, records), ledger


def test_plan_takes_the_ledger_and_moves_its_denominator(tmp_path):
    """The filter never touches the transcript, so Claude Code writes what it
    held and every share `plan` computes from disk is of a session that did not
    happen. The correction existed, was tested and was rendered, and was reachable
    only from the one command that writes nothing."""
    path, ledger = _filtered_session(tmp_path, 800)
    plain = build_plan(path)
    corrected = build_plan(path, filter_ledger=ledger)

    assert corrected.report.filtered.bytes_dropped == 800
    assert (corrected.report.wire_content_bytes
            == plain.report.message_content_bytes - 800)
    payload = to_dict(corrected)
    assert payload["wire_content_bytes"] == corrected.report.wire_content_bytes
    assert payload["message_content_bytes"] == plain.report.message_content_bytes
    assert payload["filter_ledger"]["requests"] == 1
    # Every share is against the wire figure, not the disk one.
    assert payload["bytes"]["removed_share"] == pytest.approx(
        round(corrected.removed_bytes / corrected.report.wire_content_bytes * 100, 4)
    )


def test_without_a_ledger_nothing_moves(tmp_path):
    """A session that was never filtered must read exactly as it did before."""
    path, _ = _filtered_session(tmp_path, 4_000)
    plan = build_plan(path)
    payload = to_dict(plan)
    assert plan.report.filtered is None
    assert payload["filter_ledger"] is None
    assert payload["wire_content_bytes"] == payload["message_content_bytes"]


def test_the_readout_names_the_base_it_used_and_what_it_did_not_correct(tmp_path):
    """A share that silently changed base is worse than one that is consistently
    conservative. And `S` is still measured from disk — the positional correction
    needs a join `inspect` does not do, so the readout says so rather than
    leaving an operator to assume it was applied."""
    path, ledger = _filtered_session(tmp_path, 800)
    rendered = render(build_plan(path, filter_ledger=ledger))
    assert "kept" in rendered and "off the wire" in rendered
    assert "the API saw" in rendered
    assert "S is still measured from disk" in rendered


def test_the_flag_reaches_plan_and_fork_from_the_command_line(tmp_path):
    from winnow.fork import fork_command

    path, ledger = _filtered_session(tmp_path, 800)
    code, output = plan_command(str(path), filter_ledger=ledger, as_json=True)
    assert code in (0, 2)
    assert json.loads(output)["filter_ledger"]["requests"] == 1

    code, output = fork_command(str(path), filter_ledger=ledger, as_json=True)
    assert code in (0, 2, 3)
    assert "req_filtered" not in output  # ids are not leaked into the readout


def test_an_overstated_correction_clamps_rather_than_going_negative(tmp_path):
    """`wire_content_bytes` clamps at zero, which is why defect 3 had to be fixed
    before this parameter was threaded: a ledger read that overstated by 8.6x
    would have produced a denominator of nothing and a share of nothing, silently,
    in a gate."""
    path, ledger = _filtered_session(tmp_path, 10_000_000)
    plan = build_plan(path, filter_ledger=ledger)
    assert plan.report.wire_content_bytes == 0
    payload = to_dict(plan)
    assert payload["wire_content_bytes"] == 0
    assert payload["bytes"]["removed_share"] == 0.0
    render(plan)  # must not divide by zero
