# winnow

Reads a finished Claude Code session off disk, replaces the tool results a stated rule
says were needed once, and writes a new session you can resume from. No model is called
to make that decision, and the original file is never touched.

> [!IMPORTANT]
> **Nothing is built.** This repository contains four documents and no code. There is no
> package manifest, no entry point, no tests. What exists is a project definition,
> written 2026-08-23, and the measurements that justify or kill it.
>
> Read [docs/DECISIONS.md](docs/DECISIONS.md) §1 before anything else. It says why this
> project probably should not be built as an actuator, and what it is worth building as
> an instrument.

---

## The honest case against it, first

Three things were established before this document was written, and all three cut against
the tool as briefed.

**It already exists.** [cozempic](https://github.com/Ruya-AI/cozempic) (375 stars, MIT,
actively released) rewrites `~/.claude/projects/*/*.jsonl` in place with eighteen
deterministic strategies, two of which — `stale-reads` and `tool-result-age` — are the
rules described here. `claude-code-prune` does a smaller version of the same thing. Neither
publishes any measurement of what it costs in task quality.

**The cheap version of the idea is already published and already works.** Lindenbauer et
al. (DL4C workshop at NeurIPS 2025) replaced environment observations older than a rolling
ten-turn window with a placeholder and matched LLM summarisation on SWE-bench Verified
solve rate at roughly half the cost — 54.8% at $0.61 against a raw agent's 53.4% at $1.29.
Their rule is pure recency. It does no classification at all. Any type-aware scheme has to
beat *that*, not the unmanaged baseline.

**The operator's own survey closed against this, two days ago.**
`/workspace/UsageFoundry/proposals/ContextControl/` weighed thirteen options for making a
run carry less and recommended building none of them —
"[t]he honest response to that is an instrument, not an actuator" — pending one live-model
experiment that has still not been run. Its measured reason is arithmetic: on that install
the prompt cache is returning about 5.5× (3.3bn cache-read tokens billed at $1,651 that
would cost $16,513 as fresh input), and editing a prefix mid-conversation needs 18 turns to
pay back a half-suffix cut and 170 turns to pay back a tenth-suffix cut.

**So the reason winnow exists is not the saving.** It is that nobody has measured what
this class of tool costs in correctness, and winnow is a cleaner instrument for that
measurement than compaction is, because its decisions are rules a person can read and
replay. See [docs/SPEC.md](docs/SPEC.md) §2.

---

## What it does

**Read path.** `winnow inspect` walks one session transcript and reports what is in it:
bytes by record type, by tool, by rule class, and the cache arithmetic from the `usage`
field Claude Code already writes on every assistant record. It writes nothing. This half is
useful on its own and is milestone 1.

**Write path.** `winnow fork` copies the transcript, replaces the `content` of selected
`tool_result` blocks with a pointer, and writes the copy under a new session ID. The
pointer carries the tool name, the arguments, a SHA-256 of the removed bytes, and the exact
command that recovers them. `winnow recover` prints those bytes back from the untouched
original. What gets dropped is decided by a stated rule, not by a summariser, so the
forked session cannot silently omit the one thing that mattered — it can only omit
something a rule in [docs/SPEC.md](docs/SPEC.md) §4 names out loud.

**When.** Only at a resume boundary, on a session that is not running. Never mid-session,
never to a live conversation, never to the original file. That is not caution, it is the
only point where the edit is free: a resume more than five minutes after the last request
finds a cache that has already expired, so a rewrite there costs no cache write that was
not going to be paid anyway.

## What it does not do

It does not call a model, summarise, rank, or score relevance. It does not install hooks,
run an MCP server, wrap the `claude` binary, or alter a session while it is running. It
does not delete anything: the original transcript is the archive and the recovery source.
It cannot see sub-agent work, because Claude Code does not write sub-agent turns into the
parent transcript (0 sidechain records in 563 transcripts measured here). Full list with
reasons in [docs/SPEC.md](docs/SPEC.md) §3.

## Who it is for

One operator running long Claude Code sessions against large repositories, who already
reads their own transcripts and wants to know what the sessions are carrying before
deciding whether to carry less. It is not a product, it has no multi-user story, and its
first real user is the person measuring whether it should have been written.

---

## The numbers this rests on

Measured here on 2026-08-23, over 563 real transcripts in `~/.claude/projects/`, restricted
to the 161 sessions carrying more than 400 KB of message content (120,090,336 bytes
pooled). Bytes, not tokens; the ÷4 conversion to tokens is an estimate and is flagged
everywhere it is used.

| Rule tier | What it strips | Share of message content |
| --------- | -------------- | ------------------------ |
| **C** conservative | directory listings, exact duplicate calls, passing test/build/lint output | **3.5%** pooled, 1.0% median |
| **B** + supersession | + a `Read` later re-read, + `ls`/`cat`/`git status`-class Bash output | **22.6%** pooled, 21.6% median |
| **A** + pre-edit reads | + a `Read` of a file the session then wrote to | **29.7%** pooled, 30.1% median |

Tier C alone does not justify the project. Tier B is where the mass is and it is the one
worth arguing about. Tier A is the largest single increment and the riskiest, because a
file the session edited is a file it was reasoning about. Derivation and per-session spread
in [docs/SPEC.md](docs/SPEC.md) §5.

## Status

Draft definition, 2026-08-23. No code. No decision to build has been taken. The first
milestone is a measurement whose result is allowed to end the project —
[docs/MILESTONES.md](docs/MILESTONES.md) names what would.
