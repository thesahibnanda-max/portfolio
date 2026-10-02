import json
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from functools import partial

import pytest

from main.package.service.data import (
    CachedDetailsSource,
    CodeforcesDetails,
    DataSourceUnavailableError,
    DetailsSource,
    InvalidDataServiceSettingError,
)
from main.package.ttl_key_value_store import TTLKeyValueStoreFactory, TTLKeyValueStoreImpl
from tests.support import ConcurrentRunner


class CountingSource(DetailsSource[CodeforcesDetails]):
    def __init__(self, delay: float = 0.0, failures: int = 0) -> None:
        self._delay = delay
        self._failures = failures
        self._lock = threading.Lock()
        self.calls = 0

    @property
    def platform(self) -> str:
        return "codeforces"

    @property
    def details_type(self) -> type[CodeforcesDetails]:
        return CodeforcesDetails

    def fetch(self, account: str) -> CodeforcesDetails:
        with self._lock:
            self.calls += 1
            should_fail = self.calls <= self._failures
        time.sleep(self._delay)
        if should_fail:
            raise DataSourceUnavailableError("down", platform=self.platform, account=account)
        return CodeforcesDetails(handle=account, current_rating=1832, contests_count=self.calls)


@pytest.fixture
def factory() -> Iterator[TTLKeyValueStoreFactory]:
    instance = TTLKeyValueStoreFactory({TTLKeyValueStoreImpl.IN_MEMORY: timedelta(minutes=20)})
    yield instance
    instance.close_all()


def _cached(factory: TTLKeyValueStoreFactory, source: DetailsSource, ttls: dict) -> CachedDetailsSource:
    return CachedDetailsSource(source, factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY), ttls)


def test_miss_calls_source_then_hit_does_not(factory: TTLKeyValueStoreFactory) -> None:
    source = CountingSource()
    cached = _cached(factory, source, {"h": timedelta(hours=1)})

    first = cached.fetch("h")
    second = cached.fetch("h")

    assert source.calls == 1
    assert first == second
    assert first is not second


def test_values_are_stored_as_json_strings_under_namespaced_keys(factory: TTLKeyValueStoreFactory) -> None:
    store = factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY)
    cached = _cached(factory, CountingSource(), {"shisukenohara": timedelta(minutes=80)})
    cached.fetch("shisukenohara")

    stored = store.get("data:codeforces:shisukenohara")
    assert isinstance(stored, str)
    assert json.loads(stored)["handle"] == "shisukenohara"
    assert cached.cache_key("x") == "data:codeforces:x"


def test_each_account_uses_its_own_ttl(factory: TTLKeyValueStoreFactory) -> None:
    store = factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY)
    cached = _cached(factory, CountingSource(), {"a": timedelta(minutes=45), "b": timedelta(minutes=120)})
    before = datetime.now(UTC)
    cached.fetch("a")
    cached.fetch("b")

    expiry_a = store._entries["data:codeforces:a"][1] - before
    expiry_b = store._entries["data:codeforces:b"][1] - before
    assert timedelta(minutes=45) <= expiry_a < timedelta(minutes=45, seconds=5)
    assert timedelta(minutes=120) <= expiry_b < timedelta(minutes=120, seconds=5)


def test_entry_is_refetched_after_its_ttl(factory: TTLKeyValueStoreFactory) -> None:
    source = CountingSource()
    cached = _cached(factory, source, {"h": timedelta(milliseconds=30)})
    cached.fetch("h")
    time.sleep(0.06)
    cached.fetch("h")

    assert source.calls == 2


def test_failures_are_not_cached(factory: TTLKeyValueStoreFactory) -> None:
    source = CountingSource(failures=1)
    cached = _cached(factory, source, {"h": timedelta(hours=1)})

    with pytest.raises(DataSourceUnavailableError):
        cached.fetch("h")

    assert cached.fetch("h").handle == "h"
    assert source.calls == 2


def test_parallel_misses_make_one_upstream_call(factory: TTLKeyValueStoreFactory) -> None:
    source = CountingSource(delay=0.05)
    cached = _cached(factory, source, {"h": timedelta(hours=1)})
    runner = ConcurrentRunner(partial(cached.fetch, "h")).run()

    assert runner.errors == []
    assert source.calls == 1
    assert {result.handle for result in runner.results} == {"h"}


def test_different_accounts_do_not_block_each_other(factory: TTLKeyValueStoreFactory) -> None:
    source = CountingSource(delay=0.05)
    cached = _cached(factory, source, {"a": timedelta(hours=1), "b": timedelta(hours=1)})
    threads = [threading.Thread(target=cached.fetch, args=(account,)) for account in ("a", "b")]
    started = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert source.calls == 2
    assert time.monotonic() - started < 0.095


def test_account_without_ttl_is_rejected(factory: TTLKeyValueStoreFactory) -> None:
    with pytest.raises(InvalidDataServiceSettingError, match="unknown"):
        _cached(factory, CountingSource(), {"h": timedelta(hours=1)}).fetch("unknown")


def test_platform_and_type_come_from_the_inner_source(factory: TTLKeyValueStoreFactory) -> None:
    cached = _cached(factory, CountingSource(), {})

    assert (cached.platform, cached.details_type) == ("codeforces", CodeforcesDetails)
    assert isinstance(cached, DetailsSource)


def test_dependencies_must_have_the_right_types(factory: TTLKeyValueStoreFactory) -> None:
    store = factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY)

    with pytest.raises(InvalidDataServiceSettingError, match="inner"):
        CachedDetailsSource("source", store, {})
    with pytest.raises(InvalidDataServiceSettingError, match="store"):
        CachedDetailsSource(CountingSource(), {}, {})
