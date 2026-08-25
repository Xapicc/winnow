import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against the production build — `next build` then
 * `next start` — never the dev server: the dev server serves different markup,
 * different assets and an error overlay, so a green dev run proves nothing
 * about what a deployment would serve.
 *
 * Port 4322, one clear of the sibling UsageFoundry site's 4321, so both suites
 * can run on one machine without either stealing the other's server.
 */
const PORT = 4322;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: `npm run build && npm run start -- --port ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
