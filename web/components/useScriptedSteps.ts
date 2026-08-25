"use client";

import { useLayoutEffect, useRef, useState } from "react";

import { prefersReducedMotion } from "@/lib/motion";

/**
 * Plays a figure through a fixed number of frames, once.
 *
 * Three rules from docs/design-language.md §5, all of them enforced here rather
 * than in each figure:
 *
 *   - The last frame is the initial state, so the server, a client without
 *     JavaScript, and a reader who asked for reduced motion all get the finished
 *     figure. The rewind to frame 0 happens in a layout effect, before paint, so
 *     there is no flash and no layout shift.
 *   - Under `prefers-reduced-motion: reduce` no timer is ever scheduled and no
 *     observer is ever attached — the animation path is not entered at all.
 *   - Nothing plays off screen. An IntersectionObserver starts the run when the
 *     figure is in view and pauses it when it leaves.
 *
 * The run stops for good at the last frame: nothing on this site loops.
 */
export function useScriptedSteps(stepCount: number, stepMs: number) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [step, setStep] = useState(stepCount - 1);

  useLayoutEffect(() => {
    if (prefersReducedMotion()) return;

    const node = containerRef.current;
    if (!node) return;

    setStep(0);

    let current = 0;
    let timer: number | null = null;

    const advance = () => {
      timer = null;
      if (current >= stepCount - 1) return;
      current += 1;
      setStep(current);
      if (current < stepCount - 1) timer = window.setTimeout(advance, stepMs);
    };

    const observer = new IntersectionObserver(
      (entries) => {
        const onScreen = entries.some((entry) => entry.isIntersecting);
        if (onScreen) {
          if (timer === null && current < stepCount - 1) {
            timer = window.setTimeout(advance, stepMs);
          }
          return;
        }
        if (timer !== null) {
          window.clearTimeout(timer);
          timer = null;
        }
      },
      { threshold: 0.4 },
    );

    observer.observe(node);

    return () => {
      observer.disconnect();
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [stepCount, stepMs]);

  return { containerRef, step };
}
