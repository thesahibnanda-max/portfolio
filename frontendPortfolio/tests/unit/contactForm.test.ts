import { describe, expect, it } from "vitest";
import { ApiClient } from "../../src/lib/api/client";
import { ApiError, NetworkError } from "../../src/lib/api/errors";
import {
  CONTACT_LIMITS,
  type ContactDraft,
  normalizeEmail,
  outcomeFor,
  sendContact,
  validateContact,
} from "../../src/lib/contact/contactForm";
import { envelope, FakeFetch, jsonResponse } from "./support";

const DRAFT: ContactDraft = {
  email: " Visitor@Example.COM ",
  subject: " Hiring? ",
  message: " Let's talk. ",
};

function apiError(
  status: number,
  code: string,
  details: { field: string; message: string }[] = [],
  retry: number | null = null,
) {
  return new ApiError({ status, timestamp: "", error: code, message: "server says", details }, retry);
}

describe("validateContact", () => {
  it("accepts a valid draft", () => {
    expect(validateContact(DRAFT)).toEqual({});
  });

  it("flags each invalid field with a friendly message", () => {
    const errors = validateContact({
      email: "nope",
      subject: "x".repeat(CONTACT_LIMITS.subject + 1),
      message: "   ",
    });

    expect(Object.keys(errors).sort()).toEqual(["email", "message", "subject"]);
  });

  it("rejects multi-line subjects and overlong messages", () => {
    expect(validateContact({ ...DRAFT, subject: "a\nb" }).subject).toMatch(/one line/);
    expect(validateContact({ ...DRAFT, subject: "" }).subject).toBeDefined();
    expect(validateContact({ ...DRAFT, message: "x".repeat(CONTACT_LIMITS.message + 1) }).message).toMatch(/under/);
  });
});

describe("sendContact", () => {
  it("posts the trimmed, lowercased draft and returns the server's reply-to", async () => {
    const fake = new FakeFetch([
      jsonResponse(200, envelope({ status: "SENT", reply_to: "visitor@example.com", sent_at: "2026-10-02T09:30:00Z" })),
    ]);

    const outcome = await sendContact(new ApiClient("http://api.test", fake.fetch), DRAFT);

    expect(outcome).toMatchObject({ kind: "sent", response: { reply_to: "visitor@example.com" } });
    expect(fake.requests[0]?.url).toBe("http://api.test/contact");
    expect(JSON.parse(String(fake.requests[0]?.init?.body))).toEqual({
      email: "visitor@example.com",
      subject: "Hiring?",
      message: "Let's talk.",
    });
  });

  it("normalizes emails by trimming and lowercasing", () => {
    expect(normalizeEmail("  Foo.Bar@Example.COM \n")).toBe("foo.bar@example.com");
  });

  it("does not call the server for an invalid draft", async () => {
    const fake = new FakeFetch([]);

    const outcome = await sendContact(new ApiClient("http://api.test", fake.fetch), { ...DRAFT, email: "nope" });

    expect(outcome.kind).toBe("invalid");
    expect(fake.requests).toHaveLength(0);
  });
});

describe("outcomeFor", () => {
  it("maps server errors to form outcomes", () => {
    expect(outcomeFor(apiError(429, "RATE_LIMITED", [], 1200))).toEqual({
      kind: "rate-limited",
      retryAfterSeconds: 1200,
    });
    expect(outcomeFor(apiError(429, "RATE_LIMITED"))).toEqual({ kind: "rate-limited", retryAfterSeconds: 60 });
    expect(outcomeFor(apiError(503, "MAIL_UNAVAILABLE"))).toEqual({ kind: "unavailable" });
    expect(outcomeFor(apiError(500, "INTERNAL_ERROR")).kind).toBe("failed");
    expect(outcomeFor(new NetworkError("down")).kind).toBe("failed");
  });

  it("maps validation details back onto fields", () => {
    const outcome = outcomeFor(apiError(400, "VALIDATION_ERROR", [{ field: "body.email", message: "bad email" }]));
    expect(outcome).toEqual({ kind: "invalid", errors: { email: "bad email" } });

    const unknownField = outcomeFor(apiError(400, "VALIDATION_ERROR", [{ field: "body.extra", message: "x" }]));
    expect(unknownField).toEqual({ kind: "invalid", errors: { message: "server says" } });
  });

  it("rethrows programming errors instead of hiding them", () => {
    const bug = new TypeError("bug");
    expect(() => outcomeFor(bug)).toThrow(bug);
  });
});
