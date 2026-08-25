"use client";

import { ScriptedFigure, rowWidth, type FigureRow } from "@/components/AsciiFigure";
import { Ticks } from "@/components/Ticks";
import { useScriptedSteps } from "@/components/useScriptedSteps";
import { HALF_CUT_TURNS, paybackTurns } from "@/lib/payback";

/**
 * Ported from `Xapicc/UsageFoundryWeb:components/demos/PaybackDemo.tsx`, which
 * drew this against the same README. Two changes on the way across: the axis is
 * the README's own worked half cut rather than the orchestrator's configured
 * horizon, and a cut that needs longer than the axis draws is `danger` rather
 * than the amber that site has. There is no `--color-warn` here — an amber
 * against an orange brand is the brand (docs/design-language.md §1) — and
 * "this cut does not pay" is a verdict, which is what `danger` is for.
 *
 * **The suffix size and the four cuts are invented for the drawing**, and the
 * caption says so. What is not invented is the behaviour, and it is the whole
 * point of the figure: the turns come out of `paybackTurns`, which is
 * `19·(S/D) − 20` at the README's 0.1× cache read and measured 2.0× one-hour
 * write; `S/D` decides and absolute size does not, which is why the same four
 * bars would be drawn for a session ten times the size; a cut taken immediately
 * before a resume that was going to rewrite the suffix anyway drops to zero
 * because the `2·D` term is refunded there; and the intake filter has no
 * break-even term at all, because nothing is edited.
 */

const STEP_MS = 700;

/**
 * Cells in the bar. One per turn, so the bar's full width is the README's own
 * half cut — the case its prose works through, and the longest wait it calls
 * clearly worth having.
 */
const BAR_WIDTH = HALF_CUT_TURNS;

/** Columns of the two text fields, so every row's bar starts in one place. */
const CUT_COLS = 13;
const RATIO_COLS = 4;
const TURNS_COLS = 5;

/** Illustrated suffix standing behind the cut point, in tokens. */
const SUFFIX_TOKENS = 120_000;

type Cut = {
  /** How much of the suffix came out, in words. */
  label: string;
  removed: number;
};

const CUTS: readonly Cut[] = [
  { label: "a tenth", removed: 12_000 },
  { label: "a quarter", removed: 30_000 },
  { label: "a half", removed: 60_000 },
  { label: "two thirds", removed: 80_000 },
];

/** The four cuts, then the boundary, then the filter. */
const STEP_COUNT = CUTS.length + 2;

const pad = (text: string, width: number) => text.padEnd(width, " ");
const padLeft = (text: string, width: number) => text.padStart(width, " ");

/**
 * A ratio with no trailing zero, so `2` and `1.5` sit in the same column
 * without one of them reading as more precise than the other.
 */
function ratioLabel(cut: Cut): string {
  const ratio = SUFFIX_TOKENS / cut.removed;
  return Number.isInteger(ratio) ? String(ratio) : ratio.toFixed(1);
}

/**
 * The bar, always `BAR_WIDTH + 1` columns: one cell per turn up to the half
 * cut's 18, then a slot that carries `▸` when the cut needs longer. The arrow
 * rather than a longer bar because the figure would otherwise have to be 170
 * columns wide to draw its first row, and because *what* is past 18 does not
 * change the reading — in the corpus that was measured, only 807 turns out of
 * 11,422 sat past index 160 at all.
 *
 * Filled and empty differ in glyph as well as in tone, and the overflow has a
 * glyph of its own, so every reading survives without colour.
 *
 * The unfilled remainder is the only thing in this figure drawn in `faint`.
 * Every label, column head and note carries information and is therefore at
 * least `muted`; a bar's empty half is filler, and the number beside it is
 * where the reading actually comes from. docs/design-language.md §1.
 */
function bar(turns: number): { filled: string; rest: string } {
  if (turns > BAR_WIDTH) {
    return { filled: "▓".repeat(BAR_WIDTH), rest: "▸" };
  }
  return { filled: "▓".repeat(turns), rest: `${"░".repeat(BAR_WIDTH - turns)} ` };
}

function cutRow(cut: Cut): FigureRow {
  const turns = paybackTurns(SUFFIX_TOKENS, cut.removed);
  if (turns === null) throw new Error("PaybackDemo: a cut that removed nothing");

  const over = turns > HALF_CUT_TURNS;
  const { filled, rest } = bar(turns);

  return {
    cells: [
      { text: ` ${pad(cut.label, CUT_COLS)}`, tone: "fg" },
      { text: padLeft(ratioLabel(cut), RATIO_COLS), tone: "muted" },
      { text: "  " },
      { text: filled, tone: over ? "danger" : "ok" },
      { text: rest, tone: over ? "danger" : "faint" },
      { text: padLeft(String(turns), TURNS_COLS), tone: over ? "danger" : "ok" },
    ],
  };
}

/**
 * The same half cut, taken immediately before a handover. Zero because the
 * `2·D` term is refunded there: the resume was going to rewrite that suffix at
 * the write rate whatever happened to it. `docs/SPEC.md` section 7.
 */
function boundaryRow(): FigureRow {
  const { filled, rest } = bar(0);
  return {
    cells: [
      { text: ` ${pad("at a boundary", CUT_COLS)}`, tone: "fg" },
      { text: padLeft("2", RATIO_COLS), tone: "muted" },
      { text: "  " },
      { text: filled, tone: "ok" },
      { text: rest, tone: "faint" },
      { text: padLeft("0", TURNS_COLS), tone: "ok" },
    ],
  };
}

/** The filter, which edits nothing and so has no break-even term to draw. */
function filterRow(): FigureRow {
  return {
    cells: [
      { text: ` ${pad("intake filter", CUT_COLS)}`, tone: "fg" },
      { text: padLeft("—", RATIO_COLS), tone: "muted" },
      { text: "  " },
      { text: `${"─".repeat(BAR_WIDTH)} `, tone: "accent" },
      { text: padLeft("none", TURNS_COLS), tone: "accent" },
    ],
  };
}

function note(text: string, hidden: boolean): FigureRow {
  return { cells: [{ text: `   ${text}`, tone: "muted" }], hidden };
}

/**
 * The axis: one character per turn, labelled at both ends, with the overflow
 * slot marked so a `▸` at the end of a bar has something to mean.
 */
const AXIS = `0 ── turns ─── ${HALF_CUT_TURNS} ▸`;

/** Every row that is not a rule, so the rules can be cut to their width. */
function bodyRows(step: number): FigureRow[] {
  return [
    {
      cells: [
        { text: " T* = 19·(S/D) − 20", tone: "fg" },
        { text: "  further turns", tone: "muted" },
      ],
    },
    {
      cells: [
        { text: ` ${pad("cut", CUT_COLS)}`, tone: "muted" },
        { text: padLeft("S/D", RATIO_COLS), tone: "muted" },
        { text: "  " },
        { text: AXIS, tone: "muted" },
        { text: padLeft("T*", TURNS_COLS), tone: "muted" },
      ],
    },
    ...CUTS.map((cut, index) => ({ ...cutRow(cut), hidden: index > step })),
    { ...boundaryRow(), hidden: step < CUTS.length },
    // The same cut as the row two above it. Without that said, the reader has
    // to notice the S/D column matches, and nobody does.
    note("the same half cut, immediately before a resume", step < CUTS.length),
    { ...filterRow(), hidden: step < CUTS.length + 1 },
    note("nothing is edited, so nothing is paid", step < CUTS.length + 1),
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
  const [formula, header, ...rest] = bodyRows(step);
  if (!formula || !header) throw new Error("PaybackDemo: empty script");
  const cuts = rest.slice(0, CUTS.length);
  const tail = rest.slice(CUTS.length);
  return [formula, header, rule, ...cuts, rule, ...tail];
}

export function PaybackDemo() {
  const { containerRef, step } = useScriptedSteps(STEP_COUNT, STEP_MS);

  return (
    <ScriptedFigure
      containerRef={containerRef}
      rows={buildRows(step)}
      cols={COLS}
      cap={16}
      alt={`Illustration of when a context cut pays for itself. Bars measure the further turns a cut must survive, against the README's worked half cut of ${HALF_CUT_TURNS}. Removing a tenth of the suffix needs ${paybackTurns(SUFFIX_TOKENS, 12_000)} turns and removing a quarter needs ${paybackTurns(SUFFIX_TOKENS, 30_000)}, both past it; removing a half needs exactly ${paybackTurns(SUFFIX_TOKENS, 60_000)} and removing two thirds needs ${paybackTurns(SUFFIX_TOKENS, 80_000)}. The same half cut taken immediately before a resume needs none, because the resume was going to rewrite that suffix anyway. The intake filter has no break-even at all.`}
    >
      <Ticks>
        {
          "Illustration, on an invented 120,000-token suffix. The arithmetic is the README's: a cache read bills at 0.1× and the one-hour write it measured over 26,194 turns bills at 2.0×, so an edit pays `1.9·S − 2·D` once and earns `0.1·D` a turn back. `S/D` decides — the same four bars are drawn for a session ten times the size."
        }
      </Ticks>
    </ScriptedFigure>
  );
}
