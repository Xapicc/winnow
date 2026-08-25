import { Fragment } from "react";

/**
 * Renders `backtick`-delimited spans in a plain string as code.
 *
 * The whole site is monospace, so a code span cannot be marked by family. It is
 * marked by colour instead: paths, flags, commands and the terms of the cache
 * arithmetic take the accent, which is the one place in body copy where the
 * accent is allowed to appear.
 */

type TicksProps = {
  children: string;
};

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
          <Fragment key={`${index}-${segment}`}>{segment}</Fragment>
        ),
      )}
    </>
  );
}
