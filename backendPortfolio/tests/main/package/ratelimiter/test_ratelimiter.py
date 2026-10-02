import threading
from datetime import timedelta
from functools import partial

import pytest
from pydantic import ValidationError

import limits.storage.memory
import main.package.ratelimiter.ratelimiter
from main.package.ratelimiter import (
    InvalidRateLimitArgumentError,
    InvalidRateLimiterSettingError,
    RateLimiter,
    RateLimiterError,
    RateLimitExceededError,
    RateLimitRule,
    RateLimitScope,
)
from tests.support import ConcurrentRunner

IP = RateLimitScope.IP
SESSION = RateLimitScope.SESSION
GLOBAL = RateLimitScope.GLOBAL


class FakeClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _rules(ip: int = 3, session: int = 3, global_: int = 100, seconds: int = 60) -> dict[RateLimitScope, RateLimitRule]:
    window = timedelta(seconds=seconds)
    return {
        IP: RateLimitRule(limit=ip, window=window),
        SESSION: RateLimitRule(limit=session, window=window),
        GLOBAL: RateLimitRule(limit=global_, window=window),
    }


def _limiter(**rules: dict[RateLimitScope, RateLimitRule]) -> RateLimiter:
    return RateLimiter(storage_uri="memory://", key_prefix="test", rules=rules or {"chat": _rules()})


def _allowed(limiter: RateLimiter, api: str, client_ip: str | None, session_id: str | None) -> bool:
    try:
        limiter.check(api, client_ip=client_ip, session_id=session_id)
    except RateLimitExceededError:
        return False
    return True


def _hit_many(limiter: RateLimiter, count: int) -> int:
    return sum(_allowed(limiter, "chat", "1.1.1.1", None) for _ in range(count))


class OwnIpHitter:
    def __init__(self, limiter: RateLimiter, count: int) -> None:
        self._limiter = limiter
        self._count = count
        self._next_ip = iter(range(1_000))
        self._lock = threading.Lock()

    def __call__(self) -> int:
        with self._lock:
            ip = f"10.0.0.{next(self._next_ip)}"
        return sum(_allowed(self._limiter, "chat", ip, None) for _ in range(self._count))


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock(1_800_000_000.0)
    monkeypatch.setattr(limits.storage.memory, "time", fake)
    monkeypatch.setattr(main.package.ratelimiter.ratelimiter, "time", fake)
    return fake


def test_allows_up_to_the_limit_then_refuses_with_the_scope(clock: FakeClock) -> None:
    limiter = _limiter()

    for _ in range(3):
        limiter.check("chat", client_ip="1.1.1.1", session_id="s1")

    with pytest.raises(RateLimitExceededError) as error:
        limiter.check("chat", client_ip="1.1.1.1", session_id="s1")

    assert (error.value.api, error.value.scope) == ("chat", IP)
    assert isinstance(error.value, RateLimiterError)


def test_ips_sessions_and_apis_have_independent_budgets(clock: FakeClock) -> None:
    limiter = _limiter(chat=_rules(ip=1, session=5), details=_rules(ip=1, session=5))

    limiter.check("chat", client_ip="1.1.1.1", session_id="s1")
    limiter.check("chat", client_ip="2.2.2.2", session_id="s1")
    limiter.check("details", client_ip="1.1.1.1", session_id="s1")

    assert not _allowed(limiter, "chat", "1.1.1.1", "s2")
    assert _allowed(limiter, "chat", "3.3.3.3", "s2")


def test_session_limit_applies_across_ips(clock: FakeClock) -> None:
    limiter = _limiter(chat=_rules(ip=10, session=2))

    limiter.check("chat", client_ip="1.1.1.1", session_id="s1")
    limiter.check("chat", client_ip="2.2.2.2", session_id="s1")

    with pytest.raises(RateLimitExceededError) as error:
        limiter.check("chat", client_ip="3.3.3.3", session_id="s1")

    assert error.value.scope is SESSION


def test_global_limit_applies_across_visitors(clock: FakeClock) -> None:
    limiter = _limiter(chat=_rules(ip=10, session=10, global_=3))

    for index in range(3):
        limiter.check("chat", client_ip=f"10.0.0.{index}", session_id=f"s{index}")

    with pytest.raises(RateLimitExceededError) as error:
        limiter.check("chat", client_ip="10.0.0.99", session_id="s99")

    assert error.value.scope is GLOBAL


def test_refused_ip_does_not_use_the_session_or_global_budget(clock: FakeClock) -> None:
    limiter = _limiter(chat=_rules(ip=2, session=10, global_=10))

    for _ in range(2):
        limiter.check("chat", client_ip="1.1.1.1", session_id="s1")
    for _ in range(5):
        assert not _allowed(limiter, "chat", "1.1.1.1", "s1")

    assert dict(limiter.remaining("chat", client_ip="1.1.1.1", session_id="s1")) == {IP: 0, SESSION: 8, GLOBAL: 8}


def test_none_identifiers_skip_their_scopes(clock: FakeClock) -> None:
    limiter = _limiter(chat=_rules(ip=1, session=1, global_=3))

    limiter.check("chat", client_ip=None, session_id=None)
    limiter.check("chat", client_ip=None, session_id=None)

    assert dict(limiter.remaining("chat", client_ip=None, session_id=None)) == {GLOBAL: 1}
    assert set(limiter.remaining("chat", client_ip="1.1.1.1", session_id=None)) == {IP, GLOBAL}
    assert set(limiter.remaining("chat", client_ip=None, session_id="s1")) == {SESSION, GLOBAL}


def test_remaining_counts_nothing(clock: FakeClock) -> None:
    limiter = _limiter()

    for _ in range(10):
        limiter.remaining("chat", client_ip="1.1.1.1", session_id="s1")

    assert dict(limiter.remaining("chat", client_ip="1.1.1.1", session_id="s1")) == {IP: 3, SESSION: 3, GLOBAL: 100}


def test_retry_after_is_whole_seconds_within_the_window(clock: FakeClock) -> None:
    limiter = _limiter(chat=_rules(ip=1, seconds=60))
    limiter.check("chat", client_ip="1.1.1.1", session_id=None)

    with pytest.raises(RateLimitExceededError) as error:
        limiter.check("chat", client_ip="1.1.1.1", session_id=None)

    retry_after = error.value.retry_after
    assert timedelta(seconds=1) <= retry_after <= timedelta(seconds=60)
    assert retry_after % timedelta(seconds=1) == timedelta(0)
    assert "retry after" in str(error.value)


def test_retry_after_is_at_least_one_second(clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = _limiter(chat=_rules(ip=1, seconds=60))
    limiter.check("chat", client_ip="1.1.1.1", session_id=None)
    monkeypatch.setattr(main.package.ratelimiter.ratelimiter, "time", FakeClock(clock.now + 10_000))

    with pytest.raises(RateLimitExceededError) as error:
        limiter.check("chat", client_ip="1.1.1.1", session_id=None)

    assert error.value.retry_after == timedelta(seconds=1)


def test_sliding_window_frees_up_gradually(clock: FakeClock) -> None:
    limiter = _limiter(chat=_rules(ip=4, seconds=10))
    clock.now = 1_800_000_000.0
    for _ in range(4):
        limiter.check("chat", client_ip="1.1.1.1", session_id=None)
    assert not _allowed(limiter, "chat", "1.1.1.1", None)

    clock.advance(10)
    assert not _allowed(limiter, "chat", "1.1.1.1", None)

    clock.advance(5)
    assert _allowed(limiter, "chat", "1.1.1.1", None)
    assert _allowed(limiter, "chat", "1.1.1.1", None)
    assert not _allowed(limiter, "chat", "1.1.1.1", None)

    clock.advance(20)
    assert sum(_allowed(limiter, "chat", "1.1.1.1", None) for _ in range(6)) == 4


def test_no_double_burst_at_the_window_edge(clock: FakeClock) -> None:
    limiter = _limiter(chat=_rules(ip=4, seconds=10))
    clock.now = 1_800_000_009.0
    allowed_before = sum(_allowed(limiter, "chat", "1.1.1.1", None) for _ in range(4))

    clock.advance(1.5)
    allowed_after = sum(_allowed(limiter, "chat", "1.1.1.1", None) for _ in range(4))

    assert allowed_before == 4
    assert allowed_after == 1


def test_reset_clears_every_counter(clock: FakeClock) -> None:
    limiter = _limiter(chat=_rules(ip=1))
    limiter.check("chat", client_ip="1.1.1.1", session_id=None)

    limiter.reset()

    limiter.check("chat", client_ip="1.1.1.1", session_id=None)


def test_apis_lists_the_configured_names() -> None:
    assert _limiter(chat=_rules(), details=_rules()).apis == frozenset({"chat", "details"})


def test_concurrent_hits_never_exceed_the_limit() -> None:
    limiter = _limiter(chat=_rules(ip=37, global_=1000, seconds=3600))

    runner = ConcurrentRunner(partial(_hit_many, limiter, 10)).run()

    assert runner.errors == []
    assert sum(runner.results) == 37


@pytest.mark.parametrize("attempt", range(20))
def test_concurrent_hits_on_one_key_admit_exactly_the_limit(attempt: int) -> None:
    limiter = _limiter(chat=_rules(ip=37, global_=1000, seconds=3600))

    assert sum(ConcurrentRunner(partial(_hit_many, limiter, 10)).run().results) == 37


def test_concurrent_visitors_get_their_own_limit_and_share_the_global_one() -> None:
    own_limits = _limiter(chat=_rules(ip=7, global_=1000, seconds=3600))
    shared_global = _limiter(chat=_rules(ip=10, global_=50, seconds=3600))

    own_results = ConcurrentRunner(OwnIpHitter(own_limits, 10)).run().results
    shared_results = ConcurrentRunner(OwnIpHitter(shared_global, 10)).run().results

    assert own_results == [7] * 16
    assert sum(shared_results) == 50


def test_scopes_are_checked_most_specific_first() -> None:
    assert list(RateLimitScope) == [IP, SESSION, GLOBAL]


@pytest.mark.parametrize("api", ["unknown", "", 5, None])
def test_unknown_api_raises(api: object) -> None:
    with pytest.raises(InvalidRateLimitArgumentError):
        _limiter().check(api, client_ip="1.1.1.1", session_id=None)

    with pytest.raises(InvalidRateLimitArgumentError):
        _limiter().remaining(api, client_ip="1.1.1.1", session_id=None)


@pytest.mark.parametrize(("client_ip", "session_id"), [("", None), ("   ", None), (None, ""), (5, None), (None, b"s")])
def test_invalid_identifiers_raise(client_ip: object, session_id: object) -> None:
    with pytest.raises(InvalidRateLimitArgumentError):
        _limiter().check("chat", client_ip=client_ip, session_id=session_id)


@pytest.mark.parametrize("storage_uri", ["", "   ", None, "bogus://x", "redis://localhost:6379", "async+memory://"])
def test_invalid_storage_uri_raises(storage_uri: object) -> None:
    with pytest.raises(InvalidRateLimiterSettingError):
        RateLimiter(storage_uri=storage_uri, key_prefix="test", rules={"chat": _rules()})


def test_unknown_storage_scheme_keeps_the_cause() -> None:
    with pytest.raises(InvalidRateLimiterSettingError) as error:
        RateLimiter(storage_uri="bogus://x", key_prefix="test", rules={"chat": _rules()})

    assert error.value.__cause__ is not None


@pytest.mark.parametrize("key_prefix", ["", "  ", None, 5])
def test_invalid_key_prefix_raises(key_prefix: object) -> None:
    with pytest.raises(InvalidRateLimiterSettingError):
        RateLimiter(storage_uri="memory://", key_prefix=key_prefix, rules={"chat": _rules()})


@pytest.mark.parametrize(
    "rules",
    [
        {},
        None,
        [("chat", _rules())],
        {"Chat": _rules()},
        {"chat/x": _rules()},
        {"": _rules()},
        {5: _rules()},
        {"chat": None},
        {"chat": {IP: RateLimitRule(limit=1, window=timedelta(seconds=1))}},
        {"chat": {**_rules(), "extra": RateLimitRule(limit=1, window=timedelta(seconds=1))}},
        {"chat": {IP: {"limit": 1, "window": 1}, SESSION: _rules()[SESSION], GLOBAL: _rules()[GLOBAL]}},
    ],
)
def test_invalid_rules_raise(rules: object) -> None:
    with pytest.raises(InvalidRateLimiterSettingError):
        RateLimiter(storage_uri="memory://", key_prefix="test", rules=rules)


def test_string_scope_keys_are_accepted() -> None:
    rules = {"ip": _rules()[IP], "session": _rules()[SESSION], "global": _rules()[GLOBAL]}

    limiter = RateLimiter(storage_uri="memory://", key_prefix="test", rules={"chat": rules})

    assert set(limiter.remaining("chat", client_ip="1.1.1.1", session_id="s1")) == {IP, SESSION, GLOBAL}


@pytest.mark.parametrize(
    ("limit", "window"),
    [
        (0, timedelta(seconds=1)),
        (True, timedelta(seconds=1)),
        ("5", timedelta(seconds=1)),
        (1, timedelta(0)),
        (1, timedelta(seconds=-1)),
        (1, timedelta(seconds=1.5)),
    ],
)
def test_invalid_rule_raises(limit: object, window: timedelta) -> None:
    with pytest.raises(ValidationError):
        RateLimitRule(limit=limit, window=window)


def test_rule_is_frozen() -> None:
    rule = RateLimitRule(limit=1, window=timedelta(seconds=1))

    with pytest.raises(ValidationError):
        rule.limit = 2
