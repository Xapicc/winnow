import { expect, test } from "@playwright/test";

import { ROUTES, SITE_URL } from "../lib/site";
import { PAGES } from "./helpers";

/**
 * What a host has to be able to serve. These run against `next start`, which is
 * what a platform runs; nothing here needs an environment variable, and that is
 * half of what is being asserted.
 */

test("the social card is a real PNG", async ({ request }) => {
  const response = await request.get("/opengraph-image");

  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("image/png");

  const body = await response.body();
  expect(body.byteLength).toBeGreaterThan(1_000);
  // PNG magic number, so this is an image and not an HTML error page.
  expect([...body.subarray(0, 4)]).toEqual([0x89, 0x50, 0x4e, 0x47]);
});

test("every page points at the social card, and says it is a large one", async ({
  page,
}) => {
  for (const path of PAGES) {
    await page.goto(path);

    const image = page.locator('meta[property="og:image"]');
    await expect(image, `og:image on ${path}`).toHaveCount(1);
    expect(
      await image.getAttribute("content"),
      `og:image url on ${path}`,
    ).toMatch(/^https:\/\/.+\/opengraph-image/);

    // §2: a `summary_large_image` card with no image is a broken card, so the
    // two move together or not at all.
    await expect(
      page.locator('meta[name="twitter:card"]'),
      `twitter:card on ${path}`,
    ).toHaveAttribute("content", "summary_large_image");
  }
});

test("the icon serves as an image", async ({ request }) => {
  const response = await request.get("/icon.svg");
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("image/svg+xml");
});

test("sitemap.xml lists exactly the routes the site serves", async ({ request }) => {
  const response = await request.get("/sitemap.xml");

  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("xml");

  const body = await response.text();
  const listed = [...body.matchAll(/<loc>([^<]+)<\/loc>/g)].map(
    (match) => match[1] ?? "",
  );

  expect(listed.sort()).toEqual(
    ROUTES.map((route) => new URL(route, SITE_URL).href).sort(),
  );

  for (const url of listed) {
    const path = new URL(url).pathname;
    const listedPage = await request.get(path);
    expect(listedPage.status(), `${path} is listed in the sitemap`).toBe(200);
  }
});

test("robots.txt allows crawling and points at the sitemap", async ({ request }) => {
  const response = await request.get("/robots.txt");

  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("text/plain");

  const body = await response.text();
  expect(body).toContain("User-Agent: *");
  expect(body).toContain("Allow: /");
  expect(body).toContain(`Sitemap: ${new URL("/sitemap.xml", SITE_URL).href}`);
});

test("the served HTML carries no local paths or secrets", async ({ request }) => {
  for (const path of PAGES) {
    const html = await (await request.get(path)).text();
    expect(html, `${path} leaks a filesystem path`).not.toMatch(
      /\/(home|Users)\/[a-z]/i,
    );
    expect(html, `${path} leaks a workspace path`).not.toContain("/workspace");
  }
});

test("the font is served from this origin, with no runtime CDN", async ({ page }) => {
  // §2: self-hosted, no runtime font CDN. A `@font-face` pointing at Google
  // would still render — it would just make every visit a third-party request.
  const origins = new Set<string>();
  page.on("request", (request) => {
    if (request.resourceType() === "font") origins.add(new URL(request.url()).origin);
  });

  await page.goto("/", { waitUntil: "networkidle" });

  expect([...origins]).toEqual([new URL(page.url()).origin]);
});
