"""SPEC §4's classification rules, guards and pointer — the one engine.

`inspect` prices a cut that has not happened, `plan` says exactly what would go,
and `fork` writes it. If any two of those disagreed about what rule B1 means, the
number milestone 1 published would not describe the file milestone 2 writes. So
the rules live here and each command imports them; `inspect.py` re-exports the
names it used to define, because milestone 1's callers import them from there.

Four things in here are easy to get subtly wrong, so they are stated once:

**Rules are first-match-wins, in the order C1, C2, C3, B1, B2, A1.** SPEC §6's
per-rule table sums to its own tier totals, which is only true if every result is
attributed to exactly one rule. Attributing a result to every rule that matches
would double-count it.

**Rule selection is which rules may fire, not which attributions survive.** SPEC
§8 lets `--rule`/`--no-rule` override a tier, and the two readings come apart: a
duplicated `ls` matches C2 first and B2 second, so filtering *after* a full-order
classification would drop it entirely when C2 is off, rather than letting B2
claim it. `classify` therefore takes the enabled set and skips disabled rules in
place. For the three tiers the readings agree — C and CB are prefixes of
RULE_ORDER, so a C-tier rule always wins before a B-tier one is reached — which
is why `inspect`'s tier arithmetic is unaffected.

**Guards run before rules, never after.** A result G1, G2 or G3 protects never
enters the rule engine, so it cannot appear in a per-rule share. G4 is the one
exception and it cannot be otherwise: it compares the result against the pointer
that would replace it, and the pointer names the rule that fired, so it can only
be decided once a rule has. It is applied by `plan` and `fork` rather than by
`inspect`, which measures the ceiling SPEC §6 published rather than the cut.

**The measure is SPEC §6's measure, not a byte count.** `len()` of the content
string, or of `json.dumps()` for a structured result. On ASCII the two agree; on
anything else they do not, and the baseline this reproduces was taken with
`len()`. The pointer is measured the same way, so G4 compares like with like.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# ─── SPEC §4 rule patterns ───────────────────────────────────────────────────

# C1: the output is a list of paths whose only consumer is the call that
# followed it.
LOCATOR_TOOLS = frozenset({"Glob", "LS"})
LOCATOR_GREP_MODES = frozenset({"files_with_matches", "count"})

# C3: a verification run that passed. A failing one is never stripped — the
# failure is the information (SPEC §4 C3, and guard G3 independently).
VERIFICATION_RE = re.compile(
    r"\b("
    r"(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:test|build|lint|typecheck|check)"
    r"|pytest"
    r"|go\s+(?:test|build|vet)"
    r"|cargo\s+(?:test|build|clippy)"
    r"|tsc"
    r"|eslint"
    r"|make\s+(?:test|build|check)"
    r"|jest"
    r"|vitest"
    r"|ruff"
    r"|mypy"
    r")\b"
)

# B2: inspection commands. Matching is on the first token of the first segment,
# so a pipeline whose head is `ls` counts and one whose head is `python` does
# not, whatever follows (SPEC §4 B2).
INSPECTION_HEADS = frozenset({
    "ls", "cat", "head", "tail", "find", "grep", "rg", "wc", "tree", "pwd",
    "which", "type", "file", "stat", "du", "df", "env", "printenv", "echo",
    "jq", "awk", "sort", "uniq", "column", "nl", "realpath", "basename",
    "dirname",
})
INSPECTION_GIT_SUBCOMMANDS = frozenset({
    "status", "log", "diff", "show", "branch", "remote", "ls-files",
})

# A1: the tools whose call makes an earlier Read of the same path stale.
MUTATING_TOOLS = frozenset({"Edit", "Write"})

RULE_ORDER = ("C1", "C2", "C3", "B1", "B2", "A1")
RULE_TIER = {"C1": "C", "C2": "C", "C3": "C", "B1": "B", "B2": "B", "A1": "A"}

# Can this rule's verdict be reached from the call and its own result, without
# seeing anything later in the conversation?
#
# The question matters to exactly one caller and it is not the pruner. The intake
# filter rewrites a live request and must render the same conversation to the same
# bytes every time, or it changes the prefix under the cache and destroys the thing
# it exists to protect. A rule whose verdict can move once a later turn arrives is
# therefore inadmissible there, whatever its precision. C2 needs a later duplicate,
# B1 a later read, A1 a later edit.
#
# Beside `RULE_TIER` rather than as a comment in `filter.py`, and for the reason
# `OPT_IN_RULES` gives one line further down: a property of a rule belongs where
# the rule is declared, so that the day a seventh rule is written is the day
# somebody has to answer this question about it rather than the day somebody
# remembers to ask.
PREFIX_DETERMINED = {
    "C1": True, "C2": False, "C3": True, "B1": False, "B2": True, "A1": False,
}
STATELESS_RULES = frozenset(rule for rule in RULE_ORDER if PREFIX_DETERMINED[rule])
TIER_RULES = {
    "C": ("C1", "C2", "C3"),
    "CB": ("C1", "C2", "C3", "B1", "B2"),
    "CBA": RULE_ORDER,
}
ALL_RULES = frozenset(RULE_ORDER)

# Tier A is opt-in and never a default (SPEC §4). Named as a set rather than
# spelled `A1` at each call site, because the day a second A-tier rule exists is
# the day a hard-coded `A1` quietly stops gating it.
OPT_IN_RULES = frozenset(rule for rule in RULE_ORDER if RULE_TIER[rule] == "A")

# SPEC §8 defaults.
DEFAULT_KEEP_LAST = 6
DEFAULT_MIN_BYTES = 2048

# ─── Rules a measurement is allowed to switch off ────────────────────────────

# MILESTONES milestone 2: "a rule below 90% on its own is disabled by default
# even if the aggregate passes". This is the defaults side of SPEC §8's
# `--rule`/`--no-rule`, and the two halves are not the same thing: `--no-rule`
# is one operator's choice on one run, this is what the tool believes about a
# rule until a better measurement moves it.
#
# **Empty, and it stays empty until the 200-sample blind label has been scored.**
# A rule turned off here without a number behind it would be the tool asserting
# a precision nobody measured, which is the failure mode this whole milestone
# exists to avoid. docs/MILESTONE-2-VALIDATION.md is the procedure that fills it.
DISABLED_BY_DEFAULT: frozenset[str] = frozenset()

# The override, so that the labelling result can be acted on the hour it lands
# rather than waiting for a release. It *replaces* DISABLED_BY_DEFAULT rather
# than adding to it, so `WINNOW_RULES_OFF=` (empty) is the way to run with every
# rule its tier names — an override that could only ever subtract more would be
# a switch with no off position.
RULES_OFF_ENV = "WINNOW_RULES_OFF"


class RuleSelectionError(ValueError):
    """A `--tier`, `--rule` or `--no-rule` that names something that is not a rule."""


def default_disabled(env: Mapping[str, str] | None = None) -> frozenset[str]:
    """The rules that are off by default: `DISABLED_BY_DEFAULT`, or `$WINNOW_RULES_OFF`.

    Separators are commas or whitespace, so `B2,A1` and `"B2 A1"` both work. A
    name that is not a rule raises rather than being skipped: an operator who
    typed `WINNOW_RULES_OFF=B3` meant to turn something off, and silently
    turning nothing off would leave them believing a rule was disabled when it
    was firing.
    """
    environ = os.environ if env is None else env
    raw = environ.get(RULES_OFF_ENV)
    if raw is None:
        return DISABLED_BY_DEFAULT
    names = [token for token in re.split(r"[,\s]+", raw) if token]
    try:
        return frozenset(_valid_rule(name) for name in names)
    except RuleSelectionError as exc:
        raise RuleSelectionError(f"{RULES_OFF_ENV}: {exc}") from exc


def resolve_rules(
    tier: str,
    enable: Iterable[str] = (),
    disable: Iterable[str] = (),
    disabled_by_default: Iterable[str] | None = None,
) -> frozenset[str]:
    """The rules that may fire, per SPEC §8: a tier, the defaults, then the overrides.

    The order is tier → minus the default-off set → plus `--rule` → minus
    `--no-rule`, and each step is doing one job. A default-off rule is subtracted
    before `--rule` so that naming it explicitly turns it back on: the default
    says what the tool believes without instruction, not what it will refuse to
    do. `--no-rule` is applied last so it always wins, which is why
    `--rule B1 --no-rule B1` disables B1 whatever order the two were typed in.

    `disabled_by_default=None` reads `default_disabled()`, which is the shipped
    set unless `$WINNOW_RULES_OFF` overrides it. Pass an explicit iterable —
    including `()` — to decide it at the call site instead; `inspect` does, because
    SPEC §6's per-rule table is the ceiling of the mechanism and a rule switched
    off for precision has not stopped being part of that ceiling.

    Naming a rule that does not exist is a usage error rather than a silent
    no-op — SPEC §10 forbids a fallback that silently keeps a result the operator
    asked to strip.
    """
    if tier not in TIER_RULES:
        raise RuleSelectionError(
            f"unknown tier {tier!r}; expected one of {', '.join(TIER_RULES)}"
        )
    off = (
        default_disabled()
        if disabled_by_default is None
        else frozenset(_valid_rule(rule) for rule in disabled_by_default)
    )
    selected = set(TIER_RULES[tier]) - off
    for rule in enable:
        selected.add(_valid_rule(rule))
    for rule in disable:
        selected.discard(_valid_rule(rule))
    return frozenset(selected)


def suppressed_by_default(
    tier: str,
    enable: Iterable[str] = (),
    disable: Iterable[str] = (),
    disabled_by_default: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """Which rules the tier named that the default-off set took away, in RULE_ORDER.

    Exists so a readout can say it. A tier that quietly means fewer rules than
    its own name lists is the silent-fallback SPEC §10 forbids, and the operator
    who most needs to be told is the one reading a share that came in lower than
    the last time they ran it.

    A rule the operator also passed `--no-rule` for is not listed: they turned it
    off themselves, and attributing their own choice to a default would misreport
    where the decision came from.
    """
    if tier not in TIER_RULES:
        raise RuleSelectionError(
            f"unknown tier {tier!r}; expected one of {', '.join(TIER_RULES)}"
        )
    off = (
        default_disabled()
        if disabled_by_default is None
        else frozenset(_valid_rule(rule) for rule in disabled_by_default)
    )
    restored = {_valid_rule(rule) for rule in enable}
    chosen_off = {_valid_rule(rule) for rule in disable}
    return tuple(
        rule
        for rule in RULE_ORDER
        if rule in TIER_RULES[tier]
        and rule in off
        and rule not in restored
        and rule not in chosen_off
    )


def _valid_rule(rule: str) -> str:
    normalised = rule.strip().upper()
    if normalised not in ALL_RULES:
        raise RuleSelectionError(
            f"unknown rule {rule!r}; expected one of {', '.join(RULE_ORDER)}"
        )
    return normalised


@dataclass
class ToolCall:
    """One `tool_use` and the `tool_result` that answered it.

    `order` is the position among tool calls, which is what guard G1 counts in
    and what the pointer ID is built from; `line` is the transcript line of the
    result, which is what the cut point is measured from. `use_id` is the
    `tool_use_id` the two blocks share, and is how a writer finds the block to
    replace without re-deriving the pairing.
    """

    order: int
    line: int
    name: str
    tool_input: dict
    result_size: int
    is_error: bool
    has_result: bool
    use_id: str = ""
    digest: str = ""


# ─── Measurement ─────────────────────────────────────────────────────────────


def result_payload(content) -> str:
    """The exact text SPEC §6 measures and the pointer digests.

    One function rather than two so that the size in a pointer and the hash in
    the same pointer can never describe different renderings of the same result.
    """
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    try:
        return json.dumps(content)
    except (TypeError, ValueError):
        # A result carrying something json cannot serialise is still content the
        # session pays for every turn. Falling back to repr() keeps it counted;
        # returning "" would quietly shrink the denominator.
        return repr(content)


def result_size(content) -> int:
    """SPEC §6's measure of a `tool_result` content: `len(str)` or `len(json.dumps(list))`."""
    return len(result_payload(content))


def content_digest(content) -> str:
    """sha256 of the payload, hex. What the pointer carries and `recover` checks."""
    return hashlib.sha256(result_payload(content).encode("utf-8", "surrogateescape")).hexdigest()


def input_size(tool_input) -> int:
    if tool_input is None:
        return 0
    try:
        return len(json.dumps(tool_input))
    except (TypeError, ValueError):
        return len(repr(tool_input))


def canonical_input(tool_input) -> str:
    """The key C2 compares on. Sorted so that key order cannot make two
    identical calls look different."""
    try:
        return json.dumps(tool_input, sort_keys=True)
    except (TypeError, ValueError):
        return repr(tool_input)


def bash_head(command: str) -> str | None:
    """The first token of the first segment, normalised for SPEC §4 B2.

    Returns `git status`-style two-token heads for git, `sed -n` for the one
    inspection use of sed, and the bare token otherwise. None when there is no
    token to match.
    """
    if not isinstance(command, str):
        return None
    # `&&` and `|` are the separators SPEC §4 B2 names. `||` and `|&` are caught
    # by the `|` split; `;` is deliberately not, because SPEC named two.
    segment = re.split(r"&&|\|", command, maxsplit=1)[0]
    tokens = segment.split()
    if not tokens:
        return None
    head = tokens[0]
    # A leading `VAR=value` is the shell setting the environment for the command
    # that follows, not the command. Skipping it means `FOO=1 ls` is still an
    # `ls`; not skipping it would make the head `FOO=1` and match nothing.
    while "=" in head and not head.startswith("=") and len(tokens) > 1:
        tokens = tokens[1:]
        head = tokens[0]
    head = head.rsplit("/", 1)[-1]  # /bin/ls → ls
    if head == "git" and len(tokens) > 1:
        return f"git {tokens[1]}"
    if head == "sed":
        return "sed -n" if "-n" in tokens[1:2] else "sed"
    return head


def is_inspection(command: str) -> bool:
    head = bash_head(command)
    if head is None:
        return False
    if head in INSPECTION_HEADS or head == "sed -n":
        return True
    if head.startswith("git "):
        return head.split(" ", 1)[1] in INSPECTION_GIT_SUBCOMMANDS
    return False


def read_range(tool_input: dict) -> tuple[str | None, int, float]:
    """`(file_path, start, end)` for a Read, with a missing range meaning the
    whole file.

    SPEC §4 B1 compares ranged reads on `(file_path, offset, limit)` and
    supersedes one only by a read that provably covers its range. A read with
    neither offset nor limit is the whole file, so it covers everything and is
    covered by nothing narrower — which is why `end` is a float: `inf` is the
    only honest upper bound for "to the end of a file whose length is not in the
    transcript".
    """
    path = tool_input.get("file_path")
    if not isinstance(path, str):
        return None, 0, float("inf")
    offset = tool_input.get("offset")
    limit = tool_input.get("limit")
    if offset is None and limit is None:
        return path, 0, float("inf")
    start = offset if isinstance(offset, int) and offset > 0 else 1
    if not isinstance(limit, int) or limit <= 0:
        return path, start, float("inf")
    return path, start, start + limit


# ─── The rule engine ─────────────────────────────────────────────────────────


def classify(
    calls: list[ToolCall],
    keep_last: int,
    min_bytes: int,
    enabled: frozenset[str] | None = None,
) -> tuple[dict[int, str], dict[str, int]]:
    """Attribute each tool call to the first enabled SPEC §4 rule that fires.

    Returns `(order → rule id)` and a count of what each guard refused, so a
    session where the guards did all the work is distinguishable from one where
    no rule matched. `enabled` defaults to every rule, which is what `inspect`
    passes: its per-rule table is the ceiling, and a tier is applied to the
    result by summing (SPEC §6).
    """
    if enabled is None:
        enabled = ALL_RULES
    guard_blocked = {"G1_keep_last": 0, "G2_min_bytes": 0, "G3_errors": 0, "G5_unpaired": 0}
    eligible: list[ToolCall] = []
    cutoff = len(calls) - keep_last

    for call in calls:
        if not call.has_result:
            # G5 in its read-only form. A `tool_use` with no `tool_result` is the
            # last in-flight call of a session (SPEC §4 measured 5 across 42,966);
            # there is nothing to strip and nothing to pair.
            guard_blocked["G5_unpaired"] += 1
            continue
        if call.order >= cutoff:
            guard_blocked["G1_keep_last"] += 1
            continue
        if call.result_size < min_bytes:
            guard_blocked["G2_min_bytes"] += 1
            continue
        if call.is_error:
            guard_blocked["G3_errors"] += 1
            continue
        eligible.append(call)

    # C2 and B1 and A1 each need to know what happens *later* in the session, so
    # the indices are built once over every call — not only the eligible ones. A
    # guarded result still supersedes an earlier one: the guard protects the
    # result from being stripped, it does not make the call invisible.
    # C2 supersedes an earlier *result* with a later *result*: SPEC §4 words it as
    # "an earlier `tool_result` … byte-identical to a later one". A later call
    # that never returned has no bytes to supersede with, so it is not an index
    # entry — unlike B1 and A1 below, which SPEC words on `tool_use` and which
    # therefore do count a call whose result never arrived.
    last_input_seen: dict[tuple[str, str], int] = {}
    for call in calls:
        if call.has_result:
            last_input_seen[(call.name, canonical_input(call.tool_input))] = call.order

    reads: list[tuple[int, str, int, float]] = []
    mutations: dict[str, list[int]] = {}
    for call in calls:
        if call.name == "Read":
            path, start, end = read_range(call.tool_input)
            if path is not None:
                reads.append((call.order, path, start, end))
        elif call.name in MUTATING_TOOLS:
            path = call.tool_input.get("file_path")
            if isinstance(path, str):
                mutations.setdefault(path, []).append(call.order)

    assigned: dict[int, str] = {}
    for call in eligible:
        rule = _first_matching_rule(call, last_input_seen, reads, mutations, enabled)
        if rule is not None:
            assigned[call.order] = rule
    return assigned, guard_blocked


_ONLY = {rule: frozenset({rule}) for rule in RULE_ORDER}


def stateless_rule_for(
    name: str,
    tool_input: Mapping,
    enabled: frozenset[str] = STATELESS_RULES,
) -> str | None:
    """C1, C3 or B2 — the rules whose verdict is fixed by the call alone.

    **The one owner of what "a locator", "a passing verification" and "an
    inspection" mean.** Both `_first_matching_rule` below and `filter.rule_for`
    reach it, so the order these three are tested in, what counts as a Bash
    command, and which `Grep` modes are locators cannot come apart between the
    component that prices a cut and the component that makes one on a live wire.
    Before this they were the same control flow written twice from the same
    constants, and the copy was faithful on all 63,931 non-error results in this
    corpus — which says it is faithful *today*, not that it will stay so.

    **It does not check `is_error`, and that is the contract.** Guard G3 belongs
    to the caller: `classify` applies it before the engine is entered, along with
    G1, G2 and G5, and `filter.rule_for` applies it itself because it is handed
    unguarded input. Calling this with an error result would newly claim 753
    results on this corpus, 19 of them above the 2,048-byte floor — and G3 is
    "errors survive, at any tier", with C3's whole rationale being that a failing
    verification is the information. Stripping a failed `pytest` from a request
    before the model reads it would remove the one result the turn existed to
    produce. So the naive merge — delete `rule_for`, call the shared engine — is a
    regression, not a refactor, and this signature is what makes that impossible
    to write by accident: there is no `is_error` parameter to forget to pass.
    """
    if "C1" in enabled:
        if name in LOCATOR_TOOLS:
            return "C1"
        if name == "Grep" and tool_input.get("output_mode") in LOCATOR_GREP_MODES:
            return "C1"
    if name == "Bash":
        command = tool_input.get("command")
        if "C3" in enabled and isinstance(command, str) and VERIFICATION_RE.search(command):
            return "C3"
        if "B2" in enabled and is_inspection(command):
            return "B2"
    return None


def _first_matching_rule(
    call: ToolCall,
    last_input_seen: dict[tuple[str, str], int],
    reads: list[tuple[int, str, int, float]],
    mutations: dict[str, list[int]],
    enabled: frozenset[str],
) -> str | None:
    """The first enabled rule in C1, C2, C3, B1, B2, A1 that fires on this call.

    First-match-wins is what makes SPEC §6's per-rule table sum to its own tier
    totals; see the module docstring.

    The three prefix-determined rules are delegated to `stateless_rule_for`, one
    rule at a time rather than in one call, because C2 sits between C1 and C3 in
    RULE_ORDER and B1 between C3 and B2. Interleaving is the point: the order is
    load-bearing and it now has one definition.
    """
    name = call.name
    tool_input = call.tool_input

    # C1 locator.
    if stateless_rule_for(name, tool_input, enabled & _ONLY["C1"]) is not None:
        return "C1"

    # C2 exact duplicate — only the earlier of an identical pair is stripped.
    if "C2" in enabled and (
        last_input_seen.get((name, canonical_input(tool_input)), call.order) > call.order
    ):
        return "C2"

    if name == "Bash":
        # C3 passing verification. `is_error` was already excluded by G3, so
        # reaching here means the run passed.
        if stateless_rule_for(name, tool_input, enabled & _ONLY["C3"]) is not None:
            return "C3"
        # B2 Bash inspection.
        if stateless_rule_for(name, tool_input, enabled & _ONLY["B2"]) is not None:
            return "B2"
        return None

    if name == "Read":
        path, start, end = read_range(tool_input)
        if path is None:
            return None
        # B1 superseded read: a later Read of the same path that provably covers
        # this range.
        if "B1" in enabled:
            for order, other_path, other_start, other_end in reads:
                if (
                    order > call.order
                    and other_path == path
                    and other_start <= start
                    and other_end >= end
                ):
                    return "B1"
        # A1 read then written, with no intervening Read of that path. An
        # intervening read is the one adjacent to the edit; this one would be
        # superseded by it under B1 rather than made stale by the edit.
        if "A1" in enabled:
            for edit_order in mutations.get(path, ()):
                if edit_order <= call.order:
                    continue
                intervening = any(
                    call.order < order < edit_order and other_path == path
                    for order, other_path, _, _ in reads
                )
                if not intervening:
                    return "A1"
    return None


# ─── SPEC §4 "The pointer" ───────────────────────────────────────────────────

# How much of the session ID the recovery command quotes. SPEC §4's worked
# example shows eight characters, and `report.resolve_session` refuses an
# ambiguous prefix loudly rather than guessing — so on the vanishingly unlikely
# day two session IDs share their first eight characters, the operator is told
# to type a longer one rather than shown the wrong bytes.
SESSION_REF_CHARS = 8

# SPEC §4's example renders the digest elided, as `9f2c…a1`, and the whole
# pointer at "~120 bytes". This carries all 64 hex characters instead, at a cost
# of about 58, and the reason is milestone 2's own acceptance criterion: recover
# "prints bytes whose SHA-256 matches the digest in the pointer". Six hex
# characters is 24 bits, which cannot tell a correct recovery from a wrong one,
# and a digest that cannot be checked is decoration. Everything else — the four
# facts SPEC's prose requires, and the two-line layout — is as written there.
POINTER_TEMPLATE = (
    "[winnow: {tool} result removed, rule {rule}, {size:,} bytes, sha256 {digest}\n"
    " recover: winnow recover {session} {pointer_id} ]"
)


def session_ref(session_id: str) -> str:
    """The session as the recovery command quotes it."""
    return session_id[:SESSION_REF_CHARS]


def pointer_id(rule: str, order: int) -> str:
    """The stable ID `winnow recover <session> <id>` looks a result up by.

    The scheme is **the tier letter of the rule that fired, lowercased, followed
    by the call's ordinal position among the session's tool calls** — so the
    eighth tool call, stripped by rule B2, is `b7`, which is the ID in SPEC §4's
    worked example.

    Both halves are properties of the transcript rather than of this run, which
    is what makes the ID deterministic and stable in the sense SPEC §10 requires:
    no counter, no timestamp, no hash of anything that could be re-rendered
    differently, and no dependence on how many *other* results were stripped. Two
    plans over the same transcript agree, and a plan agrees with the fork written
    from it. The ordinal is unique within a session and each call is attributed
    to at most one rule, so the ID is unique too.

    The tier letter earns its place by making `recover` self-checking without a
    side store — SPEC §3 forbids "a fourth store", so the only index is the
    original transcript, and an ID that names the tier lets a lookup verify it
    landed on the kind of result the pointer claims. The letter does move if the
    operator changes `--rule`/`--no-rule` such that a different rule claims the
    same call; that is not a stability problem, because every pointer in one fork
    was written under one selection and carries its own rule in its own text.
    """
    return f"{RULE_TIER[rule].lower()}{order}"


_POINTER_ID_RE = re.compile(r"^([a-z])(\d+)$")


def parse_pointer_id(value: str) -> tuple[str, int]:
    """`(tier letter uppercased, call order)`, the inverse of `pointer_id`.

    Here rather than in the recovery path so that the scheme is defined once, by
    code, and its round trip is testable without a written fork.
    """
    match = _POINTER_ID_RE.match(value.strip())
    if match is None:
        raise ValueError(
            f"malformed pointer id {value!r}; expected a tier letter followed by "
            "the call's ordinal, as in 'b7'"
        )
    tier = match.group(1).upper()
    if tier not in ("C", "B", "A"):
        raise ValueError(f"pointer id {value!r} names tier {tier!r}, which is not C, B or A")
    return tier, int(match.group(2))


def render_pointer(
    tool: str,
    rule: str,
    size: int,
    digest: str,
    session_id: str,
    identifier: str,
) -> str:
    """The text that replaces a `tool_result`'s content.

    Never interpolates transcript content: SPEC §10 treats the transcript as
    untrusted input, and the only things from it that reach this string are a
    tool name, a length and a hash. The tool name is the one value that is not
    fixed by winnow, so it is stripped of anything that could break the pointer's
    own shape.
    """
    return POINTER_TEMPLATE.format(
        tool=_safe_tool_name(tool),
        rule=rule,
        size=size,
        digest=digest,
        session=session_ref(session_id),
        pointer_id=identifier,
    )


_UNSAFE_TOOL_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_tool_name(tool: str) -> str:
    """A tool name reduced to what an MCP tool id can legitimately contain.

    `tool_use.name` arrives from the transcript, and a transcript is untrusted
    (SPEC §10). A name carrying a newline would forge a second pointer line; one
    carrying 40 KB would defeat G4's whole purpose. Both are bounded here.
    """
    cleaned = _UNSAFE_TOOL_CHARS.sub("_", tool or "?")[:64]
    return cleaned or "?"


def inflates(pointer: str, size: int) -> bool:
    """Guard G4: is the pointer longer than the content it would replace?

    SPEC §4 G4 says "if the pointer is longer than the content it replaces, the
    content stays", and the comparison here is literally that — strictly longer.
    An exactly-equal swap removes nothing but inflates nothing either, which is
    what the guard is named for. Both sides are measured in `len()`, SPEC §6's
    unit, so the comparison is like with like.
    """
    return len(pointer) > size
