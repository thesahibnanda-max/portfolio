import { expect, test } from "@playwright/test";
import { MockApi } from "./mockApi";

const RESUME_URL = /^http:\/\/localhost:8080\/details\/resume\?v=[0-9a-f]{16}$/;

test.beforeEach(async ({ page }) => {
  await new MockApi().install(page);
  await page.goto("/");
});

test("links the hero and contact résumé to the API", async ({ page }) => {
  const hero = page.locator("#top").getByRole("link", { name: "Résumé" });
  const contact = page.locator("#contact").getByRole("link", { name: /Résumé/ });

  await expect(hero).toHaveAttribute("href", RESUME_URL);
  await expect(contact).toHaveAttribute("href", RESUME_URL);
  await expect(hero).toHaveAttribute("target", "_blank");
  expect(await hero.getAttribute("href")).toBe(await contact.getAttribute("href"));
  expect(await page.locator('a[href*="supabase.co"][href$=".pdf"]').count()).toBe(0);
});

test("the résumé link serves a PDF", async ({ page, request }) => {
  const href = await page.locator("#top").getByRole("link", { name: "Résumé" }).getAttribute("href");
  expect(href).not.toBeNull();

  const response = await request.get(href ?? "");
  expect(response.ok()).toBe(true);
  expect(response.headers()["content-type"]).toBe("application/pdf");
  expect((await response.body()).subarray(0, 5).toString()).toBe("%PDF-");
});
