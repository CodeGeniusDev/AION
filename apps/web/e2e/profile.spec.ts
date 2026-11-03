import { test, expect } from "@playwright/test";

// Phase 1D: header, dashboard greeting and the Profile page must all read
// the SAME profile from GET /api/profile. Phase 2A: tests that need a
// specific profile state now drive it deterministically through the
// AION_TEST_MODE fixture endpoints (reset + optional seed) instead of
// skipping when the workspace happens to already have (or lack) a profile.

const API =
  process.env.AION_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

async function resetState(request: import("@playwright/test").APIRequestContext) {
  const res = await request.post(`${API}/api/_test/reset`);
  // 404 means AION_TEST_MODE is off — the suite would then be running
  // against a developer's real backend, which is exactly what Phase 2A
  // is designed to prevent. Fail loudly instead of silently skipping.
  expect(res.ok(), `E2E isolation broken: ${res.status()} ${await res.text()}`).toBeTruthy();
}

test.describe("Phase 1D: Profile single source of truth", () => {
  test("header and dashboard greeting match a seeded profile", async ({
    page,
    request,
  }) => {
    await resetState(request);
    await request.post(`${API}/api/_test/seed/profile`, {
      data: {
        display_name: "Ada Lovelace",
        username: "ada",
        email: "",
        role: "",
        timezone: "UTC",
        bio: "",
        avatar_color: "navy",
      },
    });
    const body = await (await request.get(`${API}/api/profile`)).json();
    expect(body.configured).toBeTruthy();

    await page.goto("/dashboard");
    const h1 = page.locator("header h1").first();
    const first = body.profile.display_name.trim().split(/\s+/)[0];
    await expect(h1).toHaveText(`Hello, ${first}`);
    await expect(
      page.getByRole("button", { name: "Open user menu" }),
    ).toContainText(body.profile.display_name);
  });

  test("profile page opens in setup state when no profile exists", async ({
    page,
    request,
  }) => {
    await resetState(request);
    const body = await (await request.get(`${API}/api/profile`)).json();
    expect(body.configured).toBeFalsy();

    await page.goto("/profile");
    await expect(
      page.getByText(
        "Set up your identity — your name appears in the header and dashboard.",
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Save profile changes" }),
    ).toContainText("Create profile");
    // Nothing is pre-filled on first run — no seeded data.
    await expect(page.getByLabel("Display name")).toHaveValue("");
  });

  test("stats tiles render real counts from the live stores", async ({
    page,
    request,
  }) => {
    await resetState(request);
    // Seed one known task so the total is a real number, not an artifact
    // of prior tests or the memory fallback.
    await request.post(`${API}/api/_test/seed/task`, {
      data: { title: "phase1d stats tile anchor", status: "pending" },
    });
    const dashRes = await request.get(`${API}/api/dashboard`);
    expect(dashRes.ok()).toBeTruthy();
    const dashboard = await dashRes.json();

    await page.goto("/profile");
    const heading = page.getByRole("heading", {
      name: "Workspace statistics",
    });
    await expect(heading).toBeVisible();
    const statsSection = heading.locator("xpath=ancestor::section[1]");
    // The tasks total tile must equal the real store value — never a demo number.
    const totalValue = statsSection
      .getByText("Tasks total", { exact: true })
      .locator("xpath=preceding-sibling::p[1]");
    await expect(totalValue).toHaveText(String(dashboard.task_counts.total));
  });
});
