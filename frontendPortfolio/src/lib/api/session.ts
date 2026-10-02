import type { ApiClient } from "./client";
import { ApiError } from "./errors";
import { type Session, sessionSchema } from "./schemas";

const STORAGE_KEY = "portfolio.session";
const EXPIRY_MARGIN_MS = 60_000;

export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export class SessionStore {
  readonly #client: ApiClient;
  readonly #storage: KeyValueStorage;
  readonly #now: () => number;
  #pending: Promise<Session> | null = null;

  constructor(client: ApiClient, storage: KeyValueStorage, now: () => number = Date.now) {
    this.#client = client;
    this.#storage = storage;
    this.#now = now;
  }

  current(): Session | null {
    const raw = this.#storage.getItem(STORAGE_KEY);
    if (raw === null) {
      return null;
    }
    let stored: unknown;
    try {
      stored = JSON.parse(raw);
    } catch {
      this.#storage.removeItem(STORAGE_KEY);
      return null;
    }
    const parsed = sessionSchema.safeParse(stored);
    if (!parsed.success || Date.parse(parsed.data.expires_at) - EXPIRY_MARGIN_MS <= this.#now()) {
      this.#storage.removeItem(STORAGE_KEY);
      return null;
    }
    return parsed.data;
  }

  async ensure(): Promise<Session> {
    return this.current() ?? this.renew();
  }

  renew(): Promise<Session> {
    if (this.#pending === null) {
      this.#pending = this.#create().finally(() => {
        this.#pending = null;
      });
    }
    return this.#pending;
  }

  async withSession<T>(operation: (sessionId: string) => Promise<T>): Promise<T> {
    const session = await this.ensure();
    try {
      return await operation(session.session_id);
    } catch (error) {
      if (error instanceof ApiError && error.isSessionExpired) {
        const renewed = await this.renew();
        return operation(renewed.session_id);
      }
      throw error;
    }
  }

  async #create(): Promise<Session> {
    const session = await this.#client.request("/sessions", sessionSchema, { method: "POST" });
    this.#storage.setItem(STORAGE_KEY, JSON.stringify(session));
    return session;
  }
}
