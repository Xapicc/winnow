import type { CSSProperties } from "react";

import type { AsciiArt } from "@/lib/ascii";

/**
 * Renders character art at whatever size fits its container. The column count
 * goes in as a CSS variable and `.wn-ascii` divides the container width by
 * `cols × 0.6em` — see docs/design-language.md §4.
 *
 * Always `aria-hidden`: the accessible name is carried by a real heading beside
 * the art, never by the block characters.
 */

type AsciiProps = {
  art: AsciiArt;
  /** Upper bound on the computed font size, in px. */
  cap?: number;
  className?: string;
  style?: CSSProperties;
};

export function Ascii({ art, cap = 32, className = "", style }: AsciiProps) {
  return (
    <pre
      aria-hidden="true"
      className={`wn-ascii ${className}`}
      style={
        {
          "--ascii-cols": art.cols,
          "--ascii-cap": `${cap}px`,
          ...style,
        } as CSSProperties
      }
    >
      {art.rows.join("\n")}
    </pre>
  );
}
