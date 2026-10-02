from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict

type MessageRole = Literal["user", "assistant"]


def _require_text(value: str) -> str:
    if not value.strip():
        raise ValueError("content must not be blank")

    return value


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Session(_FrozenModel):
    session_id: str
    created_at: datetime
    expires_at: datetime


class ChatSummary(_FrozenModel):
    chat_id: str
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class StoredMessage(_FrozenModel):
    message_id: int
    role: MessageRole
    content: str
    created_at: datetime


class Chat(ChatSummary):
    messages: tuple[StoredMessage, ...]


class NewMessage(_FrozenModel):
    role: MessageRole
    content: Annotated[str, AfterValidator(_require_text)]
