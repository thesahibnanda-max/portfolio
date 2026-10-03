import { type Dispatch, type RefObject, useCallback, useEffect, useRef } from "react";
import { ApiError } from "../../../lib/api/errors";
import type { ChatSummary } from "../../../lib/api/schemas";
import { chatTitleFrom, noticeFor } from "../../../lib/chat/notices";
import { getChatApi } from "../../../lib/chat/services";
import { error, hint, type Line, span } from "../../../lib/cli/blocks";
import type { Entry, TerminalAction, TerminalState } from "../../../lib/cli/terminalState";

const STOPPED_NOTE = "interrupted · not saved";
const dateFormat = new Intl.DateTimeFormat("en", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function newId(): string {
  return crypto.randomUUID();
}

function secondsUntil(until: number): number {
  return Math.max(1, Math.ceil((until - Date.now()) / 1000));
}

export function useAgent(dispatch: Dispatch<TerminalAction>, stateRef: RefObject<TerminalState>) {
  const abortRef = useRef<AbortController | null>(null);
  const listedRef = useRef<readonly ChatSummary[]>([]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const print = useCallback(
    (entry: Omit<Extract<Entry, { kind: "output" }>, "id">) => {
      dispatch({ type: "entries-added", entries: [{ id: newId(), ...entry }] });
    },
    [dispatch],
  );

  const fail = useCallback(
    (id: string, cause: unknown) => {
      const notice = noticeFor(cause, Date.now());
      if (notice.kind === "rate-limited") {
        dispatch({ type: "rate-limited", until: notice.until });
        dispatch({
          type: "answer-ended",
          id,
          status: "failed",
          note: `rate limited · retry in ${secondsUntil(notice.until)}s · slash commands still work`,
          at: Date.now(),
        });
        return;
      }
      const note = notice.kind === "chat-full" ? "this conversation is full · /new starts a fresh one" : notice.message;
      dispatch({ type: "answer-ended", id, status: "failed", note, at: Date.now() });
    },
    [dispatch],
  );

  const streamTurn = useCallback(
    async (question: string, id: string, signal: AbortSignal, mayRenewSession: boolean): Promise<void> => {
      const api = getChatApi();
      try {
        let chatId = stateRef.current.chatId;
        if (chatId === null) {
          chatId = (await api.createChat(chatTitleFrom(question), "cli")).chat_id;
          dispatch({ type: "chat-changed", chatId });
        }
        const events = await api.streamAgentMessage(chatId, question, signal);
        for await (const event of events) {
          if (event.type === "step") {
            dispatch({ type: "answer-step", id, label: event.label });
          } else if (event.type === "token") {
            dispatch({ type: "answer-token", id, text: event.text });
          } else if (event.type === "done") {
            dispatch({
              type: "answer-completed",
              id,
              text: event.reply.answer,
              scope: event.reply.scope,
              at: Date.now(),
            });
          } else {
            fail(id, event.error);
          }
        }
        if (signal.aborted) {
          dispatch({ type: "answer-ended", id, status: "stopped", note: STOPPED_NOTE, at: Date.now() });
        }
      } catch (cause) {
        if (signal.aborted) {
          dispatch({ type: "answer-ended", id, status: "stopped", note: STOPPED_NOTE, at: Date.now() });
          return;
        }
        if (cause instanceof ApiError && cause.isSessionExpired && mayRenewSession) {
          await api.renewSession();
          dispatch({ type: "chat-changed", chatId: null });
          await streamTurn(question, id, signal, false);
          return;
        }
        fail(id, cause);
      }
    },
    [dispatch, fail, stateRef],
  );

  const ask = useCallback(
    async (question: string) => {
      const limitedUntil = stateRef.current.rateLimitedUntil;
      if (limitedUntil !== null && limitedUntil > Date.now()) {
        print({
          kind: "output",
          blocks: [
            error(`The agent is rate limited for ${secondsUntil(limitedUntil)}s more.`),
            hint("Slash commands work meanwhile, e.g. /projects or /stats."),
          ],
        });
        return;
      }
      const id = newId();
      const controller = new AbortController();
      abortRef.current = controller;
      dispatch({ type: "answer-started", id, at: Date.now() });
      try {
        await streamTurn(question, id, controller.signal, true);
      } finally {
        abortRef.current = null;
        dispatch({ type: "busy-changed", busy: false });
      }
    },
    [dispatch, print, stateRef, streamTurn],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const listChats = useCallback(async () => {
    dispatch({ type: "busy-changed", busy: true });
    try {
      const api = getChatApi();
      const chats = api.hasSession() ? await api.listChats() : [];
      listedRef.current = chats;
      if (chats.length === 0) {
        print({
          kind: "output",
          blocks: [hint("No conversations yet. Ask anything to start one; they live for 12 hours.")],
        });
        return;
      }
      const current = stateRef.current.chatId;
      print({
        kind: "output",
        blocks: [
          { kind: "heading", text: "Conversations", meta: `${chats.length}` },
          {
            kind: "list",
            items: chats.map(
              (chat, index): Line => [
                span(`${String(index + 1).padStart(2, " ")}  `, "faint"),
                span(chat.origin === "cli" ? "cli  " : "chat ", chat.origin === "cli" ? "accent" : "muted"),
                span(chat.title, chat.chat_id === current ? "accent" : "text", chat.chat_id === current),
                span(`  ${dateFormat.format(new Date(chat.updated_at))}`, "faint"),
              ],
            ),
          },
          hint("Continue one with /open <n>."),
        ],
      });
    } catch (cause) {
      print({ kind: "output", blocks: [error(noticeMessage(cause))] });
    } finally {
      dispatch({ type: "busy-changed", busy: false });
    }
  }, [dispatch, print, stateRef]);

  const openChat = useCallback(
    async (index: number) => {
      const summary = listedRef.current[index - 1];
      if (summary === undefined) {
        print({
          kind: "output",
          blocks: [error(`No conversation #${index}.`), hint("Run /history first, then /open <n>.")],
        });
        return;
      }
      dispatch({ type: "busy-changed", busy: true });
      try {
        const chat = await getChatApi().getChat(summary.chat_id);
        const at = Date.now();
        const entries: Entry[] = chat.messages.map((message) =>
          message.role === "user"
            ? { id: newId(), kind: "input", text: message.content }
            : {
                id: newId(),
                kind: "answer",
                steps: [],
                text: message.content,
                status: "complete",
                scope: null,
                startedAt: at,
                finishedAt: at,
                note: "from history",
              },
        );
        dispatch({ type: "screen-cleared" });
        dispatch({
          type: "entries-added",
          entries: [
            {
              id: newId(),
              kind: "output",
              blocks: [{ kind: "heading", text: chat.title, meta: `${chat.messages.length} messages` }],
            },
            ...entries,
          ],
        });
        dispatch({ type: "chat-changed", chatId: chat.chat_id });
      } catch (cause) {
        print({ kind: "output", blocks: [error(noticeMessage(cause))] });
      } finally {
        dispatch({ type: "busy-changed", busy: false });
      }
    },
    [dispatch, print],
  );

  return { ask, stop, listChats, openChat };
}

function noticeMessage(cause: unknown): string {
  const notice = noticeFor(cause, Date.now());
  return notice.kind === "error" ? notice.message : "That didn't work. Please try again.";
}
