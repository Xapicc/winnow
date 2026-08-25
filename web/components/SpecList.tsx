import { AsciiRule } from "@/components/AsciiRule";
import { Ticks } from "@/components/Ticks";

/**
 * A term and what it means, for the reference pages.
 *
 * Two columns where there is room and stacked where there is not, separated by
 * the same character rule the rest of the site uses — a `<dl>` with a border
 * would be the first `1px solid` on the site, and docs/design-language.md §3
 * does not allow one.
 *
 * The divider sits inside the `<dt>`, absolutely positioned across the row,
 * for a reason that is not a style choice: a `<dl>` may contain `<dt>`/`<dd>`
 * pairs or one `<div>` per pair and nothing else, so neither a rule between the
 * groups nor a second `<div>` around each one is allowed. The first draft had
 * both, and axe reported `definition-list` and `dlitem` as serious on every
 * page that used this component — 44 nodes across `/filter` and `/status`.
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
        <div
          key={item.term}
          /* pt-9 rather than pt-3 on every row but the first: the rule's own
             line box is 24px and it is out of flow, so the row has to leave
             that height itself or the terms close up. */
          className={`relative grid gap-x-[2ch] gap-y-1 pb-3 sm:grid-cols-[24ch_minmax(0,1fr)] ${
            index > 0 ? "pt-9" : "pt-3"
          }`}
        >
          <dt className="text-small text-fg">
            {index > 0 ? <AsciiRule className="absolute inset-x-0 top-0" /> : null}
            <Ticks>{item.term}</Ticks>
          </dt>
          <dd className="text-small text-fg-muted max-w-[68ch]">
            <Ticks>{item.detail}</Ticks>
          </dd>
        </div>
      ))}
    </dl>
  );
}
