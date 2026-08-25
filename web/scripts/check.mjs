/**
 * Behavioural checks against a serving instance:
 *
 *   npm run build && npm start -- --port 4322 &
 *   node scripts/check.mjs http://127.0.0.1:4322
 *
 * These are the claims docs/design-language.md makes that markup alone cannot
 * prove: that the hero decode actually scrambles and resolves, that the
 * reduced-motion path never animates at all, that no rendered sentence falls
 * below AA, that the focus ring is the accent at the instant it appears, and
 * that §1's measured table is still what the browser measures.
 *
 * It overlaps `e2e/` deliberately and is not a duplicate of it: Playwright
 * reports pass or fail, and this reports the *number* — the ratio a token
 * measures, the widths that overflowed, which tab stop was short of 24px. A
 * regression here is meant to be readable without opening a trace.
 *
 * Playwright comes from this project's own `node_modules` rather than from a
 * global install, so the script runs anywhere `npm install` has.
 *
 * Exits non-zero on the first failed claim.
 */
import { chromium } from "@playwright/test";

const base = process.argv[2] ?? "http://127.0.0.1:4322";
const results = [];

/** The widths §3 has to hold at. */
const WIDTHS = [320, 390, 768, 1024, 1440, 1920];

/** `--color-accent`, which is what a focus ring has to be the moment it lands. */
const ACCENT_RGB = "rgb(255, 122, 26)";

/**
 * §1's table, as the browser should measure it. Ratios against
 * `--color-canvas` and against `--color-surface`, to two decimals. This is the
 * claim under test: the numbers were recomputed for an orange accent rather
 * than carried across from the blue reference site, and a token edited without
 * recomputing them is exactly the failure the table exists to catch.
 */
const DOCUMENTED = {
  "--color-fg": [16.33, 15.43],
  "--color-fg-muted": [7.18, 6.78],
  "--color-fg-faint": [3.92, 3.71],
  "--color-accent": [7.59, 7.17],
  "--color-accent-deep": [5.84, 5.52],
  "--color-ok": [9.79, 9.25],
  "--color-danger": [6.85, 6.47],
};

function check(name, passed, detail = "") {
  results.push({ name, passed, detail });
  console.log(`${passed ? "PASS" : "FAIL"}  ${name}${detail ? `  ${detail}` : ""}`);
}

const heroText = (page) => page.locator("main pre.wn-ascii").first().textContent();

/**
 * Every route the site publishes, read out of the sitemap it serves rather
 * than listed here. `app/sitemap.ts` derives itself from `NAV_LINKS`, so a page
 * added to the nav is checked by this script with no edit — and a page that is
 * not in the sitemap is one nothing links to, which §7 says should not exist.
 */
async function routesFromSitemap() {
  const xml = await (await fetch(`${base}/sitemap.xml`)).text();
  return [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(
    (match) => new URL(match[1]).pathname,
  );
}

const ROUTES = await routesFromSitemap();
check("the sitemap names at least the home page", ROUTES.includes("/"), ROUTES.join(" "));

const browser = await chromium.launch();

// --- default: the decode runs and resolves -------------------------------
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(base, { waitUntil: "domcontentloaded" });

  await page.waitForTimeout(160);
  const early = (await heroText(page)) ?? "";
  await page.waitForTimeout(1600);
  const settled = (await heroText(page)) ?? "";

  check(
    "hero scrambles on load",
    early !== settled && /[▒▚▞]/.test(early),
    `early sample: ${JSON.stringify(early.slice(0, 20))}`,
  );
  // The funnel's intake bar, centred over the word. Eleven columns in, three
  // out — §4. Checked by shape rather than by a transcription of the art.
  const rows = settled.split("\n");
  check(
    "hero resolves to the wordmark",
    rows[0]?.trim() === "█".repeat(11) && rows.at(-1)?.includes("██ ██"),
    `first row: ${JSON.stringify(rows[0] ?? "")}`,
  );
  check(
    "resolved art is rectangular",
    new Set(rows.map((row) => row.length)).size === 1,
    `${rows.length} rows × ${rows[0]?.length ?? 0} cols`,
  );
  await page.close();
}

// --- reduced motion: no animation at all ---------------------------------
{
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
  });
  await page.goto(base, { waitUntil: "domcontentloaded" });

  const samples = [];
  for (let index = 0; index < 6; index += 1) {
    samples.push((await heroText(page)) ?? "");
    await page.waitForTimeout(120);
  }
  check(
    "reduced motion never animates the hero",
    new Set(samples).size === 1,
    `${new Set(samples).size} distinct frames`,
  );
  check(
    "reduced motion shows the resolved wordmark",
    (samples[0] ?? "").split("\n")[0]?.trim() === "█".repeat(11),
  );

  const transitions = await page.evaluate(() => {
    const link = document.querySelector("header nav a");
    return link ? getComputedStyle(link).transitionDuration : "none";
  });
  check(
    "reduced motion collapses transitions",
    Number.parseFloat(transitions) < 0.05,
    transitions,
  );
  await page.close();
}

// --- no horizontal overflow, 320 to 1920 ---------------------------------
{
  const page = await browser.newPage();
  const overflowing = [];
  for (const route of ROUTES) {
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`${base}${route}`, { waitUntil: "networkidle" });
      const doc = await page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        client: document.documentElement.clientWidth,
      }));
      if (doc.scroll > doc.client) {
        overflowing.push(`${route}@${width} ${doc.scroll}>${doc.client}`);
      }
    }
  }
  check(
    "no horizontal overflow at any width",
    overflowing.length === 0,
    overflowing.join(", ") || `${ROUTES.length * WIDTHS.length} combinations`,
  );
  await page.close();
}

// --- §1's table, as the browser measures it -------------------------------
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(base, { waitUntil: "domcontentloaded" });

  const measured = await page.evaluate((tokens) => {
    const style = getComputedStyle(document.documentElement);
    const hex = (name) => style.getPropertyValue(name).trim();

    const channels = (colour) => {
      const value = colour.replace("#", "");
      return [0, 2, 4].map((at) => Number.parseInt(value.slice(at, at + 2), 16));
    };
    const luminance = (rgb) =>
      rgb
        .map((channel) => channel / 255)
        .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
        .reduce((sum, c, index) => sum + c * [0.2126, 0.7152, 0.0722][index], 0);
    const ratio = (a, b) => {
      const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
      return (hi + 0.05) / (lo + 0.05);
    };

    const canvas = channels(hex("--color-canvas"));
    const surface = channels(hex("--color-surface"));

    return Object.fromEntries(
      tokens.map((token) => {
        const rgb = channels(hex(token));
        return [
          token,
          [
            Math.round(ratio(rgb, canvas) * 100) / 100,
            Math.round(ratio(rgb, surface) * 100) / 100,
          ],
        ];
      }),
    );
  }, Object.keys(DOCUMENTED));

  const drifted = Object.entries(DOCUMENTED)
    .filter(([token, [onCanvas, onSurface]]) => {
      const [gotCanvas, gotSurface] = measured[token] ?? [];
      return gotCanvas !== onCanvas || gotSurface !== onSurface;
    })
    .map(
      ([token, pair]) =>
        `${token} doc ${pair.join("/")} measured ${(measured[token] ?? []).join("/")}`,
    );

  check(
    "the measured table matches docs/design-language.md section 1",
    drifted.length === 0,
    drifted.join(" | ") ||
      Object.entries(measured)
        .map(([token, pair]) => `${token.replace("--color-", "")} ${pair[0]}`)
        .join(" "),
  );
  await page.close();
}

// --- contrast: nothing readable falls below AA ----------------------------
{
  /* Composited through ancestors rather than read off a class name. A token
     that measures 3.92:1 looks like a tasteful grey on a good monitor, which is
     exactly why the eye cannot do this job — and a class name cannot answer it
     either, because what a string sits on is the flattened stack of every
     semi-transparent background above it (the header is `bg-canvas/92`, and the
     panels sit on surface, not on canvas). */
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const failures = [];
  let sampled = 0;
  let exempt = 0;

  for (const route of ROUTES) {
    await page.goto(`${base}${route}`, { waitUntil: "networkidle" });
    const report = await page.evaluate(() => {
      const parse = (value) => (value.match(/[\d.]+/g) ?? []).map(Number.parseFloat);

      /** Flatten a colour onto an opaque backdrop. */
      const over = ([r, g, b, a = 1], back) =>
        [r, g, b].map((channel, index) => channel * a + back[index] * (1 - a));

      const luminance = ([r, g, b]) =>
        [r, g, b]
          .map((channel) => channel / 255)
          .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
          .reduce((sum, c, index) => sum + c * [0.2126, 0.7152, 0.0722][index], 0);

      const ratio = (a, b) => {
        const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
        return (hi + 0.05) / (lo + 0.05);
      };

      const page = parse(getComputedStyle(document.body).backgroundColor).slice(0, 3);

      /* The backdrop an element actually sits on: walk up compositing every
         semi-transparent background until an opaque one stops it. */
      const backdrop = (element) => {
        let accumulated = null;
        for (let node = element; node; node = node.parentElement) {
          const colour = parse(getComputedStyle(node).backgroundColor);
          if (colour.length < 3 || colour[3] === 0) continue;
          accumulated = accumulated ? over(accumulated, over(colour, page)) : colour;
          if ((accumulated[3] ?? 1) === 1) return accumulated.slice(0, 3);
        }
        return over(accumulated ?? page, page);
      };

      /* What counts as readable, and it is not "what is in the accessibility
         tree". §1 allows `--color-fg-faint` at 3.92:1 for box-drawing frames,
         grid lines, ASCII filler and the bracket glyphs on a ghost button —
         shapes, which WCAG 1.4.3 exempts as decoration — and forbids it for
         anything with a word or a numeral in it. So the test is the content of
         the string, not the `aria-hidden` on its ancestor: `────────` is a
         rule and `01` is an ordinal somebody reads, and both were sitting at
         3.92:1 behind the same attribute. */
      const readable = (text) => /[\p{L}\p{N}]/u.test(text);

      const out = [];
      let seen = 0;
      let shapes = 0;
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const text = (node.textContent ?? "").trim();
        const element = node.parentElement;
        if (!text || !element) continue;
        if (element.closest(".sr-only")) continue;
        const box = element.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) continue;
        if (!readable(text)) {
          shapes += 1;
          continue;
        }

        seen += 1;
        const style = getComputedStyle(element);
        const size = Number.parseFloat(style.fontSize);
        const bold = Number.parseInt(style.fontWeight, 10) >= 700;
        const large = size >= 24 || (bold && size >= 18.66);
        const behind = backdrop(element);
        const measured = ratio(over(parse(style.color), behind), behind);

        if (measured < (large ? 3 : 4.5)) {
          out.push(
            `${location.pathname} ${measured.toFixed(2)}:1 ${JSON.stringify(text.slice(0, 32))}`,
          );
        }
      }
      return { out, seen, shapes };
    });
    failures.push(...report.out);
    sampled += report.seen;
    exempt += report.shapes;
  }

  check(
    "every readable string meets AA",
    failures.length === 0,
    failures.slice(0, 6).join(" | ") ||
      `${sampled} readable text nodes, 0 below AA (${exempt} shape-only nodes exempt)`,
  );
  await page.close();
}

// --- focus ring and target size -------------------------------------------
{
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.goto(base, { waitUntil: "networkidle" });

  /* Sampled with no settling time, because the bug this catches is a 150 ms
     fade rather than an absence. Tailwind's `transition-colors` includes
     `outline-color`, so a ring interpolates from the element's own colour — on
     the filled button that is `--color-canvas`, near-black, and the ring is
     invisible for exactly as long as it is needed. §5 keeps the site off
     `transition-colors` for this reason; nothing but a zero-wait sample can
     tell that rule from a comment about it. */
  const rings = [];
  const short = [];
  for (let stop = 0; stop < 16; stop += 1) {
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => {
      const element = document.activeElement;
      if (!element || element === document.body) return null;
      const style = getComputedStyle(element);
      const box = element.getBoundingClientRect();
      return {
        text: (element.textContent ?? "").trim().slice(0, 24),
        outline: `${style.outlineStyle} ${style.outlineWidth} ${style.outlineColor}`,
        shadow: style.textShadow,
        width: Math.round(box.width),
        height: Math.round(box.height),
      };
    });
    if (!focused) break;
    rings.push(focused);
    if (focused.width < 24 || focused.height < 24) {
      short.push(`${JSON.stringify(focused.text)} ${focused.width}x${focused.height}`);
    }
  }

  const ringed = rings.filter(
    (stop) => stop.outline === `solid 2px ${ACCENT_RGB}`,
  );
  check(
    "every tab stop shows the accent ring immediately",
    rings.length > 0 && ringed.length === rings.length,
    ringed.length === rings.length
      ? `${ringed.length} stops`
      : rings.find((stop) => stop.outline !== `solid 2px ${ACCENT_RGB}`)?.outline ?? "",
  );
  check(
    "every tab stop meets the 24px target minimum",
    short.length === 0,
    short.join(", ") || `${rings.length} stops`,
  );

  /* §6: the fringe is a hover affordance. On focus the ring is already the
     signal and a second effect on the same element competes with it. */
  check(
    "focus adds no chromatic fringe",
    rings.every((stop) => stop.shadow === "none" || !stop.shadow.includes("59, 48")),
    rings.find((stop) => stop.shadow?.includes("59, 48"))?.text ?? "",
  );
  await page.close();
}

// --- the motion vocabulary lives in one place -----------------------------
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(base, { waitUntil: "domcontentloaded" });

  /* lib/motion.ts reads these off :root and throws when one is absent, so a
     missing token is a blank hero rather than a wrong duration. Assert them
     here so it fails in the check run instead of in someone's browser. */
  const missing = await page.evaluate(() => {
    const style = getComputedStyle(document.documentElement);
    return [
      "--motion-fast",
      "--motion-base",
      "--motion-slow",
      "--motion-decode",
      "--motion-decode-churn",
      "--motion-decode-stagger",
      "--ease-grid",
    ].filter((token) => style.getPropertyValue(token).trim() === "");
  });
  check("every motion token is declared on :root", missing.length === 0, missing.join(", "));
  await page.close();
}

// --- accessibility surface ------------------------------------------------
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(base, { waitUntil: "networkidle" });

  const h1 = await page.locator("h1").allTextContents();
  check(
    "exactly one h1 with the product name",
    h1.length === 1 && h1[0] === "winnow",
    JSON.stringify(h1),
  );

  const artHidden = await page.evaluate(() =>
    [...document.querySelectorAll("pre.wn-ascii, pre.wn-figure")].every(
      (element) => element.getAttribute("aria-hidden") === "true",
    ),
  );
  check("all character art is aria-hidden", artHidden);

  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => {
    const element = document.activeElement;
    if (!element) return null;
    const box = element.getBoundingClientRect();
    return {
      text: element.textContent,
      visible: box.width > 0 && box.height > 0,
    };
  });
  check(
    "first tab stop is a visible skip link",
    focused?.text === "Skip to content" && focused.visible === true,
    JSON.stringify(focused),
  );

  await page.close();
}

// --- every route: headings, links, anchors, and the figure contract -------
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  for (const route of ROUTES) {
    const response = await page.goto(`${base}${route}`, { waitUntil: "networkidle" });
    check(`${route} serves 200`, response?.status() === 200, String(response?.status()));

    const headings = await page.locator("h1").allTextContents();
    check(`${route} has exactly one h1`, headings.length === 1, JSON.stringify(headings));

    const broken = await page.evaluate(async () => {
      // Both a `/filter#savings` and a bare `#savings` can point at nothing,
      // and the second kind only resolves on the page it is written on.
      const dead = [];
      const internal = [...document.querySelectorAll('a[href^="/"]')].map(
        (anchor) => anchor.getAttribute("href") ?? "",
      );
      for (const href of new Set(internal)) {
        const [path] = href.split("#");
        const response = await fetch(path, { method: "HEAD" });
        if (!response.ok) dead.push(`${href} -> ${response.status}`);
      }
      const local = [...document.querySelectorAll('a[href^="#"]')].map((anchor) =>
        (anchor.getAttribute("href") ?? "").slice(1),
      );
      for (const id of new Set(local)) {
        if (id && !document.getElementById(id)) dead.push(`#${id} -> no element`);
      }
      return dead;
    });
    check(`${route} has no dead links or anchors`, broken.length === 0, broken.join(", "));

    const figures = await page.evaluate(() =>
      [...document.querySelectorAll("pre.wn-figure")].map((element) => ({
        hidden: element.getAttribute("aria-hidden") === "true",
        described: Boolean(
          element.closest("figure")?.querySelector("figcaption")?.textContent?.trim(),
        ),
      })),
    );
    check(
      `${route} figures are hidden from the tree and captioned`,
      figures.every((figure) => figure.hidden && figure.described),
      `${figures.length} figures`,
    );
  }

  // Cross-page anchors: the home page hands six of these to the two reference
  // pages, and a wrong one scrolls nowhere — which looks, to whoever clicks it,
  // exactly like a page that has not loaded.
  const crossPage = await page.evaluate(async (routes) => {
    const dead = [];
    for (const route of routes) {
      const html = await (await fetch(route)).text();
      for (const [, path, id] of html.matchAll(/href="(\/[a-z-]*)#([a-z-]+)"/g)) {
        const target = await (await fetch(path === "" ? "/" : path)).text();
        if (!target.includes(`id="${id}"`)) dead.push(`${path}#${id}`);
      }
    }
    return dead;
  }, ROUTES);
  check(
    "no cross-page anchor points at a missing id",
    crossPage.length === 0,
    crossPage.join(", "),
  );

  await page.close();
}

// --- scripted figures: reduced motion renders the last frame, statically ---
{
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
  });
  await page.goto(base, { waitUntil: "networkidle" });

  const figure = page.locator("pre.wn-figure").first();
  await figure.scrollIntoViewIfNeeded();

  const samples = [];
  for (let index = 0; index < 5; index += 1) {
    samples.push((await figure.textContent()) ?? "");
    await page.waitForTimeout(200);
  }
  check(
    "reduced motion never animates a figure",
    new Set(samples).size === 1,
    `${new Set(samples).size} distinct frames`,
  );

  const anyTransparent = await page.evaluate(() =>
    [...document.querySelectorAll("pre.wn-figure > span")].some(
      (element) => getComputedStyle(element).opacity !== "1",
    ),
  );
  check("reduced motion shows every figure row", anyTransparent === false);

  await page.close();
}

// --- scripted figures do not move the layout when they start --------------
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(base, { waitUntil: "networkidle" });

  const figure = page.locator("pre.wn-figure").first();
  await figure.scrollIntoViewIfNeeded();
  const before = await figure.boundingBox();
  await page.waitForTimeout(2400);
  const after = await figure.boundingBox();

  check(
    "a figure keeps its box for the whole script",
    Boolean(before && after) &&
      Math.abs((before?.width ?? 0) - (after?.width ?? 0)) < 1 &&
      Math.abs((before?.height ?? 0) - (after?.height ?? 0)) < 1,
    `${before?.width}x${before?.height} -> ${after?.width}x${after?.height}`,
  );

  await page.close();
}

// --- the social card renders ----------------------------------------------
{
  const response = await fetch(`${base}/opengraph-image`);
  const body = response.ok ? Buffer.from(await response.arrayBuffer()) : null;
  check(
    "opengraph-image renders a png",
    response.ok && body?.subarray(1, 4).toString() === "PNG",
    `${response.status}, ${body?.length ?? 0} bytes`,
  );
}

await browser.close();

const failed = results.filter((result) => !result.passed);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length === 0 ? 0 : 1);
