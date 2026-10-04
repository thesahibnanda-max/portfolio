import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header
from starlette.requests import Request

from main.package.handler.container import ServiceContainer
from main.package.handler.dto import SendMessageRequest
from main.package.handler.exception_handler import ExceptionHandler
from main.package.handler.responder import Responder
from main.package.service.agent import AgentTurnStream
from main.package.service.chat import ChatReplyStream

SESSION_HEADER = "X-Session-Id"
FORWARDED_FOR_HEADER = "X-Forwarded-For"


class ClientIpResolver:
    def __init__(self, *, trust_forwarded_for: bool) -> None:
        self._trust_forwarded_for = trust_forwarded_for

    def resolve(self, request: Request) -> str | None:
        if self._trust_forwarded_for:
            first = request.headers.get(FORWARDED_FOR_HEADER, "").split(",")[0].strip()
            if first:
                return first

        return request.client.host if request.client is not None else None


@dataclass(frozen=True)
class HandlerState:
    container: ServiceContainer
    responder: Responder
    exception_handler: ExceptionHandler
    client_ip_resolver: ClientIpResolver


def handler_state(request: Request) -> HandlerState:
    return request.app.state.handler


State = Annotated[HandlerState, Depends(handler_state)]
SessionId = Annotated[str, Header(alias=SESSION_HEADER, min_length=1)]


class RateLimitGuard:
    def __init__(self, api: str) -> None:
        self._api = api

    async def __call__(self, request: Request) -> None:
        self.check(request)

    def check(self, request: Request) -> None:
        state = handler_state(request)
        state.container.rate_limiter.check(
            self._api,
            client_ip=state.client_ip_resolver.resolve(request),
            session_id=self._session_id(request),
        )

    @staticmethod
    def _session_id(request: Request) -> str | None:
        value = request.headers.get(SESSION_HEADER)
        if value is None:
            return None

        try:
            return str(uuid.UUID(value))
        except ValueError:
            return None


class ChatStreamOpener:
    def __call__(self, chat_id: str, body: SendMessageRequest, session_id: SessionId, state: State) -> Iterator[ChatReplyStream]:
        stream = state.container.chat_service.stream_message(session_id, chat_id, body.message)
        with stream:
            try:
                yield stream
            finally:
                stream.cancel()


class AgentStreamOpener:
    def __init__(self, rate_limit_api: str) -> None:
        self._rate_limit = RateLimitGuard(rate_limit_api)

    def __call__(
        self,
        request: Request,
        chat_id: str,
        body: SendMessageRequest,
        session_id: SessionId,
        state: State,
    ) -> Iterator[AgentTurnStream]:
        service = state.container.agent_service
        service.validate(body.message)
        self._rate_limit.check(request)
        turn = service.stream_message(session_id, chat_id, body.message)
        with turn.replies:
            try:
                yield turn
            finally:
                turn.replies.cancel()
