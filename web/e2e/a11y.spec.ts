import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { DESKTOP, MISSING_PATH, MOBILE, PAGES } from "./helpers";

/**
 * An automated scan catches a minority of accessibility defects, but the ones it
 * catches — contrast, names, landmarks, heading order — are exactly the ones a
 * site of this kind regresses on. Serious and critical fail the build; moderate
 * and minor are reported for a person to weigh.
 *
 * This is also the only check that covers §1's measured contrast ratios: axe
 * re-measures the rendered result, which is the claim that matters. The token
 * table is the reasoning, not the assertion.
 */
const BLOCKING = new Set(["serious", "critical"]);

for (const [label, viewport] of [
  ["desktop", DESKTOP],
  ["mobile", MOBILE],
] as const) {
  test.describe(`axe — ${label}`, () => {
    for (const path of [...PAGES, MISSING_PATH]) {
      test(`${path} has no serious or critical violations`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await page.goto(path, { waitUntil: "networkidle" });

        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .analyze();

        const blocking = results.violations.filter((violation) =>
          BLOCKING.has(violation.impact ?? ""),
        );

        expect(
          blocking.map(
            (violation) =>
              `${violation.impact}: ${violation.id} — ${violation.nodes
                .map((node) => node.target.join(" "))
                .slice(0, 4)
                .join(" | ")}`,
          ),
          `axe on ${path} at ${label}`,
        ).toEqual([]);
      });
    }
  });
}
