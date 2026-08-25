import type { Metadata } from "next";

import { AsciiPanel } from "@/components/AsciiPanel";
import { Button } from "@/components/Button";
import { ComparisonTable } from "@/components/ComparisonTable";
import { SectionHeading } from "@/components/SectionHeading";
import { SpecList } from "@/components/SpecList";
import { TerminalBlock } from "@/components/TerminalBlock";
import { Ticks } from "@/components/Ticks";
import { FilterPositionDemo } from "@/components/demos/FilterPositionDemo";
import { UnnettedDemo } from "@/components/demos/UnnettedDemo";
import { REPO_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: "The intake filter",
  description:
    "winnow filter is a local pass-through proxy that keeps a spent tool result out of the cached prefix rather than editing it out later, so there is no break-even term to pay off. It sits in the operator's credential path.",
  alternates: { canonical: "/filter" },
};

/**
 * The filter, and the command that prices it.
 *
 * Two things this page is careful about, both because the README is. The
 * comparison table is a *simulation* — a replay over historical sessions, not a
 * record of anything the filter did — and `winnow savings` is the instrument;
 * the table's own caption says so rather than a note further down. And the
 * filter is in the operator's credential path, which is stated here, on the page
 * that describes it, rather than somewhere quieter.
 */

/* README, "The intake filter". The toggle is not optional: the proxy refuses to
   start without it. */
const START_COMMANDS = [
  "export WINNOW_FILTER=1",
  "python -m winnow filter --ledger ~/.winnow/filter.jsonl",
  "export ANTHROPIC_BASE_URL=http://127.0.0.1:8789",
] as const;

const SAVINGS_COMMANDS = ["python -m winnow savings"] as const;

const OFF_COMMANDS = ["touch ~/.winnow/filter-off"] as const;

/* docs/SPEC.md section 4, and the README's note on which three can fire without
   hindsight. */
const WIRE_RULES = [
  {
    term: "C1 locator",
    detail:
      "`Glob` and `LS`, and `Grep` where `output_mode` is `files_with_matches` or `count`. The output is a list of paths whose only consumer is the call that followed it.",
  },
  {
    term: "C3 passing verification",
    detail:
      "`Bash` matching the verification pattern — `npm test`, `pytest`, `go test`, `cargo test`, `tsc`, `ruff`, `mypy` and their neighbours — and only where `is_error` is false. A failing verification is never stripped: the failure is the information.",
  },
  {
    term: "B2 Bash inspection",
    detail:
      "`Bash` where the first token of the first segment before `&&` or `|` matches the inspection pattern, so a pipeline headed by `ls` or `git status` counts and one headed by `python` does not, whatever follows.",
  },
] as const;

const HINDSIGHT_RULES = [
  {
    term: "C2 exact duplicate",
    detail:
      "Strips the *earlier* of two byte-identical results, which means knowing a later one arrives.",
  },
  {
    term: "B1 superseded read",
    detail:
      "Strips a `Read` because a later `Read` covers it. The later one has not happened yet.",
  },
  {
    term: "A1 read then written",
    detail:
      "Strips a `Read` because a later `Edit` or `Write` made it stale. Opt-in even in the pruner, and the rule `docs/SPEC.md` section 4 itself calls the most likely to be wrong.",
  },
] as const;

export default function FilterPage() {
  return (
    <div className="wn-shell py-16 sm:py-20">
      <SectionHeading as="h1" kicker="the intake filter">
        Never let the bytes into the cache
      </SectionHeading>

      <div className="wn-measure mb-16">
        <p className="text-lead tracking-tight">
          The one position that pays nothing.
        </p>
        <p className="text-body text-fg-muted mt-4">
          <Ticks>
            {
              "A pruner edits a conversation that is already cached, so it pays `1.9·S − 2·D` once and has to earn it back. `winnow filter` is a local pass-through proxy that keeps the bytes out of the cached prefix in the first place: a tool result a rule would strip is sent in full on the one request the model acts on it, placed after the last `cache_control` breakpoint so the API never writes it to cache, and is dropped on the next request."
            }
          </Ticks>
        </p>
        <p className="text-body text-fg-muted mt-4">
          <Ticks>
            {
              "It runs. `winnow filter` is `src/winnow/filter.py` and `proxy.py` — stdlib only, about 450 lines with 39 tests."
            }
          </Ticks>
        </p>
      </div>

      <section className="mb-16">
        <SectionHeading id="position" kicker="position">
          Where it acts in a turn
        </SectionHeading>

        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-[6ch]">
          <div className="wn-measure">
            <p className="text-body text-fg-muted">
              <Ticks>
                {
                  "Position is the whole mechanism. The full send sits past the last `cache_control` breakpoint, so the API never writes it — and what is never written is never read back at 0.1× on any later turn either."
                }
              </Ticks>
            </p>
            <p className="text-body text-fg-muted mt-4">
              <Ticks>
                {
                  "Nothing in the cached prefix is edited, so nothing is invalidated. That is the difference the arithmetic turns on, and it is a difference of position rather than of policy: the rules are the same rules."
                }
              </Ticks>
            </p>
            <div className="mt-6">
              <Button href="/arithmetic#no-break-even" variant="ghost">
                why that costs nothing
              </Button>
            </div>
          </div>

          <FilterPositionDemo />
        </div>
      </section>

      <section className="mb-16">
        <SectionHeading id="rules" kicker="rules">
          Three of the six can fire on the wire
        </SectionHeading>

        <div className="wn-measure mb-8">
          <p className="text-body text-fg-muted">
            <Ticks>
              {
                "The filter reaches less than the pruner, and the reason is structural rather than a matter of tuning: a rule that has to see the conversation's future cannot run on a request that is going out now."
              }
            </Ticks>
          </p>
        </div>

        <SpecList items={WIRE_RULES} className="wn-measure" />

        <div className="wn-measure mt-10">
          <h3 className="text-h3 font-semibold tracking-tight">
            And three of them cannot
          </h3>
          <p className="text-body text-fg-muted mt-4">
            <Ticks>
              {
                "Each of these decides what to strip by looking at something that has not happened yet. A policy that did would also change the prefix under the cache, which is the cost the filter exists to avoid."
              }
            </Ticks>
          </p>
        </div>

        <SpecList items={HINDSIGHT_RULES} className="wn-measure mt-4" />

        <div className="wn-measure mt-8">
          <AsciiPanel label="guards">
            <p className="text-fg-muted">
              <Ticks>
                {
                  "The six universal guards apply before any rule, at any tier: the last results in the session are kept, a result under `--min-bytes` is kept, `is_error: true` is never stripped, and a pointer longer than the content it replaces is not written."
                }
              </Ticks>
            </p>
          </AsciiPanel>
        </div>
      </section>

      <section className="mb-16">
        <SectionHeading id="terms" kicker="the cost model">
          What it avoids, term by term
        </SectionHeading>

        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-[6ch]">
          <div className="wn-measure">
            <p className="text-body text-fg-muted">
              <Ticks>
                {
                  "Per result of `D` tokens over `T` following turns, the baseline is a 2.0× cache write plus a 0.1× read on every later turn. The filter pays 1.0× once and nothing after."
                }
              </Ticks>
            </p>
            <p className="text-body text-fg-muted mt-4">
              <Ticks>
                {
                  "There is no break-even term. It is cheaper from the first request, at every `S/D`, which is the one thing the pruner cannot say."
                }
              </Ticks>
            </p>
            <p className="text-small text-fg-muted mt-4">
              <Ticks>
                {
                  "The terms stay apart rather than blending into one number, because that is how `winnow savings` reads them out — the avoided write and the avoided reads are different quantities and only one of them grows with the length of the session."
                }
              </Ticks>
            </p>
          </div>

          <UnnettedDemo />
        </div>
      </section>

      <section className="mb-16">
        <SectionHeading id="simulation" kicker="the replay">
          The table is a simulation
        </SectionHeading>

        <div className="wn-measure mb-8">
          <p className="text-body text-fg-muted">
            <Ticks>
              {
                "The 8.21% comes from replaying the three no-hindsight rules over 175 historical sessions — what the filter *would* have done, not a record of anything it did. It is stated here with that attached, because a share of a bill reads like an invoice line and this one is not."
              }
            </Ticks>
          </p>
        </div>

        <ComparisonTable
          className="wn-measure"
          rowHeader="what was replayed"
          columns={["reaches", "share of the bill", "sessions where it pays"]}
          rows={[
            {
              label: "intake filter",
              cells: ["8.21%", "+3.76%", "175 of 175"],
              emphasis: true,
            },
            {
              label: "pruner, tier CB",
              cells: ["10.17%", "+3.27%", "97 of 168"],
            },
          ]}
          caption="A replay over 175 historical sessions, from `README.md`, 'The intake filter', with the detail in `docs/COZEMPIC.md` section 3.5. Modelled, not billed. The ratio is 1.1×, and what separates the two is variance rather than size: the filter cannot be negative."
        />

        <div className="wn-measure mt-8">
          <p className="text-body text-fg-muted">
            <Ticks>
              {
                "Running both is possible and nearly pointless. The filter takes the shared mass first, leaving the pruner 2.2% against an unchanged `S` — and the pruner does not exist yet in any case."
              }
            </Ticks>
          </p>
        </div>
      </section>

      <section className="mb-16">
        <SectionHeading id="savings" kicker="the instrument">
          What the ledger says it did
        </SectionHeading>

        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-[6ch]">
          <div className="wn-measure">
            <p className="text-body text-fg-muted">
              <Ticks>
                {
                  "`winnow savings` reads `~/.winnow/filter.jsonl`, joins each line to the Claude Code transcript on `request_id` to recover which session it belongs to and how many API turns followed it, and prices it. The two numbers are not comparable and the command does not try: the simulation is a corpus average, this is one install's ledger over however long it has been on."
                }
              </Ticks>
            </p>
            <p className="text-body text-fg-muted mt-4">
              <Ticks>
                {
                  "It is `src/winnow/savings.py` — stdlib only, about 575 lines with 34 tests. The readout splits the avoided write from the avoided reads rather than blending them, and names the lines it could not join or could not price."
                }
              </Ticks>
            </p>
          </div>

          <div>
            <TerminalBlock commands={SAVINGS_COMMANDS} />
            <p className="text-small text-fg-muted wn-measure mt-4">
              <Ticks>
                {
                  "`--json` for the machine-readable form. The figure is modelled, not billed, and the command says so in its own output: the bytes were never sent, so no invoice line corresponds to them."
                }
              </Ticks>
            </p>
          </div>
        </div>

        <div className="wn-measure mt-10">
          <h3 className="text-h3 font-semibold tracking-tight">
            The two things it has to get right
          </h3>
          <p className="text-body text-fg-muted mt-4">
            <Ticks>
              {
                "The filter is stateless. It re-drops the same result on every later request that still carries it, so a ledger of 1,283 removal events on one install holds 49 distinct results — summing `bytes_dropped` over lines would report 27× what was removed. The repeats are not removals; they *are* the `0.1·D·T` term, and are priced at 0.1×. De-duplication is on `tool_use_id`, with a conservative `(tool, rule, bytes)` fallback for lines written before that field existed."
              }
            </Ticks>
          </p>
          <p className="text-body text-fg-muted mt-4">
            <Ticks>
              {
                "One API request is one turn, however many records it left on disk. Claude Code writes a response as one record per content-block group — the text, then each `tool_use` — and stamps every one of them with the same `requestId` and the same `message.usage`. Counting records instead of requests inflates both `T` and the bill it is compared against, by 1.7 to 2.4× on that install's transcripts."
              }
            </Ticks>
          </p>
        </div>
      </section>

      <section className="mb-16">
        <SectionHeading id="credentials" kicker="before you run it">
          It is in your credential path
        </SectionHeading>

        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-[6ch]">
          <div className="wn-measure">
            <AsciiPanel label="credentials" tone="accent">
              <p className="text-fg-muted">
                <Ticks>
                  {
                    "It relays your auth headers upstream, holds none of its own and logs none — but an operator running it has put a process of their own in front of their own key."
                  }
                </Ticks>
              </p>
              <p className="text-fg-muted mt-3">
                <Ticks>
                  {
                    "It refuses to start without `WINNOW_FILTER=1` for that reason, and forwards the original bytes unchanged on any failure to parse or rewrite: it must not be the thing that breaks a run."
                  }
                </Ticks>
              </p>
            </AsciiPanel>
          </div>

          <div>
            <TerminalBlock commands={START_COMMANDS} />
            <p className="text-small text-fg-muted wn-measure mt-4">
              <Ticks>
                {
                  "The third line is what the proxy prints. Point the client at it and every request goes through the filter."
                }
              </Ticks>
            </p>
          </div>
        </div>
      </section>

      <section className="mb-16">
        <SectionHeading id="off" kicker="turning it off">
          The two ways are not equivalent
        </SectionHeading>

        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-[6ch]">
          <div className="wn-measure">
            <p className="text-body text-fg-muted">
              <Ticks>
                {
                  "Set the toggle blank and restart for the full off. On a *running* install, what can be turned off is the rewriting and not the proxy: `touch ~/.winnow/filter-off` and the next request is relayed untouched. Remove the file to resume."
                }
              </Ticks>
            </p>
            <p className="text-body text-fg-muted mt-4">
              <Ticks>
                {
                  "Killing the process is not the off switch. `ANTHROPIC_BASE_URL` is fixed in a client's environment when it starts, so a listener that goes away takes every request with it."
                }
              </Ticks>
            </p>
          </div>

          <div>
            <TerminalBlock commands={OFF_COMMANDS} />
          </div>
        </div>
      </section>

      <div className="wn-measure flex flex-wrap items-center gap-[3ch]">
        <Button href={REPO_URL} external>
          Get the source<span aria-hidden="true"> ↗</span>
        </Button>
        <Button href="/status" variant="ghost">
          what runs today
        </Button>
      </div>
    </div>
  );
}
