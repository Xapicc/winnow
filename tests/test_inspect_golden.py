"""`winnow inspect --json` is pinned, byte for byte, against every session fixture.

Milestone 2 extracts SPEC §4's rule engine out of `inspect.py` so that `plan`
and, later, `fork` classify with the same code rather than a copy of it. The
extraction is only safe if it is output-neutral, and "it still looks right" is
not a check. This file is the check: the golden was generated from the code as
it stood before the extraction, and any drift in a share, a guard count or a
rule attribution fails here rather than silently moving milestone 1's number.

It is also the standing regression pin. Milestone 1's deliverable is a number
(SPEC §9: tier CB reproduces 22.6% pooled within ±3 points), and a change that
moves that number has to be a decision someone took, not a side effect.

Regenerate deliberately, never to make this pass:

    WINNOW_REGEN_GOLDEN=1 uv run --extra dev pytest tests/test_inspect_golden.py

and commit the diff with the reason it moved.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from winnow.inspect import inspect_session
from winnow.report import to_dict

FIXTURES = Path(__file__).parent / "fixtures" / "sessions"
GOLDEN = Path(__file__).parent / "fixtures" / "inspect_golden.json"

# Every tier, because the arithmetic block is tier-dependent and a rule that
# moved between tiers would otherwise show up in only one of them.
TIERS = ("C", "CB", "CBA")


def fixture_names() -> list[str]:
    return sorted(p.name for p in FIXTURES.glob("*.jsonl"))


def payload_for(name: str) -> dict:
    """`to_dict` with the one machine-specific field normalised.

    `path` is absolute and would pin the golden to whoever generated it; the
    fixture name carries the same information and travels.
    """
    report = inspect_session(FIXTURES / name)
    out = {tier: to_dict(report, tier) for tier in TIERS}
    for tier in TIERS:
        out[tier]["path"] = name
    return out


def build_golden() -> dict:
    return {name: payload_for(name) for name in fixture_names()}


def test_inspect_json_has_not_changed():
    if os.environ.get("WINNOW_REGEN_GOLDEN"):
        GOLDEN.write_text(json.dumps(build_golden(), indent=2, sort_keys=True) + "\n")
        pytest.skip(f"regenerated {GOLDEN.name}; review and commit the diff")
    expected = json.loads(GOLDEN.read_text())
    # Compared per fixture rather than as one blob so a failure names the file
    # that moved instead of printing the whole corpus.
    assert sorted(expected) == fixture_names(), (
        "a session fixture was added or removed without regenerating the golden"
    )
    for name in fixture_names():
        assert payload_for(name) == expected[name], f"inspect --json changed for {name}"


def test_the_same_transcript_twice_is_byte_identical():
    """SPEC §10 determinism, at the level milestone 1 promised it."""
    for name in fixture_names():
        first = json.dumps(payload_for(name), indent=2)
        second = json.dumps(payload_for(name), indent=2)
        assert first == second
