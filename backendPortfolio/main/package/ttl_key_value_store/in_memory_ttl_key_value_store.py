import logging
import threading
from datetime import UTC, datetime, timedelta

from main.package.ttl_key_value_store.exceptions import (
    InvalidSweepIntervalError,
    InvalidTTLKeyValueEntryError,
)
from main.package.ttl_key_value_store.ttl_key_value_store import TTLKeyValueStore

_logger = logging.getLogger(__name__)


class _InMemoryTTLKeyValueStore(TTLKeyValueStore):
    def __init__(self, sweep_interval: timedelta) -> None:
        if not isinstance(sweep_interval, timedelta) or sweep_interval <= timedelta(0):
            raise InvalidSweepIntervalError("Sweep interval must be a positive timedelta")

        self._sweep_interval_seconds = sweep_interval.total_seconds()
        self._entries: dict[str, tuple[str, datetime]] = {}
        self._lock = threading.Lock()
        self._stop_sweeper = threading.Event()
        self._sweeper = threading.Thread(
            target=self._run_sweeper,
            name="in-memory-ttl-key-value-store-sweeper",
            daemon=True,
        )
        self._sweeper.start()

    def get(self, key: str) -> str | None:
        now = datetime.now(UTC)

        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None

            value, expires_at = entry
            if expires_at <= now:
                del self._entries[key]
                return None

            return value

    def set(self, key: str, value: str, expires_at: datetime) -> None:
        self._validate_entry(key, expires_at)

        with self._lock:
            self._entries[key] = (value, expires_at)

    def set_if_absent(self, key: str, value: str, expires_at: datetime) -> bool:
        self._validate_entry(key, expires_at)
        now = datetime.now(UTC)

        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[1] > now:
                return False

            self._entries[key] = (value, expires_at)
            return True

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def close(self) -> None:
        self._stop_sweeper.set()
        self._sweeper.join()

    def _run_sweeper(self) -> None:
        while not self._stop_sweeper.wait(self._sweep_interval_seconds):
            try:
                self._purge_expired()
            except Exception:
                _logger.exception("Failed to purge expired entries from the in-memory TTL key-value store")

    def _purge_expired(self) -> None:
        now = datetime.now(UTC)

        with self._lock:
            self._entries = {
                key: entry for key, entry in self._entries.items() if entry[1] > now
            }

    @staticmethod
    def _validate_entry(key: str, expires_at: datetime) -> None:
        if not key:
            raise InvalidTTLKeyValueEntryError("Key cannot be empty")

        if expires_at.tzinfo is None:
            raise InvalidTTLKeyValueEntryError("expires_at must be timezone-aware")
