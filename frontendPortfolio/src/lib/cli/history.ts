import type { KeyValueStorage } from "../api/session";

const STORAGE_KEY = "portfolio.cli.history";
const MAX_ITEMS = 100;

export class CommandHistory {
  readonly #storage: KeyValueStorage;
  #items: string[];
  #cursor: number;
  #draft = "";

  constructor(storage: KeyValueStorage) {
    this.#storage = storage;
    this.#items = CommandHistory.#load(storage);
    this.#cursor = this.#items.length;
  }

  get items(): readonly string[] {
    return this.#items;
  }

  push(entry: string): void {
    const value = entry.trim();
    if (value !== "" && this.#items.at(-1) !== value) {
      this.#items = [...this.#items, value].slice(-MAX_ITEMS);
      this.#persist();
    }
    this.#cursor = this.#items.length;
    this.#draft = "";
  }

  previous(current: string): string {
    if (this.#cursor === this.#items.length) {
      this.#draft = current;
    }
    this.#cursor = Math.max(0, this.#cursor - 1);
    return this.#items[this.#cursor] ?? current;
  }

  next(): string {
    this.#cursor = Math.min(this.#items.length, this.#cursor + 1);
    return this.#cursor === this.#items.length ? this.#draft : (this.#items[this.#cursor] ?? this.#draft);
  }

  #persist(): void {
    try {
      this.#storage.setItem(STORAGE_KEY, JSON.stringify(this.#items));
    } catch (error) {
      console.warn("Command history could not be saved", error);
    }
  }

  static #load(storage: KeyValueStorage): string[] {
    try {
      const parsed: unknown = JSON.parse(storage.getItem(STORAGE_KEY) ?? "[]");
      return Array.isArray(parsed)
        ? parsed.filter((item): item is string => typeof item === "string").slice(-MAX_ITEMS)
        : [];
    } catch {
      return [];
    }
  }
}
