import { ApiError, NetworkError } from "../api/errors";
import type { ChatNotice } from "./chatState";

const FALLBACK_RETRY_SECONDS = 30;

export function noticeFor(error: unknown, now: number): ChatNotice {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "RATE_LIMITED":
        return {
          kind: "rate-limited",
          until: now + (error.retryAfterSeconds ?? FALLBACK_RETRY_SECONDS) * 1000,
        };
      case "CHAT_FULL":
        return { kind: "chat-full" };
      case "VALIDATION_ERROR":
        return { kind: "error", message: error.message };
      case "UPSTREAM_BUSY":
      case "UPSTREAM_ERROR":
        return { kind: "error", message: "The AI is catching its breath. Try again in a moment." };
      default:
        return { kind: "error", message: "Something went wrong on the server. Please try again." };
    }
  }
  if (error instanceof NetworkError) {
    return { kind: "error", message: "Can't reach the server right now. Check your connection and retry." };
  }
  return { kind: "error", message: "Something unexpected happened. Please try again." };
}

export function chatTitleFrom(text: string): string {
  const MAX_TITLE = 60;
  const singleLine = text.replace(/\s+/g, " ").trim();
  return singleLine.length <= MAX_TITLE ? singleLine : `${singleLine.slice(0, MAX_TITLE - 1).trimEnd()}…`;
}
