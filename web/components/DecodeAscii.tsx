"use client";

import { useRef, type CSSProperties } from "react";

import type { AsciiArt } from "@/lib/ascii";
import { useDecodedText } from "@/lib/motion";

/**
 * The one hero effect: the wordmark resolves out of noise, once, on load.
 *
 * This is the site's only client component. All of the behaviour — the timing,
 * the reduced-motion path and the off-screen settle — lives in `useDecodedText`
 * in lib/motion.ts; this file is the `<pre>` and nothing else.
 */

type DecodeAsciiProps = {
  art: AsciiArt;
  /** Upper bound on the computed font size, in px. */
  cap?: number;
  className?: string;
};

export function DecodeAscii({ art, cap = 32, className = "" }: DecodeAsciiProps) {
  const ref = useRef<HTMLPreElement>(null);
  const text = useDecodedText(ref, art);

  return (
    <pre
      ref={ref}
      aria-hidden="true"
      className={`wn-ascii ${className}`}
      style={
        {
          "--ascii-cols": art.cols,
          "--ascii-cap": `${cap}px`,
        } as CSSProperties
      }
    >
      {text}
    </pre>
  );
}
