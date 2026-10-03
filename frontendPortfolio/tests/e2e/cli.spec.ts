import { expect, type Page, test } from "@playwright/test";
import { MockApi, type MockOptions } from "./mockApi";

async function openCli(page: Page, options: MockOptions = {}): Promise<MockApi> {
  const api = new MockApi(options);
  await api.install(page);
  await page.goto("/cli");
  await expect(page.locator("#term-input")).toBeFocused();
  return api;
}

async function type(page: Page, text: string): Promise<void> {
  await page.locator("#term-input").fill(text);
  await page.keyboard.press("Enter");
}

const log = (page: Page) => page.getByRole("log", { name: "Terminal output" });

test("opens from the chat panel's Portfolio Agent CLI button", async ({ page }) => {
  await new MockApi().install(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Ask my AI anything" }).click();
  await page
    .getByRole("dialog")
    .getByRole("link", { name: /Portfolio Agent CLI/ })
    .click();

  await expect(page).toHaveURL(/\/cli$/);
  await expect(page.getByText("Welcome to")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("@portfolio: ~/agent");
});

test("the slash menu completes commands and arguments from the keyboard", async ({ page }) => {
  await openCli(page);
  const input = page.locator("#term-input");

  await input.pressSequentially("/pro");
  const menu = page.getByRole("listbox", { name: "Suggestions" });
  await expect(menu.getByRole("option").first()).toContainText("/projects [name]");
  await page.keyboard.press("Tab");
  await expect(input).toHaveValue("/projects ");

  await input.pressSequentially("relay");
  await expect(menu.getByRole("option").first()).toContainText("Relay");
  await page.keyboard.press("Enter");

  await expect(input).toHaveValue("");
  await expect(log(page)).toContainText("You typed: /projects Relay - Multi-Agent Collaboration for AI Coding CLIs");
  await expect(log(page).getByRole("link", { name: "https://relay-sahib-nanda.vercel.app" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Technologies" }).last()).toBeVisible();
});

test("slash commands answer instantly without calling the AI", async ({ page }) => {
  const api = await openCli(page);

  await type(page, "/experience cred");
  await expect(log(page)).toContainText("CRED");
  await type(page, "/whoami");
  await expect(log(page)).toContainText("CheQ");
  await type(page, "/projx");
  await expect(log(page)).toContainText("Did you mean /projects [name]?");
  await page.keyboard.press("Control+l");
  await expect(log(page)).not.toContainText("CheQ");

  expect(api.agentQuestions).toEqual([]);
});

test("a question streams steps and a markdown answer from the agent", async ({ page }) => {
  const api = await openCli(page);

  await type(page, "who is he?");

  await expect(log(page)).toContainText("Reading profile · github");
  await expect(log(page).locator("strong", { hasText: "backend engineer" })).toBeVisible();
  await expect(log(page)).toContainText(/answered in \d+\.\d+s/);
  await expect(page.getByText("agent online")).toBeVisible();
  expect(api.agentQuestions).toEqual(["who is he?"]);
  expect(api.createdChats).toEqual([{ title: "who is he?", origin: "cli" }]);

  await type(page, "/ask and his stack?");
  await expect(log(page).locator("strong", { hasText: "backend engineer" })).toHaveCount(2);
  expect(api.createdChats).toHaveLength(1);
});

test("Escape interrupts a running answer", async ({ page }) => {
  const api = await openCli(page, { holdStream: true });

  await type(page, "tell me everything");
  await expect(log(page)).toContainText("esc to interrupt");
  await page.keyboard.press("Escape");

  await expect(log(page)).toContainText("interrupted · not saved");
  await expect(page.locator("#term-input")).toBeFocused();
  api.releaseStream();
});

test("rate limits show a countdown while slash commands keep working", async ({ page }) => {
  await openCli(page, { rateLimitAgent: true });

  await type(page, "who is he?");
  await expect(log(page)).toContainText("rate limited · retry in 42s");
  await expect(page.getByText(/agent rate limited · \d+s/)).toBeVisible();

  await type(page, "another question");
  await expect(log(page)).toContainText("The agent is rate limited for");
  await type(page, "/skills");
  await expect(log(page)).toContainText("Distributed Systems");
});

test("history lists CLI conversations and reopens one", async ({ page }) => {
  await openCli(page);
  await type(page, "who is he?");
  await expect(log(page)).toContainText(/answered in/);

  await type(page, "/history");
  await expect(log(page)).toContainText("Earlier terminal chat");
  await expect(log(page)).toContainText("cli");
  await type(page, "/open 1");

  await expect(log(page)).toContainText("Who is he?");
  await expect(log(page).locator("strong", { hasText: "backend" })).toBeVisible();
});

test("/go-back returns to the portfolio", async ({ page }) => {
  await openCli(page);
  await type(page, "/go-back");

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Sahib");
});

test("fits the screen without horizontal scrolling", async ({ page }) => {
  await openCli(page);
  await type(page, "/stats");
  await expect(log(page)).toContainText("showing the snapshot");
  await expect(log(page)).toContainText("Codeforces · shisukenohara");
  await type(page, "/skills");
  await expect(log(page)).toContainText("Distributed Systems");

  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBe(0);
  if ((page.viewportSize()?.width ?? 0) < 768) {
    await page.getByRole("navigation", { name: "Quick commands" }).getByRole("button", { name: "/resume" }).click();
    await expect(log(page)).toContainText("Opening the résumé");
  }
});
