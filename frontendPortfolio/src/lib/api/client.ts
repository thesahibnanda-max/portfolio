import type { z } from "zod";
import { ApiError, InvalidResponseError, NetworkError } from "./errors";
import { errorResponseSchema, rawEnvelopeSchema } from "./schemas";

export const SESSION_HEADER = "X-Session-Id";

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface RequestOptions {
  readonly method?: "GET" | "POST" | "PATCH" | "DELETE";
  readonly body?: unknown;
  readonly sessionId?: string;
  readonly signal?: AbortSignal;
}

export class ApiClient {
  readonly #baseUrl: string;
  readonly #fetch: FetchLike;

  constructor(baseUrl: string, fetchImpl: FetchLike = globalThis.fetch.bind(globalThis)) {
    this.#baseUrl = baseUrl.replace(/\/+$/, "");
    this.#fetch = fetchImpl;
  }

  async request<T extends z.ZodType>(path: string, schema: T, options: RequestOptions = {}): Promise<z.infer<T>> {
    const response = await this.send(path, options);
    const envelope = rawEnvelopeSchema.safeParse(await this.#json(response));
    if (!envelope.success) {
      throw new InvalidResponseError(`Response from ${path} is not an API envelope`, {
        cause: envelope.error,
      });
    }
    const data = schema.safeParse(envelope.data.data);
    if (!data.success) {
      throw new InvalidResponseError(`Unexpected data from ${path}`, { cause: data.error });
    }
    return data.data;
  }

  async requestBytes(path: string, options: RequestOptions = {}): Promise<Uint8Array<ArrayBuffer>> {
    const response = await this.send(path, options);
    const contentType = response.headers.get("Content-Type") ?? "";
    if (!contentType.startsWith("image/")) {
      throw new InvalidResponseError(`Expected an image from ${path}, got "${contentType}"`);
    }
    return new Uint8Array(await response.arrayBuffer());
  }

  url(path: string): string {
    return `${this.#baseUrl}${path}`;
  }

  async requestEmpty(path: string, options: RequestOptions = {}): Promise<void> {
    await this.send(path, options);
  }

  async send(path: string, options: RequestOptions = {}): Promise<Response> {
    const headers: Record<string, string> = {};
    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    if (options.sessionId !== undefined) {
      headers[SESSION_HEADER] = options.sessionId;
    }

    let response: Response;
    try {
      response = await this.#fetch(`${this.#baseUrl}${path}`, {
        method: options.method ?? "GET",
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: options.signal,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      throw new NetworkError(`Could not reach the backend at ${this.#baseUrl}`, { cause: error });
    }

    if (!response.ok) {
      throw await this.#toApiError(response);
    }
    return response;
  }

  async #toApiError(response: Response): Promise<ApiError> {
    const parsed = errorResponseSchema.safeParse(await this.#json(response).catch(() => undefined));
    const body = parsed.success
      ? parsed.data
      : {
          status: response.status,
          timestamp: "",
          error: "UNKNOWN",
          message: response.statusText,
          details: [],
        };
    return new ApiError(body, parseRetryAfter(response.headers.get("Retry-After")));
  }

  async #json(response: Response): Promise<unknown> {
    try {
      return await response.json();
    } catch (error) {
      throw new InvalidResponseError(`Response from ${response.url} is not JSON`, { cause: error });
    }
  }
}

export function parseRetryAfter(value: string | null): number | null {
  if (value === null || !/^\d+$/.test(value.trim())) {
    return null;
  }
  return Number.parseInt(value, 10);
}
