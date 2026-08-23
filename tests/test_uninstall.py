"""winnow uninstall — reverse of init (issue #147 FR)."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from winnow.legacy import init as cz_init

# A realistic winnow hook command (carries the schema marker + canonical wrapper
# shape that _is_winnow_command recognizes — a bare "winnow ..." is NOT matched
# by design, so user inline calls are never eaten).
COZ_CMD = ("export WINNOW_NO_AUTO_INIT=1; { winnow checkpoint 2>/dev/null || "
           "python3 -m winnow checkpoint; }  # winnow-hook-schema=2")


def _settings_with(hooks):
    return {"hooks": hooks}


class _Base(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="cz_uninstall_"))
        # redirect HOME and the module-level markers into the temp home
        self._patches = [
            patch.dict(os.environ, {"HOME": str(self.home)}),
            patch.object(cz_init, "_GLOBAL_INIT_MARKER", self.home / ".winnow_global_initialized"),
            patch.object(cz_init, "_REMIND_COUNTER", self.home / ".winnow_remind_counter"),
            patch("winnow.legacy.session.get_claude_dir", return_value=self.home / ".claude"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        import shutil
        shutil.rmtree(self.home, ignore_errors=True)

    def _write_global_settings(self, settings):
        p = self.home / ".claude" / "settings.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(settings))
        return p

    def _write_slash(self, content):
        p = self.home / ".claude" / "commands" / "winnow.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p


class TestRunUninstall(_Base):
    def test_removes_global_hooks_and_slash(self):
        self._write_global_settings(_settings_with({
            "SessionStart": [{"hooks": [{"type": "command", "command": COZ_CMD}]}]
        }))
        slash = self._write_slash("# winnow\nDiagnose and prune bloated Claude Code context\nwinnow treat")
        res = cz_init.run_uninstall("global")
        self.assertTrue(any(h.get("removed") for h in res["hooks"]))
        self.assertTrue(res["slash_command"]["removed"])
        self.assertFalse(slash.exists())
        self.assertTrue((self.home / ".claude" / "commands" / "winnow.md.bak").exists())
        self.assertTrue(res["opt_out_set"])
        self.assertTrue((self.home / ".winnow_global_initialized").exists())  # opt-out marker

    def test_preserves_user_hooks_in_mixed_entry(self):
        self._write_global_settings(_settings_with({
            "SessionStart": [{"hooks": [
                {"type": "command", "command": COZ_CMD},
                {"type": "command", "command": "my-own-tool --do-thing"},
            ]}]
        }))
        cz_init.run_uninstall("global")
        s = json.loads((self.home / ".claude" / "settings.json").read_text())
        cmds = [h["command"] for e in s["hooks"]["SessionStart"] for h in e["hooks"]]
        self.assertIn("my-own-tool --do-thing", cmds)  # user hook kept
        self.assertNotIn(COZ_CMD, cmds)  # winnow hook gone

    def test_removes_a_hook_installed_under_the_inherited_marker(self):
        # The one deliberate carry-over from the fork (FORK.md §6.2): a hook
        # wired by an installed Cozempic is still ours to remove. Without it
        # `uninstall` leaves it in place and `init` appends winnow's beside it,
        # which is two SessionStart hooks and two guard daemons on one session.
        inherited = ("export COZEMPIC_NO_AUTO_INIT=1; { cozempic checkpoint "
                     "2>/dev/null || python3 -m cozempic checkpoint; }  "
                     "# cozempic-hook-schema=v14")
        self._write_global_settings(_settings_with({
            "SessionStart": [{"hooks": [{"type": "command", "command": inherited}]}]
        }))
        cz_init.run_uninstall("global")
        s = json.loads((self.home / ".claude" / "settings.json").read_text())
        cmds = [h["command"] for e in s.get("hooks", {}).get("SessionStart", [])
                for h in e["hooks"]]
        self.assertNotIn(inherited, cmds)

    def test_leaves_foreign_slash_untouched(self):
        slash = self._write_slash("# My own command named winnow\nnothing to do with the tool")
        res = cz_init.run_uninstall("global")
        self.assertTrue(slash.exists())  # not ours -> not removed
        self.assertTrue(res["slash_command"]["skipped_foreign"])

    def test_purge_removes_data_with_marker_kept(self):
        (self.home / ".winnow").mkdir()
        (self.home / ".winnow" / "receipts").mkdir()
        (self.home / ".winnow_savings.json").write_text("{}")
        res = cz_init.run_uninstall("global", purge=True)
        self.assertFalse((self.home / ".winnow").exists())
        self.assertFalse((self.home / ".winnow_savings.json").exists())
        self.assertIn(str(self.home / ".winnow"), res["purged"])
        # opt-out marker still set even on purge (so auto-init doesn't re-fire)
        self.assertTrue((self.home / ".winnow_global_initialized").exists())

    def test_no_purge_keeps_data(self):
        (self.home / ".winnow").mkdir()
        (self.home / ".winnow_savings.json").write_text("{}")
        cz_init.run_uninstall("global", purge=False)
        self.assertTrue((self.home / ".winnow").exists())
        self.assertTrue((self.home / ".winnow_savings.json").exists())

    def test_idempotent_second_run(self):
        self._write_global_settings(_settings_with({
            "SessionStart": [{"hooks": [{"type": "command", "command": COZ_CMD}]}]
        }))
        cz_init.run_uninstall("global")
        res2 = cz_init.run_uninstall("global")  # nothing left
        self.assertFalse(any(h.get("removed") for h in res2["hooks"]))

    def test_removes_remind_counter(self):
        (self.home / ".winnow_remind_counter").write_text("3")
        res = cz_init.run_uninstall("global")
        self.assertTrue(res["remind_counter_removed"])
        self.assertFalse((self.home / ".winnow_remind_counter").exists())


class TestPreviewAndDryRun(_Base):
    def test_preview_reports_without_mutating(self):
        sp = self._write_global_settings(_settings_with({
            "SessionStart": [{"hooks": [{"type": "command", "command": COZ_CMD}]}]
        }))
        before = sp.read_text()
        prev = cz_init.preview_uninstall("global")
        self.assertIn(str(sp), prev["hooks_in"])
        self.assertEqual(sp.read_text(), before)  # untouched

    def test_cmd_dry_run_changes_nothing(self):
        from winnow.legacy import cli

        sp = self._write_global_settings(_settings_with({
            "SessionStart": [{"hooks": [{"type": "command", "command": COZ_CMD}]}]
        }))
        before = sp.read_text()
        cli.cmd_uninstall(argparse.Namespace(project=False, all=False, purge=False, dry_run=True))
        self.assertEqual(sp.read_text(), before)
        self.assertFalse((self.home / ".winnow_global_initialized").exists())  # no opt-out write either


class TestOptOutHolds(_Base):
    def test_opt_out_marker_blocks_refire(self):
        # after uninstall, the global-init marker exists -> auto-init must skip
        cz_init.run_uninstall("global")
        self.assertTrue(cz_init._GLOBAL_INIT_MARKER.exists())


if __name__ == "__main__":
    unittest.main()
