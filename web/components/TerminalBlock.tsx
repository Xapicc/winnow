/**
 * An inset well for commands and their output.
 *
 * The `$` prompt is a `::before` on each command line so that selecting the
 * block copies a runnable command and not the prompt. Every command shown on
 * this site is one you can actually run — see docs/design-language.md §8.
 *
 * The well scrolls sideways rather than wrapping, because a wrapped shell
 * command is a lie about what you would type. A scroll container that only a
 * mouse can reach fails WCAG 2.1.1, so it is a named, focusable group.
 */

type TerminalBlockProps = {
  /** Shell lines, without the `$`. A line starting `#`, or blank, is not prompted. */
  commands: readonly string[];
  /** Output printed under the commands. Rendered plainly, no prompt. */
  output?: readonly string[];
  className?: string;
};

export function TerminalBlock({
  commands,
  output,
  className = "",
}: TerminalBlockProps) {
  return (
    <pre
      className={`wn-terminal ${className}`}
      role="group"
      aria-label="terminal"
      tabIndex={0}
    >
      {commands.map((command, index) => {
        // A comment and a blank line are part of a pasted block, but neither is
        // something you type at a prompt, so neither gets one.
        const isCommand = command.trim() !== "" && !command.startsWith("#");
        return (
          <span
            // Line order is fixed by the block; lines are never reordered, and
            // a block may legitimately repeat one.
            key={index}
            // fg-muted, not fg-faint: a `#` line here carries the instruction,
            // and fg-faint never carries information — see §1.
            className={isCommand ? "wn-terminal-command" : "text-fg-muted"}
          >
            {command === "" ? " " : command}
          </span>
        );
      })}
      {output?.map((line, index) => (
        <span key={index} className="text-fg-muted">
          {line}
        </span>
      ))}
    </pre>
  );
}
