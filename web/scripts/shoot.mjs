/**
 * Screenshot and layout-probe harness. Not part of the app build — run against
 * an already-serving instance:
 *
 *   npm run build && npm start -- --port 4322 &
 *   node scripts/shoot.mjs http://127.0.0.1:4322 [outDir]
 *
 * Shoots the home page at all six widths docs/design-language.md §3 covers and
 * the subpages at the two extremes, plus the two states a reader cannot catch
 * by eye — the reduced-motion hero, which has to be *already* resolved rather
 * than caught mid-scramble, and the focus ring on the filled button, which is
 * the one control whose own text is canvas-dark. It reports anything that
 * overflows the viewport or its own box at either end.
 *
 * The second argument exists so the same script can be run from a checkout of
 * an older commit to produce the "before" half of a comparison without that
 * checkout needing this version of the file.
 */
import { mkdirSync, writeFileSync } from "node:fs";

import { chromium } from "@playwright/test";

const base = process.argv[2] ?? "http://127.0.0.1:4322";
const outDir = process.argv[3] ?? "docs/screenshots";
mkdirSync(outDir, { recursive: true });

/* The six widths the layout is claimed to hold at: the narrowest phone still
   in use, a current phone, portrait tablet, landscape tablet, laptop, desktop. */
const VIEWPORTS = [
  { name: "320", width: 320, height: 780 },
  { name: "390", width: 390, height: 844 },
  { name: "768", width: 768, height: 1024 },
  { name: "1024", width: 1024, height: 768 },
  { name: "1440", width: 1440, height: 900 },
  { name: "1920", width: 1920, height: 1080 },
];

/** The two ends of that range. The subpages are shot at these only. */
const EXTREMES = new Set(["320", "1920"]);

const HOME = { name: "home", path: "/" };

/**
 * The subpages, read out of the sitemap the site serves rather than listed
 * here — `app/sitemap.ts` derives itself from `NAV_LINKS`, so a new page is
 * shot with no edit to this file.
 */
async function subpages() {
  const xml = await (await fetch(`${base}/sitemap.xml`)).text();
  return [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)]
    .map((match) => new URL(match[1]).pathname)
    .filter((path) => path !== "/")
    .map((path) => ({ name: path.replace(/^\//, ""), path }));
}

/** Everything that is wider than it should be, at this width, on this page. */
async function probe(page) {
  return page.evaluate(() => {
    const root = document.documentElement;
    const describe = (element) =>
      `${element.tagName.toLowerCase()}.${String(element.className).slice(0, 42)}`;

    const past = [...document.querySelectorAll("body *")]
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.right > root.clientWidth + 1;
      })
      .slice(0, 8)
      .map(
        (element) =>
          `${describe(element)} right=${Math.round(element.getBoundingClientRect().right)}`,
      );

    const selfOverflow = [...document.querySelectorAll("body *")]
      .filter((element) => element.scrollWidth > element.clientWidth + 1 && element.clientWidth > 0)
      .slice(0, 8)
      .map(
        (element) =>
          `${describe(element)} ${element.clientWidth}->${element.scrollWidth} ovf=${getComputedStyle(element).overflowX}`,
      );

    // Smallest art on the page. Container-query sizing has no lower bound, so
    // this is here to be read rather than asserted on: the inline marks are
    // deliberately tiny, and only a drop in the *readable* figures is a bug.
    const smallest = [...document.querySelectorAll("pre.wn-figure, pre.wn-ascii")]
      .map((element) => Number.parseFloat(getComputedStyle(element).fontSize))
      .sort((a, b) => a - b)[0];

    return {
      scrollW: root.scrollWidth,
      clientW: root.clientWidth,
      smallestArtPx: smallest ? Math.round(smallest * 10) / 10 : null,
      past,
      selfOverflow,
    };
  });
}

const browser = await chromium.launch();
const ROUTES = [HOME, ...(await subpages())];
const overflowing = [];

for (const viewport of VIEWPORTS) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();

  for (const route of ROUTES) {
    if (route !== HOME && !EXTREMES.has(viewport.name)) continue;

    await page.goto(`${base}${route.path}`, { waitUntil: "networkidle" });
    // Long enough for the hero decode and the longest scripted figure to settle.
    await page.waitForTimeout(1400);

    await page.screenshot({ path: `${outDir}/${route.name}-${viewport.name}.png` });
    await page.screenshot({
      path: `${outDir}/${route.name}-${viewport.name}-full.png`,
      fullPage: true,
    });

    const report = await probe(page);
    if (report.scrollW > report.clientW || report.past.length > 0) {
      overflowing.push(`${route.name}@${viewport.name}`);
    }
    console.log(`${route.name} ${viewport.name}`, JSON.stringify(report, null, 1));
  }

  await context.close();
}

/* The reduced-motion shot is the one a reader cannot take by eye: it has to
   show the hero already resolved rather than caught mid-scramble. */
{
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.screenshot({ path: `${outDir}/home-1440-reduced-motion.png` });
  await context.close();
}

/* The focus ring, on the one element it would be invisible on if it were ever
   transitioned: the filled button, whose own text colour is canvas-dark. */
{
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  await page.goto(base, { waitUntil: "networkidle" });
  await page.waitForTimeout(1400);

  const button = page.locator("main a", { hasText: "Get the source" }).first();
  if (await button.count()) {
    await button.focus();
    const box = await button.boundingBox();
    await page.screenshot({
      path: `${outDir}/home-1440-focus-ring.png`,
      clip: {
        x: Math.max(0, box.x - 40),
        y: Math.max(0, box.y - 40),
        width: box.width + 80,
        height: box.height + 80,
      },
    });
  } else {
    console.log("no filled button found for the focus-ring shot");
  }
  await context.close();
}

/* The share card, straight off the route rather than through a browser: it is
   already a PNG, and rendering it in a page would only add a scrollbar. */
{
  const response = await fetch(`${base}/opengraph-image`);
  if (response.ok) {
    writeFileSync(
      `${outDir}/opengraph-card.png`,
      Buffer.from(await response.arrayBuffer()),
    );
  } else {
    console.log(`opengraph-image returned ${response.status}`);
  }
}

await browser.close();

console.log(
  overflowing.length === 0
    ? "\nno element overflowed the viewport at any width"
    : `\noverflowed: ${overflowing.join(", ")}`,
);
