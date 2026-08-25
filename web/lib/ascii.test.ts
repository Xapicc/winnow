import { describe, expect, it } from "vitest";

import {
  MARK,
  MARK_SMALL,
  SCRAMBLE_GLYPHS,
  WORDMARK,
  toArt,
} from "@/lib/ascii";

/**
 * The art in `lib/ascii.ts` was drawn for this site and has no upstream to be
 * checked against — see docs/design-language.md §4. What can still be asserted
 * is its geometry, and geometry is exactly what the renderer trusts: `.wn-ascii`
 * divides the container width by a column count, so a row that is one character
 * longer than the count silently overflows its container instead of failing.
 *
 * The character allow-list here is written out rather than read from the font's
 * own `cmap`, which is the check §9 leaves to the run that builds the test layer.
 * A glyph outside the shipped subset falls back to a system font and breaks the
 * 0.6em advance the whole grid depends on.
 */

const ALLOWED = new Set([
  " ",
  "█", // U+2588 full block
  "░", // U+2591 light shade
  "▒", // U+2592 medium shade
  "▓", // U+2593 dark shade
  "▚", // U+259A quadrant upper-left and lower-right
  "▞", // U+259E quadrant upper-right and lower-left
  "╲", // U+2572 diagonal, the funnel's left wall
  "╱", // U+2571 diagonal, the funnel's right wall
  ...Array.from("#%*+=-"), // the rest of the scramble set
]);

const PIECES = [
  ["WORDMARK", WORDMARK],
  ["MARK", MARK],
  ["MARK_SMALL", MARK_SMALL],
] as const;

describe.each(PIECES)("%s", (_name, art) => {
  it("has rows that are all exactly `cols` wide", () => {
    for (const row of art.rows) {
      expect(row.length).toBe(art.cols);
    }
  });

  it("uses only characters the shipped font subset covers", () => {
    for (const row of art.rows) {
      for (const character of row) {
        expect(ALLOWED.has(character), `unexpected ${JSON.stringify(character)}`).toBe(
          true,
        );
      }
    }
  });
});

describe("the wordmark lockup", () => {
  it("is 43 columns by 11 rows", () => {
    // 7 (W) + 6 + 6 + 6 + 6 + 7 (W) plus five single-column gaps.
    expect(WORDMARK.cols).toBe(43);
    expect(WORDMARK.rows).toHaveLength(11);
  });

  it("separates the mark from the word with one blank row", () => {
    expect(WORDMARK.rows[5]?.trim()).toBe("");
    expect(WORDMARK.rows[4]?.trim()).not.toBe("");
    expect(WORDMARK.rows[6]?.trim()).not.toBe("");
  });

  it("centres the mark over the word", () => {
    // The funnel's spout is what has to land in the middle; a mark centred by
    // eye drifts a column and the lockup stops reading as one object.
    const spout = WORDMARK.rows[4] ?? "";
    const left = spout.length - spout.trimStart().length;
    const right = spout.length - spout.trimEnd().length;
    expect(left).toBe(right);
  });
});

describe("the mark", () => {
  it("takes in more than it lets out", () => {
    const ink = (row: string) => row.replace(/[^█]/g, "").length;
    const first = MARK.rows[0] ?? "";
    const last = MARK.rows[MARK.rows.length - 1] ?? "";
    expect(ink(first)).toBeGreaterThan(ink(last));
    expect(ink(last)).toBeGreaterThan(0);
  });

  it("reduces to the same taper at header size", () => {
    const ink = (row: string) => row.replace(/[^█]/g, "").length;
    const widths = MARK_SMALL.rows.map(ink);
    expect(widths).toStrictEqual([...widths].sort((a, b) => b - a));
    expect(new Set(widths).size).toBe(widths.length);
  });
});

describe("toArt", () => {
  it("pads short rows and reports the widest", () => {
    const art = toArt(["██", "█", ""]);
    expect(art.cols).toBe(2);
    expect(art.rows).toStrictEqual(["██", "█ ", "  "]);
  });
});

describe("the scramble set", () => {
  it("only contains characters the art is allowed to use", () => {
    for (const character of SCRAMBLE_GLYPHS) {
      expect(ALLOWED.has(character), `unexpected ${JSON.stringify(character)}`).toBe(
        true,
      );
    }
  });
});
