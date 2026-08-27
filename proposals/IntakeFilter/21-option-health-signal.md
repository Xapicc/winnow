# Option S — the smallest honest signal that the filter is still filtering

**Verdict: take the two-field version. Reject a status endpoint.** A filter that has quietly
stopped doing anything is indistinguishable from a session with nothing to remove, and the one
number that would tell them apart is already computed on every request and thrown away.

## What is counted now

`proxy.Stats` (`proxy.py:76-101`):

```python
requests: int = 0
filtered: int = 0
bytes_dropped: int = 0
bytes_deferred: int = 0
errors: int = 0
```

rendered as `"{requests} requests, {filtered} filtered, {bytes_dropped:,} bytes dropped,
{bytes_deferred:,} deferred, {errors} passthrough on error"`.

Four things about it that are not in the docstring.

**It is printed once, on exit.** `serve`'s `finally` block (`proxy.py:306`) is the only caller of
`Stats.line`. The dataclass docstring says *"[r]unning totals, printed on exit and readable
while it runs"*, and nothing makes them readable while it runs — no endpoint, no signal handler,
no periodic emission. `--verbose` prints one line per *changed* request (`proxy.py:188-191`),
which is the case that is already visible in the ledger.

**`requests` is not the request count.** `stats.record()` is called from `_rewrite`'s three
branches and from `_relay`'s `elif raw:` (`proxy.py:211-212`). A request with no body — every
`GET`, and `do_GET` is bound to the same `_relay` — increments nothing.

**`errors` is two different failures in one integer.** `stats.record(error=True)` fires for an
unparseable body (`proxy.py:171`) and for a filter that raised (`proxy.py:178`). The first says
the wire format changed under the filter; the second says the filter has a bug. Both also print
to stderr, so this counter is a tally rather than the alarm.

**An upstream failure is not counted at all.** The `except OSError` around the relay
(`proxy.py:248-253`) prints and returns a 502 and touches no counter, and neither does a ledger
write that fails.

## The failure this does not cover

Every one of these produces exactly the same output — `filtered = 0`, no ledger lines, no stderr
after startup:

1. **`ANTHROPIC_BASE_URL` never reached the client.** The proxy prints the `export` line
   (`proxy.py:299`) and an operator who did not run it gets a listener nothing connects to.
   `requests` stays 0, which is at least *distinguishable* — but only if anyone looks, and the
   only place it appears is the exit line of a process that is still running.
2. **The kill switch is on.** `_filtering_disabled` prints *"filtering DISABLED … still
   relaying"* on the transition and once only (`proxy.py:148-156`), deliberately, so a switch
   touched last week and forgotten is silent today. Requests are counted, `filtered` stays 0.
3. **`--min-bytes` mistyped.** `WINNOW_FILTER_MIN_BYTES=20480` is an `int()` that parses and a
   floor ten times too high. Nothing reports the setting except the startup banner
   (`proxy.py:286-287`), which is one line at the top of a long-running process's stderr.
4. **The body shape moved.** If the client ever nested `tool_result` blocks differently, or
   stopped setting `tool_use_id`, `rule_for` would return `None` everywhere and every request
   would pass through cleanly. This is the one that would not even print a warning, because
   nothing raised.

**In every case the operator's evidence is a bill that did not improve, months later.** SPEC §8
puts the standard exactly here, quoting `ContextControl/01-`: *"on a build where the lever does
nothing, does the run get quietly more expensive, or does something say so?"* Today nothing says
so.

## The number that separates them

`Plan.tool_results_seen` (`filter.py:73`, incremented at `filter.py:255`) counts every
`tool_result` in the body, on every request, whether or not anything was removed. It reaches the
ledger — but only on a *changed* request (`plan.changed` gates the line, `proxy.py:183-186`), so
the requests where the filter did nothing contribute nothing, which is precisely the population
a health signal is about.

**The smallest honest change is two fields on `Stats` and four words in one string:**

```python
tool_results_seen: int = 0     # what the filter looked at
candidates: int = 0            # what it claimed
```

fed from the plan `_rewrite` already holds, and rendered as

```
1,842 requests, 121 filtered, 6,410 tool results seen, 137 claimed,
2,904,118 bytes dropped, 88,204 deferred, 0 unreadable, 0 filter errors
```

That distinguishes all four failures above from a genuinely quiet session, because
`0 filtered` beside `6,410 tool results seen` is a fault and `0 filtered` beside `0 seen` is a
proxy nobody is talking to. Splitting `errors` into `unreadable` and `filter errors` is one more
field and separates a format change from a bug.

**What the numbers should be.** A signal is only useful against an expectation, and this corpus
supplies one. **Measured here, 2026-08-27**, over 867 main-session transcripts: **7.29% of
`tool_result` blocks are candidates** (4,715 of 64,685), **6.5% of turns would produce a ledger
line** (4,129 of 63,149), and **67.4% of sessions contain at least one candidate**. An install
running an order of magnitude below those is not a quiet week.

## Making it readable while it runs

The exit line is the wrong instrument for a process meant to run for days. Three ways to fix
that, in increasing cost.

**A ledger heartbeat.** One line every *N* changed requests, or every *N* requests, carrying the
same counters, with the `kind` discriminator [20-option-ledger-as-artefact.md](20-option-ledger-as-artefact.md)
proposes and [12-option-prefix-readout.md](12-option-prefix-readout.md) needs. No new file, no
new socket, no new failure path — `_append_ledger` is already best-effort. `winnow savings` then
has the denominator it has never had: it prices what was removed and has no idea what was
looked at. **This is the version worth building**, and it is worth building at the same time as
the `kind` tag rather than as a second change to the same file.

**A periodic stderr line.** Cheapest, and it introduces a clock. That is allowed —
[01-constraints.md](01-constraints.md) §K10's determinism constrains the *bytes sent*, and this
never reaches them, the same distinction option J draws for its prefix-hash state
([12](12-option-prefix-readout.md)). It is also the thing most likely to be lost in a terminal.

**A status endpoint.** `GET /_winnow/stats` intercepted before the relay, or a second socket.
**Reject.** §K2 charges an option for surface area beside a live credential, and this one adds a
route that returns internal state from a process whose access log is silenced
(`proxy.py:200-202`) precisely so that request lines never reach stderr. A second listener is
worse again. The ledger is a file the operator already owns and already reads.

## Which constraints it strains

- **§K2** — the ledger heartbeat adds no surface. The endpoint adds the most surface of
  anything in this proposal set except a recall store, and buys the least.
- **§K6** — counters must never be able to fail a request. `Stats.record` already takes a lock
  and does arithmetic; a heartbeat rides `_append_ledger`, which catches `OSError` and
  `JSONDecodeError` and forwards regardless.
- **§K5** — a heartbeat line is a record of what happened that nothing consults to decide
  anything, which is the reading of "no fourth store" §K5 says survives.
- **§K1, §K4, §K10** — none. No byte on the wire changes.

## What it breaks

`Stats.line()`'s format is asserted in `test_stats_line_reports_passthrough_on_error`
(`tests/test_filter.py:401-408`), which is one test and the right one to update. The heartbeat
needs the ledger readers to skip a line whose `kind` is not `"filter"` — which is the same
compatibility question §20 raises and which both readers currently fail, because they key off
field presence rather than off a tag. **The two changes are one change and should land
together**, or the first heartbeat line lands in `savings.read_ledger` as
`malformed_entries` and in `inspect.read_filter_ledger` as a `request_id` that matches nothing.

## The strongest case against

**That the operator already has a better instrument and it is not in this process.**
`winnow savings` reads the ledger and prices it; `winnow inspect --filter-ledger` joins it to a
session; `winnow trial` attributes sessions to arms. Any of the four failures above shows up
immediately as *"no ledger lines this week"* the first time somebody runs `winnow savings`, with
a readout that already reports line counts, parse errors, legacy lines and the echo factor
(`report.py:368-393`). Adding counters to a proxy so it can tell you what a command already
tells you is duplication in the one place where duplication is charged by the line.

That is a good objection and it fails on one word: *denominator*. `winnow savings` can see every
removal and cannot see a single request where nothing was removed, because the ledger line is
gated on `plan.changed`. It cannot distinguish "the filter ran all week and found nothing to
take" from "the filter has not been in the path since Tuesday". **The failure mode this option
is about is exactly the one the existing instrument is blind to, and it is blind to it because
the artefact only records successes.** Three of the four failures above produce a ledger that is
empty and a `savings` readout that says, accurately and uselessly, that nothing was saved.
