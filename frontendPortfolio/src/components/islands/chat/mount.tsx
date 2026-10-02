import { createRoot } from "react-dom/client";
import { ChatApp } from "./ChatApp";

export { CHAT_OPEN_EVENT, CHAT_TOGGLE_EVENT } from "./ChatApp";

export function mountChat(container: HTMLElement, ownerName: string): void {
  createRoot(container).render(<ChatApp ownerName={ownerName} />);
}
