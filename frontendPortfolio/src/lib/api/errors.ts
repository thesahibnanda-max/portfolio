import type { ErrorResponse } from "./schemas";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorResponse["details"];
  readonly retryAfterSeconds: number | null;

  constructor(body: ErrorResponse, retryAfterSeconds: number | null) {
    super(body.message);
    this.name = "ApiError";
    this.status = body.status;
    this.code = body.error;
    this.details = body.details;
    this.retryAfterSeconds = retryAfterSeconds;
  }

  get isSessionExpired(): boolean {
    return this.code === "SESSION_EXPIRED";
  }

  get isRateLimited(): boolean {
    return this.code === "RATE_LIMITED";
  }
}

export class NetworkError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "NetworkError";
  }
}

export class InvalidResponseError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "InvalidResponseError";
  }
}
