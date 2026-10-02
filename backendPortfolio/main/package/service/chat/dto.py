from pydantic import BaseModel, ConfigDict

from main.package.ai.common import ContextType
from main.package.ai.orchestrator import QueryScope
from main.package.repository import Chat


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChatReply(_FrozenModel):
    chat: Chat
    answer: str
    scope: QueryScope
    required_contexts: tuple[ContextType, ...]


class ChatTokenEvent(_FrozenModel):
    text: str


class ChatDoneEvent(_FrozenModel):
    reply: ChatReply


type ChatStreamEvent = ChatTokenEvent | ChatDoneEvent
