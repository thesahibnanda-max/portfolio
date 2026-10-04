from datetime import date
from functools import partial

import pytest

from main.package.service.agent import AgentBudgetExhaustedError, AgentServiceError, InvalidAgentServiceSettingError, TokenBudget
from tests.support import ConcurrentRunner


class Calendar:
    def __init__(self) -> None:
        self.day = date(2026, 10, 4)

    def today(self) -> date:
        return self.day


def _record_many(budget: TokenBudget, count: int) -> int:
    for _ in range(count):
        budget.record(1)
    return count


def test_blocks_once_the_daily_budget_is_used() -> None:
    budget = TokenBudget(daily_tokens=1000)
    budget.require_available()
    budget.record(999)
    budget.require_available()
    budget.record(1)

    with pytest.raises(AgentBudgetExhaustedError, match="1000"):
        budget.require_available()
    assert budget.used == 1000


@pytest.mark.parametrize("tokens", [None, 0, -5])
def test_missing_or_empty_usage_is_ignored(tokens: int | None) -> None:
    budget = TokenBudget(daily_tokens=10)
    budget.record(tokens)

    assert budget.used == 0


def test_resets_when_the_utc_day_changes() -> None:
    calendar = Calendar()
    budget = TokenBudget(daily_tokens=10, today=calendar.today)
    budget.record(10)
    with pytest.raises(AgentBudgetExhaustedError):
        budget.require_available()

    calendar.day = date(2026, 10, 5)

    budget.require_available()
    assert budget.used == 0


def test_counts_exactly_under_concurrency() -> None:
    budget = TokenBudget(daily_tokens=10**9)
    runner = ConcurrentRunner(partial(_record_many, budget, 500)).run()

    assert runner.errors == []
    assert budget.used == sum(runner.results)


@pytest.mark.parametrize("daily_tokens", [0, -1, True, 1.5, "100"])
def test_invalid_budget_raises(daily_tokens: object) -> None:
    with pytest.raises(InvalidAgentServiceSettingError):
        TokenBudget(daily_tokens=daily_tokens)


def test_errors_share_the_service_base() -> None:
    assert issubclass(AgentBudgetExhaustedError, AgentServiceError)
    assert issubclass(InvalidAgentServiceSettingError, AgentServiceError)
