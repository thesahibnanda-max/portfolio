from collections.abc import Iterator
from datetime import timedelta

import pytest

from main.package.ttl_key_value_store import TTLKeyValueStoreFactory, TTLKeyValueStoreImpl

SWEEP_INTERVALS = {TTLKeyValueStoreImpl.IN_MEMORY: timedelta(minutes=20)}

FAKE_GROQ_API_KEYS = "test-groq-key-1,test-groq-key-2"
FAKE_MAIL_USERNAME = "portfolio.mailer@example.com"
FAKE_MAIL_PASSWORD = "test-mail-app-password"
FAKE_MAIL_USERNAME_2 = "portfolio.mailer2@example.com"
FAKE_MAIL_PASSWORD_2 = "test-mail-app-password-2"
FAKE_RECIPIENT_MAIL = "owner@example.com"

HTTP_TIMEOUTS = {
    "connect_timeout": timedelta(seconds=10),
    "read_timeout": timedelta(seconds=60),
    "write_timeout": timedelta(seconds=60),
    "pool_timeout": timedelta(seconds=10),
}


@pytest.fixture
def ttl_factory() -> Iterator[TTLKeyValueStoreFactory]:
    factory = TTLKeyValueStoreFactory(SWEEP_INTERVALS)
    yield factory
    factory.close_all()


@pytest.fixture
def config_env(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("GROQ_API_KEYS", FAKE_GROQ_API_KEYS)
    monkeypatch.setenv("MAIL_ACCOUNT_1_USERNAME", FAKE_MAIL_USERNAME)
    monkeypatch.setenv("MAIL_ACCOUNT_1_PASSWORD", FAKE_MAIL_PASSWORD)
    monkeypatch.setenv("MAIL_ACCOUNT_2_USERNAME", FAKE_MAIL_USERNAME_2)
    monkeypatch.setenv("MAIL_ACCOUNT_2_PASSWORD", FAKE_MAIL_PASSWORD_2)
    monkeypatch.setenv("RECIPIENT_MAIL", FAKE_RECIPIENT_MAIL)
    monkeypatch.delenv("ENVYAML_STRICT_DISABLE", raising=False)
    return FAKE_GROQ_API_KEYS


@pytest.fixture
def http_timeouts() -> dict[str, timedelta]:
    return dict(HTTP_TIMEOUTS)
