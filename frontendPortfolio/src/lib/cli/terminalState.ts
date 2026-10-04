import type { QueryScope, StreamPlan } from "../api/schemas";
import type { Block } from "./blocks";

export type AnswerStatus = "streaming" | "complete" | "stopped" | "failed";

export type Entry =
  | { readonly id: string; readonly kind: "welcome" }
  | { readonly id: string; readonly kind: "input"; readonly text: string }
  | { readonly id: string; readonly kind: "output"; readonly blocks: readonly Block[] }
  | {
      readonly id: string;
      readonly kind: "answer";
      readonly steps: readonly string[];
      readonly text: string;
      readonly status: AnswerStatus;
      readonly scope: QueryScope | null;
      readonly startedAt: number;
      readonly finishedAt: number | null;
      readonly note: string | null;
      readonly plan: StreamPlan | null;
    };

export interface TerminalState {
  readonly entries: readonly Entry[];
  readonly chatId: string | null;
  readonly busy: boolean;
  readonly rateLimitedUntil: number | null;
}

export type TerminalAction =
  | { readonly type: "entries-added"; readonly entries: readonly Entry[] }
  | { readonly type: "screen-cleared" }
  | { readonly type: "chat-changed"; readonly chatId: string | null }
  | { readonly type: "busy-changed"; readonly busy: boolean }
  | { readonly type: "answer-started"; readonly id: string; readonly at: number }
  | { readonly type: "answer-step"; readonly id: string; readonly label: string }
  | { readonly type: "answer-token"; readonly id: string; readonly text: string }
  | { readonly type: "answer-plan"; readonly id: string; readonly plan: StreamPlan }
  | {
      readonly type: "answer-completed";
      readonly id: string;
      readonly text: string;
      readonly scope: QueryScope;
      readonly at: number;
    }
  | {
      readonly type: "answer-ended";
      readonly id: string;
      readonly status: "stopped" | "failed";
      readonly note: string;
      readonly at: number;
    }
  | { readonly type: "rate-limited"; readonly until: number }
  | { readonly type: "rate-limit-cleared" };

export const MAX_ENTRIES = 400;

export const initialTerminalState: TerminalState = {
  entries: [{ id: "welcome", kind: "welcome" }],
  chatId: null,
  busy: false,
  rateLimitedUntil: null,
};

export function terminalReducer(state: TerminalState, action: TerminalAction): TerminalState {
  switch (action.type) {
    case "entries-added":
      return { ...state, entries: [...state.entries, ...action.entries].slice(-MAX_ENTRIES) };
    case "screen-cleared":
      return { ...state, entries: [] };
    case "chat-changed":
      return { ...state, chatId: action.chatId };
    case "busy-changed":
      return { ...state, busy: action.busy };
    case "answer-started":
      return {
        ...state,
        busy: true,
        entries: [
          ...state.entries,
          {
            id: action.id,
            kind: "answer" as const,
            steps: [],
            text: "",
            status: "streaming" as const,
            scope: null,
            startedAt: action.at,
            finishedAt: null,
            note: null,
            plan: null,
          },
        ].slice(-MAX_ENTRIES),
      };
    case "answer-step":
      return updateAnswer(state, action.id, (answer) => ({ ...answer, steps: [...answer.steps, action.label] }));
    case "answer-token":
      return updateAnswer(state, action.id, (answer) => ({ ...answer, text: answer.text + action.text }));
    case "answer-plan":
      return updateAnswer(state, action.id, (answer) => ({ ...answer, plan: action.plan }));
    case "answer-completed":
      return {
        ...updateAnswer(state, action.id, (answer) => ({
          ...answer,
          text: action.text,
          scope: action.scope,
          status: "complete",
          finishedAt: action.at,
        })),
        busy: false,
      };
    case "answer-ended":
      return {
        ...updateAnswer(state, action.id, (answer) => ({
          ...answer,
          status: action.status,
          note: action.note,
          finishedAt: action.at,
        })),
        busy: false,
      };
    case "rate-limited":
      return { ...state, rateLimitedUntil: action.until };
    case "rate-limit-cleared":
      return { ...state, rateLimitedUntil: null };
  }
}

type AnswerEntry = Extract<Entry, { kind: "answer" }>;

function updateAnswer(state: TerminalState, id: string, update: (answer: AnswerEntry) => AnswerEntry): TerminalState {
  return {
    ...state,
    entries: state.entries.map((entry) => (entry.kind === "answer" && entry.id === id ? update(entry) : entry)),
  };
}
