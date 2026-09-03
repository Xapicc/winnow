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
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from winnow.context import (
    KINDS,
    Node,
    attachment_chars,
    attachment_keys,
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


def composition(name: str, **options):
    path = FIXTURES / f"context_{name}.jsonl"
    return compose(path, [record for _, record, _ in load_messages(path)], **options)


def tokens(comp, label: str) -> int:
    return next((node.tokens for node in comp.nodes if node.label == label), 0)


def child(node, prefix: str):
    """The one child whose label starts with `prefix`, or an AssertionError."""
    matches = [c for c in node.children if c.label.startswith(prefix)]
    assert len(matches) == 1, \
        f"{prefix!r} matched {[c.label for c in matches]} in {node.label!r}"
    return matches[0]


def descend(comp, *labels):
    """Walk the tree by label prefix, from a top-level node down."""
    node = next(n for n in comp.nodes if n.label == labels[0])
    for label in labels[1:]:
        node = child(node, label)
    return node


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
    # The claim being refused is "256% full", not the digits: at --depth 3 this
    # readout prints a few hundred token counts and one of them will eventually
    # contain 256.
    assert not re.search(r"\b256(\.\d+)?%", output), "a hardcoded 200,000 denominator"
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
    # M2 reads one thing M1 did not: a sub-agent's own transcript, from the
    # sidecar directory beside the session (§C11). That is new I/O under
    # ~/.claude and it is inside this test's guarantee, so it is copied in too.
    delegating = "bbbbbbbb-1111-2222-3333-444444444444"
    shutil.copy(FIXTURES / "context_agent.jsonl", projects / f"{delegating}.jsonl")
    shutil.copytree(FIXTURES / "context_agent" / "subagents",
                    projects / delegating / "subagents")

    read_only = [tmp_path / "claude", tmp_path / "claude" / "projects", projects,
                 projects / delegating, projects / delegating / "subagents"]
    for directory in read_only:
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

        code, output = context_command("bbbbbbbb", depth=3, by_path=True)
        assert code == 0
        assert "own window 144,000, not added" in output

        assert snapshot() == before
    finally:
        # Restore write permission or pytest cannot remove its own tmp_path.
        for directory in reversed(read_only):
            directory.chmod(0o755)


def test_the_command_reaches_no_pruning_policy():
    """05- M1, acceptance 6. In a fresh interpreter, because a sibling test that
    imported the proxy first would otherwise make this pass for the wrong
    reason."""
    program = (
        "import json, sys\n"
        "from winnow.cli import main\n"
        # Every M2 flag, because a new code path is a new chance to import
        # something. `rules.bash_head` is the one module M2 added to the reach.
        f"main(['context', {fixture('golden')!r}, '--json', '--depth', '4'])\n"
        f"main(['context', {fixture('agent')!r}, '--by-path'])\n"
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
    # M2's three. `depth` is how many levels were drawn, and the other two are
    # counts of distinct paths — none of them says anything about the window,
    # and the two figures that do (`pooled_by_path.tokens` and `.repeated`)
    # carry their kind.
    "$.depth", "$.pooled_by_path.paths", "$.pooled_by_path.repeated_paths",
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
    document = to_dict(composition(name, depth=3), window_argument)
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

    Taken with `--audit` because M3's two derived blocks are where a silent move
    is now most likely: the prefix and retained reasoning are each an exact
    number minus an estimate, and a change to what the classifier counts as
    visible moves tokens between them and the tree without moving the total.
    The audit document pins both derivations and the unapplied constant.
    """
    code, output = context_command(fixture("golden"), as_json=True, audit=True)
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
    # `--depth 3` explicitly, which is what the success-criteria row measures,
    # and which builds and rounds every artefact node rather than only the top.
    subprocess.run([sys.executable, "-m", "winnow", "context", str(path), "--depth", "3"],
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
    estimated tokens that are not in the final window.

    The prefix is subtracted from the first request *in this window*, which is
    the one after the boundary, not the one at the top of the file — so a
    compacted session gets a prefix priced against a request whose context
    already contains the summary. Anchoring it on the file's first request
    instead would price the pre-compaction prefix and then subtract it from a
    window that no longer holds it.
    """
    comp = composition("compacted")

    assert comp.window == 12_000
    assert comp.requests == 4 and comp.requests_in_window == 2
    assert tokens(comp, "compaction summary") == 1_000
    assert tokens(comp, "tool traffic") == 508, "the post-boundary Bash only"
    assert tokens(comp, "conversation") == 8
    assert comp.floor.first_context == 9_000, "the first request after the boundary"
    assert tokens(comp, "prefix") == 8_000, "9,000 less the 1,000 summary before it"
    assert tokens(comp, "unattributed") == 2_476
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


def test_depth_one_is_still_exactly_m1s_readout():
    """`--depth` caps rather than reshapes: at 1 the tree is M1's, unchanged.

    Worth pinning, because the milestone that adds levels is also the milestone
    most likely to move a token between two top-level categories by accident.
    """
    document = json.loads(
        context_command(fixture("golden"), as_json=True, depth=1)[1])

    assert all(node["children"] == [] for node in document["nodes"])
    assert Node(label="x", tokens=0, kind="estimated").children == []

    deep = json.loads(context_command(fixture("golden"), as_json=True, depth=3)[1])
    assert [(n["label"], n["tokens"]) for n in deep["nodes"]] == \
           [(n["label"], n["tokens"]) for n in document["nodes"]]
    assert any(node["children"] for node in deep["nodes"]), "the drill-down"


# ─── M2: the drill-down ──────────────────────────────────────────────────────


def test_read_and_edit_pooled_by_path_reproduce_the_thirty_seven(real_claude_dir):
    """05- M2, acceptance 1, and the criterion 06- §4 called unmeetable.

    It is meetable, and the spike's diagnosis was half right. The shape does
    halve the number — this test asserts both halves below — but the missing 8
    nodes were `Write`, which 06- left out of the tool set. Pooled across the
    three path-bearing tools this run measures 37 distinct paths, 81,368
    estimated tokens and 33.5% of them from paths touched more than once,
    against 01- §5's 37 paths / 211,557 characters / 34%. 211,557 / 2.6 =
    81,368 exactly, so the character count agrees to the character too.
    """
    path = real_session("f6ea2591")
    records = [record for _, record, _ in load_messages(path)]
    comp = compose(path, records, depth=3, by_path=True)

    assert comp.pooled["paths"] == 37
    assert abs(comp.pooled["repeated_percent"] - 34) <= 2, \
        f"within 2 points of 34%, got {comp.pooled['repeated_percent']:.1f}%"

    # Every one of the 37 is a node in the rendered tree, not just a statistic:
    # no roll-up, so `--json` and the terminal carry the same 37.
    traffic = next(n for n in comp.nodes if n.label == "tool traffic")
    drawn = [n for n in traffic.children if not n.label.startswith("$ ")
             and n.label != "tool_use inputs"]
    assert len(drawn) == 37

    repeated = [n for n in drawn if "×" in n.label.split("  ")[-1]]
    assert len(repeated) == comp.pooled["repeated_paths"] == 12
    for node in repeated:
        assert re.search(r"×\d+ \(", node.label), node.label


def test_the_default_shape_halves_the_repeated_share_and_says_so(real_claude_dir):
    """06- §4's measurement, kept in the suite rather than in a document.

    Tool-then-path is the default because 05- §M2 mandates it and acceptance 2
    pins it, and it is worse at the question 01- §5 calls the most actionable
    there is. Both numbers are asserted so that a later change to either keying
    cannot quietly move one without the other.
    """
    path = real_session("f6ea2591")
    records = [record for _, record, _ in load_messages(path)]
    comp = compose(path, records, depth=3)

    traffic = next(n for n in comp.nodes if n.label == "tool traffic")
    read_and_edit = [child(traffic, "Read results"), child(traffic, "Edit results")]
    nodes = [n for parent in read_and_edit for n in parent.children]
    assert len(nodes) == 32, "06- §4's 32 nodes, keyed by (tool, path)"

    total = sum(n.tokens for n in nodes)
    repeated = sum(n.tokens for n in nodes if "×" in n.label)
    assert abs(100 * repeated / total - 16.8) < 0.5, "06- §4's 16.8%"

    # And the same session's pooled figure is computed either way, so the
    # readout can state the number the shape it is drawn in cannot reach.
    assert comp.pooled["paths"] == 37


def test_the_three_result_bearing_tools_and_the_sibling_inputs(real_claude_dir):
    """05- M2, acceptance 2. The one criterion 06- §4 says the spike passed.

    `tool_use` inputs are a sibling of the result nodes rather than folded into
    them: an `Edit` input carries the new file content and is routinely larger
    than the result it produces, so folding the two hides which is the cost.
    """
    path = real_session("e698739e")
    records = [record for _, record, _ in load_messages(path)]
    traffic = next(n for n in compose(path, records, depth=3).nodes
                   if n.label == "tool traffic")

    results = [n for n in traffic.children if n.label.endswith(" results")]
    assert [n.label for n in results] == \
           ["Bash results", "Read results", "Edit results"]
    for node, expected in zip(results, (42_609, 7_650, 646)):
        assert abs(node.tokens - expected) <= 0.02 * expected, node.label

    inputs = child(traffic, "tool_use inputs")
    assert abs(inputs.tokens - 18_087) <= 0.02 * 18_087
    assert inputs in traffic.children, "a sibling, not a child of a result node"


def test_a_sub_agents_own_window_is_beside_its_return_and_never_in_it():
    """05- M2, acceptance 3, and §C11.

    The fixture states its own answer: the return is 4,000 characters — 1,538
    estimated tokens — and the sub-agent's own transcript anchors at 144,000.
    Adding them produces a number that is not the size of any window that ever
    existed, so the test asserts the parent's total never moves toward it.
    """
    comp = composition("agent", depth=3)
    returns = descend(comp, "tool traffic", "Agent returns")

    assert returns.tokens == 1_538, "the return, and only the return"
    assert len(returns.children) == 1
    leaf = returns.children[0]
    assert leaf.tokens == 1_538
    assert "Explore: map the orchestrator" in leaf.label
    assert "own window 144,000, not added" in leaf.label
    assert tokens(comp, "tool traffic") == 1_566, "the return plus the 28-token call"
    assert max(node.tokens for node, _ in _walk(comp.nodes)) < 144_000, \
        "no node anywhere grew toward the sub-agent's own budget"
    assert any("never added to this one" in note for note in comp.notes)


def test_a_sub_agent_with_no_sidecar_says_so_rather_than_guessing():
    """The sidecar can be absent — a transcript copied without its directory.
    The return is still the node; the missing half is named, not invented."""
    comp = composition("agent_no_sidecar", depth=3)
    leaf = descend(comp, "tool traffic", "Agent returns").children[0]

    assert leaf.tokens == 1_538
    assert "no sidecar found" in leaf.label
    assert any("unknown rather than zero" in note for note in comp.notes)


def test_a_persisted_output_node_is_sized_at_the_preview_and_says_so():
    """05- M2, acceptance 4, and §C9.

    The fixture's wrapper is 2,300 characters holding a preview of a 45.9 KB
    sidecar. 2,300 / 2.6 = 885. Sizing the sidecar instead would report ~18,000.
    """
    comp = composition("persisted_output", depth=3)
    node = descend(comp, "tool traffic", "Bash results", "$ gh")

    assert node.tokens == 885, "the preview, not the 45.9 KB behind it"
    assert "45.9 KB of sidecar behind it, not counted" in node.note
    assert any("not at the tool-results/ sidecar" in note for note in comp.notes)

    _, output = context_command(fixture("persisted_output"), depth=3)
    assert "45.9 KB" in output
    assert "18," not in output, "the sidecar sized as if it were on the wire"


def test_bash_keeps_its_command_head_when_the_tree_is_re_keyed_by_path():
    """`--by-path` re-keys by artefact, and Bash output has no artefact.

    05- §M2 rejects H3 as a root partly because its "other" bin is routinely the
    largest node — on 01- §2.6 the top tool by result size is Bash. So a result
    with no path keeps its command head as its own key and is never binned.
    """
    comp = composition("persisted_output", depth=3, by_path=True)
    traffic = next(n for n in comp.nodes if n.label == "tool traffic")

    assert [n.label for n in traffic.children if n.label.startswith("$ ")] == ["$ gh"]
    assert not any("other" in n.label for n in traffic.children)
    assert child(traffic, "$ gh").children[0].label == "Bash"


def test_pooling_a_path_across_tools_is_one_node_with_its_counts():
    """The operator's question — *which files did the reads touch* — and the
    part of it that is new: a path touched by two tools is one row.

    The fixture reads `~/src/app.ts` twice and edits it once, so the default
    tree draws it as `Read results → app.ts ×2` and `Edit results → app.ts` in
    two subtrees, and `--by-path` draws one node marked `×3 (Read ×2, Edit)`.
    """
    default = composition("by_path", depth=3)
    assert descend(default, "tool traffic", "Read results", "~/src/app.ts").tokens == 800
    assert descend(default, "tool traffic", "Edit results", "~/src/app.ts").tokens == 40

    pooled = composition("by_path", depth=3, by_path=True)
    node = descend(pooled, "tool traffic", "~/src/app.ts")
    assert node.tokens == 840, "one node, both tools"
    assert node.label == "~/src/app.ts  ×3 (Read ×2, Edit)"
    assert [(c.label, c.tokens) for c in node.children] == \
           [("Read  ×2", 800), ("Edit", 40)]

    # And the pooled statistic is the same number whichever way it is drawn.
    for comp in (default, pooled):
        assert comp.pooled["paths"] == 2
        assert comp.pooled["repeated_paths"] == 1
        assert round(comp.pooled["repeated_percent"], 1) == 68.9


def test_an_image_is_priced_by_its_header_in_every_format_or_labelled_zero():
    """05- non-goal 12 and §C5: JPEG SOF, PNG IHDR, and zero for neither.

    `len(base64)/4` over-reports a real image 14x (01- §2.5). The fixture holds
    one PNG at 1518x784, one JPEG at 600x400, and one blob whose header does not
    parse — which is sized zero and labelled, never guessed.
    """
    comp = composition("image", depth=3)
    images = descend(comp, "conversation", "images")

    # 1518*784/750 = 1,586.78, 600*400/750 = 320.00, the third one 0 — so 1,907
    # apportioned inside a 1,912 parent that also holds 13 characters of prose.
    # By len(base64)/4 the three would be 31, 27 and 254 — which puts the blob
    # that is not an image at all above the 1518x784 PNG. On a real image the
    # error runs the other way and is 14x (01- §2.5); either way it is not a
    # smaller number, it is a different ordering of the same three blocks.
    assert images.tokens == 1_907
    assert tokens(comp, "conversation") == 1_912
    assert any("sized ZERO and labelled" in note for note in comp.notes)

    _, output = context_command(fixture("image"), depth=3)
    assert "never at len(base64)/4" in output


def test_the_children_of_every_node_sum_to_it_exactly():
    """§C3, one level down. The parts are apportioned into the total at the top
    and at every level below it, so a drill-down can never show a row whose own
    children disagree with it."""
    for name in ("golden", "compacted", "skill_body", "agent", "image",
                 "persisted_output", "by_path"):
        for by_path in (False, True):
            comp = composition(name, depth=4, by_path=by_path)
            for node, _ in _walk(comp.nodes):
                if node.children:
                    assert sum(c.tokens for c in node.children) == node.tokens, \
                        f"{name}: {node.label}"


def test_every_level_is_sorted_biggest_first():
    """05- M2: "sorted biggest-first at every level"."""
    comp = composition("golden", depth=4)
    for node, _ in _walk(comp.nodes):
        sizes = [c.tokens for c in node.children]
        assert sizes == sorted(sizes, reverse=True), node.label


def test_the_tree_and_the_json_carry_the_same_nodes():
    """The scope's one rendering rule: rendered in the tree and in `--json`
    identically. No roll-up in one and not the other, no "17 more, each
    smaller" bin that a consumer of the JSON cannot see."""
    code, payload = context_command(fixture("golden"), as_json=True, depth=3)
    assert code == 0
    document = json.loads(payload)

    def labels(nodes):
        return [(n["label"], n["tokens"], labels(n["children"])) for n in nodes]

    comp = composition("golden", depth=3)

    def from_tree(nodes):
        return [(n.label, n.tokens, from_tree(n.children)) for n in nodes]

    assert labels(document["nodes"]) == from_tree(comp.nodes)

    _, rendered = context_command(fixture("golden"), depth=3)
    for node, _ in _walk(comp.nodes):
        head = node.label.split("  ")[0][:24]
        assert head[-12:] in rendered, node.label


def _walk(nodes, level=1):
    for node in nodes:
        yield node, level
        yield from _walk(node.children, level + 1)


def test_standing_configuration_names_the_memory_file_it_loaded():
    """05- M2: `standing configuration` → attachment class → memory-file path.

    "What is my standing cost before I type anything" is only actionable if the
    answer names the file, and `nested_memory` carries one.
    """
    node = descend(composition("golden", depth=3),
                   "standing configuration", "nested_memory")

    assert [c.label for c in node.children] == ["~/.claude/CLAUDE.md"]
    assert node.children[0].tokens == node.tokens


def test_two_mcp_servers_split_one_attachment_by_their_own_blocks():
    """05- M2's other named leaf. `mcp_instructions_delta` carries one prose
    block per server, so a server takes its own block's share rather than an
    equal one — and the shares still sum to the attachment they came from."""
    attachment = {
        "type": "mcp_instructions_delta",
        "addedNames": ["alpha", "beta"],
        "addedBlocks": ["## alpha" + "a" * 90, "## beta" + "b" * 10],
        "removedNames": [],
    }
    keys = attachment_keys(attachment)

    assert [key[-1] for key, _ in keys] == ["alpha", "beta"]
    assert sum(chars for _, chars in keys) == attachment_chars(attachment)
    assert keys[0][1] > 4 * keys[1][1], "by block length, not equally"


def test_an_mcp_delta_that_names_servers_without_blocks_stays_one_node():
    """The split needs both halves to be there and to line up. Where they do
    not, the attachment is one node — a wrong split is worse than no split."""
    for attachment in (
        {"type": "mcp_instructions_delta", "addedNames": ["x"], "addedBlocks": []},
        {"type": "mcp_instructions_delta", "addedNames": [], "addedBlocks": ["b"]},
        {"type": "mcp_instructions_delta", "addedNames": ["x", "y"],
         "addedBlocks": ["only one"]},
    ):
        keys = attachment_keys(attachment)
        assert [key for key, _ in keys] == \
               [("standing configuration", "mcp_instructions_delta")]
        assert keys[0][1] == attachment_chars(attachment)


def test_a_depth_below_one_is_a_usage_error():
    code, output = context_command(fixture("golden"), depth=0)

    assert code == 1
    assert output.startswith("winnow: ")


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
