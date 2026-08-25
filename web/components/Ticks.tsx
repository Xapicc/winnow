import { Fragment, type ReactNode } from "react";

/**
 * Renders the two marks the copy is written with: `backtick` spans as code, and
 * `*starred*` spans as emphasis.
 *
 * The whole site is monospace, so a code span cannot be marked by family. It is
 * marked by colour instead: paths, flags, commands and the terms of the cache
 * arithmetic take the accent, which is the one place in body copy where the
 * accent is allowed to appear.
 *
 * Emphasis is marked by weight and tone rather than by slope. docs/design-
 * language.md §2 ships no italic face, so an `<em>` left to the browser would be
 * a synthesised oblique; this one is upright, a step brighter and a step
 * heavier. The mark exists at all because the copy is lifted from documents
 * written in markdown, and an unhandled `*word*` renders as two pieces of
 * punctuation that look like markdown nobody compiled.
 *
 * Stars are resolved inside the plain segments only, so a star inside a code
 * span — a glob, a memory path with a wildcard directory in it — stays literal.
 * Only single stars are a mark: a `**double**` leaves a visible stray star
 * rather than a silent one, which is the failure worth having in copy that
 * lives in a file nobody previews.
 */

type TicksProps = {
  children: string;
};

/** `*starred*` spans inside one run of plain text. */
function emphasise(text: string): ReactNode[] {
  return text
    .split("*")
    .map((segment, index) =>
      index % 2 === 1 ? (
        <em key={`${index}-${segment}`} className="text-fg font-medium not-italic">
          {segment}
        </em>
      ) : (
        <Fragment key={`${index}-${segment}`}>{segment}</Fragment>
      ),
    );
}

export function Ticks({ children }: TicksProps) {
  const segments = children.split("`");

  return (
    <>
      {segments.map((segment, index) =>
        index % 2 === 1 ? (
          <code key={`${index}-${segment}`} className="text-accent">
            {segment}
          </code>
        ) : (
          <Fragment key={`${index}-${segment}`}>{emphasise(segment)}</Fragment>
        ),
      )}
    </>
  );
}
