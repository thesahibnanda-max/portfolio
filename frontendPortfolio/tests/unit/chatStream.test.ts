import { describe, expect, it } from "vitest";
import { ChatApi } from "../../src/lib/api/chatApi";
import { streamAgentMessage, streamChatMessage, toChatStreamEvent } from "../../src/lib/api/chatStream";
import { ApiClient } from "../../src/lib/api/client";
import { ApiError, InvalidResponseError } from "../../src/lib/api/errors";
import { SessionStore } from "../../src/lib/api/session";
import { envelope, errorBody, FakeFetch, jsonResponse, MemoryStorage, sseResponse } from "./support";

const reply = {
  chat: { chat_id: "c", title: "t", created_at: "x", updated_at: "x", messages: [] },
  answer: "He has a 1832 rating.",
  scope: "IN_SCOPE",
  required_contexts: ["CODEFORCES"],
};

async function collect(chunks: readonly string[]) {
  const fake = new FakeFetch([sseResponse(chunks)]);
  const events = [];
  for await (const event of streamChatMessage(new ApiClient("http://api.test", fake.fetch), "s", "c", "hi")) {
    events.push(event);
  }
  return { events, fake };
}

describe("streamChatMessage", () => {
  it("yields tokens then the validated done reply, across chunk boundaries", async () => {
    const done = JSON.stringify(envelope(reply));
    const { events, fake } = await collect([
      'event: token\ndata: {"text":"He has "}\n\n: ping\n\nevent: tok',
      'en\ndata: {"text":"a 1832 rating."}\n\n',
      `event: done\ndata: ${done.slice(0, 20)}`,
      `${done.slice(20)}\n\n`,
    ]);

    expect(events.map((event) => event.type)).toEqual(["token", "token", "done"]);
    expect(events[2]).toMatchObject({
      type: "done",
      reply: { answer: reply.answer, required_contexts: ["CODEFORCES"] },
    });
    expect(fake.requests[0]?.url).toBe("http://api.test/chats/c/messages/stream");
    expect(fake.requests[0]?.init?.body).toBe('{"message":"hi"}');
  });

  it("surfaces a mid-stream error event as an ApiError", async () => {
    const { events } = await collect([
      'event: token\ndata: {"text":"Part"}\n\n',
      `event: error\ndata: ${JSON.stringify(errorBody(502, "UPSTREAM_ERROR"))}\n\n`,
    ]);

    const last = events.at(-1);
    expect(last?.type).toBe("error");
    expect(last?.type === "error" && last.error).toBeInstanceOf(ApiError);
  });

  it("fails loudly when the stream ends without done or error", async () => {
    await expect(collect(['event: token\ndata: {"text":"Part"}\n\n'])).rejects.toBeInstanceOf(InvalidResponseError);
  });

  it("rejects malformed events instead of rendering garbage", () => {
    expect(() => toChatStreamEvent("token", "{nope")).toThrow(InvalidResponseError);
    expect(() => toChatStreamEvent("token", '{"text": 5}')).toThrow(InvalidResponseError);
    expect(toChatStreamEvent("unknown", "{}")).toBeNull();
  });
});

describe("streamAgentMessage", () => {
  it("yields steps before tokens and posts to the agent route", async () => {
    const fake = new FakeFetch([
      sseResponse([
        'event: step\ndata: {"label":"Reading profile · github"}\n\n',
        'event: token\ndata: {"text":"Hi"}\n\n',
        `event: done\ndata: ${JSON.stringify(envelope(reply))}\n\n`,
      ]),
    ]);
    const events = [];
    for await (const event of streamAgentMessage(new ApiClient("http://api.test", fake.fetch), "s", "c 1", "hi")) {
      events.push(event);
    }

    expect(events.map((event) => event.type)).toEqual(["step", "token", "done"]);
    expect(events[0]).toEqual({ type: "step", label: "Reading profile · github" });
    expect(fake.requests[0]?.url).toBe("http://api.test/chats/c%201/agent/stream");
  });

  it("hides step events from the chat stream", async () => {
    const { events } = await collect([
      'event: step\ndata: {"label":"Reading"}\n\n',
      `event: done\ndata: ${JSON.stringify(envelope(reply))}\n\n`,
    ]);

    expect(events.map((event) => event.type)).toEqual(["done"]);
  });

  it("rejects an invalid step", () => {
    expect(() => toChatStreamEvent("step", '{"label":""}')).toThrow(InvalidResponseError);
  });
});

describe("ChatApi origin", () => {
  it("creates chats with their origin and reads it back", async () => {
    const summary = { chat_id: "c", title: "t", created_at: "x", updated_at: "x", origin: "cli" };
    const fake = new FakeFetch([
      jsonResponse(201, envelope(summary, 201)),
      jsonResponse(201, envelope({ ...summary, origin: undefined }, 201)),
    ]);
    const storage = new MemoryStorage();
    storage.setItem(
      "portfolio.session",
      JSON.stringify({ session_id: "s", created_at: "x", expires_at: "2099-01-01T00:00:00Z" }),
    );
    const client = new ApiClient("http://api.test", fake.fetch);
    const api = new ChatApi(client, new SessionStore(client, storage));

    expect((await api.createChat("Terminal", "cli")).origin).toBe("cli");
    expect((await api.createChat()).origin).toBe("chat");
    expect(JSON.parse(String(fake.requests[0]?.init?.body))).toEqual({ title: "Terminal", origin: "cli" });
    expect(JSON.parse(String(fake.requests[1]?.init?.body))).toEqual({ origin: "chat" });
  });
});
