from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from types import MappingProxyType

from main.package.ai.agent import Agent, AgentMode, AgentPlan, AnswerStyle, MarkedAnswerStream, PlanStep
from main.package.ai.common import ChatMessage, ContextType
from main.package.ai.orchestrator import QueryScope
from main.package.repository import ChatRepository, NewMessage, StoredMessage
from main.package.service.agent.answer_cache import AnswerCache
from main.package.service.agent.dto import AgentTurnStream, GateDecision
from main.package.service.agent.exceptions import InvalidAgentServiceSettingError
from main.package.service.agent.scope_gate import ScopeGate
from main.package.service.agent.token_budget import TokenBudget
from main.package.service.chat import ChatFullError, ChatReply, ChatReplyStream, HistoryWindow, MessageValidator
from main.package.service.context import ContextAggregator

_MESSAGES_PER_TURN = 2
_MAX_PLAN_STEPS = 5
_CHECK_STEP = "Checking the question"
_RECALL_STEP = "Recalling a saved answer"
_RECALL_PLAN_STEP = "Recalling a saved plan"
_PLAN_STEP = "Planning terminal commands"
_READ_STEP = "Reading {sections}"
_SECTION_SEPARATOR = " · "
_COMMAND_PREFIX = "/"
_PLAN_VARIANT = "plan"


@dataclass(frozen=True)
class _Turn:
    session_id: str
    chat_id: str
    question: str
    history: tuple[ChatMessage, ...]
    decision: GateDecision
    earlier_answer: str | None


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
        skill_names: Collection[str],
        plan_fallback_message: str,
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

        if isinstance(skill_names, str) or not isinstance(skill_names, Collection) or not skill_names:
            raise InvalidAgentServiceSettingError("skill_names must be a non-empty collection of command names")

        if not isinstance(plan_fallback_message, str) or not plan_fallback_message.strip():
            raise InvalidAgentServiceSettingError("plan_fallback_message must be a non-empty string")

        self._repository = repository
        self._agent = agent
        self._scope_gate = scope_gate
        self._context_aggregator = context_aggregator
        self._message_validator = message_validator
        self._history_window = history_window
        self._answer_cache = answer_cache
        self._token_budget = token_budget
        self._fallback_messages = self._require_fallback_messages(fallback_messages, agent)
        self._skill_names = frozenset(name.casefold() for name in skill_names)
        self._plan_fallback_message = plan_fallback_message.strip()
        self._max_messages_per_chat = max_messages_per_chat

    def validate(self, question: str) -> str:
        return self._message_validator.validate(question)

    def stream_message(
        self,
        session_id: str,
        chat_id: str,
        question: str,
        *,
        style: AnswerStyle = AnswerStyle.CONCISE,
        mode: AgentMode = AgentMode.ANSWER,
    ) -> AgentTurnStream:
        if not isinstance(style, AnswerStyle) or not isinstance(mode, AgentMode):
            raise InvalidAgentServiceSettingError("style must be an AnswerStyle and mode an AgentMode")

        turn = self._prepare_turn(session_id, chat_id, question)
        scope = turn.decision.scope

        if scope is not QueryScope.IN_SCOPE:
            return self._fixed_turn(turn, scope, _CHECK_STEP, self._fallback_messages[scope])

        if mode is AgentMode.PLAN:
            return self._plan_turn(turn)

        cached = turn.earlier_answer
        if cached is None and not turn.history:
            cached = self._answer_cache.get(turn.question, style.value)
        if cached is not None:
            return self._fixed_turn(turn, QueryScope.IN_SCOPE, _RECALL_STEP, cached)

        self._token_budget.require_available()
        context = self._context_aggregator.aggregate(turn.decision.contexts)
        answer_stream = MarkedAnswerStream(
            self._agent.stream(turn.question, turn.history, context, style),
            markers=self._agent.markers,
            fallback_messages=self._fallback_messages,
        )
        return AgentTurnStream(
            steps=(self._read_step(turn.decision.contexts),),
            replies=ChatReplyStream(
                complete=partial(self._complete_streamed_turn, turn, answer_stream, style),
                answer_stream=answer_stream,
            ),
        )

    def _plan_turn(self, turn: _Turn) -> AgentTurnStream:
        cached = None if turn.history else self._answer_cache.get(turn.question, _PLAN_VARIANT)
        if cached is not None:
            return self._plan_stream(turn, AgentPlan.model_validate_json(cached), _RECALL_PLAN_STEP)

        self._token_budget.require_available()
        contexts = tuple(context for context in ContextType if context in {*turn.decision.contexts, ContextType.SITE})
        plan, usage = self._agent.plan(turn.question, turn.history, self._context_aggregator.aggregate(contexts))
        self._token_budget.record(None if usage is None else usage.total_tokens)

        if plan.scope is not QueryScope.IN_SCOPE:
            fallback = self._fallback_messages.get(plan.scope, self._fallback_messages[QueryScope.NOT_RELATED_TO_PORTFOLIO])
            return self._fixed_turn(turn, plan.scope, _PLAN_STEP, fallback)

        valid = self._valid_plan(plan)
        if not valid.steps:
            return self._fixed_turn(turn, QueryScope.IN_SCOPE, _PLAN_STEP, self._plan_fallback_message)

        if not turn.history:
            self._answer_cache.put(turn.question, _PLAN_VARIANT, valid.model_dump_json())
        return self._plan_stream(turn, valid, _PLAN_STEP)

    def _plan_stream(self, turn: _Turn, plan: AgentPlan, step: str) -> AgentTurnStream:
        complete = partial(self._complete_turn, turn, QueryScope.IN_SCOPE)
        return AgentTurnStream(
            steps=(step,),
            replies=ChatReplyStream(complete=complete, fallback_answer=self._plan_text(plan)),
            plan=plan,
        )

    def _fixed_turn(self, turn: _Turn, scope: QueryScope, step: str, answer: str) -> AgentTurnStream:
        complete = partial(self._complete_turn, turn, scope)
        return AgentTurnStream(steps=(step,), replies=ChatReplyStream(complete=complete, fallback_answer=answer))

    def _valid_plan(self, plan: AgentPlan) -> AgentPlan:
        steps = tuple(step for step in plan.steps if self._is_known_command(step))[:_MAX_PLAN_STEPS]
        cleaned = tuple(PlanStep(command=step.command.strip(), reason=step.reason.strip()) for step in steps)
        return AgentPlan(scope=QueryScope.IN_SCOPE, summary=plan.summary.strip(), steps=cleaned)

    def _is_known_command(self, step: PlanStep) -> bool:
        command = step.command.strip()
        if not command.startswith(_COMMAND_PREFIX) or "\n" in command:
            return False
        name = command.removeprefix(_COMMAND_PREFIX).split(maxsplit=1)
        return bool(name) and name[0].casefold() in self._skill_names

    @staticmethod
    def _plan_text(plan: AgentPlan) -> str:
        lines = [f"Plan: {plan.summary}" if plan.summary else "Plan:"]
        lines.extend(
            f"{index}. {step.command}" + (f" -- {step.reason}" if step.reason else "")
            for index, step in enumerate(plan.steps, start=1)
        )
        return "\n".join(lines)

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
            earlier_answer=self._earlier_answer(chat.messages, text),
        )

    @staticmethod
    def _earlier_answer(messages: Sequence[StoredMessage], question: str) -> str | None:
        wanted = AnswerCache.normalize(question)
        answer = None
        for asked, replied in zip(messages, messages[1:]):
            if (
                asked.role == "user"
                and replied.role == "assistant"
                and AnswerCache.normalize(asked.content) == wanted
                and not replied.content.startswith("Plan:")
            ):
                answer = replied.content
        return answer

    def _complete_streamed_turn(
        self,
        turn: _Turn,
        answer_stream: MarkedAnswerStream,
        style: AnswerStyle,
        answer: str,
    ) -> ChatReply:
        usage = answer_stream.usage
        self._token_budget.record(None if usage is None else usage.total_tokens)
        reply = self._complete_turn(turn, answer_stream.scope, answer)
        if answer_stream.scope is QueryScope.IN_SCOPE and not turn.history:
            self._answer_cache.put(turn.question, style.value, answer)

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
