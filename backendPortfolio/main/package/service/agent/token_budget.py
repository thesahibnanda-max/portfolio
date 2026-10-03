import threading
from collections.abc import Callable
from datetime import UTC, date, datetime

from main.package.service.agent.exceptions import AgentBudgetExhaustedError, InvalidAgentServiceSettingError


def _utc_today() -> date:
    return datetime.now(UTC).date()


class TokenBudget:
    def __init__(self, *, daily_tokens: int, today: Callable[[], date] = _utc_today) -> None:
        if isinstance(daily_tokens, bool) or not isinstance(daily_tokens, int) or daily_tokens < 1:
            raise InvalidAgentServiceSettingError("daily_tokens must be a positive int")

        self._daily_tokens = daily_tokens
        self._today = today
        self._lock = threading.Lock()
        self._day = today()
        self._used = 0

    @property
    def used(self) -> int:
        with self._lock:
            self._roll_over()
            return self._used

    def require_available(self) -> None:
        with self._lock:
            self._roll_over()
            if self._used >= self._daily_tokens:
                raise AgentBudgetExhaustedError(f"The agent used its daily budget of {self._daily_tokens} tokens")

    def record(self, tokens: int | None) -> None:
        if tokens is None or tokens <= 0:
            return

        with self._lock:
            self._roll_over()
            self._used += tokens

    def _roll_over(self) -> None:
        today = self._today()
        if today != self._day:
            self._day = today
            self._used = 0
