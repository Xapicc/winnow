#!/usr/bin/env python3
"""Disposable. Runs `winnow context --audit` and `thinking_price.py` over one
sweep, in one process, and prints the two side by side.

`05-recommendation.md`'s first two success criteria are paired against a
same-day prototype run rather than against a fixed threshold, and the reason is
in `02-constraints.md`: the two recorded prototype runs, hours apart on the same
day over the same 200-file sweep, qualified 168 sessions and then 160, because
this machine writes transcripts into the corpus it measures. A fixed threshold
would be measuring the corpus. This script exists so that the tool's number and
the prototype's cannot come from different file lists, different filters or
different days.

Three blocks are printed. Each side on its own qualifying set, because that is
what each would report if run alone; and both on the intersection, because that
is the only comparison in which a difference is a difference in method.

usage: paired_sweep.py [n_files]

Writes nothing (§C1), reads `~/.claude/projects` and nothing else.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prefix_floor as pf
import thinking_price as tp

from winnow.context import compose
from winnow.legacy.session import load_messages

ROOT = os.path.expanduser("~/.claude/projects")

# The prototype's own qualifying filter, restated so both sides use one rule:
# no compaction boundary anywhere in the file, and at least five priced
# requests. The first is because `thinking_price.py` walks from record zero and
# would over-report a compacted session by up to 3.6x (§C6) — the tool resets at
# the boundary and does not need the exclusion, but a paired comparison cannot
# give one side sessions the other refuses.
MIN_REQUESTS = 5


def sweep_paths(want: int) -> list[str]:
    """The same even sweep `thinking_price.py` takes, by the same arithmetic."""
    paths = sorted(glob.glob(os.path.join(ROOT, "*", "*.jsonl")))
    return paths[:: max(1, len(paths) // want)][:want]


def prototype(path: str) -> dict | None:
    """`thinking_price.py`'s per-session numbers, via its own functions."""
    try:
        with open(path, "rb") as handle:
            records = [json.loads(line) for line in handle if line.strip()]
    except (OSError, ValueError):
        return None
    if any(r.get("subtype") == "compact_boundary" for r in records):
        return None
    responses = tp.responses(records)
    if len(responses) < MIN_REQUESTS:
        return None
    retained, last_index = 0.0, responses[-1]["idx"]
    for entry in responses:
        _, _, residual = tp.price(entry)
        if entry["out_tok"] <= 0:
            continue
        if entry["idx"] < last_index:
            retained += max(0.0, residual)
    visible_first = sum(pf.line_tokens(r) for r in records[: responses[0]["idx"]])
    visible_last = sum(pf.line_tokens(r) for r in records[:last_index])
    prefix = responses[0]["ctx"] - visible_first
    window = responses[-1]["ctx"]
    if window <= 0 or prefix <= 0:
        return None
    return {
        "window": window,
        "unattributed": window - visible_last - prefix - retained,
        "prefix": prefix,
        "retained": retained,
    }


def tool(path: str) -> dict | None:
    """`winnow context --audit`'s per-session numbers, via the tool's own code."""
    target = Path(path)
    try:
        records = [record for _, record, _ in load_messages(target)]
    except OSError:
        return None
    if any(r.get("subtype") == "compact_boundary" for r in records):
        return None
    composition = compose(target, records, depth=1)
    if composition.window is None or composition.requests < MIN_REQUESTS:
        return None
    node = {n.label: n.tokens for n in composition.nodes}
    residual = next((n.tokens for n in composition.nodes if n.kind == "residual"), 0)
    return {
        "window": composition.window,
        "unattributed": residual,
        "prefix": node.get("prefix", 0),
        "retained": node.get("retained reasoning", 0),
    }


def quantile(values: list[float], q: float) -> float:
    """`thinking_price.py`'s `pct`, restated so both sides use one definition."""
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


def report(label: str, rows: list[dict]) -> None:
    if not rows:
        print(f"  {label:<12s} no qualifying session")
        return
    signed = [100 * r["unattributed"] / r["window"] for r in rows]
    absolute = [abs(v) for v in signed]
    within = sum(1 for r in rows
                 if abs(r["unattributed"]) <= 0.15 * r["window"])
    negative = sum(1 for r in rows if r["unattributed"] < 0)
    prefix = [100 * r["prefix"] / r["window"] for r in rows]
    retained = [100 * r["retained"] / r["window"] for r in rows]
    print(f"  {label:<12s} n={len(rows):<4d}"
          f"  median={quantile(signed, .5):6.1f}%"
          f"  |median|={quantile(absolute, .5):5.1f}%"
          f"  p25={quantile(signed, .25):6.1f}%  p75={quantile(signed, .75):6.1f}%"
          f"  within +/-15%={within}/{len(rows)} ({100 * within / len(rows):.1f}%)"
          f"  negative={negative}"
          f"  prefix median={quantile(prefix, .5):.1f}%"
          f"  retained median={quantile(retained, .5):.1f}%")


def main() -> None:
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    paths = sweep_paths(want)
    proto = {p: prototype(p) for p in paths}
    tooled = {p: tool(p) for p in paths}
    both = [p for p in paths if proto[p] and tooled[p]]

    print(f"sweep: {len(paths)} files, evenly spaced over {ROOT}")
    print(f"qualifying: prototype {sum(1 for v in proto.values() if v)}, "
          f"tool {sum(1 for v in tooled.values() if v)}, both {len(both)}\n")
    print("share of the exact window left unattributed")
    report("prototype", [v for v in proto.values() if v])
    report("tool", [v for v in tooled.values() if v])
    print("\npaired, on the sessions both qualify")
    report("prototype", [proto[p] for p in both])
    report("tool", [tooled[p] for p in both])


if __name__ == "__main__":
    main()
