import { ImageResponse } from "next/og";

import { WORDMARK } from "@/lib/ascii";
import { SITE_NAME, SITE_TAGLINE } from "@/lib/site";

export const alt = `${SITE_NAME} — ${SITE_TAGLINE}`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * The social card, drawn by the build from the same rows the hero decodes,
 * rather than committed as a binary nobody can diff. Change the wordmark in
 * `lib/ascii.ts` and this changes with it. It needs no runtime and no
 * environment variable.
 *
 * The art is emitted as SVG geometry rather than as text because Satori cannot
 * read the WOFF2 subset this site ships — it rejects the `wOF2` signature
 * outright — and the fallback face it would otherwise use has no U+2588 to draw
 * with, let alone the `╲` and `╱` the mark's walls are made of. Geometry is
 * exact, needs no font at all, and keeps the 0.6em advance the whole grid is
 * built on. See docs/design-language.md §2 and §4.
 *
 * That leaves the two text lines set in the renderer's bundled sans rather than
 * in JetBrains Mono — the one surface on the site that departs from §2. A TTF
 * decompressed from our WOFF2 is still a *variable* font, which Satori cannot
 * instance, and shipping a second static copy of the family for one image is
 * not worth ~90 kB in the repository.
 */

const CANVAS = "#0a0a0b";
const ACCENT = "#ff7a1a";
const FG_MUTED = "#9b9ba4";
const LINE = "#23232a";

/** Every glyph in the grid advances this fraction of its own height. */
const ADVANCE = 0.6;
const PADDING = 80;

/**
 * The art is sized from the height it may occupy, not from the card's width:
 * the kicker above it and the rule and tagline below it have to fit too, and a
 * cell is ADVANCE wide and 1 tall, so fixing the row height fixes the width.
 */
const ART_HEIGHT = 264;
const CELL = ART_HEIGHT / WORDMARK.rows.length;
const COLUMN = ADVANCE * CELL;
const ART_WIDTH = Math.round(WORDMARK.cols * COLUMN);

/**
 * The mark's walls are drawn at the weight `app/icon.svg` uses for the same
 * three parts — thin enough to read as a rule, heavy enough to survive the
 * downscale a timeline serves this card at.
 */
const WALL_WIDTH = Math.max(2, CELL * 0.14);

/**
 * One rectangle per horizontal run of `█`, plus one line per diagonal cell, in
 * final pixels. Satori rasterises an SVG child at its declared width and height
 * and does not scale a viewBox to fit, so the coordinates have to be the ones
 * that get drawn.
 *
 * Successive `╲` cells step exactly one column right and one row down, and a
 * cell is one column wide and one row tall, so corner-to-corner diagonals chain
 * into a continuous wall with no join to draw.
 */
function wordmarkShapes(): string {
  const shapes: string[] = [];

  WORDMARK.rows.forEach((row, y) => {
    const top = y * CELL;
    let runStart: number | null = null;

    const closeRun = (end: number) => {
      if (runStart === null) return;
      const left = runStart * COLUMN;
      shapes.push(
        `<rect x="${left.toFixed(2)}" y="${top.toFixed(2)}" width="${((end - runStart) * COLUMN).toFixed(2)}" height="${CELL.toFixed(2)}"/>`,
      );
      runStart = null;
    };

    for (let x = 0; x <= row.length; x += 1) {
      const character = row[x];
      if (character === "█") {
        if (runStart === null) runStart = x;
        continue;
      }
      closeRun(x);
      if (character !== "╲" && character !== "╱") continue;

      const left = x * COLUMN;
      const [y1, y2] = character === "╲" ? [top, top + CELL] : [top + CELL, top];
      shapes.push(
        `<line x1="${left.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${(left + COLUMN).toFixed(2)}" y2="${y2.toFixed(2)}" stroke="${ACCENT}" stroke-width="${WALL_WIDTH.toFixed(2)}" stroke-linecap="square"/>`,
      );
    }
  });

  return shapes.join("");
}

const WORDMARK_SVG =
  `<svg xmlns="http://www.w3.org/2000/svg" width="${ART_WIDTH}" height="${ART_HEIGHT}" ` +
  `viewBox="0 0 ${ART_WIDTH} ${ART_HEIGHT}" fill="${ACCENT}">${wordmarkShapes()}</svg>`;

const WORDMARK_SRC = `data:image/svg+xml;base64,${Buffer.from(WORDMARK_SVG).toString("base64")}`;

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          backgroundColor: CANVAS,
          padding: PADDING,
        }}
      >
        {/* Set the way `.wn-kicker` sets it on the site: uppercase and
            letter-spaced, so the card reads as the same object as the page.
            fg-muted rather than fg-faint — this is a sentence someone has to
            read, and §1 reserves fg-faint for things that are not. */}
        <div
          style={{
            display: "flex",
            fontSize: 22,
            letterSpacing: 4,
            textTransform: "uppercase",
            color: FG_MUTED,
          }}
        >
          stdlib only · no network · nothing installed
        </div>

        <img src={WORDMARK_SRC} alt="" width={ART_WIDTH} height={ART_HEIGHT} />

        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{ display: "flex", height: 1, backgroundColor: LINE, marginBottom: 24 }}
          />
          <div style={{ display: "flex", fontSize: 28, color: FG_MUTED }}>
            {SITE_TAGLINE}
          </div>
        </div>
      </div>
    ),
    size,
  );
}
