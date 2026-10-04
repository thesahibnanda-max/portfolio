from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self

from main.package.clients.groq import (
    GroqStreamCancelledError,
    GroqStreamEnd,
    GroqStreamEvent,
    GroqTextDelta,
)
from main.package.service.chat.dto import ChatDoneEvent, ChatReply, ChatStreamEvent, ChatTokenEvent
from main.package.service.chat.exceptions import ChatStreamCancelledError, ChatStreamStateError


class AnswerStream(Protocol):
    def __enter__(self) -> Self:
        ...

    def __next__(self) -> GroqStreamEvent:
        ...

    def cancel(self) -> None:
        ...

    def close(self) -> None:
        ...


class ChatReplyStream:
    def __init__(
        self,
        *,
        complete: Callable[[str], ChatReply],
        answer_stream: AnswerStream | None = None,
        fallback_answer: str | None = None,
    ) -> None:
        if (answer_stream is None) == (fallback_answer is None):
            raise ChatStreamStateError("A chat stream needs exactly one of answer_stream or fallback_answer")

        self._complete = complete
        self._answer_stream = answer_stream
        self._fallback_answer = fallback_answer
        self._entered = False
        self._finished = False
        self._cancelled = False
        self._fallback_sent = False
        self._reply: ChatReply | None = None

    @property
    def reply(self) -> ChatReply | None:
        return self._reply

    @property
    def completed(self) -> bool:
        return self._reply is not None

    def __enter__(self) -> Self:
        if self._entered:
            raise ChatStreamStateError("A chat stream can only be entered once")
        self._entered = True

        if self._answer_stream is not None:
            self._answer_stream.__enter__()

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __iter__(self) -> Self:
        if not self._entered:
            raise ChatStreamStateError("Iterate a chat stream inside its with block")

        if self._finished:
            raise ChatStreamStateError("This chat stream has already been read to the end")

        return self

    def __next__(self) -> ChatStreamEvent:
        if not self._entered:
            raise ChatStreamStateError("Iterate a chat stream inside its with block")

        if self._finished:
            raise StopIteration

        if self._cancelled:
            self._finished = True
            raise ChatStreamCancelledError("Chat stream was cancelled")

        if self._answer_stream is None:
            return self._next_fallback_event()

        return self._next_answer_event()

    def cancel(self) -> None:
        if self.completed:
            return

        self._cancelled = True
        if self._answer_stream is not None:
            self._answer_stream.cancel()

    def close(self) -> None:
        if self._answer_stream is not None and self._entered:
            self._answer_stream.close()

    def _next_fallback_event(self) -> ChatStreamEvent:
        if not self._fallback_sent:
            self._fallback_sent = True
            return ChatTokenEvent(text=self._fallback_answer)

        return self._finish(self._fallback_answer)

    def _next_answer_event(self) -> ChatStreamEvent:
        try:
            event = next(self._answer_stream)
        except GroqStreamCancelledError as error:
            self._finished = True
            raise ChatStreamCancelledError("Chat stream was cancelled") from error
        except BaseException:
            self._finished = True
            raise

        if isinstance(event, GroqTextDelta):
            return ChatTokenEvent(text=event.text)

        if isinstance(event, GroqStreamEnd):
            return self._finish(event.text)

        self._finished = True
        raise ChatStreamStateError(f"Unexpected stream event {type(event).__name__}")

    def _finish(self, answer: str) -> ChatDoneEvent:
        self._finished = True
        self._reply = self._complete(answer)
        return ChatDoneEvent(reply=self._reply)
