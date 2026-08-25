import { Ascii } from "@/components/Ascii";
import { AsciiRule } from "@/components/AsciiRule";
import { MARK_SMALL } from "@/lib/ascii";
import { NAV_LINKS, REPO_URL, SITE_NAME } from "@/lib/site";

export function SiteFooter() {
  return (
    <footer className="mt-24">
      <AsciiRule tone="line" />
      <div className="wn-shell flex flex-wrap items-start justify-between gap-8 py-10">
        <div className="flex items-start gap-[2ch]">
          <Ascii
            art={MARK_SMALL}
            cap={6}
            className="text-accent-deep mt-1 shrink-0"
          />
          <div>
            <p className="text-small font-medium">{SITE_NAME}</p>
            <p className="text-micro text-fg-muted mt-1 max-w-[44ch]">
              Stdlib only. No model call, no network, no MCP server. Nothing here
              is installed and nothing is published to a package channel.
            </p>
          </div>
        </div>

        <nav
          aria-label="Footer"
          className="flex flex-col items-start gap-1 text-small"
        >
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="wn-aberrate wn-state text-fg-muted inline-flex min-h-6 items-center hover:text-fg"
            >
              {link.label}
            </a>
          ))}
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer noopener"
            className="wn-aberrate wn-state text-fg-muted inline-flex min-h-6 items-center hover:text-accent"
          >
            source<span aria-hidden="true"> ↗</span>
          </a>
        </nav>
      </div>
      <div className="wn-shell pb-10">
        {/* fg-muted, not fg-faint: this is a sentence someone has to be able to
            read, and fg-faint measures 3.92:1 on canvas. See §1. */}
        <p className="text-micro text-fg-muted">
          MIT. Contains Cozempic 1.8.39 by Ruya AI, forked and renamed. Claude
          and Claude Code are products of Anthropic; this project is not
          affiliated with Anthropic.
        </p>
      </div>
    </footer>
  );
}
