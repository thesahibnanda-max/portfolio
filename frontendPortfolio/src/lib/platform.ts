const APPLE_PLATFORM = /mac|iphone|ipad|ipod/i;

export function isApplePlatform(platform: string): boolean {
  return APPLE_PLATFORM.test(platform);
}

export function shortcutLabel(platform: string, key: string): string {
  return isApplePlatform(platform) ? `⌘${key}` : `Ctrl ${key}`;
}

export function isShortcutModifier(platform: string, event: Pick<KeyboardEvent, "metaKey" | "ctrlKey">): boolean {
  return isApplePlatform(platform) ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
}
