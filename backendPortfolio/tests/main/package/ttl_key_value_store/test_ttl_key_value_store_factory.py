from datetime import timedelta

import pytest

from main.package.ttl_key_value_store import (
    InvalidSweepIntervalError,
    MissingSweepIntervalError,
    TTLKeyValueStoreError,
    TTLKeyValueStoreFactory,
    TTLKeyValueStoreImpl,
    UnsupportedTTLKeyValueStoreImplError,
)
from main.package.ttl_key_value_store.in_memory_ttl_key_value_store import _InMemoryTTLKeyValueStore


def test_builds_every_registered_implementation(ttl_factory: TTLKeyValueStoreFactory) -> None:
    store = ttl_factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY)

    assert isinstance(store, _InMemoryTTLKeyValueStore)


def test_returns_the_same_instance_every_time(ttl_factory: TTLKeyValueStoreFactory) -> None:
    first = ttl_factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY)

    assert ttl_factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY) is first


def test_accepts_the_enum_value_as_plain_string(ttl_factory: TTLKeyValueStoreFactory) -> None:
    store = ttl_factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY)

    assert ttl_factory.get_ttl_key_value_store("in_memory") is store


def test_passes_each_impl_its_own_interval() -> None:
    factory = TTLKeyValueStoreFactory({TTLKeyValueStoreImpl.IN_MEMORY: timedelta(minutes=7)})
    try:
        store = factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY)
        assert store._sweep_interval_seconds == 420.0
    finally:
        factory.close_all()


def test_missing_interval_for_registered_impl_raises() -> None:
    with pytest.raises(MissingSweepIntervalError, match="in_memory"):
        TTLKeyValueStoreFactory({})


def test_interval_for_unregistered_impl_raises() -> None:
    with pytest.raises(UnsupportedTTLKeyValueStoreImplError, match="redis"):
        TTLKeyValueStoreFactory({TTLKeyValueStoreImpl.IN_MEMORY: timedelta(minutes=1), "redis": timedelta(minutes=1)})


def test_invalid_interval_is_rejected_by_the_implementation() -> None:
    with pytest.raises(InvalidSweepIntervalError):
        TTLKeyValueStoreFactory({TTLKeyValueStoreImpl.IN_MEMORY: timedelta(0)})


@pytest.mark.parametrize("impl", ["redis", "", None])
def test_get_unsupported_impl_raises(ttl_factory: TTLKeyValueStoreFactory, impl: object) -> None:
    with pytest.raises(UnsupportedTTLKeyValueStoreImplError):
        ttl_factory.get_ttl_key_value_store(impl)


def test_close_all_stops_every_store_and_is_safe_twice() -> None:
    factory = TTLKeyValueStoreFactory({TTLKeyValueStoreImpl.IN_MEMORY: timedelta(minutes=1)})
    store = factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY)
    assert store._sweeper.is_alive()

    factory.close_all()
    factory.close_all()

    assert not store._sweeper.is_alive()


@pytest.mark.parametrize("error_type", [MissingSweepIntervalError, UnsupportedTTLKeyValueStoreImplError])
def test_errors_share_the_store_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, TTLKeyValueStoreError)
