import type { CSSProperties, ReactNode } from "react";
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
        className={`${className} term-link break-all`}
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
        <p className="mt-2 font-semibold first:mt-0">
          {block.text}
          {block.meta !== undefined && <span className="font-normal text-faint"> · {block.meta}</span>}
        </p>
      );
    case "lines":
      return (
        <div className={block.indent === true ? "pl-[2ch]" : undefined}>
          {withKeys(block.lines, describe).map(([key, line]) => (
            <p key={key} className="whitespace-pre-wrap break-words">
              <LineView line={line} />
            </p>
          ))}
        </div>
      );
    case "list":
      return (
        <ul>
          {withKeys(block.items, describe).map(([key, line]) => (
            <li key={key} className="relative pl-[2ch] break-words">
              <span className="absolute left-0 text-faint" aria-hidden="true">
                -
              </span>
              <LineView line={line} />
            </li>
          ))}
        </ul>
      );
    case "table": {
      const columns = block.rows[0]?.length ?? 1;
      return (
        <div className="term-table" data-flex-last style={{ "--term-columns": columns } as CSSProperties}>
          {withKeys(block.rows, describe).map(([key, row]) => (
            <div key={key} className="term-row">
              <span className="break-words">
                <LineView line={row[0] ?? []} />
              </span>
              <span className="term-rest">
                {withKeys(row.slice(1), describe).map(([cellKey, cell]) => (
                  <span key={cellKey} className="break-words">
                    <LineView line={cell} />
                  </span>
                ))}
              </span>
            </div>
          ))}
        </div>
      );
    }
    case "pairs":
      return (
        <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-[2ch]">
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
      return <p className="text-muted">{block.items.join(" · ")}</p>;
    case "bars":
      return (
        <ul>
          {block.bars.map((bar) => (
            <li key={bar.label} className="flex gap-[2ch] whitespace-pre">
              <span className="w-[7ch] text-faint">{bar.label}</span>
              <span className="text-muted" aria-hidden="true">
                {asciiBar(bar.value, bar.max, BAR_WIDTH)}
              </span>
              <span>{bar.caption}</span>
            </li>
          ))}
        </ul>
      );
    case "error":
      return <p className="text-danger">Error: {block.text}</p>;
    case "hint":
      return <p className="text-faint">{block.text}</p>;
  }
}
