"""What the intake filter has actually saved on this install, priced from its own ledger.

README and [COZEMPIC.md](../../docs/COZEMPIC.md) §3.5 report the filter as a **corpus
simulation** — 8.21% reached, $246.14 netted, +3.76% of the bill, over 175 historical
sessions the filter never touched. That is a projection. This answers the other
question, and only that one: since the proxy was switched on, what did it do *here*.

**The arithmetic that decides whether this number is right.** The filter is stateless
by design (`filter.py`): it recomputes its decision from each request body, so it
re-drops the same tool result on every later request that still carries it. Summing
`bytes_dropped` over ledger lines therefore counts one removal **once per surviving
request**. On this operator's live ledger that is 889 drop events and 5,484,366 bytes
against 34 distinct results and 196,374 unique bytes — a **27.9× overstatement**. It
is the units error COZEMPIC §3.4 records for the pruner, arriving by a new route: a
per-turn quantity summed as though it were a one-time one.

A unique removed result pays the avoided write **once**. Its repeats on later requests
are not further savings — they *are* the `0.1·D·T` read term, and belong at 0.1, not
1.0. So everything here is keyed on `tool_use_id` and counted once, and a result that
appears as `deferred` on one request and `dropped` on the next is one removal, not two.

**The cost model is COZEMPIC §3.5's, taken verbatim and not re-derived:**

    baseline   W·D (one cache write) + 0.1·D·T (a read on every later turn)
    filtered   1.0·D (one uncached turn, then gone)
    saving     1.0·D + 0.1·D·T,  no break-even term

`W` is 2.0 for a 1h write and 1.25 for a 5m one, and it is **read** — from the TTL the
ledger recorded as in force on the request, or failing that from the write class the
joined session actually paid. COZEMPIC §3.1 is the record of what assuming the 1.25×
documentation figure costs: an invalidation understated by about 40%.

**The figure is modelled, not billed.** The bytes were never sent, so no line on any
invoice corresponds to them. `D` is measured (the ledger), `T` is measured (the
transcripts) and the price is published; the counterfactual — that those bytes would
have been cache-written and then read every turn until the context was compacted — is
the model. This project exists because other tools report bytes removed and call that
a saving, so the command says this in its own output and not only here.
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from .inspect import Usage, _inner, _input_size, _read_usage, _result_size
from .legacy.session import load_messages

DEFAULT_LEDGER = Path.home() / ".winnow" / "filter.jsonl"
DEFAULT_PROJECTS = Path.home() / ".claude" / "projects"

# Published list price, US dollars per million tokens, as (base input, output).
# Source: https://platform.claude.com/docs/en/about-claude/pricing, read 2026-08-24.
# Data, in one place, deliberately: a price that is inlined at the point of use is a
# price nobody re-checks. A model id absent from this table is counted and excluded
# from the dollar total, never priced at a neighbour's rate — a KPI that guesses a
# price is a KPI that cannot be reconciled against a bill.
PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.0, 50.0),
    "claude-mythos-5": (10.0, 50.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-opus-4-5": (5.0, 25.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-opus-4-0": (15.0, 75.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4-0": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-3-5-haiku": (0.8, 4.0),
    "claude-3-haiku": (0.25, 1.25),
}

# Multipliers on the base input price, from the same page and the same date.
WRITE_1H = 2.0
WRITE_5M = 1.25
CACHE_READ = 0.1

# SPEC §6's estimate, and the fallback when a session gives nothing to calibrate
# against. COZEMPIC §3.4 lists it as one of three reasons the 3.27% figure is an
# optimistic bound, so where the join affords a measurement it is preferred.
DEFAULT_BYTES_PER_TOKEN = 4.0

# A dated alias prices identically to its undated one; the suffix is a release date,
# not a tier. Stripping it keeps the table above at one row per model.
_DATE_SUFFIX = re.compile(r"-\d{8}$")

_TTL_MULTIPLIER = {"ephemeral_1h": WRITE_1H, "ephemeral_5m": WRITE_5M,
                   "1h": WRITE_1H, "5m": WRITE_5M}


def normalise_model(model: str | None) -> str | None:
    if not isinstance(model, str) or not model:
        return None
    return _DATE_SUFFIX.sub("", model)


# ─── The ledger ──────────────────────────────────────────────────────────────


@dataclass
class Removal:
    """One tool result the filter removed, counted once however often it recurs."""

    tool: str
    rule: str
    bytes: int
    request_id: str | None
    tool_use_id: str | None
    model: str | None
    ttl: str | None
    first_kind: str  # "deferred" or "dropped", whichever the result appeared as first
    repeats: int = 1  # ledger entries collapsed into this one; the 27.9×, per result


@dataclass
class LedgerRead:
    """What one ledger file contained, before any join or pricing."""

    path: Path
    lines: int = 0
    parse_errors: int = 0
    drop_events: int = 0
    bytes_summed: int = 0  # the naive sum, kept only so the readout can show the gap
    legacy_lines: int = 0  # lines predating `tool_use_id`, de-duped on the fallback
    lines_without_model: int = 0
    lines_without_ttl: int = 0
    removals: list[Removal] = field(default_factory=list)

    @property
    def unique_bytes(self) -> int:
        return sum(r.bytes for r in self.removals)


def read_ledger(path: Path) -> LedgerRead:
    """Collapse the ledger to unique removals, keyed on `tool_use_id`.

    Two de-dupe keys, and the split matters. An entry carrying a `tool_use_id` is
    exact. An entry predating that field falls back to `(tool, rule, bytes)`, which
    can merge two genuinely distinct results that happen to agree on all three — so
    the fallback is only ever consulted for entries that need it, and a triple already
    claimed by an id-bearing entry blocks a later id-less one from counting again.
    Both errors the fallback can make are undercounts, which is the direction a
    savings claim should err in.
    """
    read = LedgerRead(path=path)
    seen_ids: set[str] = set()
    seen_triples: set[tuple[str, str, int]] = set()
    claimed_triples: set[tuple[str, str, int]] = set()
    by_id: dict[str, Removal] = {}
    by_triple: dict[tuple[str, str, int], Removal] = {}

    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            read.lines += 1
            try:
                line = json.loads(raw)
            except json.JSONDecodeError:
                read.parse_errors += 1
                continue
            if not isinstance(line, dict):
                read.parse_errors += 1
                continue

            model = normalise_model(line.get("model"))
            ttl = line.get("cache_ttl") if isinstance(line.get("cache_ttl"), str) else None
            request_id = line.get("request_id") if isinstance(line.get("request_id"), str) else None
            if model is None:
                read.lines_without_model += 1
            if ttl is None:
                read.lines_without_ttl += 1
            legacy = False

            for kind in ("deferred", "dropped"):
                entries = line.get(kind)
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    size = entry.get("bytes")
                    if not isinstance(size, int) or isinstance(size, bool):
                        continue
                    tool = entry.get("tool") if isinstance(entry.get("tool"), str) else ""
                    rule = entry.get("rule") if isinstance(entry.get("rule"), str) else ""
                    use_id = entry.get("tool_use_id")
                    use_id = use_id if isinstance(use_id, str) and use_id else None
                    if kind == "dropped":
                        read.drop_events += 1
                        read.bytes_summed += size
                    if use_id is None:
                        legacy = True

                    triple = (tool, rule, size)
                    if use_id is not None:
                        if use_id in seen_ids:
                            by_id[use_id].repeats += 1
                            continue
                        seen_ids.add(use_id)
                        claimed_triples.add(triple)
                    else:
                        if triple in seen_triples:
                            by_triple[triple].repeats += 1
                            continue
                        if triple in claimed_triples:
                            continue  # already counted under its id; see the docstring
                        seen_triples.add(triple)

                    removal = Removal(
                        tool=tool, rule=rule, bytes=size, request_id=request_id,
                        tool_use_id=use_id, model=model, ttl=ttl, first_kind=kind,
                    )
                    read.removals.append(removal)
                    if use_id is not None:
                        by_id[use_id] = removal
                    else:
                        by_triple[triple] = removal

            if legacy:
                read.legacy_lines += 1
    return read


def ledger_dropped_bytes(path: Path) -> dict[str, int]:
    """`request_id → bytes_dropped`, for the calibration's prefix correction.

    The transcript still holds every byte the API never saw (COZEMPIC §3.5), so a
    request's on-disk prefix overstates the one that was actually cached by exactly
    what the filter took off it.
    """
    dropped: dict[str, int] = {}
    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                line = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(line, dict):
                continue
            request_id = line.get("request_id")
            size = line.get("bytes_dropped")
            if isinstance(request_id, str) and isinstance(size, int):
                dropped[request_id] = dropped.get(request_id, 0) + size
    return dropped


# ─── The join, against Claude Code's own transcripts ─────────────────────────


@dataclass
class RequestFacts:
    """What the transcript knows about one filtered request."""

    session_id: str
    turn_index: int  # 0-based position among billable assistant turns
    turns_after: int  # T, capped at the next compact boundary
    model: str | None
    prefix_bytes: int
    cache_read: int


@dataclass
class SessionFacts:
    path: Path
    session_id: str
    turns: int = 0
    usage: Usage = field(default_factory=Usage)
    usage_by_model: dict[str, Usage] = field(default_factory=dict)
    bytes_per_token: float = DEFAULT_BYTES_PER_TOKEN
    calibrated: bool = False
    calibration_points: int = 0


def _record_content_bytes(record: dict) -> int:
    """Message-content bytes on one record, measured exactly as `inspect` measures
    them, so a prefix here and an `S` there are the same quantity."""
    content = _inner(record).get("content")
    if isinstance(content, str):
        return len(content)
    if not isinstance(content, list):
        return 0
    total = 0
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "tool_result":
            total += _result_size(block.get("content"))
        elif btype == "tool_use":
            total += _input_size(block.get("input"))
        elif btype == "text":
            text = block.get("text")
            total += len(text) if isinstance(text, str) else 0
        elif btype == "thinking":
            thinking = block.get("thinking")
            total += len(thinking) if isinstance(thinking, str) else 0
    return total


def find_transcripts(projects_dir: Path, wanted: set[str]) -> dict[str, Path]:
    """`request_id → transcript path`, by one streaming sweep of every transcript.

    Cheap on purpose: a line without `requestId` is never parsed, and the id is pulled
    out with a regex rather than a JSON decode. On this install that is 650 files for
    six hits, and doing it any other way means reading 1.1 GB properly.
    """
    found: dict[str, Path] = {}
    if not projects_dir.is_dir():
        return found
    pattern = re.compile(r'"requestId"\s*:\s*"([^"]+)"')
    for path in sorted(projects_dir.glob("*/*.jsonl")):
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                for raw in handle:
                    if "requestId" not in raw:
                        continue
                    match = pattern.search(raw)
                    if match and match.group(1) in wanted and match.group(1) not in found:
                        found[match.group(1)] = path
        except OSError:
            continue
    return found


def read_session(path: Path, wanted: set[str], dropped: dict[str, int]) -> tuple[
    SessionFacts, dict[str, RequestFacts]
]:
    """One pass over a transcript: usage, turn positions, and the prefix at each hit."""
    facts = SessionFacts(path=path, session_id=path.stem)
    hits: dict[str, tuple[int, int, str | None, int]] = {}  # id → (turn, prefix, model, read)
    boundaries: list[int] = []  # billable turns seen when each compact boundary passed
    cumulative = 0

    for _line_index, record, _raw in load_messages(path):
        if record.get("_parse_error"):
            continue
        rtype = record.get("type", "?")
        if record.get("subtype") == "compact_boundary" or rtype == "compact_boundary":
            boundaries.append(facts.turns)

        if rtype == "assistant":
            inner = _inner(record)
            model = normalise_model(inner.get("model"))
            usage = inner.get("usage")
            billable = inner.get("model") != "<synthetic>" and isinstance(usage, dict)
            if billable:
                request_id = record.get("requestId")
                if isinstance(request_id, str) and request_id in wanted:
                    cache_read = usage.get("cache_read_input_tokens")
                    cache_read = cache_read if isinstance(cache_read, int) else 0
                    # The prefix the API actually cached is the on-disk one minus what
                    # the filter took off this very request.
                    hits[request_id] = (
                        facts.turns,
                        cumulative - dropped.get(request_id, 0),
                        model,
                        cache_read,
                    )
                _read_usage(record, facts.usage)
                if model:
                    _read_usage(record, facts.usage_by_model.setdefault(model, Usage()))
                facts.turns += 1
        cumulative += _record_content_bytes(record)

    facts.bytes_per_token, facts.calibration_points = _calibrate(
        [(prefix, read) for _turn, prefix, _model, read in hits.values()]
    )
    facts.calibrated = facts.calibration_points > 0

    resolved: dict[str, RequestFacts] = {}
    for request_id, (turn, prefix, model, cache_read) in hits.items():
        horizon = next((b for b in boundaries if b > turn), facts.turns)
        resolved[request_id] = RequestFacts(
            session_id=facts.session_id,
            turn_index=turn,
            turns_after=max(0, horizon - turn - 1),
            model=model,
            prefix_bytes=prefix,
            cache_read=cache_read,
        )
    return facts, resolved


def _calibrate(points: list[tuple[int, int]]) -> tuple[float, int]:
    """Marginal bytes per token, by least squares over (prefix bytes, cache read).

    A plain `bytes / tokens` ratio is the obvious thing and it is wrong, optimistically
    so: `cache_read_input_tokens` covers the system prompt and the tool schemas as well
    as the messages, while the bytes here are message content only. The ratio would
    therefore understate bytes-per-token and inflate every `D`. The *intercept* of a
    fit is that fixed overhead, so the *slope* is the marginal rate — which is the one
    `D` needs, because a removed tool result is marginal bytes and nothing else.

    Returns `(bytes_per_token, points_used)`; `points_used` is 0 when the sample could
    not support a fit and SPEC §6's ÷4 stands.
    """
    usable = [(float(b), float(t)) for b, t in points if b > 0 and t > 0]
    xs = {b for b, _ in usable}
    if len(usable) < 3 or len(xs) < 3:
        return DEFAULT_BYTES_PER_TOKEN, 0
    mean_x = sum(b for b, _ in usable) / len(usable)
    mean_y = sum(t for _, t in usable) / len(usable)
    variance = sum((b - mean_x) ** 2 for b, _ in usable)
    if variance <= 0:
        return DEFAULT_BYTES_PER_TOKEN, 0
    slope = sum((b - mean_x) * (t - mean_y) for b, t in usable) / variance
    if slope <= 0:
        return DEFAULT_BYTES_PER_TOKEN, 0
    bytes_per_token = 1.0 / slope
    # A fit that lands outside any plausible tokenizer is a fit of noise, not of text.
    if not 1.5 <= bytes_per_token <= 12.0:
        return DEFAULT_BYTES_PER_TOKEN, 0
    return bytes_per_token, len(usable)


# ─── Pricing ─────────────────────────────────────────────────────────────────


@dataclass
class Priced:
    """One unique removal, joined and priced. `excluded` is why it is not in the total."""

    removal: Removal
    session_id: str | None = None
    turns_after: int | None = None
    model: str | None = None
    write_multiplier: float | None = None
    bytes_per_token: float = DEFAULT_BYTES_PER_TOKEN
    calibrated: bool = False
    tokens: float = 0.0
    write_dollars: float = 0.0
    read_dollars: float = 0.0
    excluded: str | None = None

    @property
    def dollars(self) -> float:
        return self.write_dollars + self.read_dollars


@dataclass
class Savings:
    """Everything `winnow savings` knows. Writes nothing."""

    ledger: LedgerRead
    projects_dir: Path
    priced: list[Priced] = field(default_factory=list)
    sessions: dict[str, SessionFacts] = field(default_factory=dict)

    @property
    def counted(self) -> list[Priced]:
        return [p for p in self.priced if p.excluded is None]

    @property
    def unique_bytes(self) -> int:
        return sum(p.removal.bytes for p in self.priced)

    @property
    def write_dollars(self) -> float:
        return sum(p.write_dollars for p in self.counted)

    @property
    def read_dollars(self) -> float:
        return sum(p.read_dollars for p in self.counted)

    @property
    def dollars(self) -> float:
        return self.write_dollars + self.read_dollars

    @property
    def turns(self) -> list[int]:
        return sorted(p.turns_after for p in self.priced if p.turns_after is not None)

    @property
    def exclusions(self) -> dict[str, tuple[int, int]]:
        """`reason → (removals, bytes)`, so nothing drops out of the total silently."""
        out: dict[str, tuple[int, int]] = {}
        for p in self.priced:
            if p.excluded is None:
                continue
            count, size = out.get(p.excluded, (0, 0))
            out[p.excluded] = (count + 1, size + p.removal.bytes)
        return out

    @property
    def calibrated_bytes(self) -> int:
        return sum(p.removal.bytes for p in self.priced if p.calibrated)

    def bill(self) -> tuple[float, int, list[str]]:
        """`(dollars, sessions priced, model ids that had no price)`.

        The denominator for "share of the bill" is the joined sessions' own measured
        usage, not a constant: a share computed against a corpus average would move
        when the corpus moved and say nothing about this install.
        """
        total = 0.0
        unknown: list[str] = []
        for facts in self.sessions.values():
            for model, usage in facts.usage_by_model.items():
                price = PRICES.get(model)
                if price is None:
                    if model not in unknown:
                        unknown.append(model)
                    continue
                base, output = price
                total += usage.input_tokens * base / 1e6
                total += usage.output_tokens * output / 1e6
                total += usage.cache_read * CACHE_READ * base / 1e6
                total += usage.ephemeral_1h * WRITE_1H * base / 1e6
                total += usage.ephemeral_5m * WRITE_5M * base / 1e6
                # Whatever `cache_creation` reports beyond the 1h/5m split has no
                # class on the record. Price it at the class this session did pay.
                rest = max(0, usage.cache_creation - usage.ephemeral_1h - usage.ephemeral_5m)
                total += rest * _session_multiplier(usage, WRITE_5M) * base / 1e6
        return total, len(self.sessions), unknown


def _session_multiplier(usage: Usage, default: float) -> float:
    """The write multiplier this session actually paid, read from its own usage.

    A session that wrote in both classes gets the ratio it wrote them in — still read,
    not assumed, which is the whole point of COZEMPIC §3.1.
    """
    both = usage.ephemeral_1h + usage.ephemeral_5m
    if not both:
        return default
    return (usage.ephemeral_1h * WRITE_1H + usage.ephemeral_5m * WRITE_5M) / both


def compute(ledger_path: Path, projects_dir: Path = DEFAULT_PROJECTS) -> Savings:
    """Read the ledger, join it to the transcripts, and price what it did."""
    read = read_ledger(ledger_path)
    result = Savings(ledger=read, projects_dir=projects_dir)
    if not read.removals:
        return result

    wanted = {r.request_id for r in read.removals if r.request_id}
    dropped = ledger_dropped_bytes(ledger_path)
    located = find_transcripts(projects_dir, wanted)

    requests: dict[str, RequestFacts] = {}
    for path in sorted(set(located.values())):
        facts, resolved = read_session(path, wanted, dropped)
        result.sessions[facts.session_id] = facts
        requests.update(resolved)

    for removal in read.removals:
        result.priced.append(_price(removal, requests, result.sessions))
    return result


def _price(
    removal: Removal,
    requests: dict[str, RequestFacts],
    sessions: dict[str, SessionFacts],
) -> Priced:
    priced = Priced(removal=removal)
    if not removal.request_id:
        priced.excluded = "ledger line carries no request_id"
        return priced
    facts = requests.get(removal.request_id)
    if facts is None:
        priced.excluded = "request_id not found in any transcript"
        return priced

    session = sessions[facts.session_id]
    priced.session_id = facts.session_id
    priced.turns_after = facts.turns_after
    priced.bytes_per_token = session.bytes_per_token
    priced.calibrated = session.calibrated

    # The ledger's own model first: one ledger spans several, and the request body is
    # the only place that says which one this request was actually billed at.
    priced.model = removal.model or facts.model
    if priced.model is None:
        priced.excluded = "no model on the ledger line or the joined turn"
        return priced
    price = PRICES.get(priced.model)
    if price is None:
        priced.excluded = f"no published price for {priced.model}"
        return priced

    priced.write_multiplier = _TTL_MULTIPLIER.get(removal.ttl or "")
    if priced.write_multiplier is None:
        both = session.usage.ephemeral_1h + session.usage.ephemeral_5m
        if not both:
            priced.excluded = "no cache TTL on the ledger line and none paid in the session"
            return priced
        priced.write_multiplier = _session_multiplier(session.usage, WRITE_5M)

    base = price[0]
    priced.tokens = removal.bytes / priced.bytes_per_token
    # `W·D − 1.0·D`, not `W·D`. The filter still sends the result in full on the one
    # request the model acts on, and that turn is ordinary uncached input at 1.0×.
    # What it avoids is the write *premium*, which is 1.0·D at the 2.0× 1h class —
    # COZEMPIC §3.5's `saving 1.0·D`, and only 0.25·D at the 1.25× 5m one.
    priced.write_dollars = (priced.write_multiplier - 1.0) * priced.tokens * base / 1e6
    priced.read_dollars = CACHE_READ * priced.tokens * facts.turns_after * base / 1e6
    return priced


def turn_distribution(turns: list[int]) -> dict[str, float]:
    """Min, quartiles and max of `T`. One blended mean would hide the shape, and the
    read term is linear in `T`, so the shape is most of the answer."""
    if not turns:
        return {}
    return {
        "count": len(turns),
        "min": turns[0],
        "p25": statistics.quantiles(turns, n=4)[0] if len(turns) > 1 else turns[0],
        "median": statistics.median(turns),
        "p75": statistics.quantiles(turns, n=4)[2] if len(turns) > 1 else turns[0],
        "max": turns[-1],
        "mean": statistics.fmean(turns),
    }
