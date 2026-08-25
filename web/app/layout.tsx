import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";

import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { SITE_DESCRIPTION, SITE_NAME, SITE_TAGLINE, SITE_URL } from "@/lib/site";

import "./globals.css";

/**
 * Self-hosted, no runtime font CDN. Cut from the upstream JetBrains Mono
 * release rather than pulled from Google Fonts, because the Google `latin`
 * subset carries no box-drawing or block-element glyphs and this site is built
 * on them. The licence travels with the file, beside it in
 * `JetBrainsMono-OFL.txt`. See docs/design-language.md §2.
 */
const jetbrainsMono = localFont({
  src: "./fonts/JetBrainsMono-Variable-subset.woff2",
  weight: "100 800",
  style: "normal",
  display: "swap",
  variable: "--font-jetbrains-mono",
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
});

export const metadata: Metadata = {
  /* Absolute origin for the canonical URL and the sitemap. Its default is
     committed in lib/site.ts, so a build with no variables set still emits
     correct absolute URLs. */
  metadataBase: new URL(SITE_URL),
  alternates: { canonical: "/" },
  title: {
    default: `${SITE_NAME} — what pruning a Claude Code session actually costs`,
    template: `%s — ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  authors: [{ name: SITE_NAME }],
  keywords: [
    "Claude Code",
    "context pruning",
    "prompt cache",
    "tool output",
    "transcript",
    "cache invalidation",
  ],
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    title: `${SITE_NAME} — ${SITE_TAGLINE}`,
    description: SITE_DESCRIPTION,
    locale: "en_GB",
    url: "/",
  },
  twitter: {
    card: "summary",
    title: `${SITE_NAME} — ${SITE_TAGLINE}`,
    description: SITE_DESCRIPTION,
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: "#0a0a0b",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    /* en-GB, not en: the copy is British throughout ("summariser",
       "behaviour") and the OpenGraph locale already says so. */
    <html lang="en-GB" className={jetbrainsMono.variable}>
      <body className="relative min-h-screen">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-[70] focus:bg-accent focus:px-[2ch] focus:py-2 focus:text-small focus:text-canvas"
        >
          Skip to content
        </a>

        {/* Texture layers. Both are decorative and neither takes pointer events;
            the grid sits under the content, the scanlines sit over it. */}
        <div aria-hidden="true" className="wn-texture wn-texture-grid" />

        <div className="relative z-10 flex min-h-screen flex-col">
          <SiteHeader />
          <main id="main" className="flex-1">
            {children}
          </main>
          <SiteFooter />
        </div>

        <div aria-hidden="true" className="wn-texture wn-texture-scanlines" />
      </body>
    </html>
  );
}
