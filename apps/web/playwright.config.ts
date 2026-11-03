import { defineConfig } from "@playwright/test";

// Port is configurable so the suite can never "pass" against an
// unrelated app already listening on 3000 (reuseExistingServer would
// silently adopt it). Default stays 3000 for normal local dev.
const PORT = Number(process.env.PLAYWRIGHT_PORT ?? 3000);

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  // Tests share one dev server and one in-process backend (settings are
  // mutable, theme syncs to /api/settings). Serialization avoids races.
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: `http://localhost:${PORT}`,
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `/usr/local/bin/node ./node_modules/next/dist/bin/next dev --port ${PORT}`,
    port: PORT,
    timeout: 60_000,
    reuseExistingServer: true,
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
});
