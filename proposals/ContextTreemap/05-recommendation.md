# Recommendation

**Build Option A — a one-shot terminal readout — as `winnow context <session-id>` in this
repository, with provenance (`01-` §5's H1) as the only tree, the floor priced into two derived
blocks rather than confessed as one grey one, and `--json` treated as the real interface rather
than a convenience. Not a TUI, not a browser page, not a new repository, not a card. Two weeks,
and the first slice is three days.** `03-option-a-one-shot-readout.md`.

The case is short, and it is not that A wins the capability table — **it does not.**
`04-comparison.md` scores B two points above A out of fifty-four, and that is the correct
result, because B contains A: same tree model, same classifier, same apportionment, same two
derived blocks, same exact anchors, plus a cursor. A table comparing a thing to itself-plus-more
was always going to come out that way.

The case is that **A is the whole of the instrument and none of the application.** All three
renders take the same +3 on the row that is the request — none of them is `/context`, all of
them drill the category `/context` leaves flat — so nothing about *knowing more* separates
them, and what B's extra 0.6–1× of build buys is two capability points and a permanently larger
maintenance surface. A is also what B and C need anyway: B's no-TTY fallback is A's printer,
and on this machine the most frequent caller of anything is an agent with no terminal; C's
payload is A's serialiser. Build the instrument, use it, and let the diary below decide whether
the cursor is worth the second build — which is a decision that gets cheaper, not dearer, by
being deferred.

---

## The two decisions, taken

### Where it lives: a subcommand of this repository

Not on reuse. `03-option-d` costs the copy honestly and it is a week: ~900–1,000 lines
transplanted and ~90 rewritten, and the postmortems that make `legacy/` valuable come across
with the comments that hold them.

It lives here **because of what a new repository leaves behind.** `winnow inspect` ships today
and reports `cache_read_input_tokens 18,378,780` for a session whose window at the last request
was 219,485 — a lifetime sum over every assistant record, printed beside a byte-share
breakdown, which is exactly the misreading this proposal exists to prevent (`01-` §6.1,
verified by running it). `winnow savings`, the only command that renders the prefix readout, is
broken on `main` at `cli.py:609`. Neither of those is a thing a new project would ever have a
reason to touch. Here, retiring the wrong instrument is a two-line deprecation on the day the
right one lands.

The coupling objection is real and it is smaller than it looks. Measured on this tree: `import
winnow.inspect` pulls 7 winnow modules in 15 ms and reaches neither `legacy.guard` nor
`legacy.team` nor `proxy`; `import winnow.cli` pulls 16 in 27 ms, because `cli.py:23` and `:25`
eagerly import `orchestrator_safe` and `proxy`. **The substrate is already factored the way a
subcommand needs it; only the front door is not.** Moving those two imports into their subparser
handlers is an independently good change and it is on M1's list.

**If the operator later spins this out**, the extraction is a `winnow.transcript` package
containing: `legacy/session.py:722–1037` (the parser and the incremental reader), the ~120
useful accessor lines from `legacy/helpers.py`, the block walk from `inspect.py:330`,
`report.py:47 resolve_session`, `legacy/tokens.py:297 extract_usage_tokens`, and the
measurement primitives from `rules.py` including `bash_head`. That extraction is a **later
cleanup, not a prerequisite** — it is worth doing on its own merits, it is what makes the spin-
out a move rather than a copy, and nothing in M1–M4 is blocked on it. What cannot come along is
`filter.py:728 prefix_facts`, which is a pure function of a Messages API request body and has
no meaning on a transcript; it stays here as the only available cross-check on the derived
prefix, and losing reach to it is the real price of a new repository.

### What the tree is: H1, provenance, and it is the only tree

`01-` §5 offers three hierarchies and declines to choose. Choosing:

**H1 — by provenance — is the default view and the only tree in the first useful version.** Two
reasons, and the second is the one that decides it. First, its top level is a set of things the
operator can change: configuration, working style, tooling, delegation. Second, **it is the only
one of the three that can hold the prefix at all.** After `02-constraints.md`'s correction, the
prefix is a median ~24% of the window and retained reasoning ~14% — 38% of the median window is
material with no artefact and no turn, and a hierarchy keyed on either of those has nowhere to
put the largest actionable block in the readout.

**H3 — by artefact — is not an alternative hierarchy. It is the second level under `tool
traffic`, and it ships in the first useful version.** Under `Read` and `Edit`, nodes keyed by
path with a repeat count; under `Bash`, by command head (`rules.py bash_head` already
normalises them); under `mcp__*`, by server then tool. This is where the actionable question
lives — `01-` §5 measured 37 distinct paths across `Read` and `Edit` on session `f6ea2591`,
with 34% of that combined output coming from paths touched more than once, and VibeHub's
independent census puts 44.3% of read spend on re-reading unchanged content. It is rejected
*as a root* because it cannot express the prefix, and because its "other" bin is routinely the
largest node: on `01-` §2.6 column E the top tool by result size is Bash at 135,899 estimated
tokens, and Bash output has no artefact.

**H2 — by chronology — becomes M4's `--by-turn`, and it is not a competing view. It is the
audit.** Every turn is a priced request, so the per-turn residual — exact `usage` delta minus
the estimated tokens appended — is the tool checking its own apportionment against a number it
did not produce. This is not a nice-to-have bolted on later: `02-constraints.md`'s correction
*is* a per-response computation, so M3 builds the entire H2 dataset in order to price retained
reasoning, and M4 only renders it. Dropped as a root for the reason `01-` §5 gives and this run
agrees with: 311 requests is 311 top-level nodes, which is a bar chart, and nobody wants to
delete turn 40.

---

## Appetite: two weeks, and what fits it

**Two weeks of one person's work.** Fixed. The scope below is what fits, and the scope moves,
not the date.

The rule for when it slips: **if M2 is not demonstrable at the end of day 6, drop M4 and ship
M1–M3.** M4 is live mode and the turn view; both are genuinely valuable and neither is what
makes the tool worth having. A tool that answers "what is in this finished session, and how
much of it is not in the file" is already the only thing on this machine that answers it. A
tool that also does it live is better and is not the point.

The three days for M1 are not optimism. `01-` §6.1 inventories what already exists and this run
re-checked the two claims the schedule rests on: the parse of the largest session in the
five-session table (`72acbacd`, 8,067,020 bytes, 1,525 records) takes **0.02 s**, and
`winnow.inspect` imports clean in 15 ms. The walk, the resolver and the parser are not being
written.

---

## The slices

### M1 — the walking skeleton (days 1–3, ~25% of the appetite)

The thinnest thing that runs end to end and touches every layer: resolve → parse → dedupe →
anchor → classify → apportion → print → `--json`. Top level of H1 only, no drill-down. Ugly.

- Resolve an id, a path, or an unambiguous prefix via `report.py:47 resolve_session`.
- Parse with `legacy/session.py`'s reader — `\n` splitting, `surrogateescape`, trailing-fragment
  buffering (§C8).
- Dedupe assistant responses on `message.id` before touching `usage` (§C8).
- Take the exact window from the anchoring request as `input_tokens + cache_creation +
  cache_read`, resetting the accumulator at every `compact_boundary` (§C3, §C6).
- Classify every surviving block into H1's top level, counting payload characters per `01-`
  §2.4 and excluding everything in §C4's closed list.
- Apportion the estimate inside the exact total; render one `unattributed` node for the rest.
- Print the tree with a provenance column; emit the identical tree as `--json`.
- Move the eager `orchestrator_safe` / `proxy` imports at `cli.py:23` and `:25` into their
  subparser handlers.

**Acceptance.**

- Given session `e698739e`, when `winnow context e698739e` runs, then the window total printed
  is exactly **219,485**, labelled `exact`, and the top-level nodes sum to it.
- Given session `2551cd0c` (three `auto` boundaries, at `preTokens` 167,327 / 168,578 /
  170,229 — verified by this run), when it runs, then the total is **116,030** and not 416,774,
  and a line above the tree states **444,326** cumulative dropped tokens as `exact`.
- Given session `72acbacd`, when it runs, then it reports a **512,133**-token window and prints
  **no** "% full" figure, because no `--window` was given (§C7).
- Given a session with no assistant record carrying `usage`, when it runs, then it prints the
  estimated tree, prints **no percentages at all**, exits non-zero, and names the missing
  anchor.
- Given `~/.claude` mounted read-only, when it runs on any session, then it exits 0 (§C1).
- Given the command has returned, when `sys.modules` is inspected, then it contains none of
  `winnow.legacy.guard`, `winnow.legacy.team`, `winnow.proxy`, `winnow.orchestrator_safe`.

### M2 — the drill-down (days 4–6, ~25%)

The reason the tool exists. Levels two and three, sorted biggest-first at every level, `--depth`
to cap.

- `tool traffic` → per tool → per Bash command head / per Read-and-Edit path with a repeat count
  / per MCP server → tool. This is H3, in its right place.
- `standing configuration` → per attachment class → per memory-file path, per MCP server.
- `Agent` calls → one node per sub-agent sized by its **return**, with the sub-agent's own
  transcript size shown beside it as a separate figure and never added (§C11).
- `<persisted-output>` nodes sized at the preview with the sidecar size in the label (§C9).

**Acceptance.**

- Given `f6ea2591` at `--depth 3`, when it runs, then `Read` and `Edit` together carry **37**
  distinct path nodes, paths touched more than once are marked with their count, and those
  paths' summed share of the two tools' combined output is within 2 points of **34%**.
- Given `e698739e` at `--depth 3`, when it runs, then the three result-bearing tools beneath
  `tool traffic` are Bash, Read and Edit in that order at 42,609 / 7,650 / 646 estimated
  tokens ±2%, and `tool_use` inputs are a sibling node at 18,087 ±2% and not folded into them.
- Given a session containing an `Agent` call, when it runs, then the parent's node is sized at
  the return only, and the sub-agent's own total appears in the label as a distinct number.
- Given a session containing a `<persisted-output>` wrapper, when it runs, then the node is
  sized at the ~2 KB preview, not the sidecar, and says so.

### M3 — the floor, priced, and the audit (days 7–9, ~25%)

- Prefix per session by first-request subtraction, rendered as a `derived` node.
- Retained reasoning per response by `output_tokens − est(text) − est(tool_use)`, summed over
  responses still inside the window, rendered as a `derived` node with the per-block median for
  *this* session beside it.
- `unattributed` as its own node — what is left, not what is hidden.
- `--audit`: the full reconciliation, plus the chars-per-token constant that would zero this
  session's residual, printed **with the words "not applied" beside it** (§C10).
- `--explain <node>`: the derivation sentence for any node. `04-comparison.md` scores B above A
  on exactly two rows — floor honesty and live-mode lag — and this flag buys the first of them
  for a small fraction of B's build. The second is M4's.

**Acceptance.**

- Given the 200-file even sample, when `--audit` and `scratch/thinking_price.py` are run over
  it **on the same day** — the sample is 160–168 sessions depending on when you ask, so this
  has to be a paired comparison rather than a threshold, per the note on the two runs in
  `02-constraints.md` — then the tool's median `unattributed` share is **≤5%** and **no worse
  than the prototype's**, and its within-±15% count is **no lower than the prototype's**.
- Given any session, when `--audit` runs, then it prints the solved constant and a line stating
  it was not applied.
- Given a session, when `--explain prefix` runs, then it prints the first-request context, the
  estimated visible tokens before it, and the subtraction — the three numbers, not a paragraph.

**Built and measured on 2026-09-03. `08-m3-measurements.md` records the run.** Median
`unattributed` **0.6%** against the prototype's 1.0% over 163 and 162 qualifying sessions of one
200-file sweep; within ±15% 149/162 against 148/162 paired. Prefix and retained reasoning came out
at 25.1% and 14.2% of the median window, against the ~24% and ~14% `02-constraints.md` predicted.
The residual kill criterion did not fire.

### M4 — live, and the turn view (days 10–12, ~25%)

- `--watch`: incremental read from a byte offset at a 250 ms poll (`01-` §4.4 — poll, do not
  watch), full redraw, cursor-home.
- The §C12 header: the anchoring request, its age, and the estimated tokens appended since.
- In-flight `tool_use` with no result rendered as such with an elapsed time.
- `--by-turn`: H2, as the audit view, over the data M3 already computes.

**Acceptance.**

- Given a running session, when a tool result lands, then within 1 s the "estimated since"
  figure has grown and the exact anchor line is **unchanged** until the next assistant record.
- Given a running session with a tool call in flight, when the readout renders, then that
  `tool_use` appears with no result and an elapsed time.
- Given any session, when `--by-turn` runs, then each turn shows its exact `usage` delta beside
  the estimated tokens appended in it, and the two columns differ by the per-turn residual.

Days 13–14 are slack, the README section, and the `winnow inspect` deprecation line.

---

## What the first slice deliberately does not do

M1 is a walking skeleton and it will look like one. It prints six rows and a residual. It has
no drill-down at all, so it cannot answer *which* Bash, which is the question the operator will
ask within four seconds of seeing it. It has no prefix node and no retained-reasoning node — so
its `unattributed` row will be the ~40% that `01-` §3.2 measured, and for three days the tool
will be visibly worse than what M3 makes it. It has no live mode, no `--explain`, no audit, and
no colour.

> **"no colour" was overridden by the operator on 2026-09-03**, after the mockup was drawn and
> looked at. The readout now carries colour that means provenance and nothing else, plus a key
> row and a terminal-width layout. What was overridden, why, and what shipped is recorded in
> `07-mockup.md`'s postscript. This paragraph is left as written: it is the record of what was
> decided then, not a description of the code.

That ordering is deliberate and it is ordered by risk retired per hour. M1 proves the two things
that can kill the architecture: that the exact anchor can actually be recovered from `usage`
across compaction and `[1m]` sessions, and that the apportionment sums. If either fails,
everything downstream is worthless, and it fails on day two rather than day nine.

---

## Non-goals

Things a reasonable person would expect and will not get, each with the reason and — where one
exists — the measurement that reopens it.

**1. No "reclaimable space", no "you could have saved X", no "unused" marker.** This is
TreeSize's headline affordance and the reason the analogy was reached for. It is refused twice
over: the transcript records what was sent and never whether the model attended to it (`01-`
§3.4), and removing an early block invalidates the prompt cache for everything after it, so the
saving can be negative in sign — which is why this repository has a `T* = 19·(S/D) − 20`
break-even arithmetic at all. *Reopens:* nothing in this tool. It is `winnow`'s question, on the
proxy, with a counterfactual.

**2. No cross-session anything.** One id in, one picture out. `ccusage`, `session-report` and
`receipts` occupy that ground with a different denominator — dollars per day against tokens per
window (`01-` §6.4). *Reopens:* never; it is a different instrument.

**3. No writes, no pruning, no `--fix`, no cache of parsed sessions beside the transcripts.**
§C1. The tool will be pointed at files the CLI is appending to right now, with no lock. *Reopens:*
never.

**4. No sub-agent tokens in the parent's total.** One block sized by the return; the
sub-agent's own budget shown beside it and never added (§C11). Adding them produces a number
that is not the size of any window that ever existed. *Reopens:* never — but drilling sideways
into a sub-agent's own tree is a legitimate M5.

**5. No "% of window full" by default.** Nothing in a transcript states the context-window size
(`01-` §7 item 9); `72acbacd` reports 512,133 tokens on a nominally 200,000-token model because
it is a `[1m]` session and the flag is recorded nowhere. Available only with an explicit
`--window N`. *Reopens:* a record type that states the window, or the `/context` cross-check
below.

**6. No claim of parity with `/context`.** `01-` §7 item 7 attempted the comparison and was
blocked: `/context` under `-p` is dispatched before any request is assembled, so it reports a
skeleton with every memory file at 0 tokens, and populating it needs a credential this sandbox
binds to `/dev/null`. Until someone with credentials runs the diff, the readout must not say
its categories match `/context`'s. *Reopens:* that diff, and it is the highest-value single
thing anyone could do to this proposal.

**7. No live-session auto-discovery by mtime.** The project-slug transform is lossy and two
sessions sharing a working directory is normal on this machine — sibling agents run
concurrently in the same worktree (`01-` §4.1). The id is required, or comes from a
`SessionStart` hook the operator installed, which is the only certain route. *Reopens:* never
for mtime; a hook is a documented setup step, not a feature.

**8. No tokenizer, no network, no `count_tokens`.** `01-` §2.2: nothing is installable offline
and Anthropic's tokenizer is not public. The constant is a constant and the residual is the
confession. *Reopens:* an `--exact` mode calling `count_tokens` with a credential, which would
settle `01-` §7 item 1 outright and changes the tool's threat model, so it is a separate
decision and not a milestone.

**9. No self-calibration.** The tool can solve for the chars-per-token constant that balances a
session's books (median 2.57, IQR 2.41–2.75) and it will not apply it. §C10: a residual that
cannot be non-zero is not evidence, and a fitted constant silently absorbs any category the
classifier missed. It is printed as a diagnostic and labelled "not applied". *Reopens:* never
while the residual is the tool's only self-check.

**10. No repair or removal of `winnow inspect` in this appetite.** It gets a deprecation line
naming `winnow context` and stating why its `cache_read_input_tokens` is a lifetime sum rather
than a window. Rewriting a shipped command with its own tests does not fit two weeks alongside
M1–M4. *Reopens:* immediately after, and it should be the next thing.

**11. No TUI, no browser page, no served port.** `03-option-b` and `03-option-c`, argued and
priced. *Reopens:* the diary below, not taste — and for C specifically, a failure of
`scratch/thinking_price.py` (see kill criteria), which would bring back a 40% block that wants a
render able to draw a difference in kind.

**12. No image sizing beyond a header read.** JPEG SOF or PNG IHDR out of the first ~3 KB of
decoded base64, priced at `w·h/750`; if the header does not parse, the node is **zero and
labelled**, never `len(data)/4`, which over-reports by 14× (`01-` §2.5). *Reopens:* nothing —
this is the correct behaviour, not a limitation.

---

## Success criteria

Baselines are measured on this container on 2026-09-02 unless the cell says otherwise. The
sample is the 200-file even sweep over `~/.claude/projects` that `scratch/thinking_price.py`
uses: 160–168 uncompacted sessions with ≥5 requests, the range being what two runs hours apart
returned, because this machine is writing transcripts into the corpus it measures. **The first
two rows are therefore paired against a same-day prototype run rather than against a fixed
threshold**, and the third column says so.

| Metric | Baseline today | Target | How it is measured | Checked when |
|---|---|---|---|---|
| Median share of the exact window left `unattributed` | **~40%** with visible material only (39.7% / 45.2% on the two runs of `scratch/thinking_price.py`; `01-` §3.2 measured 42.5%); ~14% with the prefix also priced | **≤5%**, and no worse than a same-day prototype run | `winnow context --audit` over the sweep, one line per session, beside `scratch/thinking_price.py` on the same day | end of M3 |
| Sessions whose residual is within ±15% of their own exact window | **154/168 (91.7%)** and **149/160 (93.1%)** on the two runs, at 2.6 chars/token | **no lower than the same-day prototype's count**, and no regression as the classifier grows | same paired run | end of M3, and re-run at M4 |
| Rendered numbers carrying no provenance label | n/a — no tool exists | **0** | a test that walks the `--json` tree and asserts every node has `exact` / `derived` / `estimated` / `residual` | M1, and it fails the build thereafter |
| Sessions where the tool refuses rather than guesses | n/a | **100%** of the refusable set: no `usage` anchor → no percentages and a non-zero exit; no `--window` → no fullness figure | a fixture set of six degenerate sessions committed to the repo | M1 |
| Over-report on a compacted session | **3.6×** — session `2551cd0c` sums to 416,774 est. tokens against a real final window of 116,030 (`01-` §2.6) | **1.00×** — the reported total equals `usage` exactly | that session as a fixture | M1 |
| Wall clock, largest session in the five-session table (`72acbacd`, 8,067,020 bytes, 1,525 records) | full `json.loads` of every line: **0.02 s**; `import winnow.cli`: **27 ms** | **<300 ms** end to end, cold | `time winnow context 72acbacd --depth 3` | M1, re-checked at M2 |
| **Guardrail** — bytes written under `~/.claude` or `~/.winnow` | 0 | **0** | the command exits 0 with `~/.claude` mounted read-only | M1, every milestone |
| **Guardrail** — reach into pruning policy | `import winnow.cli` pulls **16** winnow modules, 27 ms | `winnow.legacy.guard`, `winnow.legacy.team`, `winnow.proxy`, `winnow.orchestrator_safe` absent from `sys.modules` after the command returns | a test asserting on `sys.modules` | M1, every milestone |
| **Guardrail** — `winnow filter`'s behaviour | unchanged | unchanged: no shared module edited except `cli.py`'s import placement, and the existing suite green | the existing test suite | every milestone |

The last guardrail is weaker than it should be and that is worth saying: this run did not find a
latency benchmark for `winnow filter`, so "the filter did not get slower" is protected only by
the import-set assertion and by not editing shared modules. If a benchmark exists that this run
missed, use it; if it does not, building one is not in this appetite.

## The one criterion that cannot be measured

**Whether the operator does anything differently.** `00-` §6 names it as the third and most
insidious way this dies — *"if nobody would act on it, it is a chart"* — and there is no
offline proxy for it. The transcript records what was sent; it does not record what was
decided.

The weakest honest substitute, and it is a diary rather than a metric: **for the first ten
sessions after M2, one line each — what the readout said, and what was done differently.** If
fewer than three of the ten name an action, the kill criterion below fires. This is a sample of
ten, self-reported, by the person who commissioned the tool, and it is worth roughly what that
sounds like. It is recorded because the alternative is having no signal at all on the criterion
that decides whether the other nine were worth measuring.

## Definition of done

**This list is scoped to whatever slices actually shipped.** M4 can be dropped by either of two
routes above — the day-6 slip rule, or the diary kill criterion — and if it is, `--watch` and
`--by-turn` are struck from the first line rather than owed. Nothing else here is conditional.

- `winnow context <id|path|prefix>` exists with `--depth`, `--json`, `--audit`, `--explain`,
  `--window` — and `--watch` and `--by-turn` *if M4 shipped* — documented in `--help` and in one
  README section that says which modes exist.
- Every rendered number carries a provenance label — `exact`, `derived` or `estimated`, plus the
  reserved `residual` on the single unattributed node (§C2) — enforced by a test that walks
  `--json` rather than by review.
- Committed fixtures: the six degenerate sessions; the compacted session; the `[1m]` session;
  one session with a `<persisted-output>` spill; one with an `Agent` call; one with an image.
- A golden `--json` for one small fixture session, so that a classifier change that silently
  moves tokens between categories fails the build. **This is the only defence against the tool's
  one unfalsifiable error** — misattribution conserves the total, so the residual does not catch
  it (`03-option-a`, *How it fails*).
- Tests: the read-only mount; the `sys.modules` assertion; the compaction reset; the
  `message.id` dedupe against a session where naive summing inflates by 1.7–2.4×.
- `--audit` run over the sweep beside `scratch/thinking_price.py` on the same day, and both
  medians recorded in the repository with the date and the session count, so that the next run
  can tell drift from regression.
- `winnow inspect` carries a deprecation line naming `winnow context` and stating why.
- The existing suite green, and `winnow filter` untouched apart from `cli.py`'s import placement.
- The diary file exists and has its first entry.

## Kill criteria

Decided now, while nobody is attached to it.

**The diary.** Ten sessions after M2 with fewer than three entries naming an action: stop. Do
not build M4. The tool is a chart and the honest thing is to say so on a branch rather than in
six months.

**The residual.** If `--audit`'s median over the sample exceeds **15%**, the apportionment is
not good enough to draw. Fall back to printing the exact anchors — window, compaction
accounting, per-request totals — and abandon the tree. That readout would still be more than
`/context` gives and it would be entirely exact.

**The `/context` diff.** If somebody with credentials runs `01-` §7 item 7 and this tool's
categories disagree with `/context`'s by more than 20 points on any row other than `Messages`,
the classifier is wrong and no amount of rendering fixes it. Fix the classifier or stop.

**The thinking measurement.** `02-constraints.md`'s correction rests on retained reasoning
actually being retained on this model class, which `01-` §7 item 2 lists as unsettled. If a
controlled A/B — same prompt, thinking on and off, watching `cache_read` — shows it is not, then
the ~14% attributed to it is something else, the residual returns to ~14%, and **this
recommendation should be re-run rather than patched**: a 40% invisible block wants a render
that can draw a difference in kind, which is `03-option-c`'s one structural advantage
(`04-comparison.md`, third correction).

**A better source appearing.** If a record type appears that states the context-window size and
the prefix, most of M3 evaporates. Rewrite the tool around it rather than extending this one.

## What this recommendation does not claim

**It does not claim the tool will save money.** It computes no saving and §C13 forbids it from
suggesting one. Every action available to an operator who has seen the composition — read less,
read with `offset`, prune, restart, trim the prefix — was available before, and this only makes
the target visible.

**It does not claim the estimate is good.** The chars-per-token constant is 2.6 with a stated
band of 2.4–3.0, and four independent methods agree on that band without closing it (`01-`
§2.3's three, plus the residual-zeroing 2.57 in `02-constraints.md`). What it claims is
narrower and defensible: the **total** is exact by construction, ~38% of the median window is
**derived** from exact anchors rather than estimated — 64% on the one session worked end to end
in `03-option-a` — and every figure says which it is.

**It does not claim the hierarchy is right.** H1 is chosen because it is the only one that can
hold the prefix, not because there is evidence the operator thinks in provenance. `--by-turn`
exists partly so that the choice is revisable at the cost of a flag rather than a rewrite.

**It does not claim to have beaten `/context`.** It has not been compared to it, because it
cannot be here (`01-` §7 item 7). It drills the row `/context` leaves flat, which is a
structural difference and not a measurement, and until somebody runs the diff that is the whole
of the claim.
