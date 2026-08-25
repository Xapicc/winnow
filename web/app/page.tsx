import { AsciiPanel } from "@/components/AsciiPanel";
import { AsciiRule } from "@/components/AsciiRule";
import { Button } from "@/components/Button";
import { DecodeAscii } from "@/components/DecodeAscii";
import { SectionHeading } from "@/components/SectionHeading";
import { TerminalBlock } from "@/components/TerminalBlock";
import { Ticks } from "@/components/Ticks";
import { WORDMARK } from "@/lib/ascii";
import { REPO_URL, SECTIONS, SITE_NAME, SITE_TAGLINE } from "@/lib/site";

/**
 * The home page shell.
 *
 * Each of the six sections carries its heading, its one-paragraph statement and
 * its deep link. The figures, panels and worked examples that go under them are
 * a later run's; what is here is the scaffolding and the copy that fixes what
 * each section is allowed to claim.
 */

/* From the README's own blocks, unchanged. winnow publishes to no package
   channel, so the first line of any recipe is a checkout. */
const INSPECT_COMMANDS = [
  "git clone https://github.com/Xapicc/winnow",
  "cd winnow",
  "python -m winnow inspect <session-id>",
] as const;

const FILTER_COMMANDS = [
  "export WINNOW_FILTER=1",
  "python -m winnow filter --ledger ~/.winnow/filter.jsonl",
  "export ANTHROPIC_BASE_URL=http://127.0.0.1:8789",
] as const;

export default function HomePage() {
  return (
    <>
      <section className="wn-shell pt-16 pb-20 sm:pt-24">
        <p className="wn-kicker">
          stdlib only <span aria-hidden="true">·</span> no network{" "}
          <span aria-hidden="true">·</span> nothing installed
        </p>

        {/* The art is decorative; this heading carries the accessible name. */}
        <h1 className="sr-only">{SITE_NAME}</h1>

        <div className="wn-ascii-fit mt-6 max-w-[52rem]">
          <DecodeAscii art={WORDMARK} cap={30} className="wn-glow text-accent" />
        </div>

        <div className="mt-10 max-w-[68ch]">
          <p className="text-lead tracking-tight">{SITE_TAGLINE}</p>
          <p className="text-body text-fg-muted mt-4">
            <Ticks>
              {
                "A long Claude Code session is mostly tool output — across 563 transcripts and 175.6 MB of message content, `tool_result` and `tool_use` inputs are 91.6% of the bytes. Several tools will strip that for you. None of them can tell you whether stripping it saved you anything."
              }
            </Ticks>
          </p>
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-[3ch]">
          <Button href={REPO_URL} external>
            Get the source<span aria-hidden="true"> ↗</span>
          </Button>
          <Button href="#what-is-here" variant="ghost">
            what is here<span aria-hidden="true"> ↓</span>
          </Button>
        </div>

        <div className="mt-16 max-w-[68ch]">
          <AsciiPanel label="scope" tone="accent">
            <p className="text-fg-muted">
              <Ticks>
                {
                  "The pruner does not exist yet. What runs is the instrument — `winnow inspect`, `winnow filter` and `winnow savings` — and the harness that makes the inherited tool survivable under an unattended session."
                }
              </Ticks>
            </p>
            <p className="text-fg-muted mt-3">
              No claim that pruning a Claude Code session saves money has been
              made here, or anywhere else.
            </p>
          </AsciiPanel>
        </div>
      </section>

      <section className="wn-shell pb-20">
        <SectionHeading id="what-is-here" kicker="what is here">
          Six things, and two of them are absences
        </SectionHeading>

        <ul className="grid gap-0">
          {SECTIONS.map((section) => (
            <li key={section.id}>
              <a
                href={`#${section.id}`}
                className="group wn-state grid grid-cols-[4ch_1fr] items-start gap-x-[2ch] py-6 hover:bg-surface"
              >
                <span
                  aria-hidden="true"
                  className="wn-state text-small text-fg-faint pt-1 group-hover:text-accent"
                >
                  {section.index}
                </span>
                <div className="min-w-0">
                  {/* No aberration: the row already answers a hover with a fill
                      and a colour change, and a third effect on the same target
                      is the pile-up §6 is trying to avoid. */}
                  <h3 className="wn-state text-h3 font-semibold group-hover:text-accent">
                    {section.title}
                  </h3>
                  <p className="text-body text-fg-muted mt-2 max-w-[72ch]">
                    <Ticks>{section.line}</Ticks>
                  </p>
                </div>
              </a>
              <AsciiRule />
            </li>
          ))}
        </ul>
      </section>

      {/* The six section shells. A later run fills each one out with the
          figures and worked examples; the heading, the statement and the deep
          link are fixed here so that what a section may claim is settled before
          anybody writes a paragraph under it. */}
      {SECTIONS.map((section) => (
        <section key={section.id} className="wn-shell pb-20">
          <SectionHeading id={section.id} kicker={`${section.index} · ${section.id}`}>
            {section.title}
          </SectionHeading>

          <div className="wn-measure">
            <p className="text-body text-fg-muted">
              <Ticks>{section.line}</Ticks>
            </p>
            <p className="text-body text-fg-muted mt-4">
              <Ticks>{section.detail}</Ticks>
            </p>
            <div className="mt-6">
              <Button href={section.href} variant="ghost">
                {section.hrefLabel}
              </Button>
            </div>
          </div>
        </section>
      ))}

      <section className="wn-shell pb-24">
        <SectionHeading id="start" kicker="start here">
          Clone it and read one session
        </SectionHeading>

        <div className="grid items-start gap-12 lg:grid-cols-2 lg:gap-[6ch]">
          <div>
            <TerminalBlock commands={INSPECT_COMMANDS} />
            <p className="text-small text-fg-muted mt-4 wn-measure">
              <Ticks>
                {
                  "winnow publishes to no package channel, so installing means a checkout. `inspect` writes nothing: it reads one session and prints the composition readout, the six guards and `T*`."
                }
              </Ticks>
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-[3ch]">
              <Button href={REPO_URL} external>
                Get the source<span aria-hidden="true"> ↗</span>
              </Button>
              <Button href="/status" variant="ghost">
                what runs today
              </Button>
            </div>
          </div>

          <div>
            <TerminalBlock commands={FILTER_COMMANDS} />
            <p className="text-small text-fg-muted mt-4 wn-measure">
              <Ticks>
                {
                  "The filter refuses to start without `WINNOW_FILTER=1`, because running it puts a process of your own in front of your own key. It relays your auth headers upstream, holds none of its own and logs none — and it forwards the original bytes unchanged on any failure to parse or rewrite."
                }
              </Ticks>
            </p>
            <div className="mt-6">
              <AsciiPanel label="turning it off">
                <p className="text-fg-muted">
                  <Ticks>
                    {
                      "Killing the process is not the off switch. `ANTHROPIC_BASE_URL` is fixed in a client's environment when it starts, so a listener that goes away takes every request with it. On a running install, `touch ~/.winnow/filter-off` and the next request is relayed untouched."
                    }
                  </Ticks>
                </p>
              </AsciiPanel>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
