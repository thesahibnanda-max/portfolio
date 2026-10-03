import { expect, type Page, test } from "@playwright/test";
import { type ContactBehaviour, MockApi } from "./mockApi";

async function openForm(page: Page, behaviour: ContactBehaviour = "sent"): Promise<MockApi> {
  const api = new MockApi({ contact: behaviour });
  await api.install(page);
  await page.goto("/");
  await page.locator("#contact").scrollIntoViewIfNeeded();
  return api;
}

async function fill(page: Page, email = "visitor@example.com"): Promise<void> {
  await page.getByLabel("Your email").fill(email);
  await page.getByLabel("Subject").fill("Backend role");
  await page.getByLabel("Message", { exact: true }).fill("We'd love to talk about a distributed systems role.");
}

test("sends the message, announces it and resets the form", async ({ page }) => {
  const api = await openForm(page);
  await fill(page);
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.getByRole("status").filter({ hasText: "Message sent" })).toContainText("visitor@example.com");
  await expect(page.getByLabel("Message", { exact: true })).toHaveValue("");
  expect(api.contactBodies).toEqual([
    {
      email: "visitor@example.com",
      subject: "Backend role",
      message: "We'd love to talk about a distributed systems role.",
    },
  ]);
});

test("validates on the client before sending", async ({ page }) => {
  const api = await openForm(page);
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.getByLabel("Your email")).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByLabel("Your email")).toBeFocused();
  await expect(page.locator('[data-field-error="message"]')).toHaveText("Write a message.");
  expect(api.contactBodies).toEqual([]);
});

test("marks the field the server rejected", async ({ page }) => {
  await openForm(page, "invalid-email");
  await fill(page);
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.locator('[data-field-error="email"]')).toHaveText("That address bounced on the server.");
  await expect(page.getByLabel("Your email")).toHaveAttribute("aria-invalid", "true");
});

test("counts down when rate limited", async ({ page }) => {
  await openForm(page, "rate-limited");
  await fill(page);
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.locator("[data-contact-status]")).toContainText(/send again in 1[78]\d\ds/);
  await expect(page.getByRole("button", { name: "Send message" })).toBeDisabled();
});

test("falls back to email when mail is unavailable", async ({ page }) => {
  await openForm(page, "unavailable");
  await fill(page);
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.locator("[data-contact-status]")).toContainText("email me directly");
  await expect(page.getByLabel("Message", { exact: true })).not.toHaveValue("");
});

test("sends a normalized email and has no honeypot field", async ({ page }) => {
  const api = await openForm(page);
  await fill(page, "  Visitor@Example.COM ");
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.getByRole("status").filter({ hasText: "Message sent" })).toContainText("visitor@example.com");
  expect(api.contactBodies).toEqual([expect.objectContaining({ email: "visitor@example.com" })]);
  await expect(page.locator('[name="website"]')).toHaveCount(0);
});

test("lists profiles and the résumé but not the outdated website", async ({ page }) => {
  await new MockApi().install(page);
  await page.goto("/");
  const contact = page.locator("#contact");

  for (const label of ["GitHub", "LinkedIn", "X", "LeetCode", "Codeforces", "Résumé"]) {
    await expect(contact.getByRole("link", { name: new RegExp(`^${label}(\\s|$)`) })).toHaveCount(1);
  }
  await expect(contact.getByRole("link", { name: /Website/ })).toHaveCount(0);
  await expect(page.locator('a[href*="sahib-nanda-portfolio.vercel.app"]')).toHaveCount(0);
});
