import { AsciiPanel } from "@/components/AsciiPanel";
import { Button } from "@/components/Button";
import { SectionHeading } from "@/components/SectionHeading";
import { NAV_LINKS } from "@/lib/site";

/**
 * The 404. It renders inside the root layout, so it carries the site's own
 * header, footer and skip link rather than the framework's bare default.
 */
export default function NotFound() {
  return (
    <div className="wn-shell py-16">
      <SectionHeading kicker="404">No such page</SectionHeading>

      <div className="wn-measure mb-10">
        <p className="text-body text-fg-muted">
          That path is not part of this site. Everything it has is on three
          pages.
        </p>
      </div>

      <div className="max-w-[68ch]">
        <AsciiPanel label="pages">
          <ul className="flex flex-col gap-2">
            <li>
              <a href="/" className="wn-aberrate text-fg-muted hover:text-fg">
                home
              </a>
            </li>
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  className="wn-aberrate text-fg-muted hover:text-fg"
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </AsciiPanel>
      </div>

      <div className="mt-10">
        <Button href="/" variant="ghost">
          back to the start
        </Button>
      </div>
    </div>
  );
}
