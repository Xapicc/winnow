import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Ascii } from "@/components/Ascii";
import { Button } from "@/components/Button";
import { DecodeAscii } from "@/components/DecodeAscii";
import { MARK_SMALL, WORDMARK, toArt } from "@/lib/ascii";
import { REPO_URL } from "@/lib/site";

/**
 * The contracts docs/design-language.md puts in the components rather than in
 * `lib/`. Everything on this site renders on the server, so
 * `renderToStaticMarkup` is the whole harness — and for `DecodeAscii`, the one
 * client component, that is itself the assertion (§5: the server renders the
 * resolved art).
 *
 * `Ticks` has its own file; this one is everything else.
 */

describe("Ascii", () => {
  it("hands the column count to CSS so the art can be sized from it", () => {
    const html = renderToStaticMarkup(<Ascii art={WORDMARK} cap={30} />);
    expect(html).toContain(`--ascii-cols:${WORDMARK.cols}`);
    expect(html).toContain("--ascii-cap:30px");
  });

  it("is aria-hidden, because a real heading carries the accessible name", () => {
    expect(renderToStaticMarkup(<Ascii art={MARK_SMALL} />)).toContain(
      'aria-hidden="true"',
    );
  });

  it("renders the rows as one newline-joined text node", () => {
    const art = toArt(["ab", "c"]);
    expect(renderToStaticMarkup(<Ascii art={art} />)).toContain("ab\nc ");
  });
});

describe("DecodeAscii", () => {
  it("renders the resolved art on the server, so no-JS and pre-paint are correct", () => {
    const html = renderToStaticMarkup(<DecodeAscii art={WORDMARK} cap={30} />);
    expect(html).toContain(WORDMARK.rows.join("\n"));
    expect(html).toContain('aria-hidden="true"');
  });
});

describe("Button", () => {
  it("gives an external link a new tab and rel=noopener", () => {
    // `target="_blank"` without it hands the opened document a live
    // `window.opener` back into this one.
    const html = renderToStaticMarkup(
      <Button href={REPO_URL} external>
        Get the source
      </Button>,
    );
    expect(html).toContain('target="_blank"');
    expect(html).toMatch(/rel="[^"]*\bnoopener\b/);
  });

  it("leaves an internal link in the same tab", () => {
    const html = renderToStaticMarkup(<Button href="/filter">the filter</Button>);
    expect(html).not.toContain("target=");
    expect(html).not.toContain("rel=");
  });

  it("brackets a ghost label and hides the brackets from screen readers", () => {
    const html = renderToStaticMarkup(
      <Button href="/arithmetic" variant="ghost">
        the break-even formula
      </Button>,
    );
    expect(html).toContain('<span aria-hidden="true" class="text-fg-faint">[</span>');
    expect(html).toContain('<span aria-hidden="true" class="text-fg-faint">]</span>');
  });

  it("fills a primary control with the accent and canvas-dark text, never white", () => {
    // §1, and the rule is stronger here than on the blue reference site:
    // white on `--color-accent` measures 2.15:1 and on `--color-accent-deep`
    // 3.39:1. Canvas-dark on the accent is 7.59:1, the same ratio the other
    // way round.
    const html = renderToStaticMarkup(<Button href="/status">status</Button>);
    expect(html).toContain("bg-accent");
    expect(html).toContain("text-canvas");
    expect(html).not.toContain("text-white");
    expect(html).not.toContain("text-fg");
  });

  it("keeps the glow and the fringe off the filled control", () => {
    // §6: both are text-shadows, and this is the one place the text is
    // canvas-dark on a saturated fill — the glow paints an orange halo behind
    // dark glyphs and the fringe paints a red one on them. Both read as a
    // rendering fault rather than as texture.
    const html = renderToStaticMarkup(<Button href="/status">status</Button>);
    expect(html).not.toContain("wn-glow");
    expect(html).not.toContain("wn-aberrate");
  });

  it("does not transition the focus ring on either variant", () => {
    // §5: `.wn-state` transitions colour and background only. Tailwind's
    // `transition-colors` includes `outline-color`, which fades the ring in
    // from the element's own colour — near-black on the filled button.
    for (const variant of ["primary", "ghost"] as const) {
      const html = renderToStaticMarkup(
        <Button href="/status" variant={variant}>
          status
        </Button>,
      );
      expect(html, variant).not.toContain("transition-colors");
    }
  });
});
