/**
 * The break-even formula, as a function the figures can draw.
 *
 * Ported from `Xapicc/UsageFoundryWeb:lib/payback.ts`, where it was written
 * against these same documents. What changed on the way across is where the
 * constants are sourced from: on that site they were the orchestrator's own
 * `src/lib/pricing.ts`, and here they are `README.md`'s "The question", which is
 * where that file got them.
 *
 * A conversation sits in the API's cached prefix, where a read bills at a tenth
 * of the input rate. Matching is exact and prefix-ordered, so an edit to the
 * transcript invalidates everything after the cut point and forces a full-price
 * rewrite of it. That is why removing half a conversation does not halve the
 * bill, and why it is not obvious that it lowers it at all.
 *
 * With `S` the suffix as it stood before the cut and `D` what came out of it,
 * the edit pays `1.9·S − 2·D` once and earns `0.1·D` back on every later turn,
 * so it breaks even after `19·(S/D) − 20` further turns. The ratio decides, not
 * the size of the session.
 *
 * The two multipliers below are the whole of that formula, which is why the 19
 * and the 20 are derived here rather than written as literals: a site that
 * printed the ratio without the multipliers it comes from would be one more
 * unfalsifiable number.
 */

/** A cache read bills at a tenth of the input rate. `README.md`, "The question". */
export const CACHE_READ_MULTIPLIER = 0.1;

/**
 * A one-hour cache write bills at twice the input rate.
 *
 * Not the list-price 1.25× five-minute class, and the difference is a
 * measurement rather than a preference: `README.md` records it as a measurement
 * over 26,194 turns of one install where every main-thread turn wrote at the
 * one-hour class. `docs/COZEMPIC.md` §3.1 keeps the earlier version on the
 * record, where 1.25× was assumed from the documentation and invalidation came
 * out about 40 percent too cheap.
 */
export const CACHE_WRITE_1H_MULTIPLIER = 2.0;

/**
 * The README's worked half cut: "Cut half the suffix and it pays for itself in
 * 18 turns."
 *
 * It is a worked example and not a setting. winnow has no horizon to configure
 * and the site does not imply one — the figures use this as the length of an
 * axis, because a cut at `S/D = 2` is the case the sources actually work
 * through, and a cut needing longer is a bet on how many turns a session has
 * left. In the corpus that was measured only 807 turns out of 11,422 sat past
 * index 160 at all.
 */
export const HALF_CUT_TURNS = 18;

/**
 * The published formula's `19` and `20`, in units of one turn's cache read.
 *
 * `19` is what the edit pays once — the suffix rewritten at the write rate
 * instead of read at the read rate — and `20` is the part of it the removed
 * tokens refund. Rounded here rather than at the end because binary floating
 * point does not hold `0.1`: `(2.0 − 0.1) / 0.1` evaluates to
 * `18.999999999999996`, and carrying that through lands `S/D = 1.5` on
 * `8.499999999999996`, which rounds to 8 where the README's own
 * `19·(S/D) − 20` gives 9. One turn, on exactly the cut the half example sits at.
 */
const TURNS_PER_RATIO = Math.round(
  (CACHE_WRITE_1H_MULTIPLIER - CACHE_READ_MULTIPLIER) / CACHE_READ_MULTIPLIER,
);
const TURNS_REFUNDED = Math.round(
  CACHE_WRITE_1H_MULTIPLIER / CACHE_READ_MULTIPLIER,
);

/**
 * Further turns before an edit that removed `removedTokens` pays for itself.
 *
 * `suffixBeforeCut` is the whole of what sat after the cut point **including the
 * part about to be removed**. Passing the after figure instead is off by exactly
 * `D` — small when the cut is small and enormous when it is large, so it
 * flatters precisely the cuts that do not pay.
 *
 * Null when nothing was removed, because then there is no edit to pay for. Zero
 * rather than a negative number when the cut is large enough to have paid
 * already: "it pays immediately" is the meaning, and a caller comparing against
 * a horizon should not have to know the formula can go below zero.
 */
export function paybackTurns(
  suffixBeforeCut: number,
  removedTokens: number,
): number | null {
  if (removedTokens <= 0) return null;

  const turns =
    TURNS_PER_RATIO * (suffixBeforeCut / removedTokens) - TURNS_REFUNDED;
  return Math.max(0, Math.round(turns));
}
