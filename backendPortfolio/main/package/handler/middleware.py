from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from main.package.handler.exception_handler import ExceptionHandler
from main.package.handler.exceptions import InvalidHandlerSettingError, RequestBodyTooLargeError


class LimitedReceive:
    def __init__(self, receive: Receive, *, max_body_bytes: int) -> None:
        self._receive = receive
        self._max_body_bytes = max_body_bytes
        self._received = 0

    async def __call__(self) -> Message:
        message = await self._receive()
        if message["type"] == "http.request":
            self._received += len(message.get("body", b""))
            if self._received > self._max_body_bytes:
                raise RequestBodyTooLargeError(max_body_bytes=self._max_body_bytes)

        return message


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int, exception_handler: ExceptionHandler) -> None:
        if isinstance(max_body_bytes, bool) or not isinstance(max_body_bytes, int) or max_body_bytes < 1:
            raise InvalidHandlerSettingError("max_body_bytes must be a positive int")

        self._app = app
        self._max_body_bytes = max_body_bytes
        self._exception_handler = exception_handler

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        if self._declared_length(scope) > self._max_body_bytes:
            response = self._exception_handler.respond(RequestBodyTooLargeError(max_body_bytes=self._max_body_bytes))
            await response(scope, receive, send)
            return

        await self._app(scope, LimitedReceive(receive, max_body_bytes=self._max_body_bytes), send)

    @staticmethod
    def _declared_length(scope: Scope) -> int:
        value = Headers(scope=scope).get("content-length", "")
        return int(value) if value.isdigit() else 0


class UnhandledErrorMiddleware:
    def __init__(self, app: ASGIApp, *, exception_handler: ExceptionHandler) -> None:
        self._app = app
        self._exception_handler = exception_handler

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        tracker = ResponseStartTracker(send)
        try:
            await self._app(scope, receive, tracker)
        except Exception as error:
            if tracker.started:
                raise
            response = self._exception_handler.respond(error)
            await response(scope, receive, send)


class ResponseStartTracker:
    def __init__(self, send: Send) -> None:
        self._send = send
        self.started = False

    async def __call__(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.started = True
        await self._send(message)
