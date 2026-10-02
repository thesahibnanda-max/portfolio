const RESET_MS = 1800;

export function startCopyButtons(): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>("[data-copy]")) {
    const label = button.querySelector<HTMLElement>("[data-copy-label]");
    const original = label?.textContent ?? "";
    button.addEventListener("click", async () => {
      const value = button.dataset.copy ?? "";
      try {
        await navigator.clipboard.writeText(value);
        if (label !== null) {
          label.textContent = "Copied to clipboard";
        }
      } catch {
        window.location.href = `mailto:${value}`;
        return;
      }
      window.setTimeout(() => {
        if (label !== null) {
          label.textContent = original;
        }
      }, RESET_MS);
    });
  }
}
