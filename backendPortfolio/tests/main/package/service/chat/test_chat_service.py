import json
import threading
from collections.abc import Iterator
from datetime import timedelta
from functools import partial
from pathlib import Path

import httpx
import pytest

from main.config import AppConfig
from main.package.ai.common import ContextType
from main.package.ai.orchestrator import Orchestrator, QueryScope
from main.package.ai.worker import Worker
from main.package.clients.groq import GroqHTTPStatusError, GroqRequestError, GroqStreamIncompleteError
from main.package.repository import ChatNotFoundError, NewMessage, SqliteChatRepository
from main.package.service.chat import (
    ChatDoneEvent,
    ChatFullError,
    ChatMessageTooLongError,
    ChatReply,
    ChatReplyStream,
    ChatService,
    ChatServiceError,
    ChatStreamCancelledError,
    ChatStreamStateError,
    ChatTokenEvent,
    EmptyChatMessageError,
    HistoryWindow,
    InvalidChatServiceSettingError,
    MessageValidator,
)
from main.package.ttl_key_value_store import TTLKeyValueStoreFactory
from tests.main.package.ai.fakes import OWNER_NAME, answering, groq_client, selector
from tests.main.package.clients.groq.sse import DONE, SSE_HEADERS, chunk
from tests.main.package.service.context.fakes import Upstream, aggregator, data_service, ttl_factory
from tests.support import ConcurrentRunner, RecordingTransport, ResponseSpec

FALLBACKS = {
    QueryScope.NOT_RELATED_TO_PORTFOLIO: "Please ask about the portfolio.",
    QueryScope.PROMPT_INJECTION: "I can't change how I work.",
    QueryScope.UNSAFE: "I can't help with that.",
}
ANSWER_STREAM = chunk("He has ") + chunk("a 1832") + chunk(" rating.") + chunk(finish_reason="stop") + DONE


def _decision(scope: str, contexts: list[str]) -> str:
    return json.dumps({"scope": scope, "requiredContexts": contexts, "reason": "test"})


class BlockingStream(httpx.MockTransport):
    def __init__(self) -> None:
        self.first_sent = threading.Event()
        self.release = threading.Event()
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=self._body(), headers=SSE_HEADERS)

    def _body(self) -> Iterator[bytes]:
        yield chunk("Partial").encode()
        self.first_sent.set()
        self.release.wait(5)
        yield (chunk(" rest") + DONE).encode()


class Harness:
    def __init__(self, tmp_path: Path, factory: TTLKeyValueStoreFactory) -> None:
        self.repository = SqliteChatRepository(
            database_path=tmp_path / "chat.sqlite3",
            session_ttl=timedelta(hours=12),
            sweep_interval=timedelta(minutes=20),
            busy_timeout=timedelta(seconds=5),
        )
        self.upstream = Upstream()
        self.data_service = data_service(self.upstream, factory)
        self.aggregator = aggregator(self.data_service)
        self.orchestrator_transport = answering(_decision("IN_SCOPE", ["CODEFORCES"]))
        self.worker_transport: httpx.BaseTransport = answering("He has a 1832 rating.")
        self.session = self.repository.create_session()
        self.chat = self.repository.create_chat(self.session.session_id, "Ratings")

    def service(self, **overrides: object) -> ChatService:
        orchestrator = Orchestrator(
            groq_client(self.orchestrator_transport),
            selector(),
            owner_name=OWNER_NAME,
            temperature=0.0,
            top_p=1.0,
            max_completion_tokens=256,
        )
        worker = Worker(groq_client(self.worker_transport), selector(), owner_name=OWNER_NAME, max_completion_tokens=256)
        settings = {
            "repository": self.repository,
            "orchestrator": orchestrator,
            "worker": worker,
            "context_aggregator": self.aggregator,
            "message_validator": MessageValidator(max_message_chars=100),
            "history_window": HistoryWindow(max_messages=20, max_chars=12000),
            "fallback_messages": FALLBACKS,
            "max_messages_per_chat": 200,
        } | overrides
        return ChatService(**settings)

    def route_to(self, scope: str, contexts: list[str]) -> None:
        self.orchestrator_transport = answering(_decision(scope, contexts))

    def stream_answer(self, body: str) -> None:
        self.worker_transport = RecordingTransport(ResponseSpec(content=body.encode(), headers=SSE_HEADERS))

    def stored_messages(self) -> list[tuple[str, str]]:
        chat = self.repository.get_chat(self.session.session_id, self.chat.chat_id)
        return [(message.role, message.content) for message in chat.messages]

    def worker_prompt(self) -> str:
        return json.loads(self.worker_transport.last_request.content)["messages"][1]["content"]

    def close(self) -> None:
        self.aggregator.close()
        self.data_service.close()
        self.repository.close()


@pytest.fixture
def factory() -> Iterator[TTLKeyValueStoreFactory]:
    instance = ttl_factory()
    yield instance
    instance.close_all()


@pytest.fixture
def harness(tmp_path: Path, factory: TTLKeyValueStoreFactory) -> Iterator[Harness]:
    instance = Harness(tmp_path, factory)
    yield instance
    instance.close()


def _send(service: ChatService, harness: Harness, message: str) -> ChatReply:
    return service.send_message(harness.session.session_id, harness.chat.chat_id, message)


def _stream(service: ChatService, harness: Harness, message: str) -> ChatReplyStream:
    return service.stream_message(harness.session.session_id, harness.chat.chat_id, message)


def _read(stream: ChatReplyStream) -> list:
    with stream:
        return list(stream)


def test_in_scope_message_is_answered_with_context_and_saved(harness: Harness) -> None:
    reply = _send(harness.service(), harness, "  What is his Codeforces rating?  ")

    assert reply.answer == "He has a 1832 rating."
    assert reply.scope is QueryScope.IN_SCOPE
    assert reply.required_contexts == (ContextType.CODEFORCES,)
    assert harness.stored_messages() == [("user", "What is his Codeforces rating?"), ("assistant", "He has a 1832 rating.")]
    assert [message.content for message in reply.chat.messages] == ["What is his Codeforces rating?", "He has a 1832 rating."]
    prompt = harness.worker_prompt()
    assert prompt.startswith("Context:\nCODEFORCES (shisukenohara): current rating 1832")
    assert prompt.endswith("Current message:\nWhat is his Codeforces rating?")


def test_in_scope_without_data_skips_the_data_service(harness: Harness) -> None:
    harness.route_to("IN_SCOPE", [])
    reply = _send(harness.service(), harness, "hi")

    assert reply.required_contexts == (ContextType.NONE,)
    assert harness.upstream.request_count() == 0
    assert harness.worker_prompt() == "Current message:\nhi"


def test_history_is_sent_to_both_ais(harness: Harness) -> None:
    harness.repository.add_messages(
        harness.session.session_id,
        harness.chat.chat_id,
        [NewMessage(role="user", content="Who is he?"), NewMessage(role="assistant", content="A backend engineer.")],
    )
    _send(harness.service(), harness, "And his rating?")

    orchestrator_prompt = json.loads(harness.orchestrator_transport.last_request.content)["messages"][1]["content"]
    expected = "Conversation so far:\nUSER: Who is he?\nASSISTANT: A backend engineer.\n\nCurrent message:\nAnd his rating?"
    assert orchestrator_prompt == expected
    assert harness.worker_prompt().endswith(expected)


@pytest.mark.parametrize("scope", [QueryScope.NOT_RELATED_TO_PORTFOLIO, QueryScope.PROMPT_INJECTION, QueryScope.UNSAFE])
def test_flagged_messages_get_the_configured_fallback_without_ai_or_data(harness: Harness, scope: QueryScope) -> None:
    harness.route_to(scope.value, [])
    reply = _send(harness.service(), harness, "Explain taxes")

    assert reply.answer == FALLBACKS[scope]
    assert reply.scope is scope
    assert reply.required_contexts == ()
    assert harness.worker_transport.requests == []
    assert harness.upstream.request_count() == 0
    assert harness.stored_messages() == [("user", "Explain taxes"), ("assistant", FALLBACKS[scope])]


@pytest.mark.parametrize(("message", "error_type"), [("", EmptyChatMessageError), ("   ", EmptyChatMessageError), ("x" * 101, ChatMessageTooLongError)])
@pytest.mark.parametrize("method", [_send, _stream])
def test_invalid_messages_are_rejected_before_any_call(harness: Harness, method, message: str, error_type: type[Exception]) -> None:
    with pytest.raises(error_type):
        method(harness.service(), harness, message)

    assert harness.orchestrator_transport.requests == []
    assert harness.stored_messages() == []


@pytest.mark.parametrize("method", [_send, _stream])
def test_full_chat_is_rejected_before_any_call(harness: Harness, method) -> None:
    harness.repository.add_messages(harness.session.session_id, harness.chat.chat_id, [NewMessage(role="user", content="one")])

    with pytest.raises(ChatFullError) as error:
        method(harness.service(max_messages_per_chat=2), harness, "two")

    assert error.value.max_messages == 2
    assert harness.orchestrator_transport.requests == []


def test_chat_exactly_at_room_for_one_turn_is_accepted(harness: Harness) -> None:
    assert len(_send(harness.service(max_messages_per_chat=2), harness, "hi").chat.messages) == 2


def test_unknown_or_foreign_chat_is_rejected(harness: Harness) -> None:
    other = harness.repository.create_session()

    with pytest.raises(ChatNotFoundError):
        harness.service().send_message(other.session_id, harness.chat.chat_id, "hi")

    assert harness.orchestrator_transport.requests == []


def test_worker_errors_save_nothing(harness: Harness) -> None:
    harness.worker_transport = RecordingTransport(ResponseSpec(503, text="down"))

    with pytest.raises(GroqHTTPStatusError):
        _send(harness.service(), harness, "rating?")

    assert harness.stored_messages() == []


def test_stream_yields_tokens_then_done_and_saves(harness: Harness) -> None:
    harness.stream_answer(ANSWER_STREAM)
    stream = _stream(harness.service(), harness, "rating?")

    assert harness.stored_messages() == []
    events = _read(stream)

    assert [event.text for event in events[:-1]] == ["He has ", "a 1832", " rating."]
    assert isinstance(events[-1], ChatDoneEvent)
    assert events[-1].reply.answer == "He has a 1832 rating."
    assert stream.completed is True and stream.reply == events[-1].reply
    assert harness.stored_messages() == [("user", "rating?"), ("assistant", "He has a 1832 rating.")]
    assert json.loads(harness.worker_transport.last_request.content)["stream"] is True


@pytest.mark.parametrize("scope", [QueryScope.NOT_RELATED_TO_PORTFOLIO, QueryScope.PROMPT_INJECTION, QueryScope.UNSAFE])
def test_flagged_stream_yields_the_fallback_then_done(harness: Harness, scope: QueryScope) -> None:
    harness.route_to(scope.value, [])
    events = _read(_stream(harness.service(), harness, "Explain taxes"))

    assert events[0] == ChatTokenEvent(text=FALLBACKS[scope])
    assert isinstance(events[1], ChatDoneEvent) and len(events) == 2
    assert harness.worker_transport.requests == []
    assert harness.stored_messages() == [("user", "Explain taxes"), ("assistant", FALLBACKS[scope])]


def test_stream_routing_happens_before_returning(harness: Harness) -> None:
    harness.stream_answer(ANSWER_STREAM)
    _stream(harness.service(), harness, "rating?")

    assert len(harness.orchestrator_transport.requests) == 1
    assert harness.worker_transport.requests == []


def test_incomplete_stream_saves_nothing(harness: Harness) -> None:
    harness.stream_answer(chunk("He has") + chunk(" a"))

    with pytest.raises(GroqStreamIncompleteError):
        _read(_stream(harness.service(), harness, "rating?"))

    assert harness.stored_messages() == []


def test_failed_stream_saves_nothing(harness: Harness) -> None:
    harness.worker_transport = RecordingTransport(error=httpx.ReadError)

    with pytest.raises(GroqRequestError):
        _read(_stream(harness.service(), harness, "rating?"))

    assert harness.stored_messages() == []


def test_cancelled_stream_saves_nothing(harness: Harness) -> None:
    transport = BlockingStream()
    harness.worker_transport = transport
    stream = _stream(harness.service(), harness, "rating?")
    events: list = []
    errors: list = []
    reader = threading.Thread(target=_collect, args=(stream, events, errors))
    reader.start()
    assert transport.first_sent.wait(5)

    stream.cancel()
    transport.release.set()
    reader.join(5)

    assert isinstance(errors[0], ChatStreamCancelledError)
    assert events == [ChatTokenEvent(text="Partial")]
    assert harness.stored_messages() == []


def _collect(stream: ChatReplyStream, events: list, errors: list) -> None:
    try:
        with stream:
            for event in stream:
                events.append(event)
    except Exception as error:
        errors.append(error)


def test_cancelled_fallback_stream_saves_nothing(harness: Harness) -> None:
    harness.route_to("UNSAFE", [])
    stream = _stream(harness.service(), harness, "bad")
    with stream:
        stream.cancel()
        with pytest.raises(ChatStreamCancelledError):
            next(stream)

    assert harness.stored_messages() == []


def test_cancel_after_completion_is_a_no_op(harness: Harness) -> None:
    harness.stream_answer(ANSWER_STREAM)
    stream = _stream(harness.service(), harness, "rating?")
    _read(stream)
    stream.cancel()

    assert stream.completed is True


def test_stream_state_rules(harness: Harness) -> None:
    harness.stream_answer(ANSWER_STREAM)
    stream = _stream(harness.service(), harness, "rating?")

    with pytest.raises(ChatStreamStateError):
        iter(stream)
    with pytest.raises(ChatStreamStateError):
        next(stream)
    with stream:
        with pytest.raises(ChatStreamStateError):
            stream.__enter__()
        list(stream)
        with pytest.raises(StopIteration):
            next(stream)
        with pytest.raises(ChatStreamStateError):
            iter(stream)
    stream.close()


def test_stream_needs_exactly_one_answer_source() -> None:
    with pytest.raises(ChatStreamStateError):
        ChatReplyStream(complete=str)
    with pytest.raises(ChatStreamStateError):
        ChatReplyStream(complete=str, answer_stream=object(), fallback_answer="x")


class UnknownEventStream:
    def __enter__(self) -> "UnknownEventStream":
        return self

    def __next__(self) -> str:
        return "not an event"

    def close(self) -> None:
        return None


def test_unknown_stream_events_are_rejected() -> None:
    with ChatReplyStream(complete=str, answer_stream=UnknownEventStream()) as stream:
        with pytest.raises(ChatStreamStateError, match="Unexpected"):
            next(stream)


def test_unentered_fallback_stream_closes_quietly() -> None:
    ChatReplyStream(complete=str, fallback_answer="x").close()


def test_parallel_turns_on_separate_chats(harness: Harness) -> None:
    service = harness.service()
    runner = ConcurrentRunner(partial(_own_chat_turn, service, harness)).run()

    assert runner.errors == []
    assert runner.results == [2] * 16


def _own_chat_turn(service: ChatService, harness: Harness) -> int:
    session = harness.repository.create_session()
    chat = harness.repository.create_chat(session.session_id)
    return len(service.send_message(session.session_id, chat.chat_id, "rating?").chat.messages)


@pytest.mark.parametrize(
    "overrides",
    [
        {"repository": None},
        {"orchestrator": "orchestrator"},
        {"worker": None},
        {"context_aggregator": None},
        {"message_validator": None},
        {"history_window": None},
        {"max_messages_per_chat": 1},
        {"max_messages_per_chat": True},
        {"fallback_messages": None},
        {"fallback_messages": {QueryScope.UNSAFE: "x"}},
        {"fallback_messages": FALLBACKS | {QueryScope.IN_SCOPE: "x"}},
        {"fallback_messages": FALLBACKS | {QueryScope.UNSAFE: "   "}},
        {"fallback_messages": FALLBACKS | {QueryScope.UNSAFE: 5}},
    ],
)
def test_invalid_settings_are_rejected(harness: Harness, overrides: dict) -> None:
    with pytest.raises(InvalidChatServiceSettingError):
        harness.service(**overrides)


def test_fallback_messages_accept_scope_values_as_strings(harness: Harness) -> None:
    harness.route_to("UNSAFE", [])
    service = harness.service(fallback_messages={scope.value: f"  {text}  " for scope, text in FALLBACKS.items()})

    assert _send(service, harness, "bad").answer == FALLBACKS[QueryScope.UNSAFE]


def test_errors_share_the_base() -> None:
    for error_type in (InvalidChatServiceSettingError, EmptyChatMessageError, ChatMessageTooLongError, ChatFullError, ChatStreamCancelledError, ChatStreamStateError):
        assert issubclass(error_type, ChatServiceError)


def test_builds_from_app_config(config_env: str, harness: Harness) -> None:
    chat = AppConfig.load().chat
    harness.route_to("NOT_RELATED_TO_PORTFOLIO", [])
    service = harness.service(
        message_validator=MessageValidator(max_message_chars=chat.max_message_chars),
        history_window=HistoryWindow(max_messages=chat.max_history_messages, max_chars=chat.max_history_chars),
        fallback_messages=chat.fallback_messages,
        max_messages_per_chat=chat.max_messages_per_chat,
    )

    assert _send(service, harness, "Explain taxes").answer == chat.fallback_messages[QueryScope.NOT_RELATED_TO_PORTFOLIO]
