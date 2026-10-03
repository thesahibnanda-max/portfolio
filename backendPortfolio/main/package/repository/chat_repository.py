from abc import ABC, abstractmethod
from collections.abc import Sequence

from main.package.repository.dto import Chat, ChatOrigin, ChatSummary, NewMessage, Session


class ChatRepository(ABC):
    @abstractmethod
    def create_session(self) -> Session:
        ...

    @abstractmethod
    def get_session(self, session_id: str) -> Session:
        ...

    @abstractmethod
    def create_chat(self, session_id: str, title: str = "New chat", origin: ChatOrigin = ChatOrigin.CHAT) -> ChatSummary:
        ...

    @abstractmethod
    def list_chats(self, session_id: str) -> tuple[ChatSummary, ...]:
        ...

    @abstractmethod
    def get_chat(self, session_id: str, chat_id: str) -> Chat:
        ...

    @abstractmethod
    def rename_chat(self, session_id: str, chat_id: str, title: str) -> ChatSummary:
        ...

    @abstractmethod
    def add_messages(self, session_id: str, chat_id: str, messages: Sequence[NewMessage]) -> Chat:
        ...

    @abstractmethod
    def delete_chat(self, session_id: str, chat_id: str) -> None:
        ...

    @abstractmethod
    def delete_expired_sessions(self) -> int:
        ...

    @abstractmethod
    def close(self) -> None:
        ...
