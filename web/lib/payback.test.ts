import { describe, expect, it } from "vitest";

import {
  CACHE_READ_MULTIPLIER,
  CACHE_WRITE_1H_MULTIPLIER,
  HALF_CUT_TURNS,
  paybackTurns,
} from "./payback";

/**
 * Ported with the code it tests, from `Xapicc/UsageFoundryWeb:lib/payback.test.ts`.
 *
 * The break-even formula is the one piece of arithmetic on this site, and every
 * way of getting it wrong typechecks: swapped arguments, the after figure
 * instead of the before figure, the list-price write multiplier instead of the
 * measured one. All three produce a smaller, friendlier number, which is the
 * direction a site about not overclaiming can least afford to drift in.
 */

describe("the cache multipliers", () => {
  it("price a read at a tenth and a one-hour write at twice the input rate", () => {
    expect(CACHE_READ_MULTIPLIER).toBe(0.1);
    expect(CACHE_WRITE_1H_MULTIPLIER).toBe(2.0);
  });

  it("give the 19 and the 20 the README's formula is written with", () => {
    // If either multiplier is edited, `19·(S/D) − 20` stops being what the
    // figure draws and the site's own prose stops matching its own code.
    // Close-to rather than exact: binary floating point does not hold 0.1, and
    // paybackTurns rounds these to integers before using them for that reason.
    const invalidation = CACHE_WRITE_1H_MULTIPLIER - CACHE_READ_MULTIPLIER;
    expect(invalidation / CACHE_READ_MULTIPLIER).toBeCloseTo(19, 10);
    expect(CACHE_WRITE_1H_MULTIPLIER / CACHE_READ_MULTIPLIER).toBeCloseTo(20, 10);
  });
});

describe("paybackTurns", () => {
  it("reproduces the README's two worked examples", () => {
    // "Cut half the suffix and it pays for itself in 18 turns. Cut a tenth and
    // it needs 170 more turns than the session has had."
    expect(paybackTurns(120_000, 60_000)).toBe(18);
    expect(paybackTurns(120_000, 12_000)).toBe(170);
  });

  it("depends on S/D and not on the size of the session", () => {
    const small = paybackTurns(1_200, 600);
    const large = paybackTurns(1_200_000, 600_000);
    expect(small).toBe(large);
  });

  it("puts the half cut exactly on the number the README states", () => {
    // 18 is not a taste: it is the break-even for cutting exactly half.
    expect(paybackTurns(2, 1)).toBe(HALF_CUT_TURNS);
  });

  it("lands a two-thirds cut on 9, where the formula falls exactly on a half turn", () => {
    // 19·1.5 − 20 = 8.5. Deriving the 19 and the 20 from the multipliers
    // without rounding them first gives 8.499999999999996 and this returns 8.
    expect(paybackTurns(120_000, 80_000)).toBe(9);
  });

  it("flatters the cut when handed the suffix after the cut instead of before", () => {
    // Off by exactly D, so it is worst on the large cuts — the ones whose
    // payback claim matters.
    const before = paybackTurns(120_000, 60_000);
    const after = paybackTurns(120_000 - 60_000, 60_000);
    expect(before).toBe(18);
    // Not "18-ish": the after figure claims the cut has already paid for itself.
    expect(after).toBe(0);
  });

  it("returns null when nothing was removed, because there is no edit to pay for", () => {
    expect(paybackTurns(120_000, 0)).toBeNull();
    expect(paybackTurns(120_000, -1)).toBeNull();
  });

  it("floors at zero rather than going negative once the cut has paid already", () => {
    // S/D below 20/19 makes the formula negative; "it pays immediately" is the
    // meaning, and a caller comparing against a horizon should not have to know.
    expect(paybackTurns(100, 99)).toBe(0);
    expect(paybackTurns(100, 100)).toBe(0);
  });
});
