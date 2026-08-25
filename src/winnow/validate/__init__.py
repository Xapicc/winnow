"""Harnesses for the three milestone 2 criteria that code cannot check.

MILESTONES milestone 2 has seven acceptance criteria the test suite settles and
three it cannot: the **100-fork resume test**, which needs real transcripts and
real model calls; the **200-sample blind label**, which needs a human reading
real turns; and the **week of accumulated disk cost**, which needs a week. This
package is what the session running those three has to run, and nothing more.

Two properties are load-bearing and are held by every module here:

**Nothing in this package is imported by winnow's own commands.** `inspect`,
`plan`, `fork` and `recover` do not know it exists. A measurement that could
change the thing it measures is not a measurement, and SPEC §3 keeps winnow out
of the spawn path for the same reason — `resume.py` shells out to `claude`, so
it lives here rather than behind a `winnow` subcommand.

**Nothing here reads `~/.claude/projects/` or spawns `claude` at import time,
and the tests exercise none of it.** Every path and every corpus root is an
argument. That is what lets `tests/test_validate_*.py` run in a container with
no transcripts and no credentials, and it is why a green suite still does not
mean these three criteria passed. docs/MILESTONE-2-VALIDATION.md is the
procedure; this is the code it drives.
"""
