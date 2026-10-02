import { expect, test } from "@playwright/test";
import { MockApi } from "./mockApi";

const SECTIONS = [
  "top",
  "experience",
  "projects",
  "competitive",
  "open-source",
  "skills",
  "achievements",
  "off-the-clock",
  "contact",
];

test("renders every section without console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(message.text());
    }
  });
  await new MockApi().install(page);
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1 })).toContainText("Sahib");
  for (const id of SECTIONS) {
    await expect(page.locator(`#${id}`)).toBeAttached();
  }
  await expect(page.locator("body")).not.toContainText("physical");
  await expect(page.getByText("API status: operational")).toBeAttached();
  expect(errors).toEqual([]);
});

test("shows only the primary GitHub in contact links", async ({ page }) => {
  await new MockApi().install(page);
  await page.goto("/");
  const contactLinks = page.locator("#contact ul a");
  await expect(contactLinks.filter({ hasText: "GitHub" })).toHaveCount(1);
});

test("streams an answer with source chips from the palette", async ({ page }) => {
  const api = new MockApi();
  await api.install(page);
  await page.goto("/");

  await page.keyboard.press("ControlOrMeta+k");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "What's his Codeforces peak rating?" }).click();

  await expect(dialog.locator('[data-streamdown="strong"]', { hasText: "Codeforces peak" })).toBeVisible();
  await expect(dialog.getByText("is 1987.")).toBeVisible();
  await expect(dialog.getByRole("list", { name: "Sources used" })).toContainText("codeforces");
  expect(api.sessionsCreated).toHaveLength(1);
});

test("renews an expired session and retries once", async ({ page }) => {
  const api = new MockApi({ expireFirstSession: true });
  await api.install(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Ask my AI anything" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Your question").fill("Codeforces?");
  await dialog.getByLabel("Your question").press("Enter");

  await expect(dialog.getByText("is 1987.")).toBeVisible();
  expect(api.streamSessions).toEqual(["session-1", "session-2"]);
});

test("shows a countdown when rate limited", async ({ page }) => {
  await new MockApi({ rateLimitStream: true }).install(page);
  await page.goto("/");

  await page.keyboard.press("ControlOrMeta+k");
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Your question").fill("hi");
  await dialog.getByRole("button", { name: "Send" }).click();

  await expect(dialog.getByRole("status")).toContainText(/ask again in 4[12]s/);
  await expect(dialog.getByRole("button", { name: "Retry" })).toBeDisabled();
  await expect(dialog.getByText("failed · not saved")).toBeVisible();
});

test("stop aborts a running answer and Escape closes the chat", async ({ page }) => {
  const api = new MockApi({ holdStream: true });
  await api.install(page);
  await page.goto("/");

  await page.keyboard.press("ControlOrMeta+k");
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Your question").fill("hi");
  await dialog.getByLabel("Your question").press("Enter");
  await dialog.getByRole("button", { name: "Stop generating" }).click();

  await expect(dialog.getByText("stopped · not saved")).toBeVisible();
  api.releaseStream();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("shows content immediately without animation", async ({ page }) => {
    await new MockApi().install(page);
    await page.goto("/");
    await expect(page.locator("html")).toHaveClass(/reduced-motion/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveCSS("opacity", "1");
    await expect(page.locator("html")).not.toHaveClass(/lenis/);
  });
});
