import { safeHref } from "./blocks";

export type Inline =
  | { readonly kind: "text"; readonly text: string }
  | { readonly kind: "strong"; readonly children: readonly Inline[] }
  | { readonly kind: "em"; readonly children: readonly Inline[] }
  | { readonly kind: "code"; readonly text: string }
  | { readonly kind: "link"; readonly href: string; readonly children: readonly Inline[] };

export type MarkdownBlock =
  | { readonly kind: "paragraph"; readonly children: readonly Inline[] }
  | { readonly kind: "heading"; readonly children: readonly Inline[] }
  | { readonly kind: "list"; readonly ordered: boolean; readonly items: readonly (readonly Inline[])[] }
  | { readonly kind: "code"; readonly text: string };

const FENCE = /^\s*```/;
const HEADING = /^\s{0,3}#{1,6}\s+(.*)$/;
const BULLET = /^\s*[-*+]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const INLINE =
  /(`[^`\n]+`)|(\*\*[^*\n]+\*\*|(?<!\w)__[^_\n]+__(?!\w))|(\[[^\]\n]+\]\([^)\s]+\))|(\*[^*\s][^*\n]*\*|(?<!\w)_[^_\n]+_(?!\w))/;

export function parseMarkdown(source: string): readonly MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  let paragraph: string[] = [];
  let index = 0;

  const flushParagraph = (): void => {
    if (paragraph.length > 0) {
      blocks.push({ kind: "paragraph", children: parseInline(paragraph.join(" ")) });
      paragraph = [];
    }
  };

  while (index < lines.length) {
    const line = lines[index] ?? "";
    if (FENCE.test(line)) {
      flushParagraph();
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !FENCE.test(lines[index] ?? "")) {
        code.push(lines[index] ?? "");
        index += 1;
      }
      blocks.push({ kind: "code", text: code.join("\n") });
      index += 1;
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading !== null) {
      flushParagraph();
      blocks.push({ kind: "heading", children: parseInline(heading[1] ?? "") });
      index += 1;
      continue;
    }
    const listMatch = BULLET.exec(line) ?? NUMBERED.exec(line);
    if (listMatch !== null) {
      flushParagraph();
      const ordered = NUMBERED.test(line) && !BULLET.test(line);
      const items: (readonly Inline[])[] = [];
      while (index < lines.length) {
        const item = (ordered ? NUMBERED : BULLET).exec(lines[index] ?? "");
        if (item === null) {
          break;
        }
        items.push(parseInline(item[1] ?? ""));
        index += 1;
      }
      blocks.push({ kind: "list", ordered, items });
      continue;
    }
    if (line.trim() === "") {
      flushParagraph();
    } else {
      paragraph.push(line.trim());
    }
    index += 1;
  }
  flushParagraph();
  return blocks;
}

export function parseInline(source: string): readonly Inline[] {
  const nodes: Inline[] = [];
  let rest = source;
  while (rest !== "") {
    const match = INLINE.exec(rest);
    if (match === null) {
      nodes.push({ kind: "text", text: rest });
      break;
    }
    if (match.index > 0) {
      nodes.push({ kind: "text", text: rest.slice(0, match.index) });
    }
    nodes.push(toInline(match));
    rest = rest.slice(match.index + match[0].length);
  }
  return nodes;
}

function toInline(match: RegExpExecArray): Inline {
  const [whole, code, strong, linkText, em] = match;
  if (code !== undefined) {
    return { kind: "code", text: code.slice(1, -1) };
  }
  if (strong !== undefined) {
    return { kind: "strong", children: parseInline(strong.slice(2, -2)) };
  }
  if (linkText !== undefined) {
    const split = linkText.indexOf("](");
    const label = linkText.slice(1, split);
    const href = safeHref(linkText.slice(split + 2, -1));
    return href === undefined ? { kind: "text", text: label } : { kind: "link", href, children: parseInline(label) };
  }
  if (em !== undefined) {
    return { kind: "em", children: parseInline(em.slice(1, -1)) };
  }
  return { kind: "text", text: whole };
}
