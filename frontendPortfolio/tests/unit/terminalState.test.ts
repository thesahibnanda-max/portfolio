import { describe, expect, it } from "vitest";
import { initialTerminalState, MAX_ENTRIES, terminalReducer } from "../../src/lib/cli/terminalState";

describe("terminalReducer", () => {
  it("starts with the welcome screen", () => {
    expect(initialTerminalState.entries).toEqual([{ id: "welcome", kind: "welcome" }]);
  });

  it("streams an answer from steps and tokens to completion", () => {
    let state = terminalReducer(initialTerminalState, { type: "answer-started", id: "a", at: 1000 });
    expect(state.busy).toBe(true);
    state = terminalReducer(state, { type: "answer-step", id: "a", label: "Reading profile" });
    state = terminalReducer(state, { type: "answer-token", id: "a", text: "He " });
    state = terminalReducer(state, { type: "answer-token", id: "a", text: "builds." });
    state = terminalReducer(state, {
      type: "answer-completed",
      id: "a",
      text: "He builds.",
      scope: "IN_SCOPE",
      at: 2500,
    });

    expect(state.busy).toBe(false);
    expect(state.entries.at(-1)).toMatchObject({
      kind: "answer",
      steps: ["Reading profile"],
      text: "He builds.",
      status: "complete",
      finishedAt: 2500,
    });
  });

  it("marks stopped and failed answers with a note", () => {
    let state = terminalReducer(initialTerminalState, { type: "answer-started", id: "a", at: 0 });
    state = terminalReducer(state, { type: "answer-ended", id: "a", status: "stopped", note: "interrupted", at: 5 });

    expect(state.busy).toBe(false);
    expect(state.entries.at(-1)).toMatchObject({ status: "stopped", note: "interrupted" });
  });

  it("caps the scrollback and clears the screen", () => {
    let state = initialTerminalState;
    for (let index = 0; index < MAX_ENTRIES + 10; index += 1) {
      state = terminalReducer(state, {
        type: "entries-added",
        entries: [{ id: `e${index}`, kind: "input", text: "x" }],
      });
    }
    expect(state.entries).toHaveLength(MAX_ENTRIES);
    expect(state.entries.at(-1)?.id).toBe(`e${MAX_ENTRIES + 9}`);
    expect(terminalReducer(state, { type: "screen-cleared" }).entries).toEqual([]);
  });

  it("tracks the chat, busy flag and rate limit", () => {
    let state = terminalReducer(initialTerminalState, { type: "chat-changed", chatId: "c1" });
    state = terminalReducer(state, { type: "busy-changed", busy: true });
    state = terminalReducer(state, { type: "rate-limited", until: 99 });
    expect(state).toMatchObject({ chatId: "c1", busy: true, rateLimitedUntil: 99 });
    expect(terminalReducer(state, { type: "rate-limit-cleared" }).rateLimitedUntil).toBeNull();
  });

  it("ignores updates for unknown answers", () => {
    const state = terminalReducer(initialTerminalState, { type: "answer-token", id: "missing", text: "x" });
    expect(state.entries).toEqual(initialTerminalState.entries);
  });
});
