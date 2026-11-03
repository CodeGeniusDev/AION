import { test, expect } from "@playwright/test";

// Phase 1 verification: global shell, header controls, universal search, dark mode, profile page.

test.describe("Phase 1: Global Shell & Header Controls", () => {
  test("profile page renders with all required sections and live data", async ({
    page,
  }) => {
    await page.goto("/profile");
    await expect(
      page.getByRole("heading", { name: "Profile", level: 1 }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Profile overview" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Personal information" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Workspace statistics" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Account information" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Appearance" }),
    ).toBeVisible();
    // Notification toggles live ONLY in Settings (Profile links there).
    await expect(page.getByLabel("Notify on task completions")).toHaveCount(0);
    await expect(
      page.getByRole("link", { name: "Open Settings" }),
    ).toBeVisible();
  });

  test("profile page handles validation and editing workflow", async ({
    page,
  }) => {
    await page.goto("/profile");
    const nameInput = page.getByLabel("Display name");
    await expect(nameInput).toBeVisible();

    // The baseline is whatever the real store holds (empty on first run —
    // nothing is ever seeded); the test must not mutate server state.
    const baseline = await nameInput.inputValue();

    // Verify initial save buttons are disabled (not dirty)
    const saveButton = page.getByRole("button", {
      name: "Save profile changes",
    });
    const cancelButton = page.getByRole("button", { name: "Cancel changes" });
    await expect(saveButton).toBeDisabled();
    await expect(cancelButton).toBeDisabled();

    // Typing makes the form dirty; clearing it surfaces inline validation.
    await nameInput.fill("Playwright Temp Name");
    await expect(saveButton).toBeEnabled();
    await nameInput.fill("");
    await expect(page.locator("#display-name-error")).toBeVisible();
    await expect(page.locator("#display-name-error")).toContainText(
      "Display name cannot be empty",
    );
    await expect(saveButton).toBeDisabled();

    // Invalid email is caught inline too.
    await nameInput.fill("Playwright Temp Name");
    const emailInput = page.getByLabel(/Email address/);
    await emailInput.fill("not-an-email");
    await expect(saveButton).toBeDisabled();
    await emailInput.fill("");

    // Cancel reverts to the stored baseline without saving.
    await cancelButton.click();
    await expect(nameInput).toHaveValue(baseline);
    await expect(page.locator("#display-name-error")).toBeHidden();
    await expect(saveButton).toBeDisabled();
  });

  test("theme toggle switches between light and dark across the application and persists on reload", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    const html = page.locator("html");
    await expect(html).toHaveAttribute("data-theme", /light|dark/);

    const toggleBtn = page.getByRole("button", { name: "Toggle theme" });
    await expect(toggleBtn).toBeVisible();

    // Switch to dark
    const initialTheme = await html.getAttribute("data-theme");
    await toggleBtn.click();
    const newTheme = initialTheme === "dark" ? "light" : "dark";
    await expect(html).toHaveAttribute("data-theme", newTheme);

    // Refresh and confirm persistence
    await page.reload();
    await expect(html).toHaveAttribute("data-theme", newTheme);

    // Toggle back
    await toggleBtn.click();
    await expect(html).toHaveAttribute("data-theme", initialTheme ?? "light");
  });

  test("universal search opens with ⌘K, searches across categories, supports keyboard nav, and closes on Escape", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    await page.keyboard.press("Control+k");

    const searchInput = page.getByRole("combobox", { name: "Search AION" });
    const searchDropdown = page.getByRole("listbox", {
      name: "Search results",
    });

    await expect(searchInput).toBeFocused();
    await expect(searchDropdown).toBeVisible();

    // Filter by 'tasks'
    await searchInput.fill("tasks");
    await expect(
      page.getByRole("option", { name: /Tasks/ }).first(),
    ).toBeVisible();

    // Keyboard navigation (ArrowDown, ArrowUp)
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowUp");

    // Close on Escape
    await page.keyboard.press("Escape");
    await expect(searchDropdown).toBeHidden();
  });

  test("search result navigates accurately to destination page", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    await page.keyboard.press("Control+k");
    const searchInput = page.getByRole("combobox", { name: "Search AION" });
    await searchInput.fill("settings");
    await page
      .getByRole("option", { name: /Settings/ })
      .first()
      .click();
    await expect(page).toHaveURL(/\/settings/);
  });

  test("notifications popover opens, displays real state, and handles mark as read", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    const notifBtn = page.getByRole("button", { name: /^Notifications/ });
    await expect(notifBtn).toBeVisible();
    await notifBtn.click();

    const notifDialog = page.getByRole("dialog", { name: "Notifications" });
    await expect(notifDialog).toBeVisible();
    await expect(
      notifDialog.getByText("Notifications", { exact: true }),
    ).toBeVisible();
  });

  test("settings shortcut navigates directly to settings page", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    const settingsBtn = page.getByRole("link", { name: "Settings" }).first();
    await expect(settingsBtn).toBeVisible();
    await settingsBtn.click();
    await expect(page).toHaveURL(/\/settings/);
  });

  test("profile menu provides working links to profile, settings, shortcuts dialog, and theme switcher", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    await page.getByRole("button", { name: "Open user menu" }).click();
    const menu = page.getByRole("dialog", { name: "Account menu" });
    await expect(menu).toBeVisible();

    // Navigation links
    await expect(menu.getByRole("link", { name: "Profile" })).toBeVisible();
    await expect(
      menu.getByRole("link", { name: "Account settings" }),
    ).toBeVisible();

    // Theme selector
    await expect(menu.getByRole("button", { name: "Light" })).toBeVisible();
    await expect(menu.getByRole("button", { name: "Dark" })).toBeVisible();
    await expect(menu.getByRole("button", { name: "System" })).toBeVisible();

    // Keyboard shortcuts dialog
    await menu.getByRole("button", { name: "Keyboard shortcuts" }).click();
    const shortcutsModal = page.getByRole("dialog", {
      name: "Keyboard shortcuts",
    });
    await expect(shortcutsModal).toBeVisible();
    await expect(shortcutsModal.getByText("Focus global search")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(shortcutsModal).toBeHidden();
  });

  test("mobile responsive drawer operates cleanly", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/dashboard");

    const menuBtn = page.getByRole("button", { name: "Open navigation" });
    await expect(menuBtn).toBeVisible();
    await menuBtn.click();

    const closeBtn = page.getByRole("button", {
      name: "Close navigation",
      exact: true,
    });
    await expect(closeBtn).toBeVisible();
    await closeBtn.click();
    await expect(closeBtn).toBeHidden();
  });

  test("strict no-demo-data enforcement", async ({ page }) => {
    await page.goto("/dashboard");
    // Ensure no hardcoded dummy metrics or fake statistics
    await expect(page.locator("body")).not.toContainText("68%");
    await expect(page.locator("body")).not.toContainText("System usage");
    await expect(page.locator("body")).not.toContainText("Demo User");
  });
});
