# Option J — a readout of the fixed prefix

**Verdict: take it, and take it first.** It is the only option in this set that rewrites
nothing, and it is the only one that looks at the part of the request everything else in the
bill stands behind. It is also the only capability in this set that **nothing else in the
world can provide**, because the bytes it reports exist nowhere but on the wire.

## What it is

A Messages API request carries three things above the conversation: `system`, `tools` and the
model. `filter.apply` reads `body["messages"]` and `body["model"]` and never looks at the other
two (`filter.py:237-245`). They are in the same parsed dict, already in memory, already
`json.loads`-ed by `_rewrite` (`proxy.py:167`).

The proposal is to measure them and say so. No rewrite, no rule, no breakpoint. A report.

## Why nothing else can do it

**Measured here, 2026-08-27:** across every record of all 866 main-session transcripts on this
container — nineteen distinct record types, led by 103,653 `assistant`, 66,887 `user` and
38,917 `attachment` — **zero carry a system prompt or a tool definition.** The check was for any
record holding a `system`, `tools`, `systemPrompt` or `toolDefinitions` key, and it found none.
(There is a record type *called* `system`, 927 of them, and it is not one: its subtypes are
`turn_duration`, `stop_hook_summary`, `compact_boundary`, `local_command`, `api_error` and
`informational`, and the longest such record in the corpus is 2,618 bytes.)

That is not an accident of this corpus. Claude Code writes the *conversation* to disk; the
system prompt and the tool schemas are constructed at request time from the CLI's own
configuration, the project's `CLAUDE.md`, the loaded plugins and every connected MCP server.
`winnow inspect` cannot see them. `winnow plan` cannot price them. `winnow savings` and
`winnow trial` both read `message.usage`, which counts them and never says what they were.
**The only process in this tree that has ever held those bytes is the proxy, and it throws
them away.**

## What is standing behind them

The invalidation cascade runs tools → system → messages (`[[Prompt Caching]]`, high, via
SPEC §7). The fixed prefix is not merely first in the request; **it is first in the cache
key**, so one changed byte in a tool definition invalidates the system prompt and the entire
conversation behind it.

**Measured here**, on this container's 866 main sessions and 48,835 API requests:

| | |
| --- | ---: |
| cache-read tokens | 8,817,146,116 |
| …billed at 0.1× | $4,409 |
| …the same volume as fresh input, 1.0× | $44,086 |
| …the same volume as one-hour writes, 2.0× | $88,171 |
| one-hour cache **write** tokens | 188,899,673 ($1,889) |
| output tokens | 45,036,920 ($1,126) |
| uncached input tokens | 1,223,999 ($6) |
| **total** | **$7,426.47** |

**The prompt cache is worth 5.3× this corpus's entire bill** — $39,677 avoided against $7,426
paid — which reproduces `ContextControl/17-`'s "about 5.5×" on this operator's weekly figures,
quoted in SPEC §1, from a different population and a different year. Against the write class
rather than fresh input it is 11.3×.

**Every dollar of that stands behind bytes nobody in this repository has ever counted.**

And the price of disturbing them is already on the record, twice. SPEC §3 and
[README.md](../../README.md#what-it-is-not) both carry `ContextControl/12-`'s figure: one added
tool definition costs **$8.14–$8.26 a week** on this operator's install, against **$0.14** of
benefit per use. That number is the entire reason this project refuses an MCP server. It has
never been checked against a live request, and the readout is the thing that would check it.

## What it would report

Four things, each of which is one line and none of which requires a rewrite.

**1. The size of the fixed prefix, split.** `len(json.dumps(body["system"]))`,
`len(json.dumps(body["tools"]))`, and a per-tool breakdown by `name`. That answers "what does
one tool definition actually cost here" directly, in the unit `ContextControl/12-` estimated.

**2. Where the breakpoints are.** [01-constraints.md](01-constraints.md) §K4 records that the
filter's whole mechanism is drawn against a budget of four `cache_control` markers it does not
own, and that when the budget is full the filter silently declines to move one
(`filter.py:296-297`, `plan.breakpoint_moved = False`). **No figure exists anywhere for how
often that happens.** The client may place breakpoints on the system prompt and the tool list
as well as in the messages, and `_count_breakpoints` (`filter.py:164-171`) only counts the ones
in `messages` — so the filter's own cap check may already be wrong in the permissive direction,
against an API limit whose violation is a 400. This readout is what would say.

**3. Whether the prefix is stable.** Hash `system` and `tools` per request; emit a line only
when the hash changes. A stable prefix produces one line per session and nothing more. **An
unstable one is the most expensive thing that can happen to a Claude Code install and is
completely invisible today**: a tool description carrying a timestamp, an MCP server that
returns its tool list in a different order each connection, a `CLAUDE.md` re-rendered with a
changing directory listing — any of them invalidates the whole prefix on every request, and the
only symptom is a bill.

The magnitude is the table above: a prefix that never matches turns that $4,409 read line into
an $88,171 write line. Nothing in this repository, in Claude Code, or in the vendor's own
reporting would tell an operator it was happening. That is the single strongest argument for
this option and it does not depend on the filter existing at all.

**4. What changed, when it changed.** A diff at the granularity of tool names and byte counts
— *"`tools` grew by 1,204 bytes; `mcp__uf__propose_run` added"* — is enough to attribute a
prefix break to the thing an operator did that morning.

## What it costs

**Nothing on the request path.** The body is already parsed. Three `len(json.dumps(...))` calls
and a `hashlib.sha256` over two sub-objects, on a dict that is about to be re-serialised
anyway. No new socket, no new file handle if the line goes into the existing ledger, no
buffering, no rewrite, and a failure has no consequence beyond a missing line.

**One piece of state, and it is the reporting kind.** The previous request's prefix hash lives
in memory so that a line is emitted only on a change. [01-constraints.md](01-constraints.md)
§K1 and §K10 constrain the bytes *sent*; this state never reaches them, and losing it on a
restart produces one redundant ledger line rather than an invalidation. That distinction is
worth stating explicitly, because [03-option-hindsight-rules-at-a-paid-boundary.md](03-option-hindsight-rules-at-a-paid-boundary.md)
is rejected on exactly the opposite case — state whose loss changes what is sent.

## Which constraints it strains

- **§K1, §K4, §K7, §K8** — none. It changes no byte and takes no breakpoint.
- **§K2 — this is the one, and it is not small.** A system prompt is the operator's
  `CLAUDE.md`, their project instructions, their environment, and whatever their plugins
  inject; MCP tool descriptions are written by whoever wrote the server. SPEC §10 is already
  emphatic that transcripts *"routinely contain credentials pasted into a Bash command"* and
  that winnow *"must never write a log file by default"*, and `--explain` carries a warning for
  content strictly less sensitive than this.

  So the readout must report **sizes, names and hashes, and never content**, by default; a
  content dump belongs behind the same kind of flag `--explain` is, with the same warning
  attached. A tool *name* is already the least of it and even that reaches an operator's own
  MCP configuration.
- **§K5** — where the lines go. They should go in the existing ledger rather than a second
  file: one artefact, already documented, already read by two commands. A prefix line needs a
  discriminator field so `savings.read_ledger` (`savings.py:164`) and
  `inspect.read_filter_ledger` (`inspect.py:236`) skip it — and both currently key off fields
  they expect to be present rather than off a type tag, so this is a real compatibility
  question and not a formality.

## What it breaks

**It makes `winnow inspect`'s denominator visibly incomplete.** Every share this project
reports is against *message content*, and SPEC §6's method says so. Once the fixed prefix has a
measured size, the honest denominator for "what fraction of the request is this" changes, and
so does `T*`: `S` in `T* = 19·(S/D) − 20` is the suffix after the cut, but the *prefix* the cut
sits behind includes the tools and the system prompt, which are never counted. Whether that
moves any published number is not derivable until the readout has run once — which is rather
the point of running it.

**And it will produce a number somebody has to act on.** If the tool definitions turn out to be
40 KB on this install, the honest response is not a winnow feature; it is fewer MCP servers.
That is a good outcome and it is worth saying out loud that the most likely payoff of this
option is a recommendation to remove something rather than to add one.

## The strongest case against

**That it is not the intake filter, and putting it here is scope creep into the credential
path.** Every other option in this set changes what the filter removes. This one changes
nothing and reports on a different subject, and it is in `proxy.py` only because `proxy.py`
happens to be where the bytes go past. A reviewer is entitled to say that a measurement tool
belongs in a measurement command, and that DECISIONS §D7's discipline — winnow stays out of the
spawn path, out of the failure path, out of everything it does not have to touch — argues for
the smallest possible thing in the one process that sits in front of an API key.

The reply is that there is no other process. The bytes are not on disk (zero records in 866
transcripts), they are not in `usage`, and they are not obtainable without standing on the
wire. DECISIONS §1's decision for this whole project is *"build the instrument, gate the
actuator behind its own measurement"*, and this is the only instrument in the set: it is the
one option here that produces a number rather than spending one. The filter is already in the
credential path for the sake of a +3.76% rewrite; declining to *look* at the 5.3×-of-the-bill
that the same request is carrying, while it is already parsed and in memory, is a strange place
to draw the line.
