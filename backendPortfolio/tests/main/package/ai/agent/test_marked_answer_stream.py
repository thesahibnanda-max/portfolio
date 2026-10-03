import pytest

from main.package.ai.agent import AgentStreamStateError, InvalidAgentSettingError, MarkedAnswerStream
from main.package.ai.orchestrator import QueryScope
from main.package.clients.groq import GroqChatCompletionStream, GroqStreamCancelledError, GroqStreamEnd, GroqTextDelta
from tests.main.package.ai.agent.fakes import FALLBACKS, MARKERS, groq_stream


def _marked(*deltas: str, **options: object) -> tuple[MarkedAnswerStream, GroqChatCompletionStream]:
    upstream = groq_stream(*deltas, **options)
    return MarkedAnswerStream(upstream, markers=MARKERS, fallback_messages=FALLBACKS), upstream


def _read(stream: MarkedAnswerStream) -> list[object]:
    with stream:
        return list(stream)


def _texts(events: list[object]) -> list[str]:
    return [event.text for event in events if isinstance(event, GroqTextDelta)]


def _unknown_event(stream: GroqChatCompletionStream) -> object:
    return "not an event"


def test_normal_answer_streams_through_without_delay() -> None:
    stream, _ = _marked("He ", "builds ", "systems.")
    events = _read(stream)

    assert _texts(events) == ["He ", "builds ", "systems."]
    assert isinstance(events[-1], GroqStreamEnd) and events[-1].text == "He builds systems."
    assert stream.scope is QueryScope.IN_SCOPE
    assert stream.usage.total_tokens == 940


def test_leading_whitespace_and_marker_lookalikes_are_released_together() -> None:
    stream, _ = _marked(" ", "\n", "⟂", "Not a marker")

    assert _texts(_read(stream)) == [" \n⟂Not a marker"]
    assert stream.scope is QueryScope.IN_SCOPE


@pytest.mark.parametrize(
    ("deltas", "scope"),
    [
        (("⟂OOS",), QueryScope.NOT_RELATED_TO_PORTFOLIO),
        (("  ⟂", "O", "OS"), QueryScope.NOT_RELATED_TO_PORTFOLIO),
        (("⟂INJ", " and more text"), QueryScope.PROMPT_INJECTION),
        (("\n⟂UN", "S"), QueryScope.UNSAFE),
    ],
)
def test_marker_is_replaced_by_the_fallback_and_the_call_is_cancelled(deltas: tuple[str, ...], scope: QueryScope) -> None:
    stream, upstream = _marked(*deltas)
    events = _read(stream)

    assert _texts(events) == [FALLBACKS[scope]]
    assert events[-1] == GroqStreamEnd(text=FALLBACKS[scope])
    assert stream.scope is scope
    assert stream.usage is None
    assert upstream.cancelled


def test_an_unfinished_marker_at_the_end_is_kept_as_text() -> None:
    stream, _ = _marked("⟂O")
    events = _read(stream)

    assert _texts(events) == ["⟂O"]
    assert events[-1].text == "⟂O"
    assert stream.scope is QueryScope.IN_SCOPE


def test_empty_answer_just_ends() -> None:
    stream, _ = _marked()
    events = _read(stream)

    assert len(events) == 1 and isinstance(events[0], GroqStreamEnd)


def test_nothing_is_read_after_the_end() -> None:
    stream, _ = _marked("Hi")
    with stream:
        list(stream)
        with pytest.raises(StopIteration):
            next(stream)


def test_cancel_raises_like_the_groq_stream() -> None:
    stream, upstream = _marked("Hi")
    with stream:
        stream.cancel()
        with pytest.raises(GroqStreamCancelledError):
            next(stream)

    assert upstream.cancelled


def test_iterating_returns_itself() -> None:
    stream, _ = _marked("Hi")
    assert iter(stream) is stream


def test_unknown_events_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    stream, _ = _marked("Hi")
    monkeypatch.setattr(GroqChatCompletionStream, "__next__", _unknown_event)

    with stream, pytest.raises(AgentStreamStateError, match="Unexpected"):
        next(stream)


@pytest.mark.parametrize(
    "settings",
    [
        {"markers": "⟂OOS", "fallback_messages": FALLBACKS},
        {"markers": MARKERS, "fallback_messages": None},
        {"markers": MARKERS, "fallback_messages": {QueryScope.UNSAFE: "No."}},
    ],
)
def test_invalid_settings_raise(settings: dict) -> None:
    with pytest.raises(InvalidAgentSettingError):
        MarkedAnswerStream(groq_stream("Hi"), **settings)


def test_stream_must_be_a_groq_stream() -> None:
    with pytest.raises(InvalidAgentSettingError, match="GroqChatCompletionStream"):
        MarkedAnswerStream("stream", markers=MARKERS, fallback_messages=FALLBACKS)
