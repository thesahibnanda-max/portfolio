import { useEffect, useState } from "react";
import ChatPanel from "./ChatPanel";

export const CHAT_TOGGLE_EVENT = "portfolio:chat-toggle";
export const CHAT_OPEN_EVENT = "portfolio:chat-open";

interface ChatAppProps {
  readonly ownerName: string;
}

export function ChatApp({ ownerName }: ChatAppProps) {
  const [isOpen, setIsOpen] = useState(true);

  useEffect(() => {
    const onToggle = (): void => setIsOpen((current) => !current);
    const onOpen = (): void => setIsOpen(true);
    window.addEventListener(CHAT_TOGGLE_EVENT, onToggle);
    window.addEventListener(CHAT_OPEN_EVENT, onOpen);
    return () => {
      window.removeEventListener(CHAT_TOGGLE_EVENT, onToggle);
      window.removeEventListener(CHAT_OPEN_EVENT, onOpen);
    };
  }, []);

  return <ChatPanel isOpen={isOpen} onClose={() => setIsOpen(false)} ownerName={ownerName} />;
}
