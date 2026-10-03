import hashlib
import re
from datetime import UTC, datetime, timedelta

from main.package.service.agent.exceptions import InvalidAgentServiceSettingError
from main.package.ttl_key_value_store import TTLKeyValueStore

_KEY_PREFIX = "agent-answer:"
_WHITESPACE = re.compile(r"\s+")
_TRAILING_PUNCTUATION = "?!.,;: "


class AnswerCache:
    def __init__(self, *, store: TTLKeyValueStore, ttl: timedelta) -> None:
        if not isinstance(store, TTLKeyValueStore):
            raise InvalidAgentServiceSettingError("store must be a TTLKeyValueStore")

        if not isinstance(ttl, timedelta) or ttl <= timedelta(0):
            raise InvalidAgentServiceSettingError("ttl must be a positive timedelta")

        self._store = store
        self._ttl = ttl

    def get(self, question: str) -> str | None:
        return self._store.get(self.key(question))

    def put(self, question: str, answer: str) -> None:
        self._store.set(self.key(question), answer, datetime.now(UTC) + self._ttl)

    @staticmethod
    def key(question: str) -> str:
        normalized = _WHITESPACE.sub(" ", question.casefold()).strip().rstrip(_TRAILING_PUNCTUATION)
        return _KEY_PREFIX + hashlib.sha256(normalized.encode()).hexdigest()
