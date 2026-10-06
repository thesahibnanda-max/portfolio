import { describe, expect, it } from "vitest";
import { isApplePlatform, isShortcutModifier, shortcutLabel } from "../../src/lib/platform";

describe("isApplePlatform", () => {
  it.each(["macOS", "MacIntel", "iPhone", "iPad"])("treats %s as Apple", (platform) => {
    expect(isApplePlatform(platform)).toBe(true);
  });

  it.each(["Windows", "Win32", "Linux", "Linux x86_64", "Chrome OS", ""])("treats %s as not Apple", (platform) => {
    expect(isApplePlatform(platform)).toBe(false);
  });
});

describe("shortcutLabel", () => {
  it("uses the command symbol on macOS", () => {
    expect(shortcutLabel("macOS", "K")).toBe("⌘K");
  });

  it("uses Ctrl on Windows and Linux", () => {
    expect(shortcutLabel("Windows", "K")).toBe("Ctrl K");
    expect(shortcutLabel("Linux", "K")).toBe("Ctrl K");
  });
});

describe("isShortcutModifier", () => {
  const cmd = { metaKey: true, ctrlKey: false };
  const ctrl = { metaKey: false, ctrlKey: true };

  it("accepts only Cmd on macOS", () => {
    expect(isShortcutModifier("macOS", cmd)).toBe(true);
    expect(isShortcutModifier("macOS", ctrl)).toBe(false);
  });

  it("accepts only Ctrl on Windows and Linux", () => {
    expect(isShortcutModifier("Windows", ctrl)).toBe(true);
    expect(isShortcutModifier("Linux", ctrl)).toBe(true);
    expect(isShortcutModifier("Linux", cmd)).toBe(false);
  });
});
