import type { ReactNode } from "react";

/**
 * A panel whose frame is made of box-drawing characters rather than a CSS
 * border, with an optional label welded into the top edge:
 *
 *     ┌─ label ──────────────────┐
 *     │  …                       │
 *     └──────────────────────────┘
 *
 * Both fills are deliberately overlong strings clipped by `overflow: hidden`,
 * so the frame lands on whole characters at any width. The vertical edges are
 * taken out of flow — clipping hides the overhang but would not stop 200 rows
 * of `│` from setting the panel's height.
 */

const H_FILL = "─".repeat(400);
const V_FILL = Array.from({ length: 200 }, () => "│").join("\n");

type AsciiPanelProps = {
  /** One or two words. A long label pushes the frame off a narrow screen. */
  label?: string;
  tone?: "faint" | "accent";
  children: ReactNode;
  className?: string;
};

const TONE_CLASS = {
  faint: "text-fg-faint",
  accent: "text-accent",
} as const;

export function AsciiPanel({
  label,
  tone = "faint",
  children,
  className = "",
}: AsciiPanelProps) {
  const frame = TONE_CLASS[tone];
  const edge = `pointer-events-none absolute inset-y-0 select-none overflow-hidden whitespace-pre leading-none ${frame}`;

  return (
    <div className={`wn-panel text-small ${className}`}>
      <div
        aria-hidden="true"
        className={`flex items-baseline select-none whitespace-pre leading-none ${frame}`}
      >
        <span className="shrink-0">┌─</span>
        {label ? (
          <span className="text-fg-muted tracking-kicker min-w-0 overflow-hidden uppercase">
            {` ${label} `}
          </span>
        ) : null}
        <span className="min-w-0 flex-1 overflow-hidden">{H_FILL}</span>
        <span className="shrink-0">┐</span>
      </div>

      <div className="relative">
        <div aria-hidden="true" className={`${edge} left-0`}>
          {V_FILL}
        </div>
        <div className="px-[2.5ch] py-3">{children}</div>
        <div aria-hidden="true" className={`${edge} right-0`}>
          {V_FILL}
        </div>
      </div>

      <div
        aria-hidden="true"
        className={`flex select-none whitespace-pre leading-none ${frame}`}
      >
        <span className="shrink-0">└</span>
        <span className="min-w-0 flex-1 overflow-hidden">{H_FILL}</span>
        <span className="shrink-0">┘</span>
      </div>
    </div>
  );
}
