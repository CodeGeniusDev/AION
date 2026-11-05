import { defineConfig } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Port is configurable so the suite can never "pass" against an
// unrelated app already listening on 3000 (reuseExistingServer would
// silently adopt it). Phase 2A defaults to a non-development port so
// reuseExistingServer:false never collides with a running dev stack.
const PORT = Number(process.env.PLAYWRIGHT_PORT ?? 3123);
// Phase 2A: the API is booted by Playwright itself, on its own port, so
// E2E writes NEVER reach the developer's real :8000 process or DB files.
const API_PORT = Number(process.env.PLAYWRIGHT_API_PORT ?? 3124);
const API_ORIGIN = `http://127.0.0.1:${API_PORT}`;
// Fresh temp directory per Playwright invocation — every SQLite file
// (memory, approvals, profile, workflows, schedules) lives here and is
// discarded when the run ends. Nothing is written under apps/api/.data.
const TEMP_ROOT = mkdtempSync(join(tmpdir(), "aion-e2e-"));

const PY = "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3";

// Backend env for the E2E-only API process. AION_TEST_MODE turns on the
// /api/_test/* fixture endpoints so specs can seed deterministic state;
// AION_DISABLE_MODEL_CALLS keeps every test hermetic (no Gemini traffic).
const apiEnv = {
  PATH: process.env.PATH ?? "",
  HOME: process.env.HOME ?? "",
  AION_TEST_MODE: "1",
  AION_DISABLE_MODEL_CALLS: "1",
  AION_MEMORY_DB_PATH: join(TEMP_ROOT, "memory.db"),
  AION_APPROVAL_DB_PATH: join(TEMP_ROOT, "approvals.db"),
  AION_PROFILE_DB_PATH: join(TEMP_ROOT, "profile.db"),
  AION_WORKFLOW_DB_PATH: join(TEMP_ROOT, "workflows.db"),
  AION_SCHEDULE_DB_PATH: join(TEMP_ROOT, "schedules.db"),
  // Phase 2A: match the E2E browser origin so CORSMiddleware allows the
  // Next dev server on the isolated port; otherwise browser fetches fail
  // silently and profile/bell assertions read stale local state.
  FRONTEND_ORIGIN: `http://localhost:${PORT}`,
  PORT: String(API_PORT),
};

// Phase 2A: expose the E2E-only API origin to spec files so any direct
// `request.*` call hits the isolated backend on 3124 instead of the
// developer's :8000. Playwright workers inherit process.env from the
// parent, and this file is evaluated before any worker spawns.
// `PLAYWRIGHT_TEMP_ROOT` lets a spec prove a fixture wrote to the temp
// DB file, not the developer's real one.
process.env.AION_API_URL = API_ORIGIN;
process.env.PLAYWRIGHT_TEMP_ROOT = TEMP_ROOT;

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
  // Order matters: webServer starts the API first, then Next. Next waits
  // on the API to be reachable via the readiness check before its own
  // subprocess starts, so no first-request race.
  webServer: [
    {
      command: `${PY} -m uvicorn main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: "../api",
      url: `${API_ORIGIN}/health`,
      timeout: 60_000,
      reuseExistingServer: false,
      env: apiEnv,
    },
    {
      command: `/usr/local/bin/node ./node_modules/next/dist/bin/next dev --port ${PORT}`,
      port: PORT,
      timeout: 60_000,
      // reuseExistingServer: false + a non-default port guarantees we
      // never adopt a foreign dev server. Developers running the app
      // normally on :3000 keep their stack up; E2E is fully isolated.
      reuseExistingServer: false,
      env: {
        PATH: process.env.PATH ?? "",
        HOME: process.env.HOME ?? "",
        NEXT_PUBLIC_API_URL: API_ORIGIN,
      },
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
});
