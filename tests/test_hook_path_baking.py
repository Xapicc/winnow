"""#158: bake an absolute winnow interpreter into the hook fallback so the
guard daemon resolves even when bare `winnow` isn't on the hook's PATH."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from winnow.legacy import init as cz


class TestResolveAndBake(unittest.TestCase):
    def test_bake_replaces_python3_fallback_with_abs(self):
        hooks = {"SessionStart": [{"hooks": [
            {"type": "command",
             "command": "{ winnow guard 2>/dev/null || python3 -m winnow guard 2>/dev/null; } # winnow-hook-schema=v13"},
        ]}]}
        out = cz._bake_winnow_path(hooks, "/opt/uvtools/winnow/bin/python3.12")
        cmd = out["SessionStart"][0]["hooks"][0]["command"]
        self.assertIn("/opt/uvtools/winnow/bin/python3.12 -m winnow guard", cmd)
        self.assertNotIn("|| python3 -m winnow", cmd)   # bare python3 fallback gone
        self.assertIn("winnow guard 2>/dev/null ||", cmd)  # on-PATH primary kept first
        self.assertIn("winnow-hook-schema=v13", cmd)       # marker untouched

    def test_bake_does_not_mutate_input(self):
        hooks = {"E": [{"hooks": [{"command": "python3 -m winnow x"}]}]}
        cz._bake_winnow_path(hooks, "/abs/py")
        self.assertEqual(hooks["E"][0]["hooks"][0]["command"], "python3 -m winnow x")  # original intact

    def test_bake_quotes_paths_with_spaces(self):
        out = cz._bake_winnow_path({"E": [{"hooks": [{"command": "python3 -m winnow x"}]}]},
                                     "/Users/a b/py")
        self.assertIn("'/Users/a b/py' -m winnow x", out["E"][0]["hooks"][0]["command"])

    def test_bake_tolerates_malformed_entries(self):
        # non-dict entries / missing command must not crash
        cz._bake_winnow_path({"E": [{"hooks": ["nope", {"x": 1}]}, "bad"]}, "/p")

    def test_resolve_uses_sys_executable_unmodified(self):
        # must NOT realpath — a uv-tool venv python must be returned as-is so its
        # site-packages (which has winnow) is used by `-m winnow`.
        p = "/Users/x/.local/share/uv/tools/winnow/bin/python3.12"
        with patch("winnow.legacy.init.sys.executable", p):
            got, _ = cz._resolve_winnow_python()
            self.assertEqual(got, p)

    def test_resolve_flags_uvx_ephemeral(self):
        for p in ("/Users/x/.cache/uv/environments-v2/abc/bin/python3",
                  "/private/var/folders/xx/T/uvx-tmp/bin/python"):
            with patch("winnow.legacy.init.sys.executable", p):
                _, eph = cz._resolve_winnow_python()
                self.assertTrue(eph, f"{p} should be ephemeral")

    def test_resolve_degrades_when_sys_executable_empty(self):
        # exotic frozen interpreters can have an empty sys.executable — must NOT
        # return "" (which would bake an empty `'' -m winnow` no-op command).
        with patch("winnow.legacy.init.sys.executable", ""), \
                patch("winnow.legacy.init.shutil.which", return_value="/usr/bin/python3"):
            got, _ = cz._resolve_winnow_python()
            self.assertEqual(got, "/usr/bin/python3")

    def test_bake_skips_when_abs_python_empty(self):
        hooks = {"E": [{"hooks": [{"command": "python3 -m winnow x"}]}]}
        out = cz._bake_winnow_path(hooks, "")
        self.assertEqual(out["E"][0]["hooks"][0]["command"], "python3 -m winnow x")  # untouched

    def test_resolve_flags_persistent_not_ephemeral(self):
        for p in ("/Users/x/.local/share/uv/tools/winnow/bin/python3.12",
                  "/opt/homebrew/bin/python3", "/usr/local/bin/python3.11"):
            with patch("winnow.legacy.init.sys.executable", p):
                _, eph = cz._resolve_winnow_python()
                self.assertFalse(eph, f"{p} should be persistent")


class TestWireHooksBakes(unittest.TestCase):
    def test_wire_hooks_writes_absolute_fallback_and_reports_ephemeral(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("winnow.legacy.init._resolve_winnow_python",
                       return_value=("/abs/uvtool/bin/python3.12", False)):
                res = cz.wire_hooks(tmp)
            self.assertFalse(res["ephemeral"])
            self.assertEqual(res["winnow_python"], "/abs/uvtool/bin/python3.12")
            settings = json.loads((Path(tmp) / ".claude" / "settings.json").read_text())
            cmds = [h["command"] for entries in settings["hooks"].values()
                    for e in entries for h in e["hooks"]]
            # at least one hook now carries the absolute interpreter fallback
            self.assertTrue(any("/abs/uvtool/bin/python3.12 -m winnow" in c for c in cmds))
            # and none still falls back to bare python3
            self.assertFalse(any("|| python3 -m winnow" in c for c in cmds))

    def test_wire_hooks_propagates_ephemeral_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("winnow.legacy.init._resolve_winnow_python",
                       return_value=("/tmp/uvx/bin/python", True)):
                res = cz.wire_hooks(tmp)
            self.assertTrue(res["ephemeral"])


if __name__ == "__main__":
    unittest.main()
