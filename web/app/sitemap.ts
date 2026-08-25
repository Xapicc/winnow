import type { MetadataRoute } from "next";

import { ROUTES, SITE_URL } from "@/lib/site";

export const dynamic = "force-static";

/**
 * Static, from the one list of routes in `lib/site.ts` — which is itself the
 * nav, so nothing is listed twice and a page nothing links to is not published.
 *
 * No `lastModified`: the build has no honest date to put there, and a timestamp
 * that is really "when this deploy happened" tells a crawler the content
 * changed when it did not.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  return ROUTES.map((route) => ({
    url: new URL(route, SITE_URL).href,
    changeFrequency: "monthly",
    priority: route === "/" ? 1 : 0.8,
  }));
}
