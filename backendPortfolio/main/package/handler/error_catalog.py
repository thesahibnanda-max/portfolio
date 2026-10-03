from collections.abc import Sequence
from dataclasses import dataclass
from http import HTTPStatus
from types import MappingProxyType

from main.package.ai.orchestrator import OrchestratorResponseError
from main.package.ai.worker import WorkerResponseError
from main.package.clients.groq import GroqClientError, GroqRateLimitError
from main.package.handler.exceptions import InvalidHandlerSettingError
from main.package.mail import MailDeliveryError
from main.package.ratelimiter import RateLimitExceededError
from main.package.repository import (
    ChatNotFoundError,
    InvalidRepositoryArgumentError,
    RepositoryOperationError,
    SessionNotFoundError,
)
from main.package.service.agent import AgentBudgetExhaustedError
from main.package.service.chat import ChatFullError, InvalidChatMessageError
from main.package.service.contact import InvalidContactSubmissionError
from main.package.service.data import DataSourceResponseError, DataSourceUnavailableError

_UPSTREAM_ERROR_MESSAGE = "An upstream service failed; please try again shortly"
_UPSTREAM_BUSY_MESSAGE = "An upstream service is busy; please try again shortly"
_INTERNAL_ERROR_MESSAGE = "Something went wrong on our side; please try again"
_MAIL_UNAVAILABLE_MESSAGE = "Couldn't send your message right now; please email directly"
_AGENT_BUDGET_MESSAGE = "The AI has used today's budget; every slash command still works"


@dataclass(frozen=True)
class ErrorRule:
    exception_type: type[BaseException]
    status: HTTPStatus
    code: str
    public_message: str | None = None


class ErrorCatalog:
    def __init__(self, rules: Sequence[ErrorRule], *, fallback: ErrorRule) -> None:
        if not all(isinstance(rule, ErrorRule) for rule in (*rules, fallback)):
            raise InvalidHandlerSettingError("rules and fallback must be ErrorRule instances")

        types = [rule.exception_type for rule in rules]
        if len(set(types)) != len(types):
            raise InvalidHandlerSettingError("every exception type may have only one rule")

        self._rules = MappingProxyType({rule.exception_type: rule for rule in rules})
        self._fallback = fallback

    @property
    def exception_types(self) -> tuple[type[BaseException], ...]:
        return tuple(self._rules)

    def rule_for(self, error: BaseException) -> ErrorRule:
        for error_type in type(error).__mro__:
            rule = self._rules.get(error_type)
            if rule is not None:
                return rule

        return self._fallback

    @classmethod
    def default(cls) -> "ErrorCatalog":
        return cls(
            (
                ErrorRule(InvalidChatMessageError, HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR"),
                ErrorRule(InvalidRepositoryArgumentError, HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR"),
                ErrorRule(InvalidContactSubmissionError, HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR"),
                ErrorRule(SessionNotFoundError, HTTPStatus.UNAUTHORIZED, "SESSION_EXPIRED"),
                ErrorRule(ChatNotFoundError, HTTPStatus.NOT_FOUND, "CHAT_NOT_FOUND"),
                ErrorRule(ChatFullError, HTTPStatus.CONFLICT, "CHAT_FULL"),
                ErrorRule(RateLimitExceededError, HTTPStatus.TOO_MANY_REQUESTS, "RATE_LIMITED"),
                ErrorRule(GroqRateLimitError, HTTPStatus.SERVICE_UNAVAILABLE, "UPSTREAM_BUSY", _UPSTREAM_BUSY_MESSAGE),
                ErrorRule(
                    AgentBudgetExhaustedError,
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "AGENT_BUDGET_EXHAUSTED",
                    _AGENT_BUDGET_MESSAGE,
                ),
                ErrorRule(GroqClientError, HTTPStatus.BAD_GATEWAY, "UPSTREAM_ERROR", _UPSTREAM_ERROR_MESSAGE),
                ErrorRule(DataSourceUnavailableError, HTTPStatus.BAD_GATEWAY, "UPSTREAM_ERROR", _UPSTREAM_ERROR_MESSAGE),
                ErrorRule(DataSourceResponseError, HTTPStatus.BAD_GATEWAY, "UPSTREAM_ERROR", _UPSTREAM_ERROR_MESSAGE),
                ErrorRule(OrchestratorResponseError, HTTPStatus.BAD_GATEWAY, "UPSTREAM_ERROR", _UPSTREAM_ERROR_MESSAGE),
                ErrorRule(WorkerResponseError, HTTPStatus.BAD_GATEWAY, "UPSTREAM_ERROR", _UPSTREAM_ERROR_MESSAGE),
                ErrorRule(MailDeliveryError, HTTPStatus.SERVICE_UNAVAILABLE, "MAIL_UNAVAILABLE", _MAIL_UNAVAILABLE_MESSAGE),
                ErrorRule(RepositoryOperationError, HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", _INTERNAL_ERROR_MESSAGE),
            ),
            fallback=ErrorRule(Exception, HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", _INTERNAL_ERROR_MESSAGE),
        )
