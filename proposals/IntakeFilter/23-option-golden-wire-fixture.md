# Option U — pin the emitted request body, the way milestone 1's number is pinned

**Verdict: take it, at a smaller scale than the existing golden.** `winnow inspect --json` is
pinned byte-for-byte across seven fixtures and three tiers because *"a change that moves that
number has to be a decision someone took, not a side effect"*. The filter's output is a request
body, the request body is the cache key, and nothing pins a single byte of it. Writing the
golden also surfaces an invariant nobody has stated: **on a changed request the filter
re-serialises the entire body, and on an unchanged one it forwards the client's original
bytes.**

## The precedent

`tests/test_inspect_golden.py:1-19`:

> `winnow inspect --json` is pinned, byte for byte, against every session fixture. … The
> extraction is only safe if it is output-neutral, and "it still looks right" is not a check.
> … It is also the standing regression pin. Milestone 1's deliverable is a number (SPEC §9: tier
> CB reproduces 22.6% pooled within ±3 points), and a change that moves that number has to be a
> decision someone took, not a side effect.
>
> Regenerate deliberately, never to make this pass:
> `WINNOW_REGEN_GOLDEN=1 uv run --extra dev pytest tests/test_inspect_golden.py`

`tests/fixtures/inspect_golden.json` is 15 KB covering seven session fixtures × three tiers, and
the test asserts the fixture list matches so a fixture cannot be added without a regeneration.

## What is pinned for the filter, which is nothing

`tests/test_filter.py`'s own preamble states the right principle and then does not apply it:

> The policy tests assert on request bodies, because the request body **is** the cache key — a
> policy that produced the right decision and the wrong bytes would be worse than no policy at
> all.

Every one of the 39 tests asserts a *property* of a body — that a particular block's content
`startswith("[winnow:")`, that a position is or is not in `breakpoints_of(request)`, that a
count is 2. None compares a whole body against a recorded one.
`test_the_policy_is_idempotent_so_the_prefix_never_flaps` (`:158-166`) is the only test that
serialises a body at all, and it compares the body to itself after a second `apply`.

So these changes pass the suite today:

- **Rewording the pointer.** `test_the_pointer_says_where_the_bytes_went` (`:243-248`) asserts
  `"rule B2" in text`, `"41208 bytes" in text` and `"recover" not in text`. Every other word is
  free. The pointer is content the model reads and DECISIONS §Q3 records that nobody has
  published a comparison between placeholder wordings; changing it is a legitimate experiment
  and it should be a visible one.
- **Changing where `_place_breakpoint_before` lands** — one block earlier, say — as long as it
  is still before the candidate. Four tests assert ordering; none asserts position.
- **Emitting `cache_control` as `{"type": "ephemeral"}` versus with a `"ttl"` key** on a request
  where the client asked for none. One test covers the `1h` case (`:197-206`); nothing covers
  the absent-TTL case's exact object.
- **Changing whether `cache_control` is popped off a dropped block** (`filter.py:289`). Nothing
  asserts it, and it is the line that decides whether a pointered result carries a stale
  breakpoint into the prefix.

Each is a byte on the wire, and the wire is the cache key.

## The invariant the golden would surface

`proxy._rewrite` (`proxy.py:183-192`) has two exits:

```python
if not plan.changed:
    stats.record()
    return raw, None                                  # the client's own bytes, verbatim
...
return json.dumps(body).encode("utf-8"), ledger_line(plan)   # re-rendered from scratch
```

**On a changed request the whole body is re-serialised in Python's default JSON style** —
`", "` and `": "` separators, `ensure_ascii=True`, so every non-ASCII character becomes a
`\uXXXX` escape. The client's own encoding choices are not preserved and nothing tries to
preserve them. On an unchanged request they are preserved exactly, because the original bytes go
out untouched.

So one conversation is transmitted in two different encodings depending on whether the filter
found a candidate that turn. That is safe if and only if:

> **I11 — the API's cache key is computed over the parsed content, not over the request's JSON
> encoding.**

If it were not, the filter would break its own cache on every request where `plan.changed`
flipped, which is most of them. It plainly does not — COZEMPIC §3.5 reports a working
mechanism — so I11 holds. **It is nowhere written down**, and it belongs beside I1–I10 in
[02-what-runs-today.md](02-what-runs-today.md), because it is the assumption that licenses the
one line of `proxy.py` a reader is most likely to think is free. A golden that records the
emitted bytes makes any change to that line visible even though it cannot test I11 itself.

## What the golden should be

**Smaller than `inspect_golden.json`, and on inputs rather than sessions.** `inspect`'s golden
runs over real session transcripts because its deliverable is a corpus statistic. The filter's
deliverable is a transformation, so the fixtures should be request bodies chosen to cover the
branches:

| Fixture | Covers |
| --- | --- |
| one candidate, no client breakpoint | the placement path |
| one candidate, client breakpoint on it | the strip-then-place path |
| four client breakpoints, candidate after all of them | the cap branch |
| a parallel batch of three, two of them candidates | [04](04-option-defer-by-turn-not-by-result.md)'s shape, which nothing constructs today |
| a candidate below `min_bytes` and one above | G2 |
| an `is_error` candidate | G3 |
| a result whose content is a list with an image block | [19](19-option-content-shapes.md)'s shape, which nothing constructs today |
| a body already carrying a pointer | the re-entry guard |

and the golden records three things per fixture: **the emitted body**, `ledger_line(plan)`, and
`plan` as a dict. The ledger line matters as much as the body — it is the durable artefact two
commands read, and [20-option-ledger-as-artefact.md](20-option-ledger-as-artefact.md) argues its
next migration changes what a key *means*, which a golden catches and a schema check does not.

The regeneration discipline should be copied verbatim, environment variable and all, because
that discipline is the whole value: *"[r]egenerate deliberately, never to make this pass … and
commit the diff with the reason it moved."*

Two of the eight fixtures above are shapes no existing test constructs. **Writing the golden is
how those shapes get into the suite at all**, which is the second reason to do it — the same
reason `test_inspect_golden.py` gives for asserting the fixture list matches.

## Which constraints it strains

- **§K1** — the golden is K1's regression pin, in the same sense the property test in
  [17-option-cache-write-invariant.md](17-option-cache-write-invariant.md) is K1's enforcement.
  They are different instruments and both are wanted: the property test says *no body violates
  the rule*, the golden says *these bodies have not moved*. A property test does not notice a
  reworded pointer; a golden does not notice a body nobody wrote down.
- **§K10** — determinism. `apply` has no clock, no counter and no random source, so a golden is
  reproducible; `json.dumps(..., sort_keys=True)` in the golden file itself, as
  `test_inspect_golden.py` already does, removes dict-ordering as a source of noise. Note that
  the *emitted* body must be recorded as `json.dumps(body)` exactly as `_rewrite` produces it,
  not sorted, or the golden pins something the wire never carries.
- **§K2, §K3, §K6, §K9** — none. It is a test file and a fixture.

## What it breaks

Nothing, and that is the risk: a golden that never fails is a golden nobody trusts, and a golden
that fails on every legitimate change teaches regeneration as a reflex. `test_inspect_golden.py`
guards against that with a comment rather than a mechanism (*"never to make this pass"*), and
the same guard is all that is available here. The mitigation is to keep the fixture count small
— eight bodies, not seven sessions × three tiers — so that a diff is readable and a reviewer can
see what moved.

## The strongest case against

**That a golden pins the implementation rather than the contract, and the filter's contract is
not "these bytes" but "no result the model still needs is removed, and nothing cached is
rewritten".** Those are the properties, they are what §17 proposes to test, and a golden over
concrete bodies adds friction to every change while catching only the class of change that a
careful reviewer would see in the diff anyway. `inspect`'s golden earns its friction because its
output is a *published number* with a ±3-point reproduction target in SPEC §9; the filter has no
published number of that kind, and pinning bytes for a component with no external commitment is
ceremony.

The reply is that the filter has something stronger than a published number: **a byte-level
contract with a cache it cannot observe.** `inspect` being wrong produces a misleading readout
that a second run corrects. The filter being wrong by one byte in the wrong place produces
`1.9·S` on a warm prefix, silently, in a bill that arrives weeks later, in a process nobody is
watching — which is exactly the failure §17 found reachable through `--keep-newest 2` and which
five hand-built breakpoint tests did not catch. The friction is the point, and eight fixtures is
a small amount of it.

The narrower version of the objection should be accepted: **do not pin sessions, and do not pin
three tiers of anything.** The filter has no tiers today, and if
[15-option-honour-rule-selection.md](15-option-honour-rule-selection.md) gives it some, the
golden should grow by rule selection rather than by fixture, or it will be regenerated so often
that nobody reads the diff.
