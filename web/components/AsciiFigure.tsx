import type { ReactNode, Ref } from "react";
import type { CSSProperties } from "react";

import { Ascii } from "@/components/Ascii";
import type { AsciiArt } from "@/lib/ascii";

/**
 * The two ways a figure gets onto the page.
 *
 * `AsciiFigure` draws a fixed diagram; `ScriptedFigure` draws rows that carry a
 * state colour and can be revealed a frame at a time. Both put the drawing in an
 * `aria-hidden` <pre> and the meaning in a real caption, because a screen reader
 * reading box-drawing characters aloud gets nothing — docs/design-language.md §4.
 *
 * `alt` is the description a screen reader hears; `children` is the caption
 * everyone sees. Neither may say the figure is live: every one of them is an
 * illustration drawn from a fixed script, and on this site several of them
 * illustrate software that does not exist yet. §8.
 */

type FigureShellProps = {
  alt: string;
  children: ReactNode;
  className?: string;
  drawing: ReactNode;
  innerRef?: Ref<HTMLDivElement>;
};

function FigureShell({
  alt,
  children,
  className = "",
  drawing,
  innerRef,
}: FigureShellProps) {
  return (
    <figure className={className}>
      <div ref={innerRef} className="wn-ascii-fit flex justify-center">
        {drawing}
      </div>
      <figcaption className="wn-measure mt-4 text-micro text-fg-muted">
        <span className="sr-only">{alt} </span>
        {children}
      </figcaption>
    </figure>
  );
}

export function AsciiFigure({
  art,
  alt,
  cap = 15,
  className,
  children,
}: {
  art: AsciiArt;
  alt: string;
  cap?: number;
  className?: string;
  children: ReactNode;
}) {
  return (
    <FigureShell
      alt={alt}
      className={className}
      drawing={<Ascii art={art} cap={cap} className="text-fg-muted" />}
    >
      {children}
    </FigureShell>
  );
}

/**
 * No `warn`. There is no `--color-warn` on this site: an amber status against
 * an orange brand is the brand. An indeterminate row is `muted` plus a `╱`
 * hatch in the art itself — docs/design-language.md §1.
 */
export type FigureTone =
  | "fg"
  | "muted"
  | "faint"
  | "accent"
  | "ok"
  | "danger";

export type FigureCell = { text: string; tone?: FigureTone };

export type FigureRow = {
  cells: readonly FigureCell[];
  /** Not yet reached in the script. Kept in the DOM at full height, so nothing moves. */
  hidden?: boolean;
};

const TONE_CLASS: Record<FigureTone, string> = {
  fg: "text-fg",
  muted: "text-fg-muted",
  faint: "text-fg-faint",
  accent: "text-accent",
  ok: "text-ok",
  danger: "text-danger",
};

export function rowWidth(cells: readonly FigureCell[]): number {
  return cells.reduce((width, cell) => width + cell.text.length, 0);
}

export function ScriptedFigure({
  rows,
  cols,
  alt,
  cap = 15,
  className,
  containerRef,
  children,
}: {
  rows: readonly FigureRow[];
  /**
   * Widest row across every frame of the script, not just this one. Sizing from
   * the current frame would resize the type as the figure plays.
   */
  cols: number;
  alt: string;
  cap?: number;
  className?: string;
  containerRef?: Ref<HTMLDivElement>;
  children: ReactNode;
}) {
  return (
    <FigureShell
      alt={alt}
      className={className}
      innerRef={containerRef}
      drawing={
        <pre
          aria-hidden="true"
          className="wn-figure"
          style={
            {
              "--figure-cols": cols,
              "--figure-cap": `${cap}px`,
            } as CSSProperties
          }
        >
          {rows.map((row, rowIndex) => (
            <span
              // Row order is fixed by the script; a row is never inserted or moved.
              key={rowIndex}
              className={row.hidden ? "opacity-0" : undefined}
            >
              {row.cells.map((cell, cellIndex) => (
                <span key={cellIndex} className={TONE_CLASS[cell.tone ?? "muted"]}>
                  {cell.text}
                </span>
              ))}
            </span>
          ))}
        </pre>
      }
    >
      {children}
    </FigureShell>
  );
}
