# Option C — a page served from the CLI

`winnow context <session-id> --serve` binds a loopback port, serves one page built from one
JSON payload, and prints a URL. The page draws nested rectangles sized by tokens: an actual
treemap, the thing the request asked for by name. `--watch` upgrades the payload to a stream.

*Same ten headings as `03-option-a` and `03-option-b`.*

## The strongest case

**It is the only option that can draw a difference in kind.** This matters more here than in
any ordinary visualisation, and `01-` §5 says so outright: *"the single most important
rendering decision is whether the invisible part is drawn."* `02-constraints.md`'s correction
sharpens it — the invisible part is not one grey lump but two derived blocks worth a median
~24% and ~14% of the window, computed from exact anchors, as trustworthy as anything on the
screen and arrived at by a completely different route. A terminal has one channel for that
distinction: a word in a column. A page has fill pattern, border, opacity and texture, and can
say *this rectangle is measured, that one is derived, that thin one is what we could not
account for* in a way the eye reads before the label does. Nothing else in this set can.

**Second, it is the only option where the whole window is on screen at once.** A and B show a
ranked list with the tail collapsed into an `(N more)` row. A treemap shows all of it, and
"there is nothing big, it is a hundred small things" is an answer a ranked list actively hides.

**This corpus does not support that case and it should be said here rather than in the
comparison.** Take the most tool-diverse session it contains — `01-` §2.6's column E, 311
requests, an MCP browser server, sub-agents and web work. Measured by this run rather than
taken from the table: **13 distinct tool names**, 165,796 estimated tool-result tokens, of
which **Bash alone is 135,897**. The other twelve together are 29,899, or **5.8% of that
session's 512,133-token window**, and nine of the twelve are under 2,500 each. A ranked list
that shows five rows and folds the rest into `(8 more) 2,850` loses nothing an operator would
act on. The case for drawing the tail rests on session shapes this corpus does not contain:
many servers, many mid-sized results, no dominant tool. Whether the operator's sessions move
that way is a bet on a trend, not a reading of the evidence, and it is C's bet to lose.

**Third, it is the only option that survives being shown to somebody else.** A screenshot of a
treemap is a document. It goes into a note, a message, a proposal like this one. `00-` §2's
fourth question — "this session cost four times what the last one cost, what is different
about it" — is very often asked *about* two sessions in front of a second person, and the
answer that lands is two pictures side by side.

## Shape

The CLI computes the same tree Option A computes and serialises it once. A single-file page —
HTML with inlined CSS and JavaScript, no build step, no CDN, because `01-` §2.2 establishes
that this environment has no network and a page that fetches `d3` from a CDN is a page that
renders blank on the machine it was written for — lays the tree out with a squarified treemap
and handles click-to-zoom, breadcrumb, hover and a detail panel. `--watch` replaces the static
payload with server-sent events over the same JSON.

Serving is `http.server` from the standard library, bound to `127.0.0.1` on an ephemeral port,
with a one-shot token in the URL and a shutdown when the page disconnects.

That last clause is not boilerplate. **The payload is transcript content.** `01-` §1.2 records
that the environment attachment carries the working directory, git status and the user's email
address; `nested_memory` carries whole rule files; `tool_use` inputs carry commands and file
contents; and any secret that ever appeared in a tool result is in the transcript verbatim.
Node labels are derived from all of it. A served page is that material published to whatever
can reach the port, and on a machine running a dozen concurrent agents in shared mounts that
is not a hypothetical. Loopback, ephemeral, tokened, short-lived — and the labels truncated
rather than full — is the minimum, and it is a real cost that neither terminal option pays.

## What the operator sees

One rectangle, divided by tokens. On the worked session in `03-option-a`, `tool traffic` is
31.4% of the area, subdivided by tool and then by Bash command head and read path; `prefix` and
`retained reasoning` are 42.8% and 21.2%, hatched rather than filled; `unattributed` is a 0.4%
sliver in the corner — 891 tokens of 219,485 — and the fact that it is a sliver is the message.
Click any rectangle to zoom into it; a breadcrumb walks back out; hover gives the token count,
the provenance and the derivation.

The one honest sketch of the failure mode: on `01-` §2.6's column A — a young session, 80%
prefix — the operator sees a screen that is four fifths hatched, which is exactly correct and
looks like a bug.

## The floor, drawn

Best of the three on the *signal*, and the worst on the *explanation*.

Hatching says "different in kind" faster and more reliably than any word. But the sentence that
makes the prefix actionable — *this is the system prompt, your tool definitions, your MCP
servers and your skills; it is a median 24% of your window — 42.8% on this one — before you
type; here is the first-request arithmetic that derives it* — has to live in a hover tooltip or
a side panel, and both are places explanations go unread. `03-option-b`'s detail pane is a worse
signal and a better explanation, and on this particular node the explanation is what changes
behaviour, because the prefix is the one block an operator fixes by editing configuration rather
than by working differently.

## When the data is missing, partial or lying

Every case from `03-option-a` produces the same tree; what differs is that a page can *encode*
the degradation rather than print it. A node sized at a `<persisted-output>` preview gets a
distinct border and a hover line naming the sidecar size. A hook-rewritten result gets a
marker. A session with no `usage` anchor gets a banner and every percentage suppressed.

The genuinely worse case is the small one. A treemap allocates area proportionally, so a node
worth a tenth of a percent of the window gets a thousandth of the canvas; whatever that is in
pixels on the operator's screen, the caveat attached to it is unhoverable and effectively
invisible, and there is no size of screen at which that stops being true — it is a property of
proportional area, not of this layout. `01-` §1.1's warning about `queue-operation` — 1.96 MB
that looks exactly like context and is not — is a warning about a class of error that manifests
as *many small rectangles*, and small rectangles are where a treemap is blind. A ranked list
with an `(N more)` row at least states how many things were folded into it.

## Live mode

Server-sent events at the same 250 ms cadence, and the browser animates rectangles between
sizes rather than redrawing, which is the nicest live experience in the set — a growing tool
result is a rectangle visibly growing.

§C12 is drawable and drawable well: the material appended since the last priced request is a
distinct region with its own hatch, the anchor age is a ticking line in the header, and an
in-flight `tool_use` is an outlined rectangle with no fill. The rhythm — anchored tree, growing
un-anchored region, snap on the next assistant record — is more legible animated than static.

Against that: **the browser is a second surface the operator has to keep alive.** The terminal
options live in a pane beside the work. A page lives in a window behind the editor, goes stale
when the laptop sleeps, needs the process still running, and reconnects badly. And a CLI that
holds a port open for the length of a session is a process the operator has to remember to
kill — on this machine, one more thing in `pgrep`.

## Where this render wants the code to live

Furthest from here of the three. It drags in a static asset tree, a second language, a server
and a security surface, into a package whose `pyproject.toml` declares one runtime dependency
and whose existing extras pattern exists precisely so that `winnow list` does not pull an MCP
framework. Behind a `winnow[web]` extra it is *admissible*; as a reason to build the whole
tool elsewhere it is the strongest one `03-option-d` has.

It is also the option that most obviously wants to be a card in UsageFoundry rather than a CLI
at all — which `03-option-d` takes up and rejects, on the grounds that the operator asked for a
command taking a session id, and UsageFoundry only knows about runs it launched.

## What it costs to build

Option A's cost, plus a front end.

**New**, with the same caveat as `03-option-b`'s list — the line counts are this run's guess
about code that does not exist: the squarified layout (~120 lines of JavaScript, a known
algorithm, no dependency needed); zoom, breadcrumb, hover and the detail panel (~250); the
provenance encoding, which is the hard part, because "hatched, but still legible at four pixels,
in both light and dark, and distinguishable from the selection highlight" is a real design
problem and not a CSS class (~150 and an afternoon of looking at it); the server, token and
shutdown (~120 Python); the SSE path (~100 across both sides); packaging a static asset tree
into a Python distribution and testing that it is actually present in a wheel.

**Roughly 2–2.5× Option A**, and the multiplier understates it, because it is the only option
whose cost includes a category the rest of this repository has none of: front-end review, a
second test harness, and a security argument about a bound port that has to be made once and
then re-made every time the payload changes.

## How it fails, and whether loudly

**Loudly at the process level and silently at the perceptual level.** If the server does not
start, the operator knows. If the page renders, every number on it is subject to the failure
this option is uniquely prone to: **area is a bad encoder for the comparison the operator
actually makes.** The questions in `00-` §2 are "what is the biggest", "how much is one tool"
and "how much is one file" — a ranking and two magnitudes. Rectangles of different aspect
ratios in different parts of a screen are read badly for both; a sorted bar is read well for
both. The treemap's strength is showing *that the tail exists*; its weakness is every
quantitative judgement made across it, and the operator will make those judgements anyway
because the picture invites them.

The second silent failure is a category error the format encourages. A treemap is a
*space-filling* diagram, and the thing it is filling looks like a disk with free space on it.
Every visual convention it inherits from TreeSize implies "delete the big rectangle to get the
space back", which §C13 establishes is false in this domain and can be false *in sign*, since
removing an early block invalidates the prompt cache for everything after it. Options A and B
inherit no such implication. C inherits it by construction and has to spend design effort
fighting the metaphor it was chosen for.

## What would have to be true

**That the tail matters**, and on this corpus it demonstrably does not — see the second
paragraph of *The strongest case*, where E's four non-Bash tool families come to about 5% of
its window. If the answer is always three nodes, a page is an expensive way to draw three
nodes and A wins. C's case requires future sessions with many MCP servers and no dominant
tool, which is a plausible direction of travel and is not evidence.

**That the operator wants to show somebody.** A screenshot is C's real product. If the readout
is only ever read by the person who ran it, the terminal is strictly better.

**That a bound port on this machine is acceptable**, having read the paragraph in *Shape*.

---

**And the fact that most weakens it, stated plainly:** it is the most chart-like option, and
`00-` §6 already wrote the epitaph — *"if nobody would act on it, it is a chart."* The actions
available to an operator who has seen the composition are narrow: read less, read with
`offset`, prune, restart, trim the prefix. Not one of them becomes easier because the
composition was drawn as rectangles rather than as rows. Everything C adds is legibility of the
*shape* of a window, and the operator's problem is not that they cannot picture their window —
it is that they cannot name the biggest thing in it. A sorted list names it in one line. C
spends 2–2.5× Option A's build, a bound port carrying transcript content, and a fight with an
inherited "reclaimable space" metaphor, to name it in a rectangle.
