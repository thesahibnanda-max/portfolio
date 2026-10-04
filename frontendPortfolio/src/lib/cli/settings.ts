import { z } from "zod";
import type { CliManifest } from "../api/schemas";
import type { KeyValueStorage } from "../api/session";

export const SETTINGS_STORAGE_KEY = "portfolio.cli.config";
export const MODES = ["default", "auto-run", "plan"] as const;
export type CliMode = (typeof MODES)[number];

export interface CliSettings {
  readonly values: Readonly<Record<string, string>>;
  readonly plugins: Readonly<Record<string, boolean>>;
}

export type SettingsChange =
  | { readonly ok: true; readonly settings: CliSettings; readonly message: string }
  | { readonly ok: false; readonly message: string };

export function defaultSettings(manifest: CliManifest): CliSettings {
  return {
    values: Object.fromEntries(manifest.settings.map((setting) => [setting.key, setting.default])),
    plugins: Object.fromEntries(manifest.plugins.map((plugin) => [plugin.name, plugin.enabled_by_default])),
  };
}

export function loadSettings(storage: KeyValueStorage, manifest: CliManifest): CliSettings {
  const defaults = defaultSettings(manifest);
  const stored = readStored(storage);
  if (stored === null) {
    return defaults;
  }
  const values = { ...defaults.values };
  for (const setting of manifest.settings) {
    const value = stored.values[setting.key];
    if (typeof value === "string" && setting.options.includes(value)) {
      values[setting.key] = value;
    }
  }
  const plugins = { ...defaults.plugins };
  for (const plugin of manifest.plugins) {
    const enabled = stored.plugins[plugin.name];
    if (typeof enabled === "boolean" && plugin.removable) {
      plugins[plugin.name] = enabled;
    }
  }
  return { values, plugins };
}

export function saveSettings(storage: KeyValueStorage, settings: CliSettings): void {
  try {
    storage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch (error) {
    console.warn("Terminal settings could not be saved", error);
  }
}

export function changeSetting(
  settings: CliSettings,
  manifest: CliManifest,
  key: string,
  value: string,
): SettingsChange {
  const setting = manifest.settings.find((candidate) => candidate.key.toLowerCase() === key.toLowerCase());
  if (setting === undefined) {
    return {
      ok: false,
      message: `Unknown setting "${key}". Settings: ${manifest.settings.map((item) => item.key).join(", ")}.`,
    };
  }
  const option = setting.options.find((candidate) => candidate.toLowerCase() === value.toLowerCase());
  if (option === undefined) {
    return { ok: false, message: `${setting.key} can be ${setting.options.join(", ")}.` };
  }
  return {
    ok: true,
    settings: { ...settings, values: { ...settings.values, [setting.key]: option } },
    message: `${setting.label} set to ${option}.`,
  };
}

export function cycleSetting(settings: CliSettings, manifest: CliManifest, key: string, step = 1): CliSettings {
  const setting = manifest.settings.find((candidate) => candidate.key === key);
  if (setting === undefined) {
    return settings;
  }
  const index = setting.options.indexOf(settingValue(settings, key));
  const next = setting.options[(index + step + setting.options.length) % setting.options.length] ?? setting.default;
  return { ...settings, values: { ...settings.values, [key]: next } };
}

export function changePlugin(
  settings: CliSettings,
  manifest: CliManifest,
  name: string,
  enabled: boolean,
): SettingsChange {
  const plugin = manifest.plugins.find((candidate) => candidate.name === name.toLowerCase());
  if (plugin === undefined) {
    return {
      ok: false,
      message: `Unknown plugin "${name}". Plugins: ${manifest.plugins.map((item) => item.name).join(", ")}.`,
    };
  }
  if (!plugin.removable && !enabled) {
    return { ok: false, message: `The ${plugin.name} plugin is always on.` };
  }
  return {
    ok: true,
    settings: { ...settings, plugins: { ...settings.plugins, [plugin.name]: enabled } },
    message: `Plugin ${plugin.name} ${enabled ? "enabled" : "disabled"}.`,
  };
}

export function settingValue(settings: CliSettings, key: string): string {
  return settings.values[key] ?? "";
}

export function isOn(settings: CliSettings, key: string): boolean {
  return settingValue(settings, key) !== "off";
}

export function currentMode(settings: CliSettings): CliMode {
  const value = settingValue(settings, "mode");
  return MODES.find((mode) => mode === value) ?? "default";
}

export function isPluginEnabled(settings: CliSettings, name: string): boolean {
  return settings.plugins[name] === true;
}

const storedSchema = z.object({
  values: z.record(z.string(), z.unknown()).catch({}),
  plugins: z.record(z.string(), z.unknown()).catch({}),
});

function readStored(storage: KeyValueStorage): z.infer<typeof storedSchema> | null {
  try {
    const result = storedSchema.safeParse(JSON.parse(storage.getItem(SETTINGS_STORAGE_KEY) ?? "null"));
    return result.success ? result.data : null;
  } catch {
    return null;
  }
}
