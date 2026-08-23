"""Tests for winnow's orchestrator-safe mode (src/winnow/orchestrator_safe.py).

Written as ``unittest.TestCase`` classes on purpose. pytest collects them like
any other test file, and they also run under bare ``python3 -m unittest`` — the
only thing available in the harness container, which has no pip, no venv and no
pytest (docs/USAGEFOUNDRY.md §7). Nothing here depends on a pytest fixture, so
each test that touches the environment isolates its own.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from winnow import cli as winnow_cli
from winnow import orchestrator_safe as safe

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO_ROOT / "plugin"


class TestTheSwitch(unittest.TestCase):
    def test_truthy_values_enable_the_mode(self):
        for raw in ("1", "true", "TRUE", "yes", "on", " 1 "):
            self.assertTrue(safe.is_enabled({safe.ENV_SWITCH: raw}), raw)

    def test_falsey_values_and_absence_leave_it_off(self):
        for raw in ("0", "false", "no", "off", ""):
            self.assertFalse(safe.is_enabled({safe.ENV_SWITCH: raw}), raw)
        self.assertFalse(safe.is_enabled({}))

    def test_an_unrecognised_value_raises_rather_than_reading_as_off(self):
        # The switch decides whether a daemon that can SIGKILL the session may
        # start. A typo must stop the invocation, not silently disarm the mode.
        with self.assertRaises(ValueError) as caught:
            safe.is_enabled({safe.ENV_SWITCH: "yeah"})
        self.assertIn(safe.ENV_SWITCH, str(caught.exception))

    def test_reads_the_process_environment_by_default(self):
        with mock.patch.dict(os.environ, {safe.ENV_SWITCH: "1"}, clear=False):
            self.assertTrue(safe.is_enabled())


class TestEnvironmentOverlay(unittest.TestCase):
    def test_every_switch_usagefoundry_names_is_in_the_overlay(self):
        for name in (
            "WINNOW_NO_GLOBAL_INIT",
            "WINNOW_NO_AUTO_INIT",
            "WINNOW_NO_RECEIPTS",
        ):
            self.assertIn(name, safe.SAFE_ENV)

    def test_the_deleted_switches_are_not_in_the_overlay(self):
        # Setting a variable the tree no longer reads would say the mode is
        # holding something off that nothing does any more (FORK.md §5.1).
        for name in (
            "WINNOW_NO_AUTO_UPDATE",
            "WINNOW_PIN",
            "WINNOW_NO_TELEMETRY",
        ):
            self.assertNotIn(name, safe.SAFE_ENV)

    def test_interactive_is_forced_on_not_off(self):
        # guard.py:1410 — interactive mode only ever makes the guard MORE
        # conservative about reloading. `off` would be the wrong direction.
        self.assertEqual(safe.SAFE_ENV["WINNOW_INTERACTIVE"], "on")

    def test_the_mid_turn_force_line_is_disabled(self):
        # guard.py:1479 — 0 disables the force that overrides the deferral.
        self.assertEqual(safe.SAFE_ENV["WINNOW_FORCE_RELOAD_PCT"], "0")

    def test_every_overlay_entry_carries_a_reason(self):
        self.assertEqual(set(safe.SAFE_ENV), set(safe.SAFE_ENV_REASONS))
        for name, why in safe.SAFE_ENV_REASONS.items():
            self.assertTrue(why.strip(), name)

    def test_overlay_wins_and_nothing_is_removed(self):
        merged = safe.safe_environment({"PATH": "/bin", "WINNOW_NO_RECEIPTS": "0"})
        self.assertEqual(merged["PATH"], "/bin")
        self.assertEqual(
            merged["WINNOW_NO_RECEIPTS"], safe.SAFE_ENV["WINNOW_NO_RECEIPTS"]
        )

    def test_apply_puts_it_in_the_process_environment(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WINNOW_NO_GLOBAL_INIT", None)
            safe.apply_safe_environment()
            self.assertEqual(os.environ["WINNOW_NO_GLOBAL_INIT"], "1")


class TestDataDirectory(unittest.TestCase):
    def test_default_is_a_sibling_of_the_winnow_state_dir(self):
        self.assertEqual(safe.data_dir({}), (Path.home() / ".winnow").resolve())

    def test_honours_the_override(self):
        with _temp_dir() as tmp:
            self.assertEqual(
                safe.data_dir({safe.DATA_DIR_ENV: str(tmp)}), tmp.resolve()
            )

    def test_refuses_a_data_dir_inside_the_bind_mounted_claude_dir(self):
        with _temp_dir() as tmp:
            claude = tmp / "claude"
            claude.mkdir()
            with self.assertRaises(ValueError) as caught:
                safe.data_dir({
                    "CLAUDE_CONFIG_DIR": str(claude),
                    safe.DATA_DIR_ENV: str(claude / "winnow"),
                })
            self.assertIn("bind mount", str(caught.exception))

    def test_refuses_the_claude_dir_itself(self):
        with _temp_dir() as tmp:
            claude = tmp / "claude"
            claude.mkdir()
            with self.assertRaises(ValueError):
                safe.data_dir({
                    "CLAUDE_CONFIG_DIR": str(claude),
                    safe.DATA_DIR_ENV: str(claude),
                })


class TestSubcommandMirror(unittest.TestCase):
    @staticmethod
    def _parser_subcommands() -> set[str]:
        import argparse

        from winnow.legacy.cli import build_parser

        for action in build_parser()._actions:
            if isinstance(action, argparse._SubParsersAction):
                # `safe` is winnow's own group, registered onto this parser so
                # that `winnow --help` lists one program. winnow.cli dispatches
                # it before the inherited main() runs, so it is never an argv
                # the gate classifies and never reaches `winnow safe run --`.
                return set(action.choices) - {"safe"}
        raise AssertionError("the inherited parser has no subparsers any more")

    def test_the_mirror_matches_the_parser(self):
        # If a subcommand is added, this fails and somebody classifies it.
        # The alternative is a new subcommand defaulting to allowed, silently.
        self.assertEqual(set(safe.LEGACY_SUBCOMMANDS), self._parser_subcommands())

    def test_the_mirror_covers_what_cli_subcommands_misses(self):
        # cli._SUBCOMMANDS is missing `nudge`, so a gate mirroring that constant
        # would let through the one command that writes into the bind mount.
        # Asserted rather than worked around, so the day the two are reconciled
        # this stops being a special case and says so.
        from winnow.legacy.cli import _SUBCOMMANDS

        self.assertEqual(self._parser_subcommands() - set(_SUBCOMMANDS), {"nudge"})
        self.assertIn("nudge", safe.LEGACY_SUBCOMMANDS)

    def test_finds_the_subcommand_the_way_the_cli_does(self):
        self.assertEqual(safe.subcommand_of(["treat", "abc", "--execute"]), "treat")
        self.assertEqual(safe.subcommand_of(["--context-window", "1", "list"]), "list")
        self.assertIsNone(safe.subcommand_of(["--version"]))
        self.assertIsNone(safe.subcommand_of([]))


class TestArgvGate(unittest.TestCase):
    def assert_refused(self, argv, *, live_pid=None, naming=None):
        reason = safe.refusal_for(argv, live_pid=live_pid)
        self.assertIsNotNone(reason, f"{argv} should be refused")
        self.assertIn("refused", reason)
        if naming:
            self.assertIn(naming, reason)
        return reason

    def assert_allowed(self, argv, *, live_pid=None):
        self.assertIsNone(
            safe.refusal_for(argv, live_pid=live_pid), f"{argv} should be allowed"
        )

    def test_the_guard_daemon_is_refused(self):
        # Invariant 1: the daemon SIGKILLs the process holding the session.
        for argv in (["guard"], ["guard", "--daemon"], ["guard", "--reload-self"]):
            self.assert_refused(argv, naming="SIGKILL")

    def test_reload_is_refused_and_the_reason_names_resume(self):
        # Invariant 2: --resume belongs to the harness.
        self.assert_refused(["reload", "-rx", "gentle"], naming="--resume")

    def test_commands_that_write_settings_json_are_refused(self):
        self.assert_refused(["init", "--global"], naming="settings.json")
        self.assert_refused(["uninstall"], naming="settings.json")

    def test_the_inherited_checkpoint_is_refused_in_favour_of_winnows(self):
        # The command moved under `team` at the fork (docs/FORK.md §2.1). The
        # refusal has to follow it, or the argv that writes into the bind mount
        # is the one nobody classified.
        self.assert_refused(["team", "checkpoint"], naming="winnow safe checkpoint")

    def test_reading_the_team_checkpoint_back_is_not_refused(self):
        # `team post-compact` only reads, so refusing the whole group would
        # refuse a command that does nothing this mode objects to.
        self.assert_allowed(["team", "post-compact"])

    def test_digest_inject_is_refused_but_reading_the_digest_is_not(self):
        # Invariant 6: MEMORY.md is loaded into every session's context.
        self.assert_refused(["digest", "inject"], naming="MEMORY.md")
        self.assert_allowed(["digest", "show"])

    def test_the_two_commands_that_write_home_paths_in_function_are_refused(self):
        # redirect_home_writes reaches module-level constants only; these two
        # build the path inside the function, so refusal is the only closure.
        self.assert_refused(["nudge"], naming="winnow-metrics")
        self.assert_refused(["remind"], naming="winnow_remind_counter")

    def test_the_watchdog_is_refused_only_when_it_would_signal(self):
        self.assert_refused(["guard-watchdog", "--fix"], naming="SIGTERM")
        self.assert_allowed(["guard-watchdog"])

    def test_refusals_do_not_depend_on_a_live_session(self):
        self.assert_refused(["guard", "--daemon"], live_pid=4242)
        self.assert_refused(["reload"], live_pid=None)

    def test_a_prune_is_allowed_between_cycles_and_refused_during_one(self):
        # USAGEFOUNDRY §2: pruning happens between cycles, on a transcript
        # nobody is holding, or it does not happen.
        self.assert_allowed(["treat", "abc", "--execute"], live_pid=None)
        reason = self.assert_refused(["treat", "abc", "--execute"], live_pid=4242)
        self.assertIn("4242", reason)
        self.assert_refused(["strategy", "stale-reads", "abc", "--execute"], live_pid=1)
        self.assert_refused(["digest", "flush"], live_pid=1)

    def test_a_dry_run_is_allowed_even_during_a_cycle(self):
        self.assert_allowed(["treat", "abc"], live_pid=4242)
        self.assert_allowed(["diagnose", "abc"], live_pid=4242)
        self.assert_allowed(["list"], live_pid=4242)

    def test_an_argv_with_no_subcommand_is_not_refused(self):
        self.assert_allowed(["--version"])


class TestStrategyExclusion(unittest.TestCase):
    def test_metadata_strip_is_the_excluded_strategy(self):
        self.assertIn("metadata-strip", safe.EXCLUDED_STRATEGIES)

    def test_pure_form_removes_it_from_every_prescription(self):
        before = {"gentle": ["progress-collapse", "metadata-strip"]}
        after = safe.prescriptions_without(before)
        self.assertEqual(after, {"gentle": ["progress-collapse"]})
        self.assertEqual(before["gentle"], ["progress-collapse", "metadata-strip"])

    def test_apply_mutates_in_place_so_importers_see_it(self):
        # cli.py:24 and guard.py:203 bind the dict at import time; rebinding the
        # module attribute would leave both holding the original.
        prescriptions = {"gentle": ["progress-collapse", "metadata-strip"]}
        held_elsewhere = prescriptions["gentle"]
        removed = safe.apply_strategy_exclusions(prescriptions)
        self.assertEqual(removed, {"gentle": ["metadata-strip"]})
        self.assertEqual(held_elsewhere, ["progress-collapse"])

    def test_apply_is_idempotent(self):
        prescriptions = {"gentle": ["metadata-strip"]}
        safe.apply_strategy_exclusions(prescriptions)
        self.assertEqual(safe.apply_strategy_exclusions(prescriptions), {})

    def test_the_vendored_registry_ships_it_in_every_prescription(self):
        # The premise of the exclusion. If this stops being true the exclusion
        # is dead code and should go.
        from winnow.legacy.registry import PRESCRIPTIONS

        for name, strategies in PRESCRIPTIONS.items():
            self.assertIn("metadata-strip", strategies, name)

    def test_applying_to_the_real_registry_clears_it_everywhere(self):
        from winnow.legacy import registry

        original = {name: list(v) for name, v in registry.PRESCRIPTIONS.items()}
        try:
            removed = safe.apply_strategy_exclusions()
            self.assertEqual(set(removed), set(original))
            for name, strategies in registry.PRESCRIPTIONS.items():
                self.assertNotIn("metadata-strip", strategies, name)
        finally:
            for name, strategies in original.items():
                registry.PRESCRIPTIONS[name][:] = strategies


class TestHomeStateRedirect(unittest.TestCase):
    def setUp(self):
        # redirect_home_writes rebinds module globals in the vendored tree, and
        # a leak from one test into the next would look like a passing mirror.
        import importlib

        self._saved = {
            (module_name, attribute): getattr(
                importlib.import_module(module_name), attribute
            )
            for module_name, attribute, _ in safe._HOME_WRITE_REDIRECTS
        }

    def tearDown(self):
        import importlib

        for (module_name, attribute), value in self._saved.items():
            setattr(importlib.import_module(module_name), attribute, value)

    def test_every_redirected_constant_still_exists_and_still_points_at_home(self):
        # The premise. If upstream moves one of these the redirect is silently
        # aimed at nothing, so this fails instead.
        import importlib

        for module_name, attribute, _ in safe._HOME_WRITE_REDIRECTS:
            module = importlib.import_module(module_name)
            self.assertTrue(hasattr(module, attribute), f"{module_name}.{attribute}")
            current = Path(getattr(module, attribute))
            self.assertIn(
                Path.home(),
                [current, *current.parents],
                f"{module_name}.{attribute} = {current} is not under $HOME",
            )

    def test_no_redirected_constant_is_imported_by_value_elsewhere(self):
        # Rebinding winnow.legacy.digest.DIGEST_DIR only works because every read
        # goes through that module's global. A `from .digest import DIGEST_DIR`
        # in a second module would keep the old path, silently.
        import re

        source_root = REPO_ROOT / "src" / "winnow" / "legacy"
        for module_name, attribute, _ in safe._HOME_WRITE_REDIRECTS:
            owner = module_name.split(".")[-1]
            pattern = re.compile(
                rf"^from\s+\.\w*\s+import\s+.*\b{re.escape(attribute)}\b", re.M
            )
            for path in sorted(source_root.glob("*.py")):
                if path.stem == owner:
                    continue
                self.assertIsNone(
                    pattern.search(path.read_text(encoding="utf-8")),
                    f"{path.name} imports {attribute} by value",
                )

    def test_the_paths_are_resolved_under_the_target_directory(self):
        targets = safe.home_write_targets(Path("/data/winnow"))
        self.assertEqual(
            targets[("winnow.legacy.helpers", "_SAVINGS_FILE")],
            Path("/data/winnow/winnow-savings.json"),
        )
        for destination in targets.values():
            self.assertIn(Path("/data/winnow"), destination.parents)

    def test_the_digest_file_paths_stay_under_the_redirected_digest_dir(self):
        # digest.py derives DIGEST_FILE from DIGEST_DIR at import time, so both
        # have to move or the pair disagrees.
        targets = safe.home_write_targets(Path("/data/winnow"))
        digest_dir = targets[("winnow.legacy.digest", "DIGEST_DIR")]
        for attribute in ("DIGEST_FILE", "DIGEST_MD_FILE"):
            self.assertEqual(
                targets[("winnow.legacy.digest", attribute)].parent, digest_dir
            )

    def test_applying_it_moves_the_savings_ledger_off_home(self):
        # The ledger is the one redirected constant a plain prune writes to, so
        # it is the one that proves the rebinding reaches a real write rather
        # than only the table. (It replaced the updater's install sentinel as
        # this test's subject when the updater went — FORK.md §5.1.)
        import winnow.legacy.helpers

        with _temp_dir() as tmp:
            applied = safe.redirect_home_writes(tmp)
            self.assertEqual(
                winnow.legacy.helpers._SAVINGS_FILE, tmp / "winnow-savings.json"
            )
            self.assertEqual(
                applied["winnow.legacy.helpers._SAVINGS_FILE"],
                tmp / "winnow-savings.json",
            )
            winnow.legacy.helpers.record_savings(1000)
            self.assertTrue((tmp / "winnow-savings.json").is_file())

    def test_it_creates_the_parents_so_a_write_cannot_fall_back(self):
        with _temp_dir() as tmp:
            for destination in safe.redirect_home_writes(tmp).values():
                self.assertTrue(destination.parent.is_dir(), destination)

    def test_a_vanished_constant_is_an_error_not_a_new_attribute(self):
        import winnow.legacy.helpers

        del winnow.legacy.helpers._SAVINGS_FILE
        with _temp_dir() as tmp:
            with self.assertRaises(AttributeError):
                safe.redirect_home_writes(tmp)

    def test_the_updaters_state_in_home_is_reported_as_a_bypass(self):
        # Still the inherited name: the two updater dotfiles are deleted with
        # the updater rather than renamed with everything else (FORK.md §6.1).
        with _temp_dir() as tmp:
            (tmp / ".cozempic_installed").write_text("1.8.39", encoding="utf-8")
            finding = safe._check_home_state(tmp)
            self.assertFalse(finding.ok)
            self.assertIn(".cozempic_installed", finding.detail)

    def test_renamed_state_in_home_is_reported_as_a_bypass(self):
        with _temp_dir() as tmp:
            (tmp / ".winnow_savings.json").write_text("{}", encoding="utf-8")
            finding = safe._check_home_state(tmp)
            self.assertFalse(finding.ok)
            self.assertIn(".winnow_savings.json", finding.detail)

    def test_the_modes_own_data_directory_is_not_a_bypass(self):
        # ~/.winnow is data_dir(), which redirect_home_writes creates on every
        # `safe run`. Since the rename it also matches the .winnow* prefix this
        # check scans for, so without the exclusion the mode reports itself.
        with _temp_dir() as tmp:
            (tmp / ".winnow").mkdir()
            with mock.patch.object(safe, "data_dir", return_value=tmp / ".winnow"):
                finding = safe._check_home_state(tmp)
        self.assertTrue(finding.ok, finding.detail)

    def test_a_clean_home_is_not_a_violation(self):
        with _temp_dir() as tmp:
            (tmp / ".bashrc").write_text("", encoding="utf-8")
            self.assertTrue(safe._check_home_state(tmp).ok)


class TestPluginDirectory(unittest.TestCase):
    def test_the_vendored_manifest_declares_the_events_we_classified(self):
        manifest = json.loads(
            (PLUGIN_DIR / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            sorted(safe.dropped_hook_events(manifest)),
            ["PostToolUse", "SessionStart", "Stop"],
        )

    def test_an_unclassified_event_is_dropped_not_carried_over(self):
        dropped = safe.dropped_hook_events({"hooks": {"SomethingNew": []}})
        self.assertEqual(dropped, ["SomethingNew"])

    def test_a_manifest_with_no_hooks_object_fails_loudly(self):
        with self.assertRaises(ValueError):
            safe.dropped_hook_events({"hooks": []})

    def test_materialised_directory_contains_no_session_start_hook(self):
        with _temp_dir() as tmp:
            report = safe.materialise_plugin_dir(PLUGIN_DIR, tmp / "plugin")
            hooks = json.loads(
                (tmp / "plugin" / "hooks" / "hooks.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                sorted(hooks["hooks"]), ["PostCompact", "PreCompact"]
            )
            self.assertIn("SessionStart", report["dropped_hook_events"])

    def test_no_hook_command_can_update_start_a_daemon_or_call_the_inherited_cli(self):
        with _temp_dir() as tmp:
            safe.materialise_plugin_dir(PLUGIN_DIR, tmp / "plugin")
            text = (tmp / "plugin" / "hooks" / "hooks.json").read_text(
                encoding="utf-8"
            )
            for forbidden in ("pip install", "uv pip", "uv tool", "guard --daemon",
                              "--reload-self", "winnow guard", "winnow reload",
                              "cozempic"):
                self.assertNotIn(forbidden, text, forbidden)

    def test_the_hooks_carry_the_switch_so_they_cannot_silently_no_op(self):
        with _temp_dir() as tmp:
            safe.materialise_plugin_dir(PLUGIN_DIR, tmp / "plugin")
            text = (tmp / "plugin" / "hooks" / "hooks.json").read_text(
                encoding="utf-8"
            )
            self.assertEqual(text.count(f"{safe.ENV_SWITCH}=1"), 2)

    def test_the_mcp_server_and_the_skills_are_excluded(self):
        with _temp_dir() as tmp:
            report = safe.materialise_plugin_dir(PLUGIN_DIR, tmp / "plugin")
            dest = tmp / "plugin"
            self.assertFalse((dest / ".mcp.json").exists())
            self.assertFalse((dest / "servers").exists())
            self.assertFalse((dest / "skills").exists())
            for name in (".mcp.json", "servers", "skills"):
                self.assertIn(name, report["dropped_paths"])
                self.assertTrue(report["reasons"][name])

    def test_every_path_upstream_ships_is_either_rebuilt_or_named_as_dropped(self):
        # The directory is built from scratch rather than copied and filtered,
        # so a path upstream adds is excluded whether or not anyone classified
        # it. This is what turns that silence into a failure.
        rebuilt = {"hooks", ".claude-plugin"}
        unaccounted = sorted(
            entry.name
            for entry in PLUGIN_DIR.iterdir()
            if entry.name not in rebuilt and entry.name not in safe.DROPPED_PLUGIN_PATHS
        )
        self.assertEqual(unaccounted, [])

    def test_the_manifest_is_winnows_own_and_carries_nothing_of_upstreams(self):
        # UsageFoundry shows `name` and `description` out of this file
        # (plugins.ts:107-114), so a copied manifest presents the directory as
        # cozempic's, under cozempic's version, describing a feature this
        # mode does not have.
        with _temp_dir() as tmp:
            safe.materialise_plugin_dir(PLUGIN_DIR, tmp / "plugin")
            plugin = json.loads(
                (tmp / "plugin" / ".claude-plugin" / "plugin.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(plugin["name"], "winnow")
        self.assertEqual(sorted(plugin), ["description", "name"])
        self.assertNotIn("version", plugin)
        for event in ("PreCompact", "PostCompact"):
            self.assertIn(event, plugin["description"])
        for absent in ("cozempic", "prune", "weight-loss", "1.8.39"):
            self.assertNotIn(absent, plugin["description"], absent)

    def test_the_provenance_is_recorded_next_to_what_was_dropped(self):
        with _temp_dir() as tmp:
            report = safe.materialise_plugin_dir(PLUGIN_DIR, tmp / "plugin")
            written = json.loads(
                (tmp / "plugin" / "winnow-safe-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
        for manifest in (report, written):
            self.assertEqual(manifest["derived_from"]["name"], "cozempic")
            self.assertEqual(
                manifest["derived_from"]["version"],
                safe.UPSTREAM_VERSION,
            )
            self.assertEqual(manifest["derived_from"]["license"], "MIT")
            self.assertIn("Ruya AI", manifest["derived_from"]["copyright"])

    def test_the_recorded_notice_matches_the_licence_it_points_at(self):
        # The attribution has to stay true of the file it names, so this reads
        # the repository's LICENSE rather than trusting the string.
        provenance = safe.upstream_provenance({"license": "MIT"})
        licence = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn(provenance["copyright"], licence)
        self.assertIn("MIT License", licence)

    def test_the_upstream_version_is_read_not_hardcoded(self):
        # A vendored tree moved to another release should say so here without
        # an edit to winnow.
        with _temp_dir() as tmp:
            source = tmp / "source"
            (source / ".claude-plugin").mkdir(parents=True)
            (source / "hooks").mkdir()
            (source / "hooks" / "hooks.json").write_text(
                json.dumps({"hooks": {"SessionStart": []}}), encoding="utf-8"
            )
            (source / ".claude-plugin" / "plugin.json").write_text(
                json.dumps({"name": "cozempic", "version": "9.9.9",
                            "license": "MIT"}),
                encoding="utf-8",
            )
            report = safe.materialise_plugin_dir(source, tmp / "out")
        self.assertEqual(report["derived_from"]["version"], "9.9.9")

    def test_the_default_destination_is_one_the_plugin_scan_can_reach(self):
        # UsageFoundry walks its workspace mounts and skips dot-directories and
        # the names in plugins.ts:48-58. A destination it skips is a directory
        # that can be generated and never enabled, which is what
        # ~/.winnow/plugin was.
        skipped = {"node_modules", ".git", ".uf-worktrees", ".next", "dist",
                   "build", "vendor", "target", "__pycache__"}
        name = safe.PLUGIN_DEST_DIRNAME
        self.assertFalse(name.startswith("."), name)
        self.assertNotIn(name, skipped)
        self.assertEqual(Path(name).name, name)  # one path component, no parents

    def test_the_default_destination_is_not_inside_the_vendored_plugin(self):
        # plugins.ts stops walking at the first plugin it finds ("a plugin does
        # not nest inside another plugin"), and PLUGIN_DIR is already one.
        self.assertFalse((PLUGIN_DIR / safe.PLUGIN_DEST_DIRNAME).exists())
        self.assertNotEqual(safe.PLUGIN_DEST_DIRNAME, PLUGIN_DIR.name)

    def test_the_output_is_deterministic(self):
        # SPEC §10. Also what makes the directory reviewable: a diff between two
        # runs should be empty, so a change in it is a change somebody made.
        with _temp_dir() as tmp:
            command = "PYTHONPATH=/x /usr/bin/python3 -m winnow"
            first = _snapshot(
                safe.materialise_plugin_dir(
                    PLUGIN_DIR, tmp / "a", command=command
                )["dest"]
            )
            second = _snapshot(
                safe.materialise_plugin_dir(
                    PLUGIN_DIR, tmp / "b", command=command
                )["dest"]
            )
            self.assertEqual(first, second)

    def test_it_replaces_an_existing_directory(self):
        with _temp_dir() as tmp:
            dest = tmp / "plugin"
            dest.mkdir()
            (dest / "stale.json").write_text("{}", encoding="utf-8")
            safe.materialise_plugin_dir(PLUGIN_DIR, dest)
            self.assertFalse((dest / "stale.json").exists())

    def test_a_source_without_a_hooks_manifest_fails_loudly(self):
        with _temp_dir() as tmp:
            with self.assertRaises(FileNotFoundError):
                safe.materialise_plugin_dir(tmp / "nothing", tmp / "out")


class TestRedirectedCheckpoint(unittest.TestCase):
    fixture = REPO_ROOT / "tests" / "fixtures" / "sessions" / "team_two_subagents.jsonl"

    def test_the_checkpoint_lands_in_the_directory_it_was_given(self):
        with _temp_dir() as tmp:
            target = tmp / "data"
            written = safe.write_checkpoint(self.fixture, target)
            self.assertEqual(written, target / "team-checkpoint.md")
            self.assertIn("Agent Team Checkpoint", written.read_text(encoding="utf-8"))

    def test_nothing_reaches_the_claude_config_dir(self):
        # The vendored writer falls back to get_claude_dir()/team-checkpoint.md
        # when the directory it is handed does not exist (team.py:1339-1344),
        # and that fallback is the bind-mount write invariant 4 forbids.
        with _temp_dir() as tmp:
            claude = tmp / "claude"
            claude.mkdir()
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(claude)}):
                safe.write_checkpoint(self.fixture, tmp / "does-not-exist-yet")
            self.assertEqual(list(claude.iterdir()), [])
            self.assertTrue((tmp / "does-not-exist-yet" / "team-checkpoint.md").is_file())

    def test_a_session_with_no_team_state_writes_nothing(self):
        with _temp_dir() as tmp:
            solo = tmp / "solo.jsonl"
            solo.write_text(
                json.dumps({
                    "type": "user",
                    "message": {"role": "user", "content": "hello"},
                }) + "\n",
                encoding="utf-8",
            )
            target = tmp / "data"
            self.assertIsNone(safe.write_checkpoint(solo, target))
            self.assertEqual(list(target.iterdir()), [])

    def test_round_trip_through_read_checkpoint(self):
        with _temp_dir() as tmp:
            target = tmp / "data"
            safe.write_checkpoint(self.fixture, target)
            content = safe.read_checkpoint(target)
            self.assertIn("task-aaa-0001", content)

    def test_read_checkpoint_never_falls_back_to_the_global_file(self):
        with _temp_dir() as tmp:
            claude = tmp / "claude"
            claude.mkdir()
            (claude / "team-checkpoint.md").write_text(
                "# another project's checkpoint", encoding="utf-8"
            )
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(claude)}):
                self.assertIsNone(safe.read_checkpoint(tmp / "empty"))


class TestHookPayload(unittest.TestCase):
    def test_a_hook_payload_is_parsed(self):
        payload = safe.hook_payload('{"transcript_path": "/tmp/x.jsonl"}')
        self.assertEqual(payload["transcript_path"], "/tmp/x.jsonl")

    def test_no_stdin_or_garbage_is_not_an_error(self):
        # Run by hand rather than by a hook. The caller falls back to detecting
        # the session from the working directory.
        for raw in ("", "   ", "not json", "[1, 2]", "null"):
            self.assertEqual(safe.hook_payload(raw), {})

    def test_the_payloads_transcript_path_wins(self):
        path = safe.resolve_session_path({"transcript_path": "/tmp/given.jsonl"})
        self.assertEqual(path, Path("/tmp/given.jsonl"))

    def test_an_empty_payload_falls_through_to_detection(self):
        with mock.patch("winnow.legacy.session.find_current_session", return_value=None):
            self.assertIsNone(safe.resolve_session_path({}, cwd="/tmp"))


class TestCheckReport(unittest.TestCase):
    def _by_name(self, findings):
        return {f.name: f for f in findings}

    def test_mode_off_is_reported_as_a_violation(self):
        findings = self._by_name(safe.check({}))
        self.assertFalse(findings["mode"].ok)

    def test_a_garbled_switch_reports_only_that(self):
        findings = safe.check({safe.ENV_SWITCH: "maybe"})
        self.assertEqual([f.name for f in findings], ["mode"])
        self.assertFalse(findings[0].ok)

    def test_the_full_overlay_satisfies_every_env_finding(self):
        env = dict(safe.SAFE_ENV)
        env[safe.ENV_SWITCH] = "1"
        findings = self._by_name(safe.check(env))
        self.assertTrue(findings["mode"].ok)
        for name in safe.SAFE_ENV:
            self.assertTrue(findings[f"env:{name}"].ok, name)

    def test_an_unset_overlay_variable_is_not_a_violation(self):
        # The overlay supplies it to every `winnow safe run`, which is the only
        # path this mode opens to the vendored tree.
        findings = self._by_name(safe.check({safe.ENV_SWITCH: "1"}))
        finding = findings["env:WINNOW_NO_AUTO_INIT"]
        self.assertTrue(finding.ok)
        self.assertIn("overlay supplies", finding.detail)

    def test_a_conflicting_overlay_variable_is_a_violation(self):
        env = {safe.ENV_SWITCH: "1", "WINNOW_NO_AUTO_INIT": "0"}
        finding = self._by_name(safe.check(env))["env:WINNOW_NO_AUTO_INIT"]
        self.assertFalse(finding.ok)
        self.assertIn("conflicts", finding.detail)

    def test_a_correctly_configured_harness_has_nothing_to_report(self):
        # A check that fails in the intended configuration is a check nobody
        # reads. The two findings that read the filesystem are pinned to an
        # empty directory so this asserts the mode's own state, not the box's.
        with _temp_dir() as tmp:
            env = dict(safe.SAFE_ENV)
            env[safe.ENV_SWITCH] = "1"
            env["CLAUDE_CONFIG_DIR"] = str(tmp)
            with mock.patch.object(safe, "_check_home_state",
                                   return_value=safe.Finding("home-state", True, "")), \
                    mock.patch.object(safe, "_check_guard_daemons",
                                      return_value=safe.Finding("guard-daemon", True, "")):
                violations = [f.name for f in safe.check(env) if not f.ok]
            self.assertEqual(violations, [])

    def test_a_digest_in_the_memory_index_is_a_violation(self):
        with _temp_dir() as tmp:
            memory = tmp / "projects" / "-some-project" / "memory"
            memory.mkdir(parents=True)
            (memory / "winnow_digest.md").write_text("rules", encoding="utf-8")
            findings = self._by_name(
                safe.check({safe.ENV_SWITCH: "1", "CLAUDE_CONFIG_DIR": str(tmp)})
            )
            self.assertFalse(findings["digest-memory"].ok)

    def test_winnow_hooks_in_the_bind_mounted_settings_are_a_violation(self):
        with _temp_dir() as tmp:
            (tmp / "settings.json").write_text(
                json.dumps({"hooks": {"SessionStart": ["winnow guard --daemon"]}}),
                encoding="utf-8",
            )
            findings = self._by_name(
                safe.check({safe.ENV_SWITCH: "1", "CLAUDE_CONFIG_DIR": str(tmp)})
            )
            self.assertFalse(findings["global-hooks"].ok)

    def test_a_clean_settings_file_is_not_a_violation(self):
        with _temp_dir() as tmp:
            (tmp / "settings.json").write_text('{"model": "opus"}', encoding="utf-8")
            findings = self._by_name(
                safe.check({safe.ENV_SWITCH: "1", "CLAUDE_CONFIG_DIR": str(tmp)})
            )
            self.assertTrue(findings["global-hooks"].ok)

    def test_a_live_guard_daemon_pidfile_is_a_violation(self):
        # The pidfile path is hardcoded to /tmp (guard.py:2636-2650), so the
        # glob is patched rather than a file planted in a shared directory.
        fake = Path("/tmp/winnow_guard_deadbeef.pid")
        with mock.patch.object(safe.Path, "glob", return_value=[fake]), \
                mock.patch.object(safe.Path, "read_text", return_value=f"{os.getpid()}\n"), \
                mock.patch.object(safe.os, "kill", return_value=None):
            finding = safe._check_guard_daemons()
        self.assertFalse(finding.ok)
        self.assertIn("SIGKILL", finding.detail)

    def test_a_stale_pidfile_is_not_a_violation(self):
        fake = Path("/tmp/winnow_guard_deadbeef.pid")
        with mock.patch.object(safe.Path, "glob", return_value=[fake]), \
                mock.patch.object(safe.Path, "read_text", return_value="999999999\n"), \
                mock.patch.object(safe.os, "kill", side_effect=OSError):
            finding = safe._check_guard_daemons()
        self.assertTrue(finding.ok)
        self.assertIn("stale", finding.detail)


class TestHookLines(unittest.TestCase):
    """One bounded ``winnow: `` line per hook-invoked action, whatever happened.

    The mode is only visible in a run's log through stderr, so a cycle where
    there was nothing to checkpoint has to read differently from one where the
    plugin was never loaded (USAGEFOUNDRY §8.5). Silence cannot do that, and
    silence is what the two commands used to emit on their commonest outcome.
    """

    fixture = REPO_ROOT / "tests" / "fixtures" / "sessions" / "team_two_subagents.jsonl"

    def _the_one_line(self, stderr: str) -> str:
        lines = [line for line in stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, f"expected one line, got: {stderr!r}")
        line = lines[0]
        self.assertTrue(line.startswith("winnow: "), line)
        self.assertLessEqual(
            len(line), winnow_cli._MAX_LINE_CHARS + len("winnow: ")
        )
        return line

    def test_a_checkpoint_that_wrote_something_says_where(self):
        with _temp_dir() as tmp:
            code, out, err = _run_cli(
                ["safe", "checkpoint"],
                stdin=json.dumps({"transcript_path": str(self.fixture)}),
                env={safe.DATA_DIR_ENV: str(tmp / "data")},
            )
            self.assertEqual(code, 0)
            self.assertEqual(out, "")
            self.assertIn("team state checkpointed to", self._the_one_line(err))

    def test_nothing_to_checkpoint_is_reported_rather_than_passed_over(self):
        with _temp_dir() as tmp:
            solo = tmp / "solo.jsonl"
            solo.write_text(
                json.dumps({
                    "type": "user",
                    "message": {"role": "user", "content": "hello"},
                }) + "\n",
                encoding="utf-8",
            )
            code, _out, err = _run_cli(
                ["safe", "checkpoint"],
                stdin=json.dumps({"transcript_path": str(solo)}),
                env={safe.DATA_DIR_ENV: str(tmp / "data")},
            )
            self.assertEqual(code, 2)
            line = self._the_one_line(err)
            self.assertIn("nothing to checkpoint", line)
            self.assertIn("solo.jsonl", line)

    def test_no_session_to_checkpoint_at_all_still_says_one_line(self):
        with _temp_dir() as tmp:
            with mock.patch("winnow.legacy.session.find_current_session",
                            return_value=None):
                code, _out, err = _run_cli(
                    ["safe", "checkpoint"],
                    env={safe.DATA_DIR_ENV: str(tmp / "data")},
                )
            self.assertEqual(code, 2)
            self.assertIn("no session to checkpoint", self._the_one_line(err))

    def test_post_compact_with_nothing_stored_says_so(self):
        with _temp_dir() as tmp:
            code, out, err = _run_cli(
                ["safe", "post-compact"],
                env={safe.DATA_DIR_ENV: str(tmp / "data")},
            )
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("no checkpoint to restore", self._the_one_line(err))

    def test_post_compact_prints_the_checkpoint_and_logs_the_fact(self):
        with _temp_dir() as tmp:
            data = tmp / "data"
            safe.write_checkpoint(self.fixture, data)
            code, out, err = _run_cli(
                ["safe", "post-compact"], env={safe.DATA_DIR_ENV: str(data)}
            )
            self.assertEqual(code, 0)
            self.assertIn("Agent Team Checkpoint", out)
            self.assertIn("checkpoint restored", self._the_one_line(err))

    def test_the_mode_being_off_is_one_prefixed_line_per_action(self):
        for action in (["safe", "checkpoint"], ["safe", "post-compact"]):
            with self.subTest(action=action):
                code, out, err = _run_cli(action, env={safe.ENV_SWITCH: "0"})
                self.assertEqual(code, 3)
                self.assertEqual(out, "")
                self.assertIn(safe.ENV_SWITCH, self._the_one_line(err))

    def test_no_refusal_reason_is_long_enough_to_be_truncated(self):
        # The bound must never cut the citation a refusal carries (§8.3).
        reasons = [
            *safe._REFUSED_SUBCOMMANDS.values(),
            *(reason for _, _, reason in safe._REFUSED_ARGV),
            safe._LIVE_SESSION_REASON,
        ]
        self.assertLessEqual(
            max(len(reason) for reason in reasons), winnow_cli._MAX_LINE_CHARS
        )

    def test_a_message_longer_than_the_bound_is_cut_not_emitted_whole(self):
        # The orchestrator stores each stderr line as a database row, so a path
        # or a session name arriving from outside cannot be trusted for length.
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            winnow_cli._say("x" * 20_000)
        line = stream.getvalue().rstrip("\n")
        self.assertEqual(
            len(line), winnow_cli._MAX_LINE_CHARS + len("winnow: ")
        )
        self.assertTrue(line.endswith("..."))
        self.assertEqual(stream.getvalue().count("\n"), 1)

    def test_the_line_is_one_line_even_when_the_message_is_not(self):
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            winnow_cli._say("first\nsecond\n\nthird")
        self.assertEqual(stream.getvalue(), "winnow: first second third\n")


def _run_cli(argv, *, stdin: str = "", env: dict[str, str] | None = None):
    """Run `winnow …` in this process. Returns (exit code, stdout, stderr).

    The mode is on unless the caller overrides the switch: these are the
    hook-invoked paths, and a hook inside the materialised directory has the
    switch baked into its command.
    """
    overlay = {safe.ENV_SWITCH: "1"}
    overlay.update(env or {})
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, overlay), \
            mock.patch("sys.stdin", io.StringIO(stdin)), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = winnow_cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def _snapshot(root) -> dict[str, str]:
    """Every file under `root`, keyed by relative path."""
    root = Path(root)
    return {
        str(p.relative_to(root)): p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _temp_dir():
    import tempfile

    class _Ctx:
        def __enter__(self):
            self._tmp = tempfile.TemporaryDirectory()
            return Path(self._tmp.name)

        def __exit__(self, *exc):
            self._tmp.cleanup()
            return False

    return _Ctx()


if __name__ == "__main__":
    unittest.main()
