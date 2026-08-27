# Option I — read `usage` off the response

**Verdict: reject the claim, adopt the narrow version.** Reading the response would *not* make
`winnow savings` measured rather than modelled — the counterfactual it prices is not observable
on any wire — and almost everything it would provide is already on disk. What it does buy is
one real thing: a per-request `usage` that is immune by construction to the double-count that
cost [docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5.2 a factor of two on both sides of its
own arithmetic.

## What it is

`proxy.py:12-17` states the non-goal:

> **What it deliberately does not do.** It does not retry, buffer a response, inspect a
> response body, or persist anything but its own ledger. A response is streamed through
> byte-for-byte…

`_relay` reads the upstream in 8,192-byte chunks and writes each one out chunked and flushed
(`proxy.py:240-246`). The proposal is to look, once, at the head of the stream: the first
Server-Sent Event of a Messages API response is `message_start`, and it carries
`message.usage` with `input_tokens`, `cache_creation_input_tokens` and
`cache_read_input_tokens` — everything the filter's arithmetic is denominated in. Extract those
three integers, write them into the ledger line that request already produces, forward every
byte unchanged.

## The claim it is usually made with, and why the claim is false

`winnow savings` says of its own output that it is *"modelled, not billed"*, and
[docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5.1 explains why:

> The bytes were never sent, so nothing on the wire proves the counterfactual: *D*, *T* and the
> prices are measured or published, but "these bytes would have been cache-written once and
> read on every turn after" is §3.5's model.

**Reading the response does not touch that.** It reports what the filtered request cost. The
saving is the difference between that and what an *unfiltered* request would have cost, and no
request was ever made in that arm. A number read off the wire is exactly as counterfactual as
one read off the transcript; it is simply measured on the side of the subtraction that was
never in doubt.

This matters because it is the shape of error this document set is supposed to catch. §3.1
took a multiplier from documentation and understated an invalidation by 40%; §3.4 divided a
per-turn quantity by a one-time one; §3.5.2 summed a per-request quantity per record. Each
looked more measured than it was. "We read it off the wire, so it is billed" would be the
fourth, and it would be harder to see than the other three because the input really is an
observation.

**The thing that answers the un-modelled question already exists and is a different command.**
`winnow trial` (`cli.py:704-718`):

> So this one models nothing. It reads `message.usage` off the transcripts, attributes each
> session to whichever arm was switched on at the time, and divides.

That is the instrument for "which configuration actually costs less here", it interleaves arms
so the difference between them is noise rather than the week, and it has never been run.
Nothing about reading a response makes it better.

## What is already available from disk

[docs/SPEC.md](../../docs/SPEC.md) §8 records the property the whole tree rests on:
`cache_read_input_tokens`, `cache_creation_input_tokens` and `output_tokens` are summed from
`message.usage`, *"which Claude Code writes on every assistant record, so the cache economics
are auditable from disk with zero model calls."* Three readers already do it — `inspect.Usage`,
`savings._read_usage`, and `trial`. The ledger's `request_id` joins to the transcript's
`requestId`, and `savings.find_transcripts` (`savings.py:284-306`) does that join with a
streaming regex sweep.

So: the write class, the read volume, the model, the per-request bill and *T* are all reachable
without opening a response. **Measured here, 2026-08-27**, the join is not the bottleneck it
might appear to be: all 48,835 distinct `requestId`s across this container's 866 main-session
transcripts carry a `message.usage`, so a ledger line for any of those requests would join.

The failure rate on the one *real* ledger is 15 unjoinable of 49 unique removals — 30.6%
([docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5.2) — and that is the number this option is
usually justified by. It is not intrinsic. Two candidate causes are visible in the code and
neither needs a response:

- **`find_transcripts` globs `*/*.jsonl`** (`savings.py:295`), so a request made by a sub-agent
  — whose transcript lives under `*/*/subagents/` — can never join. There are 352 such files
  on this container against 866 main sessions
  ([08-option-mcp-and-subagent-output.md](08-option-mcp-and-subagent-output.md)).
- **A request that failed leaves a ledger line and may leave no assistant record.** The proxy
  writes the ledger as soon as the response *headers* arrive (`proxy.py:228-229`), before the
  status is even inspected, so a 429 or a 500 produces a line that joins to nothing.

The first is a one-line fix. The second is genuinely wire-only, and is the one honest argument
in this whole file for looking at a response — except that what it needs is the *status code*,
which the proxy already has (`upstream.status`), not the body.

## What the narrow version does buy

One thing, and it is worth stating precisely because it is the only one.

**A per-request `usage` cannot be double-counted per record.** §3.5.2's audit found that Claude
Code writes one API response as several assistant records — one per content-block group — and
stamps every one with the same `requestId` and the same `message.usage`, at 1.66 to 2.43
records per request on this install. Counting records charged the same response two or three
times **in two places at once**: *T* fell from 1,740 to 917 when it was fixed, and the measured
bill of the joined sessions fell from $94.67 to $43.67. The section closes by noting that *"the
same per-record double-count exists in `inspect.py`'s own usage reader and is not touched
here"* — so the bug is still live in one of the three readers.

A usage read from `message_start` is one object per response by construction. There is no
record to double-count. **It is not a better measurement; it is a measurement that cannot make
that particular mistake**, and the mistake has been made twice in this repository and is
uncorrected in one place.

Two lesser benefits, both real and both small: the ledger becomes self-describing, so a line
carries what the filter did *and* what that request was billed without any join at all; and a
request whose transcript is unreachable — a failed call, a sub-agent under a glob that does
not match — is priced anyway.

## What it costs

**§K9 is the binding constraint and it is satisfiable, narrowly.** `message_start` is the first
event of the stream, so the parse is bounded at the front and nothing behind it is delayed. The
discipline that keeps it honest:

- **Forward every chunk the moment it arrives, before parsing.** The parse runs on a copy.
- **Accumulate only until the first complete event, with a hard byte ceiling** — a few
  kilobytes — after which the scan stops for that response and the ledger line records that
  usage was not available. A scan that could grow without bound is a buffer, which is the
  thing §K9 forbids.
- **Only when `content-type` is `text/event-stream`.** A non-streamed response carries `usage`
  at the top level of a JSON body, and reaching it means holding the whole body. That is a
  buffer and the option must decline it rather than special-case it.
- **Extract integers and nothing else.** §K2: this runs beside a live credential, and a
  response body carries the model's own output. A parse that lifted anything but three
  numbers, or that logged a fragment on error, would put model output on stderr in a process
  whose access log is silenced (`proxy.py:200-202`) precisely so that it does not.
- **§K6: any parse failure is silent and total.** No exception escapes to the relay loop; the
  ledger line simply omits the fields, and the readout says how many lines lack them — which is
  the discipline `savings` already uses for `model` and `cache_ttl`
  (`LedgerRead.lines_without_model`, `lines_without_ttl`, `savings.py:144-145`).

**The latency cost is a substring search and one `json.loads` of a few hundred bytes, off the
critical path.** No figure is derivable for it here — the proxy has not been run against a real
upstream in this container — and the measurement that would settle it is: relay a streamed
response with and without the scan and compare time-to-first-byte, which is a test and not a
production observation.

## Which constraints it strains

- **§K9** — directly, and it is the constraint that shapes the whole design. Satisfiable only
  because the field wanted is in the first event.
- **§K2** — a response body is the largest thing the proxy touches that it currently does not
  look at. The surface added is a parser, and a parser is where the interesting bugs are.
- **§K3** — an SSE parser is a hundred lines of stdlib string handling or a dependency. It has
  to be the former, and the former is the kind of code that grows.
- **§K1** — none. Nothing about a response can change a request that has already been sent.

## What it breaks

**The proxy's simplest promise.** *"It does not retry, buffer a response, inspect a response
body, or persist anything but its own ledger"* is a sentence an operator can check against the
code in a minute, and it is the sentence that makes putting this process in front of a
credential defensible at all. After this change the first half is still true and the sentence
is longer, with a qualification about which content types and which byte ceiling. That is a
real loss, and it is not obviously worth trading for immunity to one arithmetic error that a
test could also catch.

## The strongest case against

**That the whole option is a symptom of measuring the wrong thing.** Everything it improves is
an input to §3.5's cost model, and §3.5's cost model is a counterfactual that no amount of
better inputs makes into an observation. The project already knows what the un-modelled
answer looks like — `winnow trial`, interleaved arms, billed usage, `$`/task — and that command
is built, documented, and has never had a single arm recorded against it.

Reading the response would produce a more precise version of a number the project's own D8
says is not the deliverable: *"[e]valuate on cache-adjusted cost per **successful** task, never
on tokens."* Spending the credential path's surface area on a better modelled figure, while
the measured instrument sits unused, is the wrong order. **The narrow version is adoptable
because it is cheap and it closes a known class of error; it should not be presented as
progress toward the number that matters.**
