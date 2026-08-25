"use client";

import { ScriptedFigure, rowWidth, type FigureRow } from "@/components/AsciiFigure";
import { Ticks } from "@/components/Ticks";
import { useScriptedSteps } from "@/components/useScriptedSteps";

/**
 * Where the filter acts in a turn, and where a pruner would.
 *
 * Ported from `Xapicc/UsageFoundryWeb:components/demos/ContextControlDemo.tsx`
 * and cut down to what this repository can say. That version metered a work
 * cycle against the orchestrator's own 167,000-token ceiling and then pruned it;
 * neither the ceiling nor the prune belongs on a site about winnow, because the
 * ceiling is the orchestrator's number and **the pruner does not exist**
 * (docs/design-language.md §8, rule 11). What replaces them is the thing the
 * position is actually for: the cache boundary the full send sits past, and the
 * prefix a pruner would have to edit — drawn in the `╱` hatch §1 reserves for
 * what is not settled, and labelled as not built.
 *
 * **The request numbers, the tool names and the prefix proportions are invented
 * for the drawing.** What is not invented is the behaviour: a tool result is
 * sent in full on the one request the model acts on it, placed after the last
 * `cache_control` breakpoint so the API never writes it to cache, and is a
 * pointer on every request after that; and only the three rules that need no
 * hindsight can fire on the wire.
 */

const STEP_MS = 620;

/** Columns of the meter, split by the last `cache_control` breakpoint. */
const PREFIX_WIDTH = 20;
const TAIL_WIDTH = 5;

type LogLine = {
  request: number;
  tool: string;
  target: string;
  /** What the filter did: sent it in full, or replaced it with a pointer. */
  action: "full" | "pointer";
  /** winnow's own rule id, on the lines where one fired. */
  rule: string;
};

/**
 * Each line's rule is the one `docs/SPEC.md` section 4 attaches to that tool,
 * and the three are the only ones that can fire here: C1 is the *locator* rule
 * (`Glob`, `LS`, or `Grep` returning paths), C3 is a *passing verification*
 * (`npm test` and its neighbours, never a failing one — G3 keeps every error,
 * and the failure is the information), and B2 is *Bash inspection*, matched on
 * the first token of the pipeline, which is why `git status` counts and a
 * pipeline headed by `python` does not.
 *
 * A `Read` never appears here: the rule that would strip one is B1, and B1 has
 * to see the conversation's future, so no proxy can run it.
 */
const LOG: readonly LogLine[] = [
  { request: 21, tool: "Glob", target: "src/**/*.ts", action: "full", rule: "" },
  { request: 22, tool: "Glob", target: "src/**/*.ts", action: "pointer", rule: "C1" },
  { request: 23, tool: "Bash", target: "npm test", action: "full", rule: "" },
  { request: 24, tool: "Bash", target: "npm test", action: "pointer", rule: "C3" },
  { request: 25, tool: "Bash", target: "git status", action: "pointer", rule: "B2" },
];

/** One step per log line, then the cache meter, then what a pruner would touch. */
const STEP_COUNT = LOG.length + 2;

const pad = (text: string, width: number) => text.padEnd(width, " ");

function logRow(line: LogLine): FigureRow {
  const left = ` req ${line.request}  ${pad(line.tool, 5)}${pad(line.target, 12)}`;
  return line.action === "full"
    ? {
        cells: [
          { text: left, tone: "muted" },
          // muted, not faint: this says what happened to the request, and §1
          // does not let fg-faint carry information at 3.92:1.
          { text: "    past the breakpoint", tone: "muted" },
        ],
      }
    : {
        cells: [
          { text: left, tone: "muted" },
          // Three spaces so the rule id lands in the column "past" starts in
          // and both actions end flush: they are alternatives, not columns.
          // The rule that fired is a name, not filler. Same reason as above.
          { text: `    ${pad(line.rule, 4)}`, tone: "muted" },
          { text: "→ pointer", tone: "accent" },
        ],
      };
}

/**
 * The request body, split at the last `cache_control` breakpoint. Filled and
 * empty halves differ in glyph as well as in tone, so the reading survives
 * without colour — docs/design-language.md §1.
 */
function cacheRows(): FigureRow[] {
  return [
    {
      cells: [
        { text: " req 25  ", tone: "muted" },
        // Shape, not colour: §1's accent budget on this figure is already spent
        // on `[on]` and the three `→ pointer` marks, which are the mechanism.
        { text: "▓".repeat(PREFIX_WIDTH), tone: "muted" },
        { text: "│", tone: "accent" },
        { text: "░".repeat(TAIL_WIDTH), tone: "faint" },
      ],
    },
    {
      cells: [
        { text: "          cached prefix, read at 0.1×", tone: "muted" },
      ],
    },
    {
      cells: [
        { text: `          ${" ".repeat(PREFIX_WIDTH)}`, tone: "muted" },
        { text: "the full result, sent once", tone: "muted" },
      ],
    },
  ];
}

/**
 * What a pruner would have to edit, hatched because it is not built. §1 gives
 * the `╱` hatch to what is indeterminate, and this site's third state is "not
 * built yet" rather than "warning".
 */
function prunerRows(): FigureRow[] {
  return [
    {
      cells: [
        { text: " a pruner", tone: "muted" },
        { text: "  ", tone: "muted" },
        { text: "╱".repeat(PREFIX_WIDTH), tone: "muted" },
        { text: "│", tone: "faint" },
        { text: " ".repeat(TAIL_WIDTH), tone: "faint" },
      ],
    },
    {
      cells: [
        { text: "          edits the prefix, and pays 1.9·S − 2·D once", tone: "muted" },
      ],
    },
    {
      cells: [{ text: "          not built — there is no winnow fork", tone: "muted" }],
    },
  ];
}

/** Every row that is not a rule, so the rules can be cut to their width. */
function bodyRows(step: number): FigureRow[] {
  return [
    {
      cells: [
        { text: " winnow filter ", tone: "muted" },
        { text: "[on]", tone: "accent" },
      ],
    },
    ...LOG.map((entry, index) => ({ ...logRow(entry), hidden: index > step })),
    ...cacheRows().map((row) => ({ ...row, hidden: step < LOG.length })),
    ...prunerRows().map((row) => ({ ...row, hidden: step < STEP_COUNT - 1 })),
  ];
}

/**
 * Widest row across the whole script, so the type never resizes mid-play. Taken
 * from the body rows, which is what the rules are then cut to fit.
 */
const COLS = Math.max(
  ...Array.from({ length: STEP_COUNT }, (_, step) =>
    Math.max(...bodyRows(step).map((row) => rowWidth(row.cells))),
  ),
);

const rule: FigureRow = {
  cells: [{ text: ` ${"─".repeat(COLS - 1)}`, tone: "faint" }],
};

function buildRows(step: number): FigureRow[] {
  const [header, ...rest] = bodyRows(step);
  if (!header) throw new Error("FilterPositionDemo: empty script");
  const log = rest.slice(0, LOG.length);
  const cache = rest.slice(LOG.length, LOG.length + 3);
  const pruner = rest.slice(LOG.length + 3);
  return [header, rule, ...log, rule, ...cache, rule, ...pruner];
}

export function FilterPositionDemo() {
  const { containerRef, step } = useScriptedSteps(STEP_COUNT, STEP_MS);

  return (
    <ScriptedFigure
      containerRef={containerRef}
      rows={buildRows(step)}
      cols={COLS}
      cap={15}
      alt="Illustration of where the filter acts in a turn. Five requests go out: two carry a tool result in full, placed past the last cache_control breakpoint, and three carry a pointer instead, each marked with the winnow rule that fired — C1, C3 and B2. A meter then splits one request into the cached prefix, read at a tenth of the input rate, and the uncached tail the full result sits in. A pruner would instead edit the prefix and pay 1.9 S minus 2 D once; that half is hatched, because it is not built."
    >
      <Ticks>
        {
          "Illustration, on invented request numbers and proportions. Only the three rules needing no hindsight can fire on the wire — C1, C3 and B2. C2, B1 and A1 all need to see the conversation's future, and a policy that did would change the prefix under the cache. The hatched half is not software you can run: there is no `winnow fork`."
        }
      </Ticks>
    </ScriptedFigure>
  );
}
