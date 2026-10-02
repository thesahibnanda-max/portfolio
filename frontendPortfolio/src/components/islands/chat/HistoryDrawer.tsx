import { useState } from "react";
import type { ChatSummary } from "../../../lib/api/schemas";

interface HistoryDrawerProps {
  readonly chats: readonly ChatSummary[];
  readonly activeChatId: string | null;
  readonly onClose: () => void;
  readonly onOpen: (chatId: string) => void;
  readonly onRename: (chatId: string, title: string) => void;
  readonly onDelete: (chatId: string) => void;
}

const dateFormat = new Intl.DateTimeFormat("en", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function HistoryDrawer({ chats, activeChatId, onClose, onOpen, onRename, onDelete }: HistoryDrawerProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  return (
    <div className="absolute inset-0 z-10 flex flex-col bg-bg/95 backdrop-blur-xl">
      <header className="flex items-center justify-between border-b border-line px-5 py-4">
        <h3 className="font-medium">Your chats</h3>
        <button type="button" className="chat-icon-button" onClick={onClose} aria-label="Close history">
          <span aria-hidden="true">✕</span>
        </button>
      </header>
      {chats.length === 0 ? (
        <p className="p-5 text-sm text-muted">
          No conversations yet. Chats live for 12 hours and are private to this browser.
        </p>
      ) : (
        <ul className="flex-1 divide-y divide-line overflow-y-auto">
          {chats.map((chat) => (
            <li key={chat.chat_id} className="flex items-center gap-2 px-5 py-3">
              {editingId === chat.chat_id ? (
                <form
                  className="flex flex-1 gap-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    onRename(chat.chat_id, draft);
                    setEditingId(null);
                  }}
                >
                  <label htmlFor={`rename-${chat.chat_id}`} className="sr-only">
                    Chat title
                  </label>
                  <input
                    id={`rename-${chat.chat_id}`}
                    value={draft}
                    maxLength={200}
                    onChange={(event) => setDraft(event.target.value)}
                    className="flex-1 rounded-lg border border-line-strong bg-surface px-3 py-1.5 text-sm focus:border-accent/50 focus:outline-none"
                  />
                  <button type="submit" className="chat-notice-action">
                    Save
                  </button>
                </form>
              ) : (
                <>
                  <button type="button" onClick={() => onOpen(chat.chat_id)} className="min-w-0 flex-1 text-left">
                    <span
                      className={`block truncate text-sm ${chat.chat_id === activeChatId ? "text-accent" : "text-text"}`}
                    >
                      {chat.title}
                    </span>
                    <span className="font-mono text-[0.65rem] text-faint">
                      {dateFormat.format(new Date(chat.updated_at))}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="chat-icon-button"
                    onClick={() => {
                      setEditingId(chat.chat_id);
                      setDraft(chat.title);
                    }}
                    aria-label={`Rename ${chat.title}`}
                  >
                    <span aria-hidden="true">✎</span>
                  </button>
                  <button
                    type="button"
                    className="chat-icon-button hover:text-danger"
                    onClick={() => onDelete(chat.chat_id)}
                    aria-label={`Delete ${chat.title}`}
                  >
                    <span aria-hidden="true">⌫</span>
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
