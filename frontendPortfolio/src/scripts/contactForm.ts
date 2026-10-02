import { ApiClient } from "../lib/api/client";
import { BACKEND_BASE_URL } from "../lib/config";
import {
  CONTACT_LIMITS,
  type ContactDraft,
  type ContactField,
  type ContactOutcome,
  type FieldErrors,
  sendContact,
} from "../lib/contact/contactForm";

const FIELDS: readonly ContactField[] = ["email", "subject", "message"];
const client = new ApiClient(BACKEND_BASE_URL);

class ContactFormController {
  readonly #form: HTMLFormElement;
  readonly #status: HTMLElement;
  readonly #submit: HTMLButtonElement;
  readonly #counter: HTMLElement | null;
  #countdown = 0;
  #isSending = false;

  constructor(form: HTMLFormElement) {
    this.#form = form;
    this.#status = this.#required("[data-contact-status]");
    this.#submit = this.#required("[data-contact-submit]");
    this.#counter = form.querySelector<HTMLElement>("[data-contact-counter]");
    form.addEventListener("input", (event) => this.#onInput(event));
  }

  async submit(): Promise<void> {
    if (this.#isSending || this.#countdown !== 0) {
      return;
    }
    this.#setSending(true);
    this.#showErrors({});
    const draft = this.#draft();
    let outcome: ContactOutcome;
    try {
      outcome = await sendContact(client, draft);
    } catch (error) {
      console.error("Contact form failed unexpectedly", error);
      outcome = { kind: "failed", message: "Something unexpected happened. Please try again." };
    } finally {
      this.#setSending(false);
    }
    this.#render(outcome);
  }

  #render(outcome: ContactOutcome): void {
    switch (outcome.kind) {
      case "sent":
        this.#form.reset();
        this.#updateCounter();
        this.#setStatus("success", `Message sent. I'll reply to ${outcome.response.reply_to} soon.`);
        return;
      case "invalid":
        this.#showErrors(outcome.errors);
        this.#setStatus("error", "Please fix the highlighted fields.");
        return;
      case "rate-limited":
        this.#startCountdown(outcome.retryAfterSeconds);
        return;
      case "unavailable":
        this.#setStatus(
          "error",
          "Couldn't send right now. Please email me directly using the address beside the form.",
        );
        return;
      case "failed":
        this.#setStatus("error", outcome.message);
        return;
    }
  }

  #draft(): ContactDraft {
    const data = new FormData(this.#form);
    return {
      email: String(data.get("email") ?? ""),
      subject: String(data.get("subject") ?? ""),
      message: String(data.get("message") ?? ""),
    };
  }

  #showErrors(errors: FieldErrors): void {
    let firstInvalid: HTMLElement | null = null;
    for (const field of FIELDS) {
      const input = this.#form.querySelector<HTMLInputElement | HTMLTextAreaElement>(`[name="${field}"]`);
      const message = this.#form.querySelector<HTMLElement>(`[data-field-error="${field}"]`);
      const error = errors[field];
      input?.setAttribute("aria-invalid", error === undefined ? "false" : "true");
      if (message !== null) {
        message.textContent = error ?? "";
      }
      if (error !== undefined && firstInvalid === null && input !== null) {
        firstInvalid = input;
      }
    }
    firstInvalid?.focus();
  }

  #onInput(event: Event): void {
    if (event.target instanceof HTMLTextAreaElement) {
      this.#updateCounter();
    }
    if (
      (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) &&
      event.target.getAttribute("aria-invalid") === "true"
    ) {
      event.target.setAttribute("aria-invalid", "false");
      const message = this.#form.querySelector<HTMLElement>(`[data-field-error="${event.target.name}"]`);
      if (message !== null) {
        message.textContent = "";
      }
    }
  }

  #updateCounter(): void {
    const message = this.#form.querySelector<HTMLTextAreaElement>('[name="message"]');
    if (this.#counter !== null && message !== null) {
      this.#counter.textContent = `${message.value.length} / ${CONTACT_LIMITS.message}`;
    }
  }

  #startCountdown(seconds: number): void {
    this.#countdown = seconds;
    this.#submit.disabled = true;
    const tick = (): void => {
      if (this.#countdown <= 0) {
        this.#countdown = 0;
        this.#submit.disabled = false;
        this.#setStatus("idle", "You can send again now.");
        return;
      }
      this.#setStatus("error", `That's a lot of messages. You can send again in ${this.#countdown}s.`);
      this.#countdown -= 1;
      window.setTimeout(tick, 1000);
    };
    tick();
  }

  #setSending(isSending: boolean): void {
    this.#isSending = isSending;
    this.#submit.disabled = isSending;
    this.#submit.toggleAttribute("data-sending", isSending);
    this.#form.setAttribute("aria-busy", String(isSending));
    if (isSending) {
      this.#setStatus("idle", "Sending…");
    }
  }

  #setStatus(tone: "idle" | "success" | "error", text: string): void {
    this.#status.dataset.tone = tone;
    this.#status.textContent = text;
  }

  #required<T extends HTMLElement>(selector: string): T {
    const element = this.#form.querySelector<T>(selector);
    if (element === null) {
      throw new Error(`Contact form is missing ${selector}`);
    }
    return element;
  }
}

export function mountContactForm(form: HTMLFormElement): ContactFormController {
  return new ContactFormController(form);
}
