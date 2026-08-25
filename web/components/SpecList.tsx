import { AsciiRule } from "@/components/AsciiRule";
import { Ticks } from "@/components/Ticks";

/**
 * A term and what it means, for the reference pages.
 *
 * Two columns where there is room and stacked where there is not, separated by
 * the same character rule the rest of the site uses — a `<dl>` with a border
 * would be the first `1px solid` on the site, and docs/design-language.md §3
 * does not allow one.
 */

type SpecItem = {
  term: string;
  /** Backtick spans become code, as everywhere else. */
  detail: string;
};

export function SpecList({
  items,
  className = "",
}: {
  items: readonly SpecItem[];
  className?: string;
}) {
  return (
    <dl className={className}>
      {items.map((item, index) => (
        <div key={item.term}>
          {index > 0 ? <AsciiRule /> : null}
          <div className="grid gap-x-[2ch] gap-y-1 py-3 sm:grid-cols-[24ch_minmax(0,1fr)]">
            <dt className="text-small text-fg">
              <Ticks>{item.term}</Ticks>
            </dt>
            <dd className="text-small text-fg-muted max-w-[68ch]">
              <Ticks>{item.detail}</Ticks>
            </dd>
          </div>
        </div>
      ))}
    </dl>
  );
}
