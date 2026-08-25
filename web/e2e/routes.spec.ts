import { expect, test } from "@playwright/test";

import { SITE_NAME } from "../lib/site";
import { MISSING_PATH, PAGES, watchForProblems } from "./helpers";

test.describe("routes", () => {
  for (const path of PAGES) {
    test(`${path} returns 200 and serves clean`, async ({ page }) => {
      const problems = watchForProblems(page);
      const response = await page.goto(path, { waitUntil: "networkidle" });

      expect(response?.status(), `status for ${path}`).toBe(200);
      expect(problems.consoleErrors, `console errors on ${path}`).toEqual([]);
      expect(problems.failedRequests, `failed requests on ${path}`).toEqual([]);
    });

    test(`${path} carries the site chrome`, async ({ page }) => {
      await page.goto(path);

      await expect(page.locator('header nav[aria-label="Primary"]')).toBeVisible();
      await expect(page.locator('footer nav[aria-label="Footer"]')).toBeVisible();
      await expect(page.locator('a[href="#main"]')).toHaveCount(1);
      await expect(page.locator("main")).toHaveCount(1);
    });
  }

  test("an unknown path 404s and still renders the site's own chrome", async ({
    page,
  }) => {
    const problems = watchForProblems(page);
    const response = await page.goto(MISSING_PATH, { waitUntil: "networkidle" });

    expect(response?.status()).toBe(404);
    await expect(page.locator('header nav[aria-label="Primary"]')).toBeVisible();
    await expect(page.locator('footer nav[aria-label="Footer"]')).toBeVisible();
    await expect(page.locator('a[href="#main"]')).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "No such page" })).toBeVisible();

    expect(problems.consoleErrors).toEqual([]);
    expect(problems.failedRequests).toEqual([]);
  });
});

test.describe("the hero", () => {
  test("carries the product name on a real h1, with the art hidden", async ({
    page,
  }) => {
    await page.goto("/");

    const headings = page.locator("h1");
    await expect(headings).toHaveCount(1);
    await expect(headings).toHaveText(SITE_NAME);

    // §4: a screen reader gets `winnow`, not 473 block characters.
    const art = page.locator("pre.wn-ascii, pre.wn-figure");
    expect(await art.count()).toBeGreaterThan(0);
    for (const block of await art.all()) {
      await expect(block).toHaveAttribute("aria-hidden", "true");
    }
  });

  test("the h1 is available to assistive technology, not display:none", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { level: 1, name: SITE_NAME }),
    ).toBeAttached();
  });
});

test.describe("links", () => {
  for (const path of PAGES) {
    test(`in-page anchors on ${path} resolve to an element`, async ({ page }) => {
      await page.goto(path);

      const dead = await page.evaluate(() =>
        [...document.querySelectorAll('a[href^="#"]')]
          .map((anchor) => (anchor.getAttribute("href") ?? "").slice(1))
          .filter((id) => id.length > 0 && document.getElementById(id) === null),
      );
      expect(dead, `dead anchors on ${path}`).toEqual([]);
    });

    test(`internal links on ${path} resolve to a real route`, async ({
      page,
      request,
    }) => {
      await page.goto(path);

      const hrefs = await page.evaluate(() => [
        ...new Set(
          [...document.querySelectorAll('a[href^="/"]')].map(
            (anchor) => anchor.getAttribute("href") ?? "",
          ),
        ),
      ]);
      expect(hrefs.length).toBeGreaterThan(0);

      for (const href of hrefs) {
        const response = await request.get(href.split("#")[0] ?? href);
        expect(response.status(), `${href} from ${path}`).toBe(200);
      }
    });

    test(`cross-page anchors from ${path} land on a real id`, async ({
      page,
      request,
    }) => {
      // A bare `#formula` is checked above against the page it is written on.
      // A `/arithmetic#formula` is only wrong on the *other* page, which is
      // where the home page's six deep links all point.
      await page.goto(path);

      const deep = await page.evaluate(() => [
        ...new Set(
          [...document.querySelectorAll('a[href^="/"]')]
            .map((anchor) => anchor.getAttribute("href") ?? "")
            .filter((href) => href.includes("#")),
        ),
      ]);

      for (const href of deep) {
        const [route = "/", anchor = ""] = href.split("#");
        const html = await (await request.get(route || "/")).text();
        expect(html, `${href} from ${path}`).toContain(`id="${anchor}"`);
      }
    });

    test(`external links on ${path} are absolute and open safely`, async ({
      page,
    }) => {
      await page.goto(path);

      const external = await page.evaluate(() =>
        [...document.querySelectorAll("a[href]")]
          .map((anchor) => ({
            href: anchor.getAttribute("href") ?? "",
            target: anchor.getAttribute("target"),
            rel: anchor.getAttribute("rel") ?? "",
          }))
          .filter((link) => /^[a-z][a-z0-9+.-]*:/i.test(link.href)),
      );
      expect(external.length, `external links on ${path}`).toBeGreaterThan(0);

      for (const link of external) {
        expect(() => new URL(link.href), link.href).not.toThrow();
        expect(new URL(link.href).protocol, link.href).toBe("https:");
        if (link.target === "_blank") {
          expect(link.rel.split(/\s+/), `rel on ${link.href}`).toContain("noopener");
        }
      }
    });
  }
});
