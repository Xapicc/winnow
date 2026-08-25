/**
 * Character art for the site. Every piece is an array of equal-length rows so
 * the renderer can size it from a column count — see docs/design-language.md §4.
 *
 * Only characters inside the shipped font subset may appear here: basic Latin,
 * box drawing and block elements, and the punctuation, arrows and geometric
 * shapes the subset was cut with. A glyph outside it falls back to a system
 * font and breaks the grid.
 *
 * None of this was transcribed from a product asset. winnow has no icon, no SVG
 * and no brand colour — the mark and the letterforms below were drawn for this
 * site. docs/design-language.md §4 records that, so a later run does not go
 * looking for a source file that has never existed.
 */

/** One block letter: 5 rows, one blank column between neighbours. */
type Glyph = readonly [string, string, string, string, string];

/**
 * The letters "winnow" needs, and only those. Written out as art rather than
 * assembled from strokes, because the shape of each one has to be legible in
 * this file — but joined by `word()` rather than by hand, because a row of
 * block characters typed to a fixed width is not something the eye can check.
 *
 * `W` is 7 columns where the rest are 6. At six it has to fit two outer strokes,
 * two valleys and a centre riser into four interior columns, and every version
 * that does reads as `H` at hero size — which is what the first draft of this
 * file shipped. The seventh column buys the gap that tells them apart. Uniform
 * letter widths are not a rule here; `word()` joins whatever width each glyph is.
 */
const GLYPHS: Record<string, Glyph> = {
  W: [
    "█     █",
    "█     █",
    "█     █",
    "█  █  █",
    " ██ ██ ",
  ],
  I: [
    "██████",
    "  ██  ",
    "  ██  ",
    "  ██  ",
    "██████",
  ],
  N: [
    "█    █",
    "██   █",
    "█ ██ █",
    "█   ██",
    "█    █",
  ],
  O: [
    "██████",
    "█    █",
    "█    █",
    "█    █",
    "██████",
  ],
};

const GLYPH_ROWS = 5;

/** Sets a word in block letters, one blank column between them. */
function word(text: string): readonly string[] {
  const glyphs = Array.from(text.toUpperCase(), (character) => {
    const glyph = GLYPHS[character];
    if (!glyph) {
      throw new Error(
        `No block letter for "${character}". Draw it in lib/ascii.ts GLYPHS first.`,
      );
    }
    return glyph;
  });

  return Array.from({ length: GLYPH_ROWS }, (_unused, row) =>
    glyphs.map((glyph) => glyph[row] ?? "").join(" "),
  );
}

const WINNOW_ROWS = word("winnow");

/**
 * The mark: a funnel. Eleven columns of intake, converging walls, three columns
 * of spout. That is the tool in one shape — more goes in than comes out.
 *
 * An earlier draft filled the whole 11 × 5 block, `█` for what is kept and `░`
 * for what is shed. It was measured against the real font at hero size and at
 * header size and dropped both times: at 30px the stipple reads as noise rather
 * than as chaff, and the filled block is a slab of accent large enough to break
 * §6's one-accent-element budget on its own. The outline says the same thing
 * with a quarter of the ink. docs/design-language.md §4.
 *
 * Invented for this site. There is no winnow icon to transcribe.
 */
export const MARK_ROWS = [
  "███████████",
  " ╲       ╱ ",
  "  ╲     ╱  ",
  "   ╲   ╱   ",
  "    ███    ",
] as const;

/** Centres a narrower piece over a wider one, in columns. */
function centre(rows: readonly string[], width: number): readonly string[] {
  return rows.map((row) => {
    const left = Math.floor((width - row.length) / 2);
    return " ".repeat(left) + row + " ".repeat(width - row.length - left);
  });
}

const WORDMARK_COLS = WINNOW_ROWS.reduce(
  (widest, row) => Math.max(widest, row.length),
  0,
);

/**
 * The mark above the word, one blank row between: 43 × 11.
 *
 * The word sets the width and the mark is centred on it, so the funnel's
 * 3-column spout lands on the middle of the word. That is the whole reason for
 * this composition rather than a mark beside the word — it reads as one object
 * because the word is what falls out of the funnel.
 */
export const WORDMARK_ROWS: readonly string[] = [
  ...centre(MARK_ROWS, WORDMARK_COLS),
  "",
  ...WINNOW_ROWS,
];

/**
 * Small inline mark for the header and footer: the funnel's silhouette, 7 × 3.
 *
 * Filled rather than outlined, and that is a reduction rather than a second
 * mark. The header renders this at a 5px cap, where a `╲` is under a pixel wide
 * and disappears; the silhouette keeps the one thing the mark has to say at that
 * size, which is that it narrows.
 */
export const MARK_SMALL_ROWS = ["███████", " █████ ", "  ███  "] as const;

export type AsciiArt = {
  readonly rows: readonly string[];
  /** Width of the widest row, in characters. */
  readonly cols: number;
};

/**
 * Pads every row to the width of the widest one and reports that width. Ragged
 * art is a bug, but padding here means a ragged row degrades to trailing spaces
 * rather than to a collapsed grid.
 */
export function toArt(rows: readonly string[]): AsciiArt {
  const cols = rows.reduce((widest, row) => Math.max(widest, row.length), 0);
  return {
    rows: rows.map((row) => row.padEnd(cols, " ")),
    cols,
  };
}

export const WORDMARK = toArt(WORDMARK_ROWS);
export const MARK = toArt(MARK_ROWS);
export const MARK_SMALL = toArt(MARK_SMALL_ROWS);

/** Glyphs the decode effect cycles through before a cell settles. */
export const SCRAMBLE_GLYPHS = "░▒▓█▚▞#%*+=-";
