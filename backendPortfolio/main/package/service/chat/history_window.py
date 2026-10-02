from collections import deque
from collections.abc import Sequence

from main.package.ai.common import ChatMessage
from main.package.repository import StoredMessage
from main.package.service.chat.exceptions import InvalidChatServiceSettingError


def _require_positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidChatServiceSettingError(f"{name} must be a positive int")

    return value


class HistoryWindow:
    def __init__(self, *, max_messages: int, max_chars: int) -> None:
        self._max_messages = _require_positive_int("max_messages", max_messages)
        self._max_chars = _require_positive_int("max_chars", max_chars)

    def select(self, messages: Sequence[StoredMessage]) -> tuple[ChatMessage, ...]:
        kept = deque(messages[-self._max_messages:])
        total_chars = sum(len(message.content) for message in kept)

        while total_chars > self._max_chars and len(kept) > 1:
            total_chars -= len(kept.popleft().content)

        return tuple(ChatMessage(role=message.role, content=message.content) for message in kept)
