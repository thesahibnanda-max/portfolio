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
  await expect(options).toHaveCount(18);
  await expect(options.filter({ hasText: "/go-back" })).toHaveCount(1);
  await expect(options.filter({ hasText: "/config" })).toHaveCount(1);

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
  await type(page, "/stats");
  await expect(log(page)).toContainText("Codeforces · shisukenohara");
  for (const command of ["/experience", "/projects", "/skills"]) {
    await type(page, command);
  }
  await expect(log(page)).toContainText("Distributed Systems");

  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBe(0);
  if ((page.viewportSize()?.width ?? 0) < 768) {
    await page.getByRole("navigation", { name: "Quick commands" }).getByRole("button", { name: "/resume" }).click();
    await expect(log(page)).toContainText("Opening the résumé");
  }
});

test("/config changes settings from the keyboard and they reach the agent", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard panel; touch uses tap");
  const api = await openCli(page);

  await type(page, "/config");
  const panel = page.getByRole("listbox", { name: "Settings" });
  await expect(panel).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("option", { selected: true })).toContainText("detailed");
  await page.keyboard.press("Escape");
  await expect(log(page)).toContainText("Settings saved for this browser.");

  await type(page, "/config accent blue");
  await expect(log(page)).toContainText("Accent colour set to blue.");
  expect(
    await page.locator("[data-terminal]").evaluate((element) => element.style.getPropertyValue("--color-accent")),
  ).toBe("#60a5fa");

  await type(page, "who is he?");
  await expect(log(page)).toContainText(/1 AI call/);
  expect(api.agentBodies.at(-1)).toMatchObject({ style: "detailed", mode: "answer" });
});

test("plugins add and remove skills", async ({ page }) => {
  await openCli(page);

  await type(page, "/plugins disable stats");
  await expect(log(page)).toContainText("Plugin stats disabled.");
  await page.locator("#term-input").fill("/st");
  await expect(page.getByRole("listbox", { name: "Suggestions" }).getByRole("option")).not.toContainText(["/stats"]);
  await type(page, "/stats");
  await expect(log(page)).toContainText("part of the stats plugin, which is off");

  await type(page, "/plugins enable extras");
  await type(page, "/neofetch");
  await expect(log(page)).toContainText("sahib@portfolio");
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBe(0);
});

test("Shift+Tab cycles default, auto-run and plan modes", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard shortcut; phones use the mode chip");
  await openCli(page);
  const indicator = page.locator("[data-mode-indicator]");

  await page.keyboard.press("Shift+Tab");
  await expect(indicator).toContainText("⏵⏵ auto-run on");
  await page.keyboard.press("Shift+Tab");
  await expect(indicator).toContainText("⏸ plan mode on");
  await page.keyboard.press("Shift+Tab");
  await expect(indicator).toHaveCount(0);
});

test("plan mode shows the plan and runs it on Enter", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard flow");
  const api = await openCli(page);
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Shift+Tab");

  await type(page, "show me his backend work");

  await expect(log(page)).toContainText("Plan(terminal commands)");
  await expect(log(page).locator("[data-plan]")).toContainText("/projects relay");
  await expect(page.locator("[data-plan-prompt]")).toBeVisible();
  expect(api.agentBodies.at(-1)).toMatchObject({ mode: "plan" });

  await page.keyboard.press("Enter");
  await expect(log(page)).toContainText("You typed: /projects relay");
  await expect(log(page)).toContainText("You typed: /experience cred");
  await expect(log(page)).toContainText("Relay - Multi-Agent Collaboration for AI Coding CLIs");
  await expect(page.locator("[data-plan-prompt]")).toHaveCount(0);
});

test("plan mode can be cancelled with Escape", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard flow");
  await openCli(page);
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Shift+Tab");
  await type(page, "show me his backend work");
  await expect(page.locator("[data-plan-prompt]")).toBeVisible();

  await page.keyboard.press("Escape");

  await expect(log(page)).toContainText("Plan cancelled.");
  await expect(log(page)).not.toContainText("You typed: /projects relay");
});

test("auto-run mode runs the plan straight away", async ({ page }) => {
  await openCli(page);
  if ((page.viewportSize()?.width ?? 0) < 768) {
    await page.locator("[data-mode-chip]").click();
    await expect(page.locator("[data-mode-chip]")).toHaveText("mode: auto-run");
  } else {
    await page.keyboard.press("Shift+Tab");
  }

  await type(page, "show me his backend work");

  await expect(log(page)).toContainText("You typed: /experience cred");
  await expect(log(page)).toContainText("Relay - Multi-Agent Collaboration for AI Coding CLIs");
});

test("questions about the terminal itself go to the agent", async ({ page }) => {
  const api = await openCli(page, { agentAnswer: "There are **20 skills** in 5 plugins." });

  await type(page, "how many skills are in this cli?");

  await expect(log(page).locator("strong", { hasText: "20 skills" })).toBeVisible();
  expect(api.agentBodies.at(-1)).toMatchObject({ message: "how many skills are in this cli?", mode: "answer" });
  await expect(log(page)).toContainText("18 of 20 skills on");
});
