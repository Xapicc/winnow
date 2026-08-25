import type { Page } from "@playwright/test";

import { SCRAMBLE_GLYPHS, WORDMARK } from "../lib/ascii";
import { ROUTES } from "../lib/site";

/** Every route the site serves. */
export const PAGES = [...ROUTES];

/** A path that is deliberately not a route, for the 404 checks. */
export const MISSING_PATH = "/no-such-page-4d1f";

/** The widths docs/design-language.md §3 has to hold at. */
export const WIDTHS = [320, 390, 768, 1024, 1440, 1920] as const;

export const DESKTOP = { width: 1440, height: 900 } as const;
export const MOBILE = { width: 390, height: 844 } as const;

export const RESOLVED_WORDMARK = WORDMARK.rows.join("\n");

/**
 * Scramble glyphs that can only be noise, and the exclusions matter more here
 * than on the reference site:
 *
 * - the ASCII ones (`#`, `*`, `-`, `=`, …) appear in ordinary copy;
 * - `█` is what the finished art is made of;
 * - `░` and `▓` are the fill and the remainder of the bars in
 *   `components/demos/`, so they are on the page at rest.
 *
 * What is left is `▒ ▚ ▞`, and a noise frame always contains all three: the
 * pick is `(cell · 31 + seed · 17) mod 12`, 31 and 12 are coprime, so the
 * alphabet is walked in full across any dozen unsettled cells. `lib/decode.test.ts`
 * asserts that, because this file depends on it.
 */
const DRAWN_AT_REST = new Set(["█", "░", "▓"]);

export const NOISE_ONLY = [...SCRAMBLE_GLYPHS].filter(
  (glyph) => !DRAWN_AT_REST.has(glyph) && (glyph.codePointAt(0) ?? 0) > 127,
);

export type PageProblems = {
  consoleErrors: string[];
  failedRequests: string[];
};

/**
 * Starts collecting console errors and failed or error-status responses before
 * the first navigation. Every page-level listener has to be attached before
 * `goto`, or the first paint's problems are missed.
 */
export function watchForProblems(page: Page): PageProblems {
  const problems: PageProblems = { consoleErrors: [], failedRequests: [] };

  page.on("console", (message) => {
    if (message.type() !== "error") return;
    // Chromium logs "failed to load resource: 404" against the 404 document
    // itself. That navigation is the thing under test and its status is
    // asserted directly; anything else the page logs still counts.
    if (message.location().url.includes(MISSING_PATH)) return;
    problems.consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => {
    problems.consoleErrors.push(`uncaught: ${error.message}`);
  });
  page.on("requestfailed", (request) => {
    problems.failedRequests.push(
      `${request.url()} — ${request.failure()?.errorText ?? "failed"}`,
    );
  });
  page.on("response", (response) => {
    // The 404 route is requested on purpose; a sub-resource 404 is not.
    if (response.status() >= 400 && !response.url().includes(MISSING_PATH)) {
      problems.failedRequests.push(`${response.url()} — HTTP ${response.status()}`);
    }
  });

  return problems;
}

/**
 * The hero art as it currently stands on screen. Scoped to `main` — the header
 * and footer carry the small mark, which is the same kind of block.
 */
export function heroText(page: Page) {
  return page.locator("main pre.wn-ascii").first().textContent();
}

type FrameWindow = { __wnHeroFrames?: string[]; __wnHeroFrameAt?: number };

/**
 * Records every distinct state the hero art passes through. Sampling from the
 * test side after `goto` is a race the test loses on a fast machine — the whole
 * decode is 900 ms and the first round trip can land after it — so the frames
 * are collected in-page by an observer installed before any site script runs.
 * Call before `goto`.
 */
export async function recordHeroFrames(page: Page) {
  await page.addInitScript(() => {
    const frames: string[] = [];
    (window as FrameWindow).__wnHeroFrames = frames;

    const record = () => {
      const art = document.querySelector("main pre.wn-ascii");
      if (!art) return;
      const text = art.textContent ?? "";
      if (text === frames.at(-1)) return;
      frames.push(text);
      (window as FrameWindow).__wnHeroFrameAt = performance.now();
    };

    new MutationObserver(record).observe(document, {
      subtree: true,
      childList: true,
      characterData: true,
    });
  });
}

export function heroFrames(page: Page): Promise<string[]> {
  return page.evaluate(() => (window as FrameWindow).__wnHeroFrames ?? []);
}

/**
 * The frames so far, and how long the art has been still. A mid-decode frame
 * can be identical to the finished wordmark by chance — the scramble alphabet
 * contains `█`, which is what the art is made of — so "the text matches" is not
 * the same question as "the decode is over". Poll on `quietFor` for the second.
 */
export function heroFrameStatus(
  page: Page,
): Promise<{ frames: string[]; quietFor: number }> {
  return page.evaluate(() => {
    const state = window as FrameWindow;
    return {
      frames: state.__wnHeroFrames ?? [],
      quietFor: performance.now() - (state.__wnHeroFrameAt ?? 0),
    };
  });
}

/** Resolves once the hero has been unchanged for `quietMs`. */
export async function heroSettled(page: Page, quietMs = 300): Promise<string[]> {
  const deadline = 15_000;
  const startedAt = Date.now();

  for (;;) {
    const { frames, quietFor } = await heroFrameStatus(page);
    if (frames.length > 0 && quietFor >= quietMs) return frames;
    if (Date.now() - startedAt > deadline) {
      throw new Error(
        `the hero was still changing after ${deadline}ms (${frames.length} frames)`,
      );
    }
    await page.waitForTimeout(100);
  }
}
