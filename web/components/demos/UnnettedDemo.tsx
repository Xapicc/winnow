"use client";

import { ScriptedFigure, rowWidth, type FigureRow } from "@/components/AsciiFigure";
import { Ticks } from "@/components/Ticks";
import { useScriptedSteps } from "@/components/useScriptedSteps";

/**
 * The filter's cost model with its terms left apart.
 *
 * Written for this site rather than ported. It draws the README's own model —
 * "per result of `D` tokens over `T` following turns, the baseline is a 2.0×
 * cache write plus a 0.1× read on every later turn; this pays 1.0× once and
 * nothing after" — as three separate lines rather than one number, because that
 * is what `winnow savings` does: its readout "splits the avoided write from the
 * avoided reads rather than blending them".
 *
 * Nothing here is a measurement and nothing is invented either: every value on
 * the page is symbolic in `D` and `T`. Supplying a `T` would be the invented
 * number, and the sources do not state one.
 */

const STEP_MS = 640;

/** Columns of the two text fields, so every row's value starts in one place. */
const GROUP_COLS = 10;
const TERM_COLS = 25;

const pad = (text: string, width: number) => text.padEnd(width, " ");

type Term = {
  /** Left in place only on the first row of a group. */
  group: string;
  what: string;
  value: string;
  tone: "muted" | "ok" | "accent";
};

/**
 * `1.9·S − 2·D` is the pruner's whole one-off cost and `T* = 19·(S/D) − 20` the
 * turns it takes to earn back; both are the README's. The filter's rows have no
 * `S` in them at all, which is the reading the figure exists to make visible.
 */
const GROUPS: readonly (readonly Term[])[] = [
  [
    { group: "baseline", what: "cache write, once", value: "2.0 · D", tone: "muted" },
    { group: "", what: "cache read, every turn", value: "0.1 · D · T", tone: "muted" },
  ],
  [
    { group: "filter", what: "sent in full, once", value: "1.0 · D", tone: "muted" },
    { group: "", what: "nothing after", value: "0", tone: "muted" },
  ],
  [
    { group: "avoided", what: "the write", value: "1.0 · D", tone: "ok" },
    { group: "", what: "the reads", value: "0.1 · D · T", tone: "ok" },
    { group: "", what: "break-even term", value: "none", tone: "accent" },
  ],
  [
    { group: "a pruner", what: "same result, cut later", value: "1.9 · S − 2 · D", tone: "muted" },
    { group: "", what: "break-even term", value: "19·(S/D) − 20 turns", tone: "muted" },
  ],
];

const STEP_COUNT = GROUPS.length;

function termRow(term: Term): FigureRow {
  return {
    cells: [
      { text: ` ${pad(term.group, GROUP_COLS)}`, tone: "fg" },
      { text: pad(term.what, TERM_COLS), tone: "muted" },
      { text: term.value, tone: term.tone },
    ],
  };
}

function headerRow(): FigureRow {
  return {
    cells: [
      { text: " one tool result of D tokens, ", tone: "muted" },
      { text: "T turns still to come", tone: "fg" },
    ],
  };
}

/** Every row that is not a rule, so the rules can be cut to their width. */
function bodyRows(step: number): FigureRow[] {
  return [
    headerRow(),
    ...GROUPS.flatMap((group, index) =>
      group.map((term) => ({ ...termRow(term), hidden: index > step })),
    ),
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

/** A rule between every group, so the three readings do not run together. */
function buildRows(step: number): FigureRow[] {
  const [header, ...rest] = bodyRows(step);
  if (!header) throw new Error("UnnettedDemo: empty script");

  const rows: FigureRow[] = [header];
  let cursor = 0;
  for (const group of GROUPS) {
    rows.push(rule, ...rest.slice(cursor, cursor + group.length));
    cursor += group.length;
  }
  return rows;
}

export function UnnettedDemo() {
  const { containerRef, step } = useScriptedSteps(STEP_COUNT, STEP_MS);

  return (
    <ScriptedFigure
      containerRef={containerRef}
      rows={buildRows(step)}
      cols={COLS}
      cap={15}
      alt="Illustration of the intake filter's cost model with its terms left apart. Doing nothing costs a 2.0 times cache write once plus a 0.1 times read on every later turn. The filter pays 1.0 times once and nothing after. What it avoids is therefore two terms — the write and the reads — and there is no third, because there is no break-even term to pay off. A pruner removing the same result pays 1.9 S minus 2 D once and earns it back over 19 times S over D minus 20 turns."
    >
      <Ticks>
        {
          "The README's cost model, per result, with the terms unblended — which is how `winnow savings` reads them out. `D` and `T` are left symbolic: the model is stated for any result over any number of following turns, and supplying a number for either would be one this site invented."
        }
      </Ticks>
    </ScriptedFigure>
  );
}
