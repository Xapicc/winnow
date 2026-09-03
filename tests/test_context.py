"""Tests for `winnow context` — proposals/ContextTreemap, milestone M1.

Two kinds of test here and the split is deliberate. The synthetic fixtures in
`fixtures/sessions/context_*.jsonl` state their own right answer, so they can
assert exact token counts; the real sessions under `~/.claude/projects` cannot,
so they assert only the numbers `05-recommendation.md` names as acceptance —
the exact window, the compaction accounting, and what is refused — and skip
when the session is not on this machine.

The provenance test is the one that matters most. `02-constraints.md` §C2 says
every number carries its kind, and the success-criteria table says that is
"enforced by a test that walks the `--json` tree rather than by review". It
walks the document for any object holding a figure and fails if the figure has
no kind beside it, so a new figure added without a label fails the build rather
than being noticed in a diff.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from winnow.context import (
    KINDS,
    Node,
    compose,
    context_command,
    priced_responses,
    to_dict,
)
from winnow.legacy.session import load_messages
from winnow.report import resolve_session

FIXTURES = Path(__file__).parent / "fixtures" / "sessions"

# The four modules `winnow context` must never reach: the pruning policy, the
# team state, the proxy and the orchestrator-safe mode. 05-'s second guardrail.
FORBIDDEN_MODULES = frozenset({
    "winnow.legacy.guard", "winnow.legacy.team", "winnow.proxy",
    "winnow.orchestrator_safe",
})


def fixture(name: str) -> str:
    return str(FIXTURES / f"context_{name}.jsonl")


def composition(name: str):
    path = FIXTURES / f"context_{name}.jsonl"
    return compose(path, [record for _, record, _ in load_messages(path)])


def tokens(comp, label: str) -> int:
    return next((node.tokens for node in comp.nodes if node.label == label), 0)


@pytest.fixture
def real_claude_dir(monkeypatch):
    """Undo conftest's hermetic `CLAUDE_CONFIG_DIR` for the acceptance sessions.

    The hermetic default exists because `find_current_session` consults a
    *writable* store under `~/.claude` and a test must not pick up the live
    session's record. This command has no write path at all (§C1) and the
    sessions `05-recommendation.md` names as acceptance are real ones on this
    machine, so the tests that need them read the real directory and skip when
    it does not hold them.
    """
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


def real_session(prefix: str) -> Path:
    try:
        return resolve_session(prefix)
    except LookupError:
        pytest.skip(f"session {prefix} is not on this machine")


# ─── the six acceptance criteria ─────────────────────────────────────────────


def test_exact_window_is_read_not_computed_and_the_nodes_sum_to_it(real_claude_dir):
    """05- M1, acceptance 1: session e698739e reports exactly 219,485."""
    path = real_session("e698739e")
    comp = compose(path, [record for _, record, _ in load_messages(path)])

    assert comp.window == 219_485
    assert sum(node.tokens for node in comp.nodes) == 219_485
    assert to_dict(comp, None)["window"] == {"tokens": 219_485, "kind": "exact"}


def test_compaction_resets_the_accumulator_on_a_real_session(real_claude_dir):
    """05- M1, acceptance 2: 116,030 and not 416,774, with 444,326 dropped.

    The 3.6x is what a tool that walks from record zero and adds reports on this
    session (01- §2.6 column F). The assertion below is that the reported total
    is the window rather than the lifetime sum.
    """
    path = real_session("2551cd0c")
    records = [record for _, record, _ in load_messages(path)]
    comp = compose(path, records)

    assert comp.window == 116_030
    assert len(comp.boundaries) == 3
    assert sum(node.tokens for node in comp.nodes) == 116_030

    document = to_dict(comp, None)
    assert document["compaction"]["dropped"] == {"tokens": 444_326, "kind": "exact"}

    code, output = context_command(str(path))
    assert code == 0
    assert "116,030" in output
    assert "416,774" not in output
    assert "444,326" in output
    # The cumulative-dropped line sits above the tree, not inside it: it is not
    # part of the window and adding it to a node would be the over-report again.
    assert output.index("444,326") < output.index("unattributed")


def test_no_percent_full_without_a_stated_denominator(real_claude_dir):
    """05- M1, acceptance 3, and §C7. 72acbacd is a [1m] session: a hardcoded
    200,000 would render its 512,133 tokens as 256% full."""
    path = real_session("72acbacd")
    code, output = context_command(str(path))

    assert code == 0
    assert "512,133" in output
    assert "% full" not in output
    assert "256" not in output, "a hardcoded 200,000 denominator"
    assert to_dict(compose(path, [r for _, r, _ in load_messages(path)]),
                   None)["fullness"] is None

    _, with_denominator = context_command(str(path), window=1_000_000)
    assert "of a --window of 1,000,000" in with_denominator
    assert "51.2% full" in with_denominator


def test_no_usage_anchor_refuses_rather_than_guesses():
    """05- M1, acceptance 4: the estimated tree, no percentages, non-zero exit."""
    code, output = context_command(fixture("no_anchor"))

    assert code == 3
    assert "%" not in output
    assert "no assistant record in this session carries a `usage` block" in output
    # The tree is still printed — a session with no anchor is not a session with
    # no content, and withholding the estimate as well would help nobody.
    assert "conversation" in output
    assert "tool traffic" in output
    assert "unattributed" not in output


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores a read-only mode")
def test_exits_zero_with_a_read_only_claude_directory(tmp_path, monkeypatch):
    """§C1 and 05- M1, acceptance 5. Also: nothing under it changes at all."""
    projects = tmp_path / "claude" / "projects" / "-workspace-winnow"
    projects.mkdir(parents=True)
    shutil.copy(FIXTURES / "context_golden.jsonl",
                projects / "aaaaaaaa-1111-2222-3333-444444444444.jsonl")

    for directory in (tmp_path / "claude", tmp_path / "claude" / "projects", projects):
        directory.chmod(0o555)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))

    def snapshot() -> dict[str, tuple[int, int]]:
        return {str(p): (p.stat().st_size, p.stat().st_mtime_ns)
                for p in sorted((tmp_path / "claude").rglob("*"))}

    before = snapshot()
    try:
        code, output = context_command("aaaaaaaa")
        assert code == 0
        assert "5,000" in output
        assert snapshot() == before
    finally:
        # Restore write permission or pytest cannot remove its own tmp_path.
        for directory in (tmp_path / "claude" / "projects" / projects.name,
                          tmp_path / "claude" / "projects", tmp_path / "claude"):
            directory.chmod(0o755)


def test_the_command_reaches_no_pruning_policy():
    """05- M1, acceptance 6. In a fresh interpreter, because a sibling test that
    imported the proxy first would otherwise make this pass for the wrong
    reason."""
    program = (
        "import json, sys\n"
        "from winnow.cli import main\n"
        f"main(['context', {fixture('golden')!r}, '--json'])\n"
        f"forbidden = set({sorted(FORBIDDEN_MODULES)!r})\n"
        "print('LEAKED', json.dumps(sorted(forbidden & set(sys.modules))),"
        " file=sys.stderr)\n"
    )
    result = subprocess.run([sys.executable, "-c", program],
                            capture_output=True, text=True, check=True)
    leaked = json.loads(result.stderr.rsplit("LEAKED ", 1)[1])
    assert leaked == []


# ─── the success-criteria rows checked at M1 ─────────────────────────────────


# The only numbers in the document that are not a claim about the window, and so
# the only ones exempt from carrying a kind: counts of things in the file, and
# the estimator's own constant. Listed rather than pattern-matched, so that a
# figure added later is unlabelled-and-failing until somebody decides which it
# is. This list is the decision.
NOT_A_WINDOW_CLAIM = frozenset({
    "$.records", "$.requests", "$.requests_in_window", "$.chars_per_token",
    "$.compaction.boundaries",
})


def walk_numbers(document) -> tuple[list[tuple[str, dict]], list[str]]:
    """Every figure in the document, split into labelled and bare.

    A figure is labelled when it sits in an object beside its own `kind`; it is
    bare when it is a raw number hanging off a key. The second list is what the
    §C2 test asserts against, so a new bare number fails until it is either
    wrapped with a kind or added to `NOT_A_WINDOW_CLAIM` deliberately.
    """
    labelled: list[tuple[str, dict]] = []
    bare: list[str] = []

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            if "kind" in node:
                labelled.append((path, node))
                return  # its numbers are that kind's; do not re-count them bare
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")
        elif isinstance(node, bool):
            pass
        elif isinstance(node, (int, float)):
            bare.append(path)

    walk(document, "$")
    return labelled, bare


@pytest.mark.parametrize("name,window_argument", [
    ("golden", None),
    ("golden", 200_000),
    ("compacted", None),
    ("boundary_after_anchor", None),
    ("skill_body", None),
    ("no_anchor", None),
    ("duplicate_message_id", None),
    ("torn_trailing", None),
    ("zero_usage_anchor", None),
    ("bookkeeping_only", None),
    ("empty", None),
])
def test_every_rendered_number_carries_a_provenance_label(name, window_argument):
    """§C2, and the success-criteria row whose target is zero unlabelled numbers.

    Walked rather than reviewed, so that a figure added later without a label
    fails the build. Both directions: every labelled figure's kind is one of the
    four, and every bare number is one the exemption list names.
    """
    document = to_dict(composition(name), window_argument)
    labelled, bare = walk_numbers(document)

    for path, figure in labelled:
        assert figure["kind"] in KINDS, f"{path} carries a kind that is not one of {KINDS}"
    unexplained = sorted(set(bare) - NOT_A_WINDOW_CLAIM)
    assert not unexplained, f"numbers with no provenance: {unexplained}"


def test_the_json_tree_is_the_committed_golden():
    """The only defence against the one error the residual cannot catch.

    Misattribution conserves the total, so moving tokens between categories
    leaves the residual untouched and the readout looking exactly as correct as
    before. Regenerate this file deliberately when the classifier changes.
    """
    code, output = context_command(fixture("golden"), as_json=True)
    assert code == 0
    document = json.loads(output)
    document.pop("path")
    assert document == json.loads((FIXTURES / "context_golden.json").read_text())


def test_wall_clock_on_the_largest_session_is_under_300ms(real_claude_dir):
    """The success-criteria row: <300 ms end to end, cold, on 8 MB / 1,525
    records. Best of three fresh processes, because this container runs several
    agents at once and the criterion is about the tool rather than the load."""
    path = real_session("72acbacd")
    best = min(_timed_run(path) for _ in range(3))
    assert best < 0.300, f"best of three cold runs was {best:.3f}s"


def _timed_run(path: Path) -> float:
    start = time.perf_counter()
    subprocess.run([sys.executable, "-m", "winnow", "context", str(path)],
                   capture_output=True, check=True)
    return time.perf_counter() - start


# ─── the constraints, on fixtures that state their own answer ────────────────


def test_one_response_over_several_lines_is_counted_once():
    """§C8. Summing `usage` per JSONL line inflates the window by 1.7-2.4x."""
    path = FIXTURES / "context_duplicate_message_id.jsonl"
    records = [record for _, record, _ in load_messages(path)]
    comp = compose(path, records)

    assert comp.window == 12_000
    assert comp.requests == 2, "seven lines, two priced requests"

    naive = sum(
        (record["message"]["usage"]["input_tokens"]
         + record["message"]["usage"]["cache_creation_input_tokens"]
         + record["message"]["usage"]["cache_read_input_tokens"])
        for record in records if record.get("type") == "assistant")
    assert naive == 54_000, "the defect this dedupe exists to avoid"
    assert comp.window * 4 < naive


def test_the_accumulator_resets_at_the_compaction_boundary():
    """§C6, on a fixture whose pre-boundary result is 5,200 characters — 2,000
    estimated tokens that are not in the final window."""
    comp = composition("compacted")

    assert comp.window == 12_000
    assert comp.requests == 4 and comp.requests_in_window == 2
    assert tokens(comp, "compaction summary") == 1_000
    assert tokens(comp, "tool traffic") == 508, "the post-boundary Bash only"
    assert tokens(comp, "conversation") == 8
    assert tokens(comp, "unattributed") == 10_484
    assert sum(node.tokens for node in comp.nodes) == 12_000


def test_a_boundary_after_the_anchor_does_not_become_the_window_start():
    """§C6, the other way round. Compaction has happened and the next request
    has not come back, so the only window this file can describe is the one at
    the last priced request — which is *before* that boundary. Resetting to it
    would report a window of 20,000 tokens holding almost nothing.
    """
    comp = composition("boundary_after_anchor")

    assert comp.window == 20_000
    assert len(comp.boundaries) == 1
    assert tokens(comp, "tool traffic") == 1_018, "the pre-boundary Read result"
    assert tokens(comp, "compaction summary") == 0, "it is not in this window"
    assert any("follows the anchoring request" in note for note in comp.notes)
    assert sum(node.tokens for node in comp.nodes) == 20_000


def test_a_tool_return_outside_a_tool_result_envelope_is_tool_traffic():
    """A `user` text block carrying `sourceToolUseID` is a tool's return, not a
    user turn. 06-spike-findings §5 measures what keying on the record type
    alone costs: 53.0% of session c3566197's window filed as `conversation`.
    """
    comp = composition("skill_body")

    assert tokens(comp, "tool traffic") == 2_010, "2,000 of Skill's body + the call"
    assert tokens(comp, "conversation") == 5, "the user's four-word turn, only"
    assert any("sourceToolUseID" in note for note in comp.notes)


def test_bookkeeping_records_are_worth_zero_tokens():
    """§C4. `queue-operation` carries a copy of the user's prompt, so it looks
    like context; 1.96 MB of it on this machine, none of it on the wire."""
    comp = composition("bookkeeping_only")

    assert comp.window is None
    assert comp.nodes == []

    code, output = context_command(fixture("bookkeeping_only"))
    assert code == 3
    assert "pull request" not in output, "a bookkeeping payload reached the tree"


def test_a_synthetic_response_does_not_anchor_the_readout():
    """A `<synthetic>` record — an interrupt, or an API error the CLI wrote in
    the model's place — carries a usage object of all zeros. Anchoring on it
    would report a window of nothing."""
    comp = composition("zero_usage_anchor")

    assert comp.window == 8_000
    assert comp.requests == 1
    assert comp.model == "claude-opus-5"


def test_a_torn_trailing_line_is_read_around_and_named():
    """§C8. The CLI appends while this reads; the last line can be half-written."""
    comp = composition("torn_trailing")

    assert comp.window == 6_000
    assert comp.records == 2, "the half-written line is not yet a record"
    assert any("did not parse" in note for note in comp.notes)


def test_an_empty_session_refuses_without_raising():
    code, output = context_command(fixture("empty"))

    assert code == 3
    assert "0 records" in output


def test_an_image_is_priced_by_its_header_and_never_by_its_base64():
    """§C5. `len(base64)/4` over-reports a real image 14x; here the fixture's
    base64 is short and the image is 1518x784, so the two disagree by 100x and
    only the header-derived figure can produce the number asserted."""
    comp = composition("golden")

    # 1518 x 784 / 750 = 1,586.8, plus 29 estimated tokens of prose.
    assert tokens(comp, "conversation") == 1_616


def test_thinking_blocks_are_worth_zero_and_their_signatures_nothing():
    """§C4 and 01- §1.3: 1.4-2.7 KB of opaque blob per block, zero tokens.

    The golden fixture carries two thinking blocks with 64-character signatures.
    Nothing in the tree may move when they are removed.
    """
    path = FIXTURES / "context_golden.jsonl"
    records = [record for _, record, _ in load_messages(path)]
    with_thinking = compose(path, records)

    for record in records:
        message = record.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), list):
            message["content"] = [block for block in message["content"]
                                  if block.get("type") != "thinking"]
    without = compose(path, records)

    assert [(n.label, n.tokens) for n in with_thinking.nodes] == \
           [(n.label, n.tokens) for n in without.nodes]


def test_the_residual_absorbs_the_rounding_so_the_rows_always_sum():
    """§C3. The total is exact and the parts are apportioned into it, so the
    printed rows sum to the window whichever way each estimate rounds."""
    for name in ("golden", "compacted", "boundary_after_anchor", "skill_body",
                 "duplicate_message_id", "torn_trailing", "zero_usage_anchor"):
        comp = composition(name)
        assert sum(node.tokens for node in comp.nodes) == comp.window, name
        residual = [node for node in comp.nodes if node.kind == "residual"]
        assert len(residual) == 1, f"{name}: exactly one residual node (§C2)"
        assert residual[0].label == "unattributed"


def test_an_unresolvable_session_is_a_usage_error_not_a_traceback():
    code, output = context_command("no-such-session-anywhere")

    assert code == 1
    assert output.startswith("winnow: ")


def test_nodes_carry_an_empty_children_list_for_the_drill_down_to_fill():
    """M1 has no second level. `--json` is the interface M2 builds on, so the
    shape a consumer parses must not change when the drill-down lands."""
    document = json.loads(context_command(fixture("golden"), as_json=True)[1])

    assert all(node["children"] == [] for node in document["nodes"])
    assert Node(label="x", tokens=0, kind="estimated").children == []


def test_every_group_can_render_its_own_help():
    """argparse %-expands a help string, so a literal percent in one raises
    TypeError at `--help` time and nowhere else. `--window`'s help talks about
    "% full", which is exactly the trap."""
    from winnow.cli import _SUBPARSERS, build_parser

    for group in _SUBPARSERS:
        parser = build_parser(group)
        action = next(a for a in parser._subparsers._group_actions)
        assert action.choices[group].format_help()


def test_priced_responses_ignore_records_with_no_usage():
    path = FIXTURES / "context_no_anchor.jsonl"
    assert priced_responses([r for _, r, _ in load_messages(path)]) == []
