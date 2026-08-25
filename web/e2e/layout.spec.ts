import { expect, test } from "@playwright/test";

import { MISSING_PATH, PAGES, WIDTHS } from "./helpers";

/**
 * Horizontal overflow is the failure this site is most exposed to: it is built
 * out of deliberately overlong character runs (the rules, the panel frames) that
 * are clipped rather than wrapped, and one missing `overflow: hidden` puts the
 * whole page on a horizontal scrollbar.
 */
test.describe("no horizontal overflow", () => {
  for (const width of WIDTHS) {
    for (const path of [...PAGES, MISSING_PATH]) {
      test(`${path} at ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.goto(path, { waitUntil: "networkidle" });

        const report = await page.evaluate(() => {
          const root = document.documentElement;
          const offenders = [...document.querySelectorAll<HTMLElement>("body *")]
            .filter((element) => {
              const rect = element.getBoundingClientRect();
              return rect.width > 0 && rect.right > root.clientWidth + 1;
            })
            .slice(0, 5)
            .map((element) => {
              const rect = element.getBoundingClientRect();
              return `${element.tagName.toLowerCase()}.${element.className
                .toString()
                .split(/\s+/)
                .slice(0, 2)
                .join(".")} right=${Math.round(rect.right)}`;
            });
          return {
            scrollWidth: root.scrollWidth,
            clientWidth: root.clientWidth,
            offenders,
          };
        });

        expect(
          report.scrollWidth,
          `overflow at ${width}px on ${path}; widest: ${report.offenders.join(" | ")}`,
        ).toBeLessThanOrEqual(report.clientWidth);
      });
    }
  }
});

test.describe("the character grid holds", () => {
  test("the hero art never wraps", async ({ page }) => {
    // §4: a wrapped piece of ASCII art is worse than no art. The art is sized
    // by container query rather than by breakpoint, so this is the check that
    // the arithmetic works at every width rather than at the ones picked.
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");

      const rows = await page
        .locator("main pre.wn-ascii")
        .first()
        .evaluate((element) => {
          const style = getComputedStyle(element);
          return {
            whiteSpace: style.whiteSpace,
            lines: (element.textContent ?? "").split("\n").length,
            height: element.getBoundingClientRect().height,
            lineHeight:
              Number.parseFloat(style.lineHeight) ||
              Number.parseFloat(style.fontSize),
          };
        });

      expect(rows.whiteSpace, `white-space at ${width}px`).toBe("pre");
      // A wrapped block would be taller than one line-box per row of art.
      expect(rows.height, `art height at ${width}px`).toBeLessThanOrEqual(
        rows.lineHeight * rows.lines + 2,
      );
    }
  });

  test("body copy is never set wider than the measure", async ({ page }) => {
    // §2: never a paragraph wider than 72ch. `ch` resolves against the
    // element's own font-size, so this is asked in the browser rather than
    // computed from the class list.
    await page.setViewportSize({ width: 1920, height: 1080 });

    for (const path of PAGES) {
      await page.goto(path, { waitUntil: "networkidle" });

      const tooWide = await page.evaluate(() =>
        [...document.querySelectorAll<HTMLElement>("main p")]
          .filter((element) => (element.textContent ?? "").trim().length > 80)
          .map((element) => {
            const style = getComputedStyle(element);
            // One `0` of this element's own font, which is what `ch` means:
            // the glyph's advance, so `letter-spacing` is explicitly not part
            // of it. The `font` shorthand does not reset that property, and
            // this site sets -0.01em on `body` — inheriting it makes every
            // paragraph measure about 1.7% wider than it is.
            const probe = document.createElement("span");
            probe.textContent = "0";
            probe.style.font = style.font;
            probe.style.letterSpacing = "normal";
            probe.style.position = "absolute";
            probe.style.visibility = "hidden";
            document.body.append(probe);
            const column = probe.getBoundingClientRect().width;
            probe.remove();
            return {
              chars: element.getBoundingClientRect().width / column,
              text: (element.textContent ?? "").slice(0, 40),
            };
          })
          .filter((entry) => entry.chars > 72)
          .map((entry) => `${entry.chars.toFixed(0)}ch ${JSON.stringify(entry.text)}`),
      );

      expect(tooWide, `paragraphs over 72ch on ${path}`).toEqual([]);
    }
  });
});
