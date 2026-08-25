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

test("reduced motion schedules no work, rather than animating and hiding it", async ({
  browser,
}) => {
  /* §5 asks for more than a still hero: the component reads the media query
     *before* scheduling anything, so no frame is requested and no timer is set.
     A component that requests a frame and then bails honours the preference on
     paper only — it has already paid for a paint.

     Asserted against a control rather than against a number. React and Next
     schedule work of their own on both paths, so "zero" is not the claim and a
     magic threshold would only be this machine's frame rate written down; what
     the decode adds is one frame per tick for 900 ms, which is an order of
     magnitude, not a margin. */
  const count = async (reducedMotion: "reduce" | "no-preference") => {
    const context = await browser.newContext({ reducedMotion });
    const page = await context.newPage();
    await page.addInitScript(() => {
      const scheduled = { frames: 0, timers: 0 };
      (window as { __wnScheduled?: typeof scheduled }).__wnScheduled = scheduled;

      const frame = window.requestAnimationFrame.bind(window);
      window.requestAnimationFrame = (callback) => {
        scheduled.frames += 1;
        return frame(callback);
      };

      const timer = window.setTimeout.bind(window);
      window.setTimeout = ((handler: TimerHandler, delay?: number, ...rest: unknown[]) => {
        scheduled.timers += 1;
        return timer(handler, delay, ...rest);
      }) as typeof window.setTimeout;
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);
    const scheduled = await page.evaluate(
      () =>
        (window as { __wnScheduled?: { frames: number; timers: number } })
          .__wnScheduled ?? { frames: 0, timers: 0 },
    );
    await context.close();
    return scheduled;
  };

  const [still, animating] = await Promise.all([count("reduce"), count("no-preference")]);

  expect(animating.frames, "the control never decoded").toBeGreaterThan(20);
  expect(
    still.frames,
    `reduced motion requested ${still.frames} frames against the control's ${animating.frames}`,
  ).toBeLessThan(animating.frames / 4);
  expect(
    still.timers,
    "reduced motion scheduled more timers than the animating path",
  ).toBeLessThanOrEqual(animating.timers);
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
