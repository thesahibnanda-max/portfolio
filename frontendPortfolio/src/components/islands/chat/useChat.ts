import { useCallback, useEffect, useReducer, useRef } from "react";
import { ApiError } from "../../../lib/api/errors";
import { chatReducer, initialChatState } from "../../../lib/chat/chatState";
import { chatTitleFrom, noticeFor } from "../../../lib/chat/notices";
import { getChatApi } from "../../../lib/chat/services";

interface Turn {
  readonly userId: string;
  readonly assistantId: string;
  readonly text: string;
}

function newId(): string {
  return crypto.randomUUID();
}

export function useChat() {
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const stateRef = useRef(state);
  const abortRef = useRef<AbortController | null>(null);
  const lastTurnRef = useRef<Turn | null>(null);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const refreshHistory = useCallback(async () => {
    const api = getChatApi();
    if (!api.hasSession()) {
      return;
    }
    try {
      dispatch({ type: "history-loaded", chats: await api.listChats() });
    } catch (error) {
      console.warn("Chat history unavailable", error);
    }
  }, []);

  const stream = useCallback(
    async (chatId: string | null, turn: Turn, signal: AbortSignal, mayRenewSession: boolean): Promise<void> => {
      const api = getChatApi();
      try {
        let activeChatId = chatId;
        if (activeChatId === null) {
          activeChatId = (await api.createChat(chatTitleFrom(turn.text))).chat_id;
          dispatch({ type: "chat-created", chatId: activeChatId });
        }
        const events = await api.streamMessage(activeChatId, turn.text, signal);
        for await (const event of events) {
          if (event.type === "token") {
            dispatch({ type: "token-received", assistantId: turn.assistantId, text: event.text });
          } else if (event.type === "done") {
            dispatch({
              type: "answer-completed",
              assistantId: turn.assistantId,
              answer: event.reply.answer,
              scope: event.reply.scope,
              contexts: event.reply.required_contexts,
            });
          } else {
            dispatch({
              type: "answer-failed",
              assistantId: turn.assistantId,
              notice: noticeFor(event.error, Date.now()),
            });
          }
        }
        if (signal.aborted) {
          dispatch({ type: "answer-stopped", assistantId: turn.assistantId });
        }
      } catch (error) {
        if (signal.aborted) {
          dispatch({ type: "answer-stopped", assistantId: turn.assistantId });
          return;
        }
        if (error instanceof ApiError && error.isSessionExpired && mayRenewSession) {
          await api.renewSession();
          await stream(null, turn, signal, false);
          return;
        }
        dispatch({
          type: "answer-failed",
          assistantId: turn.assistantId,
          notice: noticeFor(error, Date.now()),
        });
      }
    },
    [],
  );

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (trimmed === "" || stateRef.current.isStreaming) {
        return;
      }
      const turn: Turn = { userId: newId(), assistantId: newId(), text: trimmed };
      const controller = new AbortController();
      abortRef.current = controller;
      lastTurnRef.current = turn;
      dispatch({ type: "send-started", userId: turn.userId, assistantId: turn.assistantId, text: trimmed });
      try {
        await stream(stateRef.current.chatId, turn, controller.signal, true);
      } finally {
        abortRef.current = null;
        void refreshHistory();
      }
    },
    [stream, refreshHistory],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const retry = useCallback(async () => {
    const turn = lastTurnRef.current;
    if (turn === null || stateRef.current.isStreaming) {
      return;
    }
    dispatch({ type: "turn-discarded", userId: turn.userId, assistantId: turn.assistantId });
    await send(turn.text);
  }, [send]);

  const startNewChat = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: "chat-reset" });
  }, []);

  const openChat = useCallback(async (chatId: string) => {
    abortRef.current?.abort();
    try {
      const chat = await getChatApi().getChat(chatId);
      dispatch({ type: "chat-opened", chatId: chat.chat_id, messages: chat.messages });
    } catch (error) {
      console.warn("Chat could not be opened", error);
      dispatch({ type: "chat-removed", chatId });
    }
  }, []);

  const renameChat = useCallback(async (chatId: string, title: string) => {
    const trimmed = title.trim();
    if (trimmed === "") {
      return;
    }
    try {
      dispatch({ type: "chat-renamed", chat: await getChatApi().renameChat(chatId, trimmed) });
    } catch (error) {
      console.warn("Chat could not be renamed", error);
    }
  }, []);

  const deleteChat = useCallback(async (chatId: string) => {
    try {
      await getChatApi().deleteChat(chatId);
      dispatch({ type: "chat-removed", chatId });
    } catch (error) {
      console.warn("Chat could not be deleted", error);
    }
  }, []);

  const clearNotice = useCallback(() => dispatch({ type: "notice-cleared" }), []);

  return {
    state,
    send,
    stop,
    retry,
    startNewChat,
    openChat,
    renameChat,
    deleteChat,
    refreshHistory,
    clearNotice,
  };
}
