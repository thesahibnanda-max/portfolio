import { useEffect, useRef, useState } from "react";
import { Composer } from "./Composer";
import { HistoryDrawer } from "./HistoryDrawer";
import { MessageView } from "./MessageView";
import { NoticeBar } from "./NoticeBar";
import { useChat } from "./useChat";

const STICKY_SCROLL_PX = 80;

interface ChatPanelProps {
  readonly isOpen: boolean;
  readonly openRequest: number;
  readonly onClose: () => void;
  readonly ownerName: string;
}

export default function ChatPanel({ isOpen, openRequest, onClose, ownerName }: ChatPanelProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const handledRequestRef = useRef(-1);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const chat = useChat();
  const { state } = chat;

  const suggestions = [
    `What does ${ownerName} work on right now?`,
    "What's his Codeforces peak rating?",
    "Which project shows his backend skills best?",
    "What's his tech stack for distributed systems?",
  ];

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) {
      return;
    }
    const isNewRequest = handledRequestRef.current !== openRequest;
    handledRequestRef.current = openRequest;
    if (isOpen && !dialog.open && (isNewRequest || openerRef.current === null)) {
      openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
      dialog.querySelector<HTMLTextAreaElement>("#chat-input")?.focus();
      void chat.refreshHistory();
    } else if (!isOpen && dialog.open) {
      dialog.close();
    }
    if (!isOpen && openerRef.current?.isConnected === true) {
      openerRef.current.focus({ preventScroll: true });
      openerRef.current = null;
    }
  }, [isOpen, openRequest, chat.refreshHistory]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) {
      return;
    }
    const onBackdropClick = (event: MouseEvent): void => {
      if (event.target === dialog) {
        onClose();
      }
    };
    dialog.addEventListener("click", onBackdropClick);
    return () => dialog.removeEventListener("click", onBackdropClick);
  }, [onClose]);

  useEffect(() => {
    const list = listRef.current;
    if (list === null) {
      return;
    }
    let isPinned = true;
    const onScroll = (): void => {
      isPinned = list.scrollHeight - list.scrollTop - list.clientHeight < STICKY_SCROLL_PX;
    };
    const observer = new MutationObserver(() => {
      if (isPinned) {
        list.scrollTop = list.scrollHeight;
      }
    });
    list.addEventListener("scroll", onScroll, { passive: true });
    observer.observe(list, { childList: true, subtree: true, characterData: true });
    return () => {
      list.removeEventListener("scroll", onScroll);
      observer.disconnect();
    };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      data-chat-dialog
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={() => {
        if (isOpen && dialogRef.current?.open !== true) {
          onClose();
        }
      }}
      aria-labelledby="chat-title"
      data-lenis-prevent
      className="chat-dialog fixed inset-y-0 right-0 left-auto m-0 h-dvh max-h-dvh w-full max-w-xl border-l border-line bg-bg p-0 text-text sm:w-[min(36rem,100vw)]"
    >
      <div className="relative flex h-full flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <h2 id="chat-title" className="flex items-center gap-2 font-medium">
              <span className="size-2 animate-pulse rounded-full bg-accent" aria-hidden="true" />
              Ask about {ownerName}
            </h2>
            <p className="font-mono text-[0.7rem] text-faint">AI answers grounded in live portfolio data</p>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="chat-icon-button"
              onClick={() => setIsHistoryOpen(true)}
              aria-label="Chat history"
            >
              <span aria-hidden="true">☰</span>
            </button>
            <button type="button" className="chat-icon-button" onClick={chat.startNewChat} aria-label="New chat">
              <span aria-hidden="true">＋</span>
            </button>
            <button type="button" className="chat-icon-button" onClick={onClose} aria-label="Close chat">
              <span aria-hidden="true">✕</span>
            </button>
          </div>
        </header>

        <a href="/cli" className="cli-entry group" data-cli-entry>
          <span className="cli-entry-prompt" aria-hidden="true">
            &gt;_
          </span>
          <span className="flex-1">
            <span className="block text-sm text-text">Portfolio Agent CLI</span>
            <span className="hidden font-mono text-[0.7rem] text-faint sm:block">
              A terminal with /commands, autocomplete and the same AI
            </span>
          </span>
          <span aria-hidden="true" className="text-faint transition-transform duration-300 group-hover:translate-x-1">
            →
          </span>
        </a>

        <div
          ref={listRef}
          className="flex-1 overflow-y-auto overscroll-contain px-5 py-6"
          aria-live="polite"
          aria-busy={state.isStreaming}
        >
          {state.messages.length === 0 ? (
            <div className="flex min-h-full flex-col gap-6 pb-4">
              <div className="flex-1" aria-hidden="true" />
              <p className="display text-5xl leading-none">
                Hi, I'm {ownerName}'s <em className="text-accent italic">AI.</em>
              </p>
              <p className="max-w-sm text-muted">
                Ask about his experience, projects, ratings or what he's like to work with.
              </p>
              <ul className="grid gap-2">
                {suggestions.map((suggestion) => (
                  <li key={suggestion}>
                    <button
                      type="button"
                      onClick={() => void chat.send(suggestion)}
                      className="w-full rounded-xl border border-line px-4 py-3 text-left text-sm text-muted transition-colors duration-200 hover:border-accent/40 hover:bg-accent-soft hover:text-text"
                    >
                      {suggestion}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <ol className="grid gap-6">
              {state.messages.map((message) => (
                <MessageView key={message.id} message={message} />
              ))}
            </ol>
          )}
        </div>

        {state.notice !== null && (
          <NoticeBar
            notice={state.notice}
            onRetry={() => void chat.retry()}
            onNewChat={chat.startNewChat}
            onDismiss={chat.clearNotice}
          />
        )}

        <Composer
          isStreaming={state.isStreaming}
          isOpen={isOpen}
          onSend={(text) => void chat.send(text)}
          onStop={chat.stop}
        />

        {isHistoryOpen && (
          <HistoryDrawer
            chats={state.history}
            activeChatId={state.chatId}
            onClose={() => setIsHistoryOpen(false)}
            onOpen={(chatId) => {
              setIsHistoryOpen(false);
              void chat.openChat(chatId);
            }}
            onRename={(chatId, title) => void chat.renameChat(chatId, title)}
            onDelete={(chatId) => void chat.deleteChat(chatId)}
          />
        )}
      </div>
    </dialog>
  );
}
