import logging
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from functools import partial

import pytest

from main.package.ttl_key_value_store import (
    InvalidSweepIntervalError,
    InvalidTTLKeyValueEntryError,
    TTLKeyValueStore,
    TTLKeyValueStoreError,
)
from main.package.ttl_key_value_store.in_memory_ttl_key_value_store import _InMemoryTTLKeyValueStore
from tests.support import ConcurrentRunner, wait_until


class FailingPurge:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0

    def __call__(self) -> None:
        with self._lock:
            self.calls += 1
        raise RuntimeError("injected purge failure")

    def called_at_least_twice(self) -> bool:
        return self.calls >= 2


def _in(seconds: float) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)


def _holds_only(store: _InMemoryTTLKeyValueStore, keys: set[str]) -> bool:
    return set(store._entries) == keys


@pytest.fixture
def store() -> Iterator[_InMemoryTTLKeyValueStore]:
    instance = _InMemoryTTLKeyValueStore(timedelta(minutes=20))
    yield instance
    instance.close()


@pytest.fixture
def fast_store() -> Iterator[_InMemoryTTLKeyValueStore]:
    instance = _InMemoryTTLKeyValueStore(timedelta(milliseconds=20))
    yield instance
    instance.close()


def test_implements_the_interface(store: _InMemoryTTLKeyValueStore) -> None:
    assert isinstance(store, TTLKeyValueStore)


def test_get_missing_key_returns_none(store: _InMemoryTTLKeyValueStore) -> None:
    assert store.get("missing") is None


def test_set_then_get(store: _InMemoryTTLKeyValueStore) -> None:
    store.set("key", "value", _in(60))

    assert store.get("key") == "value"


def test_set_overwrites_existing_value(store: _InMemoryTTLKeyValueStore) -> None:
    store.set("key", "first", _in(60))
    store.set("key", "second", _in(60))

    assert store.get("key") == "second"


def test_expired_entry_reads_as_absent_and_is_removed(store: _InMemoryTTLKeyValueStore) -> None:
    store.set("key", "value", _in(0.05))
    time.sleep(0.1)

    assert store.get("key") is None
    assert "key" not in store._entries


def test_entry_already_expired_when_set_is_absent(store: _InMemoryTTLKeyValueStore) -> None:
    store.set("key", "value", _in(-1))

    assert store.get("key") is None


def test_delete_removes_entry(store: _InMemoryTTLKeyValueStore) -> None:
    store.set("key", "value", _in(60))
    store.delete("key")

    assert store.get("key") is None


def test_delete_missing_key_is_not_an_error(store: _InMemoryTTLKeyValueStore) -> None:
    store.delete("missing")


def test_set_if_absent_stores_only_first_value(store: _InMemoryTTLKeyValueStore) -> None:
    assert store.set_if_absent("key", "first", _in(60)) is True
    assert store.set_if_absent("key", "second", _in(60)) is False
    assert store.get("key") == "first"


def test_set_if_absent_succeeds_again_after_expiry(store: _InMemoryTTLKeyValueStore) -> None:
    assert store.set_if_absent("key", "first", _in(0.05)) is True
    time.sleep(0.1)

    assert store.set_if_absent("key", "second", _in(60)) is True
    assert store.get("key") == "second"


@pytest.mark.parametrize("method", ["set", "set_if_absent"])
def test_empty_key_is_rejected(store: _InMemoryTTLKeyValueStore, method: str) -> None:
    with pytest.raises(InvalidTTLKeyValueEntryError):
        getattr(store, method)("", "value", _in(60))


@pytest.mark.parametrize("method", ["set", "set_if_absent"])
def test_naive_expiry_is_rejected(store: _InMemoryTTLKeyValueStore, method: str) -> None:
    with pytest.raises(InvalidTTLKeyValueEntryError):
        getattr(store, method)("key", "value", datetime.now())


def test_exactly_one_thread_wins_set_if_absent_race(store: _InMemoryTTLKeyValueStore) -> None:
    runner = ConcurrentRunner(partial(store.set_if_absent, "race", "1", _in(60))).run()

    assert runner.errors == []
    assert runner.results.count(True) == 1
    assert runner.results.count(False) == 15


@pytest.mark.parametrize("interval", [timedelta(0), timedelta(seconds=-1), 20, None, "20m"])
def test_sweep_interval_must_be_positive_timedelta(interval: object) -> None:
    with pytest.raises(InvalidSweepIntervalError):
        _InMemoryTTLKeyValueStore(interval)


def test_sweeper_thread_runs_as_daemon(store: _InMemoryTTLKeyValueStore) -> None:
    assert store._sweeper.is_alive()
    assert store._sweeper.daemon is True
    assert store._sweep_interval_seconds == 1200.0


def test_sweeper_removes_only_expired_entries(fast_store: _InMemoryTTLKeyValueStore) -> None:
    fast_store.set("old", "value", _in(0.05))
    fast_store.set("new", "value", _in(3600))

    assert wait_until(partial(_holds_only, fast_store, {"new"}))


def test_sweeper_survives_and_logs_purge_errors(
    fast_store: _InMemoryTTLKeyValueStore,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    failing = FailingPurge()
    monkeypatch.setattr(fast_store, "_purge_expired", failing)

    with caplog.at_level(logging.ERROR):
        assert wait_until(failing.called_at_least_twice)

    assert fast_store._sweeper.is_alive()
    assert "Failed to purge expired entries" in caplog.text


def test_close_stops_sweeper_and_is_safe_twice() -> None:
    instance = _InMemoryTTLKeyValueStore(timedelta(minutes=20))
    instance.close()
    instance.close()

    assert not instance._sweeper.is_alive()


@pytest.mark.parametrize("error_type", [InvalidSweepIntervalError, InvalidTTLKeyValueEntryError])
def test_errors_share_the_store_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, TTLKeyValueStoreError)
