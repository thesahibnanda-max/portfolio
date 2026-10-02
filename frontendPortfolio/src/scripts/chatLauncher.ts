type ChatModule = typeof import("../components/islands/chat/mount");

let loading: Promise<ChatModule> | null = null;
let mounted = false;

function loadChat(): Promise<ChatModule> {
  loading ??= import("../components/islands/chat/mount");
  return loading;
}

async function openChat(toggle: boolean): Promise<void> {
  const container = document.querySelector<HTMLElement>("[data-chat-root]");
  if (container === null) {
    return;
  }
  const chat = await loadChat();
  if (!mounted) {
    mounted = true;
    chat.mountChat(container, container.dataset.ownerName ?? "me");
    return;
  }
  window.dispatchEvent(new Event(toggle ? chat.CHAT_TOGGLE_EVENT : chat.CHAT_OPEN_EVENT));
}

function reportFailure(error: unknown): void {
  console.error("The chat could not be loaded", error);
}

export function startChatLauncher(): void {
  window.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openChat(true).catch(reportFailure);
    }
  });
  document.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest("[data-open-chat]") !== null) {
      event.preventDefault();
      openChat(false).catch(reportFailure);
    }
  });
  for (const trigger of document.querySelectorAll<HTMLElement>("[data-open-chat]")) {
    trigger.addEventListener("pointerenter", () => void loadChat().catch(reportFailure), { once: true });
    trigger.addEventListener("focus", () => void loadChat().catch(reportFailure), { once: true });
  }
}
