"""What accumulated forks cost on disk, measured rather than estimated.

Milestone 2's definition of done asks for "the disk cost of accumulated forks,
measured over a week rather than estimated". A week cannot happen inside one run,
so this is a script that takes one observation and appends it to a series. Run it
now, run it in a week, and the difference between the two records is the number
the DoD wants. **Nothing here computes that number from one observation**: a
growth rate extrapolated from a single point is an estimate wearing a
measurement's clothes, which is the thing the DoD said not to hand in.

The pooled figure is the honest one. Per-session pairing needs to know which
source a fork came out of, and a fork's session id is a UUIDv5 that cannot be
run backwards, so the pairing comes from the resume harness's ledger where one
exists. Forks with no ledger entry are still counted in the pooled totals and
reported as unpaired, because a fork whose parent is unknown still occupies the
disk.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import corpus
from .resume import Ledger

SERIES_SCHEMA_VERSION = 1

# Below this, a series is one point and a bit rather than a week, and any rate
# taken from it is dominated by whatever happened on the day. The DoD says a
# week; this is the number that decides whether `render` is allowed to state a
# rate at all.
WEEK_SECONDS = 7 * 24 * 3600


def _pairing(ledger_paths: list[Path]) -> dict[str, str]:
    """`{fork path: source path}` from every ledger given, later ones winning."""
    pairs: dict[str, str] = {}
    for path in ledger_paths:
        for attempt in Ledger(path).attempts:
            if attempt.fork_path:
                pairs[attempt.fork_path] = attempt.source_path
    return pairs


def measure(
    root: Path,
    ledger_paths: list[Path] | None = None,
    now: float | None = None,
) -> dict:
    """One observation: what the corpus holds right now, in bytes.

    Deterministic given the same tree and the same `now`, so a test can assert on
    it and two observations a week apart differ only in what actually changed.
    """
    observed_at = time.time() if now is None else now
    pairs = _pairing(list(ledger_paths or []))
    found = corpus.transcripts(root)

    sources = {t.path: t for t in found if not t.is_fork}
    forks = [t for t in found if t.is_fork]

    per_session: dict[str, dict] = {}
    for transcript in sources.values():
        per_session[str(transcript.path)] = {
            "source_session": transcript.session_id,
            "source_bytes": transcript.size,
            "forks": 0,
            "fork_bytes": 0,
        }
    unpaired_bytes = 0
    unpaired = 0
    for transcript in forks:
        source_path = pairs.get(str(transcript.path))
        row = per_session.get(source_path) if source_path else None
        if row is None:
            unpaired += 1
            unpaired_bytes += transcript.size
            continue
        row["forks"] += 1
        row["fork_bytes"] += transcript.size

    source_bytes = sum(t.size for t in sources.values())
    fork_bytes = sum(t.size for t in forks)
    for row in per_session.values():
        row["overhead_share"] = (
            round(row["fork_bytes"] / row["source_bytes"], 6)
            if row["source_bytes"]
            else None
        )

    return {
        "schema_version": SERIES_SCHEMA_VERSION,
        "observed_at": round(observed_at, 3),
        "corpus": str(root),
        "sources": len(sources),
        "forks": len(forks),
        "source_bytes": source_bytes,
        "fork_bytes": fork_bytes,
        "total_bytes": source_bytes + fork_bytes,
        "overhead_share": (
            round(fork_bytes / source_bytes, 6) if source_bytes else None
        ),
        "unpaired_forks": unpaired,
        "unpaired_fork_bytes": unpaired_bytes,
        "per_session": [
            per_session[path] for path in sorted(per_session) if per_session[path]["forks"]
        ],
    }


def append_series(path: Path, record: dict) -> None:
    """Append one observation. The file is the series; the series is the measurement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def read_series(path: Path) -> list[dict]:
    """Every observation in a series, oldest first, refusing a line it cannot read."""
    if not path.exists():
        return []
    out = []
    for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number}: unreadable series line: {exc}") from exc
    return sorted(out, key=lambda r: r.get("observed_at", 0))


def growth(series: list[dict]) -> dict | None:
    """Fork bytes per day between the first and last observation, or `None`.

    `None` whenever there is one observation, or when two share a timestamp. Both
    are cases where the only rate available is division by roughly zero, and a
    large number produced that way is not a small amount of evidence — it is
    none, presented confidently.
    """
    if len(series) < 2:
        return None
    first, last = series[0], series[-1]
    span = last.get("observed_at", 0) - first.get("observed_at", 0)
    if span <= 0:
        return None
    added = last.get("fork_bytes", 0) - first.get("fork_bytes", 0)
    return {
        "span_seconds": round(span, 3),
        "span_days": round(span / 86400, 4),
        "fork_bytes_added": added,
        "fork_bytes_per_day": round(added / (span / 86400), 3),
        "is_a_week": span >= WEEK_SECONDS,
        "observations": len(series),
    }


def _human(size: int) -> str:
    for unit, scale in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if abs(size) >= scale:
            return f"{size / scale:.1f} {unit}"
    return f"{size} B"


def render(record: dict, series: list[dict] | None = None) -> str:
    """The readout: this observation, then what the series does or does not say yet."""
    out: list[str] = []
    add = out.append
    share = record["overhead_share"]
    add(f"corpus            {record['corpus']}")
    add(f"originals         {record['sources']:,} transcripts, "
        f"{_human(record['source_bytes'])}")
    add(f"forks             {record['forks']:,} transcripts, "
        f"{_human(record['fork_bytes'])}")
    add(f"overhead          {'n/a' if share is None else f'{share * 100:.1f}%'} "
        "of the originals")
    add(f"on disk           {_human(record['total_bytes'])} in total")
    if record["unpaired_forks"]:
        add(f"unpaired          {record['unpaired_forks']:,} fork(s), "
            f"{_human(record['unpaired_fork_bytes'])} — counted in the pooled "
            "figure, no source known. Pass --ledger to pair them.")

    if record["per_session"]:
        add("")
        add(f"{'session':<40}{'original':>12}{'forks':>7}{'fork bytes':>14}"
            f"{'overhead':>10}")
        for row in sorted(record["per_session"],
                          key=lambda r: -r["fork_bytes"])[:20]:
            row_share = row["overhead_share"]
            add(f"{row['source_session'][:38]:<40}"
                f"{_human(row['source_bytes']):>12}{row['forks']:>7,}"
                f"{_human(row['fork_bytes']):>14}"
                f"{('n/a' if row_share is None else f'{row_share * 100:.0f}%'):>10}")
        if len(record["per_session"]) > 20:
            add(f"… and {len(record['per_session']) - 20:,} more session(s) with forks")

    add("")
    rate = growth(list(series or []))
    if rate is None:
        add("SERIES: one observation. The definition of done asks for the disk "
            "cost measured over a week, and one point is not a week. Run this "
            "again in seven days against the same series file.")
    elif not rate["is_a_week"]:
        add(f"SERIES: {rate['observations']} observations over "
            f"{rate['span_days']:.2f} days — {_human(rate['fork_bytes_added'])} of "
            f"forks added, {_human(int(rate['fork_bytes_per_day']))}/day. "
            "Short of the week the definition of done asks for; keep going.")
    else:
        add(f"SERIES: {rate['observations']} observations over "
            f"{rate['span_days']:.2f} days — {_human(rate['fork_bytes_added'])} of "
            f"forks added, {_human(int(rate['fork_bytes_per_day']))}/day. "
            "This is the measured week the definition of done asks for.")
    return "\n".join(out)
