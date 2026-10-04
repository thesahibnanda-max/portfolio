import { type KeyboardEvent, type SubmitEvent, useEffect, useRef, useState } from "react";

const MAX_MESSAGE_CHARS = 4000;

const MAX_INPUT_HEIGHT_PX = 180;

function fitToContent(input: HTMLTextAreaElement): void {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, MAX_INPUT_HEIGHT_PX)}px`;
}

interface ComposerProps {
  readonly isStreaming: boolean;
  readonly isOpen: boolean;
  readonly onSend: (text: string) => void;
  readonly onStop: () => void;
}

export function Composer({ isStreaming, isOpen, onSend, onStop }: ComposerProps) {
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
    }
  }, [isOpen]);

  const submit = (event?: SubmitEvent<HTMLFormElement>): void => {
    event?.preventDefault();
    if (isStreaming || text.trim() === "") {
      return;
    }
    onSend(text);
    setText("");
    if (inputRef.current !== null) {
      inputRef.current.style.height = "auto";
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      submit();
    }
  };

  return (
    <form onSubmit={submit} className="border-t border-line p-4">
      <div className="flex items-end gap-2 rounded-2xl border border-line-strong bg-surface p-2 transition-colors duration-200 focus-within:border-accent/50">
        <label htmlFor="chat-input" className="sr-only">
          Your question
        </label>
        <textarea
          id="chat-input"
          ref={inputRef}
          rows={1}
          value={text}
          maxLength={MAX_MESSAGE_CHARS}
          onChange={(event) => {
            setText(event.target.value);
            fitToContent(event.target);
          }}
          onKeyDown={onKeyDown}
          placeholder="Ask anything about his work…"
          className="max-h-44 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[0.95rem] text-text placeholder:text-faint focus:outline-none"
        />
        {isStreaming ? (
          <button
            type="button"
            onClick={onStop}
            className="chat-send bg-elevated text-text"
            aria-label="Stop generating"
          >
            <span className="size-3 rounded-sm bg-current" aria-hidden="true" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={text.trim() === ""}
            className="chat-send bg-accent text-bg disabled:opacity-30"
            aria-label="Send"
          >
            <span aria-hidden="true">↑</span>
          </button>
        )}
      </div>
      <p className="mt-2 flex justify-between px-1 font-mono text-[0.7rem] text-faint">
        <span>Enter to send · Shift+Enter for a new line</span>
        {text.length > MAX_MESSAGE_CHARS * 0.8 && (
          <span>
            {text.length}/{MAX_MESSAGE_CHARS}
          </span>
        )}
      </p>
    </form>
  );
}
