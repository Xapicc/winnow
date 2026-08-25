import type { ReactNode } from "react";

import { AsciiRule } from "@/components/AsciiRule";

/**
 * Kicker, heading, and a `═` rule that takes the width the heading does not.
 * The rule is the section boundary; it is heavier than anything drawn inside a
 * panel, which is how the eye tells the two apart.
 */

type SectionHeadingProps = {
  /** Anchor target, so a link from elsewhere on the site lands on the section. */
  id?: string;
  kicker?: string;
  children: ReactNode;
  /** `h1` is the page title on a subpage; the home page carries its own. */
  as?: "h1" | "h2" | "h3";
};

export function SectionHeading({
  id,
  kicker,
  children,
  as = "h2",
}: SectionHeadingProps) {
  const Heading = as;
  const size = as === "h3" ? "text-h3 tracking-grid" : "text-h2 tracking-tight";

  return (
    <div className="mb-8">
      {kicker ? <p className="wn-kicker mb-2">{kicker}</p> : null}
      <div className="flex items-baseline gap-[2ch]">
        <Heading id={id} className={`${size} font-semibold scroll-mt-24`}>
          {children}
        </Heading>
        <AsciiRule weight="heavy" tone="line" className="flex-1" />
      </div>
    </div>
  );
}
