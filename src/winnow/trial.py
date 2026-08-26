"""An A/B trial priced from the bill, not from the cost model.

Every dollar figure this project has published so far is **modelled**. COZEMPIC
§3.5's table — the filter at 8.21% reach and $246.14, the pruner at 10.17% and
$214.46 — is one cost model replayed over 175 historical transcripts that neither
tool ever touched, and §3.5.1 says so about itself. `winnow savings` prices the
filter's real ledger, but the saving it reports is still a counterfactual: the
bytes were never sent, so no invoice line corresponds to them.

That is the right way to answer "what would this have saved". It cannot answer
"which of these should I run", because both arms of that question are modelled
with the same model, and a model cannot referee itself. The two figures being
compared differ by 1.1× — well inside what the ÷4 bytes→tokens estimate and the
unpriced quality cost could move.

**So this module models nothing.** It reads `message.usage` off the transcripts —
what the API said it billed — attributes each session to whichever arm the
operator had switched on at the time, and divides. The only counterfactual left
is the one that cannot be removed: the two arms did different work, on different
days, and the difference between them includes everything else that changed.
Interleaving the arms is what makes that noise rather than bias, and it is the
operator's job, not this file's.

## What it will not do

- **It will not compute a saving.** It reports what each arm cost. A saving needs
  a counterfactual and there isn't one here; that is the point.
- **It will not decide the denominator.** Cost per *session* is derivable and
  cost per *completed task* is not — a transcript does not record whether the
  work was any good, and SPEC §9's milestone-3 target is denominated per
  successful task precisely because the token figure alone is gameable by a tool
  that makes the model dumber and cheaper. `--tasks` takes that count from the
  operator or the report says it is missing.
- **It will not tell you the arms were comparable.** It reports how many sessions
  straddled an arm change and how far apart the arms' medians are, and leaves
  the reading to a person.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from .inspect import Usage, _inner, _read_usage
from .savings import (
    CACHE_READ,
    PRICES,
    WRITE_1H,
    WRITE_5M,
    normalise_model,
)

DEFAULT_ARMS = Path.home() / ".winnow" / "trial-arms.jsonl"

# A tool call is counted as a repeat when an earlier call in the same session had
# the same name and the same arguments. It is a **proxy** for re-derivation and
# is labelled as one everywhere it is reported.
#
# The thing actually worth counting is "work the model had to redo because a
# result it needed was gone", and no transcript records that: a repeat may be the
# model recovering a stripped result, or it may be an ordinary re-check of a file
# that has since changed. What makes the proxy worth having anyway is that it is
# the *same* proxy in both arms, so a rise in it between them is the signal even
# though its absolute level is not.
REPEAT_NOTE = (
    "identical (tool, arguments) called twice in one session — a proxy for "
    "re-derivation, not a measurement of it"
)


# ─── The arm ledger ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Arm:
    """One switch of the configuration, and the moment it happened."""

    at: float
    label: str
    note: str = ""


def record_arm(path: Path, label: str, note: str = "", now: float | None = None) -> Arm:
    """Append an arm switch. Everything from `now` on belongs to `label`.

    Append-only, like the resume ledger and for the same reason: the record of
    what was running when is the one thing that cannot be reconstructed later.
    A transcript does not carry the configuration that produced it.
    """
    import time

    arm = Arm(at=now if now is not None else time.time(), label=label, note=note)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({"at": arm.at, "label": arm.label, "note": arm.note}) + "\n"
        )
    return arm


def read_arms(path: Path) -> list[Arm]:
    """The arm switches, oldest first. A malformed line is skipped, not fatal."""
    if not path.exists():
        return []
    arms: list[Arm] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(row, dict)
            and isinstance(row.get("at"), (int, float))
            and row.get("label")
        ):
            arms.append(
                Arm(
                    at=float(row["at"]),
                    label=str(row["label"]),
                    note=str(row.get("note", "")),
                )
            )
    arms.sort(key=lambda a: a.at)
    return arms


def arm_for(arms: list[Arm], when: float) -> str | None:
    """Which arm was in force at `when`, or None if it predates the first switch.

    Sessions that predate the first switch are reported separately rather than
    folded into the earliest arm. They ran under a configuration nobody wrote
    down, and quietly attributing them to whichever arm happened to be declared
    first is how a trial acquires a result it did not measure.
    """
    found: str | None = None
    for arm in arms:
        if arm.at <= when:
            found = arm.label
        else:
            break
    return found


# ─── Reading a session off disk ──────────────────────────────────────────────


@dataclass
class SessionCost(Usage):
    """One session's billed usage, plus what it took to get it."""

    session: str = ""
    path: str = ""
    first_ts: float = 0.0
    last_ts: float = 0.0
    model: str | None = None
    tool_calls: int = 0
    repeat_tool_calls: int = 0

    @property
    def billed_input(self) -> int:
        """Every input token the API charged for, however it was billed.

        `input + cache_creation + cache_read`, which is the whole prompt — a
        cached token is still a token the model read, and a comparison that
        counted only the uncached part would credit an arm for the caching it
        happened to get rather than for the context it carried.
        """
        return self.input_tokens + self.cache_creation + self.cache_read


def read_session(path: Path) -> SessionCost | None:
    """Sum one transcript's billed usage and count its repeated tool calls.

    Returns None for a transcript with no billed turn at all: a session that
    never reached the API is not a data point about what an arm costs, and
    letting it through would drag every per-session figure toward zero in
    whichever arm happened to collect more of them.
    """
    cost = SessionCost(session=path.stem, path=str(path))
    seen: set[tuple[str, str]] = set()
    for line in _lines(path):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        ts = _timestamp(record.get("timestamp"))
        if ts is not None:
            if cost.first_ts == 0.0 or ts < cost.first_ts:
                cost.first_ts = ts
            cost.last_ts = max(cost.last_ts, ts)
        before = cost.turns
        _read_usage(record, cost)
        if cost.turns > before and cost.model is None:
            cost.model = normalise_model(_inner(record).get("model"))
        _count_tools(record, seen, cost)
    return cost if cost.turns else None


def _lines(path: Path):
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            yield from handle
    except OSError:
        return


def _timestamp(value) -> float | None:
    """Claude Code's ISO-8601 `timestamp`, as epoch seconds."""
    if not isinstance(value, str) or not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _count_tools(record: dict, seen: set[tuple[str, str]], cost: SessionCost) -> None:
    """Count `tool_use` blocks, and how many repeat an earlier call exactly.

    Keyed on `(name, json.dumps(input, sort_keys=True))` — the same key rule C2
    uses in `rules.canonical_input`, so that a call ordering difference cannot
    make two identical calls look distinct.
    """
    content = _inner(record).get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        cost.tool_calls += 1
        key = (
            str(block.get("name")),
            json.dumps(block.get("input"), sort_keys=True, default=str),
        )
        if key in seen:
            cost.repeat_tool_calls += 1
        else:
            seen.add(key)


# ─── Pricing, from the same table `savings` uses ─────────────────────────────


def price_session(cost: SessionCost) -> float | None:
    """What this session's input and output actually cost, at list.

    None for a model absent from the price table, never a neighbour's rate and
    never zero — `savings.py`'s rule, restated here because it is the one that
    keeps a total reconcilable against an invoice.

    The write class is read back from the session's own `cache_creation` detail
    rather than assumed, which is COZEMPIC §3.1's correction: pricing a 1h write
    at the documented 1.25× understates it by about 40%.
    """
    if cost.model is None:
        return None
    price = PRICES.get(cost.model)
    if price is None:
        return None
    base_in, base_out = price
    write = WRITE_1H if cost.write_class == "1h" else WRITE_5M
    dollars = (
        cost.input_tokens * base_in
        + cost.cache_creation * base_in * write
        + cost.cache_read * base_in * CACHE_READ
        + cost.output_tokens * base_out
    ) / 1_000_000
    return dollars


# ─── The arithmetic, pure ────────────────────────────────────────────────────


@dataclass
class ArmResult:
    """One arm's billed total, and what it is a total over."""

    label: str
    sessions: int = 0
    priced_sessions: int = 0
    turns: int = 0
    billed_input: int = 0
    output_tokens: int = 0
    dollars: float = 0.0
    tool_calls: int = 0
    repeat_tool_calls: int = 0
    tasks: int | None = None
    per_session_dollars: list[float] = field(default_factory=list)

    @property
    def dollars_per_session(self) -> float | None:
        return self.dollars / self.priced_sessions if self.priced_sessions else None

    @property
    def dollars_per_turn(self) -> float | None:
        return self.dollars / self.turns if self.turns else None

    @property
    def dollars_per_task(self) -> float | None:
        """The figure that actually decides it, when the operator supplied one."""
        return self.dollars / self.tasks if self.tasks else None

    @property
    def median_session_dollars(self) -> float | None:
        """Reported next to the mean because these distributions are not normal.

        A single very long session dominates a mean over a handful of them, and
        an arm that happened to collect one reads as the expensive arm.
        """
        return (
            statistics.median(self.per_session_dollars)
            if self.per_session_dollars
            else None
        )

    @property
    def repeat_rate(self) -> float | None:
        return self.repeat_tool_calls / self.tool_calls if self.tool_calls else None


@dataclass
class Trial:
    """Every arm, plus what could not be attributed to one."""

    arms: list[ArmResult] = field(default_factory=list)
    unattributed_sessions: int = 0
    straddling_sessions: int = 0
    unpriced_sessions: int = 0
    corpus: str = ""


def build_trial(
    costs: list[SessionCost],
    arms: list[Arm],
    tasks: dict[str, int] | None = None,
) -> Trial:
    """Attribute each session to an arm and add the arms up.

    Attribution is by the session's **first** billed turn, not its last: an arm
    is a statement about the configuration a session ran under, and a session
    that began before a switch ran mostly under what came before it. Sessions
    that were still going when the arm changed are counted in
    `straddling_sessions` so the reader can judge how much of the total is
    contaminated rather than being told a clean-looking number.
    """
    tasks = tasks or {}
    by_label: dict[str, ArmResult] = {a.label: ArmResult(label=a.label) for a in arms}
    trial = Trial()

    for cost in costs:
        label = arm_for(arms, cost.first_ts)
        if label is None:
            trial.unattributed_sessions += 1
            continue
        if arm_for(arms, cost.last_ts) != label:
            trial.straddling_sessions += 1
        result = by_label[label]
        result.sessions += 1
        result.turns += cost.turns
        result.billed_input += cost.billed_input
        result.output_tokens += cost.output_tokens
        result.tool_calls += cost.tool_calls
        result.repeat_tool_calls += cost.repeat_tool_calls
        dollars = price_session(cost)
        if dollars is None:
            trial.unpriced_sessions += 1
        else:
            result.priced_sessions += 1
            result.dollars += dollars
            result.per_session_dollars.append(dollars)

    for label, result in by_label.items():
        result.tasks = tasks.get(label)
    # In the order the operator declared them, so a report reads as a timeline.
    seen: set[str] = set()
    for arm in arms:
        if arm.label not in seen:
            seen.add(arm.label)
            trial.arms.append(by_label[arm.label])
    return trial


def collect(corpus: Path) -> list[SessionCost]:
    """Every transcript under `corpus` that billed at least one turn."""
    out: list[SessionCost] = []
    paths = sorted(corpus.rglob("*.jsonl")) if corpus.is_dir() else [corpus]
    for path in paths:
        cost = read_session(path)
        if cost is not None:
            out.append(cost)
    return out
