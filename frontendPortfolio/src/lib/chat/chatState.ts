import type { ChatSummary, QueryScope, StoredMessage } from "../api/schemas";

export type MessageStatus = "streaming" | "complete" | "stopped" | "failed";

export interface ChatMessageView {
  readonly id: string;
  readonly role: "user" | "assistant";
  readonly content: string;
  readonly status: MessageStatus;
  readonly scope: QueryScope | null;
  readonly contexts: readonly string[];
}

export type ChatNotice =
  | { readonly kind: "rate-limited"; readonly until: number }
  | { readonly kind: "chat-full" }
  | { readonly kind: "error"; readonly message: string };

export interface ChatState {
  readonly chatId: string | null;
  readonly messages: readonly ChatMessageView[];
  readonly history: readonly ChatSummary[];
  readonly isStreaming: boolean;
  readonly notice: ChatNotice | null;
}

export type ChatAction =
  | { readonly type: "chat-opened"; readonly chatId: string; readonly messages: readonly StoredMessage[] }
  | { readonly type: "chat-reset" }
  | { readonly type: "history-loaded"; readonly chats: readonly ChatSummary[] }
  | { readonly type: "chat-removed"; readonly chatId: string }
  | { readonly type: "chat-renamed"; readonly chat: ChatSummary }
  | {
      readonly type: "send-started";
      readonly userId: string;
      readonly assistantId: string;
      readonly text: string;
    }
  | { readonly type: "chat-created"; readonly chatId: string }
  | { readonly type: "turn-discarded"; readonly userId: string; readonly assistantId: string }
  | { readonly type: "token-received"; readonly assistantId: string; readonly text: string }
  | {
      readonly type: "answer-completed";
      readonly assistantId: string;
      readonly answer: string;
      readonly scope: QueryScope;
      readonly contexts: readonly string[];
    }
  | { readonly type: "answer-stopped"; readonly assistantId: string }
  | { readonly type: "answer-failed"; readonly assistantId: string; readonly notice: ChatNotice }
  | { readonly type: "notice-cleared" };

export const initialChatState: ChatState = {
  chatId: null,
  messages: [],
  history: [],
  isStreaming: false,
  notice: null,
};

function updateMessage(
  messages: readonly ChatMessageView[],
  id: string,
  update: (message: ChatMessageView) => ChatMessageView,
): readonly ChatMessageView[] {
  return messages.map((message) => (message.id === id ? update(message) : message));
}

function fromStored(message: StoredMessage): ChatMessageView {
  return {
    id: `stored-${message.message_id}`,
    role: message.role,
    content: message.content,
    status: "complete",
    scope: null,
    contexts: [],
  };
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "chat-opened":
      return {
        ...state,
        chatId: action.chatId,
        messages: action.messages.map(fromStored),
        isStreaming: false,
        notice: null,
      };
    case "chat-reset":
      return { ...state, chatId: null, messages: [], isStreaming: false, notice: null };
    case "history-loaded":
      return { ...state, history: action.chats };
    case "chat-removed":
      return {
        ...state,
        history: state.history.filter((chat) => chat.chat_id !== action.chatId),
        ...(state.chatId === action.chatId ? { chatId: null, messages: [] } : {}),
      };
    case "chat-renamed":
      return {
        ...state,
        history: state.history.map((chat) => (chat.chat_id === action.chat.chat_id ? action.chat : chat)),
      };
    case "chat-created":
      return { ...state, chatId: action.chatId };
    case "turn-discarded":
      return {
        ...state,
        notice: null,
        messages: state.messages.filter((message) => message.id !== action.userId && message.id !== action.assistantId),
      };
    case "send-started":
      return {
        ...state,
        isStreaming: true,
        notice: null,
        messages: [
          ...state.messages,
          {
            id: action.userId,
            role: "user",
            content: action.text,
            status: "complete",
            scope: null,
            contexts: [],
          },
          {
            id: action.assistantId,
            role: "assistant",
            content: "",
            status: "streaming",
            scope: null,
            contexts: [],
          },
        ],
      };
    case "token-received":
      return {
        ...state,
        messages: updateMessage(state.messages, action.assistantId, (message) => ({
          ...message,
          content: message.content + action.text,
        })),
      };
    case "answer-completed":
      return {
        ...state,
        isStreaming: false,
        messages: updateMessage(state.messages, action.assistantId, (message) => ({
          ...message,
          content: action.answer,
          status: "complete",
          scope: action.scope,
          contexts: action.contexts,
        })),
      };
    case "answer-stopped":
      return {
        ...state,
        isStreaming: false,
        messages: updateMessage(state.messages, action.assistantId, (message) => ({
          ...message,
          status: "stopped",
        })),
      };
    case "answer-failed":
      return {
        ...state,
        isStreaming: false,
        notice: action.notice,
        messages: updateMessage(state.messages, action.assistantId, (message) => ({
          ...message,
          status: "failed",
        })),
      };
    case "notice-cleared":
      return { ...state, notice: null };
  }
}
