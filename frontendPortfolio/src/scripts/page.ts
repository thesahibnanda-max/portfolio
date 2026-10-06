import { startChatLauncher } from "./chatLauncher";
import { startContactLauncher } from "./contactLauncher";
import { startCopyButtons } from "./copy";
import { startCountUps } from "./countUp";
import { startNavMenu } from "./navMenu";
import { startReveals } from "./reveal";
import { startShortcutLabels } from "./shortcut";
import { startSmoothScroll } from "./smoothScroll";
import { startSpotlights } from "./spotlight";

startReveals();
startCountUps();
startSpotlights();
startCopyButtons();
startChatLauncher();
startNavMenu();
startContactLauncher();
startSmoothScroll();
startShortcutLabels();

function startDataRefresh(): void {
  void import("./liveStats").then((module) => module.startLiveStats());
  void import("./apiStatus").then((module) => module.startApiStatus());
}

if (typeof window.requestIdleCallback === "function") {
  window.requestIdleCallback(startDataRefresh, { timeout: 3000 });
} else {
  window.setTimeout(startDataRefresh, 1500);
}
