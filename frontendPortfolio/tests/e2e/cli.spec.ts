import { expect, type Page, test } from "@playwright/test";
import { MockApi, type MockOptions, seedSession } from "./mockApi";

async function openCli(page: Page, options: MockOptions = {}, path = "/cli"): Promise<MockApi> {
  const api = new MockApi(options);
  await api.install(page);
  await page.goto(path);
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

  await expect(page).toHaveURL(/\/cli\/?$/);
  await expect(log(page)).toContainText("Welcome to");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Portfolio Agent CLI/);
});

test("a bare slash lists every command and Tab then Enter runs the overview", async ({ page }) => {
  await openCli(page);
  const input = page.locator("#term-input");

  await input.fill("/");
  const options = page.getByRole("listbox", { name: "Suggestions" }).getByRole("option");
  await expect(options).toHaveCount(16);
  await expect(options.last()).toContainText("/go-back");

  await input.fill("/ex");
  await page.keyboard.press("Tab");
  await expect(input).toHaveValue("/experience ");
  await page.keyboard.press("Enter");

  await expect(log(page)).toContainText("Experience (8 roles)");
  await expect(log(page)).toContainText("Details: /experience <company>");
});

test("arguments complete from the data and the highlighted one runs after arrow keys", async ({ page }) => {
  await openCli(page);
  const input = page.locator("#term-input");

  await input.fill("/projects rel");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Enter");

  await expect(input).toHaveValue("");
  await expect(log(page)).toContainText("/projects Relay - Multi-Agent Collaboration for AI Coding CLIs");
  await expect(log(page).getByRole("link", { name: "https://relay-sahib-nanda.vercel.app" })).toBeVisible();
});

test("slash commands answer instantly without calling the AI", async ({ page }) => {
  const api = await openCli(page);

  await type(page, "/experience cred");
  await expect(log(page)).toContainText("CRED");
  await type(page, "/whoami");
  await expect(log(page)).toContainText("GitHub 2");
  await type(page, "/projx");
  await expect(log(page)).toContainText("Did you mean /projects [name]?");
  await page.keyboard.press("Control+l");
  await expect(log(page)).not.toContainText("CRED");

  expect(api.agentQuestions).toEqual([]);
});

test("a question shows the tool call, the answer and its cost", async ({ page }) => {
  const api = await openCli(page);

  await type(page, "who is he?");

  await expect(log(page)).toContainText("Read(profile · github)");
  await expect(log(page).locator("strong", { hasText: "backend engineer" })).toBeVisible();
  await expect(log(page)).toContainText(/1 AI call · \d+\.\ds/);
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

test("a rate-limited first question leaves no empty conversation behind", async ({ page }) => {
  const api = await openCli(page, { rateLimitAgent: true });

  await type(page, "who is he?");
  await expect(log(page)).toContainText("rate limited · retry in 42s");
  await expect(page.getByText(/^rate limited · \d+s$/)).toBeVisible();
  await expect.poll(() => api.deletedChats).toEqual(["cli-chat-for-session-1"]);

  await type(page, "another question");
  await expect(log(page)).toContainText("The agent is rate limited for");
  await type(page, "/skills");
  await expect(log(page)).toContainText("Distributed Systems");
});

test("the input grows with a long question", async ({ page }) => {
  await openCli(page);
  const input = page.locator("#term-input");
  const oneLine = (await input.boundingBox())?.height ?? 0;

  await input.fill("tell me about ".repeat(30));

  expect((await input.boundingBox())?.height ?? 0).toBeGreaterThan(oneLine * 2);
});

test("history lists CLI conversations and reopens one", async ({ page }) => {
  await openCli(page);
  await type(page, "who is he?");
  await expect(log(page)).toContainText(/1 AI call/);

  await type(page, "/history");
  await expect(log(page)).toContainText("Earlier terminal chat");
  await type(page, "/open 1");

  await expect(log(page)).toContainText("Who is he?");
  await expect(log(page).locator("strong", { hasText: "backend" })).toBeVisible();
});

test("a terminal conversation picked in the chat history opens in the terminal", async ({ page }) => {
  await seedSession(page);
  await new MockApi({ seedHistory: true }).install(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Ask my AI anything" }).click();
  const dialog = page.getByRole("dialog", { name: /Ask about/ });
  await dialog.getByRole("button", { name: "Chat history" }).click();
  await dialog.getByRole("link", { name: /Earlier terminal chat/ }).click();

  await expect(page).toHaveURL(/\/cli\/?$/);
  await expect(log(page)).toContainText("Earlier terminal chat");
  await expect(log(page)).toContainText("Who is he?");
});

test("/go-back returns to the portfolio", async ({ page }) => {
  await openCli(page);
  await type(page, "/go-back");

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Sahib");
});

test("fits the screen without horizontal scrolling", async ({ page }) => {
  await openCli(page);
  for (const command of ["/stats", "/experience", "/projects", "/skills"]) {
    await type(page, command);
  }
  await expect(log(page)).toContainText("Distributed Systems");

  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBe(0);
  if ((page.viewportSize()?.width ?? 0) < 768) {
    await page.getByRole("navigation", { name: "Quick commands" }).getByRole("button", { name: "/resume" }).click();
    await expect(log(page)).toContainText("Opening the résumé");
  }
});
