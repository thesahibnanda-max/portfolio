import { streamChatMessage } from "./chatStream";
import type { ApiClient } from "./client";
import { type Chat, type ChatSummary, chatListSchema, chatSchema, chatSummarySchema } from "./schemas";
import type { SessionStore } from "./session";

export class ChatApi {
  readonly #client: ApiClient;
  readonly #sessions: SessionStore;

  constructor(client: ApiClient, sessions: SessionStore) {
    this.#client = client;
    this.#sessions = sessions;
  }

  listChats(): Promise<readonly ChatSummary[]> {
    return this.#sessions.withSession(async (sessionId) => {
      const list = await this.#client.request("/chats", chatListSchema, { sessionId });
      return list.chats;
    });
  }

  createChat(title?: string): Promise<ChatSummary> {
    return this.#sessions.withSession((sessionId) =>
      this.#client.request("/chats", chatSummarySchema, {
        method: "POST",
        body: title === undefined ? {} : { title },
        sessionId,
      }),
    );
  }

  getChat(chatId: string): Promise<Chat> {
    return this.#sessions.withSession((sessionId) =>
      this.#client.request(`/chats/${encodeURIComponent(chatId)}`, chatSchema, { sessionId }),
    );
  }

  renameChat(chatId: string, title: string): Promise<ChatSummary> {
    return this.#sessions.withSession((sessionId) =>
      this.#client.request(`/chats/${encodeURIComponent(chatId)}`, chatSummarySchema, {
        method: "PATCH",
        body: { title },
        sessionId,
      }),
    );
  }

  deleteChat(chatId: string): Promise<void> {
    return this.#sessions.withSession((sessionId) =>
      this.#client.requestEmpty(`/chats/${encodeURIComponent(chatId)}`, { method: "DELETE", sessionId }),
    );
  }

  async streamMessage(chatId: string, message: string, signal?: AbortSignal) {
    const session = await this.#sessions.ensure();
    return streamChatMessage(this.#client, session.session_id, chatId, message, signal);
  }

  async renewSession(): Promise<void> {
    await this.#sessions.renew();
  }

  hasSession(): boolean {
    return this.#sessions.current() !== null;
  }
}
