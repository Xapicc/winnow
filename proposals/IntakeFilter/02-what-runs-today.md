# What runs today

The mechanism as built, at the level of detail an argument about changing it needs. Nothing
here is a proposal. Everything is a file and a line number in this checkout, and the last
section states the invariants the code depends on and does not name.

## The surface

```sh
export WINNOW_FILTER=1
python -m winnow filter --ledger ~/.winnow/filter.jsonl
export ANTHROPIC_BASE_URL=http://127.0.0.1:8789
```

`cli.cmd_filter` (`cli.py:625-639`) refuses with exit 3 unless `WINNOW_FILTER=1` or `--force`.
Settings come from the environment through `proxy.config_from_env` (`proxy.py:310-330`) and
are overridden by flags: `--port` (default 8789, chosen because UsageFoundry's Discord relay
already holds 8787 in the same container, `proxy.py:40-43`), `--upstream`, `--min-bytes`
(2,048), `--keep-newest` (1), `--ledger`, `--off-file`, `--verbose`.

`proxy.serve` (`proxy.py:280-307`) runs a `ThreadingHTTPServer` on `127.0.0.1`, prints the
`export` line an operator needs, creates the kill switch's parent directory so the documented
`touch` works, and on exit prints a stats line. `do_POST`, `do_GET` and `do_DELETE` are all
`_relay` (`proxy.py:257-259`).

Only `/v1/messages` is rewritten. `_is_filtered` (`proxy.py:66-73`) is an **exact** match on
the path with the query string discarded, deliberately not a prefix test:
`/v1/messages/count_tokens` starts with `/v1/messages`, and filtering it would make the count
disagree with the request it counts. Everything else — models, files, batches — is a straight
relay.

## `rule_for` — the three rules, exactly

`filter.rule_for` (`filter.py:99-120`) takes `(name, tool_input, is_error)` and returns
`"C1"`, `"C3"`, `"B2"` or `None`. It is deliberately **not**
`rules._first_matching_rule`, which also answers C2, B1 and A1.

```
is_error is True                                     → None      (G3; and for C3 the failure is the information)
name in {"Glob", "LS"}                               → "C1"
name == "Grep" and output_mode in
        {"files_with_matches", "count"}              → "C1"
name == "Bash" and VERIFICATION_RE.search(command)   → "C3"
name == "Bash" and is_inspection(command)            → "B2"
otherwise                                            → None
```

The constants are `rules.LOCATOR_TOOLS`, `rules.LOCATOR_GREP_MODES` (`rules.py:51-52`),
`rules.VERIFICATION_RE` (`rules.py:56-70`: `npm|pnpm|yarn|bun` with an optional `run`,
`pytest`, `go`, `cargo`, `tsc`, `eslint`, `make`, `jest`, `vitest`, `ruff`, `mypy`) and
`rules.is_inspection` (`rules.py:343-351`) over `INSPECTION_HEADS` and
`INSPECTION_GIT_SUBCOMMANDS` (`rules.py:75-83`).

`is_inspection` matches on `bash_head` (`rules.py:313-340`), which is the first token of the
first segment before `&&` or `|`, with three normalisations: a leading `VAR=value` is skipped
so `FOO=1 ls` is still an `ls`; a path is reduced to its basename so `/bin/ls` is `ls`; and
`git` and `sed` take a two-token head, so `git status` matches and `git push` does not. `;` is
deliberately not a separator, because SPEC §4 named two. Ordering matters: C3 is tested before
B2, so `Bash` running `pytest` is C3 and `Bash` running `cat` is B2, matching
`RULE_ORDER`'s first-match-wins.

**What this reaches, measured on this container's 866 main-session transcripts, 2026-08-27:**
B2 is 22,317,415 bytes (8.15% of message content), C3 is 841,148 (0.31%) and C1 is 70,729
(0.03%). C1 and C3 together are 4.0% of what the filter removes. The intake filter is rule B2.

## `apply` — one pass over one body

`filter.apply(body, min_bytes=2048, keep_newest=1)` (`filter.py:226-298`) mutates the body in
place and returns `(body, Plan)`. In order:

1. **Bail out** if `body["messages"]` is not a list. `Plan()` is unchanged, `plan.changed` is
   `False`, and the proxy forwards the original bytes.
2. **Record `model` and `cache_ttl`.** Neither decides anything. `_ttl_in_force`
   (`filter.py:198-209`) answers `"ephemeral_1h"`, `"ephemeral_5m"` or `None` — `None` when
   the request carries no breakpoint at all, because a request with no write class should say
   so rather than default to one. The names are `usage.cache_creation`'s own keys so the
   ledger and the transcript compare without a mapping.
3. **Index every `tool_use` by id** (`_index_tool_uses`, `filter.py:128-142`), flat over the
   whole message list, `id → (name, input)`.
4. **Walk every `tool_result` in wire order**, count it into `tool_results_seen`, skip it if
   its content already carries a pointer (below), look its `tool_use` up by `tool_use_id`,
   compute `rule_for` and `result_size`, and append to `results`.
5. **Candidates** are results with a rule and `size >= min_bytes`. No candidates, no change.
6. **Exempt the newest `keep_newest`** — see the deferral, below.
7. **Non-exempt candidates are pointered**: `block["content"]` is replaced,
   `cache_control` is popped off the block (`filter.py:289`), and a ledger entry is appended.
8. **If any exempt candidate was seen**, move the breakpoint in front of the last of them.

`result_size` is `rules.result_size` (`rules.py:285-287`) — SPEC §6's measure, `len()` of the
string or of `json.dumps()` for a structured result, so the filter, `inspect`, `plan` and
`fork` all count the same thing.

## The `keep_newest` deferral

```python
exempt_from = len(results) - keep_newest
exempt_ids = {id(results[i][2]) for i in range(max(0, exempt_from), len(results))}
```
`filter.py:275-276`.

The exemption is counted over **all** results, not only candidates, so a candidate two calls
back is dropped even when the two after it are not. `keep_newest = 1` is the design and not a
tuning parameter: a candidate is sent uncached on the request where the model acts on it and
dropped on the next, and the guarantee "cheaper from the first request" holds at 1 and becomes
a trade above it, because the uncached tail is re-sent at 1.0× on every request it survives
(`filter.py:50-55`).

Two properties of this that the docstring does not state.

**The exempt candidate is the *last* one, not each of them.** The loop over `candidates`
overwrites `newest_candidate` on each exempt candidate it sees (`filter.py:279-286`), so with
`keep_newest > 1` the breakpoint lands in front of the latest exempt candidate and everything
after it — including results no rule claims — falls out of the cached prefix for that request.
Checked: with `keep_newest=2` over three Bash turns whose last result is not a candidate, the
breakpoint moves to the assistant message carrying the second call and the third result's
3,000 bytes are sent uncached. Raising `keep_newest` therefore costs 1.0× on bytes the filter
was never going to remove, which is a cost the constant's own comment describes only for the
candidates.

**"The request where the model acts on it" is true per result, not per turn.** Exemption is
over `results`, and a parallel tool-call batch puts several results in one user message. Only
the last of them is exempt; the rest are pointered on the first request that carries them —
the request where the model was about to read them. See
[04-option-defer-by-turn-not-by-result.md](04-option-defer-by-turn-not-by-result.md), where it
is measured.

## Moving the breakpoint

Two functions, and they run in this order (`filter.py:293-297`):

```python
ttl = _existing_ttl(messages)
_strip_breakpoints_from(messages, newest_candidate)
if _count_breakpoints(messages) < MAX_BREAKPOINTS:
    plan.breakpoint_moved = _place_breakpoint_before(messages, newest_candidate, ttl)
```

**`_strip_breakpoints_from(messages, start)`** (`filter.py:145-161`) pops `cache_control` from
every block at or after `(message_index, block_index)`. Claude Code puts a breakpoint on the
newest block; when that block is a candidate, leaving it there would cache exactly the bytes
the filter exists to keep out of the cache.

**`_place_breakpoint_before(messages, position, ttl)`** (`filter.py:174-195`) scans backwards
from the block before `position` and puts `{"type": "ephemeral"}` — plus `"ttl"` when the
client was already asking for one — on the first block it reaches. If it finds an existing
breakpoint on the way, it returns `False` and changes nothing: that block is already the
boundary, the candidate is already outside the prefix, and there is nothing to move.

**`_existing_ttl`** (`filter.py:212-223`) reads whatever TTL the client was already asking
for, first match in wire order, so the filter cannot silently reprice a request from the 2.0×
one-hour class to the 1.25× five-minute one. That is
[docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.1's 40% error in the opposite direction, and
`test_the_clients_ttl_is_carried_onto_the_moved_breakpoint` is the guard.

**The cap.** `MAX_BREAKPOINTS = 4` (`filter.py:57-59`). The strip runs first, which is what
frees a slot when the client's own breakpoint was sitting on the candidate; the count is taken
after the strip. On a request that is still full, the placement is skipped, `breakpoint_moved`
stays `False`, and the deferred result is cache-written after all — the saving on that one
result is lost rather than the request becoming a 400. Two tests hold both sides.

## The `POINTER_RE` re-entry guard

```python
POINTER_RE = re.compile(r"^\[winnow: .* removed, rule [A-Z]\d, \d+ bytes")
```
`filter.py:61`, applied at `filter.py:259-262`: a result whose content is a `str` matching it
is counted into `tool_results_seen` and then skipped — not appended to `results`, so it is
neither re-decided nor re-counted, and it does not enter the `keep_newest` arithmetic.

Its stated reason is that re-deciding a pointer would strip a pointer and count its bytes a
second time, "which is the double-count `79dd165` records for the pruner's own re-runs".
Worth being precise about when it can actually fire, because that changes what an option may
rely on:

- **Not from the client.** Claude Code builds each request from what it holds in memory,
  which is the original bytes; the filter rewrites a copy on the wire and the client never
  sees the rewrite come back. A resume reads the transcript, which the filter never touched.
- **Not from a fork.** A `winnow fork` pointer is a different string —
  `rules.POINTER_TEMPLATE` (`rules.py:539-542`) renders the size comma-grouped, so
  `41,208 bytes` does not match `\d+ bytes`, and it carries a `sha256` and a `recover` line.
  Checked: `POINTER_RE.match` on a rendered pruner pointer is `None`.
- **Not by size either way.** The filter's own pointer is 115 bytes and the pruner's is 163,
  both far below the 2,048 floor, so G2 would exclude them even if the regex matched.
- **It fires on a second `apply` over the same object**, which is what
  `test_a_pointer_is_never_re_dropped_or_re_counted` exercises.

So it is a defence in depth rather than a load-bearing path, and it is *narrower* than the set
of pointers winnow can write. That is fine today and would not be if an option changed the
pointer text.

## The ledger line

`filter.ledger_line(plan, request_id)` (`filter.py:319-347`) emits one JSON line per **changed**
request — `plan.changed` is true when anything was dropped or the breakpoint moved
(`filter.py:80-82`). The proxy writes it in `_append_ledger` (`proxy.py:265-277`) after the
upstream response headers arrive, stamping it with the API's own `request-id` header
(`proxy.py:228-229`), under a lock, best effort: a ledger that cannot be written costs a line
on stderr and nothing more.

```json
{"request_id": …, "model": …, "cache_ttl": …,
 "dropped": [{"tool": …, "rule": …, "bytes": …, "tool_use_id": …}],
 "deferred": [ … same shape … ],
 "bytes_dropped": …, "bytes_deferred": …, "tool_results_seen": …}
```

`request_id` is the only key that joins to anything: the filter sees a Messages API body,
which carries no session identity, and Claude Code stamps the same `requestId` on the
assistant records of the turn it answered. Both `inspect.read_filter_ledger`
(`inspect.py:236-271`) and `savings.read_ledger` (`savings.py:164-…`) join on it.

`tool_use_id` is why `_entry` (`filter.py:301-316`) is a function at all. The filter is
stateless, so it re-drops the same result on every later request that still carries it, and a
ledger without an identity cannot tell a removal from its own echo — summing `bytes_dropped`
over lines overstated one real ledger by **27.2×**, 1,283 removal events over 49 distinct
results ([docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5.1). `model` and `cache_ttl` are there
so `savings` can price a removal at what that request would have cost rather than at a
documentation figure.

One thing to know before arguing about the ledger: **its two readers disagree.**
`savings.read_ledger` collapses on `tool_use_id`; `inspect.read_filter_ledger` sums
`bytes_dropped` over joining lines with no collapse at all, and feeds
`Report.wire_content_bytes`, which clamps at zero (`inspect.py:152-162`). The existing tests
(`tests/test_inspect.py:517-564`) use one line per session, so nothing covers a repeat. Named
here as the state of the code, not as an option.

## The invariants, stated because the code relies on them without naming them

Each of these is assumed, unchecked, and load-bearing. An option that breaks one breaks the
mechanism silently.

**I1 — Claude Code appends, and never rewrites an earlier turn.** Every argument in
[01-constraints.md](01-constraints.md) §K1 assumes that request *t*+1's message list contains
request *t*'s as a prefix. If the client ever re-ordered, re-serialised or re-rendered an
earlier turn, the filter's verdicts would be stable and the bytes would not be, and the cache
would break for reasons the filter could neither cause nor see. Nothing checks it and nothing
could.

**I2 — one `tool_use` per `tool_use_id`, and it is present.** `_index_tool_uses` builds a flat
`dict` over the whole body and never checks ordering or collision; a later `tool_use` with the
same id would overwrite an earlier one and could move a verdict between requests. When a
result's `tool_use` is missing, `uses.get(...)` yields `("", {})`, `rule_for` returns `None`,
and the result is kept — under-firing, which is the safe direction.

**I3 — `tool_use.name` and `tool_use.input` are never rewritten, by anyone.** They are two of
`rule_for`'s three inputs. Winnow guarantees its own half (SPEC §4's opening sentence,
DECISIONS §D3) and the vendor's `clear_tool_uses_20250919` defaults `clear_tool_inputs` to
`false`. If a client ever elided a tool input, the filter's verdict on that result would move
mid-session. This is the invariant [09-option-tool-use-inputs.md](09-option-tool-use-inputs.md)
proposes to break.

**I4 — `is_error` is written once.** `rule_for`'s third input, and G3's whole basis.

**I5 — `result_size` of a given result is the same on every request.** The `min_bytes`
comparison is a threshold on a number derived by re-serialising whatever the client sent
(`json.dumps` for a structured result), so a client that re-ordered keys inside a
`tool_result` could move a result across the floor between two requests, flipping its
rendering after it had been cached. In practice `json.loads` preserves document order and
Python dicts preserve insertion order, so the round trip is stable. It is an assumption, not a
guarantee.

**I6 — the last breakpoint is at or after the newest candidate, or the candidate is already
outside the prefix.** `_place_breakpoint_before` returning `False` on an existing breakpoint
is correct only under this reading. It holds because Claude Code puts a breakpoint on the
newest block.

**I7 — nothing between the new breakpoint and the candidate needed caching.** True at
`keep_newest = 1`, where the candidate is the last result and only it and the trailing blocks
are displaced. Not true above 1, as the deferral section shows.

**I8 — `apply` runs once per request, on a freshly parsed body.** It mutates in place;
`_rewrite` parses fresh each time (`proxy.py:166-176`). `POINTER_RE` is what makes a second
call harmless.

**I9 — a pointer is always a bare `str`.** `POINTER_RE` is only tested against
`isinstance(content, str)` (`filter.py:261`). A pointer written inside a structured content
list would not be recognised. Closed today because the filter only ever writes a bare string.

**I10 — the model tolerates a pointer where an answer was.** The whole mechanism rests on it,
nothing in this repository measures it, and SPEC §9's 200-sample blind label — which would
measure the adjacent question for the pruner — has not been run. This is the invariant every
option in this set inherits and none of them improves.
