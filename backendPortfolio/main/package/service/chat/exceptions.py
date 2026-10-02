class ChatServiceError(Exception):
    pass


class InvalidChatServiceSettingError(ChatServiceError):
    pass


class InvalidChatMessageError(ChatServiceError):
    pass


class EmptyChatMessageError(InvalidChatMessageError):
    pass


class ChatMessageTooLongError(InvalidChatMessageError):
    def __init__(self, message: str, *, max_chars: int, actual_chars: int) -> None:
        super().__init__(message)
        self.max_chars = max_chars
        self.actual_chars = actual_chars


class ChatFullError(ChatServiceError):
    def __init__(self, message: str, *, max_messages: int) -> None:
        super().__init__(message)
        self.max_messages = max_messages


class ChatStreamStateError(ChatServiceError):
    pass


class ChatStreamCancelledError(ChatServiceError):
    pass
