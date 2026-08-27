# Option Q — the shapes a `tool_result` actually comes in

**Verdict: nothing to change today, and a precondition to write down before anything widens
`rule_for`.** The filter has never seen a structured `tool_result` on a path that matters — of
4,715 candidates on this corpus, **zero** carry list-form content — so every content-shape
hazard in the code is closed by the same coincidence of scope that closes the pointer's
tool-name hole. This file establishes the shapes, the mass behind each, and the one that cannot
be re-run. It also corrects [00-problem.md](00-problem.md)'s image caveat, which is understated
by 2.7×.

## The shapes, measured

**Measured here, 2026-08-27**, over every `tool_result` block in the 867 main-session
transcripts under `~/.claude/projects/*/*.jsonl` on this container, sized with
`rules.result_size`:

| `content` is | Blocks | Bytes | Share of `tool_result` bytes |
| --- | ---: | ---: | ---: |
| a `str` | 61,895 | 130,775,255 | 67.9% |
| a `list` of blocks | 2,759 | 61,893,116 | 32.1% |
| absent, or `None` | **0** | 0 | — |
| anything else | **0** | 0 | — |
| **total** | **64,654** | **192,668,371** | 100% |

And inside the list-form ones:

| Inner block type | Blocks | Bytes |
| --- | ---: | ---: |
| `image` | 475 | **54,533,135** |
| `text` | 3,344 | 7,263,553 |
| `tool_reference` | 1,392 | 86,006 |

`tool_reference` is `{"type": "tool_reference", "tool_name": "WebFetch"}` — 62 bytes, a handle
the client emits when a tool is named rather than called. It is 0.03% of message content and is
mentioned here only so that "list-form content" is not read as "text and images".

**Every one of the 4,715 candidates has `str` content.** Not one is a list. That is not luck: a
candidate is a `Glob`, `LS`, `Grep` or `Bash` result, and none of those four tools returns a
structured result. Every structured result on this corpus comes from an MCP tool, an `Agent`, a
`Read` of an image, or a `WebFetch`.

## What `apply` would do with each, if a rule ever claimed one

Traced through the code rather than asserted.

**A list.** `result_size(content)` is `len(json.dumps(content))` (`rules.py:285-287`), so a
result carrying a 300 KB base64 screenshot measures as 300 KB and clears any floor. The pointer
check `isinstance(content, str) and POINTER_RE.match(content)` (`filter.py:261`) is `False`, so
it is decided normally. If a rule fired, `block["content"] = pointer(...)` (`filter.py:288`)
would replace the whole list with a bare string. **That is legal** — the Messages API documents
`tool_result.content` as a string or a list of blocks — and it keeps the re-entry guard working,
because what the filter writes is always a `str` and invariant I9 survives. So there is no
crash and no malformed request. What is lost is the whole list, images included, in one
substitution with no per-block choice.

**An `image` block inside one.** The bytes go and the model gets a text pointer where a picture
was. SPEC §7's route 1 is *"re-run the call"*, and whether that recovers anything depends
entirely on which tool produced it — see the split below. The pointer's own text,
*"Re-run the call if it is needed again"*, is the instruction, and for a browser screenshot it
is an instruction to take a different picture.

**No content at all.** `result_payload(None)` returns `""` (`rules.py:274-275`), so
`result_size` is 0, so the result is below any positive floor and can never be a candidate. Two
things follow: it is safe at every shipped setting, and it stops being safe at `min_bytes ≤ 0`,
which is the same unbounded flag [16-option-guards-by-name.md](16-option-guards-by-name.md)
shows breaks G4. At `--min-bytes 0` an empty result would be replaced by a 112-byte pointer
saying 0 bytes were removed. It does not occur on this corpus — there are no empty results at
all — and it is the second thing a G4 check would refuse for free.

**A missing `tool_use`.** `uses.get(id, ("", {}))` yields an empty name and input, `rule_for`
returns `None`, the result is kept. Under-firing, the safe direction, and it is not
hypothetical: **3 of the 64,654 results counted above have no matching `tool_use` in their own transcript
[measured here]**, 1,948 bytes.

## The image correction, and it moves every share in this set

[00-problem.md](00-problem.md) records a caveat that governs every percentage in this
directory:

> **19,954,267 of those 273,722,399 bytes — 7.29% — are 276 base64 image blocks inside MCP tool
> results [measured here]**, almost all of them browser screenshots.

That figure is exactly right for MCP and it is not the whole population. **Measured here**,
every `image` block inside list-form `tool_result` content, by the tool that produced it:

| Tool | Image blocks | Bytes |
| --- | ---: | ---: |
| `Read` | **199** | **34,578,868** |
| `mcp__claude-in-chrome__browser_batch` | 216 | 16,080,092 |
| `mcp__claude-in-chrome__computer` | 60 | 3,874,175 |
| **all** | **475** | **54,533,135** |

The two MCP tools sum to 276 blocks and 19,954,267 bytes — §00's figure to the byte, so the
populations agree and the difference is entirely the 199 `Read` results. **A `Read` of a `.png`
returns an image block**, and `Read` is a rule-free tool that no document in this set was
looking at for images.

Total base64 payload across all 475 is **54,492,036 bytes**. Against the corpus's message
content as accounted here — **280,679,191 bytes**, 2.5% above §00's 273,722,399 because the
corpus is live and gained a session between the two runs — that is **19.4% of message content
whose token cost `bytes ÷ 4` overstates by roughly the factor
[08-option-mcp-and-subagent-output.md](08-option-mcp-and-subagent-output.md) measured on the
MCP half: 27.7×.**

So §00's correction runs further than it says. On a denominator with all image blocks removed —
226,146,056 bytes — the filter's reach is **10.28%**, not the 9.15% §00 gives for its partial
correction and not the 8.28% the full denominator gives. **Every share in this proposal set is
low by about a quarter, not by about a twelfth.** The direction §00 states is right and the
magnitude is larger, and the reason it was missed is instructive: the image mass was found by
looking at MCP, and the largest single holder of it is the most ordinary tool in the set.

## The one thing that cannot be re-run, and it is not what it looks like

SPEC §7 route 1 is the filter's only recovery path, and
[10-option-recall-store.md](10-option-recall-store.md) rejects a store on the argument that the
filter's three rules are exactly the subset route 1 always serves. Split the image mass by that
test:

| | Blocks | Bytes | Re-runnable? |
| --- | ---: | ---: | --- |
| `Read` of an image file | 199 | 34,578,868 | **yes** — route 1 exactly: read the file again, and it is fresher |
| browser screenshot | 276 | 19,954,267 | **no** — the page has moved on; a re-taken screenshot is a different picture |

**63% of the image mass is recoverable and 37% is not.** The un-recoverable third is the one
option H says would invert its rejection, and it is the only content class in this corpus where
that inversion applies. Naming it in bytes is the useful form: an option that widens `rule_for`
to MCP results is taking on 19,954,267 bytes of content that route 1 cannot return, and it owes
either a store or a rule that excludes `image` blocks by shape.

## The precondition, stated once so an option can be judged against it

**Any option that widens `rule_for` past `Glob`, `LS`, `Grep` and `Bash` must state what it does
with a list.** Three answers exist and they are not equivalent:

1. **Refuse.** `if not isinstance(content, str): return None` before the rule is even consulted.
   One line, no loss, and it is what
   [08-option-mcp-and-subagent-output.md](08-option-mcp-and-subagent-output.md) already
   recommends for elision — *"size-capped elision applies to results whose content is a plain
   `str`"*. On this corpus it excludes 2,759 results and 32.1% of `tool_result` bytes, which is
   most of what those options were reaching for.
2. **Replace the whole list with a string pointer.** Legal, simple, and it takes the images with
   it. Acceptable for the `Read`-of-an-image half and not for the screenshot half.
3. **Block-wise.** Drop whole `image` blocks, elide inside `text` blocks, keep the list a list.
   §08 names this and correctly says it is *"a real design and it is a larger one than this
   proposal set has argued"*. It also breaks the re-entry guard: invariant I9 holds because the
   filter only ever writes a bare `str`, and a marker written *inside* a list would not be
   recognised by `POINTER_RE` on the next request, so the result would be re-decided and
   re-counted — the double-count `79dd165` records, arriving by a fourth route.

**(1) is the default the code should have today**, because it costs nothing while zero
candidates are structured and it makes the next widening state its choice out loud instead of
inheriting (2) by accident.

## Which constraints it strains

- **§K8** — substitution discipline. Replacing a list with a string keeps the block, the type
  and the `tool_use_id`, so G5 holds; what it does not keep is any of the structure, and §K8
  does not currently say whether it should.
- **§K7** — the ledger records `bytes` from `result_size`, which for a list is the JSON dump.
  A per-block removal would need a per-block accounting, which is the same field
  [05](05-option-truncate-instead-of-drop.md) needs for elision.
- **§K10** — `POINTER_RE`'s `str`-only test (I9) is a closure by scope, exactly like
  `filter.pointer`'s unbounded tool name. Both open at the same moment, and an option that
  widens the rule set owes both.
- **§K1** — none. Shape is a static property of the result.

## What it breaks

Nothing today. The one-line refusal is a no-op on 100% of current candidates, and the test it
owes is a body with a list-form `tool_result` under a name a rule would claim — which no test in
`tests/test_filter.py` constructs, because `res()` (`tests/test_filter.py:36-45`) takes a
`content` that defaults to a string and every call site passes a string.

## The strongest case against

**That this is a guard against a situation that does not exist, written into a component whose
first principle is minimum surface.** Zero candidates are structured. The refusal would never
fire. Adding a branch to `apply` to defend against a widening nobody has adopted is exactly the
kind of speculative generality §K2 charges for by the line.

The reply is that the branch is not the deliverable — the sentence is. The measurement here is
what an option needs in order to be judged: **32.1% of `tool_result` bytes are structured,
19.4% of message content is base64 images, 37% of that is not re-runnable, and the filter's
current safety on all of it is an accident of which four tool names happen to return strings.**
Whether the one-line refusal ships now or with the first widening is a small call. Writing down
that it is a *precondition* rather than a detail is not, because
[06](06-option-per-tool-byte-cap.md) and [08](08-option-mcp-and-subagent-output.md) are both
recommended in part and both aimed squarely at the class that has never been on this code path.
