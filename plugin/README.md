# winnow plugin for Claude Code

The whole winnow surface as a Claude Code plugin: prune bloated sessions, checkpoint agent-team state across compaction, and monitor context usage from inside Claude Code.

Enabling this directory starts a background process (the guard daemon, on `SessionStart`) and gives the model tools that rewrite the live transcript. The subset that does neither is what `winnow safe plugin-dir` generates; see `docs/USAGEFOUNDRY.md` §8.5.

## Prerequisites

Python 3.10 or newer, `winnow` on `PATH`, and — for the MCP server only — `uv` on `PATH`.

```bash
git clone https://github.com/Xapicc/winnow
cd winnow
uv tool install .          # or: pip install -e .
```

There is no published package: install from a checkout. The skills and hooks call `winnow` (the hooks fall back to `python3 -m winnow`), so the console script has to be resolvable in the shell Claude Code spawns hooks in.

The MCP server is spawned as `uv run`, so `uv` must be on `PATH` for that one entry point. In this container it is at `/usr/local/bin/uv`. Nothing else in the plugin needs it; without `uv` the hooks and skills still work and only the MCP tools are missing.

## Install

```bash
claude --plugin-dir ./plugin
```

Keep the directory where it is. `.mcp.json` resolves the Python project as `${CLAUDE_PLUGIN_ROOT}/..`, so the plugin has to stay inside the checkout it belongs to; copying `plugin/` somewhere else breaks the server and nothing else.

## Skills

| Skill | Description | Invocation |
|-------|-------------|------------|
| `/winnow:diagnose` | Analyze session bloat, token count, context % | User or Claude (auto) |
| `/winnow:treat [rx]` | Prune session with gentle/standard/aggressive | User only |
| `/winnow:reload [rx]` | Treat + auto-resume in new terminal | User only |
| `/winnow:guard` | Start the background guard daemon | User only |
| `/winnow:winnow-doctor` | Run health checks | User or Claude (auto) |

The doctor skill carries the plugin name twice because the skill itself is named `winnow-doctor`: a skill named `doctor` would shadow Claude Code's built-in `/doctor`.

## Hooks

Automatically registered when the plugin is enabled:

| Event | Action |
|-------|--------|
| `SessionStart` | Inject the behavioural digest, then start the guard daemon in the background |
| `PostToolUse` (Task/TaskCreate/TaskUpdate) | Checkpoint agent-team state |
| `PostToolUse` (any) | Emit a reminder if one is due |
| `PreCompact` | Checkpoint team state and flush the digest before the summariser runs |
| `PostCompact` | Restore team state and re-inject the digest |
| `Stop` | Final checkpoint, digest flush and nudge |

## MCP Tools

The plugin ships an MCP server that gives Claude direct access to winnow:

- `diagnose_current` — full session diagnosis with token counts
- `estimate_tokens` — quick token count + context % check
- `list_sessions` — all sessions with sizes and tokens
- `treat_session` — dry-run or apply a prescription
- `list_strategies` — available strategies and prescriptions

Claude can invoke these automatically when it detects context pressure. `treat_session(execute=True)` rewrites the session file, with a backup and under the same prune lock the CLI uses.

It runs over stdio, spawned by Claude Code from `.mcp.json`:

```
uv run --project ${CLAUDE_PLUGIN_ROOT}/.. --extra mcp --frozen python ${CLAUDE_PLUGIN_ROOT}/servers/winnow_mcp.py
```

`--project` rather than `--directory` because the server derives the project slug from the working directory, so the working directory must not change. `--extra mcp` supplies `fastmcp` from this repository's own optional dependency, and `--frozen` means nothing is resolved or fetched at spawn: the server that runs is this tree, not a release of anything. Importing the module registers the five tools and does nothing else.

## How It Works

- **Skills** call `winnow` CLI commands via Bash
- **Hooks** call `winnow guard`, `winnow team checkpoint`, `winnow digest`, `winnow remind` and `winnow nudge` on lifecycle events
- **MCP server** imports `winnow.legacy` directly, for richer tool integration than a CLI round trip
