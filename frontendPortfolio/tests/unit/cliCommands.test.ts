import { describe, expect, it } from "vitest";
import type { Block } from "../../src/lib/cli/blocks";
import {
  type CommandEffect,
  closestCommand,
  editDistance,
  findCommand,
  runCommand,
  statsBlocks,
} from "../../src/lib/cli/commands";
import { parseInput } from "../../src/lib/cli/parser";
import { CONTEXT, DATA } from "./cliData";

function run(input: string): CommandEffect {
  const parsed = parseInput(input);
  return runCommand(parsed.name, { args: parsed.args, rest: parsed.rest }, CONTEXT);
}

function printed(effect: CommandEffect): readonly Block[] {
  if (effect.kind !== "print") {
    throw new Error(`expected print, got ${effect.kind}`);
  }
  return effect.blocks;
}

function textOf(blocks: readonly Block[]): string {
  return JSON.stringify(blocks);
}

describe("command registry", () => {
  it("has unique names and aliases", () => {
    const names = CONTEXT.registry.all.flatMap((command) => [command.name, ...command.aliases]);
    expect(new Set(names).size).toBe(names.length);
  });

  it("finds commands by name or alias, case-insensitively", () => {
    expect(findCommand(CONTEXT.registry, "EXP")?.name).toBe("experience");
    expect(findCommand(CONTEXT.registry, "quit")?.name).toBe("go-back");
    expect(findCommand(CONTEXT.registry, "nope")).toBeUndefined();
  });

  it("suggests the closest command for typos", () => {
    expect(closestCommand(CONTEXT.registry, "projcts")?.name).toBe("projects");
    expect(closestCommand(CONTEXT.registry, "xyzzy")).toBeUndefined();
    expect(editDistance("kitten", "sitting")).toBe(3);
    const unknown = textOf(printed(run("/projcts")));
    expect(unknown).toContain("Unknown command /projcts.");
    expect(unknown).toContain("Did you mean /projects [name]?");
    expect(textOf(printed(run("/xyzzy")))).toContain("Type /help");
  });
});

describe("explore commands", () => {
  it("/help lists every command group and shortcut", () => {
    const help = textOf(printed(run("/help")));
    for (const command of CONTEXT.registry.commands) {
      expect(help).toContain(command.usage);
    }
    expect(help).toContain("Ctrl+L");
    expect(textOf(printed(run("?")))).toBe(help);
  });

  it("/whoami summarises the current role and links", () => {
    const text = textOf(printed(run("/whoami")));
    expect(text).toContain(DATA.ownerName);
    expect(text).toContain("CheQ");
    expect(text).toContain("mailto:");
    expect(text).toContain("linkedin.com/in/sahib-nanda");
    expect(text).toContain('"GitHub 1"');
    expect(text).toContain('"GitHub 2"');
  });

  it("/experience lists every role and details every role at one company", () => {
    expect(textOf(printed(run("/experience")))).toContain("TatavGyan");
    const cred = printed(run("/experience cred"));
    expect(cred.filter((block) => block.kind === "heading")).toHaveLength(3);
    expect(textOf(cred)).not.toContain("PwC");
  });

  it("/projects shows one project by a partial name", () => {
    const relay = textOf(printed(run("/projects relay")));
    expect(relay).toContain("Relay - Multi-Agent Collaboration for AI Coding CLIs");
    expect(relay).toContain('"kind":"chips"');
    expect(textOf(printed(run("/projects")))).toContain("fastclient");
    expect(printed(run("/projects"))[1]).toMatchObject({ kind: "table" });
    expect(printed(run("/experience"))[1]).toMatchObject({ kind: "table" });
  });

  it("explains misses with the valid options", () => {
    const miss = textOf(printed(run("/projects quantum")));
    expect(miss).toContain('No project matches \\"quantum\\".');
    expect(miss).toContain("Relay");
    expect(textOf(printed(run("/experience google")))).toContain("CRED");
    expect(textOf(printed(run("/skills cooking")))).toContain("Backend");
  });

  it("/skills, /education and /achievements print their data", () => {
    expect(textOf(printed(run("/skills")))).toContain("Distributed Systems");
    expect(textOf(printed(run("/skills backend")))).toContain('"kind":"chips"');
    expect(textOf(printed(run("/education")))).toContain("University of Petroleum and Energy Studies");
    expect(printed(run("/achievements"))[1]).toMatchObject({ kind: "list" });
  });

  it("/stats picks a platform by prefix", () => {
    expect(run("/stats")).toEqual({ kind: "stats", target: "all" });
    expect(run("/stats code")).toEqual({ kind: "stats", target: "codeforces" });
    expect(textOf(printed(run("/stats chess")))).toContain("Unknown platform");
  });

  it("renders stats with bars, rating changes and top repositories", () => {
    const all = textOf(statsBlocks("all", DATA));
    expect(all).toContain("LeetCode · @imsahibnanda");
    expect(all).toContain("Codeforces · shisukenohara");
    expect(all).toContain("GitHub · @");
    expect(statsBlocks("leetcode", DATA).some((block) => block.kind === "bars")).toBe(true);
    expect(textOf(statsBlocks("codeforces", DATA))).not.toContain("LeetCode");
    expect(statsBlocks("github", DATA).some((block) => block.kind === "bars")).toBe(false);
    expect(textOf(statsBlocks("github", DATA))).toContain("★ ");
  });
});

describe("actions", () => {
  it("/resume and /contact mail open URLs", () => {
    expect(run("/resume")).toMatchObject({ kind: "open-url", url: DATA.resumeUrl });
    expect(run("/contact mail")).toMatchObject({
      kind: "open-url",
      url: `mailto:${DATA.profile.profile_details.email}`,
    });
    expect(textOf(printed(run("/contact")))).toContain("Email");
  });

  it("/ask needs a question", () => {
    expect(run("/ask what is relay?")).toEqual({ kind: "ask", question: "what is relay?" });
    expect(textOf(printed(run("/ask")))).toContain("Ask what?");
  });

  it("session commands map to effects", () => {
    expect(run("/clear")).toEqual({ kind: "clear" });
    expect(run("/new")).toEqual({ kind: "new-chat" });
    expect(run("/history")).toEqual({ kind: "list-chats" });
    expect(run("/open 2")).toEqual({ kind: "open-chat", index: 2 });
    expect(textOf(printed(run("/open zero")))).toContain("Usage: /open <n>");
    expect(textOf(printed(run("/open 0")))).toContain("Usage");
    for (const alias of ["/go-back", "/exit", "/home", "/quit"]) {
      expect(run(alias)).toMatchObject({ kind: "navigate", href: "/" });
    }
  });
});
