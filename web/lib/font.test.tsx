import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { brotliDecompressSync } from "node:zlib";

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import ArithmeticPage from "@/app/arithmetic/page";
import FilterPage from "@/app/filter/page";
import HomePage from "@/app/page";
import StatusPage from "@/app/status/page";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

import { MARK, MARK_SMALL, SCRAMBLE_GLYPHS, WORDMARK } from "./ascii";

/**
 * Every character the site renders is in the shipped font, read out of the
 * font's own `cmap` rather than trusted from a comment.
 *
 * docs/design-language.md §2 names this check and §9 records it as unwritten.
 * It matters because the failure is silent: a glyph outside the subset falls
 * back to a system font at a different advance width, which in prose is a
 * slightly wrong character and in a `<pre>` of character art is a broken grid.
 * Nothing about the page looks wrong enough to notice.
 *
 * It caught two on the run that wrote it — `§` and `±`, both in body copy —
 * which is why the subset's coverage is now written down in §2 rather than
 * described.
 */

const FONT_PATH = fileURLToPath(
  new URL("../app/fonts/JetBrainsMono-Variable-subset.woff2", import.meta.url),
);

/**
 * The 63 table tags a WOFF2 directory may reference by index instead of
 * spelling out, in the order the specification fixes. Index 63 means an
 * arbitrary four-byte tag follows.
 */
const KNOWN_TAGS =
  "cmap head hhea hmtx maxp name OS/2 post cvt fpgm glyf loca prep CFF VORG EBDT EBLC gasp hdmx kern LTSH PCLT VDMX vhea vmtx BASE GDEF GPOS GSUB EBSC JSTF MATH CBDT CBLC COLR CPAL SVG sbix acnt avar bdat bloc bsln cvar fdsc feat fmtx fvar gvar hsty just lcar mort morx opbd prop trak Zapf Silf Glat Gloc Feat Sill".split(
    " ",
  );

/** WOFF2's variable-length integer: seven bits a byte, high bit continues. */
function readBase128(buf: Buffer, start: number): [value: number, next: number] {
  let value = 0;
  for (let i = 0; i < 5; i += 1) {
    const byte = buf[start + i];
    if (byte === undefined) break;
    value = ((value << 7) | (byte & 0x7f)) >>> 0;
    if ((byte & 0x80) === 0) return [value, start + i + 1];
  }
  throw new Error("WOFF2: UIntBase128 longer than five bytes");
}

/**
 * The `cmap` table's bytes, out of the WOFF2 container.
 *
 * Tables are stored back to back inside one Brotli stream in directory order,
 * each occupying its transformed length where it has one and its original
 * length otherwise. `cmap` is never transformed, so once it is located it can be
 * read as an ordinary sfnt table.
 */
function readCmapTable(font: Buffer): Buffer {
  if (font.toString("latin1", 0, 4) !== "wOF2") {
    throw new Error("Not a WOFF2 file — the subset was replaced with another format");
  }

  const numTables = font.readUInt16BE(12);
  const totalCompressedSize = font.readUInt32BE(20);

  let cursor = 48;
  const tables: { tag: string; length: number }[] = [];

  for (let i = 0; i < numTables; i += 1) {
    const flags = font[cursor];
    if (flags === undefined) throw new Error("WOFF2: table directory ran off the end");
    cursor += 1;

    const tagIndex = flags & 0x3f;
    let tag: string;
    if (tagIndex === 63) {
      tag = font.toString("latin1", cursor, cursor + 4);
      cursor += 4;
    } else {
      tag = KNOWN_TAGS[tagIndex] ?? "";
    }

    const version = (flags >> 6) & 0x03;
    let [length, next] = readBase128(font, cursor);
    cursor = next;

    // The null transform is version 3 for `glyf` and `loca` and version 0 for
    // everything else; a transformed table carries its own length after the
    // original one.
    const nullTransform = tag === "glyf" || tag === "loca" ? version === 3 : version === 0;
    if (!nullTransform) {
      [length, next] = readBase128(font, cursor);
      cursor = next;
    }

    tables.push({ tag, length });
  }

  const data = brotliDecompressSync(font.subarray(cursor, cursor + totalCompressedSize));

  let offset = 0;
  for (const table of tables) {
    if (table.tag === "cmap") return data.subarray(offset, offset + table.length);
    offset += table.length;
  }
  throw new Error("WOFF2: no cmap table — the subset carries no character mapping");
}

/** Every code point the font maps to a real glyph. */
function readCoveredCodePoints(cmap: Buffer): Set<number> {
  const covered = new Set<number>();
  const numSubtables = cmap.readUInt16BE(2);

  for (let i = 0; i < numSubtables; i += 1) {
    const start = cmap.readUInt32BE(8 + i * 8);
    const format = cmap.readUInt16BE(start);

    if (format === 4) {
      const segCountX2 = cmap.readUInt16BE(start + 6);
      const endBase = start + 14;
      const startBase = endBase + segCountX2 + 2;
      const deltaBase = startBase + segCountX2;
      const rangeBase = deltaBase + segCountX2;

      for (let seg = 0; seg < segCountX2 / 2; seg += 1) {
        const segEnd = cmap.readUInt16BE(endBase + seg * 2);
        const segStart = cmap.readUInt16BE(startBase + seg * 2);
        const delta = cmap.readInt16BE(deltaBase + seg * 2);
        const rangeOffset = cmap.readUInt16BE(rangeBase + seg * 2);
        if (segStart === 0xffff) continue;

        for (let code = segStart; code <= segEnd; code += 1) {
          let glyph: number;
          if (rangeOffset === 0) {
            glyph = (code + delta) & 0xffff;
          } else {
            const index = rangeBase + seg * 2 + rangeOffset + (code - segStart) * 2;
            if (index + 1 >= cmap.length) continue;
            glyph = cmap.readUInt16BE(index);
            if (glyph !== 0) glyph = (glyph + delta) & 0xffff;
          }
          if (glyph !== 0) covered.add(code);
        }
      }
      continue;
    }

    if (format === 12) {
      const numGroups = cmap.readUInt32BE(start + 12);
      for (let group = 0; group < numGroups; group += 1) {
        const base = start + 16 + group * 12;
        const first = cmap.readUInt32BE(base);
        const last = cmap.readUInt32BE(base + 4);
        for (let code = first; code <= last; code += 1) covered.add(code);
      }
    }
  }

  return covered;
}

const COVERED = readCoveredCodePoints(readCmapTable(readFileSync(FONT_PATH)));

/**
 * Names every character a string uses that the font does not carry, so a
 * failure says which glyph rather than that some glyph is wrong.
 *
 * Newline and tab are structure rather than glyphs — art is joined with
 * newlines — and are not expected in a `cmap`.
 */
function uncovered(text: string): string[] {
  const missing = new Set<string>();
  for (const character of text) {
    const code = character.codePointAt(0);
    if (code === undefined || code < 0x20) continue;
    if (!COVERED.has(code)) {
      missing.add(`U+${code.toString(16).toUpperCase().padStart(4, "0")} ${character}`);
    }
  }
  return [...missing].sort();
}

describe("the shipped font subset", () => {
  it("covers printable ASCII, box drawing and block elements", () => {
    // §2's three named ranges. Art is written from all three and the grid
    // arithmetic assumes every one of them has the same advance.
    for (let code = 0x20; code <= 0x7e; code += 1) expect(COVERED.has(code)).toBe(true);
    for (let code = 0x2500; code <= 0x257f; code += 1) expect(COVERED.has(code)).toBe(true);
    for (let code = 0x2580; code <= 0x259f; code += 1) expect(COVERED.has(code)).toBe(true);
  });

  it("does not carry the section sign or the plus-minus sign", () => {
    // Not a wish: this is what the shipped file contains, and copy has to be
    // written around it until someone re-cuts the font. Recorded in §2 so the
    // next run reaching for `§4` knows before it renders.
    expect(COVERED.has(0x00a7)).toBe(false);
    expect(COVERED.has(0x00b1)).toBe(false);
  });
});

describe("lib/ascii.ts", () => {
  it("draws every piece of art from characters the font carries", () => {
    for (const art of [WORDMARK, MARK, MARK_SMALL]) {
      expect(uncovered(art.rows.join("\n"))).toEqual([]);
    }
  });

  it("scrambles through characters the font carries", () => {
    // A fallback glyph mid-decode is the same broken grid, for 900ms.
    expect(uncovered(SCRAMBLE_GLYPHS)).toEqual([]);
  });
});

/**
 * The text every route actually renders, tags removed and the five entities
 * React escapes put back.
 *
 * Tags are stripped rather than parsed, which drops attribute values with them
 * — a `class` or an `href` is not a glyph anybody sees. What survives is text
 * content, including the `sr-only` descriptions on the figures, which is right:
 * those are read aloud rather than drawn, but they are in the DOM either way
 * and a stray character in one is still a character this site put there.
 */
function renderedText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replaceAll("&quot;", '"')
    .replaceAll("&#x27;", "'")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&amp;", "&");
}

const ROUTE_MARKUP: Record<string, string> = {
  "/": renderToStaticMarkup(<HomePage />),
  "/arithmetic": renderToStaticMarkup(<ArithmeticPage />),
  "/filter": renderToStaticMarkup(<FilterPage />),
  "/status": renderToStaticMarkup(<StatusPage />),
  header: renderToStaticMarkup(<SiteHeader />),
  footer: renderToStaticMarkup(<SiteFooter />),
};

describe.each(Object.entries(ROUTE_MARKUP))(
  "%s",
  (_route, markup) => {
    it("renders no character the font would have to fall back for", () => {
      // This is the assertion that caught `§` and `±`. Both looked correct in
      // a screenshot; both were a different font at a different advance width.
      expect(uncovered(renderedText(markup))).toEqual([]);
    });
  },
);
