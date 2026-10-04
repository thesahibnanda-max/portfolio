from collections import deque
from collections.abc import Mapping
from types import MappingProxyType, TracebackType
from typing import Self

from main.package.ai.agent.exceptions import AgentStreamStateError, InvalidAgentSettingError
from main.package.ai.orchestrator import QueryScope
from main.package.clients.groq import GroqChatCompletionStream, GroqStreamEnd, GroqStreamEvent, GroqTextDelta, GroqUsage


class MarkedAnswerStream:
    def __init__(
        self,
        stream: GroqChatCompletionStream,
        *,
        markers: Mapping[QueryScope, str],
        fallback_messages: Mapping[QueryScope, str],
    ) -> None:
        if not isinstance(stream, GroqChatCompletionStream):
            raise InvalidAgentSettingError("stream must be a GroqChatCompletionStream")

        if not isinstance(markers, Mapping) or not isinstance(fallback_messages, Mapping):
            raise InvalidAgentSettingError("markers and fallback_messages must be mappings")

        missing = set(markers) - set(fallback_messages)
        if missing:
            raise InvalidAgentSettingError(f"fallback_messages has no message for {sorted(missing)}")

        self._stream = stream
        self._markers = MappingProxyType(dict(markers))
        self._fallback_messages = fallback_messages
        self._pending: deque[GroqStreamEvent] = deque()
        self._buffer = ""
        self._decided = False
        self._ended = False
        self._scope = QueryScope.IN_SCOPE
        self._usage: GroqUsage | None = None

    @property
    def scope(self) -> QueryScope:
        return self._scope

    @property
    def usage(self) -> GroqUsage | None:
        return self._usage

    def __enter__(self) -> Self:
        self._stream.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> GroqStreamEvent:
        if self._pending:
            return self._pending.popleft()

        if self._ended:
            raise StopIteration

        while True:
            event = next(self._stream)
            if isinstance(event, GroqStreamEnd):
                return self._end(event)

            if not isinstance(event, GroqTextDelta):
                raise AgentStreamStateError(f"Unexpected stream event {type(event).__name__}")

            if self._decided:
                return event

            self._buffer += event.text
            scope = self._classify(self._buffer.lstrip())
            if scope is QueryScope.IN_SCOPE:
                return self._release()

            if scope is not None:
                return self._divert(scope)

    def cancel(self) -> None:
        self._stream.cancel()

    def close(self) -> None:
        self._stream.close()

    def _end(self, event: GroqStreamEnd) -> GroqStreamEvent:
        self._ended = True
        self._usage = event.usage
        if self._decided or not self._buffer:
            self._decided = True
            return event

        self._decided = True
        self._pending.append(event)
        return GroqTextDelta(text=self._buffer)

    def _release(self) -> GroqTextDelta:
        self._decided = True
        return GroqTextDelta(text=self._buffer)

    def _divert(self, scope: QueryScope) -> GroqTextDelta:
        self._decided = True
        self._scope = scope
        self._ended = True
        self._stream.cancel()

        answer = self._fallback_messages[scope]
        self._pending.append(GroqStreamEnd(text=answer))
        return GroqTextDelta(text=answer)

    def _classify(self, text: str) -> QueryScope | None:
        for scope, marker in self._markers.items():
            if text.startswith(marker):
                return scope

        if any(marker.startswith(text) for marker in self._markers.values()):
            return None

        return QueryScope.IN_SCOPE
