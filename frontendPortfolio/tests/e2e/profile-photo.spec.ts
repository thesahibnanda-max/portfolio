import { expect, test } from "@playwright/test";
import { MockApi } from "./mockApi";

test.beforeEach(async ({ page }) => {
  await new MockApi().install(page);
  await page.goto("/");
});

test("shows the profile photo in the hero without overflowing", async ({ page }) => {
  const portrait = page.getByRole("img", { name: "Sahib Nanda" });

  await expect(portrait).toBeVisible();
  await expect(portrait).toBeInViewport();
  expect(await portrait.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBe(0);
});

test("serves the photo from the site's own optimized assets", async ({ page }) => {
  const sources = await page
    .locator(".hero-portrait source")
    .evaluateAll((elements) =>
      elements.map((element) => `${element.getAttribute("type")} ${element.getAttribute("srcset")}`),
    );

  expect(sources.some((source) => source.startsWith("image/avif /_astro/"))).toBe(true);
  expect(sources.some((source) => source.startsWith("image/webp /_astro/"))).toBe(true);
  expect(await page.locator(".hero-portrait img").getAttribute("src")).toMatch(/^\/_astro\//);
});

test("places the photo beside the name on wide screens and above it on phones", async ({ page }) => {
  const portrait = await page.getByRole("img", { name: "Sahib Nanda" }).boundingBox();
  const heading = await page.getByRole("heading", { level: 1 }).boundingBox();
  const width = page.viewportSize()?.width ?? 0;

  expect(portrait).not.toBeNull();
  expect(heading).not.toBeNull();
  if (portrait === null || heading === null) {
    return;
  }
  if (width >= 768) {
    expect(portrait.x).toBeGreaterThan(heading.x + heading.width / 2);
  } else {
    expect(portrait.y + portrait.height).toBeLessThan(heading.y);
  }
});

test("uses the photo as the tab icon", async ({ page, request }) => {
  await expect(page.locator('link[rel="icon"]')).toHaveAttribute("href", "/favicon.png");
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute("href", "/apple-touch-icon.png");

  for (const path of ["/favicon.png", "/apple-touch-icon.png"]) {
    const response = await request.get(path);
    expect(response.ok()).toBe(true);
    expect((await response.body()).subarray(0, 8)).toEqual(
      Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    );
  }
});
