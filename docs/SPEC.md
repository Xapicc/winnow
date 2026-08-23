# winnow — specification

> **Status of this document, 2026-08-23.** Written before the Cozempic merge (`210b026`), which
> deleted it. Restored here verbatim: nothing below has been rewritten to agree with the code that
> now sits in `src/cozempic/`. Where the two disagree, [COZEMPIC.md](COZEMPIC.md) says which side
> wins and why, decision by decision. Read that document alongside this one; a reader who takes
> only this file will believe things the repository no longer does, and a reader who takes only the
> code will believe things this project never agreed to.

**One-liner:** A command-line tool that reads a finished Claude Code session transcript,
replaces the tool results a stated rule classifies as once-only with recoverable pointers,
and writes a forked session the operator can resume — deciding what to drop from what the
harness already wrote to disk, with no model in the loop.

**Appetite:** two weeks of one person's work · **Status:** draft · **Date:** 2026-08-23

Every load-bearing claim below cites its source. Vault notes are cited as
`[[Note Name]] (confidence)` and resolved to full paths with their frontmatter confidence
in §11. Measurements taken for this document on 2026-08-23 are marked **[measured here]**
and their method is in §5.

---

## 1. Problem

A long Claude Code session on a large repository accumulates a conversation in which most
of the volume is tool output. **[measured here]** across 563 transcripts (175.6 MB of
message content), the split is:

| Content class | Bytes | Share |
| --- | ---: | ---: |
| `tool_result` | 115,631,018 | 65.8% |
| `tool_use` inputs | 45,265,463 | 25.8% |
| user text | 12,055,790 | 6.9% |
| assistant text | 2,649,047 | 1.5% |
| thinking | 1,858 | 0.0% |

Within `tool_result`, `Read` is 50.1% and `Bash` 31.8%. This matches the operator's own
independent measurement in `/workspace/UsageFoundry/proposals/ContextControl/`, which put
`Read` at 57.1% and `Bash` at 38.2% of tool characters — 95.3% between them — and it is
the same order as the only peer-reviewed figure available, Lindenbauer et al.'s "around
84% of an average SWE-agent turn" for observation tokens.

Some of that volume was needed once. A `git status` run to orient, a `Read` of a file the
session then rewrote, a passing `npm test`, a directory listing already acted on. Some of
it is needed for the rest of the work: the task, the decisions taken, the shape of the code
being changed. Nothing in the harness distinguishes them, and the whole conversation is
re-sent on every turn thereafter.

**What that costs is not what it looks like.** The conversation sits at the front of the
cached prefix and is billed at 0.1× ([[Prompt Caching]], high). On the operator's own
install, 3.3 billion cache-read tokens cost $1,651 against the $16,513 they would cost as
fresh input, on a weekly bill of $2,700 — the cache is returning about 5.5×
(`ContextControl/17-recommendation.md`). `[[Controls on Agent Run Cost]]` (medium) lists
"trim the conversation history, it is half your tokens" under the heading **What is
folklore**, for exactly this reason.

**So the problem is not cost. It is that nobody knows the answer.** Three notes record the
same gap independently: "Nobody has published the netting" ([[What Breaks a Cache in an
Agent Loop]], medium); "Nobody has netted the token saving against the cache cost, and
nobody has priced the information loss" ([[Controls on Agent Run Cost]], medium); and the
vendor's own `clear_tool_uses` rests on the sentence "Older tool results (like file
contents or search results) are no longer needed once Claude has processed them", which
[[Mid-Session Context Mutation with Claude]] (medium) records as "the assumption doing the
work, and it is unevaluated on the page", with no quantitative result of any kind published
alongside it and no independent reproduction as of 2026-08-21.

The observable symptom, and therefore the primary metric: **a session that carries 30% dead
tool output pays for it on every subsequent turn, and no one can currently say whether
removing it costs anything.**

## 2. Why build this rather than one of the things that already exist

| Existing thing | What it does | Why it does not close the question |
| --- | --- | --- |
| Claude Code auto-compaction | Summarises and restarts | Irreversible by construction. [[Compaction and Context Editing]] (medium): AppWorld full context 85.7%, summary 72.8%, FIFO 42.2%; constraint violation 0% → 30% after one compaction. Costs −66.1 points of cache hit rate |
| `/clear`, `--resume`, `--fork-session` | All-or-nothing | No selection at all |
| API `clear_tool_uses_20250919` | Clears by age, keeps last 3 | **Not reachable from the Claude Code CLI.** Verified two ways: no flag in `claude --help` at 2.1.226 **[measured here]**, and `ContextControl/20-` found `clear_at_least` and `exclude_tools` appear zero times in the CLI bundle, with `--settings` keys accepted and silently ignored |
| `PostToolUse` / `PreToolUse` hooks | Rewrite a result on the way in | Cannot reach anything already in the conversation. Confirmed by the vendor hooks reference and by `ContextControl/02-`, which probed it on the pinned binary |
| Sub-agents | Isolate a side task's context | Vendor recommends them for exactly this ("search results, logs, or file contents you won't reference again") with no measurement anywhere ([[Sub-Agent Architectures]], medium), and `[[Controls on Agent Run Cost]]` ranks fan-out **last of six** cost levers at 2.0×–4.3× cost |
| cozempic, claude-code-prune | Rewrite the JSONL by rule, today | **Neither publishes any task-quality measurement.** Both report token reduction only |
| Lindenbauer et al. observation masking | Recency-only placeholder substitution | Peer-reviewed and it works. **This is the baseline to beat, and it is not the unmanaged agent** |

The gap two independent searches agree on: there is **no head-to-head of type-aware rules
against summarisation**, and **no evaluation of any Claude Code JSONL pruning tool against
task quality**. That is the whole reason for this project, and it makes the deliverable a
number rather than a binary.

## 3. Scope

### In scope

- **Reading session state on disk.** `~/.claude/projects/<slugified-cwd>/<sessionId>.jsonl`, one JSON record per line.
- **Rewriting session state on disk, copy-on-write only.** Winnow reads the original and writes a *new* file under a new session ID. The original is never opened for writing.
- **Deciding between sessions.** The decision is taken at a resume boundary, on a session with no live process.

### Explicitly out of scope, and why

| Not doing | Reason |
| --- | --- |
| **Wrapping the `claude` CLI as a subprocess** | Winnow prints the `claude --resume <new-id>` line; the operator runs it. Keeping winnow out of the spawn path means it cannot break a run, and means the tool has no opinion about flags, budgets or permissions. *Exception:* the measurement harness in milestone 3 does spawn `claude -p` — that is the bench, not the tool, and it lives behind `winnow bench` |
| **Hooks** | A hook cannot reach anything already in the conversation, so it solves a different problem (intake filtering). It is also the thing `readGuard.ts` already ships in UsageFoundry |
| **An MCP server** | Every added tool definition sits at the top of the invalidation cascade and costs a standing per-turn charge — `ContextControl/12-` priced one added tool definition at $8.14–$8.26/week on that install, against a $0.14 benefit per use |
| **Deciding at spawn time / mid-session** | See §7. The cache arithmetic only works at a boundary where the cache is already cold |
| **Altering a live session** | The vendor hooks reference states the transcript file "is written asynchronously and may lag the in-memory conversation". Editing the file mid-session does not change what is sent. It is not merely unsafe, it does not work |
| **Summarising, ranking, scoring, embedding, or any model call** | Operator constraint, and the correctness literature is against it (§1) |
| **Touching `thinking` blocks** | There is nothing to touch: 1,858 bytes of thinking text across 563 transcripts **[measured here]**; `ContextControl/00-` counted 13,454 thinking blocks with zero non-empty. The text is stripped before it reaches disk |
| **Touching sub-agent transcripts** | 0 sidechain records in 563 transcripts **[measured here]**. Sub-agent turns are not in the parent file |
| **Deleting anything** | The original transcript is both archive and recovery source. Winnow adds files; it never removes them |
| **A database, index, or content store** | `ContextControl/01-` calls this "a fourth store" and forbids it: it would need its own retention horizon, liveness query and storage accounting. Winnow's only persistent state is the forked transcript itself |

## 4. Classification rules

A rule may only fire on the `content` of a `tool_result` block. It may never touch a
`tool_use` block, assistant text, user text, `thinking`, or any non-message record. This
follows the vendor's own default: `clear_tool_inputs` defaults to `false` in
`clear_tool_uses_20250919`, so the call and its arguments survive and only the answer is
cleared ([[Mid-Session Context Mutation with Claude]], medium). Keeping the input is what
makes the pointer legible.

**Substitution, not deletion.** The Messages API requires every `tool_use` to be answered:
"Tool result blocks must immediately follow their corresponding tool use blocks in the
message history." `content` is documented as optional on a `tool_result`, so an empty
result is legal — but the vendor's own strategy substitutes placeholder text rather than
emptiness, and no one has published whether that choice matters. Winnow substitutes a
pointer and records the choice as an open question (DECISIONS §Q3). **[measured here]**
pairing in practice is total: 42,966 `tool_use` blocks, 5 without a matching `tool_result`,
all of them the last in-flight call of a session.

### Tier C — conservative

A result is once-only if any of:

- **C1 locator.** `tool_use.name ∈ {Glob, LS}`, or `Grep` with `output_mode ∈ {files_with_matches, count}`. The output is a list of paths whose only consumer is the call that followed it.
- **C2 exact duplicate.** An earlier `tool_result` whose `(name, canonicalised input)` is byte-identical to a later one. The later one supersedes it. Only the *earlier* is stripped.
- **C3 passing verification.** `Bash` where the command matches the verification pattern (`npm|pnpm|yarn|bun run? (test|build|lint|typecheck|check)`, `pytest`, `go test|build|vet`, `cargo test|build|clippy`, `tsc`, `eslint`, `make test|build|check`, `jest`, `vitest`, `ruff`, `mypy`) **and** `is_error` is false. A failing verification is never stripped — the failure is the information.

### Tier B — supersession and inspection

- **B1 superseded read.** A `Read` result is once-only if a later `tool_use` in the same session calls `Read` on a byte-identical `file_path`. Only the earlier is stripped. Ranged reads are compared on `(file_path, offset, limit)` and a ranged read is superseded only by a read that provably covers its range.
- **B2 Bash inspection.** `Bash` where the first command in the pipeline matches the inspection pattern (`ls`, `cat`, `head`, `tail`, `find`, `grep`, `rg`, `wc`, `tree`, `pwd`, `which`, `type`, `file`, `stat`, `du`, `df`, `env`, `printenv`, `echo`, `git status|log|diff|show|branch|remote|ls-files`, `jq`, `sed -n`, `awk`, `sort`, `uniq`, `column`, `nl`, `realpath`, `basename`, `dirname`) **and** `is_error` is false. Matching is on the first token of the first segment before `&&` or `|`, so a pipeline whose head is `ls` counts and one whose head is `python` does not, whatever follows.

### Tier A — pre-edit reads

- **A1 read then written.** A `Read` result is once-only if a later `tool_use` calls `Edit` or `Write` on a byte-identical `file_path` and no intervening `Read` of that path exists. The rationale is that the retained bytes are now *stale*: the file on disk no longer matches them, and the `Edit` block itself carries `old_string` and `new_string`, which is the part the session acted on.

  This is the rule most likely to be wrong. A file the session edited is a file it was reasoning about, and the surrounding lines it did not edit may be exactly what it needs. Tier A is opt-in, never a default, and milestone 3 measures it separately.

### Universal guards, applied before any rule

- **G1 keep the tail.** The last `--keep-last N` tool results in the session are never stripped (default 6, doubling the vendor's `keep: 3`).
- **G2 size floor.** A result under `--min-bytes` is never stripped (default 2,048). **[measured here]** the median tool result is small and the largest decile carries most of the bytes; stripping small results buys nothing and costs pointer overhead. `ContextControl/08-` measured a median result of 278 bytes with the largest 10% carrying 72.2% of all tool-result bytes.
- **G3 errors survive.** `is_error: true` is never stripped, at any tier.
- **G4 no net inflation.** If the pointer is longer than the content it replaces, the content stays.
- **G5 pairing preserved.** Every `tool_use` in the output has a matching `tool_result`. Violating this is a hard failure that aborts the fork rather than writing a broken file.

### The pointer

Replaces `content` with a single text block, ~120 bytes:

```
[winnow: Bash result removed, rule B2, 41,208 bytes, sha256 9f2c…a1
 recover: winnow recover 5051d73c b7 ]
```

It names the rule that fired, so the operator can argue with the rule rather than with the
tool, and the recovery command, so the loss is reversible in
[[Compaction and Context Editing]]'s own sense (medium): "replacing tool output with a
file path is recoverable; summarising into prose is not".

## 5. What the rules cannot decide, stated plainly

This section is the operator constraint honoured rather than routed around. The rules-only
approach cannot decide:

1. **Whether a file that was read once and never named again mattered.** `ContextControl/00-` measured this exact proxy — 39.5% of `Read` bytes belong to files the run never mentions again — and refused to act on it, in terms worth quoting: it is "a lower bound on what a perfect oracle could have dropped and an upper bound on nothing… The proxy is named here so an option cannot quietly promise the oracle." Winnow does **not** ship that rule. It is named here as the mass the tool deliberately leaves alone.
2. **Why a command was run.** A `cat` used to orient and a `cat` whose output is the answer to the user's question are the same record. Rule B2 strips both.
3. **Whether the session was still relying on a stripped read.** The reasoning that would say so is not on disk: thinking text is stripped from every transcript (§3). This is the sharpest limit, and it means no refinement of the rules can recover the signal — the evidence is absent, not merely hard to extract.
4. **Whether a strip caused a later re-fetch.** A re-fetch is an ordinary `Read`. It is indistinguishable from a read that would have happened anyway, so the cost of a bad strip is invisible to the tool that made it and is only measurable in the A/B of milestone 3.
5. **Anything about a sub-agent.** Not in the file.
6. **Whether the *first* read of a file was necessary.** Verbatim re-reads are only 0.3% of tool-result bytes (`ContextControl/08-`), so almost nothing is read twice. The saving is never "avoided duplicate work"; it is only "the session stops carrying it".

Two of these — (1) and (3) — mean the tool's ceiling is set by what the transcript records,
not by rule quality. A better rule cannot see further than the file does.

## 6. Measured baselines

**Method.** All 563 `*.jsonl` under `~/.claude/projects/`, parsed line by line;
`message.content` blocks summed by type; the `content` of a `tool_result` measured as
`len(str)` or `len(json.dumps(list))`. Restricted for the table below to the 161 sessions
carrying more than 400 KB of message content, pooling 120,090,336 bytes, because sessions
that never grow are not the population winnow is for. Tokens are estimated at bytes ÷ 4 and
that estimate is flagged wherever it is used. One operator, mixed project types, a
convenience sample of their own work — the same limitation `[[TraceLab Coding Agent
Workloads (Zhu et al 2026)]]` (medium) records about its own 43 developers.

| Rule | Bytes | Share of message content |
| --- | ---: | ---: |
| C1 locator | 5,093 | 0.00% |
| C2 duplicate | 3,338,750 | 2.78% |
| C3 passing verification | 864,255 | 0.72% |
| B1 superseded read | 11,788,563 | 9.82% |
| B2 Bash inspection | 11,160,984 | 9.29% |
| A1 read then written | 8,479,497 | 7.06% |

| Tier | Pooled | Median session | p10 | p90 |
| --- | ---: | ---: | ---: | ---: |
| C | 3.5% | 1.0% | 0.0% | 5.1% |
| C+B | 22.6% | 21.6% | 4.6% | 48.5% |
| C+B+A | 29.7% | 30.1% | 11.1% | 57.5% |

**Read this as a ceiling on the mechanism, not a saving.** It is the share of message
content a rule could replace. It says nothing about tokens (bytes ÷ 4 is crude and
different for logs than for prose), nothing about dollars (the removed bytes were being
billed at 0.1×), and nothing about correctness.

Session shape in the same population: median 613,946 bytes (~153k estimated tokens), p90
1,072,795, max 4,086,583 (~1.02M estimated tokens). 71 compaction boundaries across 563
sessions, i.e. 12.6% of sessions compacted — against `[[Agentic Coding in the Wild (Liu et
al 2026)]]`'s (medium) 7.8% on a different harness.

## 7. The retrieval path, and why the cut point is the whole design

**The constraint.** Anything stripped must be re-fetchable, and the session must look it up
rather than recall it. `[[Agentic Memory]]` (medium) states the discipline as "ASSUME
INTERRUPTION" and observes that memory is what makes clearing lossless rather than lossy.

**Three retrieval routes, in order of preference:**

1. **The file system.** A stripped `Read` is recovered by reading the file again — and it will be *more* correct than the retained bytes if the file was since edited. A stripped `git status` is recovered by running `git status`, which is likewise fresher. This is the primary path and it costs winnow nothing to build.
2. **The pointer's recovery command.** `winnow recover <session> <id>` prints the exact bytes from the untouched original. This covers the case the file system cannot: a Bash result that is not reproducible, a `WebFetch` of a page that has changed.
3. **The original transcript.** Never modified, never deleted by winnow. It is the archive of record and the reason nothing here is irreversible.

**The evidence that re-fetch is not free, stated rather than hidden.** `ContextControl/03-`
measured a fresh conversation that re-reads what it lost at **2.59× dearer** than a resumed
one, with the break-even at about **3.9 KB of re-reading per cycle**. `[[Agentic Search]]`
(medium) prices agentic re-fetch at 226K–895K query tokens per question against BM25's
flat 5.8K. And `[[Why Does File-Based Tool Output Invert the Grep Advantage]]`
(**confidence: low**, and the vault's own lowest-graded note in this area) records the one
measurement in winnow's exact configuration — Claude Code plus Opus, grep 76.7% → **68.1%**
when results are delivered via a file rather than inline. That is n=116, single-run, no
error bars, unreplicated in fifteen months, and contradicted on adjacent constructs by two
non-independent sources. It is weak evidence. It is also the only evidence, and it points
the wrong way.

**Winnow's answer is to make re-fetch rare rather than cheap.** Because verbatim re-reads
are 0.3% of tool-result bytes, the design bet is that a stripped result is mostly never
wanted again — and when it is, route 1 returns fresher bytes than were removed. Route 2 is
the escape hatch, not the plan.

**The cut point.** `[[Prompt Caching]]` (high): invalidation cascades tools → system →
messages, and "[p]runing something from the middle of the prefix is exactly what breaks a
cache". `[[What Breaks a Cache in an Agent Loop]]` (medium) prices one break at ~9.7 normal
steps at step 50 and ~10.4 at step 100, growing linearly with position, and lists "editing
anything already in the prefix" as one of the four real breakers. `ContextControl/01-`
derives the break-even in turns as `T* = 19·(S/D) − 20`, where `S` is the suffix left
standing after the cut and `D` the tokens removed — 18 turns to pay back a half-suffix cut,
**170 turns** for a tenth-suffix cut.

That formula also names the exception, and it is winnow's entire architectural claim:

> There is exactly one moment where an edit is free… the work-cycle handover, where the
> suffix is re-written anyway. There `S = D` and `T* = −1`.

Winnow generalises that moment. The cache TTL is 5 minutes by default ([[Prompt Caching]],
high) and median human idle between turns is 1,512 seconds — 25.2 minutes — with "after 1
hour, almost all steps miss the cache" ([[What Breaks a Cache in an Agent Loop]], medium).
**A resume taken more than an hour after the last request finds a cache that has already
expired.** The rewrite therefore costs a cache write that was going to be paid regardless,
and the deletion is free in the only sense that matters. Winnow refuses to fork a session
whose last request is younger than a configurable threshold (`--min-cold-age`, default
3,600 s) and says why. This is the one design decision that answers the caching objection
instead of arguing with it.

## 8. CLI surface

```
winnow inspect  <session>                       composition readout; writes nothing
winnow plan     <session> [--tier C|CB|CBA]     dry run: what would go, and the arithmetic
winnow fork     <session> [--tier ...] --write  write the forked transcript
winnow recover  <session> <pointer-id>          print original bytes from the untouched file
winnow bench    <task-set> --arms ...           the A/B harness (milestone 3)
```

`<session>` is a session ID, a path, or a prefix long enough to be unambiguous.

| Flag | Default | Does |
| --- | --- | --- |
| `--tier C\|CB\|CBA` | `CB` | Which rule tiers may fire. `CBA` requires `--i-know` |
| `--rule <id>` / `--no-rule <id>` | — | Enable or disable one rule, repeatable, overrides the tier |
| `--keep-last N` | `6` | Guard G1 |
| `--min-bytes N` | `2048` | Guard G2 |
| `--min-cold-age S` | `3600` | Refuse to fork a session whose last request is newer than this (§7) |
| `--write` | off | Without it, `fork` is a dry run. There is no `--dry-run`; dry is the default |
| `--out <path>` | derived | Where the fork goes; default is a new session ID in the same project directory |
| `--json` | off | Machine-readable output for every command |
| `--explain` | off | One line per stripped result: rule, tool, arguments, bytes |
| `--force` | off | Proceed past a soft refusal. Never past G5 |

`inspect` output, which is the deliverable of milestone 1 and useful whether or not anything
is ever stripped: bytes by record type; bytes by tool; bytes by rule class at each tier;
`cache_read_input_tokens` / `cache_creation_input_tokens` / `output_tokens` summed from
`message.usage`, which Claude Code writes on every assistant record, so the cache economics
are auditable from disk with zero model calls; the count and position of any
`compact_boundary` records; and the estimated `T*` for a cut at the current tier.

**Exit codes.** `0` success; `1` usage error; `2` nothing to do (no result met a rule);
`3` refused (session too warm, session live, G5 would be violated). A refusal is loud and
names the guard, because `ContextControl/01-`'s bar is the right one: "on a build where the
lever does nothing, does the run get quietly more expensive, or does something say so?"

## 9. Success criteria

The primary metric is deliberately **not** token reduction. `[[Controls on Agent Run
Cost]]` (medium) puts history-trimming under "folklore" precisely because token share and
dollar share come apart at the 0.1× read discount, and a 46.9% token reduction is already
claimed at blog grade by Cursor with no quality measurement attached. Evaluating on tokens
would reproduce that unfalsifiable number.

| Metric | Baseline today | Target | How measured | Checked when |
| --- | --- | --- | --- | --- |
| **Task success rate, winnow-CB vs unwinnowed resume** | Unknown; the whole point. Establishing it is milestone 3a | Within an equivalence bound of ±5 points, pre-registered before the task set is frozen | ≥40 held-out resume tasks × ≥3 runs per cell, scored by a fixed rubric written before any run | Milestone 3 |
| **Cache-adjusted cost per *successful* task** | Measured in the control arm of the same run | ≥15% lower than control | Sum of `usage` fields × the published multipliers (read 0.1×, 5-min write 1.25×, 1-h write 2×, [[Prompt Caching]] high), divided by successes. Distribution reported, not a point estimate | Milestone 3 |
| **Rule precision on a hand-labelled sample** | Unknown | ≥90% of stripped results confirmed once-only by a human reading the surrounding turns | 200 stripped results sampled stratified by rule, labelled blind by the operator | Milestone 2 |
| **Strippable share at tier CB** | **22.6% pooled, 21.6% median [measured here]** | Reproduce within ±3 points on a held-out corpus | `winnow inspect --json` over sessions not used to write the rules | Milestone 1 |
| **Guardrail: turns to completion** | Control arm of the same run | Must not rise by more than 10% | Turn count per task | Milestone 3 |
| **Guardrail: re-fetch rate** | 0 by construction in control | Stripped-then-re-read events < 1 per session at the median | Count reads in the forked session of paths whose earlier read was stripped | Milestone 3 |
| **Guardrail: `winnow fork` never produces an unresumable session** | n/a | 0 failures in 100 forks | Resume each fork with `claude -p 'reply OK'` and check exit code | Milestone 2 |

**Where a number does not exist, the measurement that would produce it:** every "unknown"
above is produced by `winnow bench` in milestone 3, whose design is copied from
`ContextControl/03-experiment-resumed-vs-fresh.md` (which ran the wire arithmetic with a
recorder standing in for the model and therefore produced no quality data at all) with the
one change that made it inconclusive corrected: **a live model in the loop.** That
experiment is ranked #1 of ten follow-ups in `ContextControl/19-validation.md` and costed
there at single-digit dollars per run. It has not been run by anyone.

**The equivalence-bound discipline is not optional.** `[[Agentic Session Standard]]` (low,
and the vault's own standing decision on this) fixes it: "measurement before authorship",
≥40 held-out tasks × ≥3 runs per cell, pre-registered process outcomes, equivalence bounds
rather than point estimates, and the task set frozen and hashed before the artefact is
written. Winnow adopts this and does not negotiate it downward — see also the
`ContextControl` warning that a within-session before/after gives −18.6% of which "a
placebo on an uncompacted ramp reproduces ~87%".

## 10. Non-functional requirements

- **Never write to the original.** Open the source transcript read-only. Write the fork to a temporary file in the same directory and `rename()` it into place, so a crash leaves either nothing or a complete file.
- **Never write outside the project directory** without an explicit `--out`.
- **Determinism.** The same input transcript and the same flags produce a byte-identical fork. No timestamps, no random IDs, no map iteration order in the output. This is what makes the milestone 3 result replayable, and it is the property compaction does not have.
- **Fail loudly.** A malformed record aborts with the line number. An unparseable `tool_use` input aborts rather than being treated as empty. G5 is a hard failure. There is no fallback that silently keeps a result the operator asked to strip, and none that silently strips one they did not.
- **No network.** Winnow makes no HTTP request of any kind. `winnow bench` does, and is the only subcommand that does.
- **Treat the transcript as untrusted input.** `[[Prompt Injection]]` (high) makes the control point "everything that consumes a sandboxed agent's output", and a tool that parses and rewrites a transcript is exactly such a consumer. Paths from `tool_use.input.file_path` are used for *comparison only* and are never opened, resolved, or globbed. Pointer text is generated by winnow and never interpolates transcript content beyond a length and a hash.
- **Secrets.** Transcripts routinely contain credentials pasted into a Bash command. Winnow prints tool arguments in `--explain` output and must therefore be documented as producing sensitive output, and must never write a log file by default.
- **Performance.** `inspect` over a 4 MB transcript in under two seconds on the operator's machine. Streaming line-by-line; the whole file is never held in memory as parsed objects.

## 11. Sources

Vault notes, with the `confidence:` from their own frontmatter. All under `/workspace2/`.

| Cited as | Path | Confidence |
| --- | --- | --- |
| [[Prompt Caching]] | `3 Resources/AI Context and Memory/Prompt Caching.md` | high |
| [[What Breaks a Cache in an Agent Loop]] | `3 Resources/AI Context and Memory/What Breaks a Cache in an Agent Loop.md` | medium |
| [[Compaction and Context Editing]] | `3 Resources/AI Context and Memory/Compaction and Context Editing.md` | medium |
| [[Mid-Session Context Mutation with Claude]] | `3 Resources/AI Context and Memory/Mid-Session Context Mutation with Claude.md` | medium |
| [[Context Manipulation with Claude]] | `3 Resources/AI Context and Memory/Context Manipulation with Claude.md` | medium |
| [[Context Rot]] | `3 Resources/AI Context and Memory/Context Rot.md` | medium |
| [[Agentic Memory]] | `3 Resources/AI Context and Memory/Agentic Memory.md` | medium |
| [[Agentic Search]] | `3 Resources/AI Context and Memory/Agentic Search.md` | medium |
| [[Sub-Agent Architectures]] | `3 Resources/AI Context and Memory/Sub-Agent Architectures.md` | medium |
| [[Controls on Agent Run Cost]] | `3 Resources/LLM Application Engineering/Controls on Agent Run Cost.md` | medium |
| [[The Cost Shape of an Agent Run]] | `3 Resources/LLM Application Engineering/The Cost Shape of an Agent Run.md` | medium |
| [[Why Does File-Based Tool Output Invert the Grep Advantage]] | `3 Resources/Questions/Why Does File-Based Tool Output Invert the Grep Advantage.md` | **low** |
| [[Is Grep All You Need (Sen et al 2026)]] | `3 Resources/Sources/Is Grep All You Need (Sen et al 2026).md` | medium (preprint) |
| [[Agentic Coding in the Wild (Liu et al 2026)]] | `3 Resources/Sources/Agentic Coding in the Wild (Liu et al 2026).md` | medium (preprint) |
| [[TraceLab Coding Agent Workloads (Zhu et al 2026)]] | `3 Resources/Sources/TraceLab Coding Agent Workloads (Zhu et al 2026).md` | medium (preprint) |
| [[Agentic Session Standard]] | `1 Projects/Agentic Session Standard/Agentic Session Standard.md` | low |
| [[Prompt Injection]] | `3 Resources/AI Security/Prompt Injection.md` | high |

Non-vault sources: `/workspace/UsageFoundry/proposals/ContextControl/` (`00-`, `01-`, `02-`,
`03-`, `08-`, `12-`, `16-`, `17-`, `19-`, `20-`), a design study by the same operator closed
2026-08-21 and revised 2026-08-22, with three of its options shipped 2026-08-23. Lindenbauer
et al., *The Complexity Trap*, arXiv:2508.21433, DL4C workshop at NeurIPS 2025 —
peer-reviewed workshop, the only rule-versus-summarisation head-to-head with numbers.
Anthropic hooks reference, context-editing docs and tool-use docs — vendor documentation,
mutable, accessed 2026-08-23. cozempic and claude-code-prune — GitHub projects, no
evaluation.
