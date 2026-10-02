import { memo } from "react";
import { Streamdown } from "streamdown";
import type { ChatMessageView } from "../../../lib/chat/chatState";

interface MessageViewProps {
  readonly message: ChatMessageView;
}

export const MessageView = memo(function MessageView({ message }: MessageViewProps) {
  if (message.role === "user") {
    return (
      <li className="chat-message ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-elevated px-4 py-3 text-[0.95rem]">
        {message.content}
      </li>
    );
  }

  const isFlagged = message.scope !== null && message.scope !== "IN_SCOPE";
  const isStreaming = message.status === "streaming";
  return (
    <li className="chat-message max-w-full">
      <div
        className={
          isFlagged
            ? "rounded-2xl border border-accent/25 bg-accent-soft px-4 py-3 text-[0.95rem] text-text"
            : "chat-markdown text-[0.95rem] leading-relaxed text-text"
        }
      >
        {message.content === "" && isStreaming ? (
          <span className="flex items-center gap-2 font-mono text-xs text-faint">
            <span className="caret" aria-hidden="true" />
            thinking
          </span>
        ) : (
          <Streamdown mode={isStreaming ? "streaming" : "static"} isAnimating={isStreaming} parseIncompleteMarkdown>
            {message.content}
          </Streamdown>
        )}
      </div>
      {message.contexts.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Sources used">
          {message.contexts
            .filter((context) => context !== "NONE")
            .map((context) => (
              <li key={context} className="pill border-accent/25 text-[0.65rem] text-accent">
                {context.toLowerCase()}
              </li>
            ))}
        </ul>
      )}
      {message.status === "stopped" && <p className="mt-2 font-mono text-xs text-faint">stopped · not saved</p>}
      {message.status === "failed" && <p className="mt-2 font-mono text-xs text-danger">failed · not saved</p>}
    </li>
  );
});
