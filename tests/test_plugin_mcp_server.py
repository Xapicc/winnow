"""Tests for the plugin's MCP server (plugin/servers/winnow_mcp.py).

Two halves, split by what they need.

``TestTheMcpInvocation`` reads ``plugin/.mcp.json`` as data and needs nothing
installed. It is the regression test for USAGEFOUNDRY §1.9: the invocation used
to be ``uv run --with cozempic``, which fetched a published release from PyPI, so
the server Claude Code talked to was somebody else's copy of this program rather
than this checkout. A ``--with`` argument reappearing in there is that bug back.

``TestTheServerModule`` and ``TestTheToolsOverTheClient`` import the module and
drive it through fastmcp's own in-memory client, so they skip when fastmcp is
absent — it is the ``mcp`` extra, not a hard dependency, and the harness
container has neither (docs/USAGEFOUNDRY.md §7). Run them with
``uv run --with pytest --with fastmcp --python 3.11 python -m pytest -q
tests/test_plugin_mcp_server.py``.

Written as ``unittest.TestCase`` classes for the reason
tests/test_orchestrator_safe.py gives.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO_ROOT / "plugin"
SERVER_PATH = PLUGIN_DIR / "servers" / "winnow_mcp.py"

TOOL_NAMES = {
    "diagnose_current",
    "estimate_tokens",
    "list_sessions",
    "treat_session",
    "list_strategies",
}

# Imported here rather than inside the tests so that the thread-count assertion
# below measures only what loading the server module starts. fastmcp's own import
# is charged to this line instead.
try:
    from fastmcp import Client  # noqa: F401

    HAS_FASTMCP = True
except ImportError:  # pragma: no cover - depends on how the suite was invoked
    HAS_FASTMCP = False

needs_fastmcp = unittest.skipUnless(
    HAS_FASTMCP, "fastmcp is the `mcp` extra; run with --with fastmcp"
)


def load_server_module():
    """Execute plugin/servers/winnow_mcp.py as a module, by path.

    By path because the plugin directory is not a package and is not on
    ``sys.path`` — which is also how Claude Code runs it: ``python
    <plugin>/servers/winnow_mcp.py``.
    """
    spec = importlib.util.spec_from_file_location("winnow_mcp_under_test", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def temp_session():
    """A throwaway transcript and the session dict the tools expect for it."""
    lines = [
        {"type": "user", "uuid": "u1", "message": {"role": "user", "content": "hi"}},
        {
            "type": "assistant",
            "uuid": "a1",
            "parentUuid": "u1",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "hello"}],
            },
        },
        {"type": "progress", "uuid": "p1", "parentUuid": "a1", "content": "tick"},
        {"type": "progress", "uuid": "p2", "parentUuid": "a1", "content": "tick"},
    ]
    session_id = "f" * 36
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{session_id}.jsonl"
        path.write_text(
            "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
        )
        yield path, {
            "path": path,
            "session_id": session_id,
            "size": path.stat().st_size,
            "lines": len(lines),
            "project": "test-project",
        }


def read_mcp_json() -> dict:
    return json.loads((PLUGIN_DIR / ".mcp.json").read_text(encoding="utf-8"))


def server_entry() -> dict:
    servers = read_mcp_json()["mcpServers"]
    return servers["winnow"]


def substitute_plugin_root(value: str) -> str:
    return value.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN_DIR))


class TestTheMcpInvocation(unittest.TestCase):
    def test_there_is_one_server_and_it_is_named_winnow(self):
        # The key is what Claude Code prefixes every tool name with, so it is
        # user-visible and part of the rename.
        self.assertEqual(list(read_mcp_json()["mcpServers"]), ["winnow"])

    def test_nothing_is_fetched_from_an_index_at_spawn(self):
        entry = server_entry()
        args = entry["args"]
        self.assertNotIn("--with", args)
        self.assertFalse(
            [a for a in args if a.startswith("--with")],
            f"a --with argument fetches a published package instead of this tree: {args}",
        )
        # --frozen is the other half: without it `uv run` may re-resolve the
        # lock against the index before handing over to the interpreter.
        self.assertIn("--frozen", args)

    def test_the_project_is_this_checkout(self):
        args = server_entry()["args"]
        self.assertIn("--project", args)
        project = Path(substitute_plugin_root(args[args.index("--project") + 1]))
        self.assertTrue((project / "pyproject.toml").is_file(), project)
        self.assertEqual(project.resolve(), REPO_ROOT)

    def test_the_project_is_not_passed_as_directory(self):
        # `uv run --directory` chdirs, and the server's find_current_session
        # derives the project slug from the working directory, so a chdir makes
        # every tool report the wrong project. --project keeps cwd alone.
        self.assertNotIn("--directory", server_entry()["args"])

    def test_the_declared_extra_is_the_one_that_provides_fastmcp(self):
        args = server_entry()["args"]
        self.assertIn("--extra", args)
        extra = args[args.index("--extra") + 1]
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f"\n{extra} = [", pyproject, f"no [{extra}] extra declared")
        self.assertIn("fastmcp", pyproject)

    def test_the_script_it_runs_exists(self):
        args = server_entry()["args"]
        script = Path(substitute_plugin_root(args[-1]))
        self.assertTrue(script.is_file(), script)
        self.assertEqual(script.resolve(), SERVER_PATH)

    def test_the_transport_is_stdio(self):
        # The operator decided against containerising this server: it stays a
        # local stdio process spawned by Claude Code. A url, a transport key or
        # a bind address here would be that decision reversed silently.
        entry = server_entry()
        self.assertEqual(entry["command"], "uv")
        for key in ("url", "transport", "type", "host", "port", "headers"):
            self.assertNotIn(key, entry)


class TestTheServerModule(unittest.TestCase):
    def test_the_code_reaches_neither_the_network_nor_a_thread(self):
        # Upstream ran a daemon thread at import that pinged an install counter
        # and self-updated from PyPI with force=True. Both calls went with
        # updater.py, so this asserts nothing is there to be called rather than
        # that a call happened to fail. Over the AST and not the text: the file's
        # comments name all of these in order to say they were removed.
        tree = ast.parse(SERVER_PATH.read_text(encoding="utf-8"))
        identifiers = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                identifiers.add(node.id)
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr)
            elif isinstance(node, ast.FunctionDef):
                identifiers.add(node.name)
            elif isinstance(node, ast.Import):
                identifiers.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                identifiers.add(node.module or "")
                identifiers.update(alias.name for alias in node.names)
        joined = " ".join(sorted(identifiers))
        for banned in (
            "_startup_maintenance",
            "threading",
            "ping_install",
            "maybe_auto_update",
            "updater",
        ):
            self.assertNotIn(banned, joined, f"{banned} is back in {SERVER_PATH.name}")

    def test_the_module_does_not_reference_the_old_package_name(self):
        source = SERVER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("cozempic", source)
        self.assertIn("import winnow.legacy.strategies", source)

    @needs_fastmcp
    def test_it_imports_and_starts_no_thread(self):
        before = threading.active_count()
        module = load_server_module()
        self.assertEqual(
            threading.active_count(),
            before,
            "importing the server started a thread",
        )
        self.assertFalse(hasattr(module, "_startup_maintenance"))

    @needs_fastmcp
    def test_the_server_is_named_winnow(self):
        self.assertEqual(load_server_module().mcp.name, "winnow")

    @needs_fastmcp
    def test_the_undetected_session_message_names_winnow(self):
        # The string a user actually sees when detection fails. It told them to
        # install a program that no longer exists under that name.
        module = load_server_module()
        # `@mcp.tool()` wraps the function in a FunctionTool; `.fn` is the
        # undecorated callable underneath.
        diagnose = getattr(module.diagnose_current, "fn", module.diagnose_current)
        with mock.patch("winnow.legacy.session.find_current_session", return_value=None):
            out = diagnose()
        self.assertIn("winnow", out)
        self.assertNotIn("cozempic", out)


@needs_fastmcp
class TestTheToolsOverTheClient(unittest.TestCase):
    """Drives the server through fastmcp's in-memory client transport.

    ``Client(mcp)`` speaks the real protocol against the server object in this
    process, so the tools are exercised the way Claude Code exercises them
    without spawning anything (USAGEFOUNDRY §6 forbids a long-lived process
    here).
    """

    @classmethod
    def setUpClass(cls):
        cls.module = load_server_module()

    def call(self, name, arguments=None):
        async def run():
            async with Client(self.module.mcp) as client:
                return await client.call_tool(name, arguments or {})

        result = asyncio.run(run())
        return "\n".join(
            block.text for block in result.content if getattr(block, "text", None)
        )

    def test_all_five_tools_are_registered_with_descriptions(self):
        async def run():
            async with Client(self.module.mcp) as client:
                return await client.list_tools()

        tools = asyncio.run(run())
        self.assertEqual({t.name for t in tools}, TOOL_NAMES)
        for tool in tools:
            self.assertTrue(tool.description, f"{tool.name} has no description")

    def test_list_strategies_returns_the_registry(self):
        from winnow.legacy.registry import PRESCRIPTIONS

        out = self.call("list_strategies")
        self.assertIn("Strategies:", out)
        self.assertIn("Prescriptions:", out)
        for name in PRESCRIPTIONS:
            self.assertIn(name, out)

    def test_treat_session_without_a_detected_session_reads_nothing(self):
        with mock.patch("winnow.legacy.session.find_current_session", return_value=None):
            out = self.call("treat_session")
        self.assertIn("Could not detect current session", out)

    def test_an_unknown_prescription_is_refused_without_writing(self):
        with temp_session() as (path, session):
            before = path.read_bytes()
            with mock.patch(
                "winnow.legacy.session.find_current_session", return_value=session
            ):
                out = self.call("treat_session", {"prescription": "homeopathic"})
            self.assertIn("Unknown prescription", out)
            self.assertEqual(path.read_bytes(), before)

    def test_treat_session_defaults_to_a_dry_run_that_changes_no_bytes(self):
        with temp_session() as (path, session):
            before = path.read_bytes()
            with mock.patch(
                "winnow.legacy.session.find_current_session", return_value=session
            ):
                out = self.call("treat_session")
            self.assertIn("DRY RUN", out)
            self.assertIn("Prescription: standard", out)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(
                sorted(p.name for p in path.parent.iterdir()),
                [path.name],
                "a dry run left a file behind",
            )


if __name__ == "__main__":
    unittest.main()
