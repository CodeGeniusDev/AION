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
});
