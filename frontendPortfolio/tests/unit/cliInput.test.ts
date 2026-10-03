import { describe, expect, it } from "vitest";
import { ghostText, suggest } from "../../src/lib/cli/autocomplete";
import { asciiBar, link, safeHref } from "../../src/lib/cli/blocks";
import { CommandHistory } from "../../src/lib/cli/history";
import { withKeys } from "../../src/lib/cli/keys";
import { findByName, normalize, parseInput, tokenize } from "../../src/lib/cli/parser";
import { DATA } from "./cliData";
import { MemoryStorage } from "./support";

describe("parseInput", () => {
  it("tells commands, questions and empty input apart", () => {
    expect(parseInput("   ")).toMatchObject({ kind: "empty" });
    expect(parseInput(" What is Relay? ")).toMatchObject({ kind: "question", rest: "What is Relay?" });
    expect(parseInput("/Projects  relay cli ")).toMatchObject({
      kind: "command",
      name: "projects",
      rest: "relay cli",
      args: ["relay", "cli"],
    });
    expect(parseInput("?")).toMatchObject({ kind: "command", name: "help" });
    expect(parseInput("/whoami")).toMatchObject({ name: "whoami", rest: "", args: [] });
  });

  it("tokenizes quoted arguments", () => {
    expect(tokenize(`a "b c" 'd e' f`)).toEqual(["a", "b c", "d e", "f"]);
  });

  it("matches names exactly, then by prefix, then by substring, ignoring accents and punctuation", () => {
    const names = ["Relay - Multi-Agent", "fastclient", "Résumé Builder"];
    expect(findByName(names, "FASTCLIENT", String)).toBe("fastclient");
    expect(findByName(names, "rel", String)).toBe("Relay - Multi-Agent");
    expect(findByName(names, "multi agent", String)).toBe("Relay - Multi-Agent");
    expect(findByName(names, "resume", String)).toBe("Résumé Builder");
    expect(findByName(names, "  ", String)).toBeUndefined();
    expect(normalize("  C++ / Go! ")).toBe("c go");
  });
});

describe("autocomplete", () => {
  it("lists every command for a bare slash and ranks prefixes first", () => {
    expect(suggest("/", DATA).length).toBeGreaterThan(5);
    expect(suggest("/pro", DATA)[0]?.value).toBe("/projects ");
    expect(suggest("/wh", DATA)[0]).toMatchObject({ value: "/whoami", label: "/whoami" });
    expect(suggest("/quit", DATA)[0]?.label).toBe("/go-back");
    expect(suggest("/zzz", DATA)).toEqual([]);
  });

  it("completes arguments from the data without duplicates", () => {
    const companies = suggest("/experience ", DATA).map((suggestion) => suggestion.label);
    expect(companies).toContain("CRED");
    expect(new Set(companies).size).toBe(companies.length);
    expect(suggest("/projects heli", DATA)[0]?.value).toBe(
      "/projects Helios - Distributed Real-Time Streaming & Analytics Platform",
    );
    expect(suggest("/stats g", DATA).map((suggestion) => suggestion.label)).toEqual(["github"]);
    expect(suggest("/clear x", DATA)).toEqual([]);
  });

  it("never completes questions or multi-line input", () => {
    expect(suggest("what about /projects", DATA)).toEqual([]);
    expect(suggest("/pro\nx", DATA)).toEqual([]);
  });

  it("shows ghost text only for a matching prefix", () => {
    expect(ghostText("/pro", suggest("/pro", DATA))).toBe("jects ");
    expect(ghostText("", suggest("/", DATA))).toBe("");
    expect(ghostText("/zzz", [])).toBe("");
    expect(ghostText("/quit", suggest("/quit", DATA))).toBe("");
  });
});

describe("blocks", () => {
  it("only links to http, https and mailto", () => {
    expect(safeHref("https://example.com/a")).toBe("https://example.com/a");
    expect(safeHref("mailto:a@b.co")).toBe("mailto:a@b.co");
    expect(safeHref("javascript:alert(1)")).toBeUndefined();
    expect(safeHref("not a url")).toBeUndefined();
    expect(link("x", "javascript:alert(1)")).toEqual({ text: "x" });
  });

  it("draws clamped ascii bars", () => {
    expect(asciiBar(5, 10, 4)).toBe("██░░");
    expect(asciiBar(50, 10, 4)).toBe("████");
    expect(asciiBar(1, 0, 3)).toBe("░░░");
  });

  it("keys repeated content uniquely", () => {
    expect(withKeys(["a", "b", "a"], String).map(([key]) => key)).toEqual(["a#1", "b#1", "a#2"]);
  });
});

describe("CommandHistory", () => {
  it("recalls entries, keeps the draft and skips repeats", () => {
    const storage = new MemoryStorage();
    const history = new CommandHistory(storage);
    history.push("/projects");
    history.push("/projects");
    history.push("hello");

    expect(history.previous("draft")).toBe("hello");
    expect(history.previous("hello")).toBe("/projects");
    expect(history.previous("/projects")).toBe("/projects");
    expect(history.next()).toBe("hello");
    expect(history.next()).toBe("draft");
    expect(new CommandHistory(storage).items).toEqual(["/projects", "hello"]);
  });

  it("survives broken or failing storage", () => {
    const storage = new MemoryStorage();
    storage.setItem("portfolio.cli.history", "{oops");
    expect(new CommandHistory(storage).items).toEqual([]);
    storage.setItem("portfolio.cli.history", JSON.stringify(["ok", 3]));
    expect(new CommandHistory(storage).items).toEqual(["ok"]);

    const failing = new MemoryStorage();
    failing.setItem = () => {
      throw new Error("quota");
    };
    const history = new CommandHistory(failing);
    history.push("/help");
    expect(history.items).toEqual(["/help"]);
  });
});
