import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Ticks } from "@/components/Ticks";

/**
 * `Ticks` is the only thing between a copy string and the page, and both of its
 * marks fail quietly when they are wrong: an unclosed backtick or star does not
 * throw, it swallows the rest of the sentence into a span.
 */

describe("Ticks", () => {
  it("marks backticked spans as code and leaves the rest alone", () => {
    const html = renderToStaticMarkup(
      <Ticks>{"reads `~/.winnow/filter.jsonl` on start"}</Ticks>,
    );
    expect(html).toBe(
      'reads <code class="text-accent">~/.winnow/filter.jsonl</code> on start',
    );
  });

  it("marks starred spans as upright weight, never as a synthesised italic", () => {
    // §2 ships no italic face. `not-italic` is the whole point of the class.
    const html = renderToStaticMarkup(<Ticks>{"what it *would* have done"}</Ticks>);
    expect(html).toBe(
      'what it <em class="text-fg font-medium not-italic">would</em> have done',
    );
  });

  it("leaves a star inside a code span literal", () => {
    // A glob is not emphasis. Backticks are resolved first for this reason.
    const html = renderToStaticMarkup(<Ticks>{"`src/**/*.ts` and *this*"}</Ticks>);
    expect(html).toContain("src/**/*.ts");
    expect(html.match(/<em/g) ?? []).toHaveLength(1);
  });

  it("handles both marks in one string", () => {
    const html = renderToStaticMarkup(<Ticks>{"`a` and *b* and `c`"}</Ticks>);
    expect(html.match(/<code/g) ?? []).toHaveLength(2);
    expect(html.match(/<em/g) ?? []).toHaveLength(1);
  });

  it("leaves a string with neither mark as plain text", () => {
    expect(renderToStaticMarkup(<Ticks>{"no marks here"}</Ticks>)).toBe(
      "no marks here",
    );
  });

  it("treats an unclosed backtick as opening a span to the end of the string", () => {
    // Not a crash and not silent truncation: the copy is visibly wrong instead.
    const html = renderToStaticMarkup(<Ticks>{"open `and never closed"}</Ticks>);
    expect(html).toContain("and never closed");
    expect(html.match(/<code/g) ?? []).toHaveLength(1);
  });

  it("does not swallow adjacent empty spans", () => {
    expect(renderToStaticMarkup(<Ticks>{"a``b"}</Ticks>)).toContain("b");
  });
});
