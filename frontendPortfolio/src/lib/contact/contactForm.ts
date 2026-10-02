import type { ApiClient } from "../api/client";
import { ApiError, NetworkError } from "../api/errors";
import { type ContactResponse, contactResponseSchema } from "../api/schemas";

export const CONTACT_LIMITS = { subject: 150, message: 5000 } as const;

export type ContactField = "email" | "subject" | "message";

export interface ContactDraft {
  readonly email: string;
  readonly subject: string;
  readonly message: string;
}

export type FieldErrors = Partial<Record<ContactField, string>>;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function normalizeEmail(value: string): string {
  return value.trim().toLowerCase();
}

export function validateContact(draft: ContactDraft): FieldErrors {
  const errors: FieldErrors = {};
  const email = normalizeEmail(draft.email);
  const subject = draft.subject.trim();
  const message = draft.message.trim();

  if (!EMAIL.test(email)) {
    errors.email = "Enter an email address I can reply to.";
  }
  if (subject === "") {
    errors.subject = "Add a short subject.";
  } else if (/[\r\n]/.test(subject)) {
    errors.subject = "Keep the subject on one line.";
  } else if (subject.length > CONTACT_LIMITS.subject) {
    errors.subject = `Keep the subject under ${CONTACT_LIMITS.subject} characters.`;
  }
  if (message === "") {
    errors.message = "Write a message.";
  } else if (message.length > CONTACT_LIMITS.message) {
    errors.message = `Keep the message under ${CONTACT_LIMITS.message} characters.`;
  }
  return errors;
}

export type ContactOutcome =
  | { readonly kind: "sent"; readonly response: ContactResponse }
  | { readonly kind: "invalid"; readonly errors: FieldErrors }
  | { readonly kind: "rate-limited"; readonly retryAfterSeconds: number }
  | { readonly kind: "unavailable" }
  | { readonly kind: "failed"; readonly message: string };

const FALLBACK_RETRY_SECONDS = 60;

export async function sendContact(
  client: ApiClient,
  draft: ContactDraft,
  signal?: AbortSignal,
): Promise<ContactOutcome> {
  const errors = validateContact(draft);
  if (Object.keys(errors).length > 0) {
    return { kind: "invalid", errors };
  }

  try {
    const response = await client.request("/contact", contactResponseSchema, {
      method: "POST",
      body: {
        email: normalizeEmail(draft.email),
        subject: draft.subject.trim(),
        message: draft.message.trim(),
      },
      signal,
    });
    return { kind: "sent", response };
  } catch (error) {
    return outcomeFor(error);
  }
}

export function outcomeFor(error: unknown): ContactOutcome {
  if (error instanceof ApiError) {
    if (error.code === "RATE_LIMITED") {
      return { kind: "rate-limited", retryAfterSeconds: error.retryAfterSeconds ?? FALLBACK_RETRY_SECONDS };
    }
    if (error.code === "MAIL_UNAVAILABLE") {
      return { kind: "unavailable" };
    }
    if (error.code === "VALIDATION_ERROR") {
      return { kind: "invalid", errors: fieldErrorsFrom(error) };
    }
    return { kind: "failed", message: "Something went wrong on the server. Please try again." };
  }
  if (error instanceof NetworkError) {
    return { kind: "failed", message: "Can't reach the server right now. Check your connection and retry." };
  }
  throw error;
}

function fieldErrorsFrom(error: ApiError): FieldErrors {
  const errors: FieldErrors = {};
  for (const detail of error.details) {
    const field = detail.field.replace(/^body\./, "");
    if (field === "email" || field === "subject" || field === "message") {
      errors[field] = detail.message;
    }
  }
  return Object.keys(errors).length > 0 ? errors : { message: error.message };
}
