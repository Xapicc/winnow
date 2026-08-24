"""Tests for the two SPEC §4 B1 rules: identical-reread and changed-reread."""

from __future__ import annotations

import unittest

from winnow.legacy.config import FloorConfig
from winnow.legacy.executor import execute_actions, run_prescription
from winnow.legacy.helpers import get_content_blocks, msg_bytes
from winnow.legacy.registry import PRESCRIPTIONS, STRATEGIES

# Ensure strategies are registered
import winnow.legacy.strategies  # noqa: F401

# Comfortably over the 2,048-byte default floor.
BODY = "def handler(request):\n    return None\n" * 80
POINTER_PREFIX = "[winnow: identical re-read removed"


def make_message(line_idx: int, msg: dict) -> tuple[int, dict, int]:
    return (line_idx, msg, msg_bytes(msg))


def make_read_call(
    line_idx: int,
    tool_use_id: str,
    file_path: str = "/repo/handler.py",
    *,
    offset: object = None,
    limit: object = None,
) -> tuple[int, dict, int]:
    tool_input: dict = {"file_path": file_path}
    if offset is not None:
        tool_input["offset"] = offset
    if limit is not None:
        tool_input["limit"] = limit
    msg = {
        "type": "assistant",
        "uuid": f"uuid-{line_idx}",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_use_id, "name": "Read", "input": tool_input}],
        },
    }
    return make_message(line_idx, msg)


def make_read_result(
    line_idx: int,
    tool_use_id: str,
    content: object = BODY,
    *,
    is_error: bool = False,
    extra: dict | None = None,
) -> tuple[int, dict, int]:
    block: dict = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if is_error:
        block["is_error"] = True
    msg = {
        "type": "user",
        "uuid": f"uuid-{line_idx}",
        "message": {"role": "user", "content": [block]},
    }
    if extra:
        msg.update(extra)
    return make_message(line_idx, msg)


def run(messages: list, config: dict | None = None):
    return STRATEGIES["identical-reread"].func(messages, config or {})


def run_changed(messages: list, config: dict | None = None):
    return STRATEGIES["changed-reread"].func(messages, config or {})


def content_at(messages: list, line_idx: int, block_idx: int = 0) -> object:
    for idx, msg, _ in messages:
        if idx == line_idx:
            return get_content_blocks(msg)[block_idx].get("content")
    raise AssertionError(f"line {line_idx} not in result")


class TestSupersession(unittest.TestCase):
    def test_identical_reread_strips_the_earlier_result(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1"),
            make_read_call(2, "t2"),
            make_read_result(3, "t2"),
        ]
        sr = run(messages)
        self.assertEqual([a.line_index for a in sr.actions], [1])
        self.assertEqual(sr.messages_replaced, 1)
        self.assertGreater(sr.pruned_bytes, 0)

        after = execute_actions(messages, sr.actions)
        self.assertTrue(str(content_at(after, 1)).startswith(POINTER_PREFIX))
        self.assertEqual(content_at(after, 3), BODY)

    def test_pointer_names_the_path_and_the_surviving_bytes(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1"),
            make_read_call(2, "t2"),
            make_read_result(3, "t2"),
        ]
        after = execute_actions(messages, run(messages).actions)
        pointer = str(content_at(after, 1))
        self.assertIn("/repo/handler.py", pointer)
        self.assertIn(str(len(BODY.encode())), pointer)

    def test_changed_content_is_never_stripped(self):
        """The re-read that matters most is the one this rule refuses: same
        path, same range, content the file changed underneath."""
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY + "# one byte more\n"),
        ]
        self.assertEqual(run(messages).actions, [])

    def test_one_byte_difference_is_a_difference(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY[:-1] + "X"),
        ]
        self.assertEqual(run(messages).actions, [])

    def test_a_a_b_keeps_the_second_a(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY),
            make_read_call(4, "t3"),
            make_read_result(5, "t3", BODY + "changed\n"),
        ]
        sr = run(messages)
        self.assertEqual([a.line_index for a in sr.actions], [1])

    def test_a_b_a_strips_across_the_intervening_read(self):
        """Supersession does not require adjacency: the third read restores the
        first read's exact bytes, so the first is redundant."""
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY + "edited\n"),
            make_read_call(4, "t3"),
            make_read_result(5, "t3", BODY),
        ]
        sr = run(messages)
        self.assertEqual([a.line_index for a in sr.actions], [1])

    def test_single_read_is_untouched(self):
        messages = [make_read_call(0, "t1"), make_read_result(1, "t1")]
        self.assertEqual(run(messages).actions, [])

    def test_other_tools_are_not_compared(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1"),
            make_read_call(2, "t2"),
            make_read_result(3, "t2"),
        ]
        for line in (0, 2):
            get_content_blocks(messages[line][1])[0]["name"] = "Bash"
        self.assertEqual(run(messages).actions, [])


class TestRanges(unittest.TestCase):
    def test_same_range_identical_content_is_stripped(self):
        messages = [
            make_read_call(0, "t1", offset=40, limit=50),
            make_read_result(1, "t1"),
            make_read_call(2, "t2", offset=40, limit=50),
            make_read_result(3, "t2"),
        ]
        sr = run(messages)
        self.assertEqual([a.line_index for a in sr.actions], [1])
        after = execute_actions(messages, sr.actions)
        self.assertIn("offset=40, limit=50", str(content_at(after, 1)))

    def test_different_ranges_are_not_compared(self):
        """Identical bytes from two different windows stay put: no interval
        arithmetic, and the pointer would otherwise name a range the stripped
        read never asked for."""
        messages = [
            make_read_call(0, "t1", offset=1, limit=50),
            make_read_result(1, "t1"),
            make_read_call(2, "t2", offset=51, limit=50),
            make_read_result(3, "t2"),
        ]
        self.assertEqual(run(messages).actions, [])

    def test_ranged_read_is_not_superseded_by_a_whole_file_read(self):
        messages = [
            make_read_call(0, "t1", offset=1, limit=50),
            make_read_result(1, "t1"),
            make_read_call(2, "t2"),
            make_read_result(3, "t2"),
        ]
        self.assertEqual(run(messages).actions, [])

    def test_different_paths_are_not_compared(self):
        messages = [
            make_read_call(0, "t1", "/repo/a.py"),
            make_read_result(1, "t1"),
            make_read_call(2, "t2", "/repo/b.py"),
            make_read_result(3, "t2"),
        ]
        self.assertEqual(run(messages).actions, [])

    def test_int_and_string_offsets_stay_distinct(self):
        messages = [
            make_read_call(0, "t1", offset=40, limit=50),
            make_read_result(1, "t1"),
            make_read_call(2, "t2", offset="40", limit=50),
            make_read_result(3, "t2"),
        ]
        self.assertEqual(run(messages).actions, [])


class TestGuards(unittest.TestCase):
    def test_result_below_the_floor_is_left_alone(self):
        small = "x" * 1000
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", small),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", small),
        ]
        self.assertEqual(run(messages).actions, [])

    def test_floor_is_configurable(self):
        small = "x" * 1000
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", small),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", small),
        ]
        sr = run(messages, {"identical_reread_min_bytes": 512})
        self.assertEqual([a.line_index for a in sr.actions], [1])

    def test_pointer_longer_than_the_content_is_no_saving(self):
        """G4: with the floor off, a tiny result must still not inflate."""
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", "ok"),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", "ok"),
        ]
        self.assertEqual(run(messages, {"identical_reread_min_bytes": 0}).actions, [])

    def test_error_results_survive(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY, is_error=True),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY, is_error=True),
        ]
        self.assertEqual(run(messages).actions, [])

    def test_protected_message_is_not_rewritten(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", extra={"isVisibleInTranscriptOnly": True}),
            make_read_call(2, "t2"),
            make_read_result(3, "t2"),
        ]
        self.assertEqual(run(messages).actions, [])

    def test_protected_later_read_still_supersedes(self):
        """Protection stops a message being rewritten; it does not stop it
        acting as the surviving copy."""
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1"),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", extra={"isVisibleInTranscriptOnly": True}),
        ]
        self.assertEqual([a.line_index for a in run(messages).actions], [1])

    def test_tool_use_and_result_stay_paired(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1"),
            make_read_call(2, "t2"),
            make_read_result(3, "t2"),
        ]
        after = execute_actions(messages, run(messages).actions)
        result_ids = {
            b.get("tool_use_id")
            for _, msg, _ in after
            for b in get_content_blocks(msg)
            if b.get("type") == "tool_result"
        }
        self.assertEqual(result_ids, {"t1", "t2"})
        self.assertEqual(len(after), 4)


class TestContentShapes(unittest.TestCase):
    def test_list_content_is_compared_verbatim(self):
        blocks = [{"type": "text", "text": BODY}]
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", blocks),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", [{"type": "text", "text": BODY}]),
        ]
        self.assertEqual([a.line_index for a in run(messages).actions], [1])

    def test_string_and_list_content_do_not_match(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", [{"type": "text", "text": BODY}]),
        ]
        self.assertEqual(run(messages).actions, [])

    def test_key_order_is_a_difference(self):
        """Byte-for-byte means byte-for-byte: two blocks that differ only in key
        order are different wire payloads and are not merged."""
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", [{"type": "text", "text": BODY}]),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", [{"text": BODY, "type": "text"}]),
        ]
        self.assertEqual(run(messages).actions, [])


class TestMalformedInput(unittest.TestCase):
    def test_unanswered_read_is_ignored(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_call(1, "t2"),
            make_read_result(2, "t2"),
        ]
        self.assertEqual(run(messages).actions, [])

    def test_unhashable_offset_does_not_crash(self):
        messages = [
            make_read_call(0, "t1", offset=[1, 2], limit=50),
            make_read_result(1, "t1"),
            make_read_call(2, "t2", offset=[1, 2], limit=50),
            make_read_result(3, "t2"),
        ]
        self.assertEqual([a.line_index for a in run(messages).actions], [1])

    def test_non_dict_blocks_and_unhashable_ids_do_not_crash(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1"),
            make_read_call(2, "t2"),
            make_read_result(3, "t2"),
        ]
        get_content_blocks(messages[0][1]).insert(0, "not-a-block")
        get_content_blocks(messages[2][1])[0]["id"] = ["unhashable"]
        self.assertEqual(run(messages).actions, [])

    def test_non_dict_block_is_preserved_through_a_rewrite(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1"),
            make_read_call(2, "t2"),
            make_read_result(3, "t2"),
        ]
        get_content_blocks(messages[1][1]).append("trailing-junk")
        after = execute_actions(messages, run(messages).actions)
        blocks = [get_content_blocks(m) for idx, m, _ in after if idx == 1][0]
        self.assertEqual(blocks[1], "trailing-junk")

    def test_missing_file_path_is_ignored(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1"),
            make_read_call(2, "t2"),
            make_read_result(3, "t2"),
        ]
        for line in (0, 2):
            get_content_blocks(messages[line][1])[0]["input"] = {}
        self.assertEqual(run(messages).actions, [])


class TestPairingIndex(unittest.TestCase):
    def test_result_far_from_its_call_is_still_found(self):
        """stale-reads scans five messages ahead; progress ticks routinely push
        a result further than that, so this rule indexes by tool_use_id."""
        messages = [make_read_call(0, "t1")]
        for i in range(1, 11):
            messages.append(make_message(i, {"type": "progress", "uuid": f"uuid-{i}"}))
        messages.append(make_read_result(11, "t1"))
        messages.append(make_read_call(12, "t2"))
        messages.append(make_read_result(13, "t2"))
        self.assertEqual([a.line_index for a in run(messages).actions], [11])

    def test_parallel_reads_share_one_action(self):
        """Two Read calls in one assistant message answered in one user message:
        both blocks must be rewritten by a single action, or the second would
        overwrite the first in execute_actions."""
        call = make_message(0, {
            "type": "assistant",
            "uuid": "uuid-0",
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/repo/a.py"}},
                {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "/repo/b.py"}},
            ]},
        })
        results = make_message(1, {
            "type": "user",
            "uuid": "uuid-1",
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": BODY},
                {"type": "tool_result", "tool_use_id": "t2", "content": BODY + "b\n"},
            ]},
        })
        messages = [
            call,
            results,
            make_read_call(2, "t3", "/repo/a.py"),
            make_read_result(3, "t3", BODY),
            make_read_call(4, "t4", "/repo/b.py"),
            make_read_result(5, "t4", BODY + "b\n"),
        ]
        sr = run(messages)
        self.assertEqual([a.line_index for a in sr.actions], [1])
        after = execute_actions(messages, sr.actions)
        self.assertTrue(str(content_at(after, 1, 0)).startswith(POINTER_PREFIX))
        self.assertTrue(str(content_at(after, 1, 1)).startswith(POINTER_PREFIX))
        self.assertIn("/repo/a.py", str(content_at(after, 1, 0)))
        self.assertIn("/repo/b.py", str(content_at(after, 1, 1)))


class TestPrescriptions(unittest.TestCase):
    def test_registered_in_standard_and_aggressive(self):
        self.assertIn("identical-reread", PRESCRIPTIONS["standard"])
        self.assertIn("identical-reread", PRESCRIPTIONS["aggressive"])
        self.assertNotIn("identical-reread", PRESCRIPTIONS["gentle"])

    def test_runs_before_every_content_rewriter(self):
        rewriters = ("tool-output-trim", "tool-result-age", "stale-reads", "document-dedup")
        for tier in ("standard", "aggressive"):
            order = PRESCRIPTIONS[tier]
            mine = order.index("identical-reread")
            for name in rewriters:
                if name in order:
                    self.assertLess(mine, order.index(name), f"{name} precedes identical-reread in {tier}")

    def test_survives_the_full_pipeline(self):
        """run_prescription applies the actions, enforces the floor, fixes
        orphans and runs validate_post_prune — which raises on a broken
        tool_use/tool_result pairing."""
        messages = [
            make_message(0, {"type": "user", "uuid": "uuid-0", "parentUuid": None,
                             "message": {"role": "user", "content": "read it twice"}}),
            make_read_call(1, "t1"),
            make_read_result(2, "t1"),
            make_read_call(3, "t2"),
            make_read_result(4, "t2"),
        ]
        after, results = run_prescription(
            messages, ["identical-reread"], {}, floor_config=FloorConfig.disabled(),
        )
        self.assertTrue(str(content_at(after, 2)).startswith(POINTER_PREFIX))
        self.assertEqual(content_at(after, 4), BODY)
        self.assertEqual(len(after), 5)

    def test_standard_prescription_runs_clean(self):
        messages = [
            make_message(0, {"type": "user", "uuid": "uuid-0", "parentUuid": None,
                             "message": {"role": "user", "content": "read it twice"}}),
            make_read_call(1, "t1"),
            make_read_result(2, "t1"),
            make_read_call(3, "t2"),
            make_read_result(4, "t2"),
            make_message(5, {"type": "assistant", "uuid": "uuid-5", "parentUuid": "uuid-0",
                             "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]}}),
        ]
        after, results = run_prescription(
            messages, PRESCRIPTIONS["standard"], {}, floor_config=FloorConfig.disabled(),
        )
        names = {r.strategy_name for r in results}
        self.assertIn("identical-reread", names)
        self.assertTrue(str(content_at(after, 2)).startswith(POINTER_PREFIX))


# ---------------------------------------------------------------------------
# changed-reread — the lossy half of B1
# ---------------------------------------------------------------------------

CHANGED_POINTER_PREFIX = "[winnow: superseded re-read removed"


class TestChangedReread(unittest.TestCase):
    def test_changed_content_strips_the_earlier_read(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY + "# added\n"),
        ]
        sr = run_changed(messages)
        self.assertEqual([a.line_index for a in sr.actions], [1])
        after = execute_actions(messages, sr.actions)
        self.assertTrue(str(content_at(after, 1)).startswith(CHANGED_POINTER_PREFIX))
        self.assertEqual(content_at(after, 3), BODY + "# added\n")

    def test_identical_content_is_left_to_the_lossless_rule(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY),
        ]
        self.assertEqual(run_changed(messages).actions, [])

    def test_a_b_c_keeps_only_the_last(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY + "b\n"),
            make_read_call(4, "t3"),
            make_read_result(5, "t3", BODY + "c\n"),
        ]
        sr = run_changed(messages)
        self.assertEqual([a.line_index for a in sr.actions], [1, 3])

    def test_a_b_a_spares_the_read_that_still_matches(self):
        """Judged against the final state, not the next read: the first A is
        still an accurate picture of the file, so only B is outdated."""
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY + "b\n"),
            make_read_call(4, "t3"),
            make_read_result(5, "t3", BODY),
        ]
        sr = run_changed(messages)
        self.assertEqual([a.line_index for a in sr.actions], [3])

    def test_different_ranges_are_not_compared(self):
        messages = [
            make_read_call(0, "t1", offset=1, limit=50),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2", offset=51, limit=50),
            make_read_result(3, "t2", BODY + "b\n"),
        ]
        self.assertEqual(run_changed(messages).actions, [])

    def test_whole_file_read_does_not_supersede_a_window(self):
        messages = [
            make_read_call(0, "t1", offset=1, limit=50),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY + "b\n"),
        ]
        self.assertEqual(run_changed(messages).actions, [])

    def test_different_paths_are_not_compared(self):
        messages = [
            make_read_call(0, "t1", "/repo/a.py"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2", "/repo/b.py"),
            make_read_result(3, "t2", BODY + "b\n"),
        ]
        self.assertEqual(run_changed(messages).actions, [])

    def test_floor_and_errors_and_protection(self):
        small = "x" * 1000
        below_floor = [
            make_read_call(0, "t1"), make_read_result(1, "t1", small),
            make_read_call(2, "t2"), make_read_result(3, "t2", small + "b"),
        ]
        self.assertEqual(run_changed(below_floor).actions, [])
        self.assertEqual(
            [a.line_index for a in run_changed(below_floor, {"changed_reread_min_bytes": 512}).actions],
            [1],
        )

        errors = [
            make_read_call(0, "t1"), make_read_result(1, "t1", BODY, is_error=True),
            make_read_call(2, "t2"), make_read_result(3, "t2", BODY + "b\n"),
        ]
        self.assertEqual(run_changed(errors).actions, [])

        protected = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY, extra={"isVisibleInTranscriptOnly": True}),
            make_read_call(2, "t2"), make_read_result(3, "t2", BODY + "b\n"),
        ]
        self.assertEqual(run_changed(protected).actions, [])

    def test_unanswered_later_read_leaves_the_group_alone(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
        ]
        self.assertEqual(run_changed(messages).actions, [])

    def test_pairing_survives(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY + "b\n"),
        ]
        after = execute_actions(messages, run_changed(messages).actions)
        ids = {
            b.get("tool_use_id")
            for _, msg, _ in after
            for b in get_content_blocks(msg)
            if b.get("type") == "tool_result"
        }
        self.assertEqual(ids, {"t1", "t2"})


class TestRepruneGuard(unittest.TestCase):
    """The guard re-prunes the same session on a cycle. A result already
    carrying a winnow pointer must be invisible to both rules."""

    def test_changed_reread_ignores_an_existing_pointer(self):
        """A real pointer is caught by the floor and by G4 long before the guard
        matters, so this uses an oversized one to pin the guard itself."""
        pointer = "[winnow: identical re-read removed - /repo/handler.py] " + "x" * 4000
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", pointer),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY),
        ]
        self.assertEqual(run_changed(messages).actions, [])

    def test_identical_reread_ignores_an_existing_pointer(self):
        pointer = "[winnow: Read /repo/handler.py - 400 lines, 12.0KB]" + "x" * 3000
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", pointer),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", pointer),
        ]
        self.assertEqual(run(messages).actions, [])

    def test_running_changed_reread_twice_is_a_no_op_the_second_time(self):
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY + "b\n"),
        ]
        after = execute_actions(messages, run_changed(messages).actions)
        self.assertEqual(run_changed(after).actions, [])


class TestBothRulesTogether(unittest.TestCase):
    def test_registered_in_aggressive_only(self):
        self.assertIn("changed-reread", PRESCRIPTIONS["aggressive"])
        self.assertNotIn("changed-reread", PRESCRIPTIONS["standard"])
        self.assertNotIn("changed-reread", PRESCRIPTIONS["gentle"])

    def test_ordered_after_identical_and_before_the_rewriters(self):
        order = PRESCRIPTIONS["aggressive"]
        self.assertLess(order.index("identical-reread"), order.index("changed-reread"))
        for name in ("tool-output-trim", "tool-result-age", "stale-reads", "document-dedup"):
            self.assertLess(order.index("changed-reread"), order.index(name))

    def test_a_a_b_leaves_only_b(self):
        """Both rules on one group: identical-reread takes the first A, then
        changed-reread takes the second because B replaced it."""
        messages = [
            make_read_call(0, "t1"),
            make_read_result(1, "t1", BODY),
            make_read_call(2, "t2"),
            make_read_result(3, "t2", BODY),
            make_read_call(4, "t3"),
            make_read_result(5, "t3", BODY + "b\n"),
        ]
        after, _ = run_prescription(
            messages, ["identical-reread", "changed-reread"], {},
            floor_config=FloorConfig.disabled(),
        )
        self.assertTrue(str(content_at(after, 1)).startswith(POINTER_PREFIX))
        self.assertTrue(str(content_at(after, 3)).startswith(CHANGED_POINTER_PREFIX))
        self.assertEqual(content_at(after, 5), BODY + "b\n")

    def test_aggressive_prescription_runs_clean(self):
        messages = [
            make_message(0, {"type": "user", "uuid": "uuid-0", "parentUuid": None,
                             "message": {"role": "user", "content": "read it twice"}}),
            make_read_call(1, "t1"),
            make_read_result(2, "t1", BODY),
            make_read_call(3, "t2"),
            make_read_result(4, "t2", BODY + "b\n"),
            make_message(5, {"type": "assistant", "uuid": "uuid-5", "parentUuid": "uuid-0",
                             "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]}}),
        ]
        after, results = run_prescription(
            messages, PRESCRIPTIONS["aggressive"], {}, floor_config=FloorConfig.disabled(),
        )
        self.assertIn("changed-reread", {r.strategy_name for r in results})
        self.assertTrue(str(content_at(after, 2)).startswith(CHANGED_POINTER_PREFIX))


if __name__ == "__main__":
    unittest.main()
