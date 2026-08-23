# winnow

A long Claude Code session is mostly tool output: across 563 transcripts, 175.6 MB of message
content, `tool_result` and `tool_use` inputs are **91.6%** of the bytes and human plus assistant text
is 8.4% ([docs/SPEC.md](docs/SPEC.md) §1). Several tools will strip that for you. **None of them can
tell you whether stripping it saved you anything**, because the conversation sits in the cached
prefix at 0.1× and every edit to it forces a full-price rewrite of everything after the cut.

winnow is an attempt to answer that question and, if the answer comes back the right way, a pruner
that only fires when the arithmetic says it pays.

> [!IMPORTANT]
> **Nothing of winnow runs. There is no `src/winnow/`.** This repository holds five documents and a
> vendored copy of somebody else's working tool, kept as the thing to measure against. The
> deliverable of the first milestone is a number, not a binary, and the number has not been produced.
> [What is here today](#what-is-here-today) is the inventory, and it is short.

---

## The question

Removing half your conversation does not halve your bill. It is not obvious that it lowers it at all.

Cache reads bill at 0.1× and writes at 1.25× (five-minute) or 2× (one hour). Matching is exact and
prefix-ordered, so an edit invalidates everything after the cut point. Let *S* be the suffix after
the cut and *D* the bytes removed from it. The edit pays `1.9·S − 2·D` once, and earns `0.1·D` back on
every later turn, so it breaks even after

```
T* = 19·(S/D) − 20   further turns
```

Cut half the suffix and it pays for itself in 18 turns. Cut a tenth and it needs 170 more turns than
the session has had, and in the corpus that was measured only 807 turns out of 11,422 sat past index
160 at all. The 2.0× figure is not the
list-price assumption: it is a measurement over 26,194 turns of one install where every main-thread
turn wrote at the one-hour class, and it is recorded outside this repository in
`UsageFoundry/proposals/ContextControl/01-constraints.md`.

Three things follow, and they are the whole design:

- **`S/D` decides, not the size of the session.** The formula is model-independent and absolute size cancels. A big session is not automatically worth pruning.
- **There is exactly one moment when the edit is free.** Immediately before a handover that was going to rewrite the suffix anyway, the `2·D` term is refunded. winnow acts at resume boundaries for this reason, not out of caution ([docs/SPEC.md](docs/SPEC.md) §7).
- **The deliverable is a comparison, not a saving.** Every existing tool reports bytes or tokens removed. None reports the netted cost, and none has ever been measured against task quality ([docs/SPEC.md](docs/SPEC.md) §2).

I got this arithmetic wrong myself, once, by assuming the 1.25× multiplier from the documentation
instead of reading the measurement: that version understated invalidation by about 40 percent.
[docs/COZEMPIC.md](docs/COZEMPIC.md) §3.1 keeps the error on the record, because it is exactly the
mistake the measurement exists to catch.

## What is here today

| | |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | The specification. Content split by class, the classification rules and what they cannot decide, the six universal guards, the retrieval path, the CLI surface, and success criteria whose primary metric is deliberately not token reduction. **Not yet reconciled against the vendored code**; [docs/COZEMPIC.md](docs/COZEMPIC.md) is that reconciliation |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Eight decisions with the alternatives rejected and the cost of being wrong, plus §0, which decides what Cozempic is doing in this repository |
| [docs/MILESTONES.md](docs/MILESTONES.md) | Ten working days in three milestones, and the kill criteria, decided in advance while nobody is attached to the outcome |
| [docs/COZEMPIC.md](docs/COZEMPIC.md) | The vendored tool against the spec, decision by decision: six questions its code already answers, eight places the two disagree with a verdict and a reason on each, and what is still open |
| [docs/USAGEFOUNDRY.md](docs/USAGEFOUNDRY.md) | Eleven collisions between the vendored tool and the orchestrator that would run it, with evidence on both sides, and how any of this gets verified |
| [docs/behavioral-digest-design.md](docs/behavioral-digest-design.md) | Cozempic's own design note, arrived with the merge |
| `src/cozempic/`, `plugin/`, `npm/`, `packaging/`, `tests/` | Cozempic 1.8.39, about 21,700 lines, vendored unmodified. Not winnow, not installed, not started |

**No winnow code, no CLI, no `winnow inspect`.** The numbers the documents cite as measured were
produced by analysis scripts in earlier work and are recorded with their sample sizes; nothing in
this checkout reproduces them yet.

## The vendored tool

`src/cozempic/` is [Cozempic](https://github.com/Ruya-AI/cozempic) 1.8.39 by Ruya AI, in-tree at a
pinned upstream commit. It is real, working software: 18 pruning strategies in three tiers, a
nine-invariant validator that refuses any prune leaving a `tool_use` without its result, a floor pass
that re-adds the last 10 turns, a guard daemon, five hooks and a doctor with 15 checks. Its test
suite passes here (see below).

It is here as **one arm of a measurement**, and [docs/DECISIONS.md](docs/DECISIONS.md) §0 argues that
choice against four alternatives. Two consequences worth stating on the front page:

**It is read-only.** No change to `src/cozempic/` belongs in this repository. `winnow bench` needs a
byte-stable baseline, and Cozempic upgrades itself from PyPI on every session start and every CLI
invocation, so pinning it as a dependency would let the baseline move underneath the measurement.
Changes wanted in the tool go upstream.

**It is not installed, and that is deliberate.** Installing it starts a daemon that can `SIGKILL` a
live editor, writes hooks into `~/.claude/settings.json`, and, in its default tier, strips the
`usage` fields that any cost measurement is computed from. A session Cozempic has pruned cannot be
used to evaluate whether Cozempic's pruning paid.
[docs/USAGEFOUNDRY.md](docs/USAGEFOUNDRY.md) §4 lists what has to be off first, including the two
features that have no off switch.

**This repository makes none of Cozempic's claims.** Its README advertises "85-95% savings" on one
strategy. That figure is *file bytes removed*, which is not tokens and is not money, and it is stated
without the cache write it costs. Working out what it would have to be measured against is
[docs/COZEMPIC.md](docs/COZEMPIC.md) §3.1; the honest summary there is that the measurement can
falsify a one-armed claim but cannot prove one tool superior to another without the quality arm that
nobody has run.

## Running the tests

The suite is Cozempic's, and it is the only executable check in the repository.

```sh
python3 -m venv .venv && .venv/bin/pip install -q pytest
.venv/bin/python -m pytest -q -p no:cacheprovider
```

Measured on this tree, 2026-08-23: **1882 passed, 2 failed, 17 skipped**, in about 40 seconds. Both
failures are in `tests/test_guard_hardening.py::TestG4_PidfileWriteIsAtomic`, both are pre-existing
on the merge commit, and neither is attributable to the code with confidence: the same race
reproduced outside pytest behaves correctly, and the guard's pidfile path is hardcoded to `/tmp`
where it cannot be redirected. A change that leaves the count at two has broken nothing the suite
covers.

Some sandboxes ship `python3` without `pip` or `venv`, in which case the recipe above fails at line
one; [docs/USAGEFOUNDRY.md](docs/USAGEFOUNDRY.md) §7 has a bootstrap that needs neither, and the
one-line fix to the image that makes it unnecessary.

## What it is not

- **Not a wrapper around `claude`.** winnow will print the `claude --resume <new-id>` line; the operator runs it. Staying out of the spawn path means it cannot break a run and has no opinion about flags, budgets or permissions.
- **Not a daemon, and it never touches a live session.** The vendor's own hooks reference says the transcript "is written asynchronously and may lag the in-memory conversation": editing the file mid-session is not merely unsafe, it does not change what gets sent.
- **Not destructive.** Copy-on-write only. The original transcript is opened read-only and is both the archive and the recovery source; winnow adds files and never removes them.
- **No model call, no network, no MCP server.** Not a style preference: a summariser would put the thing being measured inside the instrument, and one added tool definition sits at the top of the invalidation cascade and was priced at $8.14 to $8.26 a week against $0.14 of benefit per use.
- **Not a competitor to Cozempic.** They are two tools for two shapes of session, and [docs/COZEMPIC.md](docs/COZEMPIC.md) §2.1 says which shape each one is right for.

Full list with reasons: [docs/SPEC.md](docs/SPEC.md) §3.

## Status

| | |
|---|---|
| Specification, decisions, milestone plan and kill criteria | **written** |
| Content-composition measurement, 563 transcripts | **done**, in earlier analysis; not reproducible from this checkout |
| Milestone 1, `winnow inspect` and the cache readout | **not started** |
| Milestone 2, the rules, the guards and `winnow fork` | **not started** |
| Milestone 3, `winnow bench` and the quality arm | **not started** |
| Any claim that pruning a Claude Code session saves money | **unmade, by anyone** |

The last row is the project. If the first milestone comes back saying the cache is already warm at a
typical resume, or that the strippable share at tier CB does not reproduce, the kill criteria in
[docs/MILESTONES.md](docs/MILESTONES.md) say to stop, and stopping then is the intended outcome
rather than a failure of it.

## Licence and attribution

[`LICENSE`](LICENSE) is **Ruya AI's MIT notice**, and it arrived with the vendored tree. It covers
`src/cozempic/`, `plugin/`, `npm/`, `packaging/` and `tests/`. It is not winnow's licence, and
winnow's licence has not been chosen. [`CONTRIBUTORS.md`](CONTRIBUTORS.md) credits Cozempic's
contributors, and stays for the same reason: the attribution obligation is real whatever this
repository decides to become.
