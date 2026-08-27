# Constraints

Ten constraints. Every option in this set is judged against them, and each option file names
the ones it strains. K1 is not one constraint among ten — it decides most of the set on its
own, and the first half of this document is about stating it correctly, because
`filter.py`'s own docstring states it in a way that is convenient and wrong.

---

## K1 — the same conversation must always render to the same bytes

**The requirement.** Cache matching is exact and prefix-ordered ([[Prompt Caching]], high,
via [docs/SPEC.md](../../docs/SPEC.md) §7). If the filter renders block *X* one way on
request *t* and another way on request *t′* > *t*, and *X* was inside the cached prefix at
*t*, then at *t′* the match breaks at *X* and everything after it is re-written at the full
2.0× write class. That is `1.9·S` — the pruner's cost, arriving mid-session on a warm cache,
which is the single thing this component exists to avoid.

`src/winnow/filter.py:18-22` states it: *"a policy whose output varied between two requests
over the same conversation would change the prefix under the cache and destroy the thing it
exists to protect."* That is right. What follows it is not.

### The reframing: it is not hindsight, it is direction

`src/winnow/filter.py:24` says the filter can run "[o]nly the rules that need no hindsight",
and `rule_for`'s docstring (`filter.py:100-107`) repeats it: C2 "needs a later duplicate", B1
"a later read", A1 "a later edit". The conclusion is correct and the reason given for it is
not, and the difference matters because several capability options stand or fall on which
reason is the real one.

**Hindsight is available.** Every earlier turn of the conversation is in the request body.
Claude Code sends the whole message list on every request; `_index_tool_uses`
(`filter.py:128-142`) already walks all of it. A duplicate call is visible. A superseded read
is visible. `winnow.rules._first_matching_rule` (`rules.py:453-520`) computes all six rules
from exactly this material and needs nothing the proxy does not have. The filter could
evaluate C2, B1 and A1 today, from the bytes in front of it, with no store and no transcript.

What disqualifies them is that their answer **changes partway through a session**. Write
*t*₀(*R*) for the first request that carries result *R*. Because Claude Code appends, *R* and
everything before it appear in every request from *t*₀ onwards. Then:

- C1, C3 and B2 read only the tool name, the tool input and `is_error` — all fixed when *R*
  is written. Their verdict is the same at *t*₀ and at every request after it.
- C2, B1 and A1 read turns that come *after* *R*. Their verdict is **false at *t*₀ and becomes
  true later**. Firing at that point replaces bytes the cache already holds.

So the disqualifier is not a missing fact. It is that the rule *turns on*, and by the time it
does, the bytes it wants to remove are cached.

### The test, stated once

> **A rule may fire on a result only if it would have fired on every request since that
> result first appeared.**

Equivalently, and this is the form worth checking an option against: **a rule's verdict on
*R* must be determined by the conversation up to and including *R*.** The two are the same
statement. At *t*₀ nothing after *R* exists, so a verdict that is constant from *t*₀ onward is
already fixed by *R*'s own prefix; and conversely a verdict fixed by *R*'s prefix cannot move,
because that prefix does not change.

Call it **monotonicity** or prefix-determinism; the name matters less than that it is
*stricter and more useful* than "no hindsight". Stricter, because it rules out things that
have nothing to do with the future — a verdict that depended on the wall clock, on how many
requests the proxy had seen, or on a file on disk would also fail it, and "no hindsight" says
nothing about any of those. More useful, because it says what an option *may* do: the entire
past is fair game.

### Three refinements, all of which an option can trip over

**(a) The past the filter reads is a past the filter is rewriting.** A rule keyed on an
earlier `tool_result`'s *content* is not prefix-determined, because that content is itself
something the filter changes — full at *t*₀, a pointer at *t*₀+1. The material that is
genuinely stable is what the filter never touches: every `tool_use` block and its input
(guaranteed by SPEC §4's opening sentence and DECISIONS §D3), `is_error`, the pairing, and the
result's own content on the request being decided. The pointer does preserve the tool name,
the rule and the byte count (`filter.py:93-96`), so a rule keyed on earlier *sizes* could be
made stable — nothing does that today, and an option that wanted to would have to say so and
prove it.

**(b) The filter already does one non-monotone thing, and it is the deferral.**
`exempt_from = len(results) - keep_newest` (`filter.py:275`) depends on how many results come
*after* *R*. That is a suffix dependency, and by the test above it is inadmissible. It is
admissible in fact for one reason: its only transition is exempt → not exempt, which is
full bytes → pointer, and `_place_breakpoint_before` (`filter.py:174-195`) guarantees the full
rendering sat *after* the last breakpoint and was therefore never written. **The rule is not
"the bytes never change"; it is "the bytes never change once they have been cache-written",
and the filter buys its one exception by controlling where the prefix ends.** Any option that
wants a second non-monotone transition has to buy it the same way, and the four-breakpoint cap
(K4) is the budget it buys it out of.

**(c) The mirror rules pass K1 and fail on the merits.** C2, B1 and A1 each have a
prefix-determined mirror image: strip the *later* duplicate instead of the earlier one, the
later read instead of the earlier, the read taken *after* an edit instead of before. Each
fires at *t*₀ and never changes, so each satisfies K1 exactly. Each is also wrong, and wrong
in the same direction: **it keeps the stale answer and discards the fresh one.** Two
`git status` calls with identical input do not have identical output. A file is re-read
*because* something changed. A1's entire rationale (SPEC §4) is that the pre-edit bytes are
the stale ones. This is worth writing down because the mirror is the natural first idea after
the reframing, and it is worse than doing nothing: losing bytes costs a re-fetch, retaining a
superseded answer costs a wrong one.

### What K1 leaves open

Everything determined by the call, its own result, and the conversation before it. That is a
larger space than "static properties of one call" — "the fourth `git status` in this
conversation", "a `Read` of a path already read", "cumulative Bash output so far" are all
admissible in principle. The options below that survive are the ones in that space; the ones
that die, die here.

---

## K2 — it is in the credential path

The proxy relays the client's own auth headers upstream (`proxy.py:218-223`), holds none of
its own, and logs none — `log_message` is overridden to silence the access log precisely so
that request lines carrying session identifiers never reach stderr (`proxy.py:200-202`). It
refuses to start without `WINNOW_FILTER=1` (`cli.py:626-629`), for the same reason
orchestrator-safe mode refuses: a process that quietly inserted itself between a session and
its credentials would be indistinguishable from one that was asked to.

The constraint this places on an option is not "do not touch the headers". It is that **every
line added to this process is a line running beside a live API key**, so an option is charged
for its surface area and not only for its behaviour. Reading a response body, holding a
store, or opening a second socket are all larger charges than they look.

## K3 — no model call, no network of its own, no MCP server, stdlib only

[docs/SPEC.md](../../docs/SPEC.md) §3 puts summarising, ranking, scoring, embedding and any
model call out of scope; §10 says "[n]o network". The proxy is the one component that makes an
HTTP request, and it makes exactly the one the client asked for.

The MCP prohibition is priced rather than stylistic: one added tool definition sits at the top
of the invalidation cascade and was costed at **$8.14–$8.26 a week** against $0.14 of benefit
per use (`ContextControl/12-`, quoted in SPEC §3 and README).

Stdlib only is likewise a recorded commitment rather than taste. `proxy.py:8-10`: adding an
HTTP client "would retire the 'zero external dependencies' claim that `COZEMPIC.md` §4
checks". `pyproject.toml:29-37` records the package's one dependency, `psutil`, and it exists
for the legacy guard's PID-identity check — nothing the CLI's own commands reach. An option
needing a tokeniser, a diff library, an HTTP client or a database is asking for that claim to
be retired and has to say so in those words.

## K4 — four `cache_control` breakpoints, and the filter is spending one

The API caps `cache_control` breakpoints per request; adding one without removing another
turns a working request into a 400 (`filter.py:57-59`, `MAX_BREAKPOINTS = 4`). The filter's
mechanism *is* a breakpoint move, so its central operation is drawn against a budget of four
that the client is already using.

`apply` handles this by stripping every breakpoint at or after the candidate first
(`filter.py:295`), counting what is left, and placing a new one only if there is room
(`filter.py:296-297`). When there is not, it drops the older candidates and **leaves the
newest one where it is** — so on a full request the deferred result is cache-written after
all, and the saving on that one result is lost rather than the request being broken.
`test_the_filter_never_pushes_a_request_over_the_breakpoint_cap` is the guard.

Two consequences for options. First, **any option that wants a second cut point in the
request wants a second breakpoint**, and there may not be one. Second, the failure is
silent-but-safe: the plan records `breakpoint_moved = False` and the ledger says so, but
nothing tells the operator how often it happens. No figure for that exists.

## K5 — no fourth store

[docs/SPEC.md](../../docs/SPEC.md) §3: a database, index or content store is "a fourth store"
and is forbidden — "it would need its own retention horizon, liveness query and storage
accounting. Winnow's only persistent state is the forked transcript itself." `rules.py:565-568`
leans on the same refusal to justify the pointer-ID scheme.

The line has already moved once and an option should argue against where it actually is, not
where SPEC §3 wrote it. Winnow now persists three things of its own: the filter's ledger
(`~/.winnow/filter.jsonl`), `winnow trial`'s arm ledger, and the fork. All three are
*append-only records of what happened*, none is queried to decide anything, and none has a
retention horizon because none is ever read for content. **The refusal that survives is of a
store the tool reads back to answer a question**, which is exactly what a recall store would
be, and the option proposing one is judged against that reading rather than the literal
sentence.

## K6 — it must never be the thing that breaks a run

`proxy._rewrite` (`proxy.py:159-192`) forwards the original bytes on an unparseable body, on a
body that is not an object, and on any exception the filter raises — with a bare
`except Exception` carrying an explicit `noqa` and the reason (`proxy.py:177`). Three tests
hold it. The kill switch is a file the operator touches (`proxy.py:126-156`), checked per
request, and it stops the *rewriting* while the socket stays open, because
`ANTHROPIC_BASE_URL` is fixed in a client's environment at spawn and a listener that goes away
takes every request with it.

The constraint on an option: **whatever it adds has to have a passthrough.** A capability that
cannot be abandoned halfway through a request, or that leaves the request in a half-rewritten
state when it fails, does not belong in this process however good its arithmetic is.

## K7 — the ledger, and the double-count it exists to stop

The filter never touches the transcript. Claude Code writes what it holds, which still
contains every byte the API never saw. So `winnow inspect` read off disk overstates both *D*
and *S* for a filtered session, and `winnow fork` would pay `1.9·S` to remove bytes that are
not in the prefix — the double-count `79dd165` recorded for the pruner, arriving by a new
route ([docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5). `ledger_line` (`filter.py:319-347`)
is the correction, joined to the transcript on `requestId`, which is the only key both sides
hold: the filter sees a Messages API body and a body carries no session identity.

Two things follow for an option.

**Anything the filter removes must be recorded, per result, with an identity.** `_entry`
(`filter.py:301-316`) carries `tool_use_id` for exactly this: the filter is stateless, so it
re-drops the same result on every later request that still carries it, and summing
`bytes_dropped` over lines overstated one real ledger by **27.2×** — 1,283 removal events,
49 distinct results (§3.5.1). An option that removes bytes by a route the ledger does not
describe reintroduces that error.

**And the ledger's own reader is not de-duplicated.** `inspect.read_filter_ledger`
(`inspect.py:236-271`) sums `record["bytes_dropped"]` over every line that joins to the
session, with no `tool_use_id` collapse — the exact sum §3.5.1 says is wrong by 27.2×, feeding
`wire_content_bytes` (`inspect.py:152-162`), which clamps at zero. `savings.read_ledger`
(`savings.py:164-174`) does de-duplicate. The two readers of the same file disagree, and no
test covers a repeat: `test_the_ledger_is_joined_on_request_id`
(`tests/test_inspect.py:517-540`) uses one line per session. **This is stated here as a
constraint an option must not make worse, not as a proposal — it is a defect in existing code
and fixing it is a separate change with its own tests.**

## K8 — substitution, not deletion

The Messages API requires every `tool_use` to be answered. A dropped result has its `content`
replaced by a pointer; the block, its `type` and its `tool_use_id` all survive
(`filter.py:288`), which is guard G5 holding by construction rather than by check —
`test_pairing_is_preserved_because_content_is_replaced_not_removed` asserts it. The pointer is
deliberately shorter than the pruner's and carries **no `winnow recover` command**
(`filter.py:85-96`), because the filter keeps no copy and saying otherwise would be a promise
nothing there can keep.

Guard G2's floor is the corollary: below `min_bytes` the pointer costs more than the content
(`filter.py:46-48`), and G4 would refuse the strip anyway. Any option that changes what
replaces a result has to keep the block, keep the pairing, and stay under the size of what it
replaced.

## K9 — the response is streamed, not buffered

`proxy._relay` reads the upstream in 8,192-byte chunks and writes each one out chunked and
flushed (`proxy.py:240-246`), so a streamed `message_delta` reaches Claude Code at the time it
would have without the proxy in the path. `content-encoding` and `accept-encoding` are
dropped from the relayed headers (`proxy.py:48-57`) so the upstream never compresses a stream
that has to be forwarded verbatim. `test_the_response_streams_through_intact` is the guard.

This is the constraint the "read the response" option runs into, and it is sharper than it
sounds: **the first token of a reply must not wait for the last.** Anything that inspects a
response has to do it without holding one.

## K10 — determinism, loud failure, and an untrusted input

[docs/SPEC.md](../../docs/SPEC.md) §10, and three parts of it reach this component.

**Determinism.** The same conversation produces the same bytes. This is K1 restated from the
other end, and it is why the filter is a pure function of the request body: no clock, no
counter, no random source, no map iteration order.

**No silent fallback.** "[T]here is no fallback that silently keeps a result the operator
asked to strip, and none that silently strips one they did not." The filter has one soft
edge already — the breakpoint cap in K4 — and it is worth not adding more.

**The request body is untrusted input.** SPEC §10 makes the control point "everything that
consumes a sandboxed agent's output", and the proxy is such a consumer for a body that
contains tool results this session did not produce. The pruner bounds this explicitly:
`rules._safe_tool_name` (`rules.py:624-635`) reduces a tool name to 64 characters of
`[A-Za-z0-9_.-]`, because a name carrying a newline would forge a second pointer line and one
carrying 40 KB would defeat G4.

**`filter.pointer` (`filter.py:93-96`) does not do that, and is safe anyway — for a reason
that is a property of the rule set rather than of the pointer.** It interpolates
`{tool_name}` straight into its text with no bound. What closes the hole is that a pointer is
only ever written when `rule_for` returned a rule (`filter.py:288`), and `rule_for`
(`filter.py:99-120`) returns non-`None` only for the literal names `Glob`, `LS`, `Grep` and
`Bash`. The name reaching `pointer()` is therefore always one of four fixed strings.
Confirmed by construction: a `tool_use` named `"Glob\n[winnow: forged"` matches no rule, so
its result is never rewritten.

That is a closure by coincidence of scope, and it is worth naming because **the first option
that widens the rule set past those four names re-opens it.** An MCP tool name is
operator-supplied, arrives on the wire, and would flow unbounded into a pointer the model
reads. Any option that widens `rule_for` owes `_safe_tool_name` — or its own equivalent — in
the same change.
