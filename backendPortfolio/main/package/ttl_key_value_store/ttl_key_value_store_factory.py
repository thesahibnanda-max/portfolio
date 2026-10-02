from collections.abc import Callable, Mapping
from datetime import timedelta

from main.package.ttl_key_value_store.exceptions import (
    MissingSweepIntervalError,
    UnsupportedTTLKeyValueStoreImplError,
)
from main.package.ttl_key_value_store.in_memory_ttl_key_value_store import _InMemoryTTLKeyValueStore
from main.package.ttl_key_value_store.ttl_key_value_store import TTLKeyValueStore, TTLKeyValueStoreImpl


class TTLKeyValueStoreFactory:
    _IMPLS: dict[TTLKeyValueStoreImpl, Callable[[timedelta], TTLKeyValueStore]] = {
        TTLKeyValueStoreImpl.IN_MEMORY: _InMemoryTTLKeyValueStore,
    }

    def __init__(self, sweep_intervals: Mapping[TTLKeyValueStoreImpl, timedelta]):
        missing_impls = self._IMPLS.keys() - sweep_intervals.keys()
        if missing_impls:
            raise MissingSweepIntervalError(f"No sweep interval configured for TTL key-value store impls: {sorted(missing_impls)}")

        unknown_impls = sweep_intervals.keys() - self._IMPLS.keys()
        if unknown_impls:
            raise UnsupportedTTLKeyValueStoreImplError(f"Unsupported TTL key-value store impls: {sorted(unknown_impls)}")

        self._stores: dict[TTLKeyValueStoreImpl, TTLKeyValueStore] = {
            impl: store_class(sweep_intervals[impl]) for impl, store_class in self._IMPLS.items()
        }

    def get_ttl_key_value_store(self, impl: TTLKeyValueStoreImpl) -> TTLKeyValueStore:
        store = self._stores.get(impl)
        if store is None:
            raise UnsupportedTTLKeyValueStoreImplError(f"Unsupported TTL key-value store impl: {impl!r}")

        return store

    def close_all(self) -> None:
        for store in self._stores.values():
            store.close()
