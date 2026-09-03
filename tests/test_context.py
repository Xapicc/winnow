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
    BAR_COLUMNS,
    BAR_GLYPH,
    CHARS_PER_TOKEN,
    COLOR_CHOICES,
    FACT_NOTE,
    FACT_RULE,
    FACT_WARN,
    FIXED_COLUMNS,
    KINDS,
    LABEL_COLUMNS,
    LEDGER_GLYPH,
    NO_ANCHOR,
    NO_CAUSE,
    OFF_SCALE,
    OVERHANG_OPEN,
    PALETTE_16,
    PALETTE_256,
    SHED_EVENTS_SHOWN,
    SHED_HEADING,
    SHED_ROW,
    THIN_REQUESTS,
    WIDEST_BAR,
    WIDEST_LABEL,
    WINDOW_RULE,
    ZERO_RULE,
    Node,
    Shed,
    Style,
    anchored_chain,
    attachment_chars,
    attachment_keys,
    audit_rows,
    compose,
    context_command,
    explain,
    indent,
    key_line,
    layout,
    ledger,
    on_anchored_chain,
    own_faults,
    palette,
    priced_responses,
    render,
    render_audit,
    resolve_style,
    shed_facts,
    shed_tokens,
    to_dict,
    too_thin,
    track,
    track_rooms,
    wants_colour,
)
from winnow.legacy.session import load_messages
from winnow.report import inspect_command, resolve_session

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
    assert "of the 1,000,000 stated by --window" in with_denominator
    assert "51.2%" in with_denominator


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
    # M3's, all inside `--audit`. The reconciliation rows carry their kind, so
    # only the `share` beside each is bare, and a share of an exactly-known
    # total is arithmetic on a labelled figure rather than a claim of its own.
    # The rest are counts — of responses, of thinking blocks — and the two
    # constants: the one the estimator ships and the one it solved for and
    # deliberately did not apply.
    "$.audit.chars_per_token",
    "$.audit.retained_reasoning.responses",
    "$.audit.retained_reasoning.thinking_blocks",
    "$.audit.retained_reasoning.control_responses",
    "$.audit.solved_constant.chars_per_token",
} | {f"$.audit.reconciliation[{index}].share" for index in range(12)}
  # Where a shedding event was measured, not how big it was: a request's
  # position among the priced ones and the record it sits on. The three figures
  # that are claims about the window — what it was before, what it was after,
  # and the difference — carry their kind.
  | {f"$.shedding.events[{index}].{key}" for index in range(8)
     for key in ("at_record", "at_request", "of_requests")})


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


@pytest.mark.parametrize("audit", [False, True], ids=["tree", "audit"])
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
    ("over_explained", None),
    ("prefix_underwater", None),
    ("shedding", None),
])
def test_every_rendered_number_carries_a_provenance_label(name, window_argument,
                                                          audit):
    """§C2, and the success-criteria row whose target is zero unlabelled numbers.

    Walked rather than reviewed, so that a figure added later without a label
    fails the build. Both directions: every labelled figure's kind is one of the
    four, and every bare number is one the exemption list names.

    Run over the audit document too, because that is where M3 put most of its
    new figures and an unlabelled one there is the same failure as an unlabelled
    one in the tree.
    """
    document = to_dict(composition(name, depth=3), window_argument, audit)
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


# ─── M3: the floor, priced, and the audit ────────────────────────────────────


def test_the_worked_example_in_the_constraints_file_reproduces(real_claude_dir):
    """05- M3, and the one session `02-constraints.md` works end to end.

    That table was produced by `scratch/thinking_price.py` and `compose_one.py`
    over a different parse, a different classifier and a different exclusion
    list. Reproducing all four numbers here is the strongest evidence available
    that the two derived blocks are a property of the session rather than of
    either implementation.
    """
    path = real_session("e698739e")
    comp = compose(path, [record for _, record, _ in load_messages(path)])

    assert comp.window == 219_485
    assert tokens(comp, "prefix") == 93_900
    assert tokens(comp, "retained reasoning") == 46_557
    assert tokens(comp, "unattributed") == 891
    derived = sum(n.tokens for n in comp.nodes if n.kind == "derived")
    assert derived == 140_457, "01- §2.6 puts this session's invisible share at 64%"
    assert round(100 * derived / comp.window, 1) == 64.0


def test_the_prefix_is_the_first_request_less_what_the_transcript_holds():
    """The subtraction, on a fixture that states its own answer: the first
    request is priced at 12,000 and the only thing before it is a 16-character
    prompt, which the tool's own classifier estimates at 6 tokens."""
    comp = composition("over_explained")

    assert comp.floor.first_context == 12_000
    assert round(comp.floor.visible_before_first) == 6
    assert tokens(comp, "prefix") == 11_994
    node = next(n for n in comp.nodes if n.label == "prefix")
    assert node.kind == "derived", "an exact number minus an estimate (§C2)"


def test_retained_reasoning_excludes_the_anchoring_response():
    """`output_tokens − est(text + tool_use)`, over responses still in the window.

    The fixture's first response emitted 500 tokens and wrote 306 characters of
    them down, so 500 − 307/2.6 = 382 is what it kept. The anchoring response
    emitted another 10 and they are *not* counted: its output was not in the
    window it was priced for, which is the same reason the tree stops at it.
    """
    comp = composition("over_explained")

    assert tokens(comp, "retained reasoning") == 382
    assert comp.floor.thinking_blocks == 1
    assert len(comp.floor.output) == 1, "the anchor's own output is excluded"
    assert comp.floor.output == [(500, 307.0)]


def test_the_per_response_dataset_is_built_even_though_nothing_renders_it(
        real_claude_dir):
    """05- M3: pricing reasoning per response *is* the whole H2 dataset.

    M4 would render it as `--by-turn` and this milestone deliberately does not,
    but the data has to be there and shaped right or M4 is a second walk. One
    `(output_tokens, visible chars)` pair per priced response in the window,
    minus the anchoring one.
    """
    path = real_session("e698739e")
    comp = compose(path, [record for _, record, _ in load_messages(path)])

    assert len(comp.floor.output) == 65, "66 requests, less the anchoring one"
    assert all(out > 0 and chars >= 0 for out, chars in comp.floor.output)


def test_the_residual_is_allowed_to_be_negative_and_renders_with_its_sign():
    """The spike found two of its three worked sessions over-explained, and
    `03-option-a`'s mock readout does not contemplate one. 67 of this run's 163
    sweep sessions are negative, so this is the normal case, not the edge."""
    comp = composition("over_explained")
    readout = render(comp, None)

    assert tokens(comp, "unattributed") == -7_500
    assert sum(node.tokens for node in comp.nodes) == comp.window
    residual_row = next(line for line in readout.splitlines()
                        if "unattributed" in line)
    assert "-7,500" in residual_row and "-50.0%" in residual_row
    left, _, right = residual_row[2:2 + BAR_COLUMNS].partition(ZERO_RULE)
    assert left.strip() and not right.strip(), \
        "the deficit is drawn on the deficit side of the zero line"
    assert any("the residual is negative" in line for line in readout.splitlines())


def test_the_audit_prints_the_solved_constant_and_that_it_was_not_applied():
    """05- M3, acceptance 2 — and §C10, which is the reason it is worded so hard."""
    code, output = context_command(fixture("over_explained"), audit=True)

    assert code == 0
    assert "chars-per-token constant that would zero this session's residual" \
        in output
    assert "NOT APPLIED" in output
    assert "a residual that cannot be non-zero is not evidence" in output.lower()


def test_the_solved_constant_zeroes_the_residual_and_is_not_the_one_shipped():
    """The bisection has to actually solve, or the diagnostic is decoration."""
    comp = composition("over_explained")
    solved = comp.audit.solve()

    assert solved is not None
    assert abs(comp.audit.residual_at(solved)) < 1.0
    assert abs(comp.audit.residual_at(CHARS_PER_TOKEN)) > 1_000, \
        "this fixture over-explains badly at the shipped constant"


def test_the_audit_changes_no_number_in_the_tree():
    """§C10 as an assertion rather than a promise: the solved constant is a
    diagnostic, so asking for it must not move a single row."""
    plain = context_command(fixture("over_explained"))[1]
    audited = context_command(fixture("over_explained"), audit=True)[1]

    assert audited.startswith(plain)
    assert CHARS_PER_TOKEN == 2.6, "still the shipped constant after a solve"


def test_the_audit_reconciliation_sums_to_the_exact_window():
    """Every row after the first is subtracted from it and the last is what is
    left, so the column has to add to zero against the window."""
    for name in ("golden", "over_explained", "compacted", "shedding"):
        comp = composition(name)
        rows = audit_rows(comp)

        assert rows[0][0].startswith("window") and rows[0][1] == comp.window
        assert rows[-1][0].startswith("= unattributed")
        assert sum(tokens for _, tokens, _ in rows[:-1]) == rows[-1][1]


def test_the_audit_json_says_the_constant_was_not_applied_in_a_field():
    """A sweep reads the document rather than the prose, and a reader that only
    saw a number would be entitled to use it."""
    document = to_dict(composition("over_explained"), None, audit=True)

    assert document["audit"]["solved_constant"]["applied"] is False
    assert document["audit"]["solved_constant"]["chars_per_token"] != CHARS_PER_TOKEN
    assert document["audit"]["prefix"]["prefix"] == {"tokens": 11_994,
                                                     "kind": "derived"}


def test_explain_prefix_is_three_numbers_and_a_subtraction():
    """05- M3, acceptance 3. Three numbers, not a paragraph."""
    code, output = context_command(fixture("over_explained"),
                                   explain_node="prefix")

    assert code == 0
    body = [line for line in output.splitlines() if line.strip()]
    assert body[0].startswith("prefix — derived, 11,994 tokens")
    assert len(body) == 4, "a header and exactly three lines of arithmetic"
    assert "12,000" in body[1] and "exact" in body[1]
    assert body[2].startswith("−") and " 6 " in body[2]
    assert body[3].startswith("=") and "11,994" in body[3]


def test_explain_an_estimated_node_gives_its_characters_and_the_constant():
    code, output = context_command(fixture("over_explained"),
                                   explain_node="tool traffic")

    assert code == 0
    assert "26,047" in output, "the characters behind the estimate"
    assert "2.6" in output and "10,018" in output


def test_explain_refuses_an_unknown_or_ambiguous_node():
    code, output = context_command(fixture("golden"), explain_node="nonsense")

    assert code == 1
    assert output.startswith("winnow: no node matching 'nonsense'")


def test_a_prefix_that_comes_out_negative_is_not_claimed():
    """§C7 — measure the prefix per session, or do not claim one.

    A subtraction at or below zero is a statement about the estimate, not about
    the prefix. The node is not drawn, the tokens stay in the residual, and the
    readout says which of those two things happened.
    """
    comp = composition("prefix_underwater")

    assert comp.floor.prefix < 0
    assert not comp.floor.claims_prefix
    assert tokens(comp, "prefix") == 0, "no prefix node at all"
    assert any("no prefix node" in note for note in comp.notes)
    assert sum(node.tokens for node in comp.nodes) == comp.window


def test_the_audit_model_reproduces_the_residual_the_tree_drew(real_claude_dir):
    """The solve is only meaningful if it sweeps the thing on the screen.

    `Audit.parts_at` re-prices the window at an arbitrary constant, which means
    it is a second model of the same arithmetic and could drift from `compose`
    silently — and a constant solved against a drifted model would be a
    diagnostic for a readout nobody is looking at. At the shipped constant the
    two must agree to within rounding, which is what this asserts.
    """
    for prefix in ("e698739e", "72acbacd", "2551cd0c"):
        path = real_session(prefix)
        comp = compose(path, [r for _, r, _ in load_messages(path)], depth=1)
        drawn = next(n.tokens for n in comp.nodes if n.kind == "residual")

        assert abs(drawn - comp.audit.residual_at(CHARS_PER_TOKEN)) < 5, \
            f"{prefix}: the audit models a different tree than the one drawn"


def test_the_derived_prefix_measures_what_prefix_facts_measures(tmp_path):
    """`filter.py:728 prefix_facts` is the only cross-check on the derived prefix.

    `04-comparison.md` scores keeping the command in this repository partly on
    this: `prefix_facts` sizes the system prompt and the tool definitions
    exactly, from a live Messages API request body. It cannot be pointed at a
    transcript — the two regions it reads are the two a transcript never holds,
    which is the whole reason the prefix has to be derived at all — so it cannot
    be run against a real session here and no assertion pretending otherwise
    would mean anything.

    What it *can* check is that both instruments measure the same quantity in
    the same units. This builds a request body, prices it the way the API would,
    writes the transcript that request would leave behind, and asserts the
    subtraction recovers `prefix_facts`'s two regions to the token. If the
    classifier ever starts counting something into `visible` that belongs to the
    prefix, or the reverse, this fails and the residual does not.
    """
    from winnow.context import estimate
    from winnow.filter import prefix_facts

    body = {
        "model": "claude-opus-5",
        "system": [{"type": "text", "text": "S" * 40_000}],
        "tools": [{"name": "Read", "description": "D" * 20_000, "input_schema": {}}],
        "messages": [{"role": "user", "content": "hello"}],
    }
    facts = prefix_facts(body)
    prefix_tokens = estimate(facts["system_bytes"] + facts["tools_bytes"])
    opening = body["messages"][0]["content"]

    path = tmp_path / "cccccccc-1111-2222-3333-444444444444.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in [
        {"type": "user", "message": {"role": "user", "content": opening}},
        {"type": "assistant", "message": {
            "id": "msg_1", "model": "claude-opus-5", "role": "assistant",
            "usage": {"input_tokens": round(prefix_tokens + estimate(len(opening))),
                      "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0, "output_tokens": 5},
            "content": [{"type": "text", "text": "hi"}]}},
        {"type": "user", "message": {"role": "user", "content": "again"}},
        {"type": "assistant", "message": {
            "id": "msg_2", "model": "claude-opus-5", "role": "assistant",
            "usage": {"input_tokens": 10, "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 24_000, "output_tokens": 4},
            "content": [{"type": "text", "text": "bye"}]}},
    ]) + "\n")
    comp = compose(path, [record for _, record, _ in load_messages(path)])

    assert round(comp.floor.visible_before_first) == round(estimate(len(opening)))
    assert tokens(comp, "prefix") == round(prefix_tokens) == 23_110


# ─── shedding ────────────────────────────────────────────────────────────────

# `context_shedding.jsonl` states its own answer: five priced requests at
# 12,000 / 30,000 / 22,000 / 25,000 / 24,000, so the window falls by 8,000 at the
# third and by 1,000 at the fifth, and nothing else in the file explains either.
SHED_EVENTS = ((3, 6, 30_000, 22_000, 8_000), (5, 10, 25_000, 24_000, 1_000))
SHED_TOTAL = 9_000


def test_a_shed_window_is_measured_exactly_and_labelled_with_its_request():
    """06- §2 item 2, and the reason the kind matters.

    A shed is a subtraction over two `usage` totals, both of them read: it is
    `exact` and must never be labelled `estimated`, because an estimate would be
    a thing the residual is entitled to argue with and this is not.
    """
    comp = composition("shedding")

    assert [(e.at_request, e.at_record, e.before, e.after, e.tokens)
            for e in comp.shed] == list(SHED_EVENTS)
    assert all(e.of_requests == comp.requests_in_window for e in comp.shed)
    document = to_dict(comp, None)["shedding"]
    assert document["shed"] == {"tokens": SHED_TOTAL, "kind": "exact"}
    assert [event["tokens"] for event in document["events"]] == [
        {"tokens": 8_000, "kind": "exact"}, {"tokens": 1_000, "kind": "exact"}]


def test_a_fall_is_counted_at_any_size_and_not_only_past_a_threshold():
    """The spike ignored anything under 2,000 tokens; this ships no floor.

    Over the 911 anchored sessions in `~/.claude/projects` the 753 falls run
    smoothly from 3 tokens to 339,518 with no gap to cut at, and a 2,000-token
    floor discards 5.0% of every shed token and silences 70 of the 190 shedding
    sessions entirely — they shed thousands in small pieces and nothing in one
    piece. The 1,000-token event in this fixture is one the spike would drop.
    """
    comp = composition("shedding")
    small = [event for event in comp.shed if event.tokens < 2_000]

    assert [event.tokens for event in small] == [1_000]


def test_a_fall_across_an_abandoned_branch_is_not_a_shed():
    """A transcript is a tree and edit-and-retry leaves both branches in it.

    `context_branched.jsonl` reads 12,000 / 30,000 / 18,000 / 34,000 in file
    order and appears to fall by 12,000; on the branch the anchor descends from
    it reads 12,000 / 30,000 / 34,000 and never falls. Pairing across the file
    instead reports 57 falls worth 458,994 tokens on d57c1426 — more than that
    session's whole window — for a session that shed nothing.
    """
    comp = composition("branched")

    assert comp.shed == []
    assert comp.requests_in_window == 4, "the abandoned branch is still priced"
    assert sum(node.tokens for node in comp.nodes) == comp.window
    assert not any(row[0] == SHED_ROW for row in audit_rows(comp))


def test_a_file_that_cannot_name_its_branches_is_read_in_its_own_order():
    """Absence of branch information is not evidence of a branch.

    A record with no `uuid` makes the walk unanswerable, and the honest reading
    is then the order the file is written in — not an exclusion on a guess.
    """
    path = FIXTURES / "context_shedding.jsonl"
    records = [record for _, record, _ in load_messages(path)]
    stripped = [{k: v for k, v in record.items() if k != "uuid"}
                for record in records]

    assert anchored_chain(records, len(records) - 1) is not None
    assert anchored_chain(stripped, len(stripped) - 1) is None
    priced = priced_responses(stripped)
    assert len(on_anchored_chain(priced, stripped)) == len(priced)


def test_the_shed_leaves_the_residual_rather_than_being_buried_in_it():
    """The correctness fix. Before this the 9,000 sat inside `unattributed`.

    The rows above the shed describe material the transcript recorded arriving,
    so they over-claim the window by what has left it; the residual absorbed that
    silently and reported a number that was wrong without saying so. Subtracting
    a measured quantity is not fitting one — nothing here is tuned, and the
    residual keeps its sign (§C10).
    """
    comp = composition("shedding")
    residual = tokens(comp, "unattributed")
    before = residual - SHED_TOTAL

    assert before == -7_066, "what this session reported before the shed was named"
    assert residual == 1_934
    assert abs(residual) < abs(before)
    assert sum(node.tokens for node in comp.nodes) == comp.window + SHED_TOTAL
    # The audit re-prices the window at other constants and would drift from the
    # tree silently if the shed were in only one of them.
    assert abs(residual - comp.audit.residual_at(CHARS_PER_TOKEN)) < 5


def test_the_reconciliation_names_the_shed_as_a_row_of_its_own():
    """`06-` prints it as `of which unmodelled shedding`, inside the residual.

    It is a row here because a quantity the tool has measured exactly is not
    something the confession should be carrying, and because the row is the only
    place the arithmetic can be checked: every row after the first has to add to
    the last one.
    """
    comp = composition("shedding")
    rows = audit_rows(comp)
    shed_row = next(row for row in rows if row[0] == SHED_ROW)

    assert shed_row == (SHED_ROW, SHED_TOTAL, "exact"), "it adds, and it is exact"
    assert rows.index(shed_row) == len(rows) - 2, "the last thing before the residual"
    assert sum(tokens for _, tokens, _ in rows[:-1]) == rows[-1][1]


def test_a_session_that_sheds_nothing_carries_no_shed_row_at_all():
    """The other half: 721 of the 911 anchored sessions on this machine never
    shed, and their books must read exactly as they did before."""
    for name in ("golden", "over_explained", "compacted", "branched"):
        comp = composition(name)

        assert comp.shed == []
        assert not any(row[0] == SHED_ROW for row in audit_rows(comp))
        assert sum(node.tokens for node in comp.nodes) == comp.window
        assert "shed" not in render(comp, None)
        assert to_dict(comp, None)["shedding"] == {
            "events": [], "shed": {"tokens": 0, "kind": "exact"}}


def test_the_shed_lines_are_above_the_tree_with_the_cause_the_file_names():
    """06- calls this "the single cheapest honesty fix available".

    Above the tree because what left is not in the window, and a row of the tree
    would be putting it back. The cause is a pointer to the records worth
    reading and is worded so it cannot be read as an attribution.
    """
    readout = render(composition("shedding"), None)
    heading = next(line for line in readout.splitlines()
                   if SHED_HEADING in line)

    assert "(2 events)" in heading and "9,000" in heading and "exact" in heading
    assert readout.index(heading) < readout.index("unattributed")
    # 07-mockup.md's figure 2 puts the magnitude in the number column and the
    # cause in a warned note beneath, and the row is a fact rather than prose.
    assert re.search(r"at request 3 \(record 6\): 30,000 -> 22,000 +8,000 +— +exact",
                     readout)
    assert f"{FACT_WARN} cause: deferred_tools_delta" in readout
    assert NO_CAUSE not in readout, \
        "five rows each saying nothing explains them is not five facts"
    assert "less shed 9,000" in readout, "the by-kind line still adds up"


def test_the_audit_says_the_prefix_was_not_re_derived_and_why():
    """§C6 offers two ways out and this takes the second: label the prefix with
    the request it was measured at, and say on the page why the re-derivation
    was refused rather than leaving it to a commit message."""
    comp = composition("shedding")
    code, output = context_command(fixture("shedding"), audit=True)
    prefix = next(node for node in comp.nodes if node.label == "prefix")

    assert code == 0
    assert "9,000 tokens have left this window since" in prefix.note
    assert "no record says whether any of them were prefix" in prefix.note
    assert "not re-derived here" in output
    assert "negative on 42 of the" in output, "the measurement, not an opinion"


def test_the_strip_runs_past_the_window_rule_by_what_left_it():
    """07-mockup.md item 3 draws claims against a hard rule at the window. A
    shedding session's claims describe more material than the window now holds,
    and the strip says so by running to what was in here at its fullest."""
    led = ledger(composition("shedding"))
    plain = ledger(composition("golden"))

    assert led.shed == SHED_TOTAL
    assert led.span == led.window + SHED_TOTAL
    assert led.claimed + led.residual == led.span
    assert plain.shed == 0 and plain.span == max(plain.window, plain.claimed)
    lines = render(composition("shedding"), None).splitlines()
    assert any(OVERHANG_OPEN in line for line in lines)
    assert any("9,000 tokens left this window" in line for line in lines)


def test_the_shed_on_the_session_the_spike_measured_it_on(real_claude_dir):
    """939a04dc, `06-` §6: the readout that made shedding a milestone item.

    The two lines the spike printed are the two largest here and reproduce to
    the token. The three below its 2,000-token floor are the difference between
    its 87,753 and this 89,078, and they are counted for the reason above.
    """
    path = real_session("939a04dc")
    comp = compose(path, [record for _, record, _ in load_messages(path)], depth=1)
    magnitudes = [event.tokens for event in comp.shed]

    assert comp.window == 222_249
    assert sorted(magnitudes, reverse=True)[:2] == [78_167, 9_586]
    assert sum(magnitudes) == 89_078
    assert sum(m for m in magnitudes if m > 2_000) == 87_753, "the spike's figure"
    largest = next(e for e in comp.shed if e.tokens == 78_167)
    assert largest.at_record == 288
    assert largest.cause == ("<synthetic> response (interrupt or API error), "
                             "deferred_tools_delta")
    # −25.6% before, and it read as an estimator that cannot count.
    assert tokens(comp, "unattributed") == 32_291 == -56_787 + 89_078


# ─── colour, the key and the width ───────────────────────────────────────────


def test_the_readout_is_clean_ascii_when_nothing_is_watching():
    """`winnow context <id> | cat` must not produce one escape byte.

    pytest's stdout is not a terminal, which is the same condition a pipe puts
    the command in, so `--color auto` is under test here rather than mocked.
    """
    code, readout = context_command(fixture("golden"), depth=3, audit=True)
    assert code == 0
    assert "\x1b" not in readout


def test_plain_output_is_what_it_was_before_there_was_a_palette():
    """The width work is allowed to use a terminal; it is not allowed to move a
    piped readout. With no terminal and no COLUMNS, the layout is M1's 22 and
    54, which is what every committed assertion about this text was written
    against."""
    assert layout(0) == (BAR_COLUMNS, LABEL_COLUMNS)
    assert resolve_style("never", columns=0) == Style()


@pytest.mark.parametrize("kind", KINDS)
def test_colour_lands_on_the_bar_and_the_kind_word_and_on_no_number(kind):
    """07-mockup.md item 4: colour means provenance and nothing else.

    Asserted by finding the kind word painted and every figure on its row bare,
    because a palette that crept onto the numbers would make the column stop
    reading as a table — which is the reason the mockup gives for keeping the
    provenance word beside the chip in the first place.
    """
    style = resolve_style("always", columns=120)
    comp = composition("golden")
    comp.nodes = [Node(label="a node", tokens=1_234, kind=kind)]
    row = next(line for line in render(comp, None, style).splitlines()
               if "a node" in line)
    open_sequence = f"\x1b[{style.palette[kind]}m"

    assert f"{ZERO_RULE}{open_sequence}{BAR_GLYPH}" in row, "the bar is not painted"
    assert row.endswith(f"{open_sequence}{kind}\x1b[0m"), "the kind is not painted"
    # Everything between the label and the kind word is the numeric block, and
    # the only escape sequence left in it should be the one that opens the kind.
    numbers, _, _ = row.split("a node", 1)[1].partition("\x1b")
    assert "1,234" in numbers and "%" in numbers
    # Two sequences opened, two reset: the bar and the word, and nothing else.
    assert row.count("\x1b") == 4, "colour reached something other than the pair"


def test_the_key_names_every_kind_and_gives_unknown_no_mark():
    """The key is the whole grammar, so it is printed rather than documented.

    `unknown` is in it by name and out of the palette by design: a thing with no
    size has no length to draw, and the absence has to read as a decision.
    """
    style = resolve_style("always", columns=120)
    key = key_line(style)

    for kind in KINDS:
        assert f"\x1b[{style.palette[kind]}m█\x1b[0m {kind}" in key
    assert "unknown" in key
    assert style.paint("█", "unknown") == "█"


def test_the_key_is_printed_once_near_the_top_and_only_when_there_is_colour():
    """In plain mode the key would name four hues that are not on the page, and
    the `how each kind was derived` block at the foot already names the kinds.
    The key says which colour; the footer says how the number was got."""
    comp = composition("golden", depth=2)
    coloured = render(comp, None, resolve_style("always", columns=120)).splitlines()
    plain = render(comp, None, resolve_style("never", columns=120)).splitlines()

    assert coloured.count(key_line(resolve_style("always", columns=120))) == 1
    assert coloured[1].startswith("colour is provenance:")
    assert not any(line.startswith("colour is provenance:") for line in plain)


@pytest.mark.parametrize("choice,no_color,term,isatty,wanted", [
    ("auto", None, "xterm-256color", True, True),
    ("auto", None, "xterm-256color", False, False),
    ("auto", None, "dumb", True, False),
    ("auto", "1", "xterm-256color", True, False),
    ("auto", "", "xterm-256color", True, True),
    ("never", None, "xterm-256color", True, False),
    ("never", "1", "xterm-256color", True, False),
    ("always", "1", "dumb", False, True),
])
def test_no_color_beats_auto_and_loses_to_always(monkeypatch, choice, no_color,
                                                 term, isatty, wanted):
    """The NO_COLOR spec's own rule: any non-empty value suppresses colour that
    the tool added by itself, and an explicit request from the operator still
    wins. An empty NO_COLOR is not set, which is the spec's wording too."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    if no_color is not None:
        monkeypatch.setenv("NO_COLOR", no_color)
    monkeypatch.setenv("TERM", term)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: isatty, raising=False)

    assert wants_colour(choice) is wanted


def test_the_palette_falls_back_to_four_hues_a_16_colour_terminal_has(monkeypatch):
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    assert palette() == PALETTE_16

    monkeypatch.setenv("TERM", "screen-256color")
    assert palette() == PALETTE_256

    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setenv("COLORTERM", "truecolor")
    assert palette() == PALETTE_256


@pytest.mark.parametrize("columns", [0, 40, 80, 100, 108, 109, 120, 160, 200, 400])
def test_the_layout_uses_the_terminal_without_ever_going_below_M1s_columns(columns):
    """Never narrower than 22 and 54 together, never past the caps, and never
    wider than the terminal it was given once it is above the floor."""
    bar_columns, label_columns = layout(columns)

    assert bar_columns >= BAR_COLUMNS and label_columns >= LABEL_COLUMNS
    assert bar_columns <= WIDEST_BAR and label_columns <= WIDEST_LABEL
    if bar_columns + label_columns > BAR_COLUMNS + LABEL_COLUMNS:
        assert bar_columns + label_columns + FIXED_COLUMNS <= columns


@pytest.mark.parametrize("columns", [80, 120, 200])
def test_a_wider_terminal_shows_more_of_a_path_and_moves_no_number(columns):
    """What the extra width is for: `indent` still truncates from the left, so
    the leaf — the actionable part of a path — is what the room buys."""
    label = "/workspace/winnow/src/winnow/" + "deeply/" * 6 + "context.py"
    _, label_columns = layout(columns)
    drawn = indent(label, 3, label_columns)

    # The indent is spent out of the label's own room, so a row is exactly as
    # wide at level 3 as at level 1 and the numbers stay in one column.
    assert len(drawn) == label_columns
    assert drawn.rstrip().endswith("context.py")
    if columns > 108:
        assert len(drawn) > LABEL_COLUMNS


def test_json_is_the_same_bytes_whatever_color_says():
    """§C5's document is for a machine, and a machine's pipe is not a terminal.
    Byte-identical under every choice, including one that forces colour on."""
    payloads = [context_command(fixture("golden"), as_json=True, audit=True,
                                depth=3, color=choice)
                for choice in COLOR_CHOICES]

    assert payloads[0] == payloads[1] == payloads[2]
    assert "\x1b" not in payloads[0][1]


def test_an_unknown_color_choice_is_a_usage_error_rather_than_a_guess():
    code, message = context_command(fixture("golden"), color="sometimes")

    assert code == 1
    assert "--color must be one of auto, always, never" in message
    assert "'sometimes'" in message


def test_the_audit_and_explain_are_coloured_by_the_same_style():
    """05- names `--audit` and `--explain <node>` as part of the same readout, so
    a kind word means the same thing and looks the same in all three."""
    style = resolve_style("always", columns=120)
    comp = composition("golden", depth=3)

    assert style.word("exact") in render_audit(comp, style)
    code, text = explain(comp, "prefix", style)
    assert code == 0
    assert style.word("derived") in text
    assert "\x1b" not in explain(comp, "prefix")[1]


# ─── the ledger strip and the diverging track ────────────────────────────────

ANSI = re.compile(r"\x1b\[[0-9;]*m")

# The two marks 07-mockup.md invented and flagged as unreviewed, on the
# fixtures that exercise each side of zero. `over_explained` and
# `prefix_underwater` both overrun their window; `golden` and `skill_body`
# leave room in theirs; `agent` claims 1.8% of a 100,000-token window.
OVERRUNNING = ("over_explained", "prefix_underwater")
UNDERCLAIMING = ("golden", "skill_body", "agent")
UNANCHORED = ("no_anchor", "empty", "bookkeeping_only")


def strip_block(readout: str) -> list[str]:
    """The ledger strip's own lines, from the strip down to its last legend line."""
    lines = readout.splitlines()
    start = next((i for i, line in enumerate(lines) if WINDOW_RULE in line), None)
    if start is None:
        return []
    return lines[start:lines.index("", start)]


@pytest.mark.parametrize("name", OVERRUNNING)
def test_an_overrun_window_is_drawn_as_an_overhang_with_a_bracket_under_it(name):
    """07-mockup.md item 3, and the reason it is worth building: the same
    arithmetic printed as a signed number in a column reads as a rounding
    artefact, and a quarter of the strip hanging past the window rule does not.
    """
    comp = composition(name)
    block = strip_block(render(comp, None))
    strip, bracket = block[0], block[1]

    assert ledger(comp).residual < 0
    assert strip.index(WINDOW_RULE) < len(strip) - 1, \
        "the window rule is inside the strip, so there is an outside to it"
    assert bracket.strip().startswith(OVERHANG_OPEN), "no bracket under the overhang"
    # The bracket starts under the first cell past the rule and ends under the
    # last, whatever the terminal is wide enough to draw.
    assert len(bracket) == len(strip)
    assert bracket.index(OVERHANG_OPEN) == strip.index(WINDOW_RULE) + 1
    assert any("overrun the window" in line for line in block)


@pytest.mark.parametrize("name", UNDERCLAIMING)
def test_a_window_with_room_left_in_it_gets_no_bracket_and_a_rule_at_the_end(name):
    """The mark has to be quiet when the books balance, or it says nothing when
    they do not. Room left over is the residual segment reaching the rule."""
    comp = composition(name)
    block = strip_block(render(comp, None))

    assert ledger(comp).residual > 0
    assert block[0].endswith(WINDOW_RULE), "the parts fit, so the rule is the end"
    assert not any(OVERHANG_OPEN in line for line in block)
    assert not any("overrun" in line for line in block)
    assert LEDGER_GLYPH["residual"] in block[0], "the room left over is not drawn"


@pytest.mark.parametrize("name", UNANCHORED)
def test_an_unanchored_session_gets_no_strip_rather_than_a_strip_of_zeroes(name):
    """§C2: no anchor, no denominator, no share — and so no scale to draw one
    against. A strip here would be four hundred columns of nothing claiming to
    be a proportion of a window nobody measured."""
    comp = composition(name)
    readout = render(comp, None)

    assert ledger(comp) is None
    assert WINDOW_RULE not in readout
    assert not any(glyph in readout for glyph in ("▓", "▒", "░"))
    assert ZERO_RULE not in readout, "an axis with no scale is a claim too"


@pytest.mark.parametrize("name", OVERRUNNING + UNDERCLAIMING + (
    "compacted", "image", "by_path", "zero_usage_anchor", "torn_trailing"))
def test_the_strip_and_the_audit_are_two_renderings_of_one_subtraction(name):
    """The constraint the strip is only allowed to exist under. `--audit` prints
    the window less every claim, leaving the residual; the strip draws the same
    rows as lengths. They are asserted equal here rather than kept equal by
    hand, because a strip that could disagree with the audit would be a second
    opinion about a subtraction that has only one answer."""
    comp = composition(name)
    led, rows = ledger(comp), audit_rows(comp)

    assert rows[0][1] == led.window
    claims: dict[str, int] = {}
    for _, tokens, kind in rows[1:]:
        if kind != "residual":
            claims[kind] = claims.get(kind, 0) - tokens
    assert dict(led.parts) == claims
    assert led.residual == next(t for _, t, k in rows if k == "residual")
    assert led.window - led.claimed == led.residual, "the strip is the subtraction"


@pytest.mark.parametrize("name", OVERRUNNING + UNDERCLAIMING)
@pytest.mark.parametrize("columns", [80, 120, 200])
def test_the_strip_never_wraps_the_terminal_it_was_given(name, columns):
    """A proportion continued on a second line is not a proportion. The strip is
    the one mark capped at the terminal rather than at the tree row's width."""
    style = resolve_style("never", columns=columns)
    block = strip_block(render(composition(name), None, style))

    assert block
    assert all(len(line) <= columns for line in block)
    assert len(block[0]) == style.strip_columns + 3, "margin, cells, window rule"


def test_a_residual_past_the_deficit_room_is_clipped_and_says_which_row_was():
    """The track keeps a quarter of the bar column for the deficit side, which
    holds every negative residual out to −31%: on the 922 anchored sessions on
    this machine the median negative is −2.6% and 16 of the 423 go past it. The
    16 are the case this asserts — the drawn length stops at the edge and says
    so, and the number two columns away is still the whole number."""
    comp = composition("over_explained")
    readout = render(comp, None)
    row = next(line for line in readout.splitlines() if "unattributed" in line)

    assert 100 * ledger(comp).residual / comp.window < -31
    assert OFF_SCALE in row, "a clipped bar does not say it was clipped"
    assert "-7,500" in row and "-50.0%" in row, "the number was shortened too"
    assert any("Only the drawing was shortened" in line
               for line in readout.splitlines())


def test_a_residual_inside_the_deficit_room_is_drawn_whole():
    """The other side of the clip: the common negative fits, so nothing is
    marked. Without this the clip mark would be free to appear on every row."""
    comp = composition("golden")
    comp.nodes = [Node(label="unattributed", tokens=-1_000, kind="residual")]
    readout = render(comp, None)

    assert OFF_SCALE not in readout
    assert not any("Only the drawing was shortened" in line
                   for line in readout.splitlines())


def test_a_claim_far_under_the_window_still_puts_the_rule_where_the_window_is():
    """`agent` claims 1,771 tokens of a 100,000-token window. The strip has to
    stay a picture of that window rather than rescale itself onto the 1.8%."""
    comp = composition("agent")
    led = ledger(comp)
    strip = strip_block(render(comp, None))[0]

    assert led.claimed / led.window < 0.02
    assert strip.endswith(WINDOW_RULE)
    assert strip.count(LEDGER_GLYPH["residual"]) > strip.count(LEDGER_GLYPH["estimated"])


@pytest.mark.parametrize("name", OVERRUNNING + UNDERCLAIMING)
def test_the_strip_is_drawn_to_the_parts_and_never_rescaled_to_fit(name):
    """06-'s finding, as an assertion: the overrun 'falls out of drawing the
    parts against an exact total and refusing to normalise'. So the rule sits at
    the window's own share of the span, and the segments keep their ratio to
    each other whichever side of the window they end up on."""
    style = resolve_style("never", columns=200)
    led = ledger(composition(name))
    strip = strip_block(render(composition(name), None, style))[0]
    cells = strip[2:].replace(WINDOW_RULE, "")

    span = max(led.window, led.claimed)
    assert abs(strip.index(WINDOW_RULE) - 2
               - style.strip_columns * led.window / span) <= 1
    for kind, tokens in led.parts:
        assert abs(cells.count(LEDGER_GLYPH[kind])
                   - style.strip_columns * tokens / span) <= 1


@pytest.mark.parametrize("name", OVERRUNNING + UNDERCLAIMING)
def test_colour_is_added_to_the_marks_and_is_never_what_carries_them(name):
    """`--color never` has to lose the palette and nothing else. Asserted by
    stripping the escapes back off the coloured readout and demanding the plain
    one byte for byte: every rule, bracket and glyph survives the strip, so
    nothing on the page is drawn in hue alone."""
    plain = render(composition(name), None, resolve_style("never", columns=120))
    coloured = render(composition(name), None, resolve_style("always", columns=120))

    assert "\x1b" in coloured
    # The key is the one line colour adds rather than paints — in plain mode it
    # would name four hues that are not on the page — so it comes back out here.
    bare = [line for line in ANSI.sub("", coloured).splitlines()
            if not line.startswith("colour is provenance:")]
    assert "\n".join(bare) == plain


def test_the_plain_strip_tells_its_three_kinds_apart_by_glyph():
    """What makes the paragraph above true of the strip in particular: three
    segments, three glyphs, and a window rule that is none of them."""
    glyphs = {LEDGER_GLYPH[kind] for kind in ("derived", "estimated", "residual")}

    assert len(glyphs) == 3
    assert WINDOW_RULE not in glyphs and ZERO_RULE not in glyphs
    assert LEDGER_GLYPH["derived"] in strip_block(render(composition("golden"), None))[0]


@pytest.mark.parametrize("columns", [BAR_COLUMNS, 24, WIDEST_BAR])
def test_the_track_gives_the_deficit_a_quarter_of_the_column_and_keeps_one_scale(
        columns):
    """07-mockup.md item 2's proportions: 60px against 180px, so a quarter here.
    One scale means the positive room is what 100% measures against on both
    sides — a −20% row and a +20% row are the same length."""
    deficit, positive = track_rooms(columns)
    style = Style(bar_columns=columns)

    assert deficit + 1 + positive == columns
    assert abs(deficit / (columns - 1) - 0.25) < 0.05
    assert (len(track(-0.2, "residual", style).strip())
            == len(track(0.2, "estimated", style).strip())), \
        "the same share is the same length on either side of zero"


def test_the_track_draws_no_axis_when_there_is_no_scale():
    """Same refusal as the strip's, one column wide: `share is None` is a
    session with no anchor, and an origin drawn against nothing is a claim."""
    assert track(None, "estimated", Style()).strip() == ""
    assert ZERO_RULE in track(0.0, "residual", Style()), "zero is still on the axis"


@pytest.mark.parametrize("share", [0.0001, -0.0001])
def test_a_magnitude_too_small_for_a_column_still_gets_a_hairline(share):
    """A row that reads as empty is the failure the mark exists to stop, and it
    is the failure the old `bar()` had on a small negative residual."""
    drawn = track(share, "residual", Style())
    left, _, right = drawn.partition(ZERO_RULE)

    assert len(drawn) == BAR_COLUMNS
    assert (left if share < 0 else right).strip()


# ─── the block of exact facts, above the tree ────────────────────────────────


def test_the_exact_facts_are_one_block_behind_one_rule():
    """07-mockup.md draws them with a 3px left border in the `exact` colour.

    The border is the whole grouping — no box, no heading — and what it groups
    is every number in the readout that was read rather than apportioned. So the
    rule runs down every line of the block and stops at the first line of
    anything else.
    """
    readout = render(composition("compacted"), 200_000).splitlines()
    block = [line for line in readout if line.startswith(FACT_RULE)]

    assert readout[1:1 + len(block)] == block, "one block, straight under the header"
    assert len(block) == 4, [line for line in block]
    assert all(FACT_RULE not in line for line in readout[1 + len(block):]), \
        "the rule is the block's and no row of the tree borrows it"
    assert all(line.rstrip().endswith("exact") or line.lstrip(FACT_RULE).strip()
               .startswith((FACT_NOTE, FACT_WARN)) for line in block)

    # The block is the same readout as the tree and not a preamble to it, so a
    # fact's three columns are a tree row's three columns.
    window = next(line for line in readout if "window at the last request" in line)
    row = next(line for line in readout if "unattributed" in line)
    ends = window.index("12,000") + len("12,000")
    assert row[:ends].endswith("2,476") and window[ends:] == "  100.0%  exact"
    assert row[ends:] == "   20.6%  residual"


def test_the_compacted_session_the_mockup_names(real_claude_dir):
    """07-mockup.md's "first thing to add if this gets a second pass": the
    fourth kind of above-tree fact, which it never drew. 2551cd0c's three exact
    numbers are named in the file and are reproduced here to the token."""
    path = real_session("2551cd0c")
    comp = compose(path, [record for _, record, _ in load_messages(path)])
    block = [line for line in render(comp, None).splitlines()
             if line.startswith(FACT_RULE)]

    assert comp.window == 116_030
    assert "116,030" in block[0] and "window at the last request" in block[0]
    assert "444,326" in block[1] and "dropped by compaction" in block[1]
    assert block[2].endswith("170,229 -> 23,301")
    assert block[2].lstrip(FACT_RULE).strip().startswith(FACT_NOTE), \
        "pre and post are one fact with two numbers, so they are its note"


def test_a_shed_row_carries_its_magnitude_in_the_number_column():
    """07-mockup.md's figure 2 gives each fall a row rather than a sentence.

    The previous slice printed them as prose beneath a total, which put the one
    number that matters in the middle of a line. Here the row is a fact: where
    it happened in the label, what left in the number column, `exact` beside it.
    """
    block = [line for line in render(composition("shedding"), None).splitlines()
             if line.startswith(FACT_RULE)]
    rows = [line for line in block if "at request" in line]
    heading = next(line for line in block if SHED_HEADING in line)

    assert len(rows) == 2, block
    assert all(re.search(r"\s(8,000|1,000)\s+—\s+exact$", row) for row in rows)
    assert rows[0].index("8,000") == heading.index("9,000"), "one number column"
    assert "(2 events)" in heading, "the total heads them"


def test_the_shed_block_never_grows_past_five_rows_and_says_what_it_folded():
    """The cap is `SHED_EVENTS_SHOWN`; what it leaves out is a row of its own,
    because a total that silently stopped adding would be the one thing this
    readout cannot afford."""
    events = [Shed(at_record=n, at_request=n, of_requests=40,
                   before=1_000 * (n + 1), after=1_000 * n, cause=NO_CAUSE)
              for n in range(1, 21)]
    facts = shed_facts(events)
    folded = facts[-1]

    assert len(facts) == 1 + SHED_EVENTS_SHOWN + 1
    assert folded.label.strip() == "and 15 more, each smaller"
    assert (int(folded.value.replace(",", ""))
            + sum(int(f.value.replace(",", "")) for f in facts[1:-1])
            == shed_tokens(events))


# ─── the four ways of having nothing to draw ─────────────────────────────────


def test_no_anchor_states_the_refusal_where_the_window_would_have_been():
    """05- §M1's acceptance criterion, given 07-mockup.md figure 6's treatment.

    Unchanged in what it does — the estimated tree, no percentage anywhere, exit
    3 — and changed in where it says why: the refusal is the reason every share
    below is missing, so it goes where the share would have been rather than
    into a footnote under the tree.
    """
    code, output = context_command(fixture("no_anchor"))
    lines = output.splitlines()
    refusal = next(n for n, line in enumerate(lines) if NO_ANCHOR[:40] in line)
    first_row = next(n for n, line in enumerate(lines) if "tool traffic" in line)

    assert code == 3
    assert "%" not in output
    assert refusal < first_row
    assert lines[1].startswith(FACT_RULE) and "unanchored" in lines[1]
    assert lines[refusal].lstrip(FACT_RULE).strip().startswith(FACT_WARN)
    assert output.count(NO_ANCHOR[:40]) == 1, "said at the top, not also at the foot"
    # It stays in the document, which has no top to say it at.
    assert NO_ANCHOR in to_dict(composition("no_anchor"), None)["notes"]


def test_an_ambiguous_prefix_lists_its_matches_and_refuses_as_inspect_does(
        tmp_path, monkeypatch):
    """The mockup invents exit 2 for this. It is 1, because `winnow inspect`
    already answers 1 to the same mistake through the same `resolve_session`,
    and one mistake answering differently in two commands is worse than either
    answer. What is new is the listing: `resolve_session`'s message names up to
    four stems and stops, and choosing between them needs more than the stems.
    """
    projects = tmp_path / "claude" / "projects" / "-workspace-winnow"
    projects.mkdir(parents=True)
    for suffix in ("aaaa", "bbbb"):
        shutil.copy(FIXTURES / "context_golden.jsonl",
                    projects / f"5f5f5f5f-1111-2222-3333-44444444{suffix}.jsonl")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))

    code, output = context_command("5f5f")

    assert code == inspect_command("5f5f", "CB", 4, 300, False)[0] == 1
    assert "matches 2 sessions" in output
    assert output.count("5f5f5f5f-1111-2222-3333-44444444") == 2, "both, in full"
    assert output.count(FACT_RULE) == 2
    assert "give more of the id" in output.lower()


def test_a_jsonl_that_is_not_a_transcript_is_refused_on_the_type_field(tmp_path):
    """Also invented as exit 2 by the mockup, and taken as 1 here: exit 2 in
    this CLI is "nothing to do, and that is not an error", where a file that is
    not a transcript is a wrong argument. Nothing is priced from it — a window
    read out of the wrong file is the one error the residual cannot catch."""
    dump = tmp_path / "dump.jsonl"
    dump.write_text('{"event":"start"}\n{"event":"row","n":2}\n{"event":"ro')

    code, output = context_command(str(dump))

    assert code == 1
    assert output.startswith("winnow: dump.jsonl is not a Claude Code transcript.")
    assert "carrying a `type` field" in output and "type: summary" in output
    assert "One trailing line did not parse" in output
    assert "is not why this failed" in output, "the torn line is named, not blamed"
    assert "window at the last request" not in output, "nothing was priced"


def test_an_empty_transcript_keeps_its_own_refusal(tmp_path):
    """The `type` check must not swallow the empty file: it has no records to be
    untyped, and 05- §M1 already answers it with the no-anchor refusal."""
    code, output = context_command(fixture("empty"))

    assert code == 3
    assert "0 records" in output and "not a Claude Code transcript" not in output


def test_one_request_prints_the_numbers_and_draws_no_tree():
    """The mockup's fourth state, at the threshold this run measured rather than
    the ten it guessed. Not an error and not a refusal: every number is here."""
    code, output = context_command(fixture("zero_usage_anchor"))
    lines = output.splitlines()

    assert code == 0
    assert "8,000  100.0%  exact" in lines[1]
    assert [line.split()[-1] for line in lines if line.startswith("  ") and
            line.strip() and line.split()[-1] in KINDS] == \
        ["derived", "estimated", "residual"], "three numbers, and no tree"
    assert "prefix (not in the file)" in output
    assert "tool traffic" not in output and "conversation" not in output
    assert f"after {THIN_REQUESTS} priced requests" in output


def test_the_threshold_is_where_the_corpus_splits_and_not_where_the_mockup_guessed():
    """07-mockup.md item 9 calls ten a guess and it is. Two is the count that
    separates ~/.claude/projects cleanly, and the readout says so on the page
    rather than in a commit message."""
    assert THIN_REQUESTS == 2
    assert too_thin(composition("zero_usage_anchor"))
    assert not too_thin(composition("golden")), "three requests is a ranking"
    assert not too_thin(composition("no_anchor")), \
        "no window is the other refusal, and it owns the screen"


def test_no_empty_state_writes_anything_or_raises(tmp_path, monkeypatch):
    """§C1 holds on the failure paths too, which is where a tool usually starts
    touching things it said it would not."""
    projects = tmp_path / "claude" / "projects" / "-workspace-winnow"
    projects.mkdir(parents=True)
    shutil.copy(FIXTURES / "context_golden.jsonl", projects / "cccc0000.jsonl")
    shutil.copy(FIXTURES / "context_golden.jsonl", projects / "cccc1111.jsonl")
    (tmp_path / "dump.jsonl").write_text('{"not":"a transcript"}\n')
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))

    before = {str(p): p.stat().st_mtime_ns for p in sorted(tmp_path.rglob("*"))}
    codes = [context_command(argument)[0] for argument in
             ("cccc", str(tmp_path / "dump.jsonl"), fixture("no_anchor"),
              fixture("zero_usage_anchor"))]

    assert codes == [1, 1, 3, 0]
    assert {str(p): p.stat().st_mtime_ns for p in sorted(tmp_path.rglob("*"))} == before


# ─── the tool's own known faults ─────────────────────────────────────────────


def test_a_known_fault_is_confessed_once_and_not_once_per_row_it_is_about():
    """07-mockup.md item 10, decided against putting these on the rows.

    The mockup drew one `$ cd` and one `edited_text_file` annotated by hand, but
    the tool draws every row of a class: on 939a04dc at `--depth 3` a per-row
    note lands six times under `Bash results` and seven under `standing
    configuration`. Both faults are properties of a key rather than of a row,
    and the same sentence repeated N times reads as N findings.
    """
    results = Node(label="Bash results", tokens=90, kind="estimated")
    results.children = [Node(label=f"$ {head}  ×3", tokens=30, kind="estimated")
                        for head in ("cd", "grep", "git log")]
    nodes = [Node(label="tool traffic", tokens=90, kind="estimated",
                  children=[results])]

    assert own_faults(nodes) == own_faults(nodes[:1] + [Node(
        label="tool traffic", tokens=0, kind="estimated")])
    assert len(own_faults(nodes)) == 1, "three rows, one fault"
    assert "`bash_head` splits" in own_faults(nodes)[0]


def test_a_fault_is_earned_by_the_tree_that_was_drawn():
    """Neither is a standing disclaimer: a tree with no `$ head` row has no
    `bash_head` fault to confess, and one with no attachment has no attachment
    class to disclaim."""
    heads = render(composition("compacted", depth=3), None)
    attachments = render(composition("golden", depth=3), None)

    assert "`bash_head` splits" in heads and "not keyed by provenance" not in heads
    assert "not keyed by provenance" in attachments
    assert "`bash_head` splits" not in attachments
    assert "`bash_head` splits" not in render(composition("compacted"), None), \
        "a `$ head` row is a level-three row and --depth 2 does not draw one"


@pytest.mark.parametrize("name", ["compacted", "golden", "by_path"])
def test_a_fault_is_a_rendering_and_never_reaches_the_document(name):
    """§C5, and this run's constraint that `--json` is what it was. A fault is
    true of a tree at a depth; `--json` is the composition."""
    document = to_dict(composition(name, depth=3), None)

    assert not any("bash_head" in note or "not keyed by provenance" in note
                   for note in document["notes"])
