import { describe, expect, it } from "vitest";
import { parseInline, parseMarkdown } from "../../src/lib/cli/markdown";

describe("parseMarkdown", () => {
  it("parses paragraphs, headings, lists and code fences", () => {
    const blocks = parseMarkdown(
      "# Title\nFirst line\ncontinues.\n\n- one\n- **two**\n\n1. a\n2. b\n```\ncode <b>\n```\nend",
    );

    expect(blocks.map((block) => block.kind)).toEqual(["heading", "paragraph", "list", "list", "code", "paragraph"]);
    expect(blocks[1]).toEqual({ kind: "paragraph", children: [{ kind: "text", text: "First line continues." }] });
    expect(blocks[2]).toMatchObject({ kind: "list", ordered: false });
    expect(blocks[3]).toMatchObject({ kind: "list", ordered: true });
    expect(blocks[4]).toEqual({ kind: "code", text: "code <b>" });
  });

  it("keeps an unfinished fence and unclosed emphasis readable while streaming", () => {
    expect(parseMarkdown("```\npartial")).toEqual([{ kind: "code", text: "partial" }]);
    expect(parseInline("half **bold")).toEqual([{ kind: "text", text: "half **bold" }]);
  });
});

describe("parseInline", () => {
  it("parses bold, italic, code and safe links", () => {
    expect(parseInline("**Go** and *Rust*, `uv`, [site](https://example.com)")).toEqual([
      { kind: "strong", children: [{ kind: "text", text: "Go" }] },
      { kind: "text", text: " and " },
      { kind: "em", children: [{ kind: "text", text: "Rust" }] },
      { kind: "text", text: ", " },
      { kind: "code", text: "uv" },
      { kind: "text", text: ", " },
      { kind: "link", href: "https://example.com/", children: [{ kind: "text", text: "site" }] },
    ]);
  });

  it("never produces unsafe links or html", () => {
    expect(parseInline("[click](javascript:alert(1))")).toEqual([
      { kind: "text", text: "click" },
      { kind: "text", text: ")" },
    ]);
    expect(parseInline("<img src=x onerror=alert(1)>")).toEqual([
      { kind: "text", text: "<img src=x onerror=alert(1)>" },
    ]);
  });

  it("leaves snake_case identifiers alone", () => {
    expect(parseInline("max_rating_changes")).toEqual([{ kind: "text", text: "max_rating_changes" }]);
  });
});
