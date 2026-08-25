import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    // Through `URL`, not concatenation: an origin supplied by
    // `NEXT_PUBLIC_SITE_URL` may well arrive with a trailing slash.
    sitemap: new URL("/sitemap.xml", SITE_URL).href,
  };
}
