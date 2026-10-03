import { memo, type ReactNode } from "react";
import { describe, withKeys } from "../../../lib/cli/keys";
import { type Inline, type MarkdownBlock, parseMarkdown } from "../../../lib/cli/markdown";

function renderInline(nodes: readonly Inline[]): ReactNode[] {
  return withKeys(nodes, describe).map(([key, node]) => renderNode(key, node));
}

function renderNode(key: string, node: Inline): ReactNode {
  if (node.kind === "text") {
    return node.text;
  }
  if (node.kind === "strong") {
    return (
      <strong key={key} className="font-semibold text-text">
        {renderInline(node.children)}
      </strong>
    );
  }
  if (node.kind === "em") {
    return (
      <em key={key} className="text-muted italic">
        {renderInline(node.children)}
      </em>
    );
  }
  if (node.kind === "code") {
    return <code key={key}>{node.text}</code>;
  }
  return (
    <a
      key={key}
      href={node.href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-accent underline underline-offset-2"
    >
      {renderInline(node.children)}
    </a>
  );
}

function renderBlock(key: string, block: MarkdownBlock): ReactNode {
  if (block.kind === "paragraph") {
    return <p key={key}>{renderInline(block.children)}</p>;
  }
  if (block.kind === "heading") {
    return (
      <p key={key} className="mt-3 font-semibold text-text first:mt-0">
        {renderInline(block.children)}
      </p>
    );
  }
  if (block.kind === "code") {
    return (
      <pre key={key}>
        <code>{block.text}</code>
      </pre>
    );
  }
  const items = withKeys(block.items, describe).map(([itemKey, item]) => (
    <li key={itemKey} className="pl-1">
      {renderInline(item)}
    </li>
  ));
  return block.ordered ? (
    <ol key={key} className="list-decimal pl-5 marker:text-faint">
      {items}
    </ol>
  ) : (
    <ul key={key} className="list-disc pl-5 marker:text-accent">
      {items}
    </ul>
  );
}

export const Markdown = memo(function Markdown({ text }: { readonly text: string }) {
  return (
    <div className="term-markdown">
      {withKeys(parseMarkdown(text), describe).map(([key, block]) => renderBlock(key, block))}
    </div>
  );
});
