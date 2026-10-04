import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { buildRegistry, executorNames, runCommand } from "../../src/lib/cli/commands";
import {
  changePlugin,
  changeSetting,
  currentMode,
  cycleSetting,
  defaultSettings,
  isOn,
  isPluginEnabled,
  loadSettings,
  SETTINGS_STORAGE_KEY,
  saveSettings,
} from "../../src/lib/cli/settings";
import { CONTEXT, contextFor, DATA, SETTINGS } from "./cliData";
import { MemoryStorage } from "./support";

const BACKEND_MANIFEST = JSON.parse(
  await readFile(new URL("../../../backendPortfolio/main/package/static/cli.json", import.meta.url), "utf8"),
);
const BACKEND_FORTUNES = (
  await readFile(new URL("../../../backendPortfolio/main/package/static/fortunes.md", import.meta.url), "utf8")
)
  .split("\n")
  .filter((line) => line.startsWith("- "))
  .map((line) => line.slice(2).trim());

function snakeCase(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(snakeCase);
  }
  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`),
        snakeCase(item),
      ]),
    );
  }
  return value;
}

function run(input: string, context = CONTEXT) {
  const [name = "", ...args] = input.slice(1).split(" ");
  return runCommand(name, { args, rest: args.join(" ") }, context);
}

describe("manifest parity", () => {
  it("the test fixture matches the backend's cli.json and fortunes.md", () => {
    const { fortunes, ...manifest } = DATA.manifest;
    expect(manifest).toEqual(snakeCase(BACKEND_MANIFEST));
    expect(fortunes).toEqual(BACKEND_FORTUNES);
  });

  it("every skill has an executor and every executor a skill", () => {
    expect([...executorNames()].sort()).toEqual(DATA.manifest.skills.map((skill) => skill.name).sort());
    expect(CONTEXT.registry.all).toHaveLength(DATA.manifest.skills.length);
  });
});

describe("settings", () => {
  it("defaults come from the manifest", () => {
    expect(SETTINGS.values).toMatchObject({ mode: "default", answers: "concise", accent: "amber" });
    expect(SETTINGS.plugins).toMatchObject({ core: true, extras: false });
    expect(currentMode(SETTINGS)).toBe("default");
    expect(isOn(SETTINGS, "autocomplete")).toBe(true);
  });

  it("loads valid stored values and ignores everything else", () => {
    const storage = new MemoryStorage();
    storage.setItem(
      SETTINGS_STORAGE_KEY,
      JSON.stringify({
        values: { answers: "detailed", accent: "pink", bogus: "x" },
        plugins: { extras: true, core: false, ghost: true },
      }),
    );
    const loaded = loadSettings(storage, DATA.manifest);

    expect(loaded.values).toMatchObject({ answers: "detailed", accent: "amber" });
    expect(loaded.values).not.toHaveProperty("bogus");
    expect(loaded.plugins).toMatchObject({ extras: true, core: true });
    expect(loaded.plugins).not.toHaveProperty("ghost");
  });

  it("falls back to defaults for broken storage and survives failed saves", () => {
    for (const stored of ["{oops", "42", "null", JSON.stringify({ values: [], plugins: "x" })]) {
      const storage = new MemoryStorage();
      storage.setItem(SETTINGS_STORAGE_KEY, stored);
      expect(loadSettings(storage, DATA.manifest)).toEqual(SETTINGS);
    }
    const failing = new MemoryStorage();
    failing.setItem = () => {
      throw new Error("quota");
    };
    saveSettings(failing, SETTINGS);
    const storage = new MemoryStorage();
    saveSettings(storage, SETTINGS);
    expect(loadSettings(storage, DATA.manifest)).toEqual(SETTINGS);
  });

  it("changes, cycles and validates settings", () => {
    const changed = changeSetting(SETTINGS, DATA.manifest, "ANSWERS", "Detailed");
    expect(changed).toMatchObject({ ok: true, message: "Answer length set to detailed." });
    expect(changeSetting(SETTINGS, DATA.manifest, "answers", "huge")).toEqual({
      ok: false,
      message: "answers can be concise, detailed.",
    });
    expect(changeSetting(SETTINGS, DATA.manifest, "colour", "red").ok).toBe(false);

    const auto = cycleSetting(SETTINGS, DATA.manifest, "mode");
    expect(currentMode(auto)).toBe("auto-run");
    expect(currentMode(cycleSetting(cycleSetting(auto, DATA.manifest, "mode"), DATA.manifest, "mode"))).toBe("default");
    expect(currentMode(cycleSetting(SETTINGS, DATA.manifest, "mode", -1))).toBe("plan");
    expect(cycleSetting(SETTINGS, DATA.manifest, "nope")).toBe(SETTINGS);
  });

  it("turns plugins on and off but never core", () => {
    const extras = changePlugin(SETTINGS, DATA.manifest, "extras", true);
    expect(extras.ok && isPluginEnabled(extras.settings, "extras")).toBe(true);
    expect(changePlugin(SETTINGS, DATA.manifest, "core", false)).toEqual({
      ok: false,
      message: "The core plugin is always on.",
    });
    expect(changePlugin(SETTINGS, DATA.manifest, "ghost", true).ok).toBe(false);
  });
});

describe("plugins and settings skills", () => {
  it("disabled plugins hide their skills and explain how to enable them", () => {
    expect(CONTEXT.registry.commands.map((command) => command.name)).not.toContain("neofetch");
    const effect = run("/neofetch");
    expect(JSON.stringify(effect)).toContain("part of the extras plugin, which is off");
    expect(JSON.stringify(effect)).toContain("/plugins enable extras");
  });

  it("/config opens the panel, shows a setting, or changes it", () => {
    expect(run("/config")).toEqual({ kind: "config-panel" });
    expect(JSON.stringify(run("/config answers"))).toContain("concise · detailed");
    expect(JSON.stringify(run("/config nope"))).toContain('Unknown setting \\"nope\\"');
    const changed = run("/config answers detailed");
    expect(changed.kind).toBe("settings");
    expect(changed.kind === "settings" && changed.settings.values.answers).toBe("detailed");
    expect(JSON.stringify(run("/config answers huge"))).toContain("answers can be concise, detailed.");
  });

  it("/plugins lists, enables and disables plugins", () => {
    const listed = JSON.stringify(run("/plugins"));
    expect(listed).toContain("extras");
    expect(listed).toContain("(always on)");
    expect(listed).toContain("18 of 20 skills on");
    const enabled = run("/plugins enable extras");
    expect(enabled.kind === "settings" && isPluginEnabled(enabled.settings, "extras")).toBe(true);
    expect(JSON.stringify(run("/plugins disable core"))).toContain("always on");
    expect(JSON.stringify(run("/plugins toggle extras"))).toContain("Usage: /plugins enable");
    expect(JSON.stringify(run("/plugins enable"))).toContain("Usage");
  });

  it("/neofetch and /fortune work once extras is on", () => {
    const change = changePlugin(SETTINGS, DATA.manifest, "extras", true);
    if (!change.ok) {
      throw new Error(change.message);
    }
    const context = contextFor(change.settings);
    const card = JSON.stringify(run("/neofetch", context));
    expect(card).toContain("sahib@portfolio");
    expect(card).toContain("Codeforces");
    expect(JSON.stringify(run("/fortune", context))).toContain(DATA.manifest.fortunes[0] ?? "");
    expect(buildRegistry(DATA.manifest, change.settings).commands).toHaveLength(20);
  });

  it("/help counts the skills that are on", () => {
    expect(JSON.stringify(run("/help"))).toContain("18 of 20 skills on · 5 plugins (4 on)");
  });
});
