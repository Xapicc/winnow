import type { Metadata } from "next";

import { AsciiPanel } from "@/components/AsciiPanel";
import { Button } from "@/components/Button";
import { SectionHeading } from "@/components/SectionHeading";
import { SpecList } from "@/components/SpecList";
import { Ticks } from "@/components/Ticks";
import { REPO_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Status",
  description:
    "What runs today, what does not, and what has never been claimed. winnow inspect, winnow filter, winnow savings and orchestrator-safe mode run. There is no winnow fork, no winnow recover and no winnow bench.",
  alternates: { canonical: "/status" },
};

/**
 * The honest inventory. This page exists so that the home page can be short
 * about what is built without being vague about it.
 *
 * Every row is the README's own. Where the README's own Status table and its
 * opening note disagree about milestone 1, the more specific statement wins and
 * the disagreement is named rather than smoothed over — docs/design-language.md
 * §8, and the note in that file about the README's stale row.
 */

const WHAT_RUNS = [
  {
    term: "`winnow inspect`",
    detail:
      "SPEC §4's six rules, the six guards, the cache readout and `T*`. About 600 lines with 54 tests. The only command in the tree that implements the specification rather than wrapping the inherited one.",
  },
  {
    term: "`winnow filter`",
    detail:
      "The intake filter and the local proxy that carries it. Stdlib only, about 450 lines with 39 tests.",
  },
  {
    term: "`winnow savings`",
    detail:
      "Prices the filter's own ledger against the transcripts, de-duped on `tool_use_id` so a stateless filter's repeats are not counted as removals. Stdlib only, about 575 lines with 34 tests.",
  },
  {
    term: "orchestrator-safe mode",
    detail:
      "The `safe` and `inspect` groups and the gate around the vendored tool, about 1,300 lines with its tests. Built and tested; never run inside a real orchestrated cycle.",
  },
  {
    term: "the inherited tree",
    detail:
      "`src/winnow/legacy/`, `plugin/` and `tests/` — Cozempic 1.8.39 by Ruya AI, about 21,700 lines, renamed into winnow. Still not installed and not started.",
  },
] as const;

const WHAT_DOES_NOT = [
  {
    term: "`winnow fork`",
    detail: "The pruner itself. Milestone 2. Not started.",
  },
  {
    term: "`winnow recover`",
    detail: "Not started.",
  },
  {
    term: "`winnow bench`",
    detail:
      "Milestone 3, and the quality arm with it. Not started — which is why no tool here can be called superior to another.",
  },
  {
    term: "a saving",
    detail:
      "Any claim that pruning a Claude Code session saves money is unmade, by anyone.",
  },
] as const;

export default function StatusPage() {
  return (
    <div className="wn-shell py-16 sm:py-20">
      <SectionHeading as="h1" kicker="status">
        What runs, and what does not
      </SectionHeading>

      <div className="wn-measure mb-16">
        <p className="text-lead tracking-tight">
          The pruner does not exist yet. The instrument does.
        </p>
        <p className="text-body text-fg-muted mt-4">
          <Ticks>
            {
              "winnow publishes to no package channel, so installing means a checkout. Nothing on this page is a roadmap: it is the state of the tree, and the rows that say `not started` are the ones the kill criteria are written against."
            }
          </Ticks>
        </p>
      </div>

      <section className="mb-16">
        <SectionHeading id="runs" kicker="built">
          In the tree today
        </SectionHeading>
        <SpecList items={WHAT_RUNS} className="wn-measure" />
      </section>

      <section className="mb-16">
        <SectionHeading id="inspect" kicker="02 · inspect">
          The instrument, and where it misses
        </SectionHeading>

        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-[6ch]">
          <div className="wn-measure">
            <p className="text-body text-fg-muted">
              <Ticks>
                {
                  "Milestone 1's number has been produced: tier CB strips 10.2% of message content pooled and 8.8% at the median, against the 22.6% / 21.6% `docs/SPEC.md` §6 recorded and the ±3 points §9 asked it to reproduce within."
                }
              </Ticks>
            </p>
            <p className="text-body text-fg-muted mt-4">
              <Ticks>
                {
                  "It misses by 12.4 points, and 8.7 of those are one rule whose measured number was taken with a looser definition than the same document specifies. The *population* lands where SPEC §6's method says it should — 174 sessions over 400 KB of message content, 129.6 MB pooled, against a recorded 161 and 120.1 MB one day earlier — so the denominator is not the disagreement."
                }
              </Ticks>
            </p>
          </div>

          <AsciiPanel label="netted" tone="accent">
            <p className="text-fg-muted">
              <Ticks>
                {
                  "Netted against the cache — `0.1·D` earned on each turn that followed the cut, `1.9·S − 2·D` paid once — a tier-CB cut pays off in 58% of sessions and is worth +3.27% of the bill, on an optimistic bound, against the 15% SPEC §9 set as the target."
                }
              </Ticks>
            </p>
            <p className="text-fg-muted mt-3">
              Milestone 1 was built to be allowed to say that.
            </p>
          </AsciiPanel>
        </div>
      </section>

      <section className="mb-16">
        <SectionHeading id="filter" kicker="03 · filter">
          The filter, and what its table is
        </SectionHeading>

        <div className="wn-measure">
          <p className="text-body text-fg-muted">
            <Ticks>
              {
                "On a replay over 175 historical sessions the filter reaches 8.21% and is worth +3.76% of the bill, against the tier-CB pruner's 10.17% and +3.27%. The ratio is 1.1×. What separates them is variance rather than size: the filter cannot be negative, and it pays in 175 sessions out of 175 against the pruner's 97 of 168."
              }
            </Ticks>
          </p>
          <p className="text-body text-fg-muted mt-4">
            <Ticks>
              {
                "That table is a simulation — what the filter *would* have done. Running both is possible and nearly pointless: the filter takes the shared mass first, leaving the pruner 2.2% against an unchanged `S`."
              }
            </Ticks>
          </p>
          <div className="mt-6">
            <Button href="/arithmetic#no-break-even" variant="ghost">
              why there is no break-even
            </Button>
          </div>
        </div>
      </section>

      <section className="mb-16">
        <SectionHeading id="savings" kicker="04 · savings">
          The ledger, and the two things it must get right
        </SectionHeading>

        <div className="wn-measure">
          <p className="text-body text-fg-muted">
            <Ticks>
              {
                "The filter is stateless. It re-drops the same result on every later request that still carries it, so a ledger of 1,283 removal events on one install holds 49 distinct results — summing `bytes_dropped` over lines would report 27× what was removed. The repeats are not removals; they *are* the `0.1·D·T` term, and are priced at 0.1×."
              }
            </Ticks>
          </p>
          <p className="text-body text-fg-muted mt-4">
            <Ticks>
              {
                "The second is that one API request is one turn, however many records it left on disk. Claude Code writes a response as one record per content-block group and stamps every one of them with the same `requestId` and the same `message.usage`; counting records instead of requests inflates both `T` and the bill it is compared against, by 1.7 to 2.4× on that install's transcripts."
              }
            </Ticks>
          </p>
          <p className="text-small text-fg-muted mt-4">
            The figure is modelled, not billed, and the command says so in its own
            output. The bytes were never sent, so no invoice line corresponds to
            them.
          </p>
        </div>
      </section>

      <section className="mb-16">
        <SectionHeading id="safe" kicker="05 · safe">
          Six guarantees, held from outside the tree
        </SectionHeading>

        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-[6ch]">
          <div className="wn-measure">
            <p className="text-body text-fg-muted">
              <Ticks>
                {
                  "It never terminates the session it runs inside; never resumes one; has no updater, no PyPI check and no upgrade step; writes nothing to `~/.claude`; does not compete with the harness's own context and cost controls; and writes nothing into the model's memory."
                }
              </Ticks>
            </p>
            <p className="text-body text-fg-muted mt-4">
              <Ticks>
                {
                  "Nothing in `src/winnow/legacy/` was modified to do any of it — which is the more honest test: a wrapper that has to patch the thing it wraps has not shown the thing is safe to run."
                }
              </Ticks>
            </p>
          </div>

          <AsciiPanel label="not shown">
            <p className="text-fg-muted">
              The mode has never run inside a real orchestrated cycle —
              everything was exercised by hand in a container. No network call
              was proved absent, only switched off. The guard was never enabled,
              deliberately.
            </p>
          </AsciiPanel>
        </div>
      </section>

      <section className="mb-16">
        <SectionHeading id="unbuilt" kicker="06 · unbuilt">
          What does not exist
        </SectionHeading>
        <SpecList items={WHAT_DOES_NOT} className="wn-measure" />

        <div className="wn-measure mt-10">
          <AsciiPanel label="the project">
            <p className="text-fg-muted">
              If the first milestone comes back saying the cache is already warm
              at a typical resume, or that the strippable share at tier CB does
              not reproduce, the kill criteria say to stop — and stopping then is
              the intended outcome rather than a failure of it.
            </p>
          </AsciiPanel>
        </div>
      </section>

      <div className="wn-measure flex flex-wrap items-center gap-[3ch]">
        <Button href={REPO_URL} external>
          Get the source<span aria-hidden="true"> ↗</span>
        </Button>
        <Button href="/arithmetic" variant="ghost">
          the arithmetic
        </Button>
      </div>
    </div>
  );
}
