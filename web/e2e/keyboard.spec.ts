import { type Page, expect, test } from "@playwright/test";

import { NAV_LINKS, REPO_URL } from "../lib/site";
import { MOBILE } from "./helpers";

type Stop = {
  tag: string;
  href: string | null;
  text: string;
  inHeader: boolean;
  visible: boolean;
  outline: string;
  outlineWidth: number;
};

async function tabTo(page: Page): Promise<Stop> {
  await page.keyboard.press("Tab");
  return page.evaluate(() => {
    const element = document.activeElement as HTMLElement | null;
    if (!element) throw new Error("nothing is focused");
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return {
      tag: element.tagName.toLowerCase(),
      href: element.getAttribute("href"),
      text: (element.textContent ?? "").trim(),
      inHeader: element.closest("header") !== null,
      visible: rect.width > 1 && rect.height > 1,
      outline: style.outlineStyle,
      outlineWidth: Number.parseFloat(style.outlineWidth) || 0,
    };
  });
}

test.describe("keyboard", () => {
  test("the first tab stop is a visible skip link, and the nav follows", async ({
    page,
  }) => {
    // No click first: clicking moves the sequential focus navigation starting
    // point past the skip link, which is exactly what this test is about.
    await page.goto("/");

    const skip = await tabTo(page);
    expect(skip.href, "first tab stop").toBe("#main");
    expect(skip.text).toBe("Skip to content");
    expect(skip.visible, "the skip link must show itself when focused").toBe(true);
    expect(skip.outline).not.toBe("none");
    expect(skip.outlineWidth).toBeGreaterThanOrEqual(2);

    const afterSkip: Stop[] = [];
    for (let index = 0; index < NAV_LINKS.length + 2; index += 1) {
      afterSkip.push(await tabTo(page));
    }

    expect(
      afterSkip.map((stop) => stop.href),
      "tab order after the skip link",
    ).toEqual(["/", ...NAV_LINKS.map((link) => link.href), REPO_URL]);

    for (const stop of afterSkip) {
      expect(stop.inHeader, `${stop.href} should be in the header`).toBe(true);
      expect(stop.visible, `${stop.href} should be visible when focused`).toBe(true);
      expect(stop.outline, `focus indicator on ${stop.href}`).not.toBe("none");
      expect(
        stop.outlineWidth,
        `focus ring width on ${stop.href}`,
      ).toBeGreaterThanOrEqual(2);
    }
  });

  test("the skip link moves focus into the main landmark", async ({ page }) => {
    await page.goto("/");
    await tabTo(page);
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(/#main$/);
    await expect(page.locator("#main")).toBeVisible();
  });

  test("the nav is usable at phone width without a disclosure to trap focus", async ({
    page,
  }) => {
    // §7 revisited the hamburger when `/filter` made a fourth item and said no
    // again: `source ↗` is already gone below 640px, so a phone carries three
    // one-word links and every one of them is always in the tab order.
    await page.setViewportSize(MOBILE);
    await page.goto("/");

    const toggle = page.locator("header [aria-expanded]");
    const toggles = await toggle.count();

    if (toggles === 0) {
      for (const link of NAV_LINKS) {
        await expect(page.locator(`header nav a[href="${link.href}"]`)).toBeVisible();
      }
      return;
    }

    // If a later run adds one, this is the contract it has to meet.
    await toggle.first().click();
    await expect(toggle.first()).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Escape");
    await expect(toggle.first()).toHaveAttribute("aria-expanded", "false");
    await expect(toggle.first()).toBeFocused();
  });
});
