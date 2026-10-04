from datetime import timedelta

import pytest

from main.package.service.agent import AnswerCache, InvalidAgentServiceSettingError
from main.package.ttl_key_value_store import TTLKeyValueStoreFactory, TTLKeyValueStoreImpl


def _cache(factory: TTLKeyValueStoreFactory, ttl: timedelta = timedelta(hours=6)) -> AnswerCache:
    return AnswerCache(store=factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY), ttl=ttl)


def test_equivalent_questions_share_one_entry(ttl_factory: TTLKeyValueStoreFactory) -> None:
    cache = _cache(ttl_factory)
    cache.put("What does Sahib do?", "concise", "Backend engineering.")

    for question in ["what does sahib do", "  WHAT   does Sahib\tdo?!  ", "What does Sahib do."]:
        assert cache.get(question, "concise") == "Backend engineering."
    assert cache.get("What does Sahib build?", "concise") is None


def test_variants_are_cached_separately(ttl_factory: TTLKeyValueStoreFactory) -> None:
    cache = _cache(ttl_factory)
    cache.put("Who?", "concise", "Short.")
    cache.put("Who?", "detailed", "Long.")

    assert (cache.get("Who?", "concise"), cache.get("Who?", "detailed"), cache.get("Who?", "plan")) == ("Short.", "Long.", None)


def test_keys_are_hashed_and_prefixed() -> None:
    key = AnswerCache.key("Hello?", "plan")

    assert key.startswith("agent-answer:plan:") and len(key) == len("agent-answer:plan:") + 64
    assert "hello" not in key
    assert AnswerCache.normalize("  Hello   THERE?! ") == "hello there"


def test_entries_expire(ttl_factory: TTLKeyValueStoreFactory) -> None:
    cache = _cache(ttl_factory, ttl=timedelta(microseconds=1))
    cache.put("Q", "concise", "A")

    assert cache.get("Q", "concise") is None


@pytest.mark.parametrize(("store", "ttl"), [("store", timedelta(hours=1)), (None, timedelta(0)), (None, 3600)])
def test_invalid_settings_raise(ttl_factory: TTLKeyValueStoreFactory, store: object, ttl: object) -> None:
    real_store = ttl_factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY)
    with pytest.raises(InvalidAgentServiceSettingError):
        AnswerCache(store=real_store if store is None else store, ttl=ttl)
