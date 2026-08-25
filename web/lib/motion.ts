/**
 * The site's motion layer. Everything that moves goes through here.
 *
 * Timings are not declared in this file — they are read out of the `--motion-*`
 * custom properties in `app/globals.css`, so the CSS is the single source of
 * truth for duration and the one JavaScript effect cannot drift from it. See
 * docs/design-language.md §5.
 */

import { useLayoutEffect, useState, type RefObject } from "react";

import { type AsciiArt } from "@/lib/ascii";
import { decodeFrame, settleFractions } from "@/lib/decode";

/**
 * The reduced-motion test, in one place because every animated component has to
 * ask it the same way: *before* scheduling anything, not inside the callback.
 *
 * A component that requests a frame and then bails honours the preference on
 * paper only — it has already paid for a paint.
 */
export function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function motionToken(name: string): string {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  if (!value) {
    throw new Error(
      `Motion token ${name} is not declared on :root. Declare it in app/globals.css.`,
    );
  }
  return value;
}

/** A `--motion-*` token that is a CSS time, in milliseconds. */
function motionMs(name: string): number {
  const raw = motionToken(name);
  const scale = raw.endsWith("ms") ? 1 : raw.endsWith("s") ? 1000 : Number.NaN;
  const value = Number.parseFloat(raw) * scale;
  if (!Number.isFinite(value)) {
    throw new Error(`Motion token ${name} is "${raw}", which is not a CSS time.`);
  }
  return value;
}

/** A `--motion-*` token that is a bare number. */
function motionNumber(name: string): number {
  const raw = motionToken(name);
  const value = Number.parseFloat(raw);
  if (!Number.isFinite(value)) {
    throw new Error(`Motion token ${name} is "${raw}", which is not a number.`);
  }
  return value;
}

/**
 * The one character-decode effect: `art` resolves out of noise, once, on load.
 *
 * Returns the text to render. The first value is the *resolved* art, so the
 * server markup is correct without JavaScript; the scramble is installed in a
 * layout effect before the browser paints, so there is no flash of
 * resolved-then-broken text.
 *
 * Three ways it declines to animate, all of them checked before a frame is
 * ever requested:
 *
 * - `prefers-reduced-motion: reduce` — never enters the animation path.
 * - The art is outside the viewport at load (a deep link to an anchor further
 *   down the page). It stays resolved; it does not decode later when scrolled
 *   to, because the decode is a load effect and replaying it on scroll is the
 *   thing §5 forbids.
 * - It leaves the viewport, or the tab is hidden, mid-run. The frame loop stops
 *   and the art settles resolved — nothing animates where nobody is looking.
 *
 * The frame itself is `decodeFrame` in lib/decode.ts, which is pure and is
 * therefore checkable without a browser. This function owns the clock, the
 * viewport test and the teardown, and nothing else.
 */
export function useDecodedText(
  ref: RefObject<Element | null>,
  art: AsciiArt,
): string {
  const resolved = art.rows.join("\n");
  const [text, setText] = useState(resolved);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || prefersReducedMotion()) return;

    // Synchronous, pre-paint equivalent of "is it in view". An
    // IntersectionObserver cannot answer this before the first paint, and
    // starting the scramble after it would be the flash the contract forbids.
    const box = element.getBoundingClientRect();
    const onScreen =
      box.bottom > 0 &&
      box.top < window.innerHeight &&
      box.right > 0 &&
      box.left < window.innerWidth;
    if (!onScreen) return;

    const duration = motionMs("--motion-decode");
    const churnMs = motionMs("--motion-decode-churn");
    const stagger = motionNumber("--motion-decode-stagger");
    const fractions = settleFractions(art, stagger);
    const start = performance.now();

    let frame: number | null = null;
    let lastChurn = 0;
    let churnSeed = 0;

    const settle = () => {
      if (frame !== null) cancelAnimationFrame(frame);
      frame = null;
      setText(resolved);
    };

    const draw = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(1, elapsed / duration);

      if (progress >= 1) {
        settle();
        return;
      }

      // Only re-pick noise glyphs on a slower clock; cells still settle on
      // every frame, so the resolve stays smooth while the noise stays legible.
      if (elapsed - lastChurn >= churnMs) {
        lastChurn = elapsed;
        churnSeed += 1;
      }

      setText(decodeFrame(art, fractions, progress, churnSeed, stagger));
      frame = requestAnimationFrame(draw);
    };

    frame = requestAnimationFrame(draw);

    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => !entry.isIntersecting)) settle();
    });
    observer.observe(element);

    const onHidden = () => {
      if (document.hidden) settle();
    };
    document.addEventListener("visibilitychange", onHidden);

    return () => {
      if (frame !== null) cancelAnimationFrame(frame);
      observer.disconnect();
      document.removeEventListener("visibilitychange", onHidden);
    };
  }, [art, ref, resolved]);

  return text;
}
