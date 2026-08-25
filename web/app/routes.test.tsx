import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import ArithmeticPage from "@/app/arithmetic/page";
import FilterPage from "@/app/filter/page";
import HomePage from "@/app/page";
import StatusPage from "@/app/status/page";
import { NAV_LINKS, ROUTES, SECTIONS } from "@/lib/site";

/**
 * Every route renders, and nothing on any of them points at something that is
 * not there.
 *
 * docs/design-language.md §9 asks for this and §7 says why it is a test rather
 * than a habit: the deep links live on `SECTIONS` so that adding a section and
 * forgetting its anchor is one edit rather than two, and the failure mode of
 * getting it wrong is a link that scrolls nowhere — which looks, to whoever
 * clicks it, exactly like a page that has not loaded yet.
 *
 * Everything here renders on the server, so `renderToStaticMarkup` is the whole
 * harness; the client components on these pages are written to render their
 * resolved state on the server for the reason §5 gives.
 */

const PAGES: Record<string, () => React.JSX.Element> = {
  "/": HomePage,
  "/arithmetic": ArithmeticPage,
  "/filter": FilterPage,
  "/status": StatusPage,
};

/** Rendered once; every assertion below reads these rather than re-rendering. */
const HTML = Object.fromEntries(
  Object.entries(PAGES).map(([route, Page]) => [route, renderToStaticMarkup(<Page />)]),
) as Record<string, string>;

/** Every `id` attribute an anchor could land on, per route. */
function idsOf(html: string): Set<string> {
  return new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((match) => match[1] ?? ""));
}

const IDS = Object.fromEntries(
  Object.entries(HTML).map(([route, html]) => [route, idsOf(html)]),
) as Record<string, Set<string>>;

/** Every `href` on a route, in source order, excluding external ones. */
function internalHrefs(html: string): string[] {
  return [...html.matchAll(/\shref="([^"]+)"/g)]
    .map((match) => match[1] ?? "")
    .filter((href) => href.startsWith("/") || href.startsWith("#"));
}

/** Splits `/filter#savings` into the route it names and the anchor on it. */
function resolve(href: string, from: string): { route: string; anchor: string } {
  if (href.startsWith("#")) return { route: from, anchor: href.slice(1) };
  const [route = "", anchor = ""] = href.split("#");
  return { route, anchor };
}

describe("the route table", () => {
  it("covers exactly the pages this test renders", () => {
    // If a route is added to `NAV_LINKS` and not here, the rest of this file
    // silently stops checking it.
    expect([...ROUTES].sort()).toEqual(Object.keys(PAGES).sort());
  });

  it("derives itself from the nav, so nothing is in the sitemap unlinked", () => {
    expect(ROUTES).toEqual(["/", ...NAV_LINKS.map((link) => link.href)]);
  });
});

describe.each(Object.keys(PAGES))("%s", (route) => {
  const html = HTML[route] ?? "";

  it("has exactly one h1", () => {
    expect(html.match(/<h1[\s>]/g) ?? []).toHaveLength(1);
  });

  it("hides every piece of character art from a screen reader", () => {
    // §4: a screen reader gets the heading or the caption, never 470 block
    // characters. `wn-terminal` is deliberately not in this set — a command
    // block is text somebody has to be able to read, and it carries a role and
    // a label instead.
    const art = [...html.matchAll(/<pre[^>]*class="(?:wn-ascii|wn-figure)[^"]*"[^>]*>/g)];
    expect(art.length).toBeGreaterThan(0);
    for (const pre of art) {
      expect(pre[0]).toContain('aria-hidden="true"');
    }
  });

  it("leaves no emphasis mark unresolved in its copy", () => {
    // `Ticks` resolves `*starred*` spans in pairs, so an odd star anywhere in a
    // copy string leaves exactly one behind — and swallows the rest of the
    // sentence into an `<em>` on the way. Character art and code spans are
    // exempt: a `T*` or a `src/**/*.ts` in one of those is literal and meant.
    const prose = html
      .replace(/<pre[\s\S]*?<\/pre>/g, " ")
      .replace(/<code[\s\S]*?<\/code>/g, " ")
      .replace(/<[^>]*>/g, " ");
    expect(prose, `${route} has a stray emphasis star`).not.toContain("*");
  });

  it("links only to routes that exist", () => {
    for (const href of internalHrefs(html)) {
      const { route: target } = resolve(href, route);
      expect(ROUTES, `${route} links to ${href}`).toContain(target);
    }
  });

  it("links only to anchors that exist on the page they name", () => {
    for (const href of internalHrefs(html)) {
      const { route: target, anchor } = resolve(href, route);
      if (!anchor) continue;
      expect([...(IDS[target] ?? [])], `${route} links to ${href}`).toContain(anchor);
    }
  });
});

describe("the home page's section index", () => {
  it("gives every section an anchor on the page itself", () => {
    for (const section of SECTIONS) {
      expect(IDS["/"]).toContain(section.id);
    }
  });

  it("gives every section a deep link that resolves", () => {
    for (const section of SECTIONS) {
      const { route, anchor } = resolve(section.href, "/");
      expect(ROUTES, `${section.id} deep-links to ${section.href}`).toContain(route);
      expect([...(IDS[route] ?? [])], `${section.id} deep-links to ${section.href}`)
        .toContain(anchor);
    }
  });
});
