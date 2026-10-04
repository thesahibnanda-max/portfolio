import { type Command, findCommand, type Registry } from "./commands";
import type { CliData } from "./data";
import { normalize } from "./parser";

export interface Suggestion {
  readonly value: string;
  readonly label: string;
  readonly detail: string;
}

const MAX_SUGGESTIONS = 8;

export function suggest(input: string, registry: Registry, data: CliData): readonly Suggestion[] {
  if (!input.startsWith("/") || input.includes("\n")) {
    return [];
  }
  const spaceAt = input.indexOf(" ");
  if (spaceAt === -1) {
    return commandSuggestions(registry, input.slice(1).toLowerCase());
  }
  const command = findCommand(registry, input.slice(1, spaceAt));
  if (command === undefined || !command.enabled || command.argOptions === undefined) {
    return [];
  }
  return argumentSuggestions(command, input.slice(spaceAt + 1), data);
}

export function ghostText(input: string, suggestions: readonly Suggestion[]): string {
  const first = suggestions[0];
  if (first === undefined || input === "" || !first.value.toLowerCase().startsWith(input.toLowerCase())) {
    return "";
  }
  return first.value.slice(input.length);
}

function commandSuggestions(registry: Registry, typed: string): readonly Suggestion[] {
  const ranked = registry.commands
    .map((command) => ({ command, score: commandScore(command, typed) }))
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score);
  return ranked.slice(0, typed === "" ? ranked.length : MAX_SUGGESTIONS).map(({ command }) => ({
    value: command.argOptions === undefined && !command.usage.includes("<") ? `/${command.name}` : `/${command.name} `,
    label: command.usage,
    detail: command.summary,
  }));
}

function commandScore(command: Command, typed: string): number {
  if (typed === "") {
    return 1;
  }
  if (command.name.startsWith(typed)) {
    return 4;
  }
  if (command.aliases.some((alias) => alias.startsWith(typed))) {
    return 3;
  }
  return isSubsequence(typed, command.name) ? 2 : 0;
}

function argumentSuggestions(command: Command, typed: string, data: CliData): readonly Suggestion[] {
  const wanted = normalize(typed);
  const options = command.argOptions?.(data) ?? [];
  return options
    .filter((option) => wanted === "" || normalize(option).includes(wanted))
    .sort((left, right) => Number(normalize(right).startsWith(wanted)) - Number(normalize(left).startsWith(wanted)))
    .slice(0, MAX_SUGGESTIONS)
    .map((option) => ({
      value: `/${command.name} ${option}`,
      label: option,
      detail: command.summary,
    }));
}

function isSubsequence(needle: string, haystack: string): boolean {
  let index = 0;
  for (const character of haystack) {
    if (character === needle[index]) {
      index += 1;
    }
  }
  return index === needle.length;
}
