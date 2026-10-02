from datetime import UTC, datetime

import pytest

from main.package.ai.common import ChatMessage
from main.package.repository import StoredMessage
from main.package.service.chat import (
    ChatMessageTooLongError,
    EmptyChatMessageError,
    HistoryWindow,
    InvalidChatMessageError,
    InvalidChatServiceSettingError,
    MessageValidator,
)

NOW = datetime(2026, 10, 2, tzinfo=UTC)


def _stored(index: int, content: str) -> StoredMessage:
    return StoredMessage(message_id=index, role="user" if index % 2 else "assistant", content=content, created_at=NOW)


def test_validator_trims_and_accepts_up_to_the_limit() -> None:
    validator = MessageValidator(max_message_chars=10)

    assert validator.validate("  hello  ") == "hello"
    assert validator.validate("x" * 10) == "x" * 10
    assert validator.max_message_chars == 10


def test_validator_rejects_messages_over_the_limit() -> None:
    with pytest.raises(ChatMessageTooLongError) as error:
        MessageValidator(max_message_chars=10).validate("x" * 11)

    assert (error.value.max_chars, error.value.actual_chars) == (10, 11)
    assert isinstance(error.value, InvalidChatMessageError)


def test_validator_counts_characters_after_trimming() -> None:
    assert MessageValidator(max_message_chars=3).validate("   abc   ") == "abc"


@pytest.mark.parametrize("message", ["", "   ", "\n\t", None, 42])
def test_validator_rejects_empty_or_non_text(message: object) -> None:
    with pytest.raises(EmptyChatMessageError):
        MessageValidator(max_message_chars=10).validate(message)


@pytest.mark.parametrize("value", [0, -1, True, "10"])
def test_validator_limit_must_be_positive(value: object) -> None:
    with pytest.raises(InvalidChatServiceSettingError):
        MessageValidator(max_message_chars=value)


def test_history_keeps_the_newest_messages_by_count() -> None:
    messages = [_stored(index, f"m{index}") for index in range(1, 8)]

    assert [message.content for message in HistoryWindow(max_messages=3, max_chars=1000).select(messages)] == ["m5", "m6", "m7"]


def test_history_drops_the_oldest_until_it_fits_the_character_budget() -> None:
    messages = [_stored(1, "a" * 10), _stored(2, "b" * 10), _stored(3, "c" * 10)]

    assert [message.content for message in HistoryWindow(max_messages=10, max_chars=20).select(messages)] == ["b" * 10, "c" * 10]


def test_history_always_keeps_the_newest_message() -> None:
    messages = [_stored(1, "a" * 50), _stored(2, "b" * 50)]

    assert [message.content for message in HistoryWindow(max_messages=10, max_chars=5).select(messages)] == ["b" * 50]


def test_history_converts_to_chat_messages() -> None:
    selected = HistoryWindow(max_messages=5, max_chars=100).select([_stored(1, "hi"), _stored(2, "hello")])

    assert selected == (ChatMessage(role="user", content="hi"), ChatMessage(role="assistant", content="hello"))


def test_empty_history_is_empty() -> None:
    assert HistoryWindow(max_messages=5, max_chars=100).select(()) == ()


@pytest.mark.parametrize("overrides", [{"max_messages": 0}, {"max_chars": -1}, {"max_messages": True}, {"max_chars": "5"}])
def test_history_settings_must_be_positive(overrides: dict) -> None:
    with pytest.raises(InvalidChatServiceSettingError):
        HistoryWindow(**({"max_messages": 5, "max_chars": 100} | overrides))
