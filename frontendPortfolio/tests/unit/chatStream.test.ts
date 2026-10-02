import { describe, expect, it } from "vitest";
import { streamChatMessage, toChatStreamEvent } from "../../src/lib/api/chatStream";
import { ApiClient } from "../../src/lib/api/client";
import { ApiError, InvalidResponseError } from "../../src/lib/api/errors";
import { envelope, errorBody, FakeFetch, sseResponse } from "./support";

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
