import { test, expect } from "@playwright/test";

// Phase 1C: header controls backed by real data — notifications bell,
// theme button, user menu, settings link, single New Task entry.
// The API must be running on :8000 (same assumption as the profile
// tests in phase1-shell.spec.ts).

const API = process.env.AION_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test.describe("Phase 1C: Header controls", () => {
  test("bell badge matches the real unread count from GET /api/alerts", async ({
    page,
    request,
  }) => {
    const apiRes = await request.get(`${API}/api/alerts?limit=50`);
    expect(apiRes.ok()).toBeTruthy();
    const { unread_count: unread } = await apiRes.json();

    await page.goto("/dashboard");
    const bell = page.getByRole("button", { name: /^Notifications/ });
    await expect(bell).toBeVisible();

    const badge = bell.locator("span").first();
    if (unread === 0) {
      await expect(bell).toHaveAttribute("aria-label", "Notifications");
      await expect(badge).toHaveCount(0);
    } else {
      await expect(bell).toHaveAttribute(
        "aria-label",
        `Notifications, ${unread} unread`,
      );
      await expect(badge).toHaveText(unread > 9 ? "9+" : String(unread));
    }
  });

  test("popover lists at most 8 alerts, View all lands on /alert, and keyboard dismiss returns focus", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    const bell = page.getByRole("button", { name: /^Notifications/ });
    await bell.click();

    const panel = page.getByRole("dialog", { name: "Notifications" });
    await expect(panel).toBeVisible();

    // Real data governs the list length; the cap is 8.
    const items = panel.locator("ul li");
    const count = await items.count();
    expect(count).toBeLessThanOrEqual(8);

    // Escape closes and focus returns to the bell trigger.
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(bell).toBeFocused();

    // View all navigates to the absolute /alert route.
    await bell.click();
    await panel.getByRole("link", { name: "View all notifications" }).click();
    await expect(page).toHaveURL(/\/alert$/);
  });

  test("theme button reflects the preference, toggles with aria-pressed and persists across reload", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    const btn = page.getByRole("button", { name: "Toggle theme" });
    await expect(btn).toHaveAttribute("aria-pressed", /true|false/);
    const svg = btn.locator("svg");
    await expect(svg).toHaveCount(1);

    const before = await btn.getAttribute("aria-pressed");
    await btn.click();
    await expect(btn).toHaveAttribute(
      "aria-pressed",
      before === "true" ? "false" : "true",
    );

    await page.reload();
    await expect(
      page.getByRole("button", { name: "Toggle theme" }),
    ).toHaveAttribute("aria-pressed", before === "true" ? "false" : "true");
  });

  test("user menu exposes real links, desktop approvals and the app version", async ({
    page,
    request,
  }) => {
    const health = await (await request.get(`${API}/health`)).json();

    await page.goto("/dashboard");
    await page.getByRole("button", { name: "Open user menu" }).click();
    const menu = page.getByRole("dialog", { name: "Account menu" });
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("link", { name: /Profile/ })).toBeVisible();
    await expect(
      menu.getByRole("link", { name: /Account settings/ }),
    ).toBeVisible();
    await expect(
      menu.getByRole("link", { name: /Desktop approvals/ }),
    ).toBeVisible();
    await expect(menu.getByText(`AION v${health.version}`)).toBeVisible();
    // No fake sign-out affordance exists anywhere in the menu.
    await expect(menu.getByRole("button", { name: /sign out/i })).toHaveCount(
      0,
    );
  });

  test("New Task exists only in the sidebar — no duplicate in page headers", async ({
    page,
  }) => {
    for (const route of ["/dashboard", "/tasks"]) {
      await page.goto(route);
      const newTask = page.getByRole("button", { name: "New Task" });
      await expect(newTask).toHaveCount(0);
      // The single real entry point is the sidebar link (desktop sidebar;
      // the mobile drawer copy is hidden at this viewport).
      const sidebarLink = page
        .locator("aside")
        .getByRole("link", { name: /New Task/ })
        .first();
      await expect(sidebarLink).toBeVisible();
    }
  });

  test("settings icon is a link with active state on /settings", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    const settingsLink = page
      .locator("header")
      .getByRole("link", { name: "Settings" });
    await expect(settingsLink).toHaveAttribute("href", "/settings");
    await expect(settingsLink).not.toHaveAttribute("aria-current", "page");

    await page.goto("/settings");
    await expect(
      page.locator("header").getByRole("link", { name: "Settings" }),
    ).toHaveAttribute("aria-current", "page");
  });
});
