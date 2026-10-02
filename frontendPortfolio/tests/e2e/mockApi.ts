import type { Page, Route } from "@playwright/test";

const API = /^http:\/\/localhost:8080/;
const NOW = "2026-10-02T00:00:00Z";

export type ContactBehaviour = "sent" | "invalid-email" | "rate-limited" | "unavailable";

export interface MockOptions {
  readonly contact?: ContactBehaviour;
  readonly expireFirstSession?: boolean;
  readonly rateLimitStream?: boolean;
  readonly holdStream?: boolean;
}

function envelope(data: unknown, status = 200) {
  return JSON.stringify({ status, timestamp: NOW, data });
}

function session(id: string) {
  return { session_id: id, created_at: NOW, expires_at: "2099-01-01T00:00:00Z" };
}

function chat(id: string) {
  return { chat_id: id, title: "What's his Codeforces peak rating?", created_at: NOW, updated_at: NOW };
}

function streamBody(chatId: string): string {
  const reply = {
    chat: { ...chat(chatId), messages: [] },
    answer: "His **Codeforces peak** is 1987.",
    scope: "IN_SCOPE",
    required_contexts: ["CODEFORCES"],
  };
  return [
    'event: token\ndata: {"text":"His **Codeforces peak** "}\n\n',
    'event: token\ndata: {"text":"is 1987."}\n\n',
    `event: done\ndata: ${envelope(reply)}\n\n`,
  ].join("");
}

export class MockApi {
  readonly sessionsCreated: string[] = [];
  readonly streamSessions: string[] = [];
  readonly contactBodies: unknown[] = [];
  #releaseStream: (() => void) | null = null;

  constructor(private readonly options: MockOptions = {}) {}

  async install(page: Page): Promise<void> {
    await page.route(API, (route) => this.#handle(route));
  }

  releaseStream(): void {
    this.#releaseStream?.();
  }

  async #handle(route: Route): Promise<void> {
    const request = route.request();
    const url = new URL(request.url());
    const sessionId = request.headers()["x-session-id"] ?? "";

    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders() });
      return;
    }
    if (url.pathname === "/sessions") {
      const id = `session-${this.sessionsCreated.length + 1}`;
      this.sessionsCreated.push(id);
      await json(route, 201, envelope(session(id), 201));
      return;
    }
    if (url.pathname === "/chats" && request.method() === "POST") {
      await json(route, 201, envelope(chat(`chat-for-${sessionId}`), 201));
      return;
    }
    if (url.pathname === "/chats" && request.method() === "GET") {
      await json(route, 200, envelope({ chats: [] }));
      return;
    }
    if (url.pathname.endsWith("/messages/stream")) {
      await this.#stream(route, sessionId, url.pathname.split("/")[2] ?? "");
      return;
    }
    if (url.pathname === "/contact") {
      await this.#contact(route);
      return;
    }
    if (url.pathname.startsWith("/details/")) {
      await json(route, 200, envelope({ accounts: [] }));
      return;
    }
    if (url.pathname === "/health") {
      await json(route, 200, envelope({ status: "UP" }));
      return;
    }
    await route.fulfill({ status: 404, headers: corsHeaders(), body: "unmocked" });
  }

  async #contact(route: Route): Promise<void> {
    this.contactBodies.push(route.request().postDataJSON());
    switch (this.options.contact ?? "sent") {
      case "sent":
        await json(route, 200, envelope({ status: "SENT", reply_to: "visitor@example.com", sent_at: NOW }));
        return;
      case "invalid-email":
        await json(
          route,
          400,
          JSON.stringify({
            status: 400,
            timestamp: NOW,
            error: "VALIDATION_ERROR",
            message: "invalid",
            details: [{ field: "body.email", message: "That address bounced on the server." }],
          }),
        );
        return;
      case "rate-limited":
        await route.fulfill({
          status: 429,
          contentType: "application/json",
          headers: { ...corsHeaders(), "Retry-After": "1800" },
          body: errorBody(429, "RATE_LIMITED"),
        });
        return;
      case "unavailable":
        await json(route, 503, errorBody(503, "MAIL_UNAVAILABLE"));
        return;
    }
  }

  async #stream(route: Route, sessionId: string, chatId: string): Promise<void> {
    this.streamSessions.push(sessionId);
    if (this.options.expireFirstSession === true && sessionId === "session-1") {
      await json(route, 401, errorBody(401, "SESSION_EXPIRED"));
      return;
    }
    if (this.options.rateLimitStream === true) {
      await route.fulfill({
        status: 429,
        contentType: "application/json",
        headers: { ...corsHeaders(), "Retry-After": "42" },
        body: errorBody(429, "RATE_LIMITED"),
      });
      return;
    }
    if (this.options.holdStream === true) {
      await new Promise<void>((resolve) => {
        this.#releaseStream = resolve;
      });
    }
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: corsHeaders(),
      body: streamBody(chatId),
    });
  }
}

function errorBody(status: number, error: string): string {
  return JSON.stringify({ status, timestamp: NOW, error, message: error, details: [] });
}

function corsHeaders(): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "*",
    "Access-Control-Expose-Headers": "Retry-After",
  };
}

async function json(route: Route, status: number, body: string): Promise<void> {
  await route.fulfill({ status, contentType: "application/json", headers: corsHeaders(), body });
}
