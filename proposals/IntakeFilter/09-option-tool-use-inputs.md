# Option G — rewrite `tool_use` inputs, not only `tool_result`s

**Verdict: rejected.** The prize is the largest single untouched class in the conversation and
the rejection is not close: it is forbidden twice in this repository's own documents, it
breaks the invariant the filter's own decision procedure runs on, and on the one sub-case that
survives all of that, 41% of the mass belongs to files the session comes back to.

## What it is

`README.md`'s opening figure is that `tool_result` **and** `tool_use` inputs are 91.6% of
message content. The filter rewrites only the first. The proposal is to reach the second — most
obviously `Write.content`, which carries a whole file into the prefix and keeps it there for
the rest of the session.

**Measured here, 2026-08-27**, over this container's 866 main-session transcripts:

| Tool | Input bytes | Share of all `tool_use` input | Share of message content |
| --- | ---: | ---: | ---: |
| `Write` | 22,832,251 | 33.92% | **8.34%** |
| `Edit` | 18,509,899 | 27.50% | 6.76% |
| `Bash` | 17,781,688 | 26.42% | 6.50% |
| `mcp__uf__propose_run` | 3,387,921 | 5.03% | 1.24% |
| `Workflow` | 1,239,592 | 1.84% | 0.45% |
| `Read` | 839,951 | 1.25% | 0.31% |
| `Agent` | 794,820 | 1.18% | 0.29% |
| **all `tool_use` inputs** | **67,312,101** | 100% | **24.59%** |

against SPEC §1's 25.8% over its own 563 transcripts, so the class has not moved. **`Write`
inputs alone are 8.34% of message content — almost exactly the size of everything the intake
filter reaches (8.49%).** Taking them would roughly double the filter's reach in one change.

And the intake filter is the *only* place it could be done. The pruner cannot: `winnow
recover`, the pointer-ID scheme and G5's re-derivation all read the transcript's `tool_use`
blocks, and DECISIONS §D2 makes the original the archive of record. A wire rewrite touches
nothing on disk. So this is not a bad idea in the wrong place; it is an idea whose only
possible place is here.

## Where it is forbidden, in this repository's own words

[docs/SPEC.md](../../docs/SPEC.md) §4, first sentence of the section:

> A rule may only fire on the `content` of a `tool_result` block. It may never touch a
> `tool_use` block, assistant text, user text, `thinking`, or any non-message record.

[DECISIONS.md](../../docs/DECISIONS.md) §D3 is the decision, and it already considered exactly
this option and named its size:

> **Rejected:** stripping `tool_use` inputs too, which is 25.8% of message content **[measured
> in SPEC §1]** and therefore tempting. Rejected because the input is what makes a pointer
> legible, and because `Write` and `Edit` inputs *are* the change the session made. **Cost of
> being wrong:** winnow leaves a quarter of the volume untouched by construction.

Both also copy the vendor's own default: `clear_tool_uses_20250919` ships
`clear_tool_inputs: false`, so the call and its arguments survive and only the answer is
cleared. That is weak evidence, and SPEC §4 says so by citing it as
`[[Mid-Session Context Mutation with Claude]]` at medium confidence — but it is evidence
pointing one way and there is none pointing the other.

A proposal set is allowed to reopen a decision. What it is not allowed to do is reopen it
without answering the reason. §D3's reason is *"`Write` and `Edit` inputs are the change the
session made"*, and everything below is an attempt to test that sentence.

## It breaks the filter's own decision procedure

This is the argument that is not in either document, because it is a property of the
implementation rather than of the policy.

`rule_for(name, tool_input, is_error)` (`filter.py:99-120`) reads the tool name and the tool
input. Those are two of its three inputs, and
[02-what-runs-today.md](02-what-runs-today.md) records the assumption as invariant **I3**:
`tool_use.name` and `tool_use.input` are never rewritten, by anyone. **This option is the
proposal to break I3, and the thing it breaks first is the filter.**

Concretely. A `Bash` call whose `command` is `ls -la` yields B2. Elide that command and
`is_inspection` (`rules.py:343-351`) sees a marker string, `bash_head` returns the marker, and
`rule_for` returns `None`. The verdict on the *result* has moved because of a rewrite the
filter itself performed on a different block.

Trace it through and the damage is not a cache break — it is worse, because it is silent. A
result already replaced by a pointer is skipped by `POINTER_RE` (`filter.py:261`) and stays
pointered, so the bytes do not flap. A result **not yet** dropped — the deferred one, and every
result below `min_bytes` — stops being a candidate the moment its input is elided, and is
therefore never dropped at all. The filter would quietly lose reach in proportion to how well
the input elision worked, and nothing would report it: the ledger records what was removed, not
what stopped being removable.

The two rewrites are coupled, `apply` does not order them, and nothing proves the pair
monotone under [01-constraints.md](01-constraints.md) §K1. Making it safe means either
excluding from elision every input a rule reads — which is `Bash.command`, 6.50% of message
content, a quarter of the class — or evaluating `rule_for` against a *pre-elision* copy of the
inputs, which means the filter holds two renderings of the same request and must prove they
never disagree. Neither is a small change to a 350-line component in the credential path.

## The typed-input problem

`tool_result.content` is documented as a string or a list of blocks, and either is legal, which
is why substituting a pointer is safe (§K8). **`tool_use.input` is not free-form: it is typed by
that tool's own `input_schema`**, which the proxy has in `body["tools"]` and never reads.

Replacing `Write.content` with a marker string still produces a string, so it type-checks. But
it produces a request in which the model appears to have written that marker to the file. For
`Bash`, replacing `command` produces an apparent command that was never run. For a tool with a
typed field — a number, an enum, an array — a marker of the wrong type is not a lie, it is
malformed.

Whether the API validates a *past-turn* `tool_use.input` against the current tool schema is not
established here and cannot be established from this checkout. If it does, the failure mode is
a 400 on a request the filter has already rewritten, and §K6's passthrough does not cover it:
`_rewrite` forwards the original bytes when the *filter* fails, not when the *upstream* rejects
what the filter produced. **The option would need a new failure path, and that path is a retry
with the original body — the one thing `proxy.py:12-14` says it deliberately does not do.**

## The one sub-case that survives, and the number that ends it

Strip everything a rule reads, everything typed, and everything §D3 names as "the change the
session made", and what is left is `Write.content`: a file the session created, which is on
disk, which SPEC §7 route 1 recovers by reading, and which is 8.34% of message content.

That is the honest version of this option, and it is genuinely tempting: 2,741 `Write` calls
on this corpus, mean input 8,371 bytes, median 6,556.

**Measured here:** of those 2,741 calls, **789 (28.8%) write a `file_path` that is `Read`,
`Edit`ed or `Write`n again later in the same session, and those carry 9,402,156 bytes — 41.0%
of the whole `Write` input mass.**

Two fifths of the prize belongs to files the session demonstrably comes back to. And that is a
*lower* bound on the mass that mattered, for exactly the reason SPEC §5.1 gives about the
39.5%-never-mentioned-again proxy: a path that never recurs may still have been what decided
the next edit, and the reasoning that would say so is stripped from the transcript before it
reaches disk. A rule with a 41% measured miss rate on the only proxy available fails SPEC §9's
90% bar before anyone labels a single sample.

It is also worth stating which way the recovery runs. For a `tool_result`, route 1 returns
*fresher* bytes than were removed — SPEC §7 makes that the primary path and says the file
system is more correct than the retained copy. For a `Write` input the relation inverts: the
file on disk is the *consequence* of the input, so re-reading it recovers what the write
achieved and not what the session intended, and if anything edited the file in between it
recovers neither. **The one class where §7's retrieval argument is strongest is the class this
option does not touch, and the one it does touch is where that argument is weakest.**

## Which constraints it strains

- **§K1** — the elision itself is admissible (a size threshold on the input's own bytes is
  static). The coupling with `rule_for` is not, and that is the failure.
- **§K6** — the typed-input problem creates a failure the passthrough does not cover.
- **§K8** — substitution discipline was written for `tool_result.content`, which is untyped.
  It does not transfer.
- **§D3, SPEC §4** — a straight contradiction, argued above rather than waved at.

## What it breaks

**The pointer stops being legible.** SPEC §4: *"Keeping the input is what makes the pointer
legible."* A conversation in which both `[winnow: Bash result removed…]` and the command that
produced it are markers is a conversation with no account of what happened, and the operator
reading `--explain` gets nothing to argue with — which is DECISIONS §D6's whole design, rules
shipping as data an operator can read and disable.

**A1 loses its rationale.** SPEC §4 A1 justifies stripping a pre-edit `Read` on the grounds
that *"the `Edit` block itself carries `old_string` and `new_string`, which is the part the
session acted on"*. Elide `Edit` inputs — 6.76% of message content, the second-largest slice —
and A1's argument for taking 7.52% of message content **[measured here]** no longer holds. The
two options are not independent: this one, taken widely, deletes the justification for the
largest rule in the pruner.

## The strongest case for it, stated fairly

The filter's ceiling is set by SPEC §4's first sentence and not by anything measured. §D3 says
so in its own cost-of-being-wrong line: *"winnow leaves a quarter of the volume untouched by
construction. Its ceiling is the 65.8% that is `tool_result`."* A quarter of the conversation
is exempt because a specification written before any of this was built drew a boundary there,
copying a vendor default whose own evidence grade is medium and which was never measured
against anything.

And the class has one property `tool_result` does not: **`Write.content` is guaranteed
recoverable.** A `Bash` result may not be reproducible and SPEC §7 keeps route 2 for that case;
a file the session wrote is on disk by definition, and the write succeeded or the result said
so.

The reply is the 41%, and it is enough on its own. But the case is strong enough that the
honest close is not "never" — it is **that this belongs in milestone 3 as an arm, not in
`filter.py` as a change.** SPEC §9's harness compares a filtered session against an unfiltered
one on task success within a ±5-point equivalence bound; a third arm that also elides
`Write.content` costs one flag and answers §D3's sentence with a number instead of a
judgement. That is the only thing that would move this verdict, and nothing in this proposal
set can substitute for it.
