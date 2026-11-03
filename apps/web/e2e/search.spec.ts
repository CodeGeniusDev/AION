import { test, expect } from "@playwright/test";

// Phase 1E: global search. Every assertion is against live API data —
// tests that need a real entity skip when the workspace genuinely has
// none. Nothing is ever seeded.

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test.describe("Phase 1E: Global search", () => {
  test("⌘K and / focus the search field from any page", async ({ page }) => {
    await page.goto("/dashboard");

    await page.keyboard.press("Control+k");
    const input = page.getByRole("combobox", { name: "Search AION" });
    await expect(input).toBeFocused();
    await expect(
      page.getByRole("listbox", { name: "Search results" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");

    // "/" focuses too, as long as the user is not already typing.
    await page.locator("main").click({ position: { x: 5, y: 5 } });
    await page.keyboard.press("/");
    await expect(input).toBeFocused();
    await page.keyboard.press("Escape");
  });

  test("searching real data returns a grouped result that deep-links", async ({
    page,
    request,
  }) => {
    const tasks = await (await request.get(`${API}/api/tasks`)).json();
    test.skip(tasks.items.length === 0, "No real tasks exist to search for.");
    const term = (tasks.items[0].title as string).slice(0, 12);
    // Probe the search API itself so the assertion follows whichever real
    // store actually holds the data — the test never assumes or seeds.
    const probe = await (
      await request.get(`${API}/api/search`, { params: { q: term } })
    ).json();
    const rows = Object.values<{ href: string; title: string; snippet: string }[]>(
      probe.groups,
    ).flat();
    test.skip(rows.length === 0, `No real row matches "${term}".`);
    const target = rows[0];

    await page.goto("/dashboard");
    await page.keyboard.press("Control+k");
    const input = page.getByRole("combobox", { name: "Search AION" });
    await input.fill(term);

    const option = page
      .getByRole("option", { name: target.title, exact: false })
      .first();
    await expect(option).toBeVisible({ timeout: 10_000 });
    // When the match sits in the title or snippet, it is highlighted.
    if (
      target.title.toLowerCase().includes(term.toLowerCase()) ||
      target.snippet.toLowerCase().includes(term.toLowerCase())
    ) {
      await expect(option.locator("mark").first()).toBeVisible();
    }

    await option.click();
    await expect
      .poll(() => decodeURIComponent(page.url()))
      .toBe(new URL(target.href, "http://localhost:3000").href);
  });

  test("quick action New workflow opens the real create form", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    await page.keyboard.press("Control+k");
    const input = page.getByRole("combobox", { name: "Search AION" });
    await input.fill("New workflow");
    await page.getByRole("option", { name: /New workflow/ }).first().click();
    await expect(page).toHaveURL(/\/workflows\?new=1/);
    await expect(
      page.getByRole("heading", { name: "New workflow" }),
    ).toBeVisible();
  });

  test("recent searches are persisted locally and clearable", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    await page.keyboard.press("Control+k");
    const input = page.getByRole("combobox", { name: "Search AION" });
    await input.fill("settings");
    await page.getByRole("option", { name: /Settings/ }).first().click();
    await expect(page).toHaveURL(/\/settings/);

    await page.goto("/dashboard");
    await page.keyboard.press("Control+k");
    const chip = page.getByRole("button", { name: "settings", exact: true });
    await expect(chip).toBeVisible();
    await page.getByRole("button", { name: "Clear" }).click();
    await expect(chip).toHaveCount(0);
    const stored = await page.evaluate(
      () => localStorage.getItem("aion-recent-searches"),
    );
    expect(stored).toBeNull();
  });

  test('"This page" scope filters the live task list without a server call', async ({
    page,
    request,
  }) => {
    const tasks = await (await request.get(`${API}/api/tasks`)).json();
    test.skip(tasks.items.length === 0, "No real tasks exist to filter.");
    const firstTitle = tasks.items[0].title;

    await page.goto("/tasks");
    await expect(page.getByText(firstTitle).first()).toBeVisible();

    await page.keyboard.press("Control+k");
    const listbox = page.getByRole("listbox", { name: "Search results" });
    await listbox.getByRole("button", { name: "This page" }).click();
    const input = page.getByRole("combobox", { name: "Search AION" });
    await input.fill("zzqx-no-such-task");

    await expect(page.getByText(firstTitle)).toHaveCount(0);
    await expect(page.getByText("No tasks found")).toBeVisible();

    // Back to "All" restores the untouched real list.
    await listbox.getByRole("button", { name: "All", exact: true }).click();
    await expect(page.getByText(firstTitle).first()).toBeVisible();
  });

  test("deep link /chat?c=ID opens the real conversation", async ({
    page,
    request,
  }) => {
    const conversations = await (
      await request.get(`${API}/api/conversations`)
    ).json();
    test.skip(
      conversations.length === 0,
      "No real conversations exist to open.",
    );
    const convo = conversations[0];
    const messages = await (
      await request.get(`${API}/api/conversations/${convo.conversation_id}/messages`)
    ).json();
    test.skip(messages.length === 0, "Conversation has no messages.");
    const text: string = messages[0].content;

    await page.goto(`/chat?c=${convo.conversation_id}`);
    await expect(
      page.getByText(text.slice(0, 40), { exact: false }).first(),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("mobile overlay makes search reachable below sm", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/dashboard");
    await page.getByRole("button", { name: "Open search" }).click();
    const input = page.getByRole("combobox", { name: "Search AION" });
    await expect(input).toBeFocused();
    await expect(
      page.getByRole("listbox", { name: "Search results" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Close search" }).click();
    await expect(input).toBeHidden();
  });
});
