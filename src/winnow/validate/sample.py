"""Drawing the stratified 200, and writing a sheet a person can fill in blind.

MILESTONES milestone 2 wants 200 stripped results **sampled stratified by rule**
and labelled **blind against the surrounding turns**. Two words there do the work.

*Stratified*, because the rules fire at wildly different rates: B2 claims most of
what a session carries, A1 almost nothing. A simple random draw of 200 would be
four fifths B2 and would leave the rules that most need a per-rule number with
three samples each. Allocation is equal per rule, with a rule that has fewer
candidates than its share handing the surplus back to the rules that still have
room.

*Blind*, because a labeller who can see which rule fired can reason from the rule
rather than from the turns, and the label would then measure agreement with the
rule's own description instead of whether the result was needed again. So the
sheet carries the tool call, the result and the surrounding turns, and the rule
goes into a **separate key file** that the labeller does not open. The items are
shuffled as well: an unshuffled sheet is sorted by rule, and blindness that
survives until someone notices the sheet is in blocks is not blindness.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from ..plan import build_plan, resolve_selection
from ..rules import RULE_ORDER
from .schema import (
    LABEL_HELP,
    LABELS,
    SCHEMA_VERSION,
    SCORING_RULE,
    SENSITIVITY_WARNING,
)

# How many records either side of the result are shown. Enough that "was this
# needed again" is answerable — the answer is usually in the next turn or two —
# and bounded because a sheet with fifty turns per item is a sheet nobody fills
# in, and an unfilled sheet scores nothing.
DEFAULT_CONTEXT_BEFORE = 4
DEFAULT_CONTEXT_AFTER = 6

# Per-field bounds on what is quoted into the sheet. The result under judgement
# gets the most, because it is the thing being judged.
RESULT_CHARS = 1200
CONTEXT_CHARS = 400
ARGUMENT_CHARS = 300

DEFAULT_TARGET = 200


@dataclass(frozen=True)
class Candidate:
    """One stripped result, with everything the sheet and the key need."""

    session: str
    source_path: str
    pointer_id: str
    order: int
    rule: str
    tool: str
    arguments: str
    result_size: int
    result_excerpt: str
    before: list[str] = field(default_factory=list)
    after: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, int]:
        """What makes two candidates the same result. Stable across runs."""
        return (self.session, self.order)


def allocate(target: int, available: dict[str, int]) -> dict[str, int]:
    """Split `target` across the rules as evenly as their supply allows.

    Equal shares, then any rule that cannot fill its share hands the surplus back
    and the rules that still have room take it — repeated until nothing moves.
    The total is `min(target, sum(available))`; a corpus that cannot supply 200 is
    reported as a corpus that cannot supply 200 rather than padded out of the one
    rule that has plenty.

    The remainder after an equal split goes to the rules with the most left, in
    `RULE_ORDER` for ties, so the same corpus and target always allocate the same
    way. A tie broken by dict order would make the sample depend on which rule
    happened to fire first.
    """
    if target < 0:
        raise ValueError(f"target must not be negative, got {target}")
    # Checked before the `> 0` filter below, or a negative count would be dropped
    # by it and the sample would quietly be short by however many that rule was
    # owed. Rule names are checked here too, because the tie-break indexes
    # `RULE_ORDER` and an unknown name would otherwise surface as a bare
    # ValueError from `.index` with nothing in it about where it came from.
    for rule, count in available.items():
        if count < 0:
            raise ValueError(f"{rule}: available must not be negative, got {count}")
        if rule not in RULE_ORDER:
            raise ValueError(f"{rule!r} is not a rule; expected one of "
                             f"{', '.join(RULE_ORDER)}")
    supply = {rule: count for rule, count in available.items() if count > 0}
    taken = dict.fromkeys(supply, 0)
    remaining = min(target, sum(supply.values()))

    while remaining > 0:
        room = [rule for rule in supply if taken[rule] < supply[rule]]
        if not room:
            break
        share, spare = divmod(remaining, len(room))
        if share == 0:
            # Fewer left than there are rules with room: hand them out one each,
            # to the rules with the most still available. Otherwise the last few
            # of a 200 would all land on whichever rule is alphabetically first.
            order = sorted(
                room,
                key=lambda rule: (-(supply[rule] - taken[rule]), RULE_ORDER.index(rule)),
            )
            for rule in order[:spare]:
                taken[rule] += 1
            break
        moved = 0
        for rule in room:
            grant = min(share, supply[rule] - taken[rule])
            taken[rule] += grant
            moved += grant
        remaining -= moved
        if moved == 0:
            break
    return {rule: count for rule, count in taken.items() if count > 0}


def _text_of(block) -> str:
    """One content block reduced to something readable, or '' if it has none."""
    if isinstance(block, str):
        return block
    if not isinstance(block, dict):
        return ""
    kind = block.get("type")
    if kind == "text":
        return str(block.get("text", ""))
    if kind == "thinking":
        return str(block.get("thinking", ""))
    if kind == "tool_use":
        name = block.get("name", "?")
        return f"[calls {name}] " + _compact(block.get("input"))
    if kind == "tool_result":
        return "[tool result] " + _payload_text(block.get("content"))
    return ""


def _payload_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_text_of(b) for b in content)
    return _compact(content)


def _compact(value) -> str:
    try:
        text = json.dumps(value, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(value)
    return " ".join(text.split())


def _render_record(record: dict) -> str:
    """A transcript record as one line of context, or '' if there is nothing in it."""
    kind = record.get("type", "?")
    message = record.get("message")
    if not isinstance(message, dict):
        return "" if kind in ("summary", "system") else f"[{kind}]"
    role = message.get("role", kind)
    content = message.get("content")
    if isinstance(content, str):
        body = content
    elif isinstance(content, list):
        body = "\n".join(part for part in (_text_of(b) for b in content) if part)
    else:
        body = _compact(content)
    body = " ".join(body.split())
    return f"{role}: {body}" if body else ""


def _read_records(path: Path) -> list[dict]:
    """Every record in a transcript, in order, with unreadable lines kept as markers.

    A malformed line is not skipped: it is a turn the labeller would otherwise
    never know was there, and "nothing happened between these two turns" is
    exactly the wrong impression to give someone deciding whether a result was
    needed again.
    """
    records: list[dict] = []
    for number, line in enumerate(path.read_text("utf-8", errors="replace").splitlines(),
                                  start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            records.append({"type": f"unparseable record at line {number}"})
            continue
        records.append(payload if isinstance(payload, dict) else {"type": "non-object"})
    return records


def _result_index(records: list[dict], use_id: str) -> int | None:
    """Where the result for `use_id` sits, found by id rather than by line number.

    The plan carries a line index, but the plan's line numbering and this
    function's record numbering are two conventions that would have to agree, and
    a context window silently off by one is a labelling error nobody would catch.
    The id is the same in both.
    """
    for index, record in enumerate(records):
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_result"
                and block.get("tool_use_id") == use_id
            ):
                return index
    return None


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def candidates_for(
    path: Path,
    *,
    tier: str = "CB",
    before: int = DEFAULT_CONTEXT_BEFORE,
    after: int = DEFAULT_CONTEXT_AFTER,
    i_know: bool = False,
) -> list[Candidate]:
    """Every result `winnow plan` would strip in one session, with its context."""
    selection = resolve_selection(tier, i_know=i_know)
    plan = build_plan(path, tier=tier, rules=selection)
    if not plan.strips:
        return []
    records = _read_records(path)

    out: list[Candidate] = []
    for strip in plan.strips:
        index = _result_index(records, strip.use_id)
        if index is None:
            # The plan and the transcript disagree about where this result is.
            # Skipping is right here and would be wrong in `fork`, which raises
            # G5 on the same evidence: a sample is allowed to be one item smaller,
            # a fork is not allowed to be one block different.
            continue
        payload = ""
        message = records[index].get("message")
        if isinstance(message, dict):
            for block in message.get("content") or []:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_result"
                    and block.get("tool_use_id") == strip.use_id
                ):
                    payload = _payload_text(block.get("content"))
        out.append(
            Candidate(
                session=plan.session_id,
                source_path=str(path),
                pointer_id=strip.pointer_id,
                order=strip.order,
                rule=strip.rule,
                tool=strip.tool,
                arguments=_clip(strip.arguments, ARGUMENT_CHARS),
                result_size=strip.result_size,
                result_excerpt=_clip(payload, RESULT_CHARS),
                before=[
                    line
                    for line in (
                        _clip(_render_record(r), CONTEXT_CHARS)
                        for r in records[max(0, index - before - 1) : index - 1]
                    )
                    if line
                ],
                after=[
                    line
                    for line in (
                        _clip(_render_record(r), CONTEXT_CHARS)
                        for r in records[index + 1 : index + 1 + after]
                    )
                    if line
                ],
            )
        )
    return out


def collect(
    paths: list[Path],
    *,
    tier: str = "CB",
    before: int = DEFAULT_CONTEXT_BEFORE,
    after: int = DEFAULT_CONTEXT_AFTER,
    i_know: bool = False,
    on_error=None,
) -> list[Candidate]:
    """Candidates across a whole corpus, in path order.

    A session that cannot be planned is reported through `on_error` and skipped
    rather than ending the sweep: one malformed transcript in 563 should not cost
    the other 562.
    """
    out: list[Candidate] = []
    for path in paths:
        try:
            out.extend(
                candidates_for(path, tier=tier, before=before, after=after,
                               i_know=i_know)
            )
        except (ValueError, OSError) as exc:
            if on_error is not None:
                on_error(path, exc)
    return out


def draw(
    candidates: list[Candidate],
    target: int = DEFAULT_TARGET,
    seed: int = 0,
) -> list[Candidate]:
    """The stratified sample, shuffled, deterministic for a given seed.

    Sorting by `key` before sampling is what makes the seed mean anything: the
    corpus arrives in filesystem order, and a seeded draw over an unordered pool
    is reproducible only on the machine that produced that order.
    """
    pool: dict[str, list[Candidate]] = {}
    for candidate in sorted(candidates, key=lambda c: c.key):
        pool.setdefault(candidate.rule, []).append(candidate)

    quota = allocate(target, {rule: len(items) for rule, items in pool.items()})
    rng = random.Random(seed)
    drawn: list[Candidate] = []
    for rule in RULE_ORDER:
        take = quota.get(rule, 0)
        if take:
            drawn.extend(rng.sample(pool[rule], take))
    # Shuffled so the sheet is not in rule blocks. Blindness that holds only until
    # the labeller notices the sheet is sorted is not blindness.
    rng.shuffle(drawn)
    return drawn


def item_id(index: int) -> str:
    return f"{index + 1:04d}"


def render_sheet(drawn: list[Candidate], meta: dict) -> str:
    """The blind sheet. Carries no rule, anywhere, for any item."""
    out: list[str] = []
    add = out.append
    add("# winnow — blind labelling sheet")
    add("")
    add(f"- schema version: {meta['schema_version']}")
    add(f"- items: {len(drawn)}")
    add(f"- corpus: {meta['corpus']}")
    add(f"- tier: {meta['tier']}   seed: {meta['seed']}")
    add(f"- key file: {meta['key_path']}  — **do not open it until you are done**")
    add("")
    add("> [!WARNING]")
    for line in SENSITIVITY_WARNING.splitlines():
        add(f"> {line}")
    add("")
    add("## What you are deciding")
    add("")
    add("For each item: **was the content of this tool result needed again after "
        "the point it was produced?** You are shown the turns either side and not "
        "which rule selected it, because a label that can see the answer is not "
        "blind.")
    add("")
    add("Write one of these after `label:` on the item's own line.")
    add("")
    for label in LABELS:
        add(f"- `{label}` — {LABEL_HELP[label]}")
    add("")
    add("Every item needs a label. A sheet with a blank item is refused rather "
        "than scored over the rest of it.")
    add("")
    add("## How it will be scored")
    add("")
    for line in SCORING_RULE.splitlines():
        add(line if line else "")
    add("")
    add("---")
    add("")

    for index, candidate in enumerate(drawn):
        identifier = item_id(index)
        add(f"<!-- winnow:item {identifier} -->")
        add(f"### item {identifier}")
        add("")
        add(f"**The tool call** — `{candidate.tool}`")
        add("")
        add(f"> {candidate.arguments or '(no arguments)'}")
        add("")
        add(f"**The result under judgement** — {candidate.result_size:,} bytes, "
            "excerpt:")
        add("")
        for line in (candidate.result_excerpt or "(empty)").splitlines():
            add(f"> {line}")
        add("")
        add(f"**Before it** ({len(candidate.before)} turn(s))")
        add("")
        for line in candidate.before or ["(nothing — this is the start of the session)"]:
            add(f"> {line}")
        add("")
        add(f"**After it** ({len(candidate.after)} turn(s))")
        add("")
        for line in candidate.after or ["(nothing — this is the end of the session)"]:
            add(f"> {line}")
        add("")
        add(f"label:  <!-- {' / '.join(LABELS)} -->")
        add("")
        add(f"<!-- winnow:end {identifier} -->")
        add("")
    return "\n".join(out) + "\n"


def render_key(drawn: list[Candidate], meta: dict) -> str:
    """The answer key: one JSON object per line, item id first.

    Separate from the sheet rather than a hidden column in it, because "hidden"
    in a text file the labeller is editing means "one scroll away".
    """
    lines = [json.dumps({"meta": meta}, sort_keys=True, ensure_ascii=False)]
    for index, candidate in enumerate(drawn):
        lines.append(
            json.dumps(
                {
                    "item": item_id(index),
                    "rule": candidate.rule,
                    "session": candidate.session,
                    "source_path": candidate.source_path,
                    "pointer_id": candidate.pointer_id,
                    "order": candidate.order,
                    "tool": candidate.tool,
                    "result_size": candidate.result_size,
                },
                sort_keys=True,
                ensure_ascii=False,
            )
        )
    return "\n".join(lines) + "\n"


def build_meta(corpus_root: Path, tier: str, seed: int, key_path: Path,
               target: int, drawn: list[Candidate],
               available: dict[str, int]) -> dict:
    """What both files record about how the sample was drawn.

    `available` is in here so that a short sheet is self-explaining: 143 items
    because the corpus held 143 candidates is a different fact from 143 items
    because somebody passed `--target 143`, and only one of them is a reason to
    go and find more sessions.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "corpus": str(corpus_root),
        "tier": tier,
        "seed": seed,
        "target": target,
        "drawn": len(drawn),
        "key_path": str(key_path),
        "available_by_rule": {
            rule: available[rule] for rule in RULE_ORDER if rule in available
        },
        "drawn_by_rule": {
            rule: sum(1 for c in drawn if c.rule == rule)
            for rule in RULE_ORDER
            if any(c.rule == rule for c in drawn)
        },
    }
