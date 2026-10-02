import json
import socket
import threading
from collections.abc import Iterator
from types import TracebackType
from typing import Self

import httpx
from httpx_sse import EventSource, ServerSentEvent
from pydantic import ValidationError

from main.package.clients.groq.dto import (
    GroqChatCompletion,
    GroqStreamEnd,
    GroqStreamEvent,
    GroqTextDelta,
    GroqUsage,
)
from main.package.clients.groq.exceptions import (
    GroqHTTPStatusError,
    GroqJsonValidationError,
    GroqRateLimitError,
    GroqRequestError,
    GroqResponseError,
    GroqStreamCancelledError,
    GroqStreamIncompleteError,
    GroqStreamStateError,
)

_DONE_SENTINEL = "[DONE]"
_RATE_LIMIT_STATUS = 429
_BAD_REQUEST_STATUS = 400
_JSON_VALIDATE_FAILED = "json_validate_failed"


def _error_code(full_body: str) -> str | None:
    try:
        payload = json.loads(full_body)
    except ValueError:
        return None

    error = payload.get("error") if isinstance(payload, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) else None


def build_status_error(status_code: int, full_body: str, limit: int) -> GroqHTTPStatusError:
    body = full_body[:limit]
    message = f"Groq API request failed. HTTP {status_code}: {body}"
    if status_code == _RATE_LIMIT_STATUS:
        return GroqRateLimitError(f"Groq API rate limit exceeded. {message}", status_code=status_code, body=body)

    if status_code == _BAD_REQUEST_STATUS and _error_code(full_body) == _JSON_VALIDATE_FAILED:
        return GroqJsonValidationError(
            f"Groq could not produce JSON matching the requested schema. {message}",
            status_code=status_code,
            body=body,
        )

    return GroqHTTPStatusError(message, status_code=status_code, body=body)


class GroqChatCompletionStream:
    def __init__(self, http: httpx.Client, request: httpx.Request, *, error_body_limit: int) -> None:
        self._http = http
        self._request = request
        self._error_body_limit = error_body_limit
        self._cancelled = threading.Event()
        self._response: httpx.Response | None = None
        self._events: Iterator[ServerSentEvent] | None = None
        self._entered = False
        self._finished = False
        self._completed = False
        self._text_parts: list[str] = []
        self._finish_reason: str | None = None
        self._usage: GroqUsage | None = None

    @property
    def text(self) -> str:
        return "".join(self._text_parts)

    @property
    def finish_reason(self) -> str | None:
        return self._finish_reason

    @property
    def usage(self) -> GroqUsage | None:
        return self._usage

    @property
    def completed(self) -> bool:
        return self._completed

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def __enter__(self) -> Self:
        if self._entered:
            raise GroqStreamStateError("A Groq stream can only be entered once")
        self._entered = True

        if self.cancelled:
            raise GroqStreamCancelledError("Groq stream was cancelled before it started", partial_text="")

        try:
            response = self._http.send(self._request, stream=True)
        except httpx.RequestError as error:
            raise GroqRequestError("Failed to call Groq API") from error

        self._response = response
        if not response.is_success:
            self._raise_for_status(response)

        if self.cancelled:
            self.close()
            raise GroqStreamCancelledError("Groq stream was cancelled before it started", partial_text="")

        self._events = EventSource(response).iter_sse()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __iter__(self) -> Self:
        if self._events is None:
            raise GroqStreamStateError("Iterate a Groq stream inside its with block")

        if self._finished:
            raise GroqStreamStateError("This Groq stream has already been read to the end")

        return self

    def __next__(self) -> GroqStreamEvent:
        if self._events is None:
            raise GroqStreamStateError("Iterate a Groq stream inside its with block")

        if self._finished:
            raise StopIteration

        while True:
            event = self._next_server_sent_event()
            if not event.data:
                continue

            if event.data == _DONE_SENTINEL:
                self._finished = True
                self._completed = True
                return GroqStreamEnd(text=self.text, finish_reason=self._finish_reason, usage=self._usage)

            delta = self._consume_chunk(event.data)
            if delta is not None:
                return delta

    def cancel(self) -> None:
        if self._completed:
            return

        self._cancelled.set()
        self._interrupt_read()

    def close(self) -> None:
        if self._response is not None:
            self._response.close()

    def _interrupt_read(self) -> None:
        response = self._response
        if response is None:
            return

        network_stream = response.extensions.get("network_stream")
        raw_socket = network_stream.get_extra_info("socket") if network_stream is not None else None
        if raw_socket is None:
            return

        try:
            raw_socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            return

    def _next_server_sent_event(self) -> ServerSentEvent:
        self._raise_if_cancelled(None)

        try:
            event = next(self._events)
        except StopIteration:
            self._finished = True
            self._raise_if_cancelled(None)
            raise GroqStreamIncompleteError(
                "Groq stream ended before completion (no [DONE] marker)",
                partial_text=self.text,
            ) from None
        except (httpx.TransportError, httpx.StreamError) as error:
            self._finished = True
            self._raise_if_cancelled(error)
            raise GroqRequestError("Groq stream failed while reading") from error
        except Exception as error:
            self._finished = True
            self._raise_if_cancelled(error)
            raise

        self._raise_if_cancelled(None)
        return event

    def _consume_chunk(self, data: str) -> GroqTextDelta | None:
        try:
            payload = json.loads(data)
        except ValueError as error:
            self._finished = True
            raise GroqResponseError("Groq stream sent a chunk that is not valid JSON") from error

        if isinstance(payload, dict) and "error" in payload:
            self._finished = True
            raise GroqResponseError(f"Groq stream reported an error: {payload['error']}")

        try:
            chunk = GroqChatCompletion.model_validate(payload)
        except ValidationError as error:
            self._finished = True
            raise GroqResponseError("Groq stream chunk does not match the expected shape") from error

        if chunk.x_groq is not None and chunk.x_groq.usage is not None:
            self._usage = chunk.x_groq.usage
        elif chunk.usage is not None:
            self._usage = chunk.usage

        if not chunk.choices:
            return None

        choice = chunk.choices[0]
        if choice.finish_reason is not None:
            self._finish_reason = choice.finish_reason

        content = choice.delta.content if choice.delta is not None else None
        if not content:
            return None

        self._text_parts.append(content)
        return GroqTextDelta(text=content)

    def _raise_if_cancelled(self, cause: BaseException | None) -> None:
        if not self.cancelled:
            return

        self._finished = True
        raise GroqStreamCancelledError("Groq stream was cancelled", partial_text=self.text) from cause

    def _raise_for_status(self, response: httpx.Response) -> None:
        try:
            response.read()
            full_body = response.text
        except (httpx.TransportError, httpx.StreamError):
            full_body = ""
        finally:
            response.close()

        raise build_status_error(response.status_code, full_body, self._error_body_limit)
