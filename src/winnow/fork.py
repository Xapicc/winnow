"""`winnow fork` and `winnow recover` — milestone 2's actuator and its round trip.

`plan` decides what would go. This module writes it, and reads it back. The
split is deliberate and load-bearing: **`fork` consumes `plan`'s list rather
than reclassifying**, so the dry run an operator read is the fork they get. Every
byte figure here is `plan`'s, and the writer's job is to make the file agree with
it rather than to have its own opinion.

Four refusals live here, and the difference between them is the whole safety
story:

* **G5 pairing preserved** — hard, never forced. SPEC §4 words it "every
  `tool_use` in the output has a matching `tool_result`", and what is enforced
  here is the stronger and narrower thing: the output's ordered `tool_use` ↔
  `tool_result` pairing is *identical* to the input's, re-derived from the bytes
  about to be written rather than from the plan that produced them.

  Stronger, because identity also catches a duplicated result, a reordering, and
  an *invented* pairing — none of which the absolute reading forbids. Narrower,
  because a `tool_use` the source never answered is left unanswered. That is
  deliberate: SPEC §4 measured 5 unanswered calls across 42,966 and they are the
  last in-flight call of a session, so the absolute reading taken literally would
  refuse an ordinary transcript, and `tests/fixtures/sessions/corrupted_tool_use.jsonl`
  is exactly that shape. SPEC §3 forbids winnow to delete anything, so it cannot
  repair such a call either. The guard winnow can honour is that winnow does not
  *introduce* an unpaired block, and that is the one it enforces.
* **--min-cold-age** — soft, `--force` proceeds. SPEC §7's entire economic case is
  that a resume past the cache TTL pays a write it was going to pay anyway. A warm
  session does not, so forking it costs `1.9·S` for nothing. MILESTONES.md's kill
  criteria name loosening this guard as itself a kill condition, which is why it
  is a refusal and not a warning.
* **G4 no net inflation, at the whole-fork level** — soft, `--force` proceeds.
  `plan` already applies G4 per result; this is the arithmetic over the fork as a
  whole, and it refuses a fork that would add more pointer than it removes
  content.
* **Q4, a session that has already compacted** — soft, `--force` proceeds. See
  DECISIONS.md §Q4, decided in this run: refuse by default.

The original is opened read-only and never written. The fork goes to a temporary
file in the destination directory and is `os.replace`d into place, so a crash
leaves either nothing or a complete file (SPEC §10).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .inspect import inspect_session
from .legacy.session import load_messages
from .plan import (
    EXPLAIN_WARNING,
    Plan,
    PlanError,
    build_plan,
    render_body,
    resolve_selection,
)
from .plan import to_dict as plan_to_dict
from .report import _human, resolve_session
from .rules import RULE_TIER, content_digest, parse_pointer_id, result_payload

# SPEC §8's default. Seconds since the session's last request finished; below
# this, the prefix may still be cached and the cut is not free.
DEFAULT_MIN_COLD_AGE = 3600

# The namespace the fork's session ID is derived under. A fixed constant rather
# than a value computed at import, so that the derivation cannot drift:
# `uuid5(NAMESPACE_URL, "https://github.com/Xapicc/winnow#fork")`, recorded here
# as its literal.
FORK_NAMESPACE = uuid.UUID("5e89c7cb-6d60-5be9-a65c-192de59b213d")

# How the fork's records are re-serialised. `ensure_ascii=False` is not cosmetic:
# the transcript is read with `surrogateescape`, so a non-UTF-8 byte is carried as
# a lone surrogate, and only a non-ASCII-escaping dump re-encodes it to the
# original byte. Compact separators match what the harness itself writes, so a
# rewritten line does not gain bytes for punctuation the source did not spend.
_JSON_ARGS = {"ensure_ascii": False, "separators": (",", ":")}


class ForkError(ValueError):
    """A usage error: SPEC §8 exit code 1."""


@dataclass(frozen=True)
class Refusal:
    """A SPEC §8 exit-3 refusal, naming what refused.

    `forceable` is the difference between a soft refusal and G5: `--force`
    proceeds past a soft one and must never get past a hard one.
    """

    guard: str
    reason: str
    forceable: bool


@dataclass
class ForkResult:
    """One fork: the plan it came from, where it would go, and what it costs."""

    plan: Plan
    new_session_id: str
    out_path: Path
    source_sha256: str
    source_bytes: int
    fork_bytes: int
    last_activity: float
    last_activity_source: str
    cold_age: float
    min_cold_age: int
    tool_uses: int
    tool_results: int
    parse_errors: int
    compact_boundaries: list[int] = field(default_factory=list)
    written: bool = False
    forced: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list, repr=False)

    @property
    def file_delta(self) -> int:
        """What the fork adds to the file, in bytes. Negative is the point."""
        return self.fork_bytes - self.source_bytes

    @property
    def resume_command(self) -> str:
        """SPEC §3: winnow prints this line; the operator runs it."""
        return f"claude --resume {self.new_session_id}"


# ─── The new session ID ──────────────────────────────────────────────────────


def derive_session_id(
    source_session_id: str,
    source_sha256: str,
    plan: Plan,
) -> str:
    """The fork's session ID, derived from its input rather than drawn from one.

    SPEC §10 requires the same transcript and the same flags to produce a
    byte-identical fork, and the file's own name is part of that output — so the
    ID cannot come from `uuid4`, from the clock, or from a counter. It is a
    **name-based UUIDv5** over a canonical description of exactly what this fork
    is, under a fixed winnow namespace:

        source session ID
        sha256 of the source file's bytes
        the resolved rule selection, sorted, with --keep-last and --min-bytes
        one line per strip: pointer id, tool_use id, content digest

    The first two pin the input, the third pins the flags, and the fourth pins
    the output — so two forks that differ in *any* respect that changes their
    content get different names and cannot overwrite one another, while re-running
    the same command lands on the same file and writes the same bytes.

    The last line matters more than it looks: were the ID derived from the input
    alone, a future change to the rule engine would write different content under
    the same name, and the fork already on disk would be silently replaced.

    The result is a well-formed UUID because that is what `claude --resume`
    expects to find as a filename stem; UUIDv5 is the standard construction for
    "derive a UUID from a name" and needs no format of winnow's own invention.
    """
    parts = [
        source_session_id,
        source_sha256,
        "rules=" + ",".join(sorted(plan.rules)),
        f"keep_last={plan.keep_last}",
        f"min_bytes={plan.min_bytes}",
    ]
    parts.extend(
        f"{strip.pointer_id} {strip.use_id} {strip.digest}" for strip in plan.strips
    )
    return str(uuid.uuid5(FORK_NAMESPACE, "\n".join(parts)))


# ─── Reading the source ──────────────────────────────────────────────────────


def source_lines(path: Path) -> tuple[list[str], str, int]:
    """`(lines, sha256, byte length)` of the source, read once, read-only.

    Split on `\\n` with the trailing element kept, so that joining the list back
    reproduces the file exactly — including whether it ended in a newline. The
    same `surrogateescape` handler `legacy.session` uses, for the same reason: a
    binary or truncated-multibyte tool result must round-trip to its original
    bytes rather than being rewritten to U+FFFD.
    """
    raw = path.read_bytes()
    text = raw.decode("utf-8", "surrogateescape")
    return text.split("\n"), hashlib.sha256(raw).hexdigest(), len(raw)


def last_activity(path: Path, records: list[dict]) -> tuple[float, str]:
    """When this session's last request finished, and how that was determined.

    The newest record `timestamp` when the transcript carries one, because that is
    literally what SPEC §7's threshold is about. The file's mtime otherwise — a
    transcript is appended to as the session runs, so its mtime is when the last
    record landed. Both are named in the refusal, because an operator who is told
    "too warm" is owed the clock that said so.
    """
    newest: float | None = None
    for record in records:
        parsed = _timestamp(record.get("timestamp"))
        if parsed is not None and (newest is None or parsed > newest):
            newest = parsed
    if newest is not None:
        return newest, "the newest record timestamp"
    return path.stat().st_mtime, "the transcript's mtime — no record carries a timestamp"


def _timestamp(value) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


# ─── Guard G5, in its enforcing form ─────────────────────────────────────────


def pairing(records: list[dict]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`(tool_use ids, tool_result ids)` in record order.

    The pair of tuples is what G5 compares between the source and the fork.
    Order is kept rather than sorted, because a writer that moved a result to a
    different record would preserve the sets and break the conversation.
    """
    uses: list[str] = []
    results: list[str] = []
    for record in records:
        inner = record.get("message")
        content = inner.get("content") if isinstance(inner, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                identifier = block.get("id")
                if isinstance(identifier, str):
                    uses.append(identifier)
            elif block.get("type") == "tool_result":
                identifier = block.get("tool_use_id")
                if isinstance(identifier, str):
                    results.append(identifier)
    return tuple(uses), tuple(results)


def _g5_violation(before: tuple, after: tuple) -> str | None:
    """What changed about the pairing, in one sentence, or None if nothing did."""
    for label, source, fork in (("tool_use", before[0], after[0]),
                                ("tool_result", before[1], after[1])):
        if source == fork:
            continue
        lost = [i for i in source if i not in fork]
        gained = [i for i in fork if i not in source]
        if lost:
            return (f"the fork lost {len(lost)} {label} block(s) the source has "
                    f"(first: {lost[0]!r})")
        if gained:
            return (f"the fork has {len(gained)} {label} block(s) the source does "
                    f"not (first: {gained[0]!r})")
        return f"the fork reorders the source's {label} blocks"
    return None


# ─── Writing the fork ────────────────────────────────────────────────────────


def build_fork(
    plan: Plan,
    out: Path | None = None,
    now: float | None = None,
    min_cold_age: int = DEFAULT_MIN_COLD_AGE,
) -> tuple[ForkResult, list[Refusal]]:
    """Render the forked transcript in memory and collect every refusal.

    Nothing is written here. The caller decides whether the refusals stand, so
    that a dry run and a `--write` see exactly the same list — which is what makes
    `fork` without `--write` worth reading.
    """
    lines, source_sha, source_bytes = source_lines(plan.path)
    # Parsed from the same lines the writer will emit, rather than through
    # `load_messages`: G5 compares the source's pairing against the fork's, and a
    # comparison whose two sides come from two parsers can report a difference
    # neither file has.
    records = _parse_all(lines)

    new_id = derive_session_id(plan.session_id, source_sha, plan)
    destination = out if out is not None else plan.path.parent / f"{new_id}.jsonl"

    forked_lines, applied, mismatched = _rewrite(lines, plan, new_id)
    forked_text = "\n".join(forked_lines)
    forked_bytes = forked_text.encode("utf-8", "surrogateescape")

    before = pairing(records)
    after = pairing(_parse_all(forked_lines))

    when, how = last_activity(plan.path, records)
    age = (time.time() if now is None else now) - when

    result = ForkResult(
        plan=plan,
        new_session_id=new_id,
        out_path=destination,
        source_sha256=source_sha,
        source_bytes=source_bytes,
        fork_bytes=len(forked_bytes),
        last_activity=when,
        last_activity_source=how,
        cold_age=age,
        min_cold_age=min_cold_age,
        tool_uses=len(before[0]),
        tool_results=len(before[1]),
        parse_errors=plan.report.parse_errors,
        compact_boundaries=list(plan.report.compact_boundaries),
        lines=forked_lines,
    )
    return result, _refusals(result, before, after, applied, mismatched, age, min_cold_age)


def _parse_all(lines: list[str]) -> list[dict]:
    out: list[dict] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            out.append(record)
    return out


def _rewrite(
    lines: list[str],
    plan: Plan,
    new_session_id: str,
) -> tuple[list[str], set[str], list[str]]:
    """The fork's lines, the pointer ids applied, and any plan/transcript mismatch.

    A line is re-serialised only if it carries something that must change — a
    `tool_result` this plan strips, or this session's own `sessionId`. Every other
    line is copied across byte for byte, which is both the cheapest way to be
    faithful and the only way to keep a record type winnow does not understand
    exactly as the harness wrote it (DECISIONS §4, "the record types nobody
    documents").
    """
    by_line: dict[int, list] = {}
    for strip in plan.strips:
        by_line.setdefault(strip.line, []).append(strip)

    applied: set[str] = set()
    mismatched: list[str] = []
    out = list(lines)

    for index, text in enumerate(lines):
        strips = by_line.get(index)
        needs_session = f'"{plan.session_id}"' in text and '"sessionId"' in text
        if not strips and not needs_session:
            continue
        stripped_text = text.strip()
        if not stripped_text:
            continue
        try:
            record = json.loads(stripped_text)
        except json.JSONDecodeError:
            # Left verbatim. A malformed line is refused before this point unless
            # the operator forced past it, and forcing past it means keeping it as
            # it is rather than guessing at what it meant.
            continue
        if not isinstance(record, dict):
            continue
        if needs_session:
            _retitle(record, plan.session_id, new_session_id)
        for strip in strips or ():
            found = _replace_result(record, strip)
            if found is None:
                mismatched.append(
                    f"{strip.pointer_id}: no tool_result for {strip.use_id!r} on "
                    f"line {strip.line}"
                )
            elif found != strip.digest:
                mismatched.append(
                    f"{strip.pointer_id}: line {strip.line} holds sha256 {found[:12]}…, "
                    f"the plan recorded {strip.digest[:12]}…"
                )
            else:
                applied.add(strip.pointer_id)
        out[index] = json.dumps(record, **_JSON_ARGS)
    return out, applied, mismatched


def _retitle(record: dict, old_session_id: str, new_session_id: str) -> None:
    """Point this record's `sessionId` at the fork it now lives in.

    Only where the value is this session's own ID: a record naming a *different*
    session — a `bridge-session`, say — is describing something else, and
    rewriting it would be the "cleaning up" DECISIONS §4 forbids. Recursive
    because the field is not always top-level.
    """
    for key, value in record.items():
        if key == "sessionId" and value == old_session_id:
            record[key] = new_session_id
        elif isinstance(value, dict):
            _retitle(value, old_session_id, new_session_id)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _retitle(item, old_session_id, new_session_id)


def _replace_result(record: dict, strip) -> str | None:
    """Swap one `tool_result`'s content for its pointer. Returns the digest of
    what was there, or None if the block was not on this record.

    The pointer is written as a **plain string**, not as a one-element list of
    text blocks. `content` is documented as accepting either, and the string is
    the only rendering whose size is exactly the `len()` guard G4 compared
    against: wrapping it would add about thirty bytes of JSON scaffolding that
    `plan` never priced, so the fork would remove less than the dry run promised.
    """
    inner = record.get("message")
    content = inner.get("content") if isinstance(inner, dict) else None
    if not isinstance(content, list):
        return None
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        if block.get("tool_use_id") != strip.use_id:
            continue
        found = content_digest(block.get("content"))
        block["content"] = strip.pointer
        return found
    return None


def _refusals(
    result: ForkResult,
    before: tuple,
    after: tuple,
    applied: set[str],
    mismatched: list[str],
    age: float,
    min_cold_age: int,
) -> list[Refusal]:
    """Everything standing between this fork and the disk, hard refusals first."""
    out: list[Refusal] = []

    violation = _g5_violation(before, after)
    if violation is not None:
        out.append(Refusal(
            "G5",
            f"pairing preserved: {violation}. Nothing was written. This is a hard "
            "failure and --force does not reach it (SPEC §4 G5).",
            forceable=False,
        ))
    if mismatched:
        out.append(Refusal(
            "G5",
            "the plan and the transcript disagree about what is on these lines, so "
            "a pointer would name bytes that are not there: "
            + "; ".join(mismatched[:3]),
            forceable=False,
        ))
    missing = sorted({s.pointer_id for s in result.plan.strips} - applied)
    if missing and not mismatched:
        out.append(Refusal(
            "G5",
            f"{len(missing)} planned strip(s) were not applied to any block "
            f"(first: {missing[0]}); the fork would not be the plan.",
            forceable=False,
        ))
    if result.parse_errors:
        out.append(Refusal(
            "parse",
            f"the source has {result.parse_errors} malformed record(s). SPEC §10 "
            "fails loudly on one rather than forking a transcript it could not "
            "fully read; --force copies them across verbatim.",
            forceable=True,
        ))
    if age < min_cold_age:
        out.append(Refusal(
            "cold-age",
            f"this session's last request finished {_duration(age)} ago, inside the "
            f"{_duration(min_cold_age)} --min-cold-age window, so its prefix may "
            f"still be cached and the cut is not free (SPEC §7). Measured from "
            f"{result.last_activity_source}.",
            forceable=True,
        ))
    if result.compact_boundaries:
        out.append(Refusal(
            "compacted",
            f"this session has already compacted ({len(result.compact_boundaries)} "
            f"boundary/boundaries, first at line {result.compact_boundaries[0]}). A "
            "resume starts from the summary, so the pre-boundary results this plan "
            "prices are not in the prefix it would be cutting (DECISIONS §Q4).",
            forceable=True,
        ))
    if not result.plan.strips and result.plan.inflated:
        out.append(Refusal(
            "G4",
            f"no net inflation: every one of the {len(result.plan.inflated):,} "
            "candidates would be replaced by a pointer longer than itself, so the "
            "fork would remove fewer bytes than it adds (SPEC §4 G4). Raising "
            f"--min-bytes above "
            f"{max(s.result_size for s in result.plan.inflated):,} removes the class.",
            forceable=True,
        ))
    elif result.plan.strips and result.plan.net_bytes <= 0:
        out.append(Refusal(
            "G4",
            f"no net inflation: this fork removes {result.plan.removed_bytes:,} bytes "
            f"and adds {result.plan.pointer_bytes:,} bytes of pointer, a net of "
            f"{result.plan.net_bytes:,} (SPEC §4 G4).",
            forceable=True,
        ))
    if result.plan.strips and result.file_delta >= 0:
        out.append(Refusal(
            "G4",
            f"no net inflation: the forked file is {result.file_delta:,} bytes "
            f"larger than the source ({result.fork_bytes:,} against "
            f"{result.source_bytes:,}). A tool asked to shrink a context must not "
            "grow it (SPEC §4 G4).",
            forceable=True,
        ))
    return out


def _duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 0:
        return "less than a second"
    if seconds < 120:
        return f"{seconds}s"
    if seconds < 7200:
        return f"{seconds // 60}m"
    if seconds < 172_800:
        return f"{seconds // 3600}h"
    return f"{seconds // 86_400}d"


def write_fork(result: ForkResult, force: bool = False) -> None:
    """Write the fork atomically, into the destination directory.

    Temporary file plus `os.replace` in the same directory, per SPEC §10: a crash
    leaves either the old file or the complete new one, never half of either. The
    original is not opened here at all — it was read once, in `build_fork`, and
    nothing in this module opens it for writing.
    """
    destination = result.out_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(result.lines).encode("utf-8", "surrogateescape")

    if (destination.exists() and not force
            and destination.read_bytes() != payload):
        raise ForkError(
            f"{destination} already exists and holds different bytes. A "
            "deterministic fork of the same session and flags lands on the "
            "same name, so this is a different fork; pass --out or --force."
        )
    temporary = destination.with_name(destination.name + ".winnow-tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    result.written = True


# ─── Rendering ───────────────────────────────────────────────────────────────


def to_dict(result: ForkResult, refusals: list[Refusal], explain: bool = False) -> dict:
    """The `--json` shape. `plan`'s payload nested whole, so a consumer that
    already reads a plan does not learn a second vocabulary for the same numbers."""
    return {
        "session_id": result.plan.session_id,
        "path": str(result.plan.path),
        "new_session_id": result.new_session_id,
        "out": str(result.out_path),
        "written": result.written,
        "resume": result.resume_command,
        "source": {
            "sha256": result.source_sha256,
            "bytes": result.source_bytes,
        },
        "fork": {
            "bytes": result.fork_bytes,
            "file_delta": result.file_delta,
        },
        "cold_age": {
            "seconds": round(result.cold_age, 3),
            "threshold": result.min_cold_age,
            "measured_from": result.last_activity_source,
        },
        "pairing": {
            "tool_uses": result.tool_uses,
            "tool_results": result.tool_results,
            "preserved": not any(r.guard == "G5" for r in refusals),
        },
        "compact_boundaries": result.compact_boundaries,
        "parse_errors": result.parse_errors,
        "forced": result.forced,
        "refusals": [
            {"guard": r.guard, "forceable": r.forceable, "reason": r.reason}
            for r in refusals
        ],
        "plan": plan_to_dict(result.plan, explain),
    }


def render(result: ForkResult, refusals: list[Refusal], explain: bool = False) -> str:
    """The human readout: the fork's own facts, then `plan`'s arithmetic."""
    plan = result.plan
    out: list[str] = []
    add = out.append

    verb = "wrote" if result.written else "would write"
    add(f"fork of session {plan.session_id}")
    add(f"  {plan.path}")
    add(f"  {verb} {result.out_path}")
    add(f"  new session id {result.new_session_id}")
    add(f"  source sha256  {result.source_sha256}  (unchanged; opened read-only)")
    add(f"  tier {plan.tier}   rules {', '.join(sorted(plan.rules)) or 'none'}   "
        f"keep-last {plan.keep_last}   min-bytes {plan.min_bytes:,}")
    add("")

    add(f"pairing          {result.tool_uses:,} tool_use, {result.tool_results:,} "
        f"tool_result — G5 "
        f"{'preserved' if not any(r.guard == 'G5' for r in refusals) else 'VIOLATED'}")
    add(f"cold age         {_duration(result.cold_age)} since the last request, "
        f"threshold {_duration(result.min_cold_age)}")
    add(f"                 measured from {result.last_activity_source}")
    if result.compact_boundaries:
        add(f"compaction       {len(result.compact_boundaries)} boundary/boundaries, "
            f"first at line {result.compact_boundaries[0]} (DECISIONS §Q4)")
    if result.parse_errors:
        add(f"malformed        {result.parse_errors:,} record(s) copied across verbatim")
    add(f"file size        {_human(result.source_bytes)} → {_human(result.fork_bytes)}   "
        f"{result.file_delta:+,} bytes")
    add("")

    add(render_body(plan, explain))

    if refusals:
        add("")
        for refusal in refusals:
            add(f"refused ({refusal.guard})  {refusal.reason}")
            if not refusal.forceable:
                add("  --force does not reach this one.")
    if result.forced:
        add("")
        add(f"forced past      {', '.join(result.forced)} — --force was given")
    if result.written:
        add("")
        add(f"resume it with   {result.resume_command}")
        add("  the original is untouched and is where `winnow recover` reads from")
    elif not refusals:
        add("")
        add("dry run          pass --write to put this on disk; there is no --dry-run")
    return "\n".join(out)


# ─── The commands ────────────────────────────────────────────────────────────


def fork_command(
    session: str,
    tier: str = "CB",
    rule: list[str] | None = None,
    no_rule: list[str] | None = None,
    keep_last: int | None = None,
    min_bytes: int | None = None,
    min_cold_age: int = DEFAULT_MIN_COLD_AGE,
    i_know: bool = False,
    write: bool = False,
    out: str | None = None,
    force: bool = False,
    as_json: bool = False,
    explain: bool = False,
    now: float | None = None,
) -> tuple[int, str]:
    """`(exit code, output)`. SPEC §8: 0 success, 1 usage, 2 nothing to do, 3 refused.

    `now` is injected rather than read from the clock at the point of use, so that
    the cold-age guard is testable without sleeping and so a caller can price a
    fork as of a stated moment. It changes nothing about the output bytes: SPEC
    §10's determinism is a property of the file, and the clock only decides
    whether the file is written.

    SPEC §8 lists three exit-3 refusals: too warm, live, and G5. There is no
    separate liveness guard here because `--min-cold-age` subsumes it — a session
    Claude Code still has open is being appended to, so its last activity is by
    definition recent, and any threshold worth setting catches it. A second guard
    firing on the same evidence would only give the operator two things to force
    past.
    """
    try:
        selection = resolve_selection(tier, rule, no_rule, i_know)
    except PlanError as exc:
        return 1, f"winnow: {exc}"
    try:
        path = resolve_session(session)
    except LookupError as exc:
        return 1, f"winnow: {exc}"
    if min_cold_age < 0:
        return 1, f"winnow: --min-cold-age must not be negative, got {min_cold_age}"
    try:
        plan = build_plan(path, tier=tier, rules=selection,
                          keep_last=keep_last, min_bytes=min_bytes)
    except PlanError as exc:
        return 1, f"winnow: {exc}"

    destination = Path(out).expanduser() if out else None
    result, refusals = build_fork(plan, out=destination, now=now,
                                  min_cold_age=min_cold_age)

    hard = [r for r in refusals if not r.forceable]
    soft = [r for r in refusals if r.forceable]
    standing = hard if force else refusals
    if force:
        result.forced = [r.guard for r in soft]

    if standing:
        body = (json.dumps(to_dict(result, standing, explain), indent=2)
                if as_json else render(result, standing, explain))
        return 3, body
    if not plan.strips:
        # Exit 2 is SPEC §8's "nothing to do — no result met a rule". Distinct from
        # the G4 refusal above, which is "a rule met a result and the swap was not
        # worth taking": one is a session with nothing in it for winnow, the other
        # is a fork that would make the context bigger.
        body = (json.dumps(to_dict(result, [], explain), indent=2)
                if as_json else render(result, [], explain))
        return 2, body + ("" if as_json else
                          "\n\nwinnow: nothing to do — no result met a rule at tier "
                          f"{tier}; nothing was written.")
    if write:
        try:
            write_fork(result, force=force)
        except ForkError as exc:
            # Exit 1, not 3: SPEC §8's exit-3 list is the guards, and "you chose a
            # destination that is taken" is a bad argument rather than a refused
            # fork. Passing --out or --force resolves it.
            return 1, f"winnow: {exc}"
        except OSError as exc:
            return 1, f"winnow: cannot write {result.out_path}: {exc}"
    body = (json.dumps(to_dict(result, [], explain), indent=2)
            if as_json else render(result, [], explain))
    return 0, body


def recover_command(
    session: str,
    identifier: str,
    as_json: bool = False,
) -> tuple[int, str]:
    """`winnow recover <session> <pointer-id>` — the original bytes, from the original.

    `<session>` is the *source* session, which is what the pointer quotes: the
    bytes live in the transcript winnow never wrote to, and that is the whole
    reason a strip is reversible (SPEC §7, retrieval route 2). Nothing here reads
    the fork, so a recovery works even if the fork has been deleted.

    The pointer ID carries the tier letter of the rule that fired and the call's
    ordinal position among the session's tool calls, so the lookup needs no index
    and no fourth store (SPEC §3).
    """
    try:
        tier, order = parse_pointer_id(identifier)
    except ValueError as exc:
        return 1, f"winnow: {exc}"
    try:
        path = resolve_session(session)
    except LookupError as exc:
        return 1, f"winnow: {exc}"

    report = inspect_session(path)
    found = next((call for call in report.calls if call.order == order), None)
    if found is None:
        return 1, (f"winnow: session {report.session_id} has no tool call at "
                   f"position {order} ({report.tool_calls:,} calls in the file)")
    if not found.has_result:
        return 1, (f"winnow: tool call {order} in session {report.session_id} never "
                   "returned a result, so there is nothing to recover")
    if tier not in RULE_TIER.values():
        return 1, f"winnow: pointer id {identifier!r} names an unknown tier {tier!r}"

    payload = _payload_at(path, found.use_id)
    if payload is None:
        return 1, (f"winnow: tool call {order} in session {report.session_id} has no "
                   f"readable result block for {found.use_id!r}")
    if as_json:
        return 0, json.dumps(
            {
                "session_id": report.session_id,
                "path": str(path),
                "pointer_id": identifier,
                "order": order,
                "tool": found.name,
                "bytes": found.result_size,
                "sha256": found.digest,
                "content": payload,
            },
            indent=2,
            ensure_ascii=False,
        )
    return 0, payload


def _payload_at(path: Path, use_id: str) -> str | None:
    """The exact text `rules.content_digest` hashed, read back from the source.

    Re-read rather than carried through `inspect`, because `recover`'s contract is
    that the bytes come from the untouched original — reporting a value winnow had
    in memory would prove nothing about the file.
    """
    for _, record, _ in load_messages(path):
        inner = record.get("message")
        content = inner.get("content") if isinstance(inner, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            if block.get("tool_use_id") == use_id:
                return result_payload(block.get("content"))
    return None


__all__ = [
    "DEFAULT_MIN_COLD_AGE",
    "EXPLAIN_WARNING",
    "ForkError",
    "ForkResult",
    "Refusal",
    "build_fork",
    "derive_session_id",
    "fork_command",
    "pairing",
    "recover_command",
    "render",
    "to_dict",
    "write_fork",
]
