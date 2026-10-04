export type Tone = "text" | "muted" | "faint" | "accent" | "success" | "danger";

export interface Span {
  readonly text: string;
  readonly tone?: Tone;
  readonly bold?: boolean;
  readonly href?: string;
}

export type Line = readonly Span[];

export type Block =
  | { readonly kind: "heading"; readonly text: string; readonly meta?: string }
  | { readonly kind: "lines"; readonly lines: readonly Line[]; readonly indent?: boolean }
  | { readonly kind: "list"; readonly items: readonly Line[] }
  | { readonly kind: "table"; readonly rows: readonly (readonly Line[])[] }
  | { readonly kind: "pairs"; readonly pairs: readonly (readonly [string, Line])[] }
  | { readonly kind: "chips"; readonly items: readonly string[] }
  | { readonly kind: "bars"; readonly bars: readonly Bar[] }
  | { readonly kind: "error"; readonly text: string }
  | { readonly kind: "hint"; readonly text: string };

export interface Bar {
  readonly label: string;
  readonly value: number;
  readonly max: number;
  readonly caption: string;
}

const SAFE_PROTOCOLS = new Set(["https:", "http:", "mailto:"]);

export function safeHref(href: string): string | undefined {
  try {
    const url = new URL(href);
    return SAFE_PROTOCOLS.has(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

export function span(text: string, tone?: Tone, bold?: boolean): Span {
  return { text, ...(tone === undefined ? {} : { tone }), ...(bold === true ? { bold } : {}) };
}

export function link(text: string, href: string): Span {
  const safe = safeHref(href);
  return safe === undefined ? { text } : { text, href: safe };
}

export function text(...lines: readonly string[]): Block {
  return { kind: "lines", lines: lines.map((line) => [span(line)]) };
}

export function hint(value: string): Block {
  return { kind: "hint", text: value };
}

export function error(value: string): Block {
  return { kind: "error", text: value };
}

export function asciiBar(value: number, max: number, width: number): string {
  const ratio = max <= 0 ? 0 : Math.min(Math.max(value / max, 0), 1);
  const filled = Math.round(ratio * width);
  return `${"█".repeat(filled)}${"░".repeat(width - filled)}`;
}
