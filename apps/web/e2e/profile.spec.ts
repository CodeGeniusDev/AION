import { test, expect } from "@playwright/test";

// Phase 1D: header, dashboard greeting and the Profile page must all read
// the SAME profile from GET /api/profile. These tests never mutate server
// state — they assert consistency between the UI and the live API, so they
// pass identically on a first-run (unseeded) install and after setup.

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test.describe("Phase 1D: Profile single source of truth", () => {
  test("header and dashboard greeting match the stored profile", async ({
    page,
    request,
  }) => {
    const res = await request.get(`${API}/api/profile`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();

    await page.goto("/dashboard");
    const h1 = page.locator("header h1").first();
    if (body.configured) {
      const first = body.profile.display_name.trim().split(/\s+/)[0];
      await expect(h1).toHaveText(`Hello, ${first}`);
      await expect(
        page.getByRole("button", { name: "Open user menu" }),
      ).toContainText(body.profile.display_name);
    } else {
      // First run: neutral greeting, no invented name anywhere.
      await expect(h1).toHaveText("Hello");
      await expect(
        page.getByRole("button", { name: "Open user menu" }),
      ).toContainText("Set up profile");
      await expect(page.locator("body")).not.toContainText("Abdullah");
    }
  });

  test("profile page opens in setup state when no profile exists", async ({
    page,
    request,
  }) => {
    const body = await (await request.get(`${API}/api/profile`)).json();
    test.skip(body.configured, "A profile is already configured; setup state not applicable.");

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
    const dashRes = await request.get(`${API}/api/dashboard`);
    expect(dashRes.ok()).toBeTruthy();
    const dashboard = await dashRes.json();

    await page.goto("/profile");
    const heading = page.getByRole("heading", {
      name: "Workspace statistics",
    });
    await expect(heading).toBeVisible();
    const statsSection = heading.locator(
      "xpath=ancestor::section[1]",
    );
    // The tasks total tile must equal the real store value — never a demo number.
    const totalValue = statsSection
      .getByText("Tasks total", { exact: true })
      .locator("xpath=preceding-sibling::p[1]");
    await expect(totalValue).toHaveText(String(dashboard.task_counts.total));
  });
});
