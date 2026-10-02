import { useEffect, useState } from "react";
import type { ChatNotice } from "../../../lib/chat/chatState";

interface NoticeBarProps {
  readonly notice: ChatNotice;
  readonly onRetry: () => void;
  readonly onNewChat: () => void;
  readonly onDismiss: () => void;
}

function secondsUntil(until: number): number {
  return Math.max(0, Math.ceil((until - Date.now()) / 1000));
}

function RateLimitCountdown({ until, onRetry }: { readonly until: number; readonly onRetry: () => void }) {
  const [remaining, setRemaining] = useState(() => secondsUntil(until));

  useEffect(() => {
    const timer = window.setInterval(() => setRemaining(secondsUntil(until)), 250);
    return () => window.clearInterval(timer);
  }, [until]);

  return (
    <>
      <span>
        Easy there — you can ask again in <span className="tabular text-accent">{remaining}s</span>.
      </span>
      <button type="button" disabled={remaining > 0} onClick={onRetry} className="chat-notice-action">
        Retry
      </button>
    </>
  );
}

export function NoticeBar({ notice, onRetry, onNewChat, onDismiss }: NoticeBarProps) {
  return (
    <div
      role="status"
      className="mx-4 mb-1 flex items-center justify-between gap-3 rounded-xl border border-line bg-elevated px-4 py-3 text-sm text-muted"
    >
      {notice.kind === "rate-limited" && <RateLimitCountdown until={notice.until} onRetry={onRetry} />}
      {notice.kind === "chat-full" && (
        <>
          <span>This conversation is full.</span>
          <button type="button" onClick={onNewChat} className="chat-notice-action">
            Start a new chat
          </button>
        </>
      )}
      {notice.kind === "error" && (
        <>
          <span>{notice.message}</span>
          <span className="flex gap-2">
            <button type="button" onClick={onRetry} className="chat-notice-action">
              Retry
            </button>
            <button type="button" onClick={onDismiss} className="chat-notice-action" aria-label="Dismiss">
              ✕
            </button>
          </span>
        </>
      )}
    </div>
  );
}
