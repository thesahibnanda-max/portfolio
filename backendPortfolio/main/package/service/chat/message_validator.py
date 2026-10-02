from main.package.service.chat.exceptions import (
    ChatMessageTooLongError,
    EmptyChatMessageError,
    InvalidChatServiceSettingError,
)


class MessageValidator:
    def __init__(self, *, max_message_chars: int) -> None:
        if isinstance(max_message_chars, bool) or not isinstance(max_message_chars, int) or max_message_chars < 1:
            raise InvalidChatServiceSettingError("max_message_chars must be a positive int")

        self._max_message_chars = max_message_chars

    @property
    def max_message_chars(self) -> int:
        return self._max_message_chars

    def validate(self, message: str) -> str:
        if not isinstance(message, str) or not message.strip():
            raise EmptyChatMessageError("Message must not be empty")

        text = message.strip()
        if len(text) > self._max_message_chars:
            raise ChatMessageTooLongError(
                f"Message is {len(text)} characters; the limit is {self._max_message_chars}",
                max_chars=self._max_message_chars,
                actual_chars=len(text),
            )

        return text
