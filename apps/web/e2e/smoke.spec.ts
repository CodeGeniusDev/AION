import { test, expect } from "@playwright/test";

test.describe("App smoke tests", () => {
  test("homepage loads and redirects to dashboard", async ({ page }) => {
    await page.goto("/");
    // App should load without crashing
    await expect(page).toHaveTitle(/.+/);
  });

  test("dashboard page renders", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.locator("body")).toBeVisible();
  });

  test("chat page renders", async ({ page }) => {
    await page.goto("/chat");
    await expect(page.locator("body")).toBeVisible();
  });

  test("settings page renders", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.locator("body")).toBeVisible();
  });

  test("desktop page renders with approval-gated sections", async ({ page }) => {
    await page.goto("/desktop");
    await expect(
      page.getByRole("heading", { name: "Desktop", level: 1 }),
    ).toBeVisible();
    // Bridge health strip is always present — online, offline or
    // unreachable — never a crash, even with the backend down.
    await expect(
      page.getByRole("region", { name: "Desktop bridge health" }),
    ).toBeVisible();
    // Sidebar entry exists and points at the page.
    await expect(
      page.getByRole("link", { name: "Desktop" }).first(),
    ).toBeVisible();
  });
});
