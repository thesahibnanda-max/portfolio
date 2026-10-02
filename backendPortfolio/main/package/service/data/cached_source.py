import threading
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from pydantic import TypeAdapter

from main.package.service.data.exceptions import InvalidDataServiceSettingError
from main.package.service.data.sources import DetailsSource
from main.package.ttl_key_value_store import TTLKeyValueStore

_KEY_PREFIX = "data"


class CachedDetailsSource[T](DetailsSource[T]):
    def __init__(self, inner: DetailsSource[T], store: TTLKeyValueStore, cache_ttls: Mapping[str, timedelta]) -> None:
        if not isinstance(inner, DetailsSource):
            raise InvalidDataServiceSettingError("inner must be a DetailsSource")

        if not isinstance(store, TTLKeyValueStore):
            raise InvalidDataServiceSettingError("store must be a TTLKeyValueStore")

        self._inner = inner
        self._store = store
        self._cache_ttls = dict(cache_ttls)
        self._adapter = TypeAdapter(inner.details_type)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    @property
    def platform(self) -> str:
        return self._inner.platform

    @property
    def details_type(self) -> type[T]:
        return self._inner.details_type

    def cache_key(self, account: str) -> str:
        return f"{_KEY_PREFIX}:{self.platform}:{account}"

    def fetch(self, account: str) -> T:
        ttl = self._cache_ttls.get(account)
        if ttl is None:
            raise InvalidDataServiceSettingError(f"No cache TTL is configured for {self.platform} account {account}")

        key = self.cache_key(account)
        cached = self._read(key)
        if cached is not None:
            return cached

        with self._lock_for(key):
            cached = self._read(key)
            if cached is not None:
                return cached

            value = self._inner.fetch(account)
            self._store.set(key, self._adapter.dump_json(value).decode("utf-8"), datetime.now(UTC) + ttl)
            return value

    def _read(self, key: str) -> T | None:
        stored = self._store.get(key)
        return self._adapter.validate_json(stored) if stored is not None else None

    def _lock_for(self, key: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.Lock())
