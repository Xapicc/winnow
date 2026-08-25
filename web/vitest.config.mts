import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

/**
 * Unit tests only — the browser layer is Playwright's, in `e2e/`.
 *
 * Components are rendered with `react-dom/server`, so no DOM implementation is
 * needed: everything on this site renders on the server, and the one client
 * component is asserted on for exactly that reason (its server output must be
 * the resolved art — docs/design-language.md §5).
 */
export default defineConfig({
  // `tsconfig.json` sets `jsx: preserve` for Next, which the transform would
  // otherwise honour and then choke on; tests need the JSX compiled.
  oxc: { jsx: { runtime: "automatic" } },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["{lib,components,app}/**/*.test.{ts,tsx}"],
  },
});
