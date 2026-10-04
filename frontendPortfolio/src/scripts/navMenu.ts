export function startNavMenu(): void {
  const dialog = document.querySelector<HTMLDialogElement>("[data-nav-menu]");
  const opener = document.querySelector<HTMLButtonElement>("[data-nav-menu-open]");
  if (dialog === null || opener === null) {
    return;
  }
  opener.addEventListener("click", () => dialog.showModal());
  dialog.querySelector("[data-nav-menu-close]")?.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (
      event.target === dialog ||
      (event.target instanceof Element && event.target.closest("[data-nav-menu-link]") !== null)
    ) {
      dialog.close();
    }
  });
  dialog.addEventListener("close", () => opener.focus({ preventScroll: true }));
}
