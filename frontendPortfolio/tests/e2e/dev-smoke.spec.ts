import { expect, test } from "@playwright/test";
import { MockApi } from "./mockApi";

test("the chat and the terminal load on the dev server", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(message.text());
    }
  });
  await new MockApi().install(page);

  await page.goto("/");
  await page.getByRole("button", { name: "Ask my AI anything" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible({ timeout: 30_000 });
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await page.keyboard.press("Control+k");
  await expect(dialog).toBeVisible();

  await page.goto("/cli");
  await expect(page.locator("#term-input")).toBeFocused({ timeout: 30_000 });
  expect(errors).toEqual([]);
});
