# Option D — a project of its own

*This option is on a different axis from A, B and C — it is about where the code lives, not
what it draws — so it does not take their ten headings, and it combines with any of them. It
is written to persuade, like the others, and it loses; the last section says on what.*

## The strongest case

**winnow is not a reader, and a reader should not have to be winnow.** `01-` §6.1's fair
summary is that there are roughly 1,200 lines of good transcript substrate here inside
~22,000 lines of pruning policy — a proxy, a guard daemon, a rule engine, a team supervisor,
strategies, and two stores under `~/.winnow`. To look at a session, an operator would install
all of it. The instrument that `00-` describes wants to be one command with one argument that
somebody can run without adopting a philosophy about pruning.

**The blast radius is genuinely asymmetric.** `winnow filter` sits in the tool-result path. A
bug in a visualiser is a bad picture; a bug in something that ships in the same distribution,
shares a version number and shares a release, is a bad picture *and* a reason to be nervous
about the thing rewriting tool results. `01-` §6.1 also records that `winnow savings` is
currently broken on `main` (`AttributeError: 'Namespace' object has no attribute
'filter_ledger'`, `cli.py:609`), which is the shape of the risk stated concretely: a CLI where
one subcommand's argument parser breaks another is a CLI where subcommands are coupled by
accident.

**The dependency direction is wrong.** `pyproject.toml` declares exactly one runtime
dependency, `psutil`, and carries an extras pattern justified on the ground that `winnow list`
should not pull an MCP framework. `03-option-b` wants a TUI library and `03-option-c` wants a
static asset tree, a server and an argument about a bound port. Both are the same objection the
extras pattern was created for, one step further along, and the honest place for a package that
grows a front end is a package of its own.

**The constants disagree.** `legacy/tokens.py:131` sets `CHARS_PER_TOKEN_DEFAULT = 3.1`,
`savings.py:97` uses `bytes/4`, `legacy/tokens.py:20` sets `SYSTEM_OVERHEAD_TOKENS = 21_000`
and `inspect.py:67` sets `BASE_PREFIX_TOKENS = 15_903`. `01-` §2.3 measures 2.6 and §3.1
measures the prefix at ~30,000 with a p90 of 82,689 — so all four are wrong against this run's
own measurements, and one of them (`BASE_PREFIX_TOKENS`) is established by `01-` §3.1 to be
dead code whose cited source no longer contains the number. A fifth constant arriving in the
same package starts an argument about which module owns it. A new project starts with one
constant and one owner.

**And the audiences do not overlap much.** Everyone with a Claude Code session has the problem
`00-` describes. Only the subset that has decided to prune wants winnow.

## Shape

A new repository. `contextmap <session-id>`, `uvx`-runnable, Python 3.10+, standard library
only for the core, extras for whichever render wins. It reads `~/.claude/projects` and nothing
else. It never writes (§C1) and therefore never needs a store, a lock, a config file or a
daemon. It is the smallest shippable thing in this whole proposal set.

## What would have to be copied, and what re-learnt

This is the part that decides the option, so it is enumerated rather than summarised. From
`01-` §6.1, with the sizes checked against the tree as it stands:

| what | where | lines | copy or rewrite |
|---|---|---:|---|
| tolerant JSONL parsing; `_split_physical_lines`; byte-offset incremental reads with inode / shrink / mtime invalidation | `legacy/session.py:722–1037` | ~315 | **copy**, and it is the single most valuable thing in the tree |
| record and block accessors — `msg_bytes`, `get_msg_type`, `get_content_blocks`, `text_of` | `legacy/helpers.py` (1,011 total) | ~120 | copy the useful part |
| the one-pass block walk, pairing `tool_use`↔`tool_result` by id | `inspect.py:330 inspect_session` (481 total) | ~150 | copy, then change the denominator |
| session resolution from id / path / unambiguous prefix | `report.py:47 resolve_session` | ~60 | copy |
| exact-window extraction from the last main-chain assistant record | `legacy/tokens.py:297` | ~50 | copy |
| measurement primitives — `result_size`, `content_digest`, `input_size`, `read_range`, `bash_head` | `rules.py` (713 total) | ~120 | copy; `bash_head` is the second level of the tool-traffic tree |
| the project-slug transform and the ordered live-session search | `legacy/session.py:275`, `:381` | ~90 | rewrite — `find_current_session` shells out to `ps` and `lsof` and reads a winnow-owned store; only the *ordering* is reusable |
| poll/kqueue watcher, degrading to poll on rename | `legacy/watcher.py` | 141 | optional; `01-` §4.4 says poll anyway |
| per-record-type counts, top-N largest, thinking vs signature bytes | `legacy/diagnosis.py` | 99 | copy — the closest existing thing to a proto-treemap |

Call it **900–1,000 lines copied and ~90 rewritten**, which is a week of nothing, not a month.
The code is not the problem.

**What cannot be copied is the reason each line is the way it is.** `01-` §6.1's closing
paragraph is the one that should decide this option: *"Nearly every guard in `legacy/` carries
a dated postmortem — the U+2028 `splitlines` trap, the surrogateescape round-trip, the forged
sentinel-key defence, 'the f464a40c wrong-session incident'. Those comments record which JSONL
malformations actually occur in production."* A copy carries the comments across on day one
and then diverges. Six months later there are two parsers, one of which has been taught about
a malformation the other has not, and the failure is silent by construction because both
produce a number either way. §C8 exists because `/workspace/gh-layer10` already made the
cheaper version of this mistake — it re-implemented usage extraction and shipped the
`message.id` double-count.

## What stays behind, and what it is worth

`winnow/filter.py:728 prefix_facts`, `:768 prefix_changes` and `proxy.py:167 PrefixWatch` —
**the only thing on this machine that can size the prefix exactly**, giving `system_bytes`,
`tools_bytes`, per-tool definition bytes and cache-breakpoint positions.

It cannot be copied to a new project in any useful sense, because it is a pure function of a
Messages API request body and a new project pointed at a `.jsonl` has no request body to give
it. `00-` §6 names the failure mode this creates: *"if the operator's real question is 'why is
my prefix 98,000 tokens' … then a transcript-only tool cannot answer it, and the honest
instrument is a proxy sitting on the request body. This repo already built one."*

`02-constraints.md`'s correction softens that considerably — the prefix is now *derived* per
session at a median ~24% of the window, and robust: `01-` §3.1 re-runs the derivation at
2.2/2.6/3.0/4.0 chars per token — an 80% swing in the constant — and the prefix median moves
only 14%, because the visible material before the first request is ~15% of it. So the exact
instrument is a cross-check rather than a necessity. But it is the *only* cross-check, it is the
one thing that would settle whether the derived prefix is right, and a new project puts a
repository boundary between the instrument and its only calibration.

## The third home: a card in UsageFoundry

Argued and rejected in one place, because it is a real option and deserves better than
silence.

**For:** UsageFoundry is already a place where the operator looks at what their agents cost; it
already has a dashboard, a card idiom, and a supervisor that walks transcripts on every guard
check; and `03-option-c`'s browser view is a page that wants a page to live on. Building one
more card is cheaper than building one more program.

**Against, and decisively:** the request is for *a command-line tool taking one session id*.
UsageFoundry knows about runs it launched, and the sessions the operator most wants to
understand include the ones it did not. Every piece of substrate inventoried above is Python;
UsageFoundry is TypeScript, so the card is a rewrite rather than a reuse, and the rewrite is of
exactly the parser whose value is its postmortems. Its own proposal set has already allocated
this surface: `01-` §6.2 records that ContextControl's `17-recommendation.md` recommends
building `04-option-see-it.md`, a per-cycle **cost** table plus one boolean — so a composition
card would be a second, differently-shaped instrument answering a different question in the
same app, with two token estimators disagreeing on the same screen. And a card cannot be
pointed at an arbitrary session id from a shell, which is the one thing the request specifies.

## What it costs to build

The copy is a week. The cost is not the copy.

**It is paid every time a parser bug is fixed in one of the two trees.** There is no mechanism
that keeps them in step and no test that fails when they drift. The failure is silent — both
parsers produce numbers — and the numbers are the product.

**And it is paid once immediately, in the thing that does not get retired.** `winnow inspect`
ships today and reports `message content 181.0 KB` and `cache_read_input_tokens 18,378,780` for
a session whose window at the last request was 219,485 (`01-` §6.1, verified by running it).
That is a real number, it is not the window, and it is presented beside a byte-share breakdown
in a way that invites exactly the misreading this whole proposal exists to prevent. Building
the correct instrument in another repository leaves the incorrect one shipping here, unmarked,
for as long as this repository exists.

## How it fails, and whether loudly

**Silently, in the drift, as above.** The second failure is quieter still: a new repository
needs its own tests, its own fixtures, its own release, its own README and its own place in the
operator's head. `00-` §6's third killer is that nobody acts on the output. A tool in a
repository nobody has installed produces no output to act on, and the cheapest possible
distribution for something whose whole value is being run casually is *being already
installed*.

## What would have to be true

**That the render wins is B or C.** A TUI library or a served page is the only argument here
strong enough to overcome the drift cost — and both are argued down in their own files.
`03-option-a` adds no dependency at all, which removes the strongest reason to leave.

**That `cli.py`'s coupling is not fixable in place.** It is: the eager `from . import
orchestrator_safe as safe` at `cli.py:23` and `from . import proxy as proxy_mod` at `:25` are a
per-invocation tax and a coupling risk, and moving them into the subparser handlers is a small,
independently good change. Measured on this tree: `import winnow.inspect` pulls 7 winnow modules
in 15 ms and touches neither `legacy.guard` nor `legacy.team` nor `proxy`; `import winnow.cli`
pulls 16 in 27 ms. **The substrate is already factored the way a subcommand needs; only the
CLI's front door is not.**

**That the operator wants to distribute it.** If this is ever published for other people's
machines, the install-surface argument becomes decisive and this option wins on that ground
alone. Nothing in `00-` says it will be.

---

**And the fact that most weakens it, stated plainly:** the reuse argument is the one everybody
expects to decide this, and it does not — 1,000 lines is a week and the postmortems can be
copied along with the comments that hold them. What decides it is the thing that stays behind.
`winnow inspect` is a shipped command that answers this exact question with the wrong
denominator, and `winnow savings` — the only command that renders the prefix readout — is
broken on `main`. Build the treemap somewhere else and both of those go on being true
indefinitely, because nothing in the new repository has any reason to touch them. Build it
here and retiring the wrong instrument is a two-line deprecation on the day the right one
lands. **A new project is the option that leaves the most wrong numbers in circulation.**
