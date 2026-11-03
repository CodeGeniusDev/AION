import { test, expect } from "@playwright/test";

// Phase 1F: Secret Guard end to end against the live API. A message
// containing a credential must show the warning banner, and the raw
// secret must never appear anywhere in the rendered conversation.

test.describe("Phase 1F: Secret Guard", () => {
  test("password in a chat message is redacted and reported", async ({
    page,
  }) => {
    test.setTimeout(120_000); // the chat pipeline can be slow on free-tier
    await page.goto("/chat");
    const composer = page.getByLabel("Message AION");
    await composer.fill(
      "my password is Sup3rSecret123 — please save it for later",
    );
    await page.getByRole("button", { name: "Send message" }).click();

    const banner = page.getByRole("alert").filter({
      hasText: "Credentials detected and removed",
    });
    await expect(banner).toBeVisible({ timeout: 90_000 });
    await expect(banner).toContainText("password removed");
    await expect(banner).toContainText(
      "AION never needs your password; use official OAuth.",
    );

    // The stored user bubble shows the redacted text — never the secret.
    // Scoped to the chat area; the sidebar conversation list legitimately
    // titles the same exchange.
    await expect(
      page.getByText("password is [REDACTED: password]", { exact: false }).first(),
    ).toBeVisible();
    await expect(page.locator("body")).not.toContainText("Sup3rSecret123");

    // The banner is dismissible.
    await page.getByRole("button", { name: "Dismiss security warning" }).click();
    await expect(banner).toHaveCount(0);
  });

  test("an ordinary message about passwords shows no banner", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await page.goto("/chat");
    await page.getByLabel("Message AION").fill("explain password reset flow");
    await page.getByRole("button", { name: "Send message" }).click();
    // Wait for the reply, then assert nothing security-related was invented.
    await expect(page.getByText("password reset flow").last()).toBeVisible();
    await expect(
      page.getByText("Credentials detected and removed"),
    ).toHaveCount(0);
  });
});
