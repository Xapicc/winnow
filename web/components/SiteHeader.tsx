import { Ascii } from "@/components/Ascii";
import { AsciiRule } from "@/components/AsciiRule";
import { MARK_SMALL } from "@/lib/ascii";
import { NAV_LINKS, REPO_URL } from "@/lib/site";

/**
 * Four items and the brand, and still no mobile disclosure menu.
 *
 * docs/design-language.md §7 said a fourth item was the moment to revisit the
 * hamburger. The fourth arrived — `/filter` — and the answer is still no: `source`
 * was already dropped below `640px`, so a phone carries three links, and three
 * one-word labels fit a 320px row measured in a browser. What the fourth item
 * did cost is the article: "the arithmetic" and "the filter" became "arithmetic"
 * and "filter", and the row's gap tightens below `sm`.
 *
 * A hamburger would still hide two links behind a control, cost a focus trap and
 * an Escape handler, and buy nothing. A fifth item is a different conversation.
 */
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 bg-canvas/92 backdrop-blur-[2px]">
      <div className="wn-shell flex h-14 items-center justify-between gap-[1.5ch] sm:gap-[4ch]">
        <a
          href="/"
          className="wn-aberrate flex min-h-6 shrink-0 items-center gap-[1.5ch] text-small font-medium"
        >
          <Ascii art={MARK_SMALL} cap={5} className="text-accent shrink-0" />
          <span className="whitespace-nowrap">winnow</span>
        </a>

        <nav
          aria-label="Primary"
          className="flex items-center gap-[1.5ch] sm:gap-[3ch]"
        >
          {/* min-h-6 is WCAG 2.5.8: a 13px line box is 20px tall, which is under
              the 24px minimum target on touch. */}
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="wn-aberrate wn-state text-small text-fg-muted inline-flex min-h-6 shrink-0 items-center whitespace-nowrap hover:text-fg"
            >
              {link.label}
            </a>
          ))}
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer noopener"
            /* Hidden on phones, where the row cannot hold four items. The same
               link is in the hero and in the footer. */
            className="wn-aberrate wn-state text-small text-fg-muted hidden min-h-6 shrink-0 items-center whitespace-nowrap hover:text-accent sm:inline-flex"
          >
            source<span aria-hidden="true"> ↗</span>
          </a>
        </nav>
      </div>
      <AsciiRule tone="line" />
    </header>
  );
}
