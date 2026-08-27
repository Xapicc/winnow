# Option H — a content-addressed recall store keyed on `tool_use_id`

**Verdict: rejected, and on a ground neither side of the usual argument uses.** The bytes are
already on disk. Claude Code writes every result to the transcript whether or not the filter
kept it off the wire, so the recovery the store would provide exists today and is unbuilt —
what is missing is a reader, not a store.

## What it is

The filter's pointer ends *"Not cached, not stored. Re-run the call if it is needed again"*
(`filter.py:93-96`), and the docstring above it is explicit that this is a deliberate weakening
of the pruner's promise:

> Shorter than the pruner's, and deliberately so — it carries no `winnow recover` command,
> because the filter keeps no copy. The recovery path is SPEC §7 route 1, the file system,
> which returns fresher bytes than these were. Saying otherwise would be a promise nothing
> here can keep.

The proposal is to make it keepable: a local content-addressed store, keyed on `tool_use_id`
with the content's sha256 as the address, written by the proxy as it drops each result, and a
`winnow recover` that reads it. The pointer would then carry a digest and a command, exactly as
`rules.POINTER_TEMPLATE` (`rules.py:539-542`) does for the pruner.

It is, on its face, exactly the "fourth store" [docs/SPEC.md](../../docs/SPEC.md) §3 refuses:

> A database, index, or content store — `ContextControl/01-` calls this "a fourth store" and
> forbids it: it would need its own retention horizon, liveness query and storage accounting.
> Winnow's only persistent state is the forked transcript itself.

## The case for it, argued properly rather than dismissed

Three things are genuinely true and worth putting on the record before the rejection.

**The sentence "[w]innow's only persistent state is the forked transcript itself" is no longer
accurate.** Winnow now writes the filter's ledger (`~/.winnow/filter.jsonl`),
`winnow trial`'s arm ledger, and forks. So the literal statement has already moved, and an
option should be judged against the reading of §3 that survives — which
[01-constraints.md](01-constraints.md) §K5 states as *a store the tool reads back to answer a
question*. The three existing artefacts are append-only records that nothing consults to make a
decision. A recall store is not; it is read back, by definition.

**Route 1 returns fresher bytes, and fresher is not the same as equivalent.** SPEC §7 makes
this a feature — a re-read after an edit is *more* correct than the retained copy — and for a
`Read` it plainly is. It is weaker for the filter's actual rule set: a `git status` taken
before three commits, an `ls` of a directory since rebuilt, a `find` over a tree that has
moved. Re-running answers "what is true now", and the removed result answered "what was true
then". If anyone ever wants to know why a session did what it did, those are different
questions.

**The pointer's own text overstates the loss to the operator.** *"Not cached, not stored"* is
true of winnow and reads as though the bytes are gone. They are not, for the reason below.

## Why it is unnecessary: the transcript already holds them

[docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5 records the fact as a *problem*:

> **The filter never touches the transcript**: Claude Code writes what it holds, which still
> contains every byte the API never saw. So `winnow inspect` read off disk overstates both *D*
> and *S* for any filtered session…

That is the reason `--ledger` exists ([01-constraints.md](01-constraints.md) §K7). Read the
same sentence as a capability rather than a hazard and the store disappears: **for every result
the filter drops, the full original bytes are sitting in
`~/.claude/projects/<project>/<session>.jsonl`, in the `tool_result` block carrying that
`tool_use_id`, untouched.** The ledger already records `request_id` and `tool_use_id` per
removal (`filter.py:301-316`), and `savings.find_transcripts` (`savings.py:284-306`) already
joins `request_id` to a transcript path by a streaming sweep.

So a `winnow recover` for the filter is: take the pointer's `tool_use_id`, join through the
ledger to the transcript, find the block, print its content. **No new storage, no retention
horizon, no liveness query, no storage accounting, and no additional bytes beside a
credential.** Everything the store was for is available from two files winnow already reads.

Three caveats, none of which the store fixes better:

- **The transcript is deletable.** `ContextControl/01-` names it — *"`--resume` needs a file
  another sweep is entitled to delete… A scheme that treats session files as disposable is on
  the other side of that decision and has to say so."* DECISIONS §D2 already accepts that
  exposure for the pruner, where the original transcript *is* the recovery source of record.
  A store would survive the sweep; it would also *be* the thing the sweep does not know about,
  and milestone 2 already has an unanswered disk-cost criterion (*"a week of accumulated disk
  cost, measured rather than estimated"*) that a second growing artefact would double.
- **The transcript lags.** The vendor hooks reference says it *"is written asynchronously and
  may lag the in-memory conversation"* (SPEC §3, DECISIONS §2). That matters for a tool
  editing a live session; it does not matter for a lookup taken after the fact, which is the
  only kind of recovery either the store or the transcript can serve.
- **`request_id` does not always join.** [docs/COZEMPIC.md](../../docs/COZEMPIC.md) §3.5.2
  reports "34 priced, 15 unjoinable, 0 unpriceable" on the one real ledger — about three joins
  in ten failing — and
  [08-option-mcp-and-subagent-output.md](08-option-mcp-and-subagent-output.md) names a
  candidate cause — `find_transcripts` globs `*/*.jsonl` and so cannot see a sub-agent
  session. That is a bug in the join, and fixing a join is cheaper than operating a store.

## And even stored, the model could not reach it

The pruner's `winnow recover` is an *operator* command: a person types it and reads the output.
The filter's failure mode is different — the thing that lost the bytes is the model, mid-run,
and it cannot run a CLI command.

Giving the model a recovery route means giving it a tool, which means an MCP server, which
[docs/SPEC.md](../../docs/SPEC.md) §3 refuses with a price: *"[e]very added tool definition
sits at the top of the invalidation cascade and costs a standing per-turn charge —
`ContextControl/12-` priced one added tool definition at **$8.14–$8.26/week** on that install,
against a **$0.14** benefit per use."*

So the store would have to earn $8.14–$8.26 a week, before its own cost, from recoveries the
model performs. On this corpus the filter drops 4,709 results across 866 sessions. For the
standing charge alone to break even at $0.14 a use, the model would have to recover about **58
results a week** — against a rule set whose entire design bet, stated in SPEC §7, is that *"a
stripped result is mostly never wanted again"*, backed by verbatim re-reads being 0.3% of
tool-result bytes.

**Without the MCP server the store serves only the operator, and the operator already has the
transcript. With it, the store has to pay a bill this project has already refused to pay
twice.**

## The argument that closes it: the filter's three rules are the three route 1 covers

This is the decisive point and it is specific to *this* rule set rather than to stores in
general.

SPEC §7 keeps route 2 — the pointer's recovery command — for the case route 1 cannot serve:
*"a Bash result that is not reproducible, a `WebFetch` of a page that has changed."* Look at
what the filter can actually claim (`filter.py:99-120`):

| Rule | What it fires on | Route 1 recovery |
| --- | --- | --- |
| C1 | `Glob`, `LS`, `Grep` in a locator mode | re-run the search |
| C3 | `Bash` matching `VERIFICATION_RE` with `is_error: false` | re-run the test |
| B2 | `Bash` whose `bash_head` is `ls`, `cat`, `git status`, … | re-run the command |

**Every one is a re-runnable inspection of local state.** There is no `WebFetch` in the set, no
network call, no non-reproducible command — `rules.INSPECTION_HEADS` (`rules.py:75-83`) is a
list of read-only shell utilities and `INSPECTION_GIT_SUBCOMMANDS` is `status`, `log`, `diff`,
`show`, `branch`, `remote`, `ls-files`. The filter's rule set is, by construction, the subset
of SPEC §4 for which route 1 always works.

So the store is insurance against a class of loss the rule set already excludes. Route 2 exists
in the pruner because the pruner reaches C2, B1 and A1 and can therefore strip a `WebFetch`
that C2 marks as duplicated. The filter cannot fire those rules —
[01-constraints.md](01-constraints.md) §K1 — so it cannot reach the class route 2 was built
for.

**That is the argument, and it inverts if any of the widening options is taken.**
[06](06-option-per-tool-byte-cap.md) and [08](08-option-mcp-and-subagent-output.md) would put
`WebFetch` pages (3,505,730 bytes here), MCP results and `Agent` transcripts inside the
filter's reach, and **none of those is reproducible.** A browser screenshot cannot be
re-taken; a delegated agent's answer cannot be re-derived without re-running the agent.

## The position

**Reject the store. Build the reader.** `winnow recover` for a filter pointer, joining
ledger → transcript → block, is a command with no new persistent state, and it converts the
pointer's *"Not cached, not stored"* from an accurate statement about winnow into an accurate
statement that also tells the operator where the bytes are.

**And write down the condition that would reopen it**, because two options in this set create
it: if the filter is ever widened to a result that cannot be re-produced by re-running its own
call — a `WebFetch`, an MCP screenshot, an `Agent` return — then route 1 no longer covers the
rule set, the transcript becomes the only copy, and the question is live again. It should be
answered then, on the widened rule set, and not now on a rule set that does not need it.

## Which constraints it strains

- **§K5** — directly, on the reading that survives. A store read back to decide is what §3
  refuses, and this is one.
- **§K2** — a store is a second file handle and a write path in the credential process, and
  the thing it writes is verbatim tool output, which SPEC §10 says *"routinely contain[s]
  credentials pasted into a Bash command"*. The `--explain` warning exists for exactly that
  content; a store would make it durable on disk by default rather than only when an operator
  asks for it.
- **§K6** — a store that cannot be written must not stop the request. That is easy to arrange
  (the ledger already does it, `proxy.py:265-277`) and worth stating, because the pointer would
  then promise a recovery that silently is not there.

## The strongest case against the rejection

**That "the transcript has it" is true today and is not a property anyone guaranteed.** It
depends on Claude Code continuing to write the full result to disk, which is a vendor
behaviour, undocumented in this respect, and DECISIONS §4 already lists the transcript format
under rabbit holes: *"[t]he format is undocumented and will change."* If a future CLI wrote
what it *sent* rather than what it *held*, the filter's bytes would vanish from disk and this
whole rejection would fail in one release — silently, because nothing checks.

That is a real risk and it argues for a check rather than a store: a `winnow savings`-side
assertion that a sample of ledger `tool_use_id`s still resolve to full content in the
transcript, reported in the readout. One line of output, no persistence, and it fails loudly
the first time the assumption stops holding — which is what SPEC §10 asks for and what a store
would have bought at forty times the price.
