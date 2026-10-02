import { z } from "zod";
import { ApiClient } from "../lib/api/client";
import { BACKEND_BASE_URL } from "../lib/config";

const healthSchema = z.object({ status: z.string() });

export async function startApiStatus(): Promise<void> {
  const dot = document.querySelector<HTMLElement>("[data-api-status-dot]");
  const label = document.querySelector<HTMLElement>("[data-api-status-label]");
  if (dot === null || label === null) {
    return;
  }
  try {
    const health = await new ApiClient(BACKEND_BASE_URL).request("/health", healthSchema);
    const up = health.status === "UP";
    dot.className = `size-1.5 rounded-full ${up ? "bg-success" : "bg-danger"}`;
    label.textContent = `API status: ${up ? "operational" : health.status.toLowerCase()}`;
  } catch {
    dot.className = "size-1.5 rounded-full bg-danger";
    label.textContent = "API status: unreachable";
  }
}
