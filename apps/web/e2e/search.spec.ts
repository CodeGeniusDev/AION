import { test, expect } from "@playwright/test";

// Phase 1E: global search. Phase 2A: tests that need real entities seed
// them through the AION_TEST_MODE fixture endpoints instead of skipping
// when the workspace happens to be empty. Every assertion still reads the
// live stores — nothing is mocked or demo data.

const API =
  process.env.AION_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

async function resetState(request: import("@playwright/test").APIRequestContext) {
  const res = await request.post(`${API}/api/_test/reset`);
  expect(
    res.ok(),
    `E2E isolation broken: ${res.status()} ${await res.text()}`,
  ).toBeTruthy();
}

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
    await resetState(request);
    const seeded = await (
      await request.post(`${API}/api/_test/seed/task`, {
        data: { title: "quantum-widget-almanac", status: "pending" },
      })
    ).json();
    const term = "quantum-widget";
    // Probe the search API itself so the assertion follows whichever real
    // store actually holds the data — the test uses the same row the UI
    // will find, no guessing.
    const probe = await (
      await request.get(`${API}/api/search`, { params: { q: term } })
    ).json();
    const rows = Object.values<
      { href: string; title: string; snippet: string }[]
    >(probe.groups).flat();
    expect(rows.length, `Seeded task ${seeded.id} should be searchable`).toBeGreaterThan(0);
    const target = rows.find((r) => r.title.includes(term)) ?? rows[0];

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
    const expected = new URL(target.href, "http://localhost");
    await expect
      .poll(() => {
        const u = new URL(page.url());
        return `${u.pathname}${u.search}`;
      })
      .toBe(`${expected.pathname}${expected.search}`);
  });

  test("quick action New workflow opens the real create form", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    await page.keyboard.press("Control+k");
    const input = page.getByRole("combobox", { name: "Search AION" });
    await input.fill("New workflow");
    await page
      .getByRole("option", { name: /New workflow/ })
      .first()
      .click();
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
    await page
      .getByRole("option", { name: /Settings/ })
      .first()
      .click();
    await expect(page).toHaveURL(/\/settings/);

    await page.goto("/dashboard");
    await page.keyboard.press("Control+k");
    const chip = page.getByRole("button", { name: "settings", exact: true });
    await expect(chip).toBeVisible();
    await page.getByRole("button", { name: "Clear" }).click();
    await expect(chip).toHaveCount(0);
    const stored = await page.evaluate(() =>
      localStorage.getItem("aion-recent-searches"),
    );
    expect(stored).toBeNull();
  });

  test('"This page" scope filters the live task list without a server call', async ({
    page,
    request,
  }) => {
    await resetState(request);
    const seeded = await (
      await request.post(`${API}/api/_test/seed/task`, {
        data: { title: "thispage-scoped-task", status: "pending" },
      })
    ).json();
    const firstTitle = seeded.title as string;

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
    await resetState(request);
    const seeded = await (
      await request.post(`${API}/api/_test/seed/conversation`, {
        data: {
          user_message: "deep-link-probe-message",
          assistant_message: "acknowledged",
        },
      })
    ).json();
    const convoId = seeded.conversation_id as string;
    const messages = await (
      await request.get(`${API}/api/conversations/${convoId}/messages`)
    ).json();
    expect(messages.length, "Fixture must produce at least one message").toBeGreaterThan(0);
    const text: string = messages[0].content;

    await page.goto(`/chat?c=${convoId}`);
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
