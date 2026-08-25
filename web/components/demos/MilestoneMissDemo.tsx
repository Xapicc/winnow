"use client";

import { ScriptedFigure, rowWidth, type FigureRow } from "@/components/AsciiFigure";
import { Ticks } from "@/components/Ticks";
import { useScriptedSteps } from "@/components/useScriptedSteps";

/**
 * Milestone 1's number, including the part of it that missed.
 *
 * Written for this site. Nothing here is illustrated: every number is out of
 * `README.md` and section 6 of `docs/SPEC.md`, and the one value that is not
 * quoted — the 3.7 points that are not the single rule — is subtracted from two
 * that are, in code, so it cannot drift away from them.
 *
 * The figure exists because the miss is the harder half to draw and the easier
 * half to leave off. A bar chart of "10.2% stripped" is true and is not the
 * result; the result is 10.2% against a recorded 22.6% that it was asked to
 * reproduce within 3 points, and a page that shows the first bar without the
 * second is doing the thing this project was built not to do.
 */

const STEP_MS = 700;

/** Tier C+B pooled, section 6 of `docs/SPEC.md`. */
const RECORDED_PERCENT = 22.6;

/** Tier CB pooled, as milestone 1 measured it. `README.md`. */
const MEASURED_PERCENT = 10.2;

/** `README.md`: "It misses by 12.4, and 8.7 of those are one rule". */
const MISS_POINTS = 12.4;
const ONE_RULE_POINTS = 8.7;

/** Section 9's reproduction band, in points either way. */
const BAND_POINTS = 3;

/** One cell per point of message content, so the two bars share a scale. */
const CELL_PER_POINT = 1;

const LABEL_COLS = 12;
const VALUE_COLS = 7;

const pad = (text: string, width: number) => text.padEnd(width, " ");
const padLeft = (text: string, width: number) => text.padStart(width, " ");

const BAR_COLS = Math.round(RECORDED_PERCENT * CELL_PER_POINT);

function bar(percent: number): { filled: string; rest: string } {
  const filled = Math.round(percent * CELL_PER_POINT);
  return { filled: "▓".repeat(filled), rest: "░".repeat(BAR_COLS - filled) };
}

function barRow(
  label: string,
  percent: number,
  tone: "muted" | "accent",
): FigureRow {
  const { filled, rest } = bar(percent);
  return {
    cells: [
      { text: ` ${pad(label, LABEL_COLS)}`, tone: "fg" },
      { text: padLeft(`${percent.toFixed(1)}%`, VALUE_COLS), tone },
      { text: "  " },
      { text: filled, tone },
      { text: rest, tone: "faint" },
    ],
  };
}

/**
 * The gap, split into the part that has an explanation and the part that does
 * not. Subtracted rather than quoted: the sources state the total and the one
 * rule, and a third number typed by hand here would be a number this site made
 * up. `toFixed(1)` because 12.4 − 8.7 is 3.7000000000000006 in binary floating
 * point.
 */
const REMAINDER_POINTS = Number((MISS_POINTS - ONE_RULE_POINTS).toFixed(1));

function missRows(): FigureRow[] {
  return [
    {
      cells: [
        { text: ` ${pad("the miss", LABEL_COLS)}`, tone: "fg" },
        { text: padLeft(`${MISS_POINTS} pts`, VALUE_COLS), tone: "danger" },
      ],
    },
    {
      cells: [
        { text: `   ${pad("", LABEL_COLS - 2)}`, tone: "muted" },
        { text: padLeft(`${ONE_RULE_POINTS}`, VALUE_COLS), tone: "danger" },
        { text: "  one rule, measured under a looser definition", tone: "muted" },
      ],
    },
    {
      cells: [
        { text: `   ${pad("", LABEL_COLS - 2)}`, tone: "muted" },
        { text: padLeft(`${REMAINDER_POINTS}`, VALUE_COLS), tone: "danger" },
        { text: "  not accounted for", tone: "muted" },
      ],
    },
  ];
}

function bandRow(): FigureRow {
  return {
    cells: [
      { text: ` ${pad("asked for", LABEL_COLS)}`, tone: "fg" },
      { text: padLeft(`${BAND_POINTS} pts`, VALUE_COLS), tone: "muted" },
      { text: "  either way, to count as reproduced", tone: "muted" },
    ],
  };
}

/** Recorded, then measured, then the gap, then the band it was asked for. */
const STEP_COUNT = 4;

/** Every row that is not a rule, so the rules can be cut to their width. */
function bodyRows(step: number): FigureRow[] {
  return [
    {
      cells: [
        { text: " tier CB, share of message content", tone: "muted" },
      ],
    },
    barRow("recorded", RECORDED_PERCENT, "muted"),
    { ...barRow("measured", MEASURED_PERCENT, "accent"), hidden: step < 1 },
    ...missRows().map((row) => ({ ...row, hidden: step < 2 })),
    { ...bandRow(), hidden: step < 3 },
  ];
}

const COLS = Math.max(
  ...Array.from({ length: STEP_COUNT }, (_, step) =>
    Math.max(...bodyRows(step).map((row) => rowWidth(row.cells))),
  ),
);

const rule: FigureRow = {
  cells: [{ text: ` ${"─".repeat(COLS - 1)}`, tone: "faint" }],
};

function buildRows(step: number): FigureRow[] {
  const [header, recorded, measured, ...rest] = bodyRows(step);
  if (!header || !recorded || !measured) throw new Error("MilestoneMissDemo: empty script");
  const miss = rest.slice(0, 3);
  const band = rest.slice(3);
  return [header, rule, recorded, measured, rule, ...miss, rule, ...band];
}

export function MilestoneMissDemo() {
  const { containerRef, step } = useScriptedSteps(STEP_COUNT, STEP_MS);

  return (
    <ScriptedFigure
      containerRef={containerRef}
      rows={buildRows(step)}
      cols={COLS}
      cap={15}
      alt={`Milestone 1's result at tier CB. The specification recorded ${RECORDED_PERCENT} percent of message content as strippable; the measurement reproduced ${MEASURED_PERCENT} percent. The gap is ${MISS_POINTS} points, of which ${ONE_RULE_POINTS} are one rule whose recorded number was taken under a looser definition and ${REMAINDER_POINTS} are not accounted for. Reproduction was asked for within ${BAND_POINTS} points either way.`}
    >
      <Ticks>
        {
          "Every number in this one is measured rather than illustrated. The recorded share is section 6 of `docs/SPEC.md` and the reproduced share is milestone 1's own, both pooled over sessions carrying more than 400 KB of message content. A share is a ceiling on the mechanism rather than a saving: the removed bytes were being billed at 0.1×."
        }
      </Ticks>
    </ScriptedFigure>
  );
}
