import type { Metadata } from "next";

import { AsciiPanel } from "@/components/AsciiPanel";
import { Button } from "@/components/Button";
import { SectionHeading } from "@/components/SectionHeading";
import { Ticks } from "@/components/Ticks";
import { PaybackDemo } from "@/components/demos/PaybackDemo";

export const metadata: Metadata = {
  title: "The arithmetic",
  description:
    "Cache reads bill at 0.1× and writes at 1.25× or 2×, and matching is prefix-ordered. A prune pays 1.9·S − 2·D once and earns 0.1·D back a turn, so it breaks even after 19·(S/D) − 20 further turns.",
  alternates: { canonical: "/arithmetic" },
};

/**
 * The page shell for the cache arithmetic. Every figure on it is the README's
 * or `docs/SPEC.md`'s; a later run adds the worked examples and the figures.
 */
export default function ArithmeticPage() {
  return (
    <div className="wn-shell py-16 sm:py-20">
      <SectionHeading as="h1" kicker="the arithmetic">
        Removing half your conversation does not halve your bill
      </SectionHeading>

      <div className="wn-measure mb-16">
        <p className="text-lead tracking-tight">
          It is not obvious that it lowers it at all.
        </p>
        <p className="text-body text-fg-muted mt-4">
          <Ticks>
            {
              "Cache reads bill at 0.1× and writes at 1.25× (five-minute) or 2× (one hour). Matching is exact and prefix-ordered, so an edit invalidates everything after the cut point."
            }
          </Ticks>
        </p>
      </div>

      <section className="mb-16">
        <SectionHeading id="formula" kicker="break-even">
          What a cut costs and what it earns
        </SectionHeading>

        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-[6ch]">
          <div className="wn-measure">
            <p className="text-body text-fg-muted">
              <Ticks>
                {
                  "Let `S` be the suffix after the cut and `D` the bytes removed from it. The edit pays `1.9·S − 2·D` once, and earns `0.1·D` back on every later turn. Neither term is a rate you can shop for: both fall out of how the API prices a cached prefix."
                }
              </Ticks>
            </p>
            <p className="text-body text-fg-muted mt-4">
              <Ticks>
                {
                  "Cut half the suffix and it pays for itself in 18 turns. Cut a tenth and it needs 170 more turns than the session has had — and in the corpus that was measured, only 807 turns out of 11,422 sat past index 160 at all."
                }
              </Ticks>
            </p>
            <p className="text-body text-fg-muted mt-4">
              <Ticks>
                {
                  "The formula is model-independent and absolute size cancels. `S/D` decides, not the size of the session: a big session is not automatically worth pruning."
                }
              </Ticks>
            </p>
          </div>

          <AsciiPanel label="break-even" tone="accent">
            <p className="text-lead text-accent tracking-tight">
              T* = 19·(S/D) − 20
            </p>
            <p className="text-fg-muted mt-3">
              further turns, before the cut has paid for itself.
            </p>
            <p className="text-fg-muted mt-3">
              <Ticks>
                {
                  "The 2.0× is not the list-price assumption. It is a measurement over 26,194 turns of one install where every main-thread turn wrote at the one-hour class, and it is recorded outside this repository."
                }
              </Ticks>
            </p>
          </AsciiPanel>
        </div>

        <div className="mt-12">
          <PaybackDemo />
        </div>
      </section>

      <section className="mb-16">
        <SectionHeading id="no-break-even" kicker="the intake filter">
          The one position that pays nothing
        </SectionHeading>

        <div className="wn-measure">
          <p className="text-body text-fg-muted">
            <Ticks>
              {
                "The pruner edits a conversation that is already cached, so it pays `1.9·S − 2·D` once. The only way not to pay that is to never let the bytes into the cached prefix."
              }
            </Ticks>
          </p>
          <p className="text-body text-fg-muted mt-4">
            <Ticks>
              {
                "Per result of `D` tokens over `T` following turns, the baseline is a 2.0× cache write plus a 0.1× read on every later turn. The filter pays 1.0× once and nothing after. There is no break-even term — it is cheaper from the first request, at every `S/D`, which is the one thing the pruner cannot say."
              }
            </Ticks>
          </p>
          <p className="text-small text-fg-muted mt-4">
            <Ticks>
              {
                "It reaches less, because only the rules needing no hindsight can fire — C1, C3 and B2. C2, B1 and A1 all need to see the conversation's future, and a policy that did would change the prefix under the cache."
              }
            </Ticks>
          </p>
          <div className="mt-6">
            <Button href="/filter#position" variant="ghost">
              what the filter does today
            </Button>
          </div>
        </div>
      </section>

      <section className="mb-16">
        <SectionHeading id="free-moment" kicker="position">
          There is exactly one moment when the edit is free
        </SectionHeading>

        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-[6ch]">
          <div className="wn-measure">
            <p className="text-body text-fg-muted">
              <Ticks>
                {
                  "Immediately before a handover that was going to rewrite the suffix anyway, the `2·D` term is refunded. winnow acts at resume boundaries for this reason, not out of caution."
                }
              </Ticks>
            </p>
            <p className="text-body text-fg-muted mt-4">
              <Ticks>
                {
                  "That is also why the deliverable is a comparison rather than a saving. Every existing tool reports bytes or tokens removed; none reports the netted cost, and none has ever been measured against task quality."
                }
              </Ticks>
            </p>
          </div>

          <AsciiPanel label="on the record">
            <p className="text-fg-muted">
              <Ticks>
                {
                  "This arithmetic was got wrong here once, by assuming the 1.25× multiplier from the documentation instead of reading the measurement. That version understated invalidation by about 40 percent, and section 3.1 of `docs/COZEMPIC.md` keeps the error on the record — it is exactly the mistake the measurement exists to catch."
                }
              </Ticks>
            </p>
          </AsciiPanel>
        </div>
      </section>

      <div className="wn-measure flex flex-wrap items-center gap-[3ch]">
        <Button href="/filter">the intake filter</Button>
        <Button href="/status" variant="ghost">
          what runs today
        </Button>
      </div>
    </div>
  );
}
