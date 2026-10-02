import { describe, expect, it } from "vitest";
import { z } from "zod";
import { ApiClient, parseRetryAfter, SESSION_HEADER } from "../../src/lib/api/client";
import { ApiError, InvalidResponseError, NetworkError } from "../../src/lib/api/errors";
import { envelope, errorBody, FakeFetch, jsonResponse } from "./support";

const healthSchema = z.object({ status: z.string() });

describe("ApiClient", () => {
  it("unwraps the envelope and validates the data", async () => {
    const fake = new FakeFetch([jsonResponse(200, envelope({ status: "UP" }))]);
    const client = new ApiClient("http://api.test/", fake.fetch);

    await expect(client.request("/health", healthSchema)).resolves.toEqual({ status: "UP" });
    expect(fake.requests[0]?.url).toBe("http://api.test/health");
  });

  it("sends JSON bodies and the session header", async () => {
    const fake = new FakeFetch([jsonResponse(201, envelope({ status: "UP" }, 201))]);
    await new ApiClient("http://api.test", fake.fetch).request("/chats", healthSchema, {
      method: "POST",
      body: { title: "x" },
      sessionId: "s-1",
    });

    const init = fake.requests[0]?.init;
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe('{"title":"x"}');
    expect(init?.headers).toEqual({ "Content-Type": "application/json", [SESSION_HEADER]: "s-1" });
  });

  it("rejects data that does not match the schema instead of trusting it", async () => {
    const fake = new FakeFetch([jsonResponse(200, envelope({ status: 5 }))]);

    await expect(new ApiClient("http://api.test", fake.fetch).request("/health", healthSchema)).rejects.toBeInstanceOf(
      InvalidResponseError,
    );
  });

  it("turns error envelopes into ApiError with the retry hint", async () => {
    const fake = new FakeFetch([jsonResponse(429, errorBody(429, "RATE_LIMITED"), { "Retry-After": "7" })]);

    const error = await new ApiClient("http://api.test", fake.fetch)
      .request("/x", healthSchema)
      .catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 429, code: "RATE_LIMITED", retryAfterSeconds: 7, isRateLimited: true });
  });

  it("keeps a usable ApiError when the error body is not JSON", async () => {
    const fake = new FakeFetch([new Response("gateway down", { status: 502, statusText: "Bad Gateway" })]);

    const error = await new ApiClient("http://api.test", fake.fetch)
      .request("/x", healthSchema)
      .catch((caught) => caught);

    expect(error).toMatchObject({ status: 502, code: "UNKNOWN" });
  });

  it("reports unreachable backends as NetworkError but lets aborts through", async () => {
    const abort = new DOMException("aborted", "AbortError");
    const client = new ApiClient("http://api.test", new FakeFetch([new TypeError("fetch failed"), abort]).fetch);

    await expect(client.request("/x", healthSchema)).rejects.toBeInstanceOf(NetworkError);
    await expect(client.request("/x", healthSchema)).rejects.toBe(abort);
  });

  it.each([
    ["5", 5],
    [" 12 ", 12],
    [null, null],
    ["soon", null],
    ["-1", null],
  ])("parses Retry-After %s", (value, expected) => {
    expect(parseRetryAfter(value)).toBe(expected);
  });
});
