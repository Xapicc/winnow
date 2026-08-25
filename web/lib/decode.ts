/**
 * The arithmetic behind the hero decode — see docs/design-language.md §5.
 *
 * It lives apart from `components/DecodeAscii.tsx` because it is the one piece
 * of real computation on the site: a frame is a pure function of the art, the
 * progress through the run and a churn counter, so it can be checked without a
 * browser or a clock.
 */

import { SCRAMBLE_GLYPHS, type AsciiArt } from "./ascii";

/** Total time from full noise to fully resolved. */
export const DECODE_DURATION_MS = 900;

/** How often a still-scrambling cell picks a new glyph. */
export const DECODE_CHURN_MS = 45;

/**
 * Fraction of the run over which cells start settling, left-to-right. Mirrors
 * `--motion-decode-stagger`; at run time `lib/motion.ts` passes the CSS value
 * in, so this is the value the pure functions are checked against and not a
 * second source of truth.
 */
export const STAGGER = 0.55;

/**
 * How long one cell spends resolving once its turn arrives. `stagger +
 * resolveWindow` must be exactly 1: any less and the last cell resolves before
 * the run ends, any more and it is still noise when the timer stops. Derived
 * from the stagger in use rather than stored, so the two cannot drift.
 */
export function resolveWindow(stagger: number): number {
  return 1 - stagger;
}

/**
 * Per-cell settle time as a fraction of the run, sweeping left-to-right with a
 * slight top-to-bottom lean so the block resolves as a diagonal rather than a
 * wipe.
 */
export function settleFractions(
  art: AsciiArt,
  stagger: number = STAGGER,
): number[][] {
  const lastRow = Math.max(1, art.rows.length - 1);
  const lastCol = Math.max(1, art.cols - 1);

  return art.rows.map((row, rowIndex) =>
    Array.from({ length: row.length }, (_unused, colIndex) => {
      const sweep = (colIndex / lastCol) * 0.8 + (rowIndex / lastRow) * 0.2;
      return sweep * stagger;
    }),
  );
}

/**
 * One frame of the decode. Spaces stay spaces, so the silhouette of the art is
 * visible from the first frame and the block never changes shape; every other
 * cell shows noise until its own settle time has passed.
 *
 * `churnSeed` advances on a slower clock than the frame rate — the noise has to
 * be legible as characters, not as a blur.
 */
export function decodeFrame(
  art: AsciiArt,
  fractions: number[][],
  progress: number,
  churnSeed: number,
  stagger: number = STAGGER,
): string {
  const window = resolveWindow(stagger);
  let cell = 0;

  return art.rows
    .map((row, rowIndex) =>
      Array.from(row, (character, colIndex) => {
        cell += 1;
        if (character === " ") return " ";
        if (progress >= (fractions[rowIndex]?.[colIndex] ?? 0) + window) {
          return character;
        }
        const pick = (cell * 31 + churnSeed * 17) % SCRAMBLE_GLYPHS.length;
        return SCRAMBLE_GLYPHS[pick] ?? character;
      }).join(""),
    )
    .join("\n");
}
