import type { KeyboardEvent, RefObject } from "react";
import type { Suggestion } from "../../../lib/cli/autocomplete";

const MAX_ROWS = 6;
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
  const rows = Math.min(MAX_ROWS, value.split("\n").length);
  return (
    <div className="relative">
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
              <span className={index === selected ? "text-accent" : "text-text"}>{suggestion.label}</span>
              <span className="min-w-0 flex-1 truncate text-right text-xs text-faint">{suggestion.detail}</span>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-start gap-2">
        <span className={`select-none pt-px ${busy ? "text-faint" : "text-accent"}`} aria-hidden="true">
          ❯
        </span>
        <div className="relative min-w-0 flex-1">
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
            rows={rows}
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
            className="term-input relative"
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={onKeyDown}
          />
        </div>
      </div>
    </div>
  );
}
