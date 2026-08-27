# Option F — MCP tool results and delegated-agent output

**Verdict: adopt the size-triggered half through
[06-option-per-tool-byte-cap.md](06-option-per-tool-byte-cap.md), restricted to plain-string
results. Reject a name-pattern rule until something has labelled one.** And read the byte
figures with the correction below, because the largest of them is 78% screenshots.

## What is invisible today

`filter.rule_for` (`filter.py:99-120`) fires on four literal tool names — `Glob`, `LS`, `Grep`
and `Bash`. Everything else returns `None`. So an MCP tool result and an `Agent` result pass
through untouched however large they are, and `winnow inspect` does not see them either, since
`rules._first_matching_rule` matches the same names.

**Measured here, 2026-08-27**, over this container's 866 main-session transcripts:

| Class | Results | Bytes | Share of message content |
| --- | ---: | ---: | ---: |
| all `mcp__*` tools (24 distinct) | 1,860 | 25,458,137 | **9.30%** |
| `Agent` | 342 | 1,790,572 | 0.65% |
| `TaskOutput` | 46 | 487,849 | 0.18% |
| — for comparison, the whole intake filter | 4,709 | 23,229,292 | 8.49% |

**MCP output alone is larger than everything the filter reaches**, and no rule in SPEC §4 has
anything to say about it.

## The correction, before any of that is spent

MCP results are almost never plain text. **1,811 of the 1,860 are list-shaped**, and inside
them are 2,957 `text` blocks and **276 `image` blocks [measured here]**. Those 276 image
blocks carry **19,954,267 bytes — 78.4% of the whole MCP mass, and 7.29% of the corpus's
message content.** Two of the 24 tools produce nearly all of it:
`mcp__claude-in-chrome__browser_batch` (16,080,092 bytes over 178 calls) and
`mcp__claude-in-chrome__computer` (3,874,175 over 104).

`rules.result_size` measures a structured result as `len(json.dumps(content))`
(`rules.py:285-287`), so a screenshot is counted at its base64 length. The vendor prices an
image at roughly width × height ÷ 750 tokens. Decoding the PNG `IHDR` header of the 226 image
blocks that carry one — the JPEG half do not put dimensions at a fixed offset and were not
decoded — gives:

| | |
| --- | ---: |
| PNG image blocks decoded | 226 |
| base64 payload | 29,706,160 bytes |
| SPEC §6's bytes ÷ 4 estimate of their tokens | 7,426,540 |
| vendor formula, width × height ÷ 750 | 268,314 |
| **overstatement** | **27.7×** |

So **MCP's 9.30% byte share is not a 9.30% token share and is nowhere near a 9.30% dollar
share.** The part of it that is comparable with the rest of this proposal set — text blocks —
is **5,489,048 bytes, 2.01% of message content**. The remaining 7.29% is real bytes on the
wire and near-nothing on the bill, which is the reverse of the error
[docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.1, §3.4 and §3.5.2 each record, and is therefore
the direction this project is *not* practised at catching.

This is the single most useful thing in this option file and it is not about MCP: **SPEC §6's
bytes ÷ 4 has a class of content it is wrong about by more than an order of magnitude, and
that class is growing.** DECISIONS §Q2 already asks whether tier B's mass is real in tokens or
an artefact of bytes ÷ 4, and answers *"[t]he direction is unlikely to change; the magnitude
could move several points either way"*. For image content the direction does change.

## What a rule over MCP would look like

Two shapes, and they are not equally defensible.

**(a) A name-pattern rule — the C1 analogue.** `mcp__*__list_*` returns an enumeration whose
only consumer is the call that followed it, which is exactly SPEC §4 C1's rationale for `Glob`
and `LS`. Reach, **measured here**: tool names containing `__list_` are **4,567,298 bytes,
1.67% of message content, over 618 calls** — `mcp__uf__list_templates` (1,850,481 over 122
calls, mean 15,168), `mcp__uf__list_runs` (1,170,109), `mcp__uf__list_folders` (1,155,735),
`mcp__uf__list_agents`, `mcp__uf__list_workflows`.

**Its precision is unknown, and it is *less* knowable than C1's.** SPEC §4's rules rest on tool
semantics the vendor defines: `Glob` returns paths, `Grep --output_mode files_with_matches`
returns paths, `is_error: false` on `pytest` means it passed. An MCP tool's name is a string
chosen by whoever wrote the server, and `list_templates` returning 15 KB is as likely to be the
catalogue the session works from for the next hour as it is to be a locator. There is no
contract, only a convention, and a rule built on a naming convention **fires on tools it has
never seen** — which is the property that makes it attractive and the property that makes it
dangerous.

SPEC §9's bar for a rule is *"≥90% of stripped results confirmed once-only by a human reading
the surrounding turns"*, 200 samples stratified by rule, and MILESTONES' kill criterion is
aggregate precision below 80%. **That study has not been run for the six rules that do have a
vendor contract behind them.** `rules.DISABLED_BY_DEFAULT` ships empty and stays empty *"until
the 200-sample blind label has been scored"* (`rules.py:106-118`), on the argument that a rule
switched off without a number is the tool asserting a precision nobody measured. Switching one
*on* without a number is the same assertion in the expensive direction.

**Reject (a)**, for 1.67% of message content, until it has been labelled. The labelling is
cheap and the harness exists: `src/winnow/validate/` already has the sampler, the sheet and the
scorer, and `docs/MILESTONE-2-VALIDATION.md` is the procedure.

**(b) A size cap, with no semantic claim at all.** This is
[06-option-per-tool-byte-cap.md](06-option-per-tool-byte-cap.md) pointed at MCP, and the
measured reach is **19,859,186 bytes elidable above 8 KB, 7.26% of message content, over 536
results** — of which the great majority is, again, screenshots.

**Adopt (b), with one restriction that (06) does not state and this class forces.**

## Elision does not work on a structured result, and MCP is where they are

`filter.apply` writes a bare string over `block["content"]` (`filter.py:288`), which is legal
whatever the original shape was — the API documents `tool_result.content` as a string or a
list of blocks. Head/tail elision is different: **you cannot cut the middle out of
`json.dumps(list_of_blocks)` and get valid content back.** An elision on a structured result
has to be a different operation — elide inside individual `text` blocks, and take whole `image`
blocks or leave them — and cutting a base64 image in half does not produce a smaller image, it
produces a corrupt one.

So the restriction is: **size-capped elision applies to results whose content is a plain
`str`.** On this corpus that is 61,787 of the 64,546 results whose content shape was counted —
and only **49 of 1,860 MCP results**, which means the cap reaches essentially none of the MCP
mass under the safe rule.
The alternative for a structured result is block-wise: drop whole `image` blocks (a
substitution, keeping the block list valid), elide inside `text` blocks. That is a real design
and it is a larger one than this proposal set has argued, and it should be named as such rather
than folded into (06) by implication.

## Sub-agents: three different things called one name

[docs/SPEC.md](../../docs/SPEC.md) §3 puts sub-agent transcripts out of scope on the grounds
that there were "0 sidechain records in 563 transcripts". COZEMPIC §3.4 already corrected the
premise — the corpus now holds transcripts under `<session-id>/subagents/` that did not exist
when SPEC measured. On this container: **1,729 `*.jsonl` in total, 866 main sessions, 352 files
under `*/*/subagents/` [measured here]**. Three distinct things follow and they get confused.

**1. The `Agent` tool result in the parent.** This *is* on the wire and *is* in the parent's
transcript: 342 results, 1,790,572 bytes, 0.65% of message content, 853,484 of them elidable
above 8 KB. It is reachable today and nothing reaches it.

It is also the worst candidate for removal in this proposal set. A delegated agent's return
value is a summary the parent explicitly asked for, produced by discarding the sub-agent's own
context — it is the *output* of a compression the harness already performed, and `[[Sub-Agent
Architectures]]` is cited in SPEC §2 as the vendor's own recommendation for exactly this. A
rule that strips it is stripping the one thing in the conversation that was already selected
for durability. **No rule should claim `Agent` results.** A size cap on the 69 of them over
8 KB is arguable; a semantic rule is not.

**2. The sub-agent's own conversation, which the filter is already filtering.** A sub-agent is
a Claude Code session making its own API requests, and it inherits `ANTHROPIC_BASE_URL` from
its parent's environment. **The intake filter therefore already applies to sub-agent traffic,
today, and nothing in the design says so.** Nothing needs to change for that to be true, and
`keep_newest = 1` is being applied to conversations whose shape nobody has looked at.

**3. And `winnow savings` cannot see any of it.** `savings.find_transcripts`
(`savings.py:295`) globs `projects_dir.glob("*/*.jsonl")` — main sessions only. A ledger line
written for a sub-agent's request joins to nothing and lands in the "unjoinable" bucket.
[docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5.2 reports **"34 priced, 15 unjoinable, 0
unpriceable"** on the one real ledger — roughly three joins in ten failing, on the reading that
makes its own arithmetic work, since 34 + 15 is that ledger's 49 unique removals rather than
its 403 lines. This glob is a candidate explanation nobody has checked.
The check is one line — widen the glob to `**/*.jsonl` and see whether the unjoinable count
falls — and it is a measurement, not an option, so it is recorded here rather than proposed.

## Which constraints it strains

- **§K1** — none for (b): size is static. None for (a) either: a tool name is fixed at the
  moment the call is made. Both are admissible; (a) fails on evidence, not on cache stability.
- **§K10** — this is the option that re-opens the pointer's tool-name hole.
  [01-constraints.md](01-constraints.md) §K10 shows `filter.pointer` interpolates a name
  unbounded and is safe today only because `rule_for` fires on four literals. An MCP tool name
  is operator-configured, arrives on the wire, and reaches the model. `rules._safe_tool_name`
  becomes mandatory in the same change.
- **§K7** — the ledger's `by_rule` breakdown in `inspect.FilterLedger` (`inspect.py:118-120`)
  is keyed on rule ids. A new rule needs an id, and an id outside `rules.RULE_ORDER` is a
  seventh rule the rest of the tree does not know about — the disagreement `rules.py`'s module
  docstring exists to prevent.

## What it breaks

**SPEC §4's rule table stops being a closed set.** Six rules over vendor-defined tools is a
thing an operator can read and argue with (DECISIONS §D6). A rule over `mcp__*__list_*` is a
rule whose population changes when the operator adds a server, and whose measured precision
therefore describes one install's servers rather than the mechanism. Every share this project
reports would become install-specific in a way it currently is not.

## The strongest case against the whole option

**That the number is a mirage and this corpus is the reason it looks big.** MCP is 9.30% of
message content here because this operator runs a browser-automation server; strip the two
`claude-in-chrome` tools and the entire MCP mass is 5,347,407 bytes, **1.95% of message
content**, spread over 22 tools none of which is individually worth a rule. The 7.26%
"elidable above 8 KB" is 78% screenshots, whose token cost bytes ÷ 4 overstates by 27.7×, so
in the unit that actually gets billed the prize is somewhere near a tenth of what the byte
table implies.

Against a filter that reaches 8.49% and is worth +3.76% of a bill, an option whose honest
token-weighted reach is around two points of *bytes* is not obviously worth a new rule class,
a `_safe_tool_name` audit, a block-wise elision path for structured content, and a precision
study that has not been run for the rules already shipping. **The measurement is the
deliverable here, not the rule.** What this file establishes is that the byte figures for MCP
cannot be read the way the rest of the table is read — and that is worth knowing whether or
not anything is ever built.
