import { type KeyboardEvent, useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { ApiClient } from "../../../lib/api/client";
import {
  accountsSchema,
  codeforcesAccountSchema,
  githubAccountSchema,
  leetcodeAccountSchema,
} from "../../../lib/api/schemas";
import type { KeyValueStorage } from "../../../lib/api/session";
import { ghostText, type Suggestion, suggest } from "../../../lib/cli/autocomplete";
import { type Block, hint, span } from "../../../lib/cli/blocks";
import { type CommandEffect, runCommand, type StatsTarget, statsBlocks } from "../../../lib/cli/commands";
import type { CliData, LiveStats } from "../../../lib/cli/data";
import { CommandHistory } from "../../../lib/cli/history";
import { parseInput } from "../../../lib/cli/parser";
import { initialTerminalState, terminalReducer } from "../../../lib/cli/terminalState";
import { BACKEND_BASE_URL } from "../../../lib/config";
import { EntryView } from "./EntryView";
import { Prompt } from "./Prompt";
import { useAgent } from "./useAgent";

const QUICK_COMMANDS = [
  "/whoami",
  "/experience",
  "/projects",
  "/skills",
  "/stats",
  "/resume",
  "/contact",
  "/help",
  "/go-back",
];
const STICKY_SCROLL_PX = 96;
const LEAVE_MS = 320;

class MemoryStorage implements KeyValueStorage {
  readonly #values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.#values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.#values.set(key, value);
  }

  removeItem(key: string): void {
    this.#values.delete(key);
  }
}

function tabStorage(): KeyValueStorage {
  try {
    const probe = "__portfolio_cli_probe__";
    window.sessionStorage.setItem(probe, probe);
    window.sessionStorage.removeItem(probe);
    return window.sessionStorage;
  } catch {
    return new MemoryStorage();
  }
}

function newId(): string {
  return crypto.randomUUID();
}

async function fetchLiveStats(): Promise<LiveStats> {
  const client = new ApiClient(BACKEND_BASE_URL);
  const [leetcode, codeforces, github] = await Promise.all([
    client.request("/details/leetcode", accountsSchema(leetcodeAccountSchema)),
    client.request("/details/codeforces", accountsSchema(codeforcesAccountSchema)),
    client.request("/details/github", accountsSchema(githubAccountSchema)),
  ]);
  return { leetcode: leetcode.accounts, codeforces: codeforces.accounts, github: github.accounts };
}

export default function Terminal({ data }: { readonly data: CliData }) {
  const [state, dispatch] = useReducer(terminalReducer, initialTerminalState);
  const stateRef = useRef(state);
  const [input, setInput] = useState("");
  const [selected, setSelected] = useState(0);
  const [menuDismissed, setMenuDismissed] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const historyRef = useRef<CommandHistory | null>(null);
  const agent = useAgent(dispatch, stateRef);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const suggestions = useMemo(
    () => (menuDismissed || state.busy ? [] : suggest(input, data)),
    [input, data, menuDismissed, state.busy],
  );
  const ghost = ghostText(input, suggestions);
  const limitedFor = state.rateLimitedUntil === null ? 0 : Math.ceil((state.rateLimitedUntil - now) / 1000);

  useEffect(() => {
    historyRef.current = new CommandHistory(tabStorage());
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (state.rateLimitedUntil === null) {
      return;
    }
    const timer = window.setInterval(() => {
      setNow(Date.now());
      if (state.rateLimitedUntil !== null && state.rateLimitedUntil <= Date.now()) {
        dispatch({ type: "rate-limit-cleared" });
      }
    }, 250);
    return () => window.clearInterval(timer);
  }, [state.rateLimitedUntil]);

  useEffect(() => {
    const viewport = window.visualViewport;
    const root = rootRef.current;
    if (viewport === null || root === null) {
      return;
    }
    const sync = (): void => {
      root.style.setProperty("--term-height", `${viewport.height}px`);
    };
    sync();
    viewport.addEventListener("resize", sync);
    return () => viewport.removeEventListener("resize", sync);
  }, []);

  useEffect(() => {
    const list = scrollRef.current;
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

  useEffect(() => {
    if (!state.busy) {
      inputRef.current?.focus({ preventScroll: true });
    }
  }, [state.busy]);

  const printBlocks = useCallback((blocks: readonly Block[]) => {
    dispatch({ type: "entries-added", entries: [{ id: newId(), kind: "output", blocks }] });
  }, []);

  const showStats = useCallback(
    async (target: StatsTarget) => {
      dispatch({ type: "busy-changed", busy: true });
      try {
        const live = await fetchLiveStats();
        const blocks = statsBlocks(target, live);
        if (blocks.length === 0) {
          throw new Error("The live API returned no accounts");
        }
        printBlocks([...blocks, hint("Live from the API.")]);
      } catch (error) {
        console.warn("Live stats unavailable; showing the build snapshot", error);
        printBlocks([
          ...statsBlocks(target, data),
          hint(`Live stats are unavailable right now; showing the snapshot from ${data.builtAt.slice(0, 10)}.`),
        ]);
      } finally {
        dispatch({ type: "busy-changed", busy: false });
      }
    },
    [data, printBlocks],
  );

  const applyEffect = useCallback(
    (effect: CommandEffect) => {
      switch (effect.kind) {
        case "print":
          printBlocks(effect.blocks);
          return;
        case "clear":
          dispatch({ type: "screen-cleared" });
          return;
        case "navigate":
          printBlocks(effect.blocks);
          setLeaving(true);
          window.setTimeout(() => window.location.assign(effect.href), LEAVE_MS);
          return;
        case "open-url":
          printBlocks(effect.blocks);
          window.open(effect.url, effect.url.startsWith("mailto:") ? "_self" : "_blank", "noopener,noreferrer");
          return;
        case "ask":
          void agent.ask(effect.question);
          return;
        case "new-chat":
          dispatch({ type: "chat-changed", chatId: null });
          printBlocks([{ kind: "lines", lines: [[span("Started a new conversation.", "muted")]] }]);
          return;
        case "list-chats":
          void agent.listChats();
          return;
        case "open-chat":
          void agent.openChat(effect.index);
          return;
        case "stats":
          void showStats(effect.target);
          return;
      }
    },
    [agent, printBlocks, showStats],
  );

  const run = useCallback(
    (raw: string) => {
      const parsed = parseInput(raw);
      if (parsed.kind === "empty" || stateRef.current.busy || leaving) {
        return;
      }
      historyRef.current?.push(parsed.raw);
      setInput("");
      setSelected(0);
      setMenuDismissed(false);
      dispatch({ type: "entries-added", entries: [{ id: newId(), kind: "input", text: parsed.raw }] });
      if (parsed.kind === "question") {
        void agent.ask(parsed.rest);
        return;
      }
      applyEffect(runCommand(parsed.name, { args: parsed.args, rest: parsed.rest }, { data, now: new Date() }));
    },
    [agent, applyEffect, data, leaving],
  );

  const accept = useCallback(
    (suggestion: Suggestion, execute: boolean) => {
      if (execute && !suggestion.value.endsWith(" ")) {
        run(suggestion.value);
        return;
      }
      setInput(suggestion.value);
      setSelected(0);
      inputRef.current?.focus();
    },
    [run],
  );

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    const isMenuOpen = suggestions.length > 0;
    const textarea = event.currentTarget;
    const hasSelection = textarea.selectionStart !== textarea.selectionEnd;

    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      const choice = suggestions[selected];
      if (isMenuOpen && choice !== undefined && choice.value.trim() !== input.trim()) {
        accept(choice, true);
      } else {
        run(input);
      }
      return;
    }
    if (event.key === "Tab" && isMenuOpen) {
      event.preventDefault();
      const choice = suggestions[selected];
      if (choice !== undefined) {
        accept(choice, false);
      }
      return;
    }
    if (event.key === "ArrowRight" && ghost !== "" && textarea.selectionStart === input.length) {
      event.preventDefault();
      setInput(input + ghost);
      return;
    }
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      const up = event.key === "ArrowUp";
      if (isMenuOpen) {
        event.preventDefault();
        setSelected((index) => (index + (up ? -1 : 1) + suggestions.length) % suggestions.length);
        return;
      }
      if (!input.includes("\n") && historyRef.current !== null) {
        event.preventDefault();
        setInput(up ? historyRef.current.previous(input) : historyRef.current.next());
        setMenuDismissed(true);
      }
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      if (state.busy) {
        agent.stop();
      } else if (isMenuOpen) {
        setMenuDismissed(true);
      } else {
        setInput("");
      }
      return;
    }
    if (event.ctrlKey && !event.metaKey && !event.altKey) {
      const key = event.key.toLowerCase();
      if (key === "c" && !hasSelection) {
        event.preventDefault();
        if (state.busy) {
          agent.stop();
        } else if (input !== "") {
          dispatch({ type: "entries-added", entries: [{ id: newId(), kind: "input", text: `${input}^C` }] });
          setInput("");
        }
      } else if (key === "l") {
        event.preventDefault();
        dispatch({ type: "screen-cleared" });
      } else if (key === "u") {
        event.preventDefault();
        setInput("");
      }
    }
  };

  const status = state.busy
    ? { tone: "text-accent", label: "thinking" }
    : limitedFor > 0
      ? { tone: "text-danger", label: `rate limited · ${limitedFor}s` }
      : { tone: "text-success", label: "online" };

  return (
    <div ref={rootRef} className="term-root" data-leaving={leaving ? "" : undefined} data-terminal>
      <div className="term-window">
        <header className="flex items-center gap-3 border-b border-line px-4 py-2.5">
          <div className="flex gap-1.5" aria-hidden="true">
            <span className="term-dot bg-danger/70" />
            <span className="term-dot bg-accent/70" />
            <span className="term-dot bg-success/70" />
          </div>
          <h1 className="min-w-0 flex-1 truncate text-center text-xs text-muted">
            {data.ownerName.split(" ")[0]?.toLowerCase()}@portfolio: ~/agent
          </h1>
          <button
            type="button"
            onClick={() => run("/go-back")}
            className="rounded-full border border-line px-3 py-1 text-xs text-muted transition-colors duration-200 hover:border-accent/50 hover:text-accent"
          >
            ← Portfolio
          </button>
        </header>

        <div
          ref={scrollRef}
          className="term-scroll"
          role="log"
          aria-live="polite"
          aria-busy={state.busy}
          aria-label="Terminal output"
          data-lenis-prevent
          onMouseUp={() => {
            if (window.getSelection()?.toString() === "") {
              inputRef.current?.focus({ preventScroll: true });
            }
          }}
        >
          {state.entries.map((entry) => (
            <EntryView key={entry.id} entry={entry} data={data} />
          ))}
        </div>

        <div className="border-t border-line px-4 pt-3 pb-2 md:px-7">
          <Prompt
            value={input}
            ghost={ghost}
            suggestions={suggestions}
            selected={Math.min(selected, Math.max(0, suggestions.length - 1))}
            busy={state.busy}
            inputRef={inputRef}
            onChange={(value) => {
              setInput(value);
              setSelected(0);
              setMenuDismissed(false);
            }}
            onKeyDown={onKeyDown}
            onPick={(suggestion) => accept(suggestion, true)}
            onHover={setSelected}
          />
          <nav aria-label="Quick commands" className="-mx-4 mt-2 flex gap-2 overflow-x-auto px-4 pb-1 md:hidden">
            {QUICK_COMMANDS.map((command) => (
              <button key={command} type="button" className="term-quick" onClick={() => run(command)}>
                {command}
              </button>
            ))}
          </nav>
          <div className="mt-1 flex items-center justify-between gap-3 text-[0.7rem] text-faint">
            <span className={status.tone}>
              <span aria-hidden="true">● </span>
              agent {status.label}
            </span>
            <span className="hidden sm:inline">
              {state.chatId === null ? "new conversation" : "conversation saved for 12h"} · ? for help · ↑↓ history ·
              esc to stop
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
