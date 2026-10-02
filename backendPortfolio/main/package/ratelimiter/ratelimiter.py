import math
import re
import threading
import time
from collections.abc import Mapping
from datetime import timedelta
from types import MappingProxyType

from limits import RateLimitItem, RateLimitItemPerSecond
from limits.errors import ConfigurationError
from limits.storage import Storage, storage_from_string
from limits.strategies import SlidingWindowCounterRateLimiter

from main.package.ratelimiter.dto import RateLimitRule, RateLimitScope
from main.package.ratelimiter.exceptions import (
    InvalidRateLimitArgumentError,
    InvalidRateLimiterSettingError,
    RateLimitExceededError,
)

_API_NAME = re.compile(r"[a-z0-9_]+")
_GLOBAL_IDENTIFIER = "all"
_MIN_RETRY_AFTER_SECONDS = 1


class RateLimiter:
    def __init__(
        self,
        *,
        storage_uri: str,
        key_prefix: str,
        rules: Mapping[str, Mapping[RateLimitScope, RateLimitRule]],
    ) -> None:
        if not isinstance(key_prefix, str) or not key_prefix.strip():
            raise InvalidRateLimiterSettingError("key_prefix must be a non-empty string")

        items = self._build_items(key_prefix.strip(), rules)
        self._storage = self._build_storage(storage_uri)
        self._strategy = SlidingWindowCounterRateLimiter(self._storage)
        self._items = items
        self._storage_lock = threading.Lock()

    @property
    def apis(self) -> frozenset[str]:
        return frozenset(self._items)

    def check(self, api: str, *, client_ip: str | None, session_id: str | None) -> None:
        items = self._items_for(api)

        for scope, identifier in self._identifiers(client_ip, session_id):
            item = items[scope]
            with self._storage_lock:
                allowed = self._strategy.hit(item, api, scope, identifier)
                retry_after = None if allowed else self._retry_after(item, api, scope, identifier)

            if retry_after is not None:
                raise RateLimitExceededError(
                    f"Rate limit for {api} by {scope} exceeded; retry after {retry_after.total_seconds():.0f}s",
                    api=api,
                    scope=scope,
                    retry_after=retry_after,
                )

    def remaining(self, api: str, *, client_ip: str | None, session_id: str | None) -> Mapping[RateLimitScope, int]:
        items = self._items_for(api)
        remaining: dict[RateLimitScope, int] = {}

        for scope, identifier in self._identifiers(client_ip, session_id):
            with self._storage_lock:
                remaining[scope] = self._strategy.get_window_stats(items[scope], api, scope, identifier).remaining

        return MappingProxyType(remaining)

    def reset(self) -> None:
        with self._storage_lock:
            self._storage.reset()

    def _items_for(self, api: str) -> Mapping[RateLimitScope, RateLimitItem]:
        if not isinstance(api, str) or api not in self._items:
            raise InvalidRateLimitArgumentError(f"Unknown rate-limited api {api!r}")

        return self._items[api]

    def _retry_after(self, item: RateLimitItem, api: str, scope: RateLimitScope, identifier: str) -> timedelta:
        reset_time = self._strategy.get_window_stats(item, api, scope, identifier).reset_time
        seconds = max(_MIN_RETRY_AFTER_SECONDS, math.ceil(reset_time - time.time()))

        return timedelta(seconds=min(seconds, item.get_expiry()))

    @staticmethod
    def _identifiers(client_ip: str | None, session_id: str | None) -> tuple[tuple[RateLimitScope, str], ...]:
        identifiers = {
            RateLimitScope.IP: client_ip,
            RateLimitScope.SESSION: session_id,
            RateLimitScope.GLOBAL: _GLOBAL_IDENTIFIER,
        }

        for scope, identifier in identifiers.items():
            if identifier is not None and (not isinstance(identifier, str) or not identifier.strip()):
                raise InvalidRateLimitArgumentError(f"{scope} identifier must be a non-empty string or None")

        return tuple((scope, identifier) for scope, identifier in identifiers.items() if identifier is not None)

    @staticmethod
    def _build_storage(storage_uri: str) -> Storage:
        if not isinstance(storage_uri, str) or not storage_uri.strip():
            raise InvalidRateLimiterSettingError("storage_uri must be a non-empty string")

        try:
            storage = storage_from_string(storage_uri.strip())
        except ConfigurationError as error:
            raise InvalidRateLimiterSettingError(f"storage_uri cannot be used: {error}") from error

        if not isinstance(storage, Storage):
            raise InvalidRateLimiterSettingError("storage_uri must name a synchronous storage, not an async+ one")

        return storage

    @staticmethod
    def _build_items(
        key_prefix: str,
        rules: Mapping[str, Mapping[RateLimitScope, RateLimitRule]],
    ) -> Mapping[str, Mapping[RateLimitScope, RateLimitItem]]:
        if not isinstance(rules, Mapping) or not rules:
            raise InvalidRateLimiterSettingError("rules must be a non-empty mapping of api name to scope rules")

        items: dict[str, Mapping[RateLimitScope, RateLimitItem]] = {}
        for api, scope_rules in rules.items():
            if not isinstance(api, str) or not _API_NAME.fullmatch(api):
                raise InvalidRateLimiterSettingError(f"api name {api!r} must match {_API_NAME.pattern}")

            if not isinstance(scope_rules, Mapping) or set(scope_rules) != set(RateLimitScope):
                raise InvalidRateLimiterSettingError(f"rules for {api} must have exactly one rule for each of {sorted(RateLimitScope)}")

            if not all(isinstance(rule, RateLimitRule) for rule in scope_rules.values()):
                raise InvalidRateLimiterSettingError(f"every rule for {api} must be a RateLimitRule")

            items[api] = MappingProxyType(
                {
                    RateLimitScope(scope): RateLimitItemPerSecond(
                        rule.limit,
                        int(rule.window.total_seconds()),
                        namespace=key_prefix,
                    )
                    for scope, rule in scope_rules.items()
                }
            )

        return MappingProxyType(items)
