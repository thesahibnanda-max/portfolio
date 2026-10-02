export function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });
}

export function envelope(data: unknown, status = 200): unknown {
  return { status, timestamp: "2026-10-02T00:00:00Z", data };
}

export function errorBody(status: number, error: string, message = "nope"): unknown {
  return { status, timestamp: "2026-10-02T00:00:00Z", error, message, details: [] };
}

export function sseResponse(chunks: readonly string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
}

export class MemoryStorage {
  readonly values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }
}

export interface RecordedRequest {
  readonly url: string;
  readonly init: RequestInit | undefined;
}

export class FakeFetch {
  readonly requests: RecordedRequest[] = [];
  readonly #responses: (Response | Error)[];

  constructor(responses: (Response | Error)[]) {
    this.#responses = responses;
  }

  readonly fetch = async (url: string, init?: RequestInit): Promise<Response> => {
    this.requests.push({ url, init });
    const next = this.#responses.shift();
    if (next === undefined) {
      throw new Error(`Unexpected request to ${url}`);
    }
    if (next instanceof Error) {
      throw next;
    }
    return next;
  };
}
