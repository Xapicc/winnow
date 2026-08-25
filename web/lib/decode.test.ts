import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { SCRAMBLE_GLYPHS, WORDMARK, toArt } from "./ascii";
import {
  DECODE_CHURN_MS,
  DECODE_DURATION_MS,
  STAGGER,
  decodeFrame,
  resolveWindow,
  settleFractions,
} from "./decode";

/**
 * The one piece of real arithmetic on the site. `lib/motion.ts` owns the clock
 * and the DOM; everything below is pure, so the effect docs/design-language.md
 * §5 describes can be checked without a browser.
 */

const resolved = WORDMARK.rows.join("\n");
const isNoise = (character: string) => SCRAMBLE_GLYPHS.includes(character);

const frameAt = (progress: number, churnSeed = 0) =>
  decodeFrame(WORDMARK, settleFractions(WORDMARK), progress, churnSeed);

/**
 * A block of ink, for the claims the wordmark cannot carry: three of its
 * corners are spaces — the intake bar is centred and the letters have gaps —
 * and a space never scrambles, so "the last cell to settle" and "the left edge
 * resolves first" have to be asked of art that is ink all the way across.
 *
 * Drawn in `╲` rather than `█` for a reason that is easy to miss: `█` is *in*
 * the scramble alphabet, so a cell showing one may be settled or may be a noise
 * pick that happened to land there, and neither this file nor the eye can tell
 * which. `╲` is a real glyph of this site (§3, the mark's left wall) and is not
 * in the alphabet, so every cell is unambiguous.
 */
const WALL = toArt(Array.from({ length: 3 }, () => "╲".repeat(11)));
const wallFrame = (progress: number, stagger = STAGGER) =>
  decodeFrame(WALL, settleFractions(WALL, stagger), progress, 0, stagger);

describe("the timings", () => {
  /* app/globals.css is the single source of truth for all three: lib/motion.ts
     reads them off :root at run time and passes the stagger into decodeFrame.
     The constants in lib/decode.ts are only the values these tests check
     against, so a token edited in the CSS and not here leaves this file
     asserting a decode the site does not run. */
  const css = readFileSync(
    fileURLToPath(new URL("../app/globals.css", import.meta.url)),
    "utf8",
  );

  const token = (name: string): string => {
    const found = css.match(new RegExp(`${name}:\\s*([^;]+);`))?.[1];
    if (!found) throw new Error(`${name} is not declared in app/globals.css`);
    return found.trim();
  };

  it("match the tokens the site actually animates on", () => {
    expect(token("--motion-decode")).toBe(`${DECODE_DURATION_MS}ms`);
    expect(token("--motion-decode-churn")).toBe(`${DECODE_CHURN_MS}ms`);
    expect(token("--motion-decode-stagger")).toBe(String(STAGGER));
  });

  it("give the 900ms single pass §5 specifies", () => {
    expect(DECODE_DURATION_MS).toBe(900);
    // The noise has to read as characters rather than as a blur, so cells
    // repick on a clock an order of magnitude slower than the frame rate.
    expect(DECODE_CHURN_MS).toBeGreaterThan(1000 / 60);
  });
});

describe("resolveWindow", () => {
  it("is whatever the stagger is not", () => {
    // The whole effect hangs on stagger + window === 1: any less and the art
    // sits finished while the timer runs, any more and the last cell is still
    // noise when the timer stops.
    for (const stagger of [0, 0.25, STAGGER, 0.8, 1]) {
      expect(stagger + resolveWindow(stagger)).toBeCloseTo(1, 12);
    }
  });
});

describe("settleFractions", () => {
  it("gives one fraction per cell of the art", () => {
    const fractions = settleFractions(WORDMARK);
    expect(fractions).toHaveLength(WORDMARK.rows.length);
    for (const row of fractions) expect(row).toHaveLength(WORDMARK.cols);
  });

  it("starts the sweep at the top-left cell and ends it at the bottom-right", () => {
    const fractions = settleFractions(WORDMARK);
    expect(fractions[0]?.[0]).toBe(0);
    expect(fractions.at(-1)?.at(-1)).toBeCloseTo(STAGGER, 10);
  });

  it("never schedules a cell outside the stagger window", () => {
    for (const row of settleFractions(WORDMARK)) {
      for (const fraction of row) {
        expect(fraction).toBeGreaterThanOrEqual(0);
        expect(fraction).toBeLessThanOrEqual(STAGGER);
      }
    }
  });

  it("leans left-to-right harder than top-to-bottom", () => {
    // §5 calls the sweep a diagonal, not a wipe: 0.8 of it is horizontal over
    // 43 columns and 0.2 vertical over 11 rows, so a step right is worth less
    // than a step down but there are four times as many of them.
    const fractions = settleFractions(WORDMARK);
    const oneRowDown = fractions[1]?.[0] ?? 0;
    const oneColumnRight = fractions[0]?.[1] ?? 0;
    expect(oneColumnRight).toBeGreaterThan(0);
    expect(oneRowDown).toBeGreaterThan(0);
    expect(oneColumnRight / WORDMARK.cols).toBeLessThan(
      oneRowDown / WORDMARK.rows.length,
    );
  });

  it("takes the stagger it is handed rather than the constant", () => {
    expect(settleFractions(WORDMARK, 0.2).at(-1)?.at(-1)).toBeCloseTo(0.2, 10);
  });

  it("does not divide by zero on single-row or single-column art", () => {
    const flat = settleFractions(toArt(["█"]));
    expect(flat[0]?.[0]).toBe(0);
    expect(Number.isFinite(flat[0]?.[0] ?? Number.NaN)).toBe(true);
  });
});

describe("decodeFrame", () => {
  it("is fully resolved exactly when the run ends, at any stagger", () => {
    for (const stagger of [0.2, STAGGER, 0.9]) {
      expect(wallFrame(1, stagger), `stagger ${stagger}`).toBe(
        WALL.rows.join("\n"),
      );
      expect(wallFrame(0.999, stagger), `stagger ${stagger}`).not.toBe(
        WALL.rows.join("\n"),
      );
    }
    expect(frameAt(1)).toBe(resolved);
  });

  it("is entirely noise at the start", () => {
    const first = frameAt(0);
    expect(first).not.toBe(resolved);
    const ink = [...first].filter(
      (character) => character !== " " && character !== "\n",
    );
    expect(ink.length).toBeGreaterThan(0);
    expect(ink.every(isNoise)).toBe(true);
  });

  it("keeps the block the same shape at every progress", () => {
    for (const progress of [0, 0.13, 0.5, 0.87, 1]) {
      const rows = frameAt(progress).split("\n");
      expect(rows).toHaveLength(WORDMARK.rows.length);
      expect(new Set(rows.map((row) => row.length))).toEqual(
        new Set([WORDMARK.cols]),
      );
    }
  });

  it("never puts noise where the art has a space", () => {
    // The silhouette is visible from the first frame, so the block never
    // changes shape and nothing on the page reflows while it runs.
    for (const progress of [0, 0.4, 0.8]) {
      const rows = frameAt(progress).split("\n");
      WORDMARK.rows.forEach((source, rowIndex) => {
        [...source].forEach((character, colIndex) => {
          if (character === " ") expect(rows[rowIndex]?.[colIndex]).toBe(" ");
        });
      });
    }
  });

  it("only ever resolves more cells as progress advances", () => {
    let previous = 0;
    for (const progress of [0, 0.2, 0.4, 0.6, 0.8, 1]) {
      const frame = frameAt(progress);
      const settled = [...frame].filter(
        (character, index) =>
          character !== " " && character !== "\n" && character === resolved[index],
      ).length;
      expect(settled).toBeGreaterThanOrEqual(previous);
      previous = settled;
    }
    expect(previous).toBe(
      [...resolved].filter(
        (character) => character !== " " && character !== "\n",
      ).length,
    );
  });

  it("resolves the left edge before the right edge", () => {
    // Asked of the wall: on its top row a cell settles at 0.45 + 0.044·column,
    // so at 0.6 the first four columns have passed their time and the fifth
    // has not.
    const row = wallFrame(0.6).split("\n")[0] ?? "";
    expect(row.slice(0, 4)).toBe("╲╲╲╲");
    expect([...row.slice(4)].every(isNoise)).toBe(true);
  });

  it("re-picks noise glyphs when the churn counter advances", () => {
    expect(frameAt(0.2, 0)).not.toBe(frameAt(0.2, 1));
  });

  it("is stable for a given progress and churn counter", () => {
    expect(frameAt(0.2, 3)).toBe(frameAt(0.2, 3));
  });

  it("shows every glyph of the scramble set in one noise frame", () => {
    // Not a curiosity: the e2e suite decides "this frame is mid-decode" by
    // looking for scramble-only glyphs, and that only works because the pick
    // (`cell · 31 + seed · 17` mod 12) walks every residue as `cell` advances.
    const glyphs = new Set([...frameAt(0)].filter(isNoise));
    expect(glyphs.size).toBe(SCRAMBLE_GLYPHS.length);
  });
});
