import threading
import time
from collections.abc import Iterator
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from main.package.clients.groq import (
    GroqChatCompletionRequest,
    GroqChatCompletionStream,
    GroqClient,
    GroqHTTPStatusError,
    GroqMessage,
    GroqRateLimitError,
    GroqRequestError,
    GroqResponseError,
    GroqStreamCancelledError,
    GroqStreamEnd,
    GroqStreamIncompleteError,
    GroqStreamStateError,
    GroqTextDelta,
)
from tests.conftest import HTTP_TIMEOUTS
from tests.main.package.clients.groq.sse import DONE, FULL_DELTAS, FULL_STREAM, FULL_TEXT, SSE_HEADERS, chunk
from tests.support import RecordingTransport, ResponseSpec

REQUEST = GroqChatCompletionRequest(model="llama-3.3-70b-versatile", messages=[GroqMessage(role="user", content="Rating?")])


class SplitBody:
    def __init__(self, data: bytes, size: int) -> None:
        self._data = data
        self._size = size

    def __call__(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=self._pieces(), headers=SSE_HEADERS)

    def _pieces(self) -> Iterator[bytes]:
        for start in range(0, len(self._data), self._size):
            yield self._data[start:start + self._size]


class FailingBody:
    def __init__(self, error: Exception, status_code: int = 200) -> None:
        self._error = error
        self._status_code = status_code

    def __call__(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self._status_code, content=self._pieces(), headers=SSE_HEADERS)

    def _pieces(self) -> Iterator[bytes]:
        yield chunk("partial").encode()
        raise self._error


class BlockingBody:
    def __init__(self, after_release: bytes | Exception) -> None:
        self.first_sent = threading.Event()
        self.release = threading.Event()
        self._after_release = after_release

    def __call__(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=self._pieces(), headers=SSE_HEADERS)

    def _pieces(self) -> Iterator[bytes]:
        yield chunk("Partial").encode()
        self.first_sent.set()
        self.release.wait(5)
        if isinstance(self._after_release, Exception):
            raise self._after_release
        yield self._after_release


class CancelDuringSend:
    def __init__(self) -> None:
        self.stream: GroqChatCompletionStream | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.stream.cancel()
        return httpx.Response(200, content=FULL_STREAM.encode(), headers=SSE_HEADERS)


class StreamReader:
    def __init__(self, stream: GroqChatCompletionStream) -> None:
        self._stream = stream
        self.events: list = []
        self.error: BaseException | None = None
        self.first_event = threading.Event()
        self.thread = threading.Thread(target=self._read)

    def start(self) -> "StreamReader":
        self.thread.start()
        return self

    def _read(self) -> None:
        try:
            with self._stream as stream:
                for event in stream:
                    self.events.append(event)
                    self.first_event.set()
        except BaseException as error:
            self.error = error


class SlowSSEHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.rfile.read(int(self.headers["content-length"]))
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        self.wfile.write(chunk("Partial").encode())
        self.wfile.flush()
        time.sleep(2)

    def log_message(self, format: str, *args: object) -> None:
        return None


def _client(transport: httpx.BaseTransport | None = None, **overrides: object) -> GroqClient:
    settings = {"base_url": "https://groq.test", "api_keys": ["key"]} | HTTP_TIMEOUTS | overrides
    return GroqClient(**settings, transport=transport)


def _sse(body: str, status: int = 200, headers: dict[str, str] | None = None) -> RecordingTransport:
    return RecordingTransport(ResponseSpec(status, content=body.encode(), headers=headers or SSE_HEADERS))


def _read_all(stream: GroqChatCompletionStream) -> list:
    with stream:
        return list(stream)


@pytest.fixture
def slow_server() -> Iterator[ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowSSEHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _socket_client(server: ThreadingHTTPServer, read_timeout: timedelta) -> GroqClient:
    return GroqClient(
        base_url=f"http://127.0.0.1:{server.server_port}",
        api_keys=["key"],
        connect_timeout=timedelta(seconds=2),
        read_timeout=read_timeout,
        write_timeout=timedelta(seconds=2),
        pool_timeout=timedelta(seconds=2),
    )


def test_yields_text_deltas_in_order_then_one_end_event() -> None:
    with _client(_sse(FULL_STREAM)) as client:
        events = _read_all(client.stream_chat_completion(REQUEST))

    assert all(isinstance(event, GroqTextDelta) for event in events[:-1])
    assert [event.text for event in events[:-1]] == FULL_DELTAS
    end = events[-1]
    assert isinstance(end, GroqStreamEnd)
    assert end.text == FULL_TEXT
    assert end.finish_reason == "stop"
    assert end.usage.total_tokens == 42


def test_whitespace_only_piece_is_kept() -> None:
    with _client(_sse(FULL_STREAM)) as client:
        events = _read_all(client.stream_chat_completion(REQUEST))

    assert GroqTextDelta(text=" ") in events
    assert "is 1832" in events[-1].text


def test_stream_properties_match_end_event() -> None:
    with _client(_sse(FULL_STREAM)) as client, client.stream_chat_completion(REQUEST) as stream:
        assert stream.completed is False
        events = list(stream)

    assert stream.text == events[-1].text == FULL_TEXT
    assert stream.finish_reason == events[-1].finish_reason
    assert stream.usage == events[-1].usage
    assert stream.completed is True
    assert stream.cancelled is False


def test_events_support_pattern_matching() -> None:
    with _client(_sse(FULL_STREAM)) as client:
        events = _read_all(client.stream_chat_completion(REQUEST))

    match events[-1]:
        case GroqStreamEnd(text=text, finish_reason="stop"):
            assert text == FULL_TEXT
        case _:
            pytest.fail("last event was not GroqStreamEnd")


def test_top_level_usage_is_used_when_x_groq_has_none() -> None:
    body = chunk("Hi") + chunk(finish_reason="stop", usage={"total_tokens": 7}) + DONE
    with _client(_sse(body)) as client, client.stream_chat_completion(REQUEST) as stream:
        list(stream)

    assert stream.usage.total_tokens == 7


def test_choice_without_delta_and_empty_data_events_are_skipped() -> None:
    body = chunk(with_delta=False) + "data:\n\n" + "event: ping\n\n" + chunk("Hi") + DONE
    with _client(_sse(body)) as client:
        events = _read_all(client.stream_chat_completion(REQUEST))

    assert events == [GroqTextDelta(text="Hi"), GroqStreamEnd(text="Hi")]


def test_crlf_line_endings_are_parsed() -> None:
    with _client(_sse(FULL_STREAM.replace("\n", "\r\n"))) as client:
        assert _read_all(client.stream_chat_completion(REQUEST))[-1].text == FULL_TEXT


@pytest.mark.parametrize("size", [1, 7, 64])
def test_events_split_across_network_chunks_are_parsed(size: int) -> None:
    with _client(httpx.MockTransport(SplitBody(FULL_STREAM.encode(), size))) as client:
        assert _read_all(client.stream_chat_completion(REQUEST))[-1].text == FULL_TEXT


def test_missing_done_marker_raises_incomplete_with_partial_text() -> None:
    with _client(_sse(FULL_STREAM.replace(DONE, ""))) as client, pytest.raises(GroqStreamIncompleteError) as error:
        _read_all(client.stream_chat_completion(REQUEST))

    assert error.value.partial_text == FULL_TEXT


def test_error_event_mid_stream_raises() -> None:
    body = chunk("Hel") + 'data: {"error": {"message": "model overloaded"}}\n\n'
    with _client(_sse(body)) as client, pytest.raises(GroqResponseError, match="model overloaded"):
        _read_all(client.stream_chat_completion(REQUEST))


@pytest.mark.parametrize("data", ["{not json", '{"choices": 5}', '{"choices": [{"delta": {"content": 5}}]}'])
def test_bad_chunk_raises(data: str) -> None:
    with _client(_sse(f"data: {data}\n\n")) as client, pytest.raises(GroqResponseError):
        _read_all(client.stream_chat_completion(REQUEST))


@pytest.mark.parametrize(("status", "error_type"), [(400, GroqHTTPStatusError), (429, GroqRateLimitError), (503, GroqHTTPStatusError)])
def test_error_status_raises_on_enter_before_any_event(status: int, error_type: type[Exception]) -> None:
    transport = RecordingTransport(ResponseSpec(status, text="busy " * 200))
    with _client(transport) as client:
        stream = client.stream_chat_completion(REQUEST)
        with pytest.raises(error_type) as error:
            stream.__enter__()

    assert type(error.value) is error_type
    assert error.value.status_code == status
    assert len(error.value.body) == 500


def test_error_status_with_unreadable_body_has_empty_body() -> None:
    with _client(httpx.MockTransport(FailingBody(httpx.ReadError("reset"), status_code=500))) as client:
        with pytest.raises(GroqHTTPStatusError) as error:
            client.stream_chat_completion(REQUEST).__enter__()

    assert error.value.body == ""


def test_connection_failure_raises_on_enter() -> None:
    with _client(RecordingTransport(error=httpx.ConnectError)) as client, pytest.raises(GroqRequestError) as error:
        client.stream_chat_completion(REQUEST).__enter__()

    assert isinstance(error.value.__cause__, httpx.ConnectError)


def test_non_event_stream_content_type_raises() -> None:
    with _client(_sse('{"x": 1}', headers={"content-type": "application/json"})) as client, pytest.raises(GroqRequestError):
        _read_all(client.stream_chat_completion(REQUEST))


def test_transport_error_mid_stream_raises_request_error() -> None:
    with _client(httpx.MockTransport(FailingBody(httpx.ReadError("reset")))) as client, pytest.raises(GroqRequestError) as error:
        _read_all(client.stream_chat_completion(REQUEST))

    assert isinstance(error.value.__cause__, httpx.ReadError)


def test_unexpected_error_mid_stream_propagates() -> None:
    with _client(httpx.MockTransport(FailingBody(RuntimeError("bug")))) as client, pytest.raises(RuntimeError, match="bug"):
        _read_all(client.stream_chat_completion(REQUEST))


def test_breaking_early_closes_the_connection() -> None:
    with _client(_sse(FULL_STREAM)) as client:
        with client.stream_chat_completion(REQUEST) as stream:
            for _ in stream:
                break
            response = stream._response

    assert response.is_closed


def test_close_is_safe_to_call_twice() -> None:
    with _client(_sse(FULL_STREAM)) as client:
        stream = client.stream_chat_completion(REQUEST)
        stream.close()
        with stream:
            list(stream)
        stream.close()
        stream.close()


def test_iterating_outside_with_block_raises() -> None:
    with _client(_sse(FULL_STREAM)) as client:
        stream = client.stream_chat_completion(REQUEST)

        with pytest.raises(GroqStreamStateError):
            iter(stream)
        with pytest.raises(GroqStreamStateError):
            next(stream)


def test_entering_twice_raises() -> None:
    with _client(_sse(FULL_STREAM)) as client:
        stream = client.stream_chat_completion(REQUEST)
        with stream:
            with pytest.raises(GroqStreamStateError):
                stream.__enter__()


def test_reading_again_after_the_end() -> None:
    with _client(_sse(FULL_STREAM)) as client, client.stream_chat_completion(REQUEST) as stream:
        list(stream)

        with pytest.raises(StopIteration):
            next(stream)
        with pytest.raises(GroqStreamStateError):
            iter(stream)


def test_cancel_from_another_thread_wakes_blocked_reader() -> None:
    body = BlockingBody((chunk(" more") + DONE).encode())
    with _client(httpx.MockTransport(body)) as client:
        stream = client.stream_chat_completion(REQUEST)
        reader = StreamReader(stream).start()
        assert body.first_sent.wait(5)
        assert reader.first_event.wait(5)

        stream.cancel()
        body.release.set()
        reader.thread.join(5)

    assert isinstance(reader.error, GroqStreamCancelledError)
    assert reader.error.partial_text == "Partial"
    assert stream.cancelled is True
    assert stream.completed is False


def test_cancel_turns_a_blocked_read_error_into_cancelled() -> None:
    body = BlockingBody(RuntimeError("socket closed under the reader"))
    with _client(httpx.MockTransport(body)) as client:
        stream = client.stream_chat_completion(REQUEST)
        reader = StreamReader(stream).start()
        assert reader.first_event.wait(5)

        stream.cancel()
        body.release.set()
        reader.thread.join(5)

    assert isinstance(reader.error, GroqStreamCancelledError)
    assert isinstance(reader.error.__cause__, RuntimeError)


def test_cancel_turns_a_closed_stream_into_cancelled() -> None:
    body = BlockingBody(httpx.ReadError("closed"))
    with _client(httpx.MockTransport(body)) as client:
        stream = client.stream_chat_completion(REQUEST)
        reader = StreamReader(stream).start()
        assert reader.first_event.wait(5)

        stream.cancel()
        body.release.set()
        reader.thread.join(5)

    assert isinstance(reader.error, GroqStreamCancelledError)
    assert isinstance(reader.error.__cause__, httpx.ReadError)


def test_cancel_when_upstream_then_ends_is_cancelled_not_incomplete() -> None:
    body = BlockingBody(b"")
    with _client(httpx.MockTransport(body)) as client:
        stream = client.stream_chat_completion(REQUEST)
        reader = StreamReader(stream).start()
        assert reader.first_event.wait(5)

        stream.cancel()
        body.release.set()
        reader.thread.join(5)

    assert isinstance(reader.error, GroqStreamCancelledError)


def test_cancel_between_events_raises_on_next_step() -> None:
    with _client(_sse(FULL_STREAM)) as client, client.stream_chat_completion(REQUEST) as stream:
        assert next(stream) == GroqTextDelta(text="My rating")
        stream.cancel()

        with pytest.raises(GroqStreamCancelledError) as error:
            next(stream)

    assert error.value.partial_text == "My rating"


def test_cancel_after_the_end_does_nothing() -> None:
    with _client(_sse(FULL_STREAM)) as client:
        stream = client.stream_chat_completion(REQUEST)
        _read_all(stream)
        stream.cancel()

    assert stream.cancelled is False
    assert stream.completed is True


def test_cancel_before_enter_raises_on_enter() -> None:
    transport = _sse(FULL_STREAM)
    with _client(transport) as client:
        stream = client.stream_chat_completion(REQUEST)
        stream.cancel()

        with pytest.raises(GroqStreamCancelledError):
            stream.__enter__()

    assert transport.requests == []


def test_cancel_while_request_is_being_sent_raises_on_enter() -> None:
    transport = CancelDuringSend()
    with _client(httpx.MockTransport(transport)) as client:
        transport.stream = client.stream_chat_completion(REQUEST)

        with pytest.raises(GroqStreamCancelledError):
            transport.stream.__enter__()

        assert transport.stream._response.is_closed


def test_cancel_on_a_real_socket_wakes_the_reader_immediately(slow_server: ThreadingHTTPServer) -> None:
    with _socket_client(slow_server, timedelta(seconds=30)) as client:
        stream = client.stream_chat_completion(REQUEST)
        reader = StreamReader(stream).start()
        assert reader.first_event.wait(5)

        started = time.monotonic()
        stream.cancel()
        stream.cancel()
        reader.thread.join(5)
        elapsed = time.monotonic() - started

    assert not reader.thread.is_alive()
    assert isinstance(reader.error, GroqStreamCancelledError)
    assert reader.error.partial_text == "Partial"
    assert elapsed < 1


def test_read_timeout_stops_a_stalled_real_stream(slow_server: ThreadingHTTPServer) -> None:
    with _socket_client(slow_server, timedelta(milliseconds=300)) as client:
        with pytest.raises(GroqRequestError) as error:
            _read_all(client.stream_chat_completion(REQUEST))

    assert isinstance(error.value.__cause__, httpx.ReadTimeout)


def test_one_client_serves_parallel_streams() -> None:
    with _client(_sse(FULL_STREAM)) as client:
        readers = [StreamReader(client.stream_chat_completion(REQUEST)).start() for _ in range(16)]
        for reader in readers:
            reader.thread.join(5)

    assert all(reader.error is None for reader in readers)
    assert all(reader.events[-1] == GroqStreamEnd(text=FULL_TEXT, finish_reason="stop", usage=readers[0].events[-1].usage) for reader in readers)
