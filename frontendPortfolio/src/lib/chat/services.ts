import { ChatApi } from "../api/chatApi";
import { ApiClient } from "../api/client";
import { type KeyValueStorage, SessionStore } from "../api/session";
import { BACKEND_BASE_URL } from "../config";

class MemoryStorage implements KeyValueStorage {
  readonly #values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.#values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.#values.set(key, value);
  }

  removeItem(key: string): void {
    this.#values.delete(key);
  }
}

function browserStorage(): KeyValueStorage {
  try {
    const probe = "__portfolio_probe__";
    window.localStorage.setItem(probe, probe);
    window.localStorage.removeItem(probe);
    return window.localStorage;
  } catch {
    return new MemoryStorage();
  }
}

let chatApi: ChatApi | null = null;

export function getChatApi(): ChatApi {
  if (chatApi === null) {
    const client = new ApiClient(BACKEND_BASE_URL);
    chatApi = new ChatApi(client, new SessionStore(client, browserStorage()));
  }
  return chatApi;
}
