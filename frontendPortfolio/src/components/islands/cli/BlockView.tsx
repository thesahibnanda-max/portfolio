import type { ReactNode } from "react";
import { asciiBar, type Block, type Line, type Tone } from "../../../lib/cli/blocks";
import { BAR_WIDTH } from "../../../lib/cli/commands";
import { describe, withKeys } from "../../../lib/cli/keys";

const TONES: Record<Tone, string> = {
  text: "text-text",
  muted: "text-muted",
  faint: "text-faint",
  accent: "text-accent",
  success: "text-success",
  danger: "text-danger",
};

export function LineView({ line }: { readonly line: Line }): ReactNode {
  return line.map((part, index) => {
    const className = `${TONES[part.tone ?? "text"]}${part.bold === true ? " font-semibold" : ""}`;
    const key = `${index}-${part.text}`;
    return part.href === undefined ? (
      <span key={key} className={className}>
        {part.text}
      </span>
    ) : (
      <a
        key={key}
        href={part.href}
        target={part.href.startsWith("mailto:") ? undefined : "_blank"}
        rel="noopener noreferrer"
        className={`${className} underline decoration-accent/40 underline-offset-2 hover:decoration-accent`}
      >
        {part.text}
      </a>
    );
  });
}

export function BlockView({ block }: { readonly block: Block }): ReactNode {
  switch (block.kind) {
    case "heading":
      return (
        <p className="mt-3 flex flex-wrap items-baseline gap-x-3 first:mt-0">
          <span className="font-semibold text-accent">{block.text}</span>
          {block.meta !== undefined && <span className="text-xs text-faint">{block.meta}</span>}
        </p>
      );
    case "lines":
      return (
        <div className={block.indent === true ? "pl-4" : undefined}>
          {withKeys(block.lines, describe).map(([key, line]) => (
            <p key={key} className="whitespace-pre-wrap break-words">
              <LineView line={line} />
            </p>
          ))}
        </div>
      );
    case "list":
      return (
        <ul className="grid gap-0.5">
          {withKeys(block.items, describe).map(([key, line]) => (
            <li key={key} className="whitespace-pre-wrap break-words">
              <LineView line={line} />
            </li>
          ))}
        </ul>
      );
    case "pairs":
      return (
        <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-0.5 sm:gap-x-5">
          {withKeys(block.pairs, describe).map(([key, [label, value]]) => (
            <div key={key} className="contents">
              <dt className="text-faint">{label}</dt>
              <dd className="break-words">
                <LineView line={value} />
              </dd>
            </div>
          ))}
        </dl>
      );
    case "chips":
      return (
        <ul className="mt-1 flex flex-wrap gap-1.5" aria-label="Technologies">
          {block.items.map((item) => (
            <li key={item} className="term-chip">
              {item}
            </li>
          ))}
        </ul>
      );
    case "bars":
      return (
        <ul className="grid gap-0.5">
          {block.bars.map((bar) => (
            <li key={bar.label} className="flex gap-3 whitespace-pre">
              <span className="w-16 text-faint">{bar.label}</span>
              <span className="overflow-hidden text-accent" aria-hidden="true">
                {asciiBar(bar.value, bar.max, BAR_WIDTH)}
              </span>
              <span>{bar.caption}</span>
            </li>
          ))}
        </ul>
      );
    case "error":
      return (
        <p className="text-danger">
          <span aria-hidden="true">✗ </span>
          {block.text}
        </p>
      );
    case "hint":
      return <p className="text-faint">{block.text}</p>;
  }
}
