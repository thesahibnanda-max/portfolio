import { describe, expect, it } from "vitest";
import { ApiClient } from "../../src/lib/api/client";
import { ApiError } from "../../src/lib/api/errors";
import { SessionStore } from "../../src/lib/api/session";
import { envelope, FakeFetch, jsonResponse, MemoryStorage } from "./support";

const NOW = Date.parse("2026-10-02T00:00:00Z");

function session(id: string, expiresAt = "2026-10-02T12:00:00Z") {
  return { session_id: id, created_at: "2026-10-02T00:00:00Z", expires_at: expiresAt };
}

function store(responses: Response[], storage = new MemoryStorage()) {
  const fake = new FakeFetch(responses);
  return {
    fake,
    storage,
    sessions: new SessionStore(new ApiClient("http://api.test", fake.fetch), storage, () => NOW),
  };
}

describe("SessionStore", () => {
  it("creates a session once and reuses the stored one", async () => {
    const { fake, sessions } = store([jsonResponse(201, envelope(session("a"), 201))]);

    expect((await sessions.ensure()).session_id).toBe("a");
    expect((await sessions.ensure()).session_id).toBe("a");
    expect(fake.requests).toHaveLength(1);
  });

  it("creates only one session for concurrent callers", async () => {
    const { fake, sessions } = store([jsonResponse(201, envelope(session("a"), 201))]);

    const [first, second] = await Promise.all([sessions.ensure(), sessions.ensure()]);

    expect([first.session_id, second.session_id]).toEqual(["a", "a"]);
    expect(fake.requests).toHaveLength(1);
  });

  it("drops expired, corrupt or invalid stored sessions", () => {
    const storage = new MemoryStorage();
    const { sessions } = store([], storage);

    storage.setItem("portfolio.session", JSON.stringify(session("old", "2026-10-02T00:00:30Z")));
    expect(sessions.current()).toBeNull();
    storage.setItem("portfolio.session", "{not json");
    expect(sessions.current()).toBeNull();
    storage.setItem("portfolio.session", JSON.stringify({ session_id: 1 }));
    expect(sessions.current()).toBeNull();
    expect(storage.values.size).toBe(0);
  });

  it("renews once and retries when the server says the session expired", async () => {
    const { sessions } = store([
      jsonResponse(201, envelope(session("a"), 201)),
      jsonResponse(201, envelope(session("b"), 201)),
    ]);
    const seen: string[] = [];

    const result = await sessions.withSession(async (sessionId) => {
      seen.push(sessionId);
      if (sessionId === "a") {
        throw new ApiError(
          { status: 401, timestamp: "", error: "SESSION_EXPIRED", message: "gone", details: [] },
          null,
        );
      }
      return "ok";
    });

    expect(result).toBe("ok");
    expect(seen).toEqual(["a", "b"]);
  });

  it("does not retry other errors", async () => {
    const { sessions } = store([jsonResponse(201, envelope(session("a"), 201))]);
    const failure = new ApiError(
      { status: 404, timestamp: "", error: "CHAT_NOT_FOUND", message: "x", details: [] },
      null,
    );

    await expect(sessions.withSession(async () => Promise.reject(failure))).rejects.toBe(failure);
  });
});
