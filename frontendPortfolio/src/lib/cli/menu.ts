import type { Suggestion } from "./autocomplete";

export type EnterDecision =
  | { readonly kind: "run"; readonly value: string }
  | { readonly kind: "fill"; readonly value: string };

export function decideEnter(input: string, choice: Suggestion | undefined, touched: boolean): EnterDecision {
  if (choice === undefined || choice.value.trim() === input.trim()) {
    return { kind: "run", value: input };
  }
  if (touched) {
    return choice.value.endsWith(" ") ? { kind: "fill", value: choice.value } : { kind: "run", value: choice.value };
  }
  if (!input.includes(" ")) {
    return { kind: "run", value: choice.value.trim() };
  }
  return { kind: "run", value: input };
}

const STEP_CALLS: readonly (readonly [string, string])[] = [
  ["Reading ", "Read"],
  ["Recalling", "Recall"],
  ["Checking", "Check"],
];

export function stepCall(label: string): { readonly name: string; readonly argument: string } {
  for (const [prefix, name] of STEP_CALLS) {
    if (label.startsWith(prefix)) {
      const rest = label.slice(prefix.length).trim();
      return { name, argument: rest === "" ? "" : rest.replace(/^(a|the) /, "") };
    }
  }
  return { name: label, argument: "" };
}
