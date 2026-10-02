"""
The chat service: answers one visitor message in a chat, either all at once
or as a stream, and saves the exchange.

Exports:
    ChatService: the facade with send_message and stream_message.
    ChatReplyStream: the stream returned by stream_message.
    MessageValidator, HistoryWindow: the input and history policies.
    ChatReply, ChatTokenEvent, ChatDoneEvent and the ChatStreamEvent alias:
    the results and stream events.
    ChatServiceError and its subclasses: the errors described under Errors.

A turn (shared by both methods):
    1. MessageValidator.validate: the message is trimmed; empty or
       whitespace-only raises EmptyChatMessageError, longer than
       max_message_chars raises ChatMessageTooLongError, so one message can
       never use up the token budget.
    2. ChatRepository.get_chat: the chat must belong to this live session
       (ChatNotFoundError otherwise). If saving this turn would exceed
       max_messages_per_chat, ChatFullError is raised.
    3. HistoryWindow.select: the newest max_history_messages messages, then
       the oldest dropped until they fit in max_history_chars, always keeping
       at least the newest one.
    4. Orchestrator.route: the guardrail and router. Its QueryScope decides
       what happens next.
    5. IN_SCOPE: ContextAggregator.aggregate renders only the requested
       knowledge domains (nothing for NONE), then the Worker AI answers.
       Any other scope (NOT_RELATED_TO_PORTFOLIO, PROMPT_INJECTION, UNSAFE):
       the answer is that scope's fallback message from config, and neither
       the data service nor the worker is called.
    6. ChatRepository.add_messages saves the user message and the answer
       together in one transaction, for fallback answers too, so the visitor's
       history always matches what they saw.
    Steps 1 to 5 run before either method returns or streams anything, so
    every validation, lookup, routing or data error is raised while the caller
    can still answer with a proper HTTP status.

send_message(session_id, chat_id, message) -> ChatReply
    ChatReply has the updated chat (with its messages), the answer, the
    scope and the required contexts.

stream_message(session_id, chat_id, message) -> ChatReplyStream
    with service.stream_message(session_id, chat_id, message) as stream:
        for event in stream:
            match event:
                case ChatTokenEvent(text=text):
                    send_token(text)
                case ChatDoneEvent(reply=reply):
                    send_done(reply)
    It yields ChatTokenEvent pieces of the answer and then exactly one
    ChatDoneEvent, sent only after the exchange has been saved. A fallback
    answer arrives as a single ChatTokenEvent followed by ChatDoneEvent, so a
    frontend handles every turn the same way. Entering opens the Worker's
    Groq stream; leaving always closes it. cancel() may be called from any
    thread: the reading thread then raises ChatStreamCancelledError. If the
    stream is cancelled, ends without Groq's [DONE] marker or fails, nothing
    is saved and the chat stays as it was, so the visitor can retry. A stream
    is read once and only inside its with block (ChatStreamStateError
    otherwise). reply and completed are available afterwards.

Construction:
    ChatService(
        *,
        repository, orchestrator, worker, context_aggregator,
        message_validator, history_window, fallback_messages,
        max_messages_per_chat,
    )
    repository: a main.package.repository.ChatRepository.
    orchestrator, worker: from main.package.ai.
    context_aggregator: main.package.service.context.ContextAggregator.
    message_validator: MessageValidator(*, max_message_chars).
    history_window: HistoryWindow(*, max_messages, max_chars).
    fallback_messages: exactly one non-empty message per QueryScope other
    than IN_SCOPE.
    max_messages_per_chat: int of at least 2.
    All limits and messages come from main.config.AppConfig.chat. A bad
    setting raises InvalidChatServiceSettingError.

Errors (all in exceptions.py, all subclasses of ChatServiceError):
    InvalidChatServiceSettingError: a constructor setting is invalid.
    InvalidChatMessageError: the message is invalid; EmptyChatMessageError
    and ChatMessageTooLongError (with max_chars and actual_chars) are its
    subclasses.
    ChatFullError: the chat has no room for another exchange (has
    max_messages).
    ChatStreamCancelledError: the stream was cancelled.
    ChatStreamStateError: the stream was used outside its contract.
    Errors from the repository (SessionNotFoundError, ChatNotFoundError),
    the orchestrator, worker, context and data services and Groq pass
    through unwrapped; each is already typed for the API's status mapping.

Thread safety:
    One ChatService can serve every thread on the free-threaded Python 3.14t
    build; it holds only its collaborators, which are all thread-safe. Each
    ChatReplyStream belongs to the thread reading it; only cancel() is meant
    for other threads.
"""

from .chat_reply_stream import ChatReplyStream
from .chat_service import ChatService
from .dto import ChatDoneEvent, ChatReply, ChatStreamEvent, ChatTokenEvent
from .exceptions import (
    ChatFullError,
    ChatMessageTooLongError,
    ChatServiceError,
    ChatStreamCancelledError,
    ChatStreamStateError,
    EmptyChatMessageError,
    InvalidChatMessageError,
    InvalidChatServiceSettingError,
)
from .history_window import HistoryWindow
from .message_validator import MessageValidator

__all__ = [
    "ChatService",
    "ChatReplyStream",
    "MessageValidator",
    "HistoryWindow",
    "ChatReply",
    "ChatTokenEvent",
    "ChatDoneEvent",
    "ChatStreamEvent",
    "ChatServiceError",
    "InvalidChatServiceSettingError",
    "InvalidChatMessageError",
    "EmptyChatMessageError",
    "ChatMessageTooLongError",
    "ChatFullError",
    "ChatStreamCancelledError",
    "ChatStreamStateError",
]
