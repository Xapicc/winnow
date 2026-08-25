import type { AnchorHTMLAttributes, ReactNode } from "react";

/**
 * The site's only control. `primary` is a filled accent block with canvas-dark
 * text (7.59:1 — white on the accent would be 2.15:1, and white on
 * `--color-accent-deep` 3.39:1, so neither is used anywhere); `ghost` is a
 * bracketed label that picks up the accent on hover.
 *
 * Both are 2.25rem tall. See docs/design-language.md §1 for the measurements.
 */

type ButtonProps = {
  href: string;
  variant?: "primary" | "ghost";
  external?: boolean;
  children: ReactNode;
  className?: string;
} & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href" | "className">;

const BASE =
  "wn-state inline-flex h-9 items-center whitespace-nowrap text-small font-medium";

const VARIANT = {
  /* No glow and no aberration here, unlike every other interactive element on
     the site. Both are text-shadows, and this is the one place the text is
     canvas-dark on a saturated fill: the glow paints an orange halo behind dark
     glyphs and the aberration paints a red fringe on them. Both read as a
     rendering fault rather than as texture. See docs/design-language.md §6.

     The hover mix lightens the fill to 8.60:1 against canvas text, so hovering
     is never a contrast regression. */
  primary:
    "bg-accent text-canvas px-[2ch] hover:bg-[color-mix(in_oklab,var(--color-accent)_86%,white)]",
  /* No outer padding: the brackets are the affordance, and they should line up
     with the text column they sit under. */
  ghost: "wn-aberrate text-fg-muted hover:text-accent focus-visible:text-accent",
} as const;

export function Button({
  href,
  variant = "primary",
  external = false,
  children,
  className = "",
  ...rest
}: ButtonProps) {
  const externalProps = external
    ? { target: "_blank", rel: "noreferrer noopener" }
    : {};

  return (
    <a
      href={href}
      className={`${BASE} ${VARIANT[variant]} ${className}`}
      {...externalProps}
      {...rest}
    >
      {variant === "ghost" ? (
        <>
          <span aria-hidden="true" className="text-fg-faint">
            [
          </span>
          <span className="px-[1ch]">{children}</span>
          <span aria-hidden="true" className="text-fg-faint">
            ]
          </span>
        </>
      ) : (
        children
      )}
    </a>
  );
}
