import { shortcutLabel } from "../lib/platform";

interface NavigatorWithUAData extends Navigator {
  userAgentData?: { platform: string };
}

export function currentPlatform(): string {
  const nav: NavigatorWithUAData = navigator;
  return nav.userAgentData?.platform || nav.platform || nav.userAgent;
}

export function startShortcutLabels(): void {
  const platform = currentPlatform();
  for (const label of document.querySelectorAll<HTMLElement>("[data-shortcut-key]")) {
    label.textContent = shortcutLabel(platform, label.dataset.shortcutKey ?? "");
  }
}
