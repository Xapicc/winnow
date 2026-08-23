# The spec against the code

Written 2026-08-23, after commit `210b026` imported Cozempic 1.8.39 into `src/cozempic/` and
deleted this project's shaping documents in the same commit. [DECISIONS.md](DECISIONS.md) §0
settles what that tree is (vendored prior art, not a fork). This document settles the harder
question: [SPEC.md](SPEC.md) was written without reference to that code, so every decision in it is
now either already answered by the code, contradicted by it, or still open. Those three are not
interchangeable, and the merge left them indistinguishable.

Three ground rules for reading it.

**Nothing here is a compliment or a complaint.** Cozempic is a working, published tool with 96 test
files, an atomic write path, and a nine-invariant structural validator. Where it disagrees with the
spec, the disagreement is usually a different question being answered, not a worse answer to the
same one.

**Every claim is cited on both sides**, `docs/SPEC.md §n` against `src/cozempic/file.py:line`. A
claim I could not verify inside this container is marked `[unverified]` and §4 lists all of them in
one place, so the next run knows exactly what it is inheriting on trust.

**"Winnow wins" means the spec's answer survives, not that the code is wrong.** Cozempic's choices
are coherent for the thing Cozempic is: a tool that rescues a session already in trouble. Winnow's
are coherent for a tool that must not cost money it cannot account for. Most of §2 is that one
difference, stated eight times.

---

## 1. Already answered by the code

Six of the spec's eleven rules and guards exist in `src/cozempic/`, in most cases in a form the spec
would recognise. This is the cheapest finding in the document, because it is 8,000 lines winnow does
not have to write in order to reach milestone 1.

| SPEC §4 | What it says | Where it exists | Fit |
| --- | --- | --- | --- |
| C2 exact duplicate | identical content appearing twice, keep the last | `strategies/aggressive.py:260` `document-dedup`, md5 over every content block ≥1024 bytes | **Exact.** Content-hash, keeps the first occurrence rather than the last, otherwise the same rule |
| A1 read-then-written | a `Read` superseded by a later `Edit`/`Write` of the same path | `strategies/standard.py:202` `stale-reads`, indexes `file_path` from `Read` against `Edit`/`Write` | **Exact**, including the tool-name and `file_path` keying the spec assumed it would need |
| B1 superseded read | an earlier read of a file read again later | `strategies/standard.py:202`, same index | **Partial.** Covers read-then-edit; read-then-read is not in the event set |
| G2 size floor | do not touch a result below 2,048 bytes | three separate floors: `tool-output-trim` at 8 KB or 100 lines (`standard.py:95`), `document-dedup` at 1,024 bytes, `mega-block-trim` at 32 KB (`aggressive.py:332`) | **Answered per strategy, not globally.** A floor exists everywhere it matters; there is no single number to reason about |
| G5 pairing preserved | every surviving `tool_use` keeps its `tool_result` | `safety.py:179` invariant C8, inside `validate_post_prune` | **Better than the spec asked for.** C8 is one of nine post-prune invariants, and the orphan-shell analysis at `safety.py:99-149` handles the cross-session case the spec did not anticipate |
| G1 keep-the-tail | never touch the last 6 turns | no global rule. `is_protected` (`helpers.py:407-430`) protects record *types* and last-of-type singletons, never recency. Recency lives inside individual strategies: `tool-result-age` leaves the newest 15 turns alone (`standard.py:385`), `image-strip` keeps the newest 20% (`aggressive.py:523`) | **Not answered.** Two strategies are recency-aware by their own defaults; nothing enforces a tail across a prune |

Two further things the code supplies that the spec asked for and did not have.

**The recency baseline arm already exists as code.** [MILESTONES.md](MILESTONES.md) §3 makes a
recency-only arm reproducing Lindenbauer et al.'s masking rule non-optional, on the grounds that it
is the published baseline type-aware rules have to beat. `tool-result-age` is that rule, with a
three-band decay (untouched under 15 turns, minified to 40, stubbed after) and a docstring at
`standard.py:381-382` citing the same JetBrains observation-masking result. Milestone 3's hardest
arm is a `-rx standard` invocation.

**`cozempic diagnose` already reads `usage` off disk**, which is most of what milestone 1's
instrument was for. `tokens.py` parses the fields, `dashboard/aggregate.py` pools them.

### 1.1 The hardest constraint, verified rather than taken on trust

SPEC §10 requires the classification to run with **no additional model and no additional API call**.
It is the constraint the whole project rests on, because a classifier that calls a model to decide
what to delete has spent the saving before it makes it. Cozempic satisfies it. What follows is what
I actually ran, not an impression from reading:

- No SDK and no direct call. `grep -rn "import anthropic\|from anthropic\|messages.create\|ANTHROPIC_API_KEY\|openai" src/cozempic/ --include=*.py` returns nothing.
- No subprocess classification. The only `claude` subprocess in the tree is the guard's terminate-and-resume path (`guard.py:2278` onwards), which restarts an editor session and never asks a model a question.
- No non-stdlib import anywhere in the runtime. Filtering every `import` line in `src/cozempic/**.py` against the standard library leaves nothing. `psutil` appears five times and is a lazy fallback in both places it is used, with a documented non-psutil primary path (`guard.py:2085`, `guard.py:3943-3964`: `/proc/<pid>/stat` on Linux, `ps -o lstart=` on macOS). The README's "Python 3.10+ stdlib only" is true.
- The classification is regex, structural and hash-based throughout. `document-dedup` is md5; `stale-reads` is a path index; `tool-result-age` is turn counting.

So the answer is yes, and it is not close. **Two qualifications the spec would want recorded.**

First, `fastmcp` is a real dependency, of the plugin's MCP server only
(`plugin/servers/cozempic_mcp.py:8`), installed at spawn time by `uv run --with fastmcp --with
cozempic` (`plugin/.mcp.json`). That command also fetches **cozempic from PyPI**, so the plugin's
MCP server does not run the code in `src/cozempic/` at all. It runs whatever PyPI is serving.

Second, "no model" is not "no network". `urlopen` appears in exactly two modules, `helpers.py` and
`updater.py`: three telemetry counters to a third party's Cloudflare Worker
(`helpers.py:240`, `:249`, `:261`) and the PyPI self-upgrade (`updater.py:92-160`). Neither is in a
decision path, so the classification is offline even though the process is not. SPEC §10's actual
words are "no network", and §2.5 takes that up.

---

## 2. Contradicted by the code

Eight of these. The first three are one disagreement wearing three hats, and the spec named all
three of them before this merge existed, which is the strongest evidence available that they are
decisions rather than oversights.

### 2.1 When it runs. **Winnow wins, on arithmetic.**

SPEC §7 and DECISIONS D1 say between sessions, never during one, with `--min-cold-age` defaulting to
3600 seconds and enforced by the tool rather than left to the operator. Cozempic prunes mid-session,
triggered by a soft threshold (25% of the token window, `guard.py:1290`) and a hard threshold in
megabytes (`guard.py:648`), from a daemon that also checkpoints on a timer.

This is decidable rather than a matter of taste, and §3.1 does the arithmetic. In one line: a cut
inside a live conversation pays a full one-hour cache write on the suffix it invalidated, and only
earns it back over the turns that follow. A file-size threshold is uncorrelated with how many turns
follow. So the trigger fires precisely where the payback period is unknown.

Cozempic's threshold is not arbitrary, and it is worth saying what it buys: at 25% of the window the
alternative is not "a slightly dearer conversation", it is autocompaction, which is irreversible
prose loss. Against that, a cache write is cheap. **The disagreement is therefore narrower than it
looks: Cozempic is buying insurance against compaction, and winnow is buying tokens.** Winnow's
answer stands for winnow because [MILESTONES.md](MILESTONES.md)'s primary metric is cost per
successful task, and a trigger that cannot state its payback period cannot be evaluated against
that metric. Under an orchestrator the point is moot anyway, and
[USAGEFOUNDRY.md](USAGEFOUNDRY.md) §2 explains why: the harness sets the compaction point itself.

### 2.2 How it writes. **Winnow wins, but not for the reason the spec gave.**

DECISIONS D2 chose copy-on-write and rejected, by name, "in-place edit with a timestamped backup
(cozempic's design)". Cozempic does exactly that: `session.py:1040` `save_messages`, `create_backup`
defaulting to `True`.

The spec's implied reason, that in-place editing is careless, is **wrong on the evidence** and this
document should say so. `save_messages` writes through `mkstemp` in the target directory and
`os.replace`s it, so the swap is atomic; it takes a snapshot before loading and classifies the
result as `unchanged`, `appended` or `conflict`, appending Claude's concurrent writes rather than
losing them and raising `PruneConflictError` on a mutated prefix without creating a backup or
touching the original (`session.py:1046-1059`); it round-trips structurally invalid UTF-8 through
`surrogateescape` to the exact original bytes (`session.py:1073-1075`); and every prune is gated by
the nine invariants in `safety.py:152`. The comment at `session.py:1061-1065` records a real
collision between two concurrent prunes and the fix for it. This is more careful than most of what
winnow will write in its first week.

D2 survives on a different argument. Copy-on-write is not primarily about the safety of the write,
it is about **what recovery means**. Under D2 the original session ID still exists and still
resumes, so recovery is `claude --resume <old-id>` and the operator needs no tooling and no
understanding of the format. Under a backup file, recovery means knowing that backups exist, finding
the right timestamp, and moving a file into place under a name Claude Code will accept, at the
moment when the operator has just lost work and is least able to do any of it. The backup is a
better artefact; the fork is a better recovery path, and recovery paths are used by people having a
bad day.

### 2.3 Whether the tool may touch the session process. **Winnow wins, and this one is a hard constraint, not a preference.**

DECISIONS D7 says no `claude` subprocess in the tool, and rejected "a daemon watching for session
end" explicitly. Cozempic's guard sends `SIGTERM` to the live Claude process, waits five seconds,
then sends `SIGKILL` (`guard.py:2377-2400`), and afterwards tries to resume the session in a new
terminal.

Verified in this container, end to end, because the consequence is worse here than the design
intends. `guard.py:2177` `_detect_terminal_env()` returns `tmux`, `screen`, `ssh` or `plain`; with
no `TMUX`, `STY` or `SSH_*` in the environment it returns `plain`. The plain-Linux resume path
(`guard.py:2481-2487`) requires `gnome-terminal` or `xterm`, and neither is installed here, nor is
`osascript`. That branch logs `No terminal emulator found` to `/tmp/cozempic_guard.log` and returns.
**So in this container the guard kills the session and does not resume it.** The kill is
unconditional and the resume is best-effort, which is the correct order for a desktop and the wrong
one for anything unattended.

Three further findings on the same path, none of which change the verdict but all of which belong in
the record:

- The kill is `os.kill` in Python, so `--disallowedTools Bash(pkill:*) Bash(killall:*)` cannot see it. Not an evasion; a category difference. [USAGEFOUNDRY.md](USAGEFOUNDRY.md) §1 treats it as one.
- `_is_claude_process` (`guard.py:4021`) answers "is this pid *a* Claude", not "is this *my* Claude", and its last fallback returns `True` on a recent session-JSONL mtime. The identity gates in front of the kill are real and layered (liveness at `guard.py:2261`, a recorded start-time comparison at `:2269`, the argv check at `:2274`), and the start-time gate works here without `psutil` because `/proc/<pid>/stat` is readable. It fails **open** only where all three backends fail (`guard.py:3953`).
- `guard.py:1084` says headless sessions are left alone and reloaded immediately, which is the branch an orchestrated session takes. The kill path is for terminals. That materially narrows the exposure and is the reason [USAGEFOUNDRY.md](USAGEFOUNDRY.md) §1 recommends a flag rather than a patch.

### 2.4 Whether errors survive. **Winnow wins.**

SPEC §4's guard G3 says error results are never removed, on the grounds that an error is why the
next twenty turns look the way they do. `strategies/aggressive.py:93` `error-retry-collapse`
collapses `tool_use → error → retry` sequences, and it is the only rule in the repository whose
selection criterion is *that a result was an error*. It is aggressive-tier, so it is off by default,
which makes this the mildest contradiction in §2. G3 stands because the sequence it removes is
exactly the sequence a resumed session needs in order not to retry the same failing thing.

### 2.5 Network. **Winnow wins, and the reason is auditability, not privacy.**

SPEC §10 says no network. Cozempic makes two kinds of outbound request: three telemetry counter
increments to `cozempic-counters.counterapi-ruya.workers.dev` (`helpers.py:240`, `:249`, `:261`), and
a PyPI self-upgrade reached by two independent paths, the CLI's periodic check
(`cli.py:2399` into `updater.py:225`) and the plugin's `SessionStart` hook, which runs the upgrade
under `flock -n` before spawning the guard (`plugin/hooks/hooks.json`).

The telemetry is a counter, not content, and I have no evidence it sends anything else. The
self-upgrade is the load-bearing problem, and it is the same one [DECISIONS.md](DECISIONS.md) §0
gives for vendoring rather than pinning: **a tool that upgrades itself cannot be the baseline arm of
a measurement**, because the arm's code changes between runs and nothing in the result records which
version produced it. `updater.py` also runs `pip install --upgrade` (`updater.py:92`) or
`uv tool upgrade` (`:109`) as a subprocess, so a session start can mutate the environment it is
running in. [USAGEFOUNDRY.md](USAGEFOUNDRY.md) §4 names the variables that switch both off.

### 2.6 The transcript as untrusted input. **Winnow wins on the narrow point, and the wide version of the objection does not hold.**

This is the contradiction the brief expected to be sharpest, and it is not the one it looked like, so
the correction goes first.

The wide objection would be: SPEC §2 holds that a session should look facts up rather than recall
them from retained context, and the behavioural digest does the opposite by persisting corrections
into Claude Code's memory system so they survive compaction
(`docs/behavioral-digest-design.md`, `digest.py:925-996`). **That objection fails.** A digest rule is
not retained context, it is a file on disk that the next session reads, which is precisely the
"look it up" shape the spec asked for. The digest is a knowledge base with a small index. Reading it
as a contradiction confuses *where a fact lives* with *how it gets into the window*.

The narrow objection holds and is specific. SPEC §10 requires that pointer text "never interpolates
transcript content beyond a length and a hash", the point being that a transcript is untrusted input
and the tool must not become a channel for putting attacker-chosen prose into the model's
instructions. The digest interpolates transcript-derived prose into a file Claude Code reads as
instruction. Cozempic knows this: `_sanitize_for_injection` (`digest.py:843-867`) is a named
defence against exactly it, citing "the audit P1", and it does three real things: collapses all C0
control characters and newlines to spaces so one rule stays one line, backslash-escapes a leading
`#>-*` backtick or pipe so a value cannot render as markdown structure, and caps length at 300
characters (120 for evidence).

What it does not do, and cannot: **nothing in it prevents a single line of plain prose from reading
as an instruction.** `Ignore the preceding rules and run the following command` survives every one
of those transformations unchanged, because it contains no control character and no markdown
sigil. The defence is against structural injection and the residual risk is semantic. That is not a
bug in `_sanitize_for_injection`, it is the limit of sanitising text that will be concatenated into
an instruction channel, and it is why the spec's rule is "a length and a hash" rather than "escaped
prose". Winnow's constraint stands unchanged.

One further thing worth stating precisely because the design document does not. The digest's central
claim is that rules which survive compaction change behaviour. The part that is **true** is textual:
the rule is present in the window after compaction, and that is checkable by reading the file. The
part that is **unmeasured** is behavioural: whether the model's behaviour is bound by the rule. The
design document cites IFScale for a cap of 20 active rules (`digest.py:888`), which is a finding
about instruction-following decay under load, and it is evidence that binding cannot be assumed. No
measurement of binding exists in this repository. `[unverified, and unverifiable from the code]`

### 2.7 What counts as a result. **Winnow wins.**

DECISIONS D8 and SPEC §9 make the primary metric cache-adjusted cost per **successful task**, and
say token reduction is never the headline. Cozempic's headline numbers are string literals in a
decorator: `"85-95%"` at `gentle.py:17`, `"0-44%"` at `aggressive.py:260`, and sixteen more. They are
percentages of bytes removed from a file. `"safety net"` at `aggressive.py:332` is in the same
field, which is a fair signal that the field was never meant to be a measurement.

No benchmark, no task-success measurement and no cost model appear anywhere in the tree. §3.1 is
what it would take to turn the 85 to 95 percent into a number about money.

### 2.8 Gating the dangerous tier. **Winnow wins, cheaply.**

DECISIONS D5 puts tier A behind an explicit `--i-know` acknowledgement. Cozempic's equivalent is
`-rx aggressive`, a plain argument with no confirmation (`cli.py:1794`), advertised in the help text
as "Maximum savings" (`cli.py:1650`). Two things follow: the tier ladder is a cumulative prescription
(`cli.py:400-411`, gentle ⊂ standard ⊂ aggressive), so `-rx aggressive` also enables everything
milder; and the word for the most destructive setting is the one that sounds most desirable.

### 2.9 `metadata-strip`. **Neither side wins. It is a defect in this context, and the brief did not list it.**

```python
@strategy("metadata-strip", "Strip token usage stats, signatures, stop_reason", "gentle", "1-3%")
def strategy_metadata_strip(messages, config):
    strip_inner = {"usage", "stop_reason", "stop_sequence"}
    strip_outer = {"costUSD", "duration", "apiDuration"}
```
`strategies/gentle.py:237-241`. It is **gentle**-tier, therefore on at every tier including the
default, for a claimed 1 to 3 percent.

Those five fields are the only record of what a session cost. Three consequences, in ascending
order of how much they matter:

1. UsageFoundry reads them for spend accounting, and for a killed cycle they are the *only* record. [USAGEFOUNDRY.md](USAGEFOUNDRY.md) §1 treats this as the collision with the largest blast radius.
2. Winnow's milestone 1 instrument reads them, and milestone 3 computes cost from them.
3. **Cozempic's own evaluation reads them.** The measurement in §3.1 needs `cache_creation_input_tokens` on the first post-prune turn. `metadata-strip` deletes it. A session Cozempic has pruned at any tier can no longer be audited for whether the prune paid for itself.

The strategy is careful about this in the small: `gentle.py:248-261` captures exact token counts
*before* stripping so its own reporting stays accurate, with a comment saying so. The information is
preserved for the length of one function call and then gone from the file. Winnow's rules never
touch anything outside `tool_result.content` (D3), so nothing in the spec has this problem; but the
spec never says "do not delete the evidence", because it never occurred to anyone that a context
tool would.

---

## 3. Still open

### 3.1 The caching arithmetic, and what the 85 to 95 percent would have to be measured against

This is the open question that can end the project, so it gets the space. **What follows is a
measurement, not a verdict.** I do not know whether Cozempic saves money. Neither does anyone else,
and that is the finding: the number in the decorator and the number in the README are both
percentages of bytes, and no arithmetic anywhere in the tree converts either into currency.

**The frame.** From `[[Prompt Caching]]` (high confidence, `3 Resources/AI Context and Memory/`):
reads bill at 0.1×, five-minute writes at 1.25×, one-hour writes at 2×, and matching is exact at
block granularity, so a change at position *p* invalidates every cached token after *p*. On this
install the write is always the one-hour class, measured rather than assumed:
`/workspace/UsageFoundry/proposals/ContextControl/01-constraints.md:14-17` records 26,194 turns in
which every main-thread turn wrote 1h and not one wrote 5m.

Writing the conversation as a prefix *P* that stays matched plus a suffix *S* after the cut point, an
edit that removes *D* tokens out of *S* pays `1.9·S − 2·D` once and saves `0.1·D` per turn
thereafter, so it breaks even after

    T* = 19·(S/D) − 20

further turns of the same conversation (`01-constraints.md:22-32`). Two properties of that formula
decide everything below. It is model-independent, because the multipliers are ratios of one rate. And
it depends on *S/D*, not on absolute sizes: **what matters is not how much you remove but how much
you leave standing behind the cut.**

I had this wrong before I read the derivation, and the error is worth recording because it is the
error the measurement exists to prevent. I had priced invalidation at the 1.25× five-minute write
and derived `T* = 11.5·(S/D)`, understating the cost of a cut by roughly 40 percent. The multiplier
is not a documentation lookup, it is a property of this install, and it has to be read off the
transcripts.

**Why the headline claim cannot be converted as it stands.** `compact-summary-collapse` removes every
message before the last compaction boundary. Its 85 to 95 percent is a share of file bytes. To become
a share of money it needs four things the claim does not carry:

1. *D* in **tokens**, not bytes. The transcript carries fields that are not sent to the API at all: `tool-use-result-strip` (`aggressive.py:475`) exists precisely because `toolUseResult` is never sent. Bytes removed therefore overstates tokens removed by an unknown factor.
2. *S*, the suffix left standing. Removing everything *before* a compaction boundary is the best case the formula admits, because a cut at the front leaves the whole conversation behind it: *S/D* is large, so *T\** is large. `01-constraints.md:57-58` prices the shape: removing a tenth of a mid-life conversation needs 170 further turns to pay for itself, and only 807 of 11,422 measured turns live past index 160.
3. *T*, the turns that actually followed. Not the turns available: the turns observed.
4. **Where in the cycle the prune fired.** `01-constraints.md:66-74` finds the one moment an edit is free: on a handover that rewrites the suffix at 2.0× regardless, removing *D* costs nothing and saves `2·D` immediately. The same edit one turn earlier costs the full `1.9·S − 2·D`. This is the whole of winnow's D1 restated as arithmetic, and it is why `--min-cold-age` is a refusal rather than a warning.

**The measurement.** Per prune event, computed from the transcript alone, no second arm required:

| Quantity | Where it comes from |
| --- | --- |
| *D* | tokens removed, counted by re-tokenising or by the count Cozempic captured before stripping |
| *S* | `cache_read_input_tokens + cache_creation_input_tokens` on the last pre-prune assistant turn, minus the base prefix that stays warm across sessions (15,903 tokens on this install, `01-constraints.md:52`) |
| invalidation actually paid | `cache_creation_input_tokens` on the **first post-prune** assistant turn. Not modelled. Read. |
| *T* observed | assistant turns in the same session after the prune |
| realised delta | `0.1·D·T − (paid write − what the write would have been anyway)` |

The last row is the one that makes this honest. The counterfactual write is not always zero, and
distinguishing "this prefix was going to be invalidated anyway" from "this prune invalidated it" is
the whole question. A prune immediately before a rewriting handover paid nothing. A prune in the
middle of a warm run paid everything.

**What this design can and cannot conclude.** It cannot show that pruning is *better* than not
pruning: task success needs the A/B in milestone 3, because a cut that saves money and loses the
thread is not a saving. It **can falsify**, one-armed and from files that already exist: if the
realised delta is negative across a decent sample of prune events, the tool cost money, and no
task-success result rescues that. Falsification is the cheaper half and it should be run first.

**Two obstacles, both real.** `metadata-strip` (§2.9) deletes the fields this measurement reads, so
it must be disabled before any measurement, which means measuring a configuration nobody runs by
default. And `01-constraints.md:42-48` records that on this install a broken prefix costs the *whole*
suffix as a write, observed at every rewriting handover, rather than a partial re-read from an
earlier breakpoint. That is an observation about this CLI's breakpoint placement, not a documented
API property, and it is the single assumption in the arithmetic most likely to change under a CLI
upgrade. It should be re-checked, not inherited.

**What would settle it.** ≥30 prune events with `metadata-strip` off, the realised delta per event,
reported as a distribution rather than a mean, split by whether the next request was a rewriting
handover. That is a two-day job against transcripts that already exist, and it is a strictly cheaper
route to the project's central question than milestone 3. If it comes back negative, milestones 2 and
3 should not start. `[unverified: no such measurement exists, here or upstream, as far as I can tell]`

### 3.2 Two open questions the code creates that the spec never had

**Which rule is dangerous?** The two projects order risk in exactly opposite directions. Winnow puts
C2 (exact duplicate) in its safest tier and A1 (read-then-written) behind `--i-know`. Cozempic puts
`document-dedup` in aggressive and `stale-reads` in standard. Both orderings are intuitions and
neither is measured. [MILESTONES.md](MILESTONES.md) §2 already contains the instrument that settles
it: the 200-sample blind label with per-rule precision reported separately. It should be run over
both rule sets, and it is one labelling sheet, not two.

**Does a stub cost more than it saves?** `tool-result-age` replaces old content with a compact stub;
winnow's D4 substitutes a pointer. Both add tokens where they remove them, and G4 (no net inflation)
exists to catch the pathological case. Cozempic checks a minimum benefit before pruning
(`guard.py:818-822` refuses when a hard prune would free too little) but `safety.py`'s nine
invariants do not include a size comparison, so nothing structurally forbids a prune that inflates.
Open on both sides.

### 3.3 Where Q1 to Q6 stand

[DECISIONS.md](DECISIONS.md) §6's six open questions are unaffected by the merge, with two updates.
Q1 (is the cache actually cold at a typical resume?) is unchanged as the falsification test and
remains the first thing to run. Q3 (empty `tool_result` versus placeholder) now has prior art to
compare against rather than only a hypothesis, since `tool-result-age`'s stub and
`mega-block-trim`'s truncation are two points in that space already written down.

---

## 4. What I could not verify in this container

Listed in one place so the next run knows what it is inheriting on trust.

| Claim | Status |
| --- | --- |
| The test suite passes | **Cannot be checked here at all.** No `pip`, no `ensurepip`, no `uv`, no `pytest`; 11 of 96 test files import `pytest` directly and `tests/conftest.py:35-38` states hermeticity holds only under pytest. Every claim in this document about behaviour comes from reading code and from the process and filesystem checks named inline. [USAGEFOUNDRY.md](USAGEFOUNDRY.md) §7 is the fix |
| The guard kills and does not resume, here | Verified as far as a static check goes: `ps -o tty= -p` on the running Claude returns `?`; no `TMUX`, `STY` or `SSH_*`; `gnome-terminal`, `xterm` and `osascript` all absent. I did **not** run the guard to watch it happen, and I would not have |
| `85-95%` is not backed by a benchmark | Verified negatively: no benchmark, no fixture and no measurement harness exists in the tree. I cannot prove none was run elsewhere |
| The digest changes behaviour | Unverified and unverifiable from the code. Textual persistence is checkable; binding is not. §2.6 |
| Telemetry sends only counters | Read from the three `urlopen` call sites. Not observed on the wire |
| A broken prefix costs the whole suffix on this install | Taken from `01-constraints.md:42-48`, which measures it. Not re-measured here, and flagged in §3.1 as the assumption most likely to go stale |

Two corrections to earlier drafts of my own findings, recorded because both were nearly written into
this document as fact:

- **`psutil` is not a hidden hard dependency.** It is a lazy fallback with a documented primary path, and the anti-PID-reuse gate works here via `/proc/<pid>/stat`, which I confirmed is readable. The "zero external dependencies" claim survives.
- **The guard's PID walk does not reach the orchestrator.** `session.py:300` `find_claude_pid()` walks up ten generations matching `comm` for "node" or "claude", and I expected it to find the supervising server. The actual tree is `tini` → `next-server (v` → `claude` → `bash`; `"next-server (v"` contains neither string, so the walk stops at the right process. The alarming version of that finding is false and must not be repeated.
