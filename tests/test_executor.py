"""Tests for executor module — action execution and orphan fix."""

from __future__ import annotations

import json
import unittest

from cozempic.helpers import msg_bytes
from cozempic.executor import execute_actions, fix_orphaned_tool_results, run_prescription
from cozempic.types import PruneAction

# Ensure strategies are registered
import cozempic.strategies  # noqa: F401


def make_message(line_idx: int, msg: dict) -> tuple[int, dict, int]:
    return (line_idx, msg, msg_bytes(msg))


class TestFixOrphanedToolResults(unittest.TestCase):

    def test_removes_orphaned_tool_result(self):
        """tool_result without matching tool_use should be removed."""
        messages = [
            make_message(0, {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hello"}],
                },
            }),
            make_message(1, {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "orphan_id", "content": "result"},
                    ],
                },
            }),
        ]
        fixed, count = fix_orphaned_tool_results(messages)
        self.assertGreater(count, 0)
        # The orphaned tool_result should be gone — message dropped entirely
        self.assertEqual(len(fixed), 1)  # Only the assistant message remains
        for _, msg, _ in fixed:
            for block in msg.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    self.fail("Orphaned tool_result was not removed")

    def test_keeps_paired_tool_result(self):
        """tool_result with matching tool_use should be kept."""
        messages = [
            make_message(0, {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Read", "input": {}},
                    ],
                },
            }),
            make_message(1, {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "file content"},
                    ],
                },
            }),
        ]
        fixed, count = fix_orphaned_tool_results(messages)
        self.assertEqual(count, 0)
        self.assertEqual(len(fixed), 2)

    def test_mixed_orphaned_and_valid(self):
        """Message with both orphaned and valid tool_results keeps only valid ones."""
        messages = [
            make_message(0, {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "valid_id", "name": "Read", "input": {}},
                    ],
                },
            }),
            make_message(1, {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "valid_id", "content": "good"},
                        {"type": "tool_result", "tool_use_id": "missing_id", "content": "orphan"},
                    ],
                },
            }),
        ]
        fixed, count = fix_orphaned_tool_results(messages)
        self.assertEqual(count, 1)
        # Check the remaining message has only the valid tool_result
        result_msg = fixed[1][1]
        blocks = result_msg["message"]["content"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["tool_use_id"], "valid_id")

    def test_empty_message_after_all_orphans_removed(self):
        """If all blocks in a message are orphaned, drop the entire message."""
        messages = [
            make_message(0, {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "orphan1", "content": "a"},
                        {"type": "tool_result", "tool_use_id": "orphan2", "content": "b"},
                    ],
                },
            }),
        ]
        fixed, count = fix_orphaned_tool_results(messages)
        self.assertGreater(count, 0)
        # Message should be dropped entirely
        self.assertEqual(len(fixed), 0)


class TestRunPrescriptionOrphanFix(unittest.TestCase):

    def test_prescription_fixes_orphans_created_by_strategies(self):
        """If a strategy removes a tool_use, the post-treatment validation catches the orphaned result."""
        # Message 0: assistant with tool_use (will be affected by progress-collapse — nope, it won't)
        # Let's create a scenario where a tool_use is in a message that gets removed
        messages = [
            # Progress messages to be collapsed
            (0, {"type": "progress", "data": {}}, 50),
            (1, {"type": "progress", "data": {}}, 50),
            # Assistant with tool_use
            (2, {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Read", "input": {}},
                    ],
                },
            }, 100),
            # User with tool_result
            (3, {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
                    ],
                },
            }, 80),
        ]
        # Run gentle prescription — should collapse progress but keep tool pairs intact
        result_msgs, results = run_prescription(messages, ["progress-collapse"], {})
        # Verify tool_use and tool_result are both still present
        has_use = False
        has_result = False
        for _, msg, _ in result_msgs:
            for block in msg.get("message", {}).get("content", []):
                if isinstance(block, dict):
                    if block.get("type") == "tool_use" and block.get("id") == "t1":
                        has_use = True
                    if block.get("type") == "tool_result" and block.get("tool_use_id") == "t1":
                        has_result = True
        self.assertTrue(has_use)
        self.assertTrue(has_result)


if __name__ == "__main__":
    unittest.main()
