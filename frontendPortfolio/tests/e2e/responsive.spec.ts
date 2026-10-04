import { expect, test } from "@playwright/test";
import { MockApi } from "./mockApi";

test.beforeEach(async ({ page }) => {
  await new MockApi().install(page);
});

test("no section overflows its card on any screen", async ({ page }) => {
  await page.goto("/");

  const overflowing = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>("#competitive li, #open-source header")]
      .filter((element) => element.scrollWidth > element.clientWidth + 1)
      .map((element) => element.textContent?.trim().slice(0, 40)),
  );
  expect(overflowing).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBe(0);

  const firstChange = page.locator("#competitive ul li").first().locator("span").last();
  await firstChange.scrollIntoViewIfNeeded();
  await expect(firstChange).toBeInViewport();
});

test("the chat's empty state stays reachable on a small phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/");
  await page.getByRole("button", { name: "Ask my AI anything" }).click();
  const heading = page.getByRole("dialog").getByText("Hi, I'm");

  await heading.scrollIntoViewIfNeeded();
  await expect(heading).toBeInViewport();
  await expect(page.locator("#chat-input")).toBeFocused();
});

test("phones get a section menu and no keyboard hints", async ({ page, isMobile }) => {
  test.skip(!isMobile, "phone-only navigation");
  await page.goto("/");

  await expect(page.locator("nav kbd")).toBeHidden();
  await page.getByRole("button", { name: "Open the section menu" }).click();
  const sheet = page.getByRole("dialog", { name: "Sections" });
  await expect(sheet).toBeVisible();
  await sheet.getByRole("link", { name: "Work" }).click();

  await expect(sheet).toBeHidden();
  await expect(page).toHaveURL(/#projects$/);
});
