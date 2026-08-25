import { Ticks } from "@/components/Ticks";

/**
 * A real table, for the one set of real numbers on this site that is shaped
 * like one.
 *
 * It is not an `AsciiFigure`, and the distinction is the whole reason this
 * component exists. docs/design-language.md §8 rule 13 makes every figure an
 * illustration drawn from a fixed script and hides its drawing from screen
 * readers; these are measurements out of `README.md`, and a measurement a screen
 * reader cannot read is not a measurement it has been told. So: a `<table>` with
 * a real `<caption>`, set below the rows, and character rules rather than
 * borders — §3 bans the `1px solid` that would otherwise draw them, and a
 * `border-b` on a row is the exception it names, being a rule the table's own
 * grid already implies.
 *
 * The caption is where the source goes. A number on this site without the
 * document it came from is a number the site invented.
 */

export type ComparisonRow = {
  label: string;
  /** One per column head, in order. */
  cells: readonly string[];
  /** Draws this row's numbers in the accent. At most one row should set it. */
  emphasis?: boolean;
};

export function ComparisonTable({
  caption,
  columns,
  rowHeader,
  rows,
  className = "",
}: {
  /** Rendered below the table, and the only place the source is named. */
  caption: string;
  columns: readonly string[];
  /** Names the row-label column for a screen reader; the head stays blank. */
  rowHeader: string;
  rows: readonly ComparisonRow[];
  className?: string;
}) {
  return (
    <table className={`text-small w-full caption-bottom border-collapse ${className}`}>
      <caption className="wn-measure text-micro text-fg-muted mt-4 text-left">
        <Ticks>{caption}</Ticks>
      </caption>
      <thead>
        <tr>
          <th scope="col" className="text-fg-muted py-2 pr-[2ch] text-left font-medium">
            <span className="sr-only">{rowHeader}</span>
          </th>
          {columns.map((column) => (
            <th
              key={column}
              scope="col"
              className="text-fg-muted py-2 pl-[2ch] text-right font-medium"
            >
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label}>
            <th
              scope="row"
              className="text-fg border-line border-t py-3 pr-[2ch] text-left font-medium"
            >
              <Ticks>{row.label}</Ticks>
            </th>
            {row.cells.map((cell, index) => (
              <td
                // Cells are positional and a column is never inserted, so the
                // index is the stable identity here.
                key={index}
                className={`border-line border-t py-3 pl-[2ch] text-right tabular-nums ${
                  row.emphasis ? "text-accent" : "text-fg-muted"
                }`}
              >
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
