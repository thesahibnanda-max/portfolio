from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from types import MappingProxyType

from main.package.ai.common import ChatMessage, Surface
from main.package.ai.orchestrator import Orchestrator, OrchestratorDecision, QueryScope
from main.package.ai.worker import Worker
from main.package.repository import ChatRepository, NewMessage
from main.package.service.chat.chat_reply_stream import ChatReplyStream
from main.package.service.chat.dto import ChatReply
from main.package.service.chat.exceptions import ChatFullError, InvalidChatServiceSettingError
from main.package.service.chat.history_window import HistoryWindow
from main.package.service.chat.message_validator import MessageValidator
from main.package.service.context import ContextAggregator

_MESSAGES_PER_TURN = 2


@dataclass(frozen=True)
class _Turn:
    session_id: str
    chat_id: str
    message: str
    history: tuple[ChatMessage, ...]
    surface: Surface
    decision: OrchestratorDecision
    context: str


class ChatService:
    def __init__(
        self,
        *,
        repository: ChatRepository,
        orchestrator: Orchestrator,
        worker: Worker,
        context_aggregator: ContextAggregator,
        message_validator: MessageValidator,
        history_window: HistoryWindow,
        fallback_messages: Mapping[QueryScope, str],
        max_messages_per_chat: int,
    ) -> None:
        self._require_instance("repository", repository, ChatRepository)
        self._require_instance("orchestrator", orchestrator, Orchestrator)
        self._require_instance("worker", worker, Worker)
        self._require_instance("context_aggregator", context_aggregator, ContextAggregator)
        self._require_instance("message_validator", message_validator, MessageValidator)
        self._require_instance("history_window", history_window, HistoryWindow)

        if isinstance(max_messages_per_chat, bool) or not isinstance(max_messages_per_chat, int) or max_messages_per_chat < _MESSAGES_PER_TURN:
            raise InvalidChatServiceSettingError(f"max_messages_per_chat must be an int of at least {_MESSAGES_PER_TURN}")

        self._repository = repository
        self._orchestrator = orchestrator
        self._worker = worker
        self._context_aggregator = context_aggregator
        self._message_validator = message_validator
        self._history_window = history_window
        self._fallback_messages = self._require_fallback_messages(fallback_messages)
        self._max_messages_per_chat = max_messages_per_chat

    def send_message(self, session_id: str, chat_id: str, message: str) -> ChatReply:
        turn = self._prepare_turn(session_id, chat_id, message)

        if turn.decision.is_in_scope:
            answer = self._worker.respond(turn.message, turn.history, turn.context, turn.surface)
        else:
            answer = self._fallback_messages[turn.decision.scope]

        return self._complete_turn(turn, answer)

    def stream_message(self, session_id: str, chat_id: str, message: str) -> ChatReplyStream:
        turn = self._prepare_turn(session_id, chat_id, message)
        complete = partial(self._complete_turn, turn)

        if turn.decision.is_in_scope:
            return ChatReplyStream(
                complete=complete,
                answer_stream=self._worker.stream(turn.message, turn.history, turn.context, turn.surface),
            )

        return ChatReplyStream(complete=complete, fallback_answer=self._fallback_messages[turn.decision.scope])

    def _prepare_turn(self, session_id: str, chat_id: str, message: str) -> _Turn:
        text = self._message_validator.validate(message)
        chat = self._repository.get_chat(session_id, chat_id)

        if len(chat.messages) + _MESSAGES_PER_TURN > self._max_messages_per_chat:
            raise ChatFullError(
                f"Chat {chat_id} has reached its limit of {self._max_messages_per_chat} messages",
                max_messages=self._max_messages_per_chat,
            )

        history = self._history_window.select(chat.messages)
        surface = Surface(chat.origin.value)
        decision = self._orchestrator.route(text, history, surface)
        context = self._context_aggregator.aggregate(decision.required_contexts) if decision.needs_context else ""

        return _Turn(
            session_id=session_id,
            chat_id=chat_id,
            message=text,
            history=history,
            surface=surface,
            decision=decision,
            context=context,
        )

    def _complete_turn(self, turn: _Turn, answer: str) -> ChatReply:
        chat = self._repository.add_messages(
            turn.session_id,
            turn.chat_id,
            [NewMessage(role="user", content=turn.message), NewMessage(role="assistant", content=answer)],
        )

        return ChatReply(
            chat=chat,
            answer=answer,
            scope=turn.decision.scope,
            required_contexts=turn.decision.required_contexts,
        )

    @staticmethod
    def _require_instance(name: str, value: object, expected: type) -> None:
        if not isinstance(value, expected):
            raise InvalidChatServiceSettingError(f"{name} must be a {expected.__name__}")

    @staticmethod
    def _require_fallback_messages(fallback_messages: Mapping[QueryScope, str]) -> Mapping[QueryScope, str]:
        if not isinstance(fallback_messages, Mapping):
            raise InvalidChatServiceSettingError("fallback_messages must be a mapping of QueryScope to message")

        expected = set(QueryScope) - {QueryScope.IN_SCOPE}
        if set(fallback_messages) != expected:
            raise InvalidChatServiceSettingError(
                f"fallback_messages must have exactly one message for each of {sorted(expected)}"
            )

        if not all(isinstance(text, str) and text.strip() for text in fallback_messages.values()):
            raise InvalidChatServiceSettingError("every fallback message must be a non-empty string")

        return MappingProxyType({QueryScope(scope): text.strip() for scope, text in fallback_messages.items()})
