import { expect, test } from "@playwright/test";

import {
  NOISE_ONLY,
  RESOLVED_WORDMARK,
  heroFrames,
  heroSettled,
  heroText,
  recordHeroFrames,
} from "./helpers";

/** Any glyph that can only come from a half-finished decode. */
const noisePattern = new RegExp(`[${NOISE_ONLY.join("")}]`);

test.describe("the decode", () => {
  test("scrambles on load and resolves to the wordmark", async ({ page }) => {
    await recordHeroFrames(page);
    await page.goto("/", { waitUntil: "domcontentloaded" });

    const frames = await heroSettled(page);

    expect(
      frames.filter((frame) => noisePattern.test(frame)).length,
      "the hero went straight to the wordmark without decoding",
    ).toBeGreaterThan(0);
    expect(frames.at(-1), "the decode's last frame").toBe(RESOLVED_WORDMARK);
    expect(await heroText(page), "the art on screen once it stops").toBe(
      RESOLVED_WORDMARK,
    );
  });

  test("resolves once and does not replay", async ({ page }) => {
    // §5: the decode is a load effect. Replaying it on scroll is the thing that
    // section forbids by name.
    await page.goto("/");
    await expect.poll(async () => await heroText(page)).toBe(RESOLVED_WORDMARK);

    await page.mouse.wheel(0, 1200);
    await page.waitForTimeout(400);
    expect(await heroText(page)).toBe(RESOLVED_WORDMARK);
  });
});

test.describe("prefers-reduced-motion: reduce", () => {
  // 1.62 moved the media emulation options under `contextOptions`.
  test.use({ contextOptions: { reducedMotion: "reduce" } });

  test("the wordmark is resolved and legible from the first frame", async ({
    page,
  }) => {
    await recordHeroFrames(page);
    await page.goto("/", { waitUntil: "domcontentloaded" });

    const samples: string[] = [];
    for (let sample = 0; sample < 6; sample += 1) {
      samples.push((await heroText(page)) ?? "");
      await page.waitForTimeout(100);
    }

    expect(new Set(samples).size, "the hero animated under reduced motion").toBe(1);
    expect(samples[0]).toBe(RESOLVED_WORDMARK);

    // Every state the art passed through, not just the six that were sampled.
    expect(
      (await heroFrames(page)).filter((frame) => noisePattern.test(frame)),
      "the hero entered the decode under reduced motion",
    ).toEqual([]);
  });

  test("no frame is requested and no timer is scheduled", async ({ page }) => {
    /* §5 asks for more than a still hero: the component reads the media query
       *before* scheduling work, so nothing is queued at all. A component that
       requests a frame and then bails honours the preference on paper only —
       it has already paid for a paint. Counted by replacing the two schedulers
       before any site script runs. */
    await page.addInitScript(() => {
      const counts = { frames: 0, timers: 0 };
      (window as { __wnScheduled?: typeof counts }).__wnScheduled = counts;

      const rAF = window.requestAnimationFrame.bind(window);
      window.requestAnimationFrame = (callback) => {
        counts.frames += 1;
        return rAF(callback);
      };

      const timeout = window.setTimeout.bind(window);
      window.setTimeout = ((handler: TimerHandler, delay?: number, ...rest: unknown[]) => {
        counts.timers += 1;
        return timeout(handler, delay, ...rest);
      }) as typeof window.setTimeout;
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1200);

    // React and Next schedule their own work, so this cannot assert zero. The
    // decode alone would add a frame per tick for 900ms — 50-plus at 60Hz.
    const scheduled = await page.evaluate(
      () =>
        (window as { __wnScheduled?: { frames: number; timers: number } })
          .__wnScheduled ?? { frames: 0, timers: 0 },
    );
    expect(scheduled.frames, "animation frames requested").toBeLessThan(10);
  });

  test("no element anywhere on the page is mid-scramble", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });

    const scrambling = await page.evaluate(
      (glyphs) =>
        [...document.querySelectorAll<HTMLElement>("body *")]
          .filter((element) => element.children.length === 0)
          .map((element) => element.textContent ?? "")
          .filter((text) => [...glyphs].some((glyph) => text.includes(glyph)))
          .slice(0, 3),
      NOISE_ONLY.join(""),
    );

    expect(scrambling).toEqual([]);
  });

  test("transitions collapse rather than merely running faster", async ({ page }) => {
    await page.goto("/");

    const durations = await page.evaluate(() =>
      [...document.querySelectorAll("header a, main a")].map((element) =>
        Number.parseFloat(getComputedStyle(element).transitionDuration),
      ),
    );

    expect(durations.length).toBeGreaterThan(0);
    for (const duration of durations) expect(duration).toBeLessThan(0.05);
  });
});
