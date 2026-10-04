import { type KeyboardEvent, type RefObject, useLayoutEffect } from "react";
import type { Suggestion } from "../../../lib/cli/autocomplete";

export const MAX_INPUT_CHARS = 500;

interface PromptProps {
  readonly value: string;
  readonly ghost: string;
  readonly suggestions: readonly Suggestion[];
  readonly selected: number;
  readonly busy: boolean;
  readonly inputRef: RefObject<HTMLTextAreaElement | null>;
  readonly onChange: (value: string) => void;
  readonly onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  readonly onPick: (suggestion: Suggestion) => void;
  readonly onHover: (index: number) => void;
}

function fitHeight(textarea: HTMLTextAreaElement): void {
  if (CSS.supports("field-sizing", "content")) {
    return;
  }
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight}px`;
}

export function Prompt({
  value,
  ghost,
  suggestions,
  selected,
  busy,
  inputRef,
  onChange,
  onKeyDown,
  onPick,
  onHover,
}: PromptProps) {
  const isMenuOpen = suggestions.length > 0;

  useLayoutEffect(() => {
    if (inputRef.current !== null && value !== undefined) {
      fitHeight(inputRef.current);
    }
  }, [inputRef, value]);

  return (
    <div>
      <div className="term-box" data-busy={busy ? "" : undefined}>
        <span className={busy ? "text-faint" : "text-muted"} aria-hidden="true">
          &gt;
        </span>
        <div className="term-field">
          <div className="term-ghost" aria-hidden="true">
            {value === "" ? (
              !busy && <span className="block truncate text-faint">Ask anything, or type / for commands</span>
            ) : (
              <>
                <span className="invisible">{value}</span>
                <span className="text-faint">{ghost}</span>
              </>
            )}
          </div>
          <label htmlFor="term-input" className="sr-only">
            Command or question
          </label>
          <textarea
            id="term-input"
            ref={inputRef}
            value={value}
            rows={1}
            maxLength={MAX_INPUT_CHARS}
            spellCheck={false}
            autoCapitalize="off"
            autoComplete="off"
            autoCorrect="off"
            enterKeyHint="send"
            role="combobox"
            aria-expanded={isMenuOpen}
            aria-controls="term-menu"
            aria-autocomplete="list"
            aria-activedescendant={isMenuOpen ? `term-option-${selected}` : undefined}
            className="term-input"
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={onKeyDown}
          />
        </div>
      </div>
      {isMenuOpen && (
        <div id="term-menu" role="listbox" aria-label="Suggestions" className="term-menu">
          {suggestions.map((suggestion, index) => (
            <div
              key={suggestion.value}
              id={`term-option-${index}`}
              role="option"
              tabIndex={-1}
              aria-selected={index === selected}
              className="term-option"
              onMouseDown={(event) => {
                event.preventDefault();
                onPick(suggestion);
              }}
              onMouseEnter={() => onHover(index)}
            >
              <span className="truncate">{suggestion.label}</span>
              <span className={`truncate ${index === selected ? "" : "text-faint"}`}>{suggestion.detail}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
