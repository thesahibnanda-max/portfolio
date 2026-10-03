from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from types import MappingProxyType

from main.package.ai.agent import Agent, MarkedAnswerStream
from main.package.ai.common import ChatMessage, ContextType
from main.package.ai.orchestrator import QueryScope
from main.package.repository import ChatRepository, NewMessage
from main.package.service.agent.answer_cache import AnswerCache
from main.package.service.agent.dto import AgentTurnStream, GateDecision
from main.package.service.agent.exceptions import InvalidAgentServiceSettingError
from main.package.service.agent.scope_gate import ScopeGate
from main.package.service.agent.token_budget import TokenBudget
from main.package.service.chat import ChatFullError, ChatReply, ChatReplyStream, HistoryWindow, MessageValidator
from main.package.service.context import ContextAggregator

_MESSAGES_PER_TURN = 2
_CHECK_STEP = "Checking the question"
_RECALL_STEP = "Recalling a saved answer"
_READ_STEP = "Reading {sections}"
_SECTION_SEPARATOR = " · "


@dataclass(frozen=True)
class _Turn:
    session_id: str
    chat_id: str
    question: str
    history: tuple[ChatMessage, ...]
    decision: GateDecision


class AgentService:
    def __init__(
        self,
        *,
        repository: ChatRepository,
        agent: Agent,
        scope_gate: ScopeGate,
        context_aggregator: ContextAggregator,
        message_validator: MessageValidator,
        history_window: HistoryWindow,
        answer_cache: AnswerCache,
        token_budget: TokenBudget,
        fallback_messages: Mapping[QueryScope, str],
        max_messages_per_chat: int,
    ) -> None:
        self._require_instance("repository", repository, ChatRepository)
        self._require_instance("agent", agent, Agent)
        self._require_instance("scope_gate", scope_gate, ScopeGate)
        self._require_instance("context_aggregator", context_aggregator, ContextAggregator)
        self._require_instance("message_validator", message_validator, MessageValidator)
        self._require_instance("history_window", history_window, HistoryWindow)
        self._require_instance("answer_cache", answer_cache, AnswerCache)
        self._require_instance("token_budget", token_budget, TokenBudget)

        if isinstance(max_messages_per_chat, bool) or not isinstance(max_messages_per_chat, int) or max_messages_per_chat < _MESSAGES_PER_TURN:
            raise InvalidAgentServiceSettingError(f"max_messages_per_chat must be an int of at least {_MESSAGES_PER_TURN}")

        self._repository = repository
        self._agent = agent
        self._scope_gate = scope_gate
        self._context_aggregator = context_aggregator
        self._message_validator = message_validator
        self._history_window = history_window
        self._answer_cache = answer_cache
        self._token_budget = token_budget
        self._fallback_messages = self._require_fallback_messages(fallback_messages, agent)
        self._max_messages_per_chat = max_messages_per_chat

    def stream_message(self, session_id: str, chat_id: str, question: str) -> AgentTurnStream:
        turn = self._prepare_turn(session_id, chat_id, question)
        scope = turn.decision.scope

        if scope is not QueryScope.IN_SCOPE:
            complete = partial(self._complete_turn, turn, scope)
            return AgentTurnStream(
                steps=(_CHECK_STEP,),
                replies=ChatReplyStream(complete=complete, fallback_answer=self._fallback_messages[scope]),
            )

        cached = None if turn.history else self._answer_cache.get(turn.question)
        if cached is not None:
            complete = partial(self._complete_turn, turn, QueryScope.IN_SCOPE)
            return AgentTurnStream(steps=(_RECALL_STEP,), replies=ChatReplyStream(complete=complete, fallback_answer=cached))

        self._token_budget.require_available()
        context = self._context_aggregator.aggregate(turn.decision.contexts)
        answer_stream = MarkedAnswerStream(
            self._agent.stream(turn.question, turn.history, context),
            markers=self._agent.markers,
            fallback_messages=self._fallback_messages,
        )
        return AgentTurnStream(
            steps=(self._read_step(turn.decision.contexts),),
            replies=ChatReplyStream(
                complete=partial(self._complete_streamed_turn, turn, answer_stream),
                answer_stream=answer_stream,
            ),
        )

    def _prepare_turn(self, session_id: str, chat_id: str, question: str) -> _Turn:
        text = self._message_validator.validate(question)
        chat = self._repository.get_chat(session_id, chat_id)

        if len(chat.messages) + _MESSAGES_PER_TURN > self._max_messages_per_chat:
            raise ChatFullError(
                f"Chat {chat_id} has reached its limit of {self._max_messages_per_chat} messages",
                max_messages=self._max_messages_per_chat,
            )

        return _Turn(
            session_id=session_id,
            chat_id=chat_id,
            question=text,
            history=self._history_window.select(chat.messages),
            decision=self._scope_gate.check(text),
        )

    def _complete_streamed_turn(self, turn: _Turn, answer_stream: MarkedAnswerStream, answer: str) -> ChatReply:
        usage = answer_stream.usage
        self._token_budget.record(None if usage is None else usage.total_tokens)
        reply = self._complete_turn(turn, answer_stream.scope, answer)
        if answer_stream.scope is QueryScope.IN_SCOPE and not turn.history:
            self._answer_cache.put(turn.question, answer)

        return reply

    def _complete_turn(self, turn: _Turn, scope: QueryScope, answer: str) -> ChatReply:
        chat = self._repository.add_messages(
            turn.session_id,
            turn.chat_id,
            [NewMessage(role="user", content=turn.question), NewMessage(role="assistant", content=answer)],
        )
        contexts = turn.decision.contexts if scope is QueryScope.IN_SCOPE else ()
        return ChatReply(chat=chat, answer=answer, scope=scope, required_contexts=contexts)

    @staticmethod
    def _read_step(contexts: tuple[ContextType, ...]) -> str:
        return _READ_STEP.format(sections=_SECTION_SEPARATOR.join(context.value.lower() for context in contexts))

    @staticmethod
    def _require_instance(name: str, value: object, expected: type) -> None:
        if not isinstance(value, expected):
            raise InvalidAgentServiceSettingError(f"{name} must be a {expected.__name__}")

    @staticmethod
    def _require_fallback_messages(fallback_messages: Mapping[QueryScope, str], agent: Agent) -> Mapping[QueryScope, str]:
        if not isinstance(fallback_messages, Mapping):
            raise InvalidAgentServiceSettingError("fallback_messages must be a mapping of QueryScope to message")

        needed = set(agent.markers) | {QueryScope.PROMPT_INJECTION}
        missing = needed - set(fallback_messages)
        if missing:
            raise InvalidAgentServiceSettingError(f"fallback_messages has no message for {sorted(missing)}")

        if not all(isinstance(text, str) and text.strip() for text in fallback_messages.values()):
            raise InvalidAgentServiceSettingError("every fallback message must be a non-empty string")

        return MappingProxyType({QueryScope(scope): text.strip() for scope, text in fallback_messages.items()})
