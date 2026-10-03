"""
The Portfolio Agent service behind the /cli terminal. It answers a visitor's
question with at most one Groq call, and often with none, and stores the
exchange in the same chats as the chat panel.

Exports:
    AgentService: runs one terminal turn and returns an AgentTurnStream.
    AgentTurnStream: steps (short labels to show before the answer) and
    replies (a main.package.service.chat.ChatReplyStream).
    ScopeGate and GateDecision: the zero-token pre-check.
    AnswerCache: cached first-turn answers.
    TokenBudget: the daily Groq token cap.
    AgentServiceError and its subclasses: the errors described under Errors.

How a turn spends tokens (least first):
    1. ScopeGate.check: a question matching any injection pattern is refused
       with the PROMPT_INJECTION fallback, 0 tokens. Otherwise keywords pick
       the context sections (for example "rating" -> CODEFORCES and
       LEETCODE); with no keyword the default_contexts are used. Steps:
       ("Checking the question",).
    2. AnswerCache: a question asked with no history whose normalized text
       (case-folded, whitespace collapsed, trailing punctuation removed) was
       answered within cache_ttl is replayed, 0 tokens. Steps:
       ("Recalling a saved answer",).
    3. TokenBudget.require_available, then one streamed Agent call with
       only the selected context, a short history window and the agent's
       own limits. MarkedAnswerStream turns an out-of-scope marker into its
       fallback message. Steps: ("Reading profile · github",) and so on.
       On completion the usage is added to the budget and an in-scope
       first-turn answer is cached.
    Every answer, including fallbacks and replays, is saved with the
    question in one transaction only after it completed, exactly like the
    chat; a cancelled or failed stream saves nothing.

Construction:
    AgentService(
        *,
        repository, agent, scope_gate, context_aggregator,
        message_validator, history_window, answer_cache, token_budget,
        fallback_messages, max_messages_per_chat,
    )
    The validator and window are the chat's classes with the agent's
    smaller limits. fallback_messages must cover every agent marker scope
    and PROMPT_INJECTION. All settings come from main.config.AppConfig.agent
    (and chat.fallback_messages). A bad setting raises
    InvalidAgentServiceSettingError.
    ScopeGate(*, injection_patterns, context_keywords, default_contexts):
    case-insensitive regular expressions; keywords match at a word start.
    AnswerCache(*, store, ttl): store is a TTLKeyValueStore; keys are
    "agent-answer:" plus the SHA-256 of the normalized question.
    TokenBudget(*, daily_tokens, today=utc date): the count resets when the
    UTC day changes. It is a soft cap: it is checked before a call and
    charged after it, so parallel calls may pass it by one answer each.

stream_message(session_id, chat_id, question) -> AgentTurnStream
    Validates the question, loads the chat (ChatFullError when it has no
    room), then follows the steps above. Enter replies with a with block and
    iterate it like the chat stream.

Errors (all in exceptions.py, all subclasses of AgentServiceError):
    InvalidAgentServiceSettingError: a constructor setting is invalid.
    AgentBudgetExhaustedError: the daily token budget is used up; the API
    answers 503 AGENT_BUDGET_EXHAUSTED and the terminal keeps working for
    every slash command.
    Validation, repository, context, data and Groq errors pass through
    unwrapped, already typed for the API's status mapping.

Thread safety:
    One AgentService serves every thread on the free-threaded build. The
    gate is immutable, the cache uses the thread-safe TTL store and the
    budget guards its counter with a lock.
"""

from .agent_service import AgentService
from .answer_cache import AnswerCache
from .dto import AgentTurnStream, GateDecision
from .exceptions import AgentBudgetExhaustedError, AgentServiceError, InvalidAgentServiceSettingError
from .scope_gate import ScopeGate
from .token_budget import TokenBudget

__all__ = [
    "AgentService",
    "AgentTurnStream",
    "ScopeGate",
    "GateDecision",
    "AnswerCache",
    "TokenBudget",
    "AgentServiceError",
    "InvalidAgentServiceSettingError",
    "AgentBudgetExhaustedError",
]
