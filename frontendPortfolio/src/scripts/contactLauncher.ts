type ContactModule = typeof import("./contactForm");
type Controller = ReturnType<ContactModule["mountContactForm"]>;

let controller: Promise<Controller> | null = null;

function mount(form: HTMLFormElement): Promise<Controller> {
  controller ??= import("./contactForm").then((module) => module.mountContactForm(form));
  return controller;
}

export function startContactLauncher(): void {
  const form = document.querySelector<HTMLFormElement>("[data-contact-form]");
  if (form === null) {
    return;
  }
  const warm = (): void => {
    mount(form).catch((error: unknown) => console.error("The contact form could not be loaded", error));
  };
  form.addEventListener("focusin", warm, { once: true });
  form.addEventListener("pointerenter", warm, { once: true });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    mount(form)
      .then((loaded) => loaded.submit())
      .catch((error: unknown) => console.error("The contact form could not be loaded", error));
  });
}
