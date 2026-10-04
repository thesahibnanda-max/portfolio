import {
  type CSSProperties,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import { ApiClient } from "../../../lib/api/client";
import {
  accountsSchema,
  codeforcesAccountSchema,
  githubAccountSchema,
  leetcodeAccountSchema,
  type StreamPlan,
} from "../../../lib/api/schemas";
import type { KeyValueStorage } from "../../../lib/api/session";
import { ghostText, type Suggestion, suggest } from "../../../lib/cli/autocomplete";
import { type Block, hint, span } from "../../../lib/cli/blocks";
import {
  buildRegistry,
  type CommandEffect,
  runCommand,
  type StatsTarget,
  skillSummary,
  statsBlocks,
} from "../../../lib/cli/commands";
import type { CliData, LiveStats } from "../../../lib/cli/data";
import { CommandHistory } from "../../../lib/cli/history";
import { decideEnter } from "../../../lib/cli/menu";
import { parseInput } from "../../../lib/cli/parser";
import {
  type CliMode,
  type CliSettings,
  currentMode,
  cycleSetting,
  defaultSettings,
  isOn,
  isPluginEnabled,
  loadSettings,
  saveSettings,
  settingValue,
} from "../../../lib/cli/settings";
import { initialTerminalState, terminalReducer } from "../../../lib/cli/terminalState";
import { BACKEND_BASE_URL } from "../../../lib/config";
import { ConfigPanel } from "./ConfigPanel";
import { EntryView } from "./EntryView";
import { Prompt } from "./Prompt";
import { useAgent } from "./useAgent";

const CHAT_PARAMETER = "chat";
const QUICK_COMMANDS = [
  "/whoami",
  "/experience",
  "/projects",
  "/skills",
  "/stats",
  "/resume",
  "/config",
  "/help",
  "/go-back",
];
const STICKY_SCROLL_PX = 96;
const LEAVE_MS = 320;
const STEP_PAUSE_MS = 220;
const ACCENTS: Readonly<Record<string, readonly [string, string]>> = {
  amber: ["#f5a524", "rgb(245 165 36 / 0.12)"],
  blue: ["#60a5fa", "rgb(96 165 250 / 0.12)"],
  green: ["#4ade80", "rgb(74 222 128 / 0.12)"],
  violet: ["#a78bfa", "rgb(167 139 250 / 0.12)"],
};
const MODE_LABELS: Readonly<Record<CliMode, string>> = {
  default: "",
  "auto-run": "⏵⏵ auto-run on",
  plan: "⏸ plan mode on",
};

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

function browserStorage(kind: "localStorage" | "sessionStorage"): KeyValueStorage {
  try {
    const storage = window[kind];
    const probe = "__portfolio_cli_probe__";
    storage.setItem(probe, probe);
    storage.removeItem(probe);
    return storage;
  } catch {
    return new MemoryStorage();
  }
}

function newId(): string {
  return crypto.randomUUID();
}

function pause(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });
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
  const [settings, setSettings] = useState<CliSettings>(() => defaultSettings(data.manifest));
  const [input, setInput] = useState("");
  const [selected, setSelected] = useState(0);
  const [menuDismissed, setMenuDismissed] = useState(false);
  const [menuTouched, setMenuTouched] = useState(false);
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [pendingPlan, setPendingPlan] = useState<StreamPlan | null>(null);
  const [isStepping, setIsStepping] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const historyRef = useRef<CommandHistory | null>(null);
  const settingsStorageRef = useRef<KeyValueStorage | null>(null);
  const agent = useAgent(dispatch, stateRef);

  const registry = useMemo(() => buildRegistry(data.manifest, settings), [data.manifest, settings]);
  const mode = currentMode(settings);
  const isBusy = state.busy || isStepping;
  const autocomplete = isOn(settings, "autocomplete");
  const suggestions = useMemo(
    () => (!autocomplete || menuDismissed || isBusy ? [] : suggest(input, registry, data)),
    [autocomplete, input, registry, data, menuDismissed, isBusy],
  );
  const ghost = ghostText(input, suggestions);
  const limitedFor = state.rateLimitedUntil === null ? 0 : Math.ceil((state.rateLimitedUntil - now) / 1000);
  const [accent, accentSoft] = ACCENTS[settingValue(settings, "accent")] ?? ACCENTS.amber ?? ["#f5a524", ""];

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const updateSettings = useCallback((next: CliSettings) => {
    setSettings(next);
    if (settingsStorageRef.current !== null) {
      saveSettings(settingsStorageRef.current, next);
    }
  }, []);

  useEffect(() => {
    historyRef.current = new CommandHistory(browserStorage("sessionStorage"));
    settingsStorageRef.current = browserStorage("localStorage");
    setSettings(loadSettings(settingsStorageRef.current, data.manifest));
    inputRef.current?.focus();
    const chatId = new URLSearchParams(window.location.search).get(CHAT_PARAMETER);
    if (chatId !== null && chatId !== "") {
      window.history.replaceState(window.history.state, "", window.location.pathname);
      void agent.openChatById(chatId);
    }
  }, [agent.openChatById, data.manifest]);

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
    if (!isBusy && !isConfigOpen) {
      inputRef.current?.focus({ preventScroll: true });
    }
  }, [isBusy, isConfigOpen]);

  const printBlocks = useCallback((blocks: readonly Block[]) => {
    dispatch({ type: "entries-added", entries: [{ id: newId(), kind: "output", blocks }] });
  }, []);

  const showStats = useCallback(
    async (target: StatsTarget) => {
      dispatch({ type: "busy-changed", busy: true });
      try {
        const blocks = statsBlocks(target, await fetchLiveStats());
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

  const askAgent = useCallback(
    async (question: string): Promise<StreamPlan | null> => {
      if (!isPluginEnabled(settings, "agent")) {
        printBlocks([
          hint("The agent plugin is off, so questions are not sent to the AI."),
          hint("Turn it on with /plugins enable agent, or use a /command."),
        ]);
        return null;
      }
      const style = settingValue(settings, "answers") === "detailed" ? "detailed" : "concise";
      return agent.ask(question, { style, mode: mode === "default" ? "answer" : "plan" });
    },
    [agent, mode, printBlocks, settings],
  );

  const applyEffect = useCallback(
    async (effect: CommandEffect): Promise<StreamPlan | null> => {
      switch (effect.kind) {
        case "print":
          printBlocks(effect.blocks);
          return null;
        case "clear":
          dispatch({ type: "screen-cleared" });
          return null;
        case "navigate":
          printBlocks(effect.blocks);
          setLeaving(true);
          window.setTimeout(() => window.location.assign(effect.href), LEAVE_MS);
          return null;
        case "open-url":
          printBlocks(effect.blocks);
          window.open(effect.url, effect.url.startsWith("mailto:") ? "_self" : "_blank", "noopener,noreferrer");
          return null;
        case "ask":
          return askAgent(effect.question);
        case "new-chat":
          dispatch({ type: "chat-changed", chatId: null });
          printBlocks([{ kind: "lines", lines: [[span("Started a new conversation.", "muted")]] }]);
          return null;
        case "list-chats":
          await agent.listChats();
          return null;
        case "open-chat":
          await agent.openChat(effect.index);
          return null;
        case "stats":
          await showStats(effect.target);
          return null;
        case "config-panel":
          setIsConfigOpen(true);
          return null;
        case "settings":
          updateSettings(effect.settings);
          printBlocks(effect.blocks);
          return null;
      }
    },
    [agent, askAgent, printBlocks, showStats, updateSettings],
  );

  const execute = useCallback(
    async (raw: string): Promise<StreamPlan | null> => {
      const parsed = parseInput(raw);
      if (parsed.kind === "empty") {
        return null;
      }
      dispatch({ type: "entries-added", entries: [{ id: newId(), kind: "input", text: parsed.raw }] });
      if (parsed.kind === "question") {
        return askAgent(parsed.rest);
      }
      const effect = runCommand(
        parsed.name,
        { args: parsed.args, rest: parsed.rest },
        { data, now: new Date(), settings, registry, random: Math.random },
      );
      return applyEffect(effect);
    },
    [applyEffect, askAgent, data, registry, settings],
  );

  const runPlan = useCallback(
    async (plan: StreamPlan) => {
      setPendingPlan(null);
      setIsStepping(true);
      try {
        for (const step of plan.steps) {
          await pause(STEP_PAUSE_MS);
          await execute(step.command);
        }
      } finally {
        setIsStepping(false);
      }
    },
    [execute],
  );

  const run = useCallback(
    (raw: string) => {
      if (stateRef.current.busy || isStepping || leaving || parseInput(raw).kind === "empty") {
        return;
      }
      historyRef.current?.push(raw.trim());
      setInput("");
      setSelected(0);
      setMenuDismissed(false);
      setMenuTouched(false);
      setPendingPlan(null);
      void execute(raw).then((plan) => {
        if (plan === null || plan.steps.length === 0) {
          return;
        }
        if (mode === "auto-run") {
          void runPlan(plan);
        } else {
          setPendingPlan(plan);
        }
      });
    },
    [execute, isStepping, leaving, mode, runPlan],
  );

  const fill = useCallback((value: string) => {
    setInput(value);
    setSelected(0);
    setMenuTouched(false);
    inputRef.current?.focus();
  }, []);

  const pick = useCallback(
    (suggestion: Suggestion) => {
      if (suggestion.value.endsWith(" ")) {
        fill(suggestion.value);
      } else {
        run(suggestion.value);
      }
    },
    [fill, run],
  );

  const cycleMode = useCallback(() => {
    const next = cycleSetting(settings, data.manifest, "mode");
    updateSettings(next);
  }, [data.manifest, settings, updateSettings]);

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    const isMenuOpen = suggestions.length > 0;
    const textarea = event.currentTarget;
    const hasSelection = textarea.selectionStart !== textarea.selectionEnd;

    if (event.key === "Tab" && event.shiftKey) {
      event.preventDefault();
      cycleMode();
      return;
    }
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (pendingPlan !== null && input.trim() === "") {
        void runPlan(pendingPlan);
        return;
      }
      const decision = decideEnter(input, isMenuOpen ? suggestions[selected] : undefined, menuTouched);
      if (decision.kind === "fill") {
        fill(decision.value);
      } else {
        run(decision.value);
      }
      return;
    }
    if (event.key === "Tab" && isMenuOpen) {
      event.preventDefault();
      const choice = suggestions[selected];
      if (choice !== undefined) {
        fill(choice.value);
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
        setMenuTouched(true);
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
      } else if (pendingPlan !== null) {
        setPendingPlan(null);
        printBlocks([hint("Plan cancelled.")]);
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

  const status = isBusy ? (
    <span className="text-accent">esc to interrupt</span>
  ) : limitedFor > 0 ? (
    <span className="text-danger">rate limited · {limitedFor}s</span>
  ) : (
    <button type="button" className="term-link" onClick={() => run("/go-back")}>
      ← portfolio
    </button>
  );

  const rootStyle = { "--color-accent": accent, "--color-accent-soft": accentSoft } as CSSProperties;

  return (
    <div
      ref={rootRef}
      className="term-root"
      style={rootStyle}
      data-leaving={leaving ? "" : undefined}
      data-motion={isOn(settings, "animations") ? "on" : "off"}
      data-mode={mode}
      data-terminal
    >
      <h1 className="sr-only">{data.ownerName} · Portfolio Agent CLI</h1>
      <div
        ref={scrollRef}
        className="term-scroll"
        role="log"
        aria-live="polite"
        aria-busy={isBusy}
        aria-label="Terminal output"
        data-lenis-prevent
        onMouseUp={() => {
          if (!isConfigOpen && window.getSelection()?.toString() === "") {
            inputRef.current?.focus({ preventScroll: true });
          }
        }}
      >
        <div className="term-column">
          {state.entries.map((entry) => (
            <EntryView
              key={entry.id}
              entry={entry}
              data={data}
              summary={skillSummary(registry, data, settings)}
              showCost={isOn(settings, "showCost")}
              animated={isOn(settings, "animations")}
            />
          ))}
          {pendingPlan !== null && (
            <p className="term-body mt-[0.4em] text-accent" data-plan-prompt>
              <span className="hover-only">Enter to run this plan · Esc to cancel</span>
              <span className="touch-only">
                <button type="button" className="term-link" onClick={() => void runPlan(pendingPlan)}>
                  run this plan
                </button>{" "}
                ·{" "}
                <button type="button" className="term-link" onClick={() => setPendingPlan(null)}>
                  cancel
                </button>
              </span>
            </p>
          )}
        </div>
      </div>

      <div className="term-column pt-[0.6em] pb-[max(0.6em,env(safe-area-inset-bottom))]">
        {isConfigOpen ? (
          <ConfigPanel
            manifest={data.manifest}
            settings={settings}
            onChange={updateSettings}
            onClose={() => {
              setIsConfigOpen(false);
              printBlocks([hint("Settings saved for this browser.")]);
            }}
          />
        ) : (
          <Prompt
            value={input}
            ghost={ghost}
            suggestions={suggestions}
            selected={Math.min(selected, Math.max(0, suggestions.length - 1))}
            busy={isBusy}
            inputRef={inputRef}
            onChange={(value) => {
              setInput(value);
              setSelected(0);
              setMenuDismissed(false);
              setMenuTouched(false);
            }}
            onKeyDown={onKeyDown}
            onPick={pick}
            onHover={(index) => {
              setSelected(index);
              setMenuTouched(true);
            }}
          />
        )}
        {suggestions.length === 0 && !isConfigOpen && (
          <div className="mt-[0.35em] flex items-center justify-between gap-[2ch] px-[0.9em] text-faint">
            {mode === "default" ? (
              <span>
                <span className="hover-only">? for shortcuts · shift+tab for modes</span>
                <span className="touch-only">/help for commands</span>
              </span>
            ) : (
              <span className={mode === "plan" ? "text-plan" : "text-accent"} data-mode-indicator>
                {MODE_LABELS[mode]} <span className="hover-only text-faint">(shift+tab to cycle)</span>
              </span>
            )}
            {status}
          </div>
        )}
        <nav
          aria-label="Quick commands"
          className="touch-only term-quick-row mt-[0.5em] flex gap-[1ch] overflow-x-auto"
        >
          <button type="button" className="term-quick" onClick={cycleMode} data-mode-chip>
            mode: {mode}
          </button>
          {QUICK_COMMANDS.map((command) => (
            <button key={command} type="button" className="term-quick" onClick={() => run(command)}>
              {command}
            </button>
          ))}
        </nav>
      </div>
    </div>
  );
}
