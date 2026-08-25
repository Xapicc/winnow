"""Finding transcripts, and telling a fork from what it was forked out of.

Shared by the resume harness and the disk-cost measurement, which both have to
walk a corpus and both have to avoid feeding winnow its own output. Nothing here
knows where `~/.claude/projects` is: every root is an argument, so the tests can
build a corpus in `tmp_path` and the production run can point at the real one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# The two lines `rules.POINTER_TEMPLATE` writes, matched as a shape rather than a
# prefix. A source transcript can contain the string "[winnow:" — an operator who
# pasted a pointer into a prompt, or a session that was working on winnow itself,
# which in this repository is not a hypothetical. Requiring the rule id, the byte
# count, the digest and the recover line together makes that far less likely,
# though it does not make it impossible: see `is_fork`.
_POINTER = re.compile(
    r"\[winnow: [^\n\"]{0,120}? result removed, rule [A-Z]\d, [\d,]+ bytes, "
    r"sha256 [0-9a-f]{64}"
)

# Suffixes that are not transcripts even though they end up in the same directory.
_SKIPPED_SUFFIXES = (".bak", ".winnow-tmp")

# Enough of a fork's head to find a pointer in every fork winnow can write, and
# small enough that classifying a 4 MB corpus is not itself the slow step. A
# pointer can legitimately sit past this — guard G1 keeps the last six calls, so
# a session whose only strippable results are late has its first pointer late —
# hence `is_fork` falls back to the whole file rather than trusting the window.
_HEAD_BYTES = 262_144


@dataclass(frozen=True)
class Transcript:
    """One `.jsonl` in a corpus, and whether winnow wrote it."""

    path: Path
    size: int
    is_fork: bool

    @property
    def session_id(self) -> str:
        return self.path.stem


def is_fork(path: Path) -> bool:
    """Whether this transcript carries winnow pointers, i.e. whether winnow wrote it.

    Read the head first and only fall back to the whole file when that misses,
    because the common case in a corpus of accumulated forks is a fork whose first
    pointer is early, and reading 563 transcripts end to end to answer a yes/no
    is a cost with nothing to show for it.

    **This is a heuristic and the false-positive direction is the dangerous one**:
    a *source* transcript misread as a fork is silently dropped from the resume
    test's population, which would quietly shrink a 100-fork guardrail. Where an
    exact answer exists — the resume ledger records every fork it wrote by path —
    prefer it, and `disk.py` does.
    """
    with path.open("rb") as handle:
        head = handle.read(_HEAD_BYTES)
    if _POINTER.search(head.decode("utf-8", "replace")):
        return True
    if len(head) < _HEAD_BYTES:
        return False
    return bool(_POINTER.search(path.read_text("utf-8", errors="replace")))


def transcripts(root: Path) -> list[Transcript]:
    """Every transcript at or under `root`, forks included, sorted by path.

    Accepts both shapes a corpus arrives in: a flat directory of `.jsonl`, and a
    projects directory whose transcripts sit one level down in per-project
    folders. A single `.jsonl` file is also a corpus of one, which is what makes
    a failure reproducible against exactly the session that produced it.
    """
    root = root.expanduser()
    if root.is_file():
        found = [root]
    elif root.is_dir():
        found = [*root.glob("*.jsonl"), *root.glob("*/*.jsonl")]
    else:
        raise FileNotFoundError(f"no corpus at {root}")

    out = []
    for path in sorted(set(found)):
        if path.name.startswith(".") or path.name.endswith(_SKIPPED_SUFFIXES):
            continue
        out.append(Transcript(path, path.stat().st_size, is_fork(path)))
    return out


def sources(root: Path) -> list[Path]:
    """The transcripts in a corpus that winnow did not write.

    The population both harnesses draw from. Forking a fork would measure winnow
    against itself: the second pass has almost nothing left to strip, so it would
    report a resume that succeeded on a file that was barely changed and count it
    towards a guardrail about changed files.
    """
    return [t.path for t in transcripts(root) if not t.is_fork]
