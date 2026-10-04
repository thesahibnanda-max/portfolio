import { useEffect, useState } from "react";
import ChatPanel from "./ChatPanel";

export const CHAT_TOGGLE_EVENT = "portfolio:chat-toggle";
export const CHAT_OPEN_EVENT = "portfolio:chat-open";

interface ChatAppProps {
  readonly ownerName: string;
}

export function ChatApp({ ownerName }: ChatAppProps) {
  const [isOpen, setIsOpen] = useState(true);
  const [openRequest, setOpenRequest] = useState(0);

  useEffect(() => {
    const onToggle = (): void => {
      const isShown = document.querySelector<HTMLDialogElement>("dialog[data-chat-dialog]")?.open === true;
      setIsOpen(!isShown);
      setOpenRequest((count) => count + 1);
    };
    const onOpen = (): void => {
      setIsOpen(true);
      setOpenRequest((count) => count + 1);
    };
    window.addEventListener(CHAT_TOGGLE_EVENT, onToggle);
    window.addEventListener(CHAT_OPEN_EVENT, onOpen);
    return () => {
      window.removeEventListener(CHAT_TOGGLE_EVENT, onToggle);
      window.removeEventListener(CHAT_OPEN_EVENT, onOpen);
    };
  }, []);

  return <ChatPanel isOpen={isOpen} openRequest={openRequest} onClose={() => setIsOpen(false)} ownerName={ownerName} />;
}
