/**
 * A horizontal rule drawn with box-drawing characters instead of an `<hr>`.
 * The string is deliberately longer than any viewport and clipped by
 * `.wn-rule`, so the rule sits on the character grid at every width.
 */

const FILL_LENGTH = 400;

type AsciiRuleProps = {
  /** `light` is an internal divider, `heavy` is a section boundary. */
  weight?: "light" | "heavy";
  tone?: "faint" | "line" | "accent";
  className?: string;
};

const TONE_CLASS = {
  faint: "text-fg-faint",
  line: "text-line-strong",
  accent: "text-accent",
} as const;

export function AsciiRule({
  weight = "light",
  tone = "faint",
  className = "",
}: AsciiRuleProps) {
  const glyph = weight === "heavy" ? "═" : "─";
  return (
    <div
      aria-hidden="true"
      className={`wn-rule ${TONE_CLASS[tone]} ${className}`}
    >
      {glyph.repeat(FILL_LENGTH)}
    </div>
  );
}
