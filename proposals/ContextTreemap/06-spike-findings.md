# The spike, and what looking at it changed

*Spike run, 2026-09-02, same branch. `spike/context_tree.py` renders
`05-recommendation.md`'s chosen hierarchy over a finished transcript. This file carries the
real output for seven sessions and the verdict. It does not amend `00-` through `05-`; where
it contradicts them it says so here. The spike is disposable and its header says so.*

---

## Verdict

**Build it — and build less of it than `05-recommendation.md` says, because the level that paid
is not the level it calls "the reason the tool exists".**

Seven sessions, chosen to differ. Three produced a fact the operator could not have got from
the session in under a minute; four produced a picture they would have guessed. Every one of
the three came from **level one or level two** of the tree. Level three — H3, per-artefact,
the drill-down `05-` §M2 calls the point of the whole thing — produced **nothing** on any of
the seven that level two had not already said. `$ cd ×87` at 7.9% of a window is not a
finding, it is a `bash_head` artefact; 48 sub-agent rows at 0.1% each are not a finding, they
are a list. And on the one session `05-` names an acceptance number for, the third level does
not merely fail to add — **it halves the number**, reporting 16.8% repeated material where the
measurement it is supposed to reproduce says 33.2%.

So the recommendation stands with three amendments, all of them about where the work goes:

1. **Demote the third level, and re-key it before shipping it.** As specified it is
   tool-then-artefact, which is what halves the number above; it has to be artefact-then-tool.
   Either way it is a `--depth 3` opt-in rather than the headline, and the days M2 was going to
   spend on the drill go to the classifier — where the spike found five faults in seven
   sessions, one of which silently misfiled half a window.
2. **Add the block `05-` has no node for.** 17 of 164 sampled sessions shed context — median
   **36,714 tokens** — with **no compaction boundary and no record of what left**. On one of the
   seven this was 78,167 tokens, a third of the final window, and it moved that session's
   residual to **−25.6%**. §C6 resets at compaction; nothing resets at this. It is the new grey
   block and it belongs above the tree, in exact tokens, with the cause where the file names
   one.
3. **Rename the ambition.** This is not a treemap. It is a five-row receipt with a drill on one
   row and three exact facts above it. `03-option-a` already argued "the operator's question is
   a ranking question, and a ranking is a list"; the spike agrees with that harder than
   `03-option-a` did, and against `04-comparison.md`'s two-point win for the TUI, which was
   scored on a drill-down that did not pay.

And the finding that carries the verdict on its own, because it recurred on two independent
sessions and it is a configuration change worth a quarter of a million tokens:

> **A single auto-invoked skill body was 54.4% and 53.0% of two half-million-token windows.**
> `Skill results → claude-api ×2`. It reaches the window as a `user`/`text` block, so `/context`
> folds it into `Messages` and the transcript makes it look like something the operator typed.
> Nothing on this machine shows it. The spike shows it as the largest row.

The counter-evidence, stated as plainly: **four of seven readouts told the operator nothing
they did not know**, and `05-`'s own kill criterion is three actions in ten sessions. This
sample gives two in seven. That is *near* the line, not clear of it.

---

## What was built

`spike/context_tree.py`, 815 lines, one file, no tests, no packaging, not on the `winnow` CLI.
Ended sessions only. It honours §C1–§C13 where they bite: the total is the exact `usage` window
and the parts are apportioned inside it (§C3), the accumulator resets at the last compaction
boundary (§C6), responses are deduped on `message.id` (§C8), the closed exclusion list is
applied (§C4), images are priced from their decoded header and never from base64 (§C5),
`<persisted-output>` is sized at the preview and labelled a pointer (§C9), a sub-agent's own
window is printed beside its return and never added to it (§C11), the solved chars-per-token
constant is printed with the words *NOT APPLIED* (§C10), and no fullness figure is printed at
all (§C7).

Everything the transcript cannot see is a node. The two that cannot even be sized — `system
prompt` and `tool definitions` — render as `unsized — unknown` with a reason, never omitted and
never folded into a neighbour.

It writes nothing. Grepped: the only file access in the program is `load_messages` and one
`Path.read_text` for sub-agent metadata, both read-only.

**Wall clock, cold, including interpreter start:** 32 ms on the smallest session, **64 ms on
`72acbacd`** (8,067,020 bytes, 1,525 records, 311 requests, and 35 images decoded).
`05-`'s <300 ms target is not in danger.

### Friction reusing `src/winnow`

Recorded rather than fixed, per the brief. Nothing under `src/` was touched.

| what | verdict |
|---|---|
| `winnow.report.resolve_session` | **Fits exactly.** Takes an id, a path or an unambiguous prefix, raises `LookupError` rather than exiting. Used verbatim. |
| `winnow.legacy.session.load_messages` | **Fits.** The tolerant reader with `surrogateescape` and the `\n` split. Returns `list[tuple[int, dict, int]]`, so every call site is `[r for _, r, _ in load_messages(p)]` — three extra tokens, not a problem. |
| `winnow.rules.bash_head` | **Fits the signature, wrong for this job.** See "where the hierarchy fought the data", item 3. |
| the import path | **Real friction.** `winnow` is only importable from the repo's `.venv`; under a bare `python3` it is not on the path. The spike inserts `src/` on `sys.path` itself — three lines at the top of the file, marked as friction. |
| the guardrail in `05-` | **Holds today, with no change to `cli.py`.** `import winnow.report` pulls 11 winnow modules in 27 ms: `filter`, `inspect`, `savings`, `trial`, `rules`, `legacy.{helpers,session,types}`. None of `legacy.guard`, `legacy.team`, `proxy`, `orchestrator_safe`. The eager-import fix at `cli.py:23`/`:25` is only needed if the command is reached through `winnow.cli`. |

### Cross-checks against numbers this run did not produce

The spike reproduces `03-option-a`'s worked readout for `e698739e` to the token — 219,485
exact; prefix 93,900; tool traffic 68,992 with Bash 42,609, `tool_use` inputs 18,087, Read
7,650, Edit 646; standing configuration 6,852; conversation 2,293; residual 891–892 — and it
hits three of `05-` §M1's acceptance criteria without being written against them:

- `2551cd0c` → **116,030**, not 416,774, with **444,326** cumulative dropped printed as `exact`.
- `72acbacd` → **512,133** and **no** "% full" figure.
- Every rendered number carries `exact` / `derived` / `est` / `residual` / `unknown`.

**It passes one of `05-` §M2's two acceptance criteria and fails the other, and that is the
most useful thing it did — because the two contradict each other.**

It passes the second exactly: on `e698739e` at `--depth 3` the result-bearing tools beneath
`tool traffic` are Bash, Read, Edit in that order at **42,609 / 7,650 / 646**, with `tool_use`
inputs a sibling at **18,087**, not folded in.

It fails the first: `f6ea2591` should show "**37** distinct path nodes … within 2 points of
**34%**". The tree reports **32 nodes and 16.8%**. The arithmetic is not wrong; the criterion is
un-meetable by the shape the same section mandates. §M2's prose says *"Under `Read` and `Edit`,
nodes keyed by path"* — one node set per tool. Its acceptance says *"`Read` and `Edit` together
carry 37 distinct path nodes"* — one node set across both. Those are different trees, and only
building it showed that. Pooling by path outside the tree reproduces the original: **29 distinct
paths, 209,163 characters, repeats 33.2%** against `01-` §5's 37 / 211,557 / 34%. The characters
and the share match; the path count differs because `01-` counted `Read`/`Edit` calls and this
counts paths that returned a result.

---

## The seven sessions

Chosen to differ: a short one, a very long one, one dominated by tool output, one compacted,
one with sub-agents, one from an unattended run, one full of images. Home directories are
collapsed to `~` by the tool itself; nothing else in the output below is edited.

### 1. Short — `e168a4c4`, 7 requests, 55,983 tokens

```
session e168a4c4  ·  28 records  ·  7 requests (7 in the window)  ·  claude-opus-5  ·  no compaction
window at the last request                                               55,983  100.0%  exact

  ███████████             prefix (not in the file)                       29,392   52.5%  derived
                            · = ctx(req 1) 33,895 - est(visible before it) 4,503
                            system prompt                               unsized       —  unknown
                              · carried by no record type
                            tool definitions                            unsized       —  unknown
                              · names only, never schemas
  ████████                tool traffic                                   22,272   39.8%  est
  ████████                  Read results                                 21,498   38.4%  est
  ████████                    …-721638d11c0b-2/proposals/README.md  x2   21,498   38.4%  est
  ▏                         tool_use inputs                                 563    1.0%  est
  ▏                           Edit  x3                                      430    0.8%  est
  ▏                           Read  x2                                       77    0.1%  est
  ▏                           Grep                                           56    0.1%  est
  ▏                         Edit results                                    205    0.4%  est
  ▏                           …-721638d11c0b-2/proposals/README.md  x3      205    0.4%  est
  ▏                         Grep results                                      6    0.0%  est
  ▏                           ^(<{7}|={7}|>{7})                               6    0.0%  est
  █                       standing configuration                          4,076    7.3%  est
  ▏                         skill_listing                                 2,356    4.2%  est
  ▏                         hook_success                                    875    1.6%  est
  ▏                         agent_listing_delta                             672    1.2%  est
  ▏                         deferred_tools_delta                            173    0.3%  est
  ▏                       retained reasoning (not in the file)            1,491    2.7%  derived
                            · = sum over 6 responses of (output_tokens - est(text + tool_use))
                            thinking text                               unsized       —  unknown
                              · stripped on disk; 2 blocks, 805 tok/block median for this session
  ▏                       conversation                                      458    0.8%  est
  ▏                         user turns                                      444    0.8%  est
  ▏                         assistant text                                   14    0.0%  est
                          unattributed                                   -1,707   -3.0%  residual

exact 55,983 = derived 30,883 (55.2%) · est 26,807 (47.9%) · residual -1,707 (-3.0%)

how each kind was derived
  exact     read from usage.{input,cache_creation,cache_read}_tokens on the anchoring request
  derived   an exact number minus an estimate — see the per-node note
  est       payload characters / 2.6 (01- §2.3; the band is 2.4-3.0)
  residual  window - everything above it; what no kind accounts for
  unknown   in the window, in no record type, not separable — deliberately unsized
  note      pointer: model saw the preview, full output is in a tool-results/ sidecar
  note      no '% of window full' is printed: nothing in a transcript states the window size (§C7)

audit
  window (exact)                                55,983
  - prefix (derived)                            29,392
  - retained reasoning (derived)                 1,491
  - visible material (estimated)                26,807
  = unattributed (residual)                     -1,707   -3.0% of the window

  chars/token that would zero this session's residual: 2.78  (shipped: 2.6)
  NOT APPLIED — §C10: a residual that cannot be non-zero is not evidence.
```

**What it shows that a minute with the session would not.** That the operator's own instruction
was **444 tokens, 0.8%** of what the request cost, and that a single `README.md` read twice is
**38.4%** of the window. **Surprise:** mild — the prefix at 52.5% is the shape `01-` §2.6
column A predicted for short sessions, and `03-option-a` warned the top row would be one the
operator cannot act on. **Would they act?** Not really. "Short sessions are almost all
overhead" is a thing you know once and then know forever. The one honest action — read that
README with `offset` — saves 21k on a session that was going to end anyway.

**Also:** the residual is **−3.0%**, i.e. the tool over-explains this window. A short session
has few responses to smooth the estimate, and the `derived` share is 55.2%.

### 2. Very long — `72acbacd`, 311 requests, 512,133 tokens, a `[1m]` session

```
session 72acbacd  ·  1,525 records  ·  311 requests (311 in the window)  ·  claude-opus-5  ·  no compaction
window at the last request                                              512,133  100.0%  exact

  █████████████           tool traffic                                  317,069   61.9%  est
  █████                     Bash results                                135,897   26.5%  est
  █                           $ sed -n  x28                              44,549    8.7%  est
  █                           $ cd  x87                                  40,375    7.9%  est
  ▏                           $ grep  x42                                21,298    4.2%  est
  ▏                           $ node  x7                                 11,121    2.2%  est
  ▏                           14 more nodes, each smaller                 9,902    1.9%  est
  ▏                           $ git diff  x4                              6,287    1.2%  est
  ▏                           $ ls  x3                                    2,364    0.5%  est
  ████                      tool_use inputs                              97,111   19.0%  est
  ██                          Bash  x221                                 53,689   10.5%  est
  ▏                           Workflow  x2                               17,748    3.5%  est
  ▏                           …p__claude-in-chrome__browser_batch  x32    9,243    1.8%  est
  ▏                           …_claude-in-chrome__javascript_tool  x19    7,462    1.5%  est
  ▏                           Edit  x11                                   7,328    1.4%  est
  ▏                           8 more nodes, each smaller                  1,641    0.3%  est
  ██                        …__claude-in-chrome__browser_batch results   60,502   11.8%  est
  ██                          claude-in-chrome  x32                      60,502   11.8%  est
  ▏                         TaskOutput results                           12,694    2.5%  est
  ▏                         …claude-in-chrome__javascript_tool results    5,438    1.1%  est
  ▏                           claude-in-chrome  x19                       5,438    1.1%  est
  ▏                         8 more nodes, each smaller                    3,024    0.6%  est
  ▏                         Read results                                  2,404    0.5%  est
  ▏                           …/UsageFoundry/src/app/runs/page.tsx  x2    1,319    0.3%  est
  ▏                           …/GIT/UsageFoundry/src/app/chat/page.tsx      535    0.1%  est
  ▏                           …/UsageFoundry/src/app/branches/page.tsx      402    0.1%  est
  ▏                           …Foundry/src/lib/mergeQueueDrain.test.ts      148    0.0%  est
  ████                    retained reasoning (not in the file)           93,810   18.3%  derived
                            · = sum over 310 responses of (output_tokens - est(text + tool_use))
                            thinking text                               unsized       —  unknown
                              · stripped on disk; 152 blocks, 346 tok/block median for this session
  █                       standing configuration                         40,029    7.8%  est
  ▏                         edited_text_file                              9,565    1.9%  est
  ▏                         queued_command                                8,595    1.7%  est
  ▏                         total_tokens_reminder                         8,373    1.6%  est
  ▏                         nested_memory                                 7,527    1.5%  est
  ▏                           ~/.claude/rules/interface-copy.md           4,067    0.8%  est
  ▏                           ~/.claude/rules/typescript.md               3,460    0.7%  est
  ▏                         skill_listing                                 3,487    0.7%  est
  ▏                         6 more nodes, each smaller                    2,483    0.5%  est
  █                       prefix (not in the file)                       38,523    7.5%  derived
                            · = ctx(req 1) 44,710 - est(visible before it) 6,187
                            system prompt                               unsized       —  unknown
                              · carried by no record type
                            tool definitions                            unsized       —  unknown
                              · names only, never schemas
  ▏                       unattributed                                   18,075    3.5%  residual
  ▏                       conversation                                    4,627    0.9%  est
  ▏                         assistant text                                4,368    0.9%  est
  ▏                         user turns                                      259    0.1%  est

exact 512,133 = est 361,725 (70.6%) · derived 132,333 (25.8%) · residual 18,075 (3.5%)

how each kind was derived
  exact     read from usage.{input,cache_creation,cache_read}_tokens on the anchoring request
  derived   an exact number minus an estimate — see the per-node note
  est       payload characters / 2.6 (01- §2.3; the band is 2.4-3.0)
  residual  window - everything above it; what no kind accounts for
  unknown   in the window, in no record type, not separable — deliberately unsized
  note      pointer: model saw the preview, full output is in a tool-results/ sidecar
  note      image priced at w*h/750 from its decoded header, not its base64 length
  note      35 images priced at 54,162 tokens total; 0 unsized. Their base64 is 2.6 MB, which /4 would have called 642,763 tokens (§C5)
  note      no '% of window full' is printed: nothing in a transcript states the window size (§C7)

audit
  window (exact)                               512,133
  - prefix (derived)                            38,523
  - retained reasoning (derived)                93,810
  - visible material (estimated)               361,725
  = unattributed (residual)                     18,075   +3.5% of the window

  chars/token that would zero this session's residual: 2.48  (shipped: 2.6)
  NOT APPLIED — §C10: a residual that cannot be non-zero is not evidence.
```

**What it shows.** The image line, and it is not about this session: **35 images priced at
54,162 tokens where their 2.6 MB of base64 divided by four would have said 642,763** — an
11.9× over-report avoided, confirming `01-` §2.5's 14× on a different sample. **Surprise:**
no. Bash at 26.5%, retained reasoning at 18.3%, browser MCP at 11.8% is exactly what a
long browser-driving session looks like. **Would they act?** No. Every large row is a thing
they chose to do.

**The third level actively misleads here.** `$ cd ×87` at 40,375 tokens is the second-largest
Bash node and names no command that was run: `bash_head` splits on `&&` and takes the first
segment, so every `cd X && rg …` is filed under `cd`.

### 3. Dominated by tool output — `b66837ed`, 107 requests, 487,584 tokens

```
session b66837ed  ·  511 records  ·  107 requests (107 in the window)  ·  claude-opus-5  ·  no compaction
window at the last request                                              487,584  100.0%  exact

  ██████████████████      tool traffic                                  417,842   85.7%  est
  ███████████               Skill results                               265,450   54.4%  est
  ███████████                 claude-api  x2                            265,450   54.4%  est
  ████                      tool_use inputs                              99,941   20.5%  est
  ███                         Write  x16                                 66,947   13.7%  est
  █                           Bash  x97                                  28,686    5.9%  est
  ▏                           Edit  x11                                   4,194    0.9%  est
  ▏                           2 more nodes, each smaller                    115    0.0%  est
  ██                        Bash results                                 45,840    9.4%  est
  ▏                           $ cd  x34                                  13,107    2.7%  est
  ▏                           …c-9581-4e38-8e4a-f73cbe1eec1d.jsonl  x2    8,214    1.7%  est
  ▏                           $ sed -n  x6                                7,171    1.5%  est
  ▏                           9 more nodes, each smaller                  5,876    1.2%  est
  ▏                           $ ls  x9                                    4,487    0.9%  est
  ▏                           $ grep  x11                                 2,808    0.6%  est
  ▏                           $ echo  x5                                  2,130    0.4%  est
  ▏                           $ find  x2                                  2,047    0.4%  est
  ▏                         Read results                                  4,522    0.9%  est
  ▏                           /tmp/uf-rdt/verify2.txt                     2,034    0.4%  est
  ▏                           /tmp/uf-rdt/verify.txt                      1,192    0.2%  est
  ▏                           /tmp/uf-rdt/verify4.txt                       770    0.2%  est
  ▏                           /tmp/uf-rdt/verify3.txt                       526    0.1%  est
  ▏                         2 more nodes, each smaller                    2,090    0.4%  est
  █                       retained reasoning (not in the file)           38,860    8.0%  derived
                            · = sum over 106 responses of (output_tokens - est(text + tool_use))
                            thinking text                               unsized       —  unknown
                              · stripped on disk; 58 blocks, 421 tok/block median for this session
  █                       prefix (not in the file)                       26,734    5.5%  derived
                            · = ctx(req 1) 34,642 - est(visible before it) 7,908
                            system prompt                               unsized       —  unknown
                              · carried by no record type
                            tool definitions                            unsized       —  unknown
                              · names only, never schemas
  ▏                       standing configuration                         18,178    3.7%  est
  ▏                         edited_text_file                             10,256    2.1%  est
  ▏                         6 more nodes, each smaller                    3,589    0.7%  est
  ▏                         skill_listing                                 2,581    0.5%  est
  ▏                         deferred_tools_delta                          1,752    0.4%  est
  ▏                       conversation                                    3,513    0.7%  est
  ▏                         user turns                                    2,902    0.6%  est
  ▏                         assistant text                                  610    0.1%  est
                          unattributed                                  -17,542   -3.6%  residual

exact 487,584 = est 439,532 (90.1%) · derived 65,593 (13.5%) · residual -17,542 (-3.6%)

how each kind was derived
  exact     read from usage.{input,cache_creation,cache_read}_tokens on the anchoring request
  derived   an exact number minus an estimate — see the per-node note
  est       payload characters / 2.6 (01- §2.3; the band is 2.4-3.0)
  residual  window - everything above it; what no kind accounts for
  unknown   in the window, in no record type, not separable — deliberately unsized
  note      pointer: model saw the preview, full output is in a tool-results/ sidecar
  note      a `user` text block carrying a tool's return outside a tool_result envelope, paired by sourceToolUseID (a Skill body arrives this way)
  note      no '% of window full' is printed: nothing in a transcript states the window size (§C7)

audit
  window (exact)                               487,584
  - prefix (derived)                            26,734
  - retained reasoning (derived)                38,860
  - visible material (estimated)               439,532
  = unattributed (residual)                    -17,542   -3.6% of the window

  chars/token that would zero this session's residual: 2.71  (shipped: 2.6)
  NOT APPLIED — §C10: a residual that cannot be non-zero is not evidence.
```

**What it shows.** `tool traffic` at **85.7%**, and inside it a single skill body — `Skill
results → claude-api ×2` — at **265,450 tokens, 54.4% of the window**. Nothing else in this
session comes close: the next row is `Write` tool inputs at 13.7%. **Surprise: yes, and it is
the biggest one the spike produced.** The skill was auto-invoked, twice, by a trigger that
matches most LLM-shaped work; the second copy is pure duplication. **Would they act? Yes** —
narrow the trigger, or invoke it once. That is a configuration change worth ~265k tokens per
session on this kind of work, and it is invisible to `/context`, which folds a `user`/`text`
block into `Messages`.

**Also:** residual **−3.6%** on a session where 90.1% of the window is `est`. When the visible
material dominates, the chars-per-token constant is the whole error bar, and it shows.

### 4. Compacted — `2551cd0c`, 164 requests, 19 of them in the window

```
session 2551cd0c  ·  630 records  ·  164 requests (19 in the window)  ·  claude-opus-5  ·  3 compaction boundaries
window at the last request                                              116,030  100.0%  exact
dropped by compaction (cumulative)                                      444,326      —  exact
  last boundary: auto compaction, pre/post                            170,229 / 23,301

  ██████                  tool traffic                                   34,310   29.6%  est
  ████                      Bash results                                 22,919   19.8%  est
  ██                          $ for  x5                                  15,240   13.1%  est
  ▏                           $ python3  x6                               3,576    3.1%  est
  ▏                           $ cat  x4                                   2,426    2.1%  est
  ▏                           $ sed -n                                      932    0.8%  est
  ▏                           $ grep  x2                                    745    0.6%  est
  ██                        tool_use inputs                              11,391    9.8%  est
  ██                          Bash  x18                                  11,391    9.8%  est
  █████                   prefix (not in the file)                       31,209   26.9%  derived
                            · = ctx(req 1) 37,389 - est(visible before it) 6,180
                            system prompt                               unsized       —  unknown
                              · carried by no record type
                            tool definitions                            unsized       —  unknown
                              · names only, never schemas
  ████                    standing configuration                         23,955   20.6%  est
  ███                       file                                         20,170   17.4%  est
  ▏                         deferred_tools_delta                          2,489    2.1%  est
  ▏                         agent_listing_delta                             672    0.6%  est
  ▏                         3 more nodes, each smaller                      624    0.5%  est
  ██                      retained reasoning (not in the file)           13,701   11.8%  derived
                            · = sum over 18 responses of (output_tokens - est(text + tool_use))
                            thinking text                               unsized       —  unknown
                              · stripped on disk; 14 blocks, 580 tok/block median for this session
  █                       compaction summary                              9,928    8.6%  est
  ▏                       unattributed                                    2,927    2.5%  residual
                          conversation                                        0    0.0%  est
                            user turns                                        0    0.0%  est

exact 116,030 = est 68,193 (58.8%) · derived 44,910 (38.7%) · residual 2,927 (2.5%)

how each kind was derived
  exact     read from usage.{input,cache_creation,cache_read}_tokens on the anchoring request
  derived   an exact number minus an estimate — see the per-node note
  est       payload characters / 2.6 (01- §2.3; the band is 2.4-3.0)
  residual  window - everything above it; what no kind accounts for
  unknown   in the window, in no record type, not separable — deliberately unsized
  note      pointer: model saw the preview, full output is in a tool-results/ sidecar
  note      no '% of window full' is printed: nothing in a transcript states the window size (§C7)

audit
  window (exact)                               116,030
  - prefix (derived)                            31,209
  - retained reasoning (derived)                13,701
  - visible material (estimated)                68,193
  = unattributed (residual)                      2,927   +2.5% of the window

  chars/token that would zero this session's residual: 2.49  (shipped: 2.6)
  NOT APPLIED — §C10: a residual that cannot be non-zero is not evidence.
```

**What it shows.** The three exact lines above the tree: the window is **116,030**, the session
dropped **444,326** tokens, and the last boundary went **170,229 → 23,301**. `/context` cannot
show any of that, and a tool that walked from the top and added would have reported 416,774
(`01-` §2.6). **Surprise:** the *composition* after compaction, mildly — `standing
configuration → file` at **17.4%** is an attachment re-injected after the summary, and
`conversation` is literally **zero**, because nothing the operator or the model said in prose
survived. **Would they act?** On the numbers, no. On the `file` attachment at 17.4% of a
post-compaction window, maybe.

**And the third level misleads again:** `$ for ×5` at 13.1% is a shell loop, filed under `for`.

### 5. Sub-agents — `c3566197`, 48 `Agent` calls, 500,871 tokens

```
session c3566197  ·  652 records  ·  86 requests (86 in the window)  ·  claude-opus-5  ·  no compaction
window at the last request                                              500,871  100.0%  exact

  █████████████████       tool traffic                                  395,757   79.0%  est
  ███████████               Skill results                               265,445   53.0%  est
  ███████████                 claude-api  x2                            265,445   53.0%  est
  ██                        tool_use inputs                              57,427   11.5%  est
  ▏                           Write  x8                                  20,570    4.1%  est
  ▏                           Agent  x48                                 18,863    3.8%  est
  ▏                           Bash  x61                                  10,815    2.2%  est
  ▏                           Edit  x15                                   7,044    1.4%  est
  ▏                           3 more nodes, each smaller                    136    0.0%  est
  █                         Read results                                 27,903    5.6%  est
  ▏                           …1638d11c0b-1/docs/external-validator.md   16,633    3.3%  est
  ▏                           …1638d11c0b-1/docs/validator-baseline.md   11,270    2.3%  est
  █                         Bash results                                 23,392    4.7%  est
  ▏                           $ node  x16                                10,191    2.0%  est
  ▏                           15 more nodes, each smaller                 4,584    0.9%  est
  ▏                           $ cd  x9                                    3,395    0.7%  est
  ▏                           $ echo  x6                                  2,999    0.6%  est
  ▏                           $ tail                                      2,223    0.4%  est
  ▏                         Agent returns                                19,902    4.0%  est
                              · 48 sub-agents spent 1,908,088 tokens of their own windows to return 19,902 into this one (§C11: their budgets are never added to it)
  ▏                           45 more nodes, each smaller                18,658    3.7%  est
  ▏                           …case 01  [own window 24,244, not added]      415    0.1%  est
  ▏                           …case 02  [own window 26,111, not added]      415    0.1%  est
  ▏                           …case 03  [own window 28,465, not added]      415    0.1%  est
  ▏                         3 more nodes, each smaller                    1,687    0.3%  est
  █                       retained reasoning (not in the file)           37,008    7.4%  derived
                            · = sum over 85 responses of (output_tokens - est(text + tool_use))
                            thinking text                               unsized       —  unknown
                              · stripped on disk; 46 blocks, 575 tok/block median for this session
  █                       standing configuration                         28,928    5.8%  est
  ▏                         queued_command                               14,848    3.0%  est
  ▏                         edited_text_file                              6,497    1.3%  est
  ▏                         nested_memory                                 3,456    0.7%  est
  ▏                           ~/.claude/rules/typescript.md               3,456    0.7%  est
  ▏                         skill_listing                                 2,407    0.5%  est
  ▏                         6 more nodes, each smaller                    1,720    0.3%  est
  █                       prefix (not in the file)                       28,406    5.7%  derived
                            · = ctx(req 1) 34,657 - est(visible before it) 6,251
                            system prompt                               unsized       —  unknown
                              · carried by no record type
                            tool definitions                            unsized       —  unknown
                              · names only, never schemas
  ▏                       unattributed                                    7,991    1.6%  residual
  ▏                       conversation                                    2,782    0.6%  est
  ▏                         user turns                                    2,530    0.5%  est
  ▏                         assistant text                                  252    0.1%  est

exact 500,871 = est 427,466 (85.3%) · derived 65,415 (13.1%) · residual 7,991 (1.6%)

how each kind was derived
  exact     read from usage.{input,cache_creation,cache_read}_tokens on the anchoring request
  derived   an exact number minus an estimate — see the per-node note
  est       payload characters / 2.6 (01- §2.3; the band is 2.4-3.0)
  residual  window - everything above it; what no kind accounts for
  unknown   in the window, in no record type, not separable — deliberately unsized
  note      a `user` text block carrying a tool's return outside a tool_result envelope, paired by sourceToolUseID (a Skill body arrives this way)
  note      no '% of window full' is printed: nothing in a transcript states the window size (§C7)

audit
  window (exact)                               500,871
  - prefix (derived)                            28,406
  - retained reasoning (derived)                37,008
  - visible material (estimated)               427,466
  = unattributed (residual)                      7,991   +1.6% of the window

  chars/token that would zero this session's residual: 2.55  (shipped: 2.6)
  NOT APPLIED — §C10: a residual that cannot be non-zero is not evidence.
```

**What it shows.** Two things, and the second is a number that exists nowhere else on this
machine:

- the same `claude-api` skill body, **53.0%** of a second, unrelated window — which is what
  turns finding 3 from an anecdote into a recurring configuration fault;
- **48 sub-agents spent 1,908,088 tokens of their own windows to return 19,902 into this one.**
  A 96:1 ratio, computed by joining `subagents/agent-*.meta.json` on `toolUseId`, and never
  added to the parent's total (§C11).

**Surprise:** yes on both. **Would they act?** On the skill, yes. On the 96:1, honestly
**no** — that ratio *is* fan-out, not a mistake; the operator paid it deliberately. It is the
"was that a trade?" question §C11 predicted, and having the number does not answer it. Worth
printing; not worth building a tool for.

### 6. An unattended UsageFoundry run — `939a04dc`, 111 requests, 222,249 tokens

This is the earlier run of *this proposal* — the session that wrote `02-constraints.md` — which
is how it is identifiable as unattended: it is in `~/.claude/projects/-workspace--uf-worktrees-winnow-…`,
and its `Read`/`Edit` nodes are this directory's own files.

```
session 939a04dc  ·  598 records  ·  111 requests (111 in the window)  ·  claude-opus-5  ·  no compaction
window at the last request                                              222,249  100.0%  exact
shed with no compaction boundary                                         78,167      —  exact
  at record 288; what left is not in the file                         cause: <synthetic> response (interrupt or API error), deferred_tools_delta
shed with no compaction boundary                                          9,586      —  exact
  at record 404; what left is not in the file                         cause: nothing in the file names a cause

  ██████████████          tool traffic                                  150,874   67.9%  est
  █████████                 tool_use inputs                              91,783   41.3%  est
  ████                        Write  x9                                  48,548   21.8%  est
  ██                          Edit  x76                                  29,833   13.4%  est
  ▏                           Bash  x39                                   9,735    4.4%  est
  ▏                           Agent  x3                                   2,728    1.2%  est
  ▏                           Read  x18                                     939    0.4%  est
  ██                        Bash results                                 29,330   13.2%  est
  █                           $ grep  x8                                 15,943    7.2%  est
  ▏                           $ python3  x6                               4,093    1.8%  est
  ▏                           $ git log  x2                               2,400    1.1%  est
  ▏                           $ sed -n  x2                                2,174    1.0%  est
  ▏                           $ timeout  x8                               2,145    1.0%  est
  ▏                           $ cd  x6                                    1,395    0.6%  est
  ▏                           6 more nodes, each smaller                  1,180    0.5%  est
  █                         Read results                                 14,815    6.7%  est
  ▏                           …s/ContextTreemap/01-what-is-knowable.md    3,015    1.4%  est
  ▏                           …als/ContextTreemap/04-comparison.md  x3    2,895    1.3%  est
  ▏                           …ContextTreemap/05-recommendation.md  x5    2,636    1.2%  est
  ▏                           …/proposals/ContextTreemap/00-problem.md    2,360    1.1%  est
  ▏                           …/ContextTreemap/scratch/prefix_floor.py    1,781    0.8%  est
  ▏                           …ntextTreemap/scratch/floor_decompose.py    1,585    0.7%  est
  ▏                           4 more nodes, each smaller                    542    0.2%  est
  ▏                         Agent returns                                 8,427    3.8%  est
                              · 3 sub-agents spent 369,134 tokens of their own windows to return 8,427 into this one (§C11: their budgets are never added to it)
  ▏                           …sisten  [own window 127,658, not added]    3,238    1.5%  est
  ▏                           …ntions  [own window 111,304, not added]    3,161    1.4%  est
  ▏                           …landed  [own window 130,172, not added]    2,028    0.9%  est
  ▏                         Edit results                                  5,853    2.6%  est
  ▏                           5 more nodes, each smaller                  2,420    1.1%  est
  ▏                           …ontextTreemap/05-recommendation.md  x20    1,498    0.7%  est
  ▏                           …emap/03-option-b-drill-down-tui.md  x13    1,035    0.5%  est
  ▏                           …s/ContextTreemap/02-constraints.md  x12      900    0.4%  est
  ▏                         Write results                                   666    0.3%  est
  ▏                           6 more nodes, each smaller                    437    0.2%  est
  ▏                           …eemap/03-option-d-project-of-its-own.md       77    0.0%  est
  ▏                           …Treemap/03-option-a-one-shot-readout.md       77    0.0%  est
  ▏                           …xtTreemap/03-option-b-drill-down-tui.md       76    0.0%  est
  █████                   retained reasoning (not in the file)           59,826   26.9%  derived
                            · = sum over 110 responses of (output_tokens - est(text + tool_use))
                            thinking text                               unsized       —  unknown
                              · stripped on disk; 17 blocks, 390 tok/block median for this session
  ████                    standing configuration                         40,823   18.4%  est
  ███                       edited_text_file                             32,018   14.4%  est
  ▏                         nested_memory                                 2,855    1.3%  est
  ▏                           ~/.claude/rules/python.md                   2,855    1.3%  est
  ▏                         skill_listing                                 2,592    1.2%  est
  ▏                         hook_success                                  1,748    0.8%  est
  ▏                         agent_listing_delta                             906    0.4%  est
  ▏                         3 more nodes, each smaller                      704    0.3%  est
  ██                      prefix (not in the file)                       24,416   11.0%  derived
                            · = ctx(req 1) 32,420 - est(visible before it) 8,004
                            system prompt                               unsized       —  unknown
                              · carried by no record type
                            tool definitions                            unsized       —  unknown
                              · names only, never schemas
  ▏                       conversation                                    3,097    1.4%  est
  ▏                         user turns                                    2,908    1.3%  est
  ▏                         assistant text                                  189    0.1%  est
                          unattributed                                  -56,787  -25.6%  residual

exact 222,249 = est 194,794 (87.6%) · derived 84,242 (37.9%) · residual -56,787 (-25.6%)

how each kind was derived
  exact     read from usage.{input,cache_creation,cache_read}_tokens on the anchoring request
  derived   an exact number minus an estimate — see the per-node note
  est       payload characters / 2.6 (01- §2.3; the band is 2.4-3.0)
  residual  window - everything above it; what no kind accounts for
  unknown   in the window, in no record type, not separable — deliberately unsized
  note      pointer: model saw the preview, full output is in a tool-results/ sidecar
  note      no '% of window full' is printed: nothing in a transcript states the window size (§C7)

audit
  window (exact)                               222,249
  - prefix (derived)                            24,416
  - retained reasoning (derived)                59,826
  - visible material (estimated)               194,794
  = unattributed (residual)                    -56,787   -25.6% of the window
    of which unmodelled shedding                  87,753   material that left the window with no record of what it was

  chars/token that would zero this session's residual: 3.67  (shipped: 2.6)
  NOT APPLIED — §C10: a residual that cannot be non-zero is not evidence.
```

**What it shows.** The failure. Two exact lines above the tree say the window **shed 78,167
tokens and then 9,586 more, with no compaction boundary**, and the first has a cause the file
does name: a `<synthetic>` response (an interrupt or API error) followed by a
`deferred_tools_delta`. Tool schemas moved behind `ToolSearch` and a third of the window went
with them. The residual is **−25.6%**, and the audit line attributes 87,753 of it to shedding.

**Surprise: yes, and it is the one that changes the design.** `05-` measures the prefix **once**,
by first-request subtraction, and treats it as a constant for the session. On this session it
was wrong by 78,167 tokens — 35% of the final window — for the last 60 requests.

**Would they act?** Yes, but not on the session: on the readout. A number that can be a third
wrong without saying so is worse than no number, and the fix is cheap — the drop is exactly
computable from consecutive `usage` totals.

**Also visible and worth one line:** `tool_use inputs` are **41.3%** of this window against
`Bash`+`Read`+`Edit`+`Write` *results* at 23.8% combined. A documentation session pays for what
it writes, not what it reads. That inverts the assumption behind `00-` §2's questions, all of
which are about material coming *in*.

### 7. Images — `e268d6c5`, 186 requests, 433,331 tokens

```
session e268d6c5  ·  788 records  ·  186 requests (186 in the window)  ·  claude-opus-5  ·  no compaction
window at the last request                                              433,331  100.0%  exact

  █████████               tool traffic                                  185,525   42.8%  est
  ███                       …__claude-in-chrome__browser_batch results   67,372   15.5%  est
  ███                         claude-in-chrome  x33                      67,372   15.5%  est
  ██                        Bash results                                 52,895   12.2%  est
  ██                          $ cd  x79                                  48,376   11.2%  est
  ▏                           $ grep  x3                                  2,547    0.6%  est
  ▏                           $ for                                       1,374    0.3%  est
  ▏                           4 more nodes, each smaller                    598    0.1%  est
  ██                        tool_use inputs                              44,324   10.2%  est
  █                           Edit  x35                                  21,123    4.9%  est
  ▏                           Bash  x87                                  10,562    2.4%  est
  ▏                           …p__claude-in-chrome__browser_batch  x33    9,545    2.2%  est
  ▏                           …__claude-in-chrome__javascript_tool  x8    2,121    0.5%  est
  ▏                           7 more nodes, each smaller                    972    0.2%  est
  ▏                         Read results                                  8,690    2.0%  est
  ▏                           …geFoundry/src/app/branches/page.tsx  x3    3,652    0.8%  est
  ▏                           …/UsageFoundry/src/lib/mergeQueue.ts  x3    2,183    0.5%  est
  ▏                           …dry/src/app/api/branches/queue/route.ts    1,874    0.4%  est
  ▏                           3 more nodes, each smaller                    980    0.2%  est
  ▏                         mcp__claude-in-chrome__computer results       5,727    1.3%  est
  ▏                           claude-in-chrome  x4                        5,727    1.3%  est
  ▏                         6 more nodes, each smaller                    4,069    0.9%  est
  ▏                         Edit results                                  2,448    0.6%  est
  ▏                           12 more nodes, each smaller                 1,124    0.3%  est
  ▏                           …ndry/src/lib/mergeQueueView.test.ts  x8      569    0.1%  est
  ▏                           …geFoundry/src/app/branches/page.tsx  x7      485    0.1%  est
  ▏                           …/UsageFoundry/src/lib/mergeQueue.ts  x4      271    0.1%  est
  ███████                 prefix (not in the file)                      146,870   33.9%  derived
                            · = ctx(req 1) 152,217 - est(visible before it) 5,347
                            system prompt                               unsized       —  unknown
                              · carried by no record type
                            tool definitions                            unsized       —  unknown
                              · names only, never schemas
  ███                     retained reasoning (not in the file)           72,903   16.8%  derived
                            · = sum over 185 responses of (output_tokens - est(text + tool_use))
                            thinking text                               unsized       —  unknown
                              · stripped on disk; 100 blocks, 486 tok/block median for this session
  ▏                       standing configuration                         15,718    3.6%  est
  ▏                         nested_memory                                 7,527    1.7%  est
  ▏                           ~/.claude/rules/interface-copy.md           4,067    0.9%  est
  ▏                           ~/.claude/rules/typescript.md               3,460    0.8%  est
  ▏                         skill_listing                                 3,028    0.7%  est
  ▏                         edited_text_file                              2,925    0.7%  est
  ▏                         6 more nodes, each smaller                    2,238    0.5%  est
  ▏                       unattributed                                   10,247    2.4%  residual
  ▏                       conversation                                    2,068    0.5%  est
  ▏                         assistant text                                1,818    0.4%  est
  ▏                         user turns                                      250    0.1%  est

exact 433,331 = derived 219,773 (50.7%) · est 203,311 (46.9%) · residual 10,247 (2.4%)

how each kind was derived
  exact     read from usage.{input,cache_creation,cache_read}_tokens on the anchoring request
  derived   an exact number minus an estimate — see the per-node note
  est       payload characters / 2.6 (01- §2.3; the band is 2.4-3.0)
  residual  window - everything above it; what no kind accounts for
  unknown   in the window, in no record type, not separable — deliberately unsized
  note      a `user` text block carrying a tool's return outside a tool_result envelope, paired by sourceToolUseID (a Skill body arrives this way)
  note      image priced at w*h/750 from its decoded header, not its base64 length
  note      49 images priced at 66,318 tokens total; 0 unsized. Their base64 is 3.8 MB, which /4 would have called 939,317 tokens (§C5)
  note      no '% of window full' is printed: nothing in a transcript states the window size (§C7)

audit
  window (exact)                               433,331
  - prefix (derived)                           146,870
  - retained reasoning (derived)                72,903
  - visible material (estimated)               203,311
  = unattributed (residual)                     10,247   +2.4% of the window

  chars/token that would zero this session's residual: 2.48  (shipped: 2.6)
  NOT APPLIED — §C10: a residual that cannot be non-zero is not evidence.
```

**What it shows.** **49 images priced at 66,318 tokens against 3.8 MB of base64 that `/4`
would have called 939,317** — a 14.2× over-report avoided, matching `01-` §2.5 exactly. And a
prefix of **33.9%**, high because this session loads a browser MCP server. **Surprise:** no.
**Would they act?** No — the screenshots are the work.

---

## What the spike proved about the design

### Where the recommended hierarchy fought the data

Five places. The first four are in descending order of how much they cost; item 4 is the only
one that failed an acceptance criterion outright.

**1. Provenance is not readable from the record type, and the biggest node in the corpus is the
proof.** A `Skill` body reaches the window as a `user`/`text` record. H1 asks *who put this
here*; the file answers *a user record*. Before the spike paired it through `sourceToolUseID`,
**53.0% of `c3566197`'s window sat under `conversation → user turns`** — a confidently,
invisibly wrong readout of exactly the kind `03-option-a` names as its only silent failure, and
the residual did not catch it because misattribution conserves the total. The join exists and
is undocumented; over an 80-file sample, four records carrying `isMeta` **and**
`sourceToolUseID` held 947,168 characters. Any classifier that keys on `type` alone will make
this mistake, and the golden fixture `05-` calls mandatory is the only thing that would have
caught it.

**2. The prefix is not constant, and H1 gives it one node.** Measured above on `939a04dc`:
78,167 tokens left the window mid-session. Corpus-wide, **17 of 164 sampled sessions (10.4%)
shed context with no compaction boundary, median 36,714 tokens**. §C6 handles compaction and
nothing handles this. Two consequences: the `prefix` node needs to be re-derived at every
shedding event, or labelled with the request it was measured at; and the residual must be
allowed to be *negative* and to say why, which the spike does and `03-option-a`'s mock readout
does not contemplate.

**3. `bash_head` is the wrong key for H3-under-Bash.** It is `winnow`'s rule-matching
normaliser and it does its own job correctly. Used as a treemap key it produces
`$ cd ×87` (7.9% of `72acbacd`), `$ cd ×79` (11.2% of `e268d6c5`) and `$ for ×5` (13.1% of
`2551cd0c`) — on three of seven sessions the largest or second-largest Bash node names no
command anybody ran. `01-` §5 already called bucketing Bash by command head "crude"; the spike
puts a number on how crude.

**4. Keying the tree tool-first makes H3's headline number unreachable — it halves it.** This
is the one that failed an acceptance criterion, and it is the strongest argument in the file
for restructuring rather than for building as specified.

`01-` §5 calls "which file is in my window more than once" *the single most actionable question
there is*, measures it on `f6ea2591` at **34% of `Read`/`Edit` output from repeated paths**, and
`05-` §M2 accepts on reproducing it while mandating a shape that cannot. The path is the *third* level,
under a *tool* at the second, so `src/lib/db.ts` read twice and edited once is not one node
with `×3` — it is `Read results → db.ts ×2` and `Edit results → db.ts`, in different subtrees.
Measured on that session, over the whole file, by the spike's own character counter:

| keyed | distinct nodes | repeated share |
|---|---:|---:|
| by path, `Read` and `Edit` pooled — what `01-` §5 measured | 29 | **33.2%** |
| by (tool, path) — what the tree renders | 32 | **16.8%** |

Three paths touched by both tools become six singleton nodes, and the number the proposal calls
its most actionable collapses to half. Adding the `tool_use` input for the same file — `Edit`'s
input carries the new content and is often larger than its result — splits it a third way: on
`939a04dc` that puts `Write ×9` inputs at **21.8%** of the window three rows from `Write
results` at **0.3%**.

The fix is a hierarchy change, not a rendering one: **artefact above tool** under `tool
traffic`, so a path is one node with its tools beneath it. That is the shape `01-` §5 described
and `05-` §M2 mandated the inverse of. It is also what makes the third level worth having at
all — the version measured here is not.

**A fifth, smaller:** `standing configuration`'s second level is the attachment `type` field,
which is a CLI implementation detail rather than a provenance. It collects `edited_text_file`
(14.4% of `939a04dc`), `queued_command` (3.0% of `c3566197`) and `file` (17.4% of `2551cd0c`) —
none of which are standing, and all of which are working-session artefacts.

### What the unknown block turned out to be worth

Three separate quantities, and `05-` conflates the first two.

**The literally-unknown block is worth nothing, and that is correct.** `system prompt` and `tool
definitions` render as two lines reading `unsized — unknown`. They carry no tokens because the
material they name is priced by their `derived` parent instead. Two lines of screen for the
guarantee that nothing was quietly dropped is the right price.

**The invisible-but-priced block is worth ~38% of the median window, and it is the best part of
the readout.** Over the 164-session sweep: prefix median **25.4%**, retained reasoning median
**12.9%**. On the seven sessions the combined `derived` share ran from **13.1%** (`c3566197`) to
**55.2%** (`e168a4c4`). This confirms `02-constraints.md`'s correction on a different classifier
and a different day.

**The residual is worth 0.4% at the median and ±25% at the tails, and the operator gets one
session.** Paired same-day run, same 200-file even sample:

| | spike `--sweep 200` | `scratch/thinking_price.py 200` |
|---|---:|---:|
| sessions qualifying | 164 | 161 |
| unexplained, visible only — median | 41.7% | 39.7% |
| **unexplained, fully decomposed — median** | **+0.4%** | **+0.3%** |
| …p25 / p75 | −1.9% / +3.5% | −1.9% / +3.1% |
| `abs(residual) ≤ 15%` | 150/164 (91.5%) | 148/161 (91.9%) |
| over-explained (residual < 0) | 74/164 | 74/161 |
| compacted sessions included | 7 | 0 — excluded by the prototype |

`05-`'s first two success criteria are met: the median is **≤5%**, and the classifier is not
worse than the prototype — 150 sessions within ±15% against 148, at a rate a third of a point
lower over a sample that also includes the compacted sessions the prototype refuses. Read the
0.4%-vs-0.3% as identical, because the sample differs by three sessions.

The distribution is the part to argue with. **A median of 0.4% is a corpus fact and the
operator has one session.** The seven here ran −25.6%, −3.6%, −3.0%, +1.6%, +2.4%, +2.5%,
+3.5%. The largest error was not the estimate — it was material that left the window unrecorded,
which the residual absorbs silently unless the shedding line is printed. That line is the
single cheapest honesty fix available and it is not in `05-`.

### How long a full first slice now looks

**The two weeks still fits. The allocation in `05-` is wrong, and it is wrong in a way that
matters.**

M1's three days were budgeted for the walk — resolve, parse, dedupe, anchor, apportion, print.
The spike did all of that plus most of M2 and M3 in one sitting and 815 lines, and hits three
M1 acceptance numbers it was not written against. `01-` §6.1 was right: the parser, the
resolver and the block walk are not being written. **M1 is closer to a day and a half than to
three days.**

The classifier is the whole cost, and `03-option-a`'s "two days of argument about the
classifier's category boundaries" is the estimate that is too low. Seven sessions surfaced five
category-boundary faults, one of which silently misplaced half a window and one of which made
M2's own acceptance number unreachable. That is not two days
of argument; that is M2.

Revised, inside the same fourteen:

| slice | `05-` | after the spike |
|---|---|---|
| M1 walking skeleton | days 1–3 | **days 1–2** — nearly free, as measured |
| M2 the drill-down | days 4–6 | **days 3–7, and it is the classifier, not the drill.** Two levels, the five faults above, the golden fixture first rather than last, `--depth 3` re-keyed artefact-then-tool, and the acceptance criterion restated so it is reachable |
| M3 the floor, priced | days 7–9 | **days 8–10**, plus a new item: prefix re-derivation at every shedding event, and the exact shed line above the tree |
| M4 live + `--by-turn` | days 10–12 | **unchanged, and more likely to be dropped.** The day-6 slip rule now fires on day 7 |

The one thing that got *cheaper*: `05-`'s guardrails. `import winnow.report` reaches none of
`guard`, `team`, `proxy` or `orchestrator_safe` today, so the `sys.modules` assertion passes
before `cli.py` is touched at all.

---

## The question the whole proposal exists to answer

*Does a sized picture of a context tell the operator anything they cannot already see?*

**On three of seven sessions, yes. On four, no.** Written out, because a spike that flatters
its own idea is worthless:

| session | new? | would the operator act? |
|---|---|---|
| `b66837ed` | **yes** — one skill body is 54.4% of the window | **yes** — narrow the trigger |
| `c3566197` | **yes** — the same skill at 53.0%; 48 sub-agents at 96:1 | **yes** on the skill; no on the ratio |
| `939a04dc` | **yes** — 78,167 tokens left the window unrecorded | **yes**, on how to read the readout |
| `e168a4c4` | partly — one README twice is 38.4% | barely |
| `2551cd0c` | the exact compaction numbers, which nothing else prints | no |
| `72acbacd` | no | no |
| `e268d6c5` | no | no |

Two clear actions in seven sessions, against `05-`'s kill criterion of **three in ten**. That
is not a pass; it is a hair over the line, on a sample of seven, self-assessed. It should be
said in the same breath as the verdict.

What tips it to *build* rather than *drop* is the shape of the two that landed. Both are
**configuration** faults — an auto-invoked skill, a harness that silently reclaims tool
schemas — not working-style faults. Neither is discoverable by working more carefully. Both
recur across sessions, so finding them once pays on every session afterwards. And both were
visible in the **first two rows** of the readout, which is why the recommendation above spends
the saved days on the classifier and not on the drill.

`00-` §6 named "nobody acts on it" as the most likely way this dies. On this evidence it does
not die, but it survives on one narrow strength: **it finds things the operator did not
choose.** That is worth building, and it is a smaller thing than a treemap.

---

## Reproducing

```
.venv/bin/python proposals/ContextTreemap/spike/context_tree.py <session-id> --depth 3 --audit
.venv/bin/python proposals/ContextTreemap/spike/context_tree.py --sweep 200
.venv/bin/python proposals/ContextTreemap/scratch/thinking_price.py 200
```

Both sweeps above were run on 2026-09-02, minutes apart, over the same 200-file even sample of
`~/.claude/projects`, for the reason `02-constraints.md` gives: this machine writes transcripts
into the corpus it measures, so only a paired same-day comparison means anything.

The spike is disposable. It should not be extended, wired into the CLI, or read as a
specification — the five classifier faults above are the specification, and they are in this
file rather than in its code.
