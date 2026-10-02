from functools import partial
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest

from main.package.ai.orchestrator import QueryScope
from tests.main.package.clients.groq.sse import chunk
from tests.main.package.handler.fakes import (
    ANSWER,
    SESSION_HEADER,
    BlockingStreamBody,
    Harness,
    LiveServer,
    decision,
    new_chat,
    new_session,
    sse_events,
)
from main.package.service.chat import ChatReplyStream
from tests.support import wait_until

_ORIGINAL_CANCEL = ChatReplyStream.cancel


class CancelSpy:
    def __init__(self) -> None:
        self.completed_when_cancelled: list[bool] = []

    def record(self, stream: ChatReplyStream) -> None:
        self.completed_when_cancelled.append(stream.completed)
        _ORIGINAL_CANCEL(stream)


@pytest.fixture
def cancel_spy(monkeypatch: pytest.MonkeyPatch) -> CancelSpy:
    spy = CancelSpy()
    monkeypatch.setattr(ChatReplyStream, "cancel", _SpyDescriptor(spy))
    return spy


class _SpyDescriptor:
    def __init__(self, spy: CancelSpy) -> None:
        self._spy = spy

    def __get__(self, stream: ChatReplyStream, owner: type) -> partial:
        return partial(self._spy.record, stream)


@pytest.fixture
def harness(config_env: str, tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def _open(harness: Harness):
    client = harness.client()
    client.__enter__()
    session_id = new_session(client)
    return client, {SESSION_HEADER: session_id}, new_chat(client, session_id)


def _messages(client, headers: dict[str, str], chat_id: str) -> list[tuple[str, str]]:
    chat = client.get(f"/chats/{chat_id}", headers=headers).json()["data"]
    return [(message["role"], message["content"]) for message in chat["messages"]]


def test_stream_sends_tokens_then_done_and_saves(harness: Harness, cancel_spy: CancelSpy) -> None:
    client, headers, chat_id = _open(harness)
    with client:
        response = client.post(f"/chats/{chat_id}/messages/stream", json={"message": "rating?"}, headers=headers)
        events = sse_events(response.text)
        saved = _messages(client, headers, chat_id)

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert [name for name, _ in events] == ["token", "token", "token", "done"]
    assert "".join(data["text"] for name, data in events if name == "token") == ANSWER
    done = events[-1][1]
    assert (done["status"], done["data"]["answer"], done["data"]["scope"]) == (HTTPStatus.OK, ANSWER, "IN_SCOPE")
    assert done["data"]["required_contexts"] == ["CODEFORCES"]
    assert saved == [("user", "rating?"), ("assistant", ANSWER)]
    assert cancel_spy.completed_when_cancelled == [True]


def test_flagged_stream_sends_the_fallback(harness: Harness) -> None:
    harness.groq.decision = decision(QueryScope.UNSAFE, ())
    client, headers, chat_id = _open(harness)
    with client:
        events = sse_events(client.post(f"/chats/{chat_id}/messages/stream", json={"message": "x"}, headers=headers).text)

    fallback = harness.config.chat.fallback_messages[QueryScope.UNSAFE]
    assert events[0] == ("token", {"text": fallback})
    assert events[1][0] == "done" and events[1][1]["data"]["scope"] == "UNSAFE"


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [({"message": " "}, HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR"), ({}, HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR")],
)
def test_errors_before_the_stream_get_their_status(harness: Harness, body: dict, status: HTTPStatus, code: str) -> None:
    client, headers, chat_id = _open(harness)
    with client:
        response = client.post(f"/chats/{chat_id}/messages/stream", json=body, headers=headers)

    assert (response.status_code, response.json()["error"]) == (status, code)
    assert response.headers["content-type"] == "application/json"


def test_unknown_chat_stream_is_404(harness: Harness) -> None:
    client, headers, _ = _open(harness)
    with client:
        response = client.post("/chats/01a0f968-0e19-7511-abcd-35c8c266e97e/messages/stream", json={"message": "hi"}, headers=headers)

    assert (response.status_code, response.json()["error"]) == (HTTPStatus.NOT_FOUND, "CHAT_NOT_FOUND")


def test_groq_refusing_the_stream_is_a_real_status(harness: Harness) -> None:
    harness.groq.answer_status = HTTPStatus.TOO_MANY_REQUESTS
    client, headers, chat_id = _open(harness)
    with client:
        response = client.post(f"/chats/{chat_id}/messages/stream", json={"message": "hi"}, headers=headers)
        saved = _messages(client, headers, chat_id)

    assert (response.status_code, response.json()["error"]) == (HTTPStatus.SERVICE_UNAVAILABLE, "UPSTREAM_BUSY")
    assert saved == []


def test_failure_mid_stream_sends_an_error_event_and_saves_nothing(harness: Harness) -> None:
    harness.groq.stream_body = chunk("Partial") + chunk(" answer")
    client, headers, chat_id = _open(harness)
    with client:
        events = sse_events(client.post(f"/chats/{chat_id}/messages/stream", json={"message": "hi"}, headers=headers).text)
        saved = _messages(client, headers, chat_id)

    assert [name for name, _ in events] == ["token", "token", "error"]
    assert (events[-1][1]["status"], events[-1][1]["error"]) == (HTTPStatus.BAD_GATEWAY, "UPSTREAM_ERROR")
    assert saved == []


def _has_no_messages(base_url: str, headers: dict[str, str], chat_id: str, body: BlockingStreamBody) -> bool:
    response = httpx.get(f"{base_url}/chats/{chat_id}", headers=headers, timeout=10)
    return body.closed.is_set() and response.json()["data"]["messages"] == []


def test_client_disconnect_cancels_the_stream(harness: Harness, cancel_spy: CancelSpy) -> None:
    body = BlockingStreamBody()
    harness.groq.stream_body = body

    with LiveServer(harness.app()) as server:
        session_id = httpx.post(f"{server.base_url}/sessions", timeout=10).json()["data"]["session_id"]
        headers = {SESSION_HEADER: session_id}
        chat_id = httpx.post(f"{server.base_url}/chats", headers=headers, timeout=10).json()["data"]["chat_id"]

        with httpx.stream("POST", f"{server.base_url}/chats/{chat_id}/messages/stream", json={"message": "hi"}, headers=headers, timeout=10) as response:
            first = next(response.iter_lines())
            assert body.first_sent.wait(5)

        body.closed.set()
        assert first.startswith("event: token") or first.startswith(":")
        assert wait_until(partial(_cancelled, cancel_spy), timeout=5)
        assert _has_no_messages(server.base_url, headers, chat_id, body)

    assert cancel_spy.completed_when_cancelled == [False]


def _cancelled(spy: CancelSpy) -> bool:
    return bool(spy.completed_when_cancelled)
