import { startChatLauncher } from "./chatLauncher";
import { startContactLauncher } from "./contactLauncher";
import { startCopyButtons } from "./copy";
import { startCountUps } from "./countUp";
import { startReveals } from "./reveal";
import { startSmoothScroll } from "./smoothScroll";
import { startSpotlights } from "./spotlight";

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

startReveals(reducedMotion);
startCountUps(reducedMotion);
startSpotlights();
startCopyButtons();
startChatLauncher();
startContactLauncher();
startSmoothScroll(reducedMotion);

function startDataRefresh(): void {
  void import("./liveStats").then((module) => module.startLiveStats());
  void import("./apiStatus").then((module) => module.startApiStatus());
}

if (typeof window.requestIdleCallback === "function") {
  window.requestIdleCallback(startDataRefresh, { timeout: 3000 });
} else {
  window.setTimeout(startDataRefresh, 1500);
}
