# winnow — decisions, risks and open questions

Written 2026-08-23. Every decision below states what was rejected and what it costs to be
wrong. Risks are ordered by how likely they are to end the project, and caching economics
is first because it is the one that can end it on arithmetic alone.

Citation convention as in [SPEC.md](SPEC.md) §11: `[[Note]] (confidence)` for vault notes,
`ContextControl/NN-` for `/workspace/UsageFoundry/proposals/ContextControl/`.

> §0 was added 2026-08-23 after the Cozempic merge (`210b026`) deleted this file. §1 onward is
> restored verbatim and unamended; where the code contradicts it, [COZEMPIC.md](COZEMPIC.md)
> adjudicates rather than this document quietly changing its mind.

---

## 0. What Cozempic is doing in this repository

Commit `210b026` imported 21,700 lines of a working, published tool (Cozempic 1.8.39, MIT,
copyright Ruya AI) into `src/cozempic/`, and deleted this project's shaping documents in the
same commit. That leaves one question that has to be answered before any other: is winnow now a
fork of Cozempic, or is Cozempic prior art that winnow keeps and measures?

**Decided: vendored prior art. Pinned, unmodified, uninstalled, and one arm of the measurement.**

Concretely:

- `src/cozempic/` is treated as a **read-only third-party tree**. Nothing in it is edited. Bug
  fixes to it are not winnow's work; if one is needed, it goes upstream or it goes in a patch file
  beside the tree, never inline.
- Winnow's own code, when it exists, goes in `src/winnow/`. There is no shared module, no common
  base class and no refactor to extract one. The two trees do not know about each other.
- Nothing in `src/cozempic/` is installed, wired, or started by default. Its hooks are not
  registered, its daemon is not launched, and its auto-update is off. [USAGEFOUNDRY.md](USAGEFOUNDRY.md)
  names the environment variables that hold that true.
- It stays in-tree, at a recorded upstream commit, because `winnow bench` needs a byte-stable
  baseline and a PyPI dependency is not one. Cozempic upgrades itself from PyPI on every session
  start (`plugin/hooks/hooks.json:9`) and on every CLI invocation (`src/cozempic/cli.py:2399` →
  `src/cozempic/updater.py:225`), so `cozempic==1.8.39` names a version that does not stay put.
  A vendored tree at a known sha is reproducible; a pin on a self-updating package is not.

**Why not a fork.** A fork inherits the maintenance, and the maintenance is the part nobody costed.
It is 4,314 lines of daemon that sends `SIGKILL` to a live editor session
(`src/cozempic/guard.py:2377-2400`), with no test CI anywhere in the repository, `pytest`
undeclared as a dependency, and an undeclared `psutil` import whose absence makes the anti-PID-reuse
check in front of that `SIGKILL` fail **open** (`src/cozempic/guard.py:2268`). It also inherits a
version number, a PyPI name, a telemetry endpoint on a third party's Cloudflare Worker
(`src/cozempic/helpers.py:240-261`), six packaging channels and another project's release process.
Winnow's appetite is two weeks and its deliverable is a number ([MILESTONES.md](MILESTONES.md)).
Adopting a 21,700-line codebase spends the whole appetite on custody.

The deeper reason is that the two designs disagree at the root, not at the edges. §3 below already
rejected Cozempic's three central choices by name, before this merge and without reference to it:
D2 rejects "in-place edit with a timestamped backup (cozempic's design)", D7 rejects "a daemon
watching for session end", and §2 rejects "[i]gnore the cache and strip whenever asked — This is
what cozempic does, and it is why no one can say whether cozempic saves money." A fork is a
commitment to a codebase whose load-bearing decisions this document rejected three times in
writing. [COZEMPIC.md](COZEMPIC.md) §3 works through all of them.

**Alternatives rejected:**

| Alternative | Why rejected |
| --- | --- |
| **Fork and diverge.** Rename, re-license, keep the code, replace the parts winnow disagrees with | The parts winnow disagrees with are the guard, the writer and the trigger, which is most of the tool. What is left is the rule set, and §1 already records that "the rules are the cheap part". It also means maintaining a hard fork of a package that auto-updates itself, under a name that has to differ from the one on PyPI, with a contributor list that is not winnow's |
| **Wrap and configure.** Winnow becomes a front-end that drives Cozempic with better defaults | Incoherent with D7, which keeps winnow out of the spawn path entirely, and with §2, which needs the strip to happen at a cold boundary. Cozempic's trigger is a token threshold crossed mid-session. Wrapping it means either not using the guard, in which case there is nothing to wrap, or using it, in which case winnow has adopted the one decision it rejected on arithmetic |
| **Delete it; recover it from history if the bench needs it** | Tempting and nearly right. Rejected because a measurement arm reachable only by `git show` is an arm that quietly does not get run, and because the code is the clearest available statement of what the rule-based class of tool actually does. Reading it is cheaper than re-deriving it. Kept visible, kept inert |
| **Git submodule against upstream** | Correct on paper and worse in practice: upstream moves, and a submodule pointing at a moving branch reintroduces exactly the reproducibility problem the vendored tree exists to solve. It also does not work in this container, which has no network path to `github.com` established for submodule fetch |

**Cost of being wrong.** Two ways, and they pull opposite.

If winnow's milestone 1 comes back badly and the project falls back to §1's own stated fallback,
"[c]ontribute the rules to cozempic instead", then a vendored tree at a stale sha is a fork that
has drifted with no upstream relationship, and every patch has to be re-derived against a moved
HEAD. The mitigation is the discipline above: never modify `src/cozempic/`, and record the upstream
commit so a rebase is a rebase rather than an archaeology exercise.

If instead the vendored tree turns out to be dead weight, 21,700 lines nobody reads and a bench
arm nobody runs, the cost is repository noise and the standing risk that some later agent takes
`src/cozempic/` for winnow's own code and edits it. That risk is real and this pass has already
seen its first instance: the merge left the repository asserting Cozempic's README as winnow's.
The mitigation is that every document here says which tree is which, in the first paragraph.

**Licensing and attribution, which the merge got wrong in both directions.**

- `LICENSE` is Cozempic's MIT notice, copyright 2026 Ruya AI. Vendoring under MIT requires that
  notice be retained, so the file stays exactly as it is, but it is **not winnow's licence**, and
  the repository currently reads as though it were. Winnow's own licence has not been chosen. Until
  it is, the honest state is one licence file that covers `src/cozempic/`, `plugin/`, `npm/` and
  `packaging/`, and no licence at all on anything winnow writes. The implementation run should
  either choose winnow's licence and add it as a second file with the scope of each stated, or
  record the decision to stay unlicensed.
- `CONTRIBUTORS.md` credits Cozempic's contributors, by name and pull-request number. That
  attribution is correct and must not be removed. What was wrong is that it sat at the root of a
  repository they have not contributed to, reading as winnow's contributor list. A header line now
  says whose list it is.
- `README.md` claimed 100,000+ users and carried a downloads badge for a package this repository
  does not publish. That was the merge asserting another project's numbers as this one's, and it is
  the failure this pass exists to fix. It has been rewritten.

## 1. The decision that comes before the others: is this worth building at all

**Decided: build the instrument, gate the actuator behind its own measurement.**

The case against is strong enough that it belongs here rather than in a risk section.

- The same operator ran a thirteen-option survey of this exact ground and closed it on 2026-08-21 with "[b]uild no context mechanism", reaffirmed 2026-08-22, on the grounds that "[n]ine options, and not one of them can name a dollar it would certainly save" and that "[t]he honest response to that is an instrument, not an actuator" (`ContextControl/16-`, `17-`).
- A working implementation already exists: cozempic, 375 stars, MIT, eighteen rules including this project's supersession and age rules.
- The cheap version of the idea is peer-reviewed and works: Lindenbauer et al. halved cost at parity solve rate with a pure-recency rule and no classification at all.
- The prompt cache on the operator's own install is returning about 5.5×, and every deletion spends against it.

**Alternatives rejected:**

| Alternative | Why rejected |
| --- | --- |
| Build the stripper as briefed and measure later | This is what cozempic did. It produces a token-reduction percentage nobody can act on, which is the exact failure `[[Controls on Agent Run Cost]]` (medium) files under folklore |
| Do nothing; the survey already closed | The survey closed *pending an experiment it costed at single-digit dollars and did not run*, and `ContextControl/19-` ranks that experiment #1 of ten. "Nobody ran it" is a reason to run it, not a reason to stop |
| Contribute the rules to cozempic instead | Reasonable, and the fallback if milestone 1 goes badly. But cozempic has no evaluation harness, and the harness is the deliverable — the rules are the cheap part |
| Buy it | There is nothing to buy. Every option surveyed is free software or a vendor feature that is unreachable from this CLI |

**Cost of being wrong:** two weeks, and a result that says the class of tool does not pay.
That result is publishable and is worth roughly what a positive one is, which is the only
reason the appetite is defensible.

## 2. Caching economics — the risk that can kill it on arithmetic

**The objection.** Winnow performs the single operation both trace studies name as
cache-destroying, on the single content type they measure as best-cached. `[[What Breaks a
Cache in an Agent Loop]]` (medium) puts tool-result steps at ~97.5% hit rate against ~84.4%
for user-initiated steps, and lists "editing anything already in the prefix" among the four
real breakers, at a price of ~9.7 normal steps at step 50 and ~10.4 at step 100. `[[Prompt
Caching]]` (high) states the mechanism: invalidation cascades tools → system → messages, so
"[p]runing something from the middle of the prefix is exactly what breaks a cache".
`ContextControl/01-` gives the break-even in turns as `T* = 19·(S/D) − 20`: 18 turns to pay
back a half-suffix cut, **170 turns** for a tenth-suffix cut. Vendor documentation says the
same thing qualitatively and ships `clear_at_least` as the knob, but publishes no formula
and no number.

**Decided: strip only where the cache is already cold, and refuse otherwise.**

`ContextControl/01-` identifies the exception itself — "[t]here is exactly one moment where
an edit is free… the work-cycle handover, where the suffix is re-written anyway. There
`S = D` and `T* = −1`." Winnow generalises that moment to any resume taken after the cache
has expired. The default TTL is 5 minutes ([[Prompt Caching]], high); median human idle
between turns is 25.2 minutes and "after 1 hour, almost all steps miss the cache"
([[What Breaks a Cache in an Agent Loop]], medium). At that point the resume pays a full
cache write regardless of whether winnow ran, so the rewrite is free in the only sense that
matters.

`--min-cold-age` defaults to 3,600 seconds and `winnow fork` exits 3 with a named refusal
below it. This is the single design decision that answers the caching objection rather than
arguing with it.

**Alternatives rejected:**

| Alternative | Why rejected |
| --- | --- |
| Strip mid-session via a `PostToolUse` hook | A hook cannot reach anything already in the conversation (`ContextControl/02-`, probed on the pinned binary). It solves intake, not accumulation, and UsageFoundry already ships that as `readGuard.ts` |
| Strip mid-session by editing the JSONL live | Does not work. The vendor hooks reference documents `transcript_path` as "written asynchronously and may lag the in-memory conversation" — the live request is built from memory, not from the file |
| Ignore the cache and strip whenever asked | This is what cozempic does, and it is why no one can say whether cozempic saves money |
| Only strip enough to clear a `clear_at_least`-style floor | Sound in principle, but the floor depends on the suffix length, which winnow knows exactly. Folded into `plan`'s reported `T*` rather than made a separate mechanism |

**Cost of being wrong:** if the cold-cache assumption is false — say Claude Code re-warms
a prefix on resume in a way that makes the write conditional on file content — every fork
costs a write it did not need to. `winnow inspect` reads `cache_creation_input_tokens` from
`message.usage` on the first turn after a resume, so this is directly falsifiable from disk
with no model call, and it is the first check in milestone 1.

## 3. Decisions taken

### D1 — Between sessions, never during one

Winnow reads a finished transcript and writes a new one. Rejected: hooks (cannot reach the
past), an MCP server (a standing per-turn cost of $8.14–$8.26/week per tool definition on
the operator's install, `ContextControl/12-`), a request-rewriting proxy in the style of
skim (works mid-session and is the architecturally correct answer, but requires standing
between the CLI and the API, which is a far larger surface and puts winnow in the failure
path of every request). **Cost of being wrong:** winnow only helps sessions that get
resumed. Sessions that run to completion in one sitting get nothing, and `[[Agentic Coding
in the Wild (Liu et al 2026)]]` (medium) puts the median session at 3 turns and 4.2 minutes
— most sessions are not winnow's population at all.

### D2 — Copy-on-write; the original is never modified

The fork gets a new session ID. **Rejected:** in-place edit with a timestamped backup
(cozempic's design). The original is the recovery source of record, and a scheme that
mutates it makes every strip irreversible the moment a retention sweep runs.
`ContextControl/01-` names the adjacent hazard: "`--resume` needs a file another sweep is
entitled to delete… A scheme that treats session files as disposable is on the other side
of that decision and has to say so." **Cost of being wrong:** disk. A forked long session
is a few megabytes and there is no garbage collection, so the project directory grows.
Accepted; documented; not solved in v1.

### D3 — Only `tool_result.content` is ever touched

Never `tool_use`, never assistant text, never user turns, never `thinking`. This copies the
vendor's own default (`clear_tool_inputs: false`) and gives a boundary a person can check
in one line of code. **Rejected:** stripping `tool_use` inputs too, which is 25.8% of
message content **[measured in SPEC §1]** and therefore tempting. Rejected because the
input is what makes a pointer legible, and because `Write` and `Edit` inputs *are* the
change the session made. **Cost of being wrong:** winnow leaves a quarter of the volume
untouched by construction. Its ceiling is the 65.8% that is `tool_result`.

### D4 — Substitute a pointer, do not delete and do not empty

The Messages API requires every `tool_use` to be answered; `content` is documented as
optional, so an empty result is legal, but the vendor's own strategy substitutes text.
**Rejected:** empty `content` (cheaper by ~120 bytes per strip, and nobody has published
whether it degrades behaviour differently — recorded as Q3 below). **Cost of being wrong:**
120 bytes × the number of strips, which at a median session is on the order of a few
hundred results, so under 50 KB. Cheap insurance.

### D5 — Three tiers, `CB` the default, `A` gated behind `--i-know`

Tier C alone is 3.5% and does not justify the tool. Tier A is 7.06% more but strips reads
of files the session then edited, which is the class most likely to have been load-bearing.
**Rejected:** a single flat rule set (hides the risk gradient), and a learned or scored
threshold (violates the no-model constraint, and Squeez's BM25 baseline collapsing to 0.22
recall against a learned model's 0.86 is a caution that scoring heuristics fail in a way
structural rules do not). **Cost of being wrong:** if tier B turns out to be the harmful
one and A the safe one, the tiering is backwards and the default is wrong. Milestone 3
measures tiers separately for exactly this reason.

### D6 — The rules ship as data the operator can read, argue with, and disable

Every pointer names the rule that fired. `--no-rule B2` turns one off. **Rejected:** an
opaque scoring function, and a config file (two call sites is not a pattern; flags are
enough until they are not). **Cost of being wrong:** a rule set expressed as flags gets
unwieldy past about a dozen rules. Acceptable at six.

### D7 — No `claude` subprocess in the tool; one in the bench

`winnow fork` prints a resume command and stops. `winnow bench` spawns `claude -p` because
an A/B cannot be run any other way. **Rejected:** wrapping the CLI so the operator runs
`winnow claude ...` (puts winnow in the failure path of every run for no measurement
benefit) and a daemon watching for session end (a service to operate, for a tool used a few
times a day). **Cost of being wrong:** one extra copy-paste per use.

### D8 — Evaluate on cache-adjusted cost per *successful* task, never on tokens

Token reduction is the metric this whole class of tool reports and it is the reason none of
them has told anyone anything. **Rejected:** percentage of context removed (Cursor's 46.9%
already exists at blog grade with no quality data), and raw dollars (run-to-run token cost
varies up to 30× on the same task, `[[The Cost Shape of an Agent Run]]` medium, so a point
estimate is meaningless). **Cost of being wrong:** the measurement is roughly ten times more
work than the tool. That is the appetite, deliberately.

## 4. Rabbit holes

Named so nobody wanders in unwarned.

- **Read supersession with ranges.** `Read` takes `offset` and `limit`. Deciding whether a later ranged read supersedes an earlier one is interval arithmetic over a file whose line count may have changed between the two calls. The honest v1 rule is: a ranged read is superseded only by a read with no range, or by one whose `(offset, limit)` provably covers it. Anything cleverer is a week.
- **Bash command classification.** `ls` is easy. `cd x && cat y | head -20` is a parse. `bash -c "$(cat script.sh)"` is not decidable at all. The rule matches the first token of the first segment and nothing else; resist every request to make it smarter, because every increment of cleverness is an increment of silent misclassification.
- **Path equality.** `./src/a.ts`, `src/a.ts`, `/abs/src/a.ts` and a symlink are the same file and four different strings. Winnow compares strings and does **not** touch the file system (SPEC §10, untrusted input). This under-fires, which is the correct direction, and the under-firing must be reported rather than hidden.
- **The record types nobody documents.** 563 transcripts contain at least eleven record types (`mode`, `bridge-session`, `file-history-snapshot`, `attachment`, `ai-title`, `last-prompt`, `file-history-delta`, …) and `attachment` alone has twenty-odd subtypes. Winnow passes every record it does not understand through unchanged and must never "clean up" one. The format is undocumented and will change.
- **Compaction interaction.** 12.6% of sessions here carry a `compact_boundary` **[measured in SPEC §6]**, and `ContextControl/19-` established that a compaction survives `--resume`. Winnow forking a session that has compacted is forking a transcript whose early history is already a summary. It should refuse, or at minimum report it — undecided, and Q4 below.
- **The `usage` field's meaning.** `[[Prompt Caching]]` (high) documents the trap that `input_tokens` counts only what follows the last cache breakpoint. Any cost arithmetic built on a naive read of `usage` will be wrong in a direction that flatters the tool.
- **"Just make the rules better."** SPEC §5 is the answer: the reasoning that would settle once-only versus durable is stripped from the transcript before it reaches disk. No rule can see what is not in the file.

## 5. Risks, likelihood, impact, mitigation

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| The cache is not actually cold at resume, so every fork pays an unnecessary write | Low | Kills the economic case | Falsifiable from `usage` on the first post-resume turn, with no model call. **First check of milestone 1** |
| Stripping tier B costs correctness | Medium | Kills the default | Milestone 3 measures tiers separately with a pre-registered ±5-point equivalence bound |
| The saving is real but too small to care about — skim's own author estimates 0–15% for this predicate | Medium | Project is a null result | A null result on a question three vault notes record as unanswered is the deliverable. Say so up front rather than discovering it at week two |
| Re-fetch costs more than the strip saved | Medium | Inverts the sign | `ContextControl/03-` puts the break-even at 3.9 KB of re-reading per cycle, and verbatim re-reads are 0.3% of tool-result bytes. Guardrail metric in SPEC §9 counts stripped-then-re-read events directly |
| File-delivery inversion: the one measurement in Claude Code + Opus shows grep 76.7% → 68.1% under file delivery | Low–medium | Undermines the retrieval path | `[[Why Does File-Based Tool Output Invert the Grep Advantage]]` is **confidence: low**, n=116, unreplicated. Mitigated by design: route 1 recovers from the file system, not from a winnow-written file. Timeboxed spike: **half a day** to check whether any stripped result in the corpus was ever recovered from anything but the original file |
| The transcript format changes | High over months | Breaks the parser | Pass unknown records through unchanged; pin nothing; fail loudly with a line number. Accepted as a maintenance cost, not designed around |
| Winnow writes an unresumable session | Low | Loses a session's work | G5 is a hard failure; the original is never modified; milestone 2's definition of done is 100 forks resumed with exit code 0 |
| Measuring this properly costs more than two weeks | **High** | Blows the appetite | Milestone 3 is explicitly the part that may not fit. If it does not, the project ships milestones 1–2 and the experiment is scoped separately. Stated now so it is not discovered later |
| A stripped session leaks a credential through `--explain` output | Low | Security | `--explain` prints tool arguments, which routinely contain pasted secrets. Documented in SPEC §10; no log file by default |

## 6. Open questions, listed as open

**Q1 — Does the cold-cache argument survive contact with the harness?** The whole
economic case rests on a resume past the TTL paying a full cache write regardless. This is
inferred from two vault notes and vendor documentation, not observed on this harness.
*Answerable from disk in milestone 1.* Until then it is an assumption, and it is the
assumption everything else stands on.

**Q2 — Is tier B's mass real in tokens, or an artefact of bytes ÷ 4?** Bash inspection
output and file contents tokenise very differently, and the 22.6% figure is a byte share.
The direction is unlikely to change; the magnitude could move several points either way.
*Answerable by running one tokeniser over the corpus.* Not done.

**Q3 — Does an empty `tool_result` degrade behaviour differently from a placeholder?**
Both are legal. Anthropic chose a placeholder for `clear_tool_uses`, which is weak evidence
that it is better, but nobody has published a comparison. Two independent searches found
none on 2026-08-23. *This is a free arm in milestone 3 and should be added if the budget
allows.*

**Q4 — What should winnow do with a session that has already compacted?** Forking one means
rewriting a transcript whose early turns are a summary somebody else wrote. Refusing is
safe and loses 12.6% of sessions. Proceeding is probably fine and is unmeasured. *Currently
undecided; `inspect` reports it either way.*

**Q5 — Does the operator's own rejection of this option class still bind?**
`ContextControl` scored Option E (externalise tool output) at +1 of a possible +24 and
recommended against it, but it scored it as a *mid-session* mechanism with a fourth store.
Winnow is the same idea at a different cut point with no store. Whether that is a material
difference or a rationalisation is a judgement, and this document takes the position that
it is material — `T* = −1` at a cold boundary versus `T* = 170` at a tenth-suffix
mid-conversation cut is a difference of two orders of magnitude, not a framing. *A reviewer
who thinks otherwise should say so before milestone 2, not after.*

**Q6 — Is the 39.5%-never-mentioned-again mass reachable at all?** `ContextControl/00-`
measured it and refused to act on it because the proxy cannot distinguish "wasted" from
"read and understood". Winnow does not ship that rule. But it is roughly as large as tiers
B and A combined, and if it is ever made safe the project's ceiling doubles. *Nothing in
the transcript will settle it, because the thinking is stripped. It would need an
instrumented harness that records what the model attended to, which nobody has.*

## 7. What this document deliberately does not claim

That winnow will save money. That the rules are correct. That 22.6% of bytes is 22.6% of
tokens or of dollars. That the operator's prior survey was wrong. That the tool is novel —
it is not; the novelty, if any, is in the evaluation and the cut point.

`[[Prompt Caching]]` (high) closes with its own open question — "[w]hether aggressive
curation and a high hit rate can coexist" — which is to say the vault records, at its
highest confidence grade, that this project's central tension is unresolved. That is the
honest state of the art and this document does not improve on it. It proposes to measure
it.
