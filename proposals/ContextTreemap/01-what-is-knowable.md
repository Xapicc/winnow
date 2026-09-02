# What is knowable about a context window from outside it

*Measured 2026-09-02 on this container against `~/.claude/projects` — 1,985 transcript files,
400,548 records, ~2.9 GB. Every figure below is either **exact** (lifted from a number the
CLI wrote down) or **estimated** (labelled, with its method and its error). Scripts are in
`scratch/`; each one names the section it feeds. Re-running them will not reproduce these
numbers exactly, because this run is itself writing transcripts into the corpus it measures.*

**Standing caveat on the corpus.** These are one operator's sessions on one machine: almost
all `claude-opus-5` (often the `[1m]` window), heavy Bash and Read use, an MCP server or two,
several custom skills, and a `winnow` guard hook that rewrites some tool results before the
model sees them. A different install will have a different prefix, a different tool mix, and
a different chars-per-token ratio. The *methods* generalise; the *constants* should be
re-measured.

---

## 1. Inventory of a context

### 1.1 What is on disk at all

Nineteen record types, from `scratch/inventory.py` over a 120-file sample (34,467 records).
`type` is the discriminator; `message.content` is present only on `user` and `assistant`.

| record `type` | in sample | what it is | in the window? |
|---|---:|---|---|
| `assistant` | 13,116 | model turn: `text`, `thinking`, `tool_use` blocks | **yes** |
| `user` | 8,312 | human turn **or** a tool-result envelope — the same type covers both | **yes** |
| `attachment` | 6,076 | everything the CLI injects: memory files, skill listing, agent listing, MCP instructions, hook output, environment, model identity | **yes** |
| `system` | 98 | `turn_duration`, `stop_hook_summary`, `compact_boundary`, `local_command`, `informational` | mostly no |
| `last-prompt`, `ai-title`, `mode`, `bridge-session`, `queue-operation`, `agent-setting`, `permission-mode`, `atis-latch`, `file-history-delta`, `file-history-snapshot`, `frame-link`, `agent-name`, `artifact-autoreact-ledger`, `cost-state`, `artifact-comment-monitor` | 6,437 | CLI bookkeeping | **no** |

Bookkeeping is 20% of records and ~7% of bytes and contributes zero tokens. A treemap that
counts records rather than context will draw it, and it should not.

### 1.2 The thing-by-thing answer

Session ids below are real; where a claim needs a specific line I give the session and how to
find the record rather than quoting content. All sessions are under `~/.claude/projects/`.

| kind of thing | present in the transcript? | evidence |
|---|---|---|
| **system prompt** | **absent** | no record of any of 19 types carries it. First-request arithmetic (§3) puts it plus tool definitions at a median 29,716 tokens |
| **tool definitions** | **absent** | same. `deferred_tools_delta` records tool *names* only — 31 names, no schemas: session `005334b4-b8f3-493c-bdc5-961ba9be1fcb`, line 4 |
| **MCP tool schemas** | **absent** | names appear in `deferred_tools_delta`; schemas never do |
| **MCP server instructions** | **present, in full** | `attachment` / `mcp_instructions_delta`, with `addedNames` and full `addedBlocks` prose. 73 in the sample |
| **CLAUDE.md and rule files** | **present, in full** | `attachment` / `nested_memory`, carrying `path`, `type` and the whole file body. Over a 255-file sample: 216 `User` records (`~/.claude/rules/*.md`) and 17 `Project` records — the latter all named `CLAUDE.md`, totalling 626,897 characters of body. *This contradicts ContextControl `00-problem.md:1262`'s "It is not in the transcript"; that test grepped for the literal string `claudeMd`, which is the wrapper name on the wire, not the record shape on disk* |
| **skill listing** | **present, in full** | `attachment` / `skill_listing` — the entire block, ~2,400 est. tokens on a typical session |
| **agent-type listing** | **present, in full** | `attachment` / `agent_listing_delta` |
| **environment block, git status, user email** | **present** | `attachment` / `environment` and `/session_context` |
| **model identity block** | **present** | `attachment` / `model`, with `modelId`, `marketingName`, `knowledgeCutoff` |
| **user turns** | **present, in full** | `user` records whose `message.content` is a bare string, or a block list with no `tool_result` |
| **assistant text** | **present, in full** | `assistant` / `text` blocks |
| **thinking** | **present as a husk; text absent** | see §1.3 |
| **`tool_use` inputs** | **present, in full** | `assistant` / `tool_use`, with `id`, `name`, `input` |
| **`tool_result` outputs** | **present, sometimes truncated** | `user` / `tool_result`. Large ones are replaced by a `<persisted-output>` wrapper — see §1.4 |
| **images** | **present, full base64** | 822 image blocks / 96.3 MB of base64 across 77 sessions. Blocks carry only `source.{type, media_type, data}` — **no dimensions**. Sizing them is §2.5 |
| **sub-agent conversations** | **absent from the parent; present in sibling files** | `<project>/<session-id>/subagents/agent-<id>.jsonl`, 962 of them. §4.5 |
| **sub-agent returns** | **present in the parent** | as the `tool_result` for the parent's `Agent` `tool_use` |
| **hook output** | **present, with the hook's own command line** | `attachment` / `hook_success`, carrying `hookName`, `hookEvent`, `content`, `stdout`, `stderr`, `exitCode` and `command` |
| **`<system-reminder>` blocks** | **partly present** | only the ones the CLI injects *into a tool result*: 37 found in 21 of 204 sampled files, 7,312 chars. The session-opening reminders — agent listing, skills, `claudeMd`, date — are on the wire as separate blocks of the first user message and reach disk as `attachment` records instead, not as reminder text |
| **compaction summaries** | **present, in full** | `user` record with `isCompactSummary: true`; 31,534 est. tokens across 3 summaries in session `2551cd0c-8233-4b3e-9346-0a1396707a63` |
| **compaction accounting** | **present and exact** | `system` / `compact_boundary` with `compactMetadata.{trigger, preTokens, postTokens, cumulativeDroppedTokens, durationMs, preservedSegment, preservedMessages}`. 867 boundaries across 210 files |

### 1.3 Thinking: verified, and both prior claims need adjusting

ContextControl states thinking blocks are "stripped from transcripts" and "retain zero
bytes". The first half is right. The second half is wrong, and the difference matters to a
treemap.

`scratch/thinking_probe.py` over a 204-file sample found **6,871 thinking blocks, of which
6,870 have `thinking: ""`**. Corpus-wide, `rg -l '"thinking":"[^"]'` matches **10 of 1,985
files**, against 1,843 files that contain a thinking block at all. So: the text is gone,
essentially always.

But every block carries `{type, thinking, signature}`, and the signature is a 1.4–2.7 KB
opaque blob. Across the sample the mean thinking block is **2,784 bytes on disk** and
contributes **zero tokens of natural-language context**. On session
`f6ea2591-5ca5-4389-9ac7-60385053510b` the 93 thinking blocks occupy 322,253 bytes of a
2,051,439-byte file — **15.7% of the file for 0% of the visible window**.

Any tool that sizes by bytes will draw thinking as the third-largest thing in the session.
It is not there at all. And what *is* there — the reasoning itself, retained in the window on
this model class — is invisible, and measured in §3.3 at ~670 tokens per block.

The handful of non-empty exceptions are all `claude-haiku-4-5-20251001` (session
`73aa8686-c70a-4e3f-aa5f-71662999c1bf`, three blocks of 402/172/1009 chars). Whether that is
a model-side or a version-side difference is **unsettled** (§7).

### 1.4 The two truncations

**`Read` pages rather than truncates.** An oversized read emits an
`attachment`/`read_truncation_notice` whose banner states the file, the line range shown, the
total, and — usefully — Claude Code's *own* token count for it: `showing lines 1-632 of 778
total (26135 tokens, cap 25000)`. The remaining lines are retrievable with `offset`; nothing
is silently lost.

**Large tool output is spilled to a sidecar.** The `tool_result` block the model sees becomes
a `<persisted-output>` wrapper of ~2.3 KB carrying the path and a 2 KB preview; the full
output goes to `<project>/<session-id>/tool-results/<id>.txt`. There are **565 sidecar files
holding 204,906,775 bytes** across 220 sessions, and 343 transcripts contain the wrapper.

The trap: the *same* record's `toolUseResult.stdout` field carries the full output anyway. On
the example inspected (session `c91dc0a7-6def-495b-ae43-fe4d82d242f3`, a 45,085-byte spill)
the model saw 2,331 characters and the record on disk holds 45,085. **`toolUseResult` is not
context.** It is a local convenience field; the API never sees it. A sub-agent measurement on
three sessions in this repo put `toolUseResult` at 32.6%, 38.2% and 45.6% of file bytes.

---

## 2. Sizing

### 2.1 The three instruments, and which is exact

| instrument | exactness | what it can size |
|---|---|---|
| `message.usage` on an assistant record | **exact** — it is what the API billed | the *whole* window at that request, and the output of that turn. No breakdown |
| `compactMetadata` on a `compact_boundary` | **exact** | tokens before, after, and cumulatively dropped |
| the `read_truncation_notice` banner | **exact** (the CLI's own counter) | one file read, when it was big enough to truncate |
| characters ÷ a calibrated ratio | **estimate, ±**, see §2.3 | every individual block |
| bytes of the JSON line | **wrong** | nothing — it counts scaffolding, `toolUseResult`, and thinking signatures |

**The two traps in `usage`.** First, one API response is written as *several* JSONL lines —
one per content block — each repeating the same `message.id` and the same `usage` object.
Summing per line inflates by 1.7–2.4×. Dedupe on `message.id` (or `message.id + requestId`).
Second, `input_tokens` alone is not the window; it counts only what falls after the last
cache breakpoint. The window is
`input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.

### 2.2 The architecture this implies

There is no tokenizer available here and there cannot be one: no network from the sandbox,
nothing cached (`uv pip install --offline tiktoken` fails; no `tokenizers`, `transformers`,
`anthropic`, or any `*.tiktoken`/`vocab.json` anywhere on the filesystem), and Anthropic's
tokenizer is not public. The `count_tokens` endpoint is exact but needs network and
credentials.

So the honest design is not *estimate everything*. It is:

> Take the total from `usage`, which is exact. Use the character estimate only to
> **apportion** that total across the visible blocks. Draw the unapportionable remainder as
> its own block.

That converts a ±30% absolute sizing error into a much smaller relative error on each slice,
inside a total that is correct by construction — and it makes the floor (§3) a visible
feature rather than a silent omission.

### 2.3 Chars per token, measured three ways

The folkloric 4 characters per token is wrong for this material by about a third. Three
independent methods, none of them using a tokenizer:

**(a) Output side.** For assistant responses whose only content block is `text` and whose
`stop_reason` is `end_turn` — no thinking, no tool call — compare characters emitted against
`usage.output_tokens`. Twelve such responses across 40 files: ratios 2.43 – 2.91, **mean 2.73**.

**(b) Input side, from request-to-request deltas.** Between consecutive API requests with no
compaction between them, the window grows by exactly the tokens of what was appended.
Restricting to spans where one category is >85% of the appended characters and no thinking
block occurred (`scratch/regress_tokens.py` and the dominated-span analysis):

| category | n | p25 | **median** | p75 |
|---|---:|---:|---:|---:|
| `assistant_text` | 20 | 2.57 | **2.76** | 2.92 |
| `attachment` | 27 | 2.47 | **2.65** | 3.07 |
| `tool_use` JSON | 452 | 2.35 | **2.50** | 2.69 |
| `tool_result` | 467 | 2.11 | **2.35** | 2.56 |

The same spans *with* a thinking block present come out systematically denser (1.75 – 2.08),
which is not a tokenisation fact — it is the invisible reasoning inflating the delta. That
gap is what §3.3 turns into a number.

**(c) Claude Code's own counter.** `read_truncation_notice` banners state a token count for a
file. Restricted to the eight cases where the file still exists on this machine *and* its
line count still matches the notice: raw ratios 2.20 – 3.38, median 2.64. Correcting for the
line-number prefix the `Read` tool adds (~3 tokens/line, not in the file's bytes) moves that
to roughly **2.9 – 3.0**.

**Adopted: 2.6 chars/token, with a stated band of 2.4 – 3.0.** Used everywhere below and set
as `CHARS_PER_TOKEN` in `scratch/size_session.py`. §3.2 shows how much the conclusions move
across that band — the answer is: the prefix barely moves, the floor moves a lot.

For contrast, this repo's own estimator (`src/winnow/legacy/tokens.py:131`,
`CHARS_PER_TOKEN_DEFAULT = 3.1`) and the `bytes/4` in `savings.py:97` are both in the wrong
direction, and both are applied to the wrong denominator (file bytes, not payload chars).

### 2.4 What to count for each kind

Not obvious, and getting it wrong is most of the error:

| kind | count | do **not** count |
|---|---|---|
| assistant text | `block.text` | the JSON envelope |
| `tool_use` | `json.dumps(block.input)` + `block.name` | `block.id` |
| `tool_result` | `block.content` if a string; the `text` sub-blocks if a list | `toolUseResult` (§1.4), `is_error`, the id |
| attachment | the payload **strings**, recursively | the JSON keys and structure — the CLI renders them into prose |
| thinking | **zero** | the signature, always (§1.3) |
| image | see §2.5 | the base64 |
| bookkeeping records | zero | everything |

### 2.5 Images

An image block carries `media_type` and base64 `data`, and no dimensions. Base64 length is a
catastrophic proxy: the API prices an image at approximately `width × height / 750` tokens.

Dimensions *are* recoverable without a decoder — base64-decode the first ~3 KB and read the
JPEG SOF or PNG IHDR header. Measured on four images in session
`e268d6c5-a844-44cb-8ce7-290278231f36`:

| media type | base64 chars | dimensions | tokens ≈ w·h/750 | what `bytes/4` would say |
|---|---:|---|---:|---:|
| image/jpeg | 96,032 | 1518 × 784 | **1,586** | 24,008 |
| image/jpeg | 82,868 | 1518 × 784 | **1,586** | 20,717 |
| image/jpeg | 88,396 | 1518 × 784 | **1,586** | 22,099 |
| image/jpeg | 84,764 | 1518 × 784 | **1,586** | 21,191 |

A **14× over-report** if you size by bytes. `w·h/750` is Anthropic's published formula, not
something this run measured; treat the header-reading as measured and the formula as cited.

### 2.6 Five sessions, measured

`scratch/table_five.py`. Sessions chosen at the p05, p25, p50, p85 and p99.5 of the
size distribution of the 928 transcripts over 20 KB, plus one with compaction. Every row is
labelled exact or estimated. Token figures are at 2.6 chars/token.

| | **A** | **B** | **C** | **D** | **E** | **F** |
|---|---|---|---|---|---|---|
| session id (first 8) | 7776e817 | 1c71412f | e698739e | f6ea2591 | 72acbacd | 2551cd0c |
| file size | 72,263 | 406,384 | 822,637 | 2,051,439 | 8,067,020 | 2,796,492 |
| lines on disk | 29 | 125 | 244 | 613 | 1,525 | 630 |
| API requests *(exact)* | 8 | 20 | 66 | 174 | 311 | 164 |
| compaction boundaries *(exact)* | 0 | 0 | 0 | 0 | 0 | 3 |
| **final context, `usage`** *(exact)* | 51,277 | 102,699 | 219,485 | 353,741 | 512,133 | 116,030 |
| peak context, `usage` *(exact)* | 51,277 | 102,699 | 219,485 | 353,741 | 512,133 | 166,927 |
| | | | | | | |
| tool-result *(est)* | 5,191 | 37,587 | 50,903 | 131,708 | 165,798 | 182,765 |
| tool-use *(est)* | 1,059 | 11,634 | 18,085 | 78,559 | 97,107 | 137,162 |
| attachment *(est)* | 3,111 | 10,540 | 6,852 | 17,368 | 40,053 | 59,683 |
| assistant-text *(est)* | 364 | 2,023 | 1,046 | 1,487 | 5,343 | 2,968 |
| user-turn *(est)* | 365 | 175 | 1,249 | 2,195 | 259 | 2,638 |
| compaction-summary *(est)* | — | — | — | — | — | 31,534 |
| system-record *(est)* | — | — | — | — | 1,216 | 24 |
| **transcript total** *(est)* | 10,090 | 61,959 | 78,135 | 231,317 | 309,776 | 416,774 |
| | | | | | | |
| thinking blocks *(exact count)* | 2 | 16 | 28 | 93 | 153 | 101 |
| thinking text on disk, chars *(exact)* | 0 | 0 | 0 | 0 | 0 | 0 |
| thinking signatures, bytes *(exact)* | 3,564 | 43,088 | 158,732 | 205,208 | 291,576 | 279,164 |
| image blocks *(exact count)* | 0 | 0 | 0 | 0 | 35 | 0 |
| | | | | | | |
| **invisible to the file** *(derived)* | 41,187 | 40,740 | 141,350 | 122,424 | 202,357 | — |
| **as share of real context** | 80% | 40% | 64% | 35% | 40% | — |

Read across it:

- **Tool traffic is the session.** `tool-result` + `tool-use` is 62–91% of everything the file
  can see, in every session. The conversation proper — user turns and assistant prose — is
  1–5%. Whatever the treemap's top level is, it has to make tool traffic drillable or it will
  show one enormous block and nothing else.
- **`tool-use` is not a rounding error.** On D and F the model's own tool *inputs* are 34% and
  33% of visible context — as much as a third. Writing a large file costs the window twice:
  once as the `tool_use.input`, once as whatever the tool returns.
- **Attachments grow with the session, not just at the start.** 7.5–14.3%. On F the biggest
  single attachment class is `file` (38,489 est. tokens) — IDE-attached files.
- **Column F is the compaction warning.** Cumulative transcript = 416,774 est. tokens; actual
  final window = 116,030. Summing a compacted transcript from the top over-reports by 3.6×.
  The tool must reset its accumulator at every `compact_boundary` and add the summary.
- **Column A is the prefix warning.** A short session is 80% prefix. The treemap of a young
  session is almost entirely the block it cannot see.
- **Column E is why `usage` matters.** `usage` says the window was 512,133 tokens on a model
  whose default window is 200,000 — this is a 1M-context session. A tool that hardcodes
  200,000 as the denominator will report 256% full.

`tool_result` broken down by tool, same sessions, est. tokens:

| session | top tools by result size |
|---|---|
| C `e698739e` | Bash 42,607 · Read 7,650 · Edit 646 |
| D `f6ea2591` | Read 78,407 · Bash 50,334 · Edit 2,046 · Write 921 |
| E `72acbacd` | Bash 135,899 · TaskOutput 12,692 · `mcp__claude-in-chrome__browser_batch` 6,515 · `…javascript_tool` 5,436 · Read 2,404 |
| F `2551cd0c` | Bash 117,500 · Read 46,670 · WebFetch 13,418 · WebSearch 3,493 |

---

## 3. The floor problem

### 3.1 The prefix, measured directly

The first API request of a session is priced in `usage`, and everything else in it — the
first user turn and its attachments — is in the transcript. Subtract:

> `prefix ≈ ctx(first request) − est_tokens(every transcript line before it)`

`scratch/prefix_floor.py` over 199 sessions sampled evenly across the corpus:

| | p10 | p25 | **median** | p75 | p90 |
|---|---:|---:|---:|---:|---:|
| first-request context *(exact)* | — | 29,610 | 36,818 | 50,643 | — |
| visible before it *(est)* | — | — | 5,364 | — | — |
| **prefix** *(derived)* | 21,520 | 24,717 | **29,716** | 42,950 | 82,689 |

Restricting to the 185 sessions with no compaction moves the median to 29,694 — no change.

**This independently corroborates ContextControl's figure.** They obtained a median of 31,575
(re-validated at 31,373) as the *intercept* of a per-file OLS of context on cumulative bytes.
This run obtained 29,716 by direct subtraction on the first request. Two unrelated methods
agreeing within 6% is about as good as this gets without a proxy.

It is also robust to the estimate. Re-running at 2.2 / 2.6 / 3.0 / 4.0 chars per token gives
prefix medians of 29,791 / 31,055 / 31,887 / 33,919 — a 14% spread across an 80% swing in the
constant, because the visible material before the first request is only ~15% of it.

The p75–p90 tail (42,950 – 82,689) is real and is not noise: it is sessions with more MCP
servers, more skills and more custom agents. **The prefix is not a constant and a tool must
not hardcode one.** This repo's two attempts — `SYSTEM_OVERHEAD_TOKENS = 21_000`
(`legacy/tokens.py:20`, an undocumented guess) and `BASE_PREFIX_TOKENS = 15_903`
(`inspect.py:67`, dead code whose cited source no longer contains the number) — are both low
by a third to a half.

### 3.2 The floor at the end of a session

At the last request `usage` states the window exactly. Sum everything the transcript can see
up to that point and the difference is what a transcript-built treemap cannot draw.
`scratch/floor_decompose.py`, 160–161 uncompacted sessions with ≥5 requests:

| chars/token | prefix (median) | **invisible (median)** | **as share of the real window** | invisible − prefix |
|---:|---:|---:|---:|---:|
| 2.2 | 29,791 | 46,978 | **32.0%** | 7,340 |
| **2.6** | **31,055** | **63,202** | **42.5%** | **22,046** |
| 3.0 | 31,887 | 77,960 | **50.2%** | 30,198 |
| 4.0 | 33,919 | 100,590 | **62.6%** | 51,248 |

At the adopted 2.6, the quartiles of the share are p25 33.4%, median 42.5%, p75 56.2%.

**Stated plainly: a treemap built from a transcript alone under-reports a mature context
window by something between a third and a half, and the single best estimate on this corpus
is 42.5%.** The uncertainty band is genuinely wide — the number is sensitive to exactly the
constant that cannot be measured exactly here — and a tool should say "roughly 40%" rather
than "42.5%".

### 3.3 What the invisible part is made of

Subtracting each session's own measured prefix leaves a median 22,046 tokens still
unaccounted for at 2.6 chars/token. Regressing that remainder on two counts (same script):

```
   669.8 tokens per thinking block
    41.8 tokens per message   (per-message framing + injected reminders + estimate slop)
```

with a median 28 thinking blocks and 185 messages per session — so ~18,750 tokens of retained
reasoning against ~7,700 tokens of framing, which together slightly over-explain the 22,046
remainder. That over-explanation is the honest signature of a 2.6 constant that is a little
too low.

So the floor decomposes, approximately, into:

- **~31,000 tokens** of system prompt and tool definitions — *fixed per session, invisible by
  construction, and the largest single block in a young window.*
- **~670 tokens per thinking block** of retained reasoning — *grows with the session,
  invisible because the API returns thinking with `display: "omitted"` and the CLI writes down
  what it received.*
- **~42 tokens per message** of framing and reminders — *small, unavoidable, and the right
  place to park the residual estimation error.*

The middle line is the one a design run should worry about, because it is the part that
*grows*. On the largest session measured here (E, 153 thinking blocks) it is on the order of
100,000 tokens — invisible, billed, and larger than everything the file can see except tool
results.

**Caveat.** That regression cannot separate "this turn had a thinking block" from "this turn
was hard, so more of everything happened". 670 is an upper-ish estimate of per-block cost and
should be read as *the invisible cost associated with a thinking block*, not a tokenizer
fact.

### 3.4 What a tool can honestly claim

| claim | status |
|---|---|
| "this window is 219,485 tokens" | **exact**, from `usage` |
| "it grew from 98,453 at the first request" | **exact** |
| "compaction dropped 301,977 tokens" | **exact**, from `compactMetadata` |
| "Bash results are 42,607 tokens of it" | **estimate**, ±20% relative |
| "Bash results are 19% of the window" | **estimate**, and only if the denominator includes the invisible part |
| "the prefix is 98,453 tokens" | **derived**, robust, ±10% |
| "this session retained 100,000 tokens of thinking" | **weak estimate**, model-dependent, flag it |
| "you could save X by not re-reading `orchestrator.ts`" | **not knowable** — the transcript records what was sent, never whether the model attended to it |

---

## 4. Live mode

Everything in this section is observation, not inference. The instrument is
`scratch/watch_partial.py`; the subject is this run's own session,
`91ee38bd-61ac-4b5d-af9a-3c01029fe69b` in project
`-workspace--uf-worktrees-winnow-f1c01ae726fd-1`, watched while it and nine sub-agents wrote.

### 4.1 Finding the session that is running now

Three routes, in order of how much they cost and how much they can be trusted:

1. **The mtime of the newest `*.jsonl` in the project directory.** The project slug is the
   working directory with every non-alphanumeric character replaced by `-`
   (`/workspace/.uf-worktrees/winnow-f1c01ae726fd-1` →
   `-workspace--uf-worktrees-winnow-f1c01ae726fd-1`). Verified: this run's session file's
   mtime was 10 seconds old when checked. **Cheap, and wrong whenever two sessions share a
   directory** — which on this machine is normal, since sibling agents run concurrently in the
   same worktree.
2. **A `SessionStart` hook.** Claude Code hands a hook `session_id` and `transcript_path` on
   stdin. This is the only route that is *certain*, and it is what `winnow` uses
   (`src/winnow/legacy/session.py:627 record_active_transcript`,
   `orchestrator_safe.py:1015 resolve_session_path`). It requires the operator to install a
   hook before the session starts.
3. **The harness's own scratch directory.** `$TMPDIR/<project-slug>/<session-id>/tasks/`
   exists for a live session; the session id is a path component. Observed, undocumented, and
   should be treated as an implementation detail.

The slug transform is **lossy**: `slug.replace("-", "/")` cannot invert a path that itself
contains a hyphen. Going directory → slug is safe; slug → directory is not.

### 4.2 Does a turn reach the file while the session is running, and how fast

Yes, and quickly. 59,100 polls at a 2 ms interval over 200 seconds across 38 files, 438 new
records observed:

```
visibility lag vs the record's own timestamp:
  min 3 ms   median 102 ms   p90 111 ms   max 21,232 ms
  assistant  n=249  median 104 ms
  user       n=161  median  87 ms
  attachment n= 26  median  91 ms
```

A record is readable about a tenth of a second after the CLI stamps it. The 21-second
outlier is real and unexplained — probably a record stamped at the start of a long operation
and flushed at its end — so a live reader must not assume records arrive in timestamp order
within a window of tens of seconds.

Importantly, records land **as they happen**, not at end of turn: the assistant's `tool_use`
appears before the tool has run, and the `tool_result` appears when it returns. A live
treemap therefore sees a turn assemble itself, and will show a `tool_use` with no result for
as long as the tool takes.

### 4.3 Partially-written lines

**Not observed once.** Zero torn tails in 59,100 polls at 2 ms across 38 concurrently-written
files. And corpus-wide, `json.loads` on every line of all **1,985 files / 400,548 records**
gives **zero unparseable lines**, and **zero files not ending in a newline**.

That is strong evidence that each record is written with a single append and that the writes
are not interleaved. It is *not* proof: a line can exceed the atomic-append size, this run
never saw a 600 KB record land, and this repo carries a `repair_torn_trailing_line` function
which suggests somebody has seen one. So:

> A reader must still buffer an incomplete trailing fragment and not advance its offset past
> it — but it should treat a torn line as a rarity to be tolerated, not as the normal case to
> be designed around.

Two real parsing hazards *were* found, both already handled in this repo and both worth
inheriting: split on `\n` and never `str.splitlines()`, because U+2028/U+2029/U+0085 are legal
unescaped inside JSON strings (`legacy/session.py:825`); and read with
`errors="surrogateescape"`, because a JSON-escaped lone surrogate from a sliced emoji will
otherwise crash the byte count.

### 4.4 Watch or poll

**Poll.** The evidence: the only signal a watcher can give is "this file grew", which is
exactly what a `stat` gives; the read is a seek-to-offset on an append-only file, so it is
cheap; and a 2 ms poll across 38 files cost 3.4 ms per full sweep on this machine — 59,100
sweeps in 200 seconds without noticeable load. Against a ~100 ms write lag, a poll interval
anywhere in 100–500 ms is indistinguishable from instant, and a treemap does not want to
redraw faster than that anyway.

`inotify`/`kqueue` buys nothing here and costs a per-platform code path, a descriptor per
file, and correct handling of the delete/rename case (this repo's `legacy/watcher.py:23`
already degrades to polling on `DELETE`/`RENAME` for exactly that reason). Use it only if the
tool must also watch a whole project directory for *new* sessions appearing.

### 4.5 Sub-agents

Sub-agent conversations are **entirely separate files**: `isSidechain` is present on parent
records and is `false`. The layout is

```
<project>/<parent-session-id>/subagents/agent-<agent-id>.jsonl
<project>/<parent-session-id>/subagents/agent-<agent-id>.meta.json
```

962 such files on this machine under 115 session directories. The `.meta.json` is the join
key and is small and complete:

```json
{"agentType":"general-purpose","description":"…","toolUseId":"toolu_01Qrk…","spawnDepth":1}
{"agentType":"Explore","description":"…","toolUseId":"toolu_01PB9…",
 "parentAgentId":"a181d10a5b11ee","spawnDepth":2}
```

`toolUseId` joins to the `id` of the parent's `Agent` `tool_use` block; `parentAgentId` and
`spawnDepth` give the tree. Verified on this run's own session: 9 sub-agents, 3 at depth 1
(spawned by the parent) and 6 at depth 2 (spawned by those), totalling 3.8 MB against the
parent's 0.4 MB.

**Do they belong in the parent's picture?** Sharply: **no, and yes at one level.**

- A sub-agent's conversation is *not in the parent's window*. It is a separate context. Its
  bytes are not the parent's bytes. Drawing them inside the parent's treemap is simply wrong.
- What *is* in the parent's window is the sub-agent's **return** — the `tool_result` for that
  `Agent` call — and that is often one of the largest single blocks in the parent, because a
  sub-agent that read forty files reports back in prose.
- So: one block in the parent, sized by the return, **drillable sideways** into the
  sub-agent's own treemap. The two totals are separate budgets that happen to be linked by
  one id, and the tool should render them that way. This is also where the operator's real
  question lives — "the sub-agent spent 230,000 tokens and gave me back 4,000; was that a
  good trade?" — and both halves of that trade are on disk.

### 4.6 Compaction

Well recorded and exact. **867 boundaries across 210 files.** A boundary is a `system` record
with `subtype: "compact_boundary"`, carrying:

```json
{"trigger":"auto","preTokens":168845,"postTokens":12329,
 "cumulativeDroppedTokens":156516,"durationMs":161198,
 "preservedSegment":{…},"preservedMessages":{…}}
```

followed by a `user` record with `isCompactSummary: true` holding the summary in full.
Observed: `trigger` is `auto` or `manual`; auto fires around 168,000 on the 200 K sessions
here and manual at 300,000+; the summary lands around 6,800–17,400 tokens.

Consequences for the tool, in order of importance:

1. **Reset the accumulator at every boundary.** Session F above sums to 416,774 est. tokens
   cumulatively and its real final window is 116,030.
2. `cumulativeDroppedTokens` is exact and is the honest way to show "what this session has
   already thrown away" — a thing `/context` cannot show at all.
3. The pre-compaction composition is *still in the file*. A tool can show the operator what
   compaction ate, which is a genuinely new capability, not a re-skin of `/context`.

### 4.7 `--resume`

`--resume` **appends to the same file**. Verified: across 1,020 main-session transcripts,
**zero** carry a `sessionId` different from their own filename, and none carries more than
one. There is no forked-and-copied case in this corpus.

There is **no record type that marks a resume.** Two candidate signals were tested:

- *Time gaps.* 88 of 340 sampled files contain a gap over five minutes (median gap 12 min,
  max 0.9 days). Necessary, nowhere near sufficient — it also fires on lunch.
- *Re-injected session-start attachments.* Tested and **refuted**: 334 of 340 files contain
  fewer than two `skill_listing` records, and where a repeat exists the gap before it is
  0 seconds. Session-start attachments are not re-emitted on resume.

What *does* work is the cache signature in `usage`. When a session resumes after the prompt
cache has expired, the next request re-writes the whole prefix instead of reading it:

| session | gap (s) | prev `cache_read` | `cache_read` | `cache_creation` | total ctx |
|---|---:|---:|---:|---:|---:|
| 16933438 | 8,572 | 131,683 | 0 | 137,557 | 137,559 |
| 2ccc88c9 | 11,460 | 265,720 | 0 | 270,402 | 270,404 |
| 53d9b67b | 6,341 | 482,779 | 0 | 483,667 | 483,669 |
| 62086ee2 | 81,996 | 124,857 | 0 | 129,187 | 129,189 |

60 such events across 340 sampled files. The rule that isolates them — `cache_read` collapses
to under a quarter of the previous request's while the total window holds above 70% — also
fires once on a same-second cache-breakpoint shuffle (`3daf6352`, gap 5 s, read 27,866), so it
needs the time gap as a second condition. **This is a derived signal, not a recorded fact,
and should be labelled as such in any UI.**

---

## 5. Hierarchy

TreeSize works because a filesystem is *one* tree and everyone already knows what it means. A
context is a flat sequence of blocks with several equally valid groupings over it, and
picking one is this proposal's central design decision. Three candidates, with what each is
good and bad at.

### H1 — By provenance: *who put this here*

```
window
├── prefix (not in the file)            ~31,000
│   ├── system prompt                        ─ not separable from the file
│   └── tool definitions                     ─ not separable from the file
├── standing configuration                    est. from attachments
│   ├── memory files → per file (nested_memory carries the path)
│   ├── skills listing
│   ├── agent listing
│   └── MCP instructions → per server
├── conversation
│   ├── user turns
│   └── assistant text
├── tool traffic
│   ├── Bash → per command head
│   ├── Read → per file path
│   ├── Agent → per sub-agent (drill sideways, §4.5)
│   └── mcp__* → per server → per tool
├── retained reasoning (not in the file)      ~670 × blocks
└── compaction summaries
```

**Answers well:** "what is my standing cost before I type anything", "which tool is eating
the window", "is this a configuration problem or a working-style problem". Maps almost
exactly onto `/context`'s eleven categories at the top level, which is an argument for it —
the operator already knows the vocabulary — and then keeps going where `/context` stops.

**Answers badly:** anything about *time*. It cannot show that the whole window was fine until
turn 40. It also puts the two blocks the tool can least defend — prefix and retained
reasoning — at the top level, which is honest but visually dominant on short sessions
(session A: 80% of the window).

**Recommended as the default.** It is the only one of the three whose top level is a set of
things the operator can actually change.

### H2 — By chronology: *when this arrived*

```
window
├── turn 1..N  (or: request 1..N, or: cycle 1..N between user prompts)
│   ├── user turn
│   ├── assistant text / tool calls
│   └── tool results
```

**Answers well:** "when did this go wrong", "what did turn 40 cost", "show me the turn that
tripled the window". It is also the only hierarchy where the *exact* `usage` numbers slot in
natively — every turn has its own priced request, so the whole tree can be built from exact
data with the estimate used only inside a turn.

**Answers badly:** the operator's actual question. Nobody wants to delete "turn 40"; they
want to delete "that file I read four times". Chronology also degrades as sessions get long —
311 requests is 311 top-level nodes, which is a bar chart, not a treemap.

**Best use: not the tree, the second view.** A per-turn growth strip beside the treemap,
where clicking a spike filters the treemap. Gregg's note on flame graphs applies exactly:
*"dropping the time axis is what makes the visualisation scale."*

### H3 — By artefact: *what real-world thing is this about*

```
window
├── src/lib/orchestrator.ts     30,528 chars  ← read 5×, edited 2×
├── src/lib/db.ts               29,106 chars  ← read 3×
├── app/page.tsx                22,046 chars  ← read 1×
├── (bash) sed …                23,615 chars
├── (bash) grep …               18,349 chars
└── …
```

Measured on session `f6ea2591`: 37 distinct file paths, 211,557 characters of `Read`/`Edit`
output, of which **34% came from paths touched more than once**.

**Answers well:** the single most actionable question there is — "which file is in my window
more than once, and do I need any of them". This is where the money is: VibeHub's independent
census on this machine put **44.3% of read spend on re-reading unchanged content**.

**Answers badly:** everything that is not a file. Bash output has to be bucketed by command
head, which is crude; MCP results, web fetches and sub-agent returns have no natural artefact
at all and end up in an "other" bin that is often the largest node. It also cannot express the
prefix, which is not about any artefact.

**Best use: the second level under H1's `tool traffic`, not the root.**

### Where the analogy breaks

Worth naming, because it is what will make this hard:

- **A file has one size; a block has three.** Bytes on disk, characters of payload, tokens in
  the window — and for thinking blocks and `<persisted-output>` wrappers these differ by
  orders of magnitude in *opposite directions*. A treemap has one area per node. The tool must
  pick tokens and say so.
- **A filesystem has no invisible directories.** This context does, and they are ~40% of it.
  The single most important rendering decision is whether the invisible part is drawn.
- **Deletion is not free and is not local.** Removing a block from a filesystem frees its
  bytes. Removing a block from a context invalidates the prompt cache for everything after
  it, so the "saving" from deleting an early block can be negative. `winnow`'s whole
  `T* = 19·(S/D) − 20` break-even arithmetic exists because of this. A treemap that shows
  "reclaimable space" the way TreeSize does would be lying.
- **The tree changes shape over time and the file only records the last shape.** After a
  compaction, most of what the file contains is no longer in the window. TreeSize scans a
  filesystem as it is; this tool reconstructs a window from a log of how it got there.
- **Ordering is load-bearing.** In a filesystem, moving a file between directories changes
  nothing about its cost. In a context, position relative to a cache breakpoint changes
  everything about it. A treemap discards order by construction.

---

## 6. What already exists

### 6.1 In this repository

Fair summary: there is a good, importable transcript-reading substrate of roughly 1,200 lines
here, wrapped in ~22,000 lines of pruning policy that a treemap wants none of. Nothing here
answers the composition question, and the one component that could — the prefix readout — is
not fed by transcripts and is currently unreachable from the CLI.

| module / symbol | what it gives a treemap | verdict |
|---|---|---|
| `legacy/session.py:722–1037` — `_parse_one_line`, `_split_physical_lines`, `load_messages`, `load_messages_incremental` | tolerant JSONL parsing with the U+2028 and surrogate hazards already handled; byte-offset incremental reads with inode/shrink/mtime invalidation | **reusable as a library** — the single most valuable thing in the tree |
| `legacy/session.py:275 cwd_to_project_slug`, `:381 find_current_session` | the slug transform, and a five-strategy live-session search in priority order | **needs extracting** — `find_current_session` shells out to `ps` and `lsof` and reads a winnow-owned JSON store in `~/.claude`; the *ordering* is the reusable part |
| `legacy/watcher.py:23 JsonlWatcher` | kqueue on BSD, 200 ms `os.stat` poll elsewhere, degrades to poll on rename | **reusable as a library**, 141 lines, stdlib only — but it signals *size deltas*, not content, so §4.4's poll is a fair substitute |
| `legacy/diagnosis.py:13 diagnose_session` | per-record-type counts and bytes, top-10 largest records, thinking vs signature bytes, cache hit rate | **reusable as a library** — 99 lines, pure. The closest existing thing to a proto-treemap, and the natural starting point |
| `legacy/tokens.py:297 extract_usage_tokens`, `:474 quick_token_estimate` | the exact window total from the last main-chain assistant record; progressive tail read for large files | **reusable**, with a caveat: they return a *total*, and the module's `estimate_session_tokens` silently switches between exact and heuristic depending on whether a `usage` block was found. Do not inherit that contract |
| `legacy/tokens.py:131` `CHARS_PER_TOKEN_DEFAULT = 3.1`, `:20 SYSTEM_OVERHEAD_TOKENS = 21_000` | — | **do not reuse.** §2.3 measures 2.6; §3.1 measures the prefix at ~30,000, not 21,000 |
| `legacy/helpers.py` — `msg_bytes`, `get_msg_type`, `get_content_blocks`, `get_dict_blocks`, `text_of` | the whole record/block accessor surface | **needs extracting** — ~120 useful lines inside 1,011, the rest is winnow's protect-pattern machinery |
| `winnow/inspect.py:330 inspect_session` → `Report` | a one-pass walk classifying every content block, pairing `tool_use`↔`tool_result` by id, with a per-line byte map | **reusable as a library** (verified importable, stdlib only, no `~/.claude` touch at import) — **but its denominator is file bytes, its `Usage` sums every assistant record into a lifetime total, and it does nothing with the compaction boundaries it records** |
| `winnow/report.py:47 resolve_session` | id / path / unambiguous-prefix → `Path`, raising rather than exiting | **reusable as a library** |
| `winnow/rules.py` — `result_size`, `content_digest`, `input_size`, `read_range`, `bash_head` | measurement primitives, incl. Bash command-head normalisation (H3's second level) | **needs extracting** — ~120 lines sitting above 400 lines of pruning policy |
| `winnow/filter.py:728 prefix_facts`, `:768 prefix_changes`, `proxy.py:167 PrefixWatch` | **the only thing on this machine that can size the prefix exactly**: `system_bytes`, `tools_bytes`, per-tool definition bytes, cache breakpoint positions | **reusable as a library — but it takes a Messages API request body, not a transcript.** It is a pure function of a dict; it cannot be pointed at a `.jsonl` |
| `winnow/savings.py:357 read_session` | de-dupes turns on `requestId` — the correctness idea §2.1 depends on | **entangled** (it is a cost model), but read it |
| everything else — `plan`, `fork`, `recover`, the rule engine, the guard daemon, `team.py`, the strategies, `~/.winnow` stores | — | **entangled** |

Two things verified by running them rather than reading them:

- `winnow inspect <session>` works and prints byte share by content class and by pruning
  rule. On session `e698739e` it reports `message content 181.0 KB` and
  `cache_read_input_tokens 18,378,780` — for a session whose actual window at the last
  request was 219,485 tokens. The 18.4 M is every assistant record's `cache_read` summed over
  the session's life; it is a real number and it is not the window.
- **`winnow savings` is broken on `main`**: `AttributeError: 'Namespace' object has no
  attribute 'filter_ledger'` (`cli.py:609` passes a flag `add_savings_subparser` never
  registers). Since `savings` is the only command that renders the prefix readout
  (`report.py:439–477`), **the prefix readout is currently unreachable from the CLI.**

The most valuable thing in this repo is not code. Nearly every guard in `legacy/` carries a
dated postmortem — the U+2028 `splitlines` trap, the surrogateescape round-trip, the forged
sentinel-key defence, "the f464a40c wrong-session incident". Those comments record which JSONL
malformations actually occur in production. Read them before writing a new parser.

### 6.2 Elsewhere on this machine

- **`/workspace/VibeHub` `research/census/token_spend.py`** — the strongest non-winnow prior
  art. "Where do an agent's tokens actually go?": pairs `tool_use`↔`tool_result`, buckets
  spend by question type, and distinguishes first-read from re-read-same-session from
  re-read-earlier-session. Measured 23.6% of read spend is a first read, 44.3% is re-reading
  unchanged content, over 22 sessions. ASCII tables; no visualisation; a research one-off.
  **The closest anyone here has come to H3.**
- **`/workspace/WinnowWeb` `components/demos/CompositionDemo.tsx`** — a two-bar stacked split
  (`tool_result + tool_use` = 91.6% vs 8.4% everything else) over 563 transcripts.
  `RecordsPerTurnDemo.tsx` documents the 1.7–2.4× double-counting trap. Marketing figures, not
  an instrument.
- **`/workspace/UsageFoundry/proposals/ContextControl/`** — 22 files. `17-recommendation.md`
  recommends building `04-option-see-it.md`, which is a per-cycle *cost* table plus one
  boolean, not a composition. The byte-level composition figures in its `00-problem.md` exist
  only as ad-hoc `node -e` scripts and ship in nothing.
- **`/workspace/gh-layer10` `eval/harness/usage.py`** — regexes all four token classes out of
  raw transcript bytes and **does not dedupe on `requestId`**. It has exactly the bug §2.1
  warns about, which is a useful demonstration that the warning is needed.
- **Plugins.** 291 in the official marketplace; three touch this territory
  (`session-report`, `receipts`, `dash0`) and all three are cross-session cost, not
  single-session composition.
- **The knowledge vault** (`/workspace2`, 1,227 notes) has the substrate researched to death
  and the visualisation untouched: `treemap`, `TreeSize`, `sunburst` and `WinDirStat` all
  return zero hits. `3 Resources/Questions/What Does a Claude Code Session Spend on Standing
  Configuration.md` states this proposal's thesis as an open question at `confidence: low`,
  and its growth step 1 is literally *"Run `/context` across a spread of sessions and record
  the breakdown."*

### 6.3 In the wild

Assessed from training knowledge only — **this sandbox has no network and none of this could
be checked.** Labelled accordingly.

- **`ccusage`** — reads the same `~/.claude/projects/**/*.jsonl`, reports tokens and dollars
  by day / month / session / 5-hour block with a live burn-rate mode. *Cross-session cost. Its
  per-session view is a total, not a decomposition.* (High confidence.)
- **Claude Code's OTel export** — emits `claude_code.token.usage` with a `type` attribute of
  input / output / cacheRead / cacheCreation. *That is a cache-class split, not a context
  category split*, and every dashboard built on it inherits the limitation. (High confidence.)
- **Claude Code Usage Monitor, claude-code-templates' analytics dashboard** — quota and
  session-level totals. (Medium confidence.)
- **`claude-code-log` and similar transcript→HTML viewers** — render the conversation; do not
  price or bucket it. (Medium confidence.)
- **Statusline projects** (`ccstatusline`, `CCometixLine`, `claude-powerline`) — consume the
  statusline JSON, which carries one scalar, so they are structurally incapable of showing
  composition. (High confidence — the contract is in the binary on this machine.)
- **A hierarchical, drillable single-window context visualiser: none known.** Knowledge cutoff
  is May 2026 and something may have shipped since. This is a *have not found one*, not a
  *there is not one*.

---

## 7. Unsettled

Things this run could not close. This list is the point of the exercise; a later run should
treat each as a task rather than a caveat.

1. **The true chars-per-token constant.** Three methods agree on 2.4–3.0 and that band is wide
   enough to move the headline floor figure from 32% to 50%. Settling it needs either a
   network `count_tokens` call or a shipped tokenizer. **This is the highest-value open
   question**, because every share in every table depends on it.
2. **Whether retained thinking is really ~670 tokens per block.** The regression cannot
   separate a thinking block's cost from the cost of the hard turn that produced it, and
   retention is documented to be model-dependent (this corpus is almost all `claude-opus-5`).
   A single controlled A/B — same prompt, thinking on and off, watch `cache_read` — would
   settle it and was not run here.
3. **Why ten files have non-empty thinking text.** All are `claude-haiku-4-5`, but other Haiku
   sessions in the same sample have empty blocks. Model-side, version-side, or setting-side is
   not established.
4. **How the guard hook contaminates the corpus.** 182 of 1,985 transcripts contain a
   `winnow: … removed` marker, meaning the recorded tool result is the *rewritten* one. It is
   not established whether the transcript ever records the original, nor whether the same is
   true for any `PostToolUse` hook. A treemap on a hooked install may be measuring
   post-hook context and calling it the conversation — which is arguably correct, but it
   should be said out loud.
5. **Whether a torn line ever actually occurs.** Zero in 400,548 records and zero in 59,100
   live polls. This repo's `repair_torn_trailing_line` suggests otherwise. Unresolved; the
   reader should tolerate one regardless.
6. **The 21-second visibility-lag outlier.** One record of 438 appeared 21 seconds after its
   own timestamp. Cause unknown. It bounds how much a live reader can trust timestamp
   ordering, and nothing here establishes the true bound.
7. **Whether `/context`'s numbers and this method's numbers agree.** `/context` computes the
   composition exactly, including the prefix. Running `claude -p "/context"` in a session and
   diffing its markdown export against a transcript-derived treemap of the same session is the
   single best validation available, it needs no network, and this run did not do it. **A
   later run should do this first.**
8. **Sub-agent return sizing.** The parent's `tool_result` for an `Agent` call is documented
   to carry a `<usage>subagent_tokens: N tool_uses: N duration_ms: N</usage>` tag. This run
   searched its own live session for it and found none — background agents appear to deliver
   through a different path. Whether foreground `Agent` returns carry it is unverified, and
   if they do it is a free exact number.
9. **The `1M` window denominator.** Session E reported a 512,133-token window. Nothing in the
   transcript states the context-window size; it has to come from the model id plus a beta
   flag that is not recorded. A tool that renders "% full" needs this and cannot get it from
   the file.
10. **Whether images are re-sent every turn.** 96 MB of base64 sits in 77 sessions. Whether an
    image stays in the window for the rest of the session (and is therefore worth ~1,600
    tokens per turn, not once) was not tested.

---

## 8. Reproducing this

```
scratch/inventory.py [n]          §1.1  record types, block types, attachment types
scratch/thinking_probe.py [n]     §1.3  thinking block keysets and text lengths
scratch/calibrate.py [n]          §2.3  chars/token, output side and input side
scratch/regress_tokens.py [n]     §2.3  per-category OLS against usage deltas
scratch/size_session.py <file>    §2.6  one session's composition
scratch/table_five.py             §2.6  the five-session table, verbatim
scratch/prefix_floor.py [n]       §3.1  prefix distribution, floor at the last request
scratch/floor_decompose.py [n]    §3.2  floor vs chars/token; thinking and framing regression
scratch/watch_partial.py <dir> <s> [ms]  §4.2–4.3  live lag and torn-tail observation
```

`[n]` samples evenly across the corpus. All are stdlib-only Python 3.11 and read
`~/.claude/projects` read-only.
