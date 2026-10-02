import { describe, expect, it } from "vitest";
import { ApiError, NetworkError } from "../../src/lib/api/errors";
import { type ChatState, chatReducer, initialChatState } from "../../src/lib/chat/chatState";
import { chatTitleFrom, noticeFor } from "../../src/lib/chat/notices";

function started(state: ChatState = initialChatState): ChatState {
  return chatReducer(state, { type: "send-started", userId: "u1", assistantId: "a1", text: "rating?" });
}

describe("chatReducer", () => {
  it("streams tokens into the assistant message and completes it", () => {
    let state = started();
    state = chatReducer(state, { type: "token-received", assistantId: "a1", text: "He has " });
    state = chatReducer(state, { type: "token-received", assistantId: "a1", text: "1832." });
    expect(state.messages[1]).toMatchObject({ content: "He has 1832.", status: "streaming" });

    state = chatReducer(state, {
      type: "answer-completed",
      assistantId: "a1",
      answer: "He has 1832.",
      scope: "IN_SCOPE",
      contexts: ["CODEFORCES"],
    });
    expect(state.isStreaming).toBe(false);
    expect(state.messages[1]).toMatchObject({ status: "complete", contexts: ["CODEFORCES"], scope: "IN_SCOPE" });
  });

  it("marks stopped and failed turns, and discards them for a retry", () => {
    const stopped = chatReducer(started(), { type: "answer-stopped", assistantId: "a1" });
    expect(stopped.messages[1]?.status).toBe("stopped");

    const failed = chatReducer(started(), { type: "answer-failed", assistantId: "a1", notice: { kind: "chat-full" } });
    expect(failed).toMatchObject({ isStreaming: false, notice: { kind: "chat-full" } });

    const discarded = chatReducer(failed, { type: "turn-discarded", userId: "u1", assistantId: "a1" });
    expect(discarded.messages).toEqual([]);
    expect(discarded.notice).toBeNull();
  });

  it("forgets the open chat when it is deleted", () => {
    let state = chatReducer(initialChatState, { type: "chat-created", chatId: "c1" });
    state = chatReducer(state, {
      type: "history-loaded",
      chats: [{ chat_id: "c1", title: "t", created_at: "x", updated_at: "x" }],
    });
    state = chatReducer(state, { type: "chat-removed", chatId: "c1" });
    expect(state).toMatchObject({ chatId: null, history: [], messages: [] });
  });
});

describe("noticeFor", () => {
  const apiError = (status: number, code: string, retry: number | null = null) =>
    new ApiError({ status, timestamp: "", error: code, message: "server says", details: [] }, retry);

  it("maps backend codes to friendly notices", () => {
    expect(noticeFor(apiError(429, "RATE_LIMITED", 9), 1000)).toEqual({ kind: "rate-limited", until: 10_000 });
    expect(noticeFor(apiError(409, "CHAT_FULL"), 0)).toEqual({ kind: "chat-full" });
    expect(noticeFor(apiError(400, "VALIDATION_ERROR"), 0)).toEqual({ kind: "error", message: "server says" });
    expect(noticeFor(apiError(503, "UPSTREAM_BUSY"), 0).kind).toBe("error");
    expect(noticeFor(new NetworkError("down"), 0)).toMatchObject({ kind: "error" });
  });
});

describe("chatTitleFrom", () => {
  it("collapses whitespace and truncates long questions", () => {
    expect(chatTitleFrom("  what   is\nhis rating?  ")).toBe("what is his rating?");
    expect(chatTitleFrom("x".repeat(100))).toHaveLength(60);
  });
});
