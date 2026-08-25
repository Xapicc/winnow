import type { Metadata } from "next";

import { AsciiPanel } from "@/components/AsciiPanel";
import { Button } from "@/components/Button";
import { SectionHeading } from "@/components/SectionHeading";
import { SpecList } from "@/components/SpecList";
import { TerminalBlock } from "@/components/TerminalBlock";
import { Ticks } from "@/components/Ticks";
import { MilestoneMissDemo } from "@/components/demos/MilestoneMissDemo";
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
 * the disagreement is named on the page rather than smoothed over — see the
 * "two readings" panel below, and docs/design-language.md §8 rule 14. A later
 * run that finds this reconciled upstream should delete the panel, not the care.
 *
 * No `§` and no `±` in rendered copy: neither glyph is in the shipped font
 * subset, so both would fall back to a system font at a different advance
 * width. `lib/font.test.tsx` checks it; docs/design-language.md §2 records it.
 */

const INSPECT_COMMANDS = [
  "python -m winnow inspect <session-id>",
  "python -m winnow inspect <session-id> --json",
  "python -m winnow inspect <session-id> --tier CBA",
] as const;

const SAFE_COMMANDS = [
  "export WINNOW_ORCHESTRATOR=1",
  "python -m winnow safe check",
  "python -m winnow safe plugin-dir --out ./out",
  "python -m winnow safe run -- list",
] as const;

const INSTALL_COMMANDS = [
  "git clone https://github.com/Xapicc/winnow",
  "cd winnow",
  "PYTHONPATH=src python3 -m unittest tests.test_orchestrator_safe",
] as const;

const WHAT_RUNS = [
  {
    term: "`winnow inspect`",
    detail:
      "Section 4 of `docs/SPEC.md`, its six rules, the six guards, the cache readout and `T*`. About 600 lines with 54 tests. The only command in the tree that implements the specification rather than wrapping the inherited one.",
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

/* README, "Orchestrator-safe mode". Six, each argued and evidenced in section 8
   of docs/USAGEFOUNDRY.md, and each held from outside the tree it wraps. */
const GUARANTEES = [
  {
    term: "no termination",
    detail:
      "It never terminates the session it runs inside. The guard daemon cannot be started and `guard-watchdog --fix`, which signals, is refused. Not deferred: the harness spawns headless, so there is no interactive quit to defer to.",
  },
  {
    term: "no resume",
    detail:
      "`--resume` and session identity belong to the harness, so `reload`, which spawns a `claude --resume` watcher, is refused.",
  },
  {
    term: "no updater",
    detail:
      "No auto-update, no PyPI check, no version drift — and not switched off but removed. There is no updater module, no `self-update` subcommand and no upgrade step in the SessionStart hook, so no code path installs a package.",
  },
  {
    term: "no writes to `~/.claude`",
    detail:
      "That directory is a bind mount shared with the host. No global hook installation and no `settings.json` the mode does not own; loading happens through `--plugin-dir`, and the checkpoint the vendored tool would write inside the mount goes to winnow's own data directory instead.",
  },
  {
    term: "no competing controls",
    detail:
      "The harness owns `--autocompact` and the per-cycle budget, so a mutating prune is refused while a Claude process is live and belongs between cycles.",
  },
  {
    term: "nothing written to memory",
    detail:
      "`digest inject` writes to `~/.claude/projects/*/memory/`; it is refused, and the plugin directory drops the skills and the MCP server.",
  },
] as const;

const WHAT_DOES_NOT = [
  {
    term: "`winnow fork`",
    detail: "The pruner itself. Milestone 2. Not started.",
  },
  {
    term: "`winnow recover`",
    detail:
      "The command the pointer names, which prints the exact bytes back out of the untouched original. Not started.",
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
                  "Milestone 1's number has been produced: tier CB strips 10.2% of message content pooled and 8.8% at the median, against the 22.6% / 21.6% section 6 of `docs/SPEC.md` recorded and the 3 points either way section 9 asked it to reproduce within."
                }
              </Ticks>
            </p>
            <p className="text-body text-fg-muted mt-4">
              <Ticks>
                {
                  "It misses by 12.4 points, and 8.7 of those are one rule whose measured number was taken with a looser definition than the same document specifies. The *population* lands where the method says it should — 174 sessions over 400 KB of message content, 129.6 MB pooled, against a recorded 161 and 120.1 MB one day earlier — so the denominator is not the disagreement."
                }
              </Ticks>
            </p>
            <p className="text-body text-fg-muted mt-4">
              <Ticks>
                {
                  "`inspect` writes nothing. It reads one session and prints the composition readout, the six guards, the cache position and `T*`."
                }
              </Ticks>
            </p>
          </div>

          <div>
            <MilestoneMissDemo />
            <div className="mt-8">
              <TerminalBlock commands={INSPECT_COMMANDS} />
            </div>
            <p className="text-small text-fg-muted wn-measure mt-4">
              <Ticks>
                {
                  "`--json` is the machine-readable form, for a corpus sweep. `--tier CBA` adds the opt-in tier — A1 strips a `Read` that a later `Edit` made stale, and it is the rule the specification itself calls the most likely to be wrong."
                }
              </Ticks>
            </p>
          </div>
        </div>

        <div className="mt-10 grid gap-6 lg:grid-cols-2 lg:gap-[6ch]">
          <AsciiPanel label="netted" tone="accent">
            <p className="text-fg-muted">
              <Ticks>
                {
                  "Netted against the cache — `0.1·D` earned on each turn that followed the cut, `1.9·S − 2·D` paid once — a tier-CB cut pays off in 58% of sessions and is worth +3.27% of the bill, on an optimistic bound, against the 15% the success criteria set as the target."
                }
              </Ticks>
            </p>
            <p className="text-fg-muted mt-3">
              Milestone 1 was built to be allowed to say that.
            </p>
          </AsciiPanel>

          {/* docs/design-language.md §8 rule 14: name the disagreement rather
              than picking quietly. Delete this panel if it is reconciled
              upstream — not the care that put it here. */}
          <AsciiPanel label="two readings">
            <p className="text-fg-muted">
              <Ticks>
                {
                  "The README disagrees with itself about this, and the site follows the more specific of the two statements. Its Status table still lists milestone 1 as `not started`; the note at the top of the same file reports the number that milestone produced, and the table of what is in the tree lists `src/winnow/inspect.py` with 54 tests."
                }
              </Ticks>
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
                "That table is a simulation — what the filter *would* have done. `winnow savings` is the instrument, and it prices one install's own ledger rather than a corpus average."
              }
            </Ticks>
          </p>
          <div className="mt-6">
            <Button href="/filter#simulation" variant="ghost">
              the table, and its source
            </Button>
          </div>
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
                  "The vendored tool assumes an interactive user: it can defer a prune until you quit, ask you to run `init`, and start a daemon that will `SIGKILL` a session it judges too large. Under an unattended harness there is nobody to defer to, and the session that daemon would kill is the one the tool is running inside."
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

          <div>
            <TerminalBlock commands={SAFE_COMMANDS} />
            <p className="text-small text-fg-muted wn-measure mt-4">
              <Ticks>
                {
                  "One switch. `safe check` prints what would be refused and why; `safe plugin-dir` writes a `--plugin-dir` with SessionStart removed; `safe run` puts a vendored command through the gate."
                }
              </Ticks>
            </p>
          </div>
        </div>

        <SpecList items={GUARANTEES} className="wn-measure mt-10" />

        <div className="wn-measure mt-10">
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

      <section className="mb-16">
        <SectionHeading id="install" kicker="install">
          There is no package to install
        </SectionHeading>

        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-[6ch]">
          <div className="wn-measure">
            <p className="text-body text-fg-muted">
              <Ticks>
                {
                  "winnow publishes to no channel. The six package channels, the npm shim and the PyPI release workflow the inherited tree arrived with were deleted, and `packaging/README.md` is the record of them. Installing means a checkout."
                }
              </Ticks>
            </p>
            <p className="text-body text-fg-muted mt-4">
              <Ticks>
                {
                  "winnow's own tests are `unittest.TestCase` classes rather than pytest functions, for one reason: they have to run where the mode runs, and the harness container has no `pip`, no `venv` and no pytest. Stdlib only, no network. pytest collects the same file unchanged."
                }
              </Ticks>
            </p>
          </div>

          <div>
            <TerminalBlock commands={INSTALL_COMMANDS} />
            <div className="mt-6">
              <AsciiPanel label="the other suite" tone="accent">
                <p className="text-fg-muted">
                  <Ticks>
                    {
                      "The inherited suite is a different matter: running it writes into your home directory. It added seven hooks to `~/.claude/settings.json`, wrote `~/.winnow_global_initialized`, and left fixture content in `~/.winnow/behavioral-digest.md`. It leaves a `settings.<timestamp>.bak` beside the file it edited, which is how it was caught."
                    }
                  </Ticks>
                </p>
                <p className="text-fg-muted mt-3">
                  <Ticks>
                    {
                      "`WINNOW_ORCHESTRATOR=1 python -m winnow safe check` before and after will tell you."
                    }
                  </Ticks>
                </p>
              </AsciiPanel>
            </div>
          </div>
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
