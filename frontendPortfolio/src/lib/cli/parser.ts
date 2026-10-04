export interface ParsedInput {
  readonly kind: "empty" | "command" | "question";
  readonly name: string;
  readonly args: readonly string[];
  readonly rest: string;
  readonly raw: string;
}

const COMMAND_PREFIX = "/";

export function parseInput(input: string): ParsedInput {
  const raw = input.trim();
  if (raw === "") {
    return { kind: "empty", name: "", args: [], rest: "", raw };
  }
  if (raw === "?") {
    return { kind: "command", name: "help", args: [], rest: "", raw };
  }
  if (!raw.startsWith(COMMAND_PREFIX)) {
    return { kind: "question", name: "", args: [], rest: raw, raw };
  }
  const body = raw.slice(COMMAND_PREFIX.length);
  const nameEnd = body.search(/\s/);
  const name = (nameEnd === -1 ? body : body.slice(0, nameEnd)).toLowerCase();
  const rest = nameEnd === -1 ? "" : body.slice(nameEnd).trim();
  return { kind: "command", name, args: tokenize(rest), rest, raw };
}

export function tokenize(value: string): readonly string[] {
  const tokens: string[] = [];
  const pattern = /"([^"]*)"|'([^']*)'|(\S+)/g;
  for (const match of value.matchAll(pattern)) {
    tokens.push(match[1] ?? match[2] ?? match[3] ?? "");
  }
  return tokens;
}

export function normalize(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function findByName<T>(items: readonly T[], query: string, nameOf: (item: T) => string): T | undefined {
  const wanted = normalize(query);
  if (wanted === "") {
    return undefined;
  }
  return (
    items.find((item) => normalize(nameOf(item)) === wanted) ??
    items.find((item) => normalize(nameOf(item)).startsWith(wanted)) ??
    items.find((item) => normalize(nameOf(item)).includes(wanted))
  );
}
