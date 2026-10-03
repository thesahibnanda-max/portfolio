from collections.abc import Iterator
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent

from main.package.handler.chat_routes import reply_events
from main.package.handler.dto import StreamStepResponse
from main.package.handler.request_context import AgentStreamOpener, RateLimitGuard, State
from main.package.service.agent import AgentTurnStream

STEP_EVENT = "step"

router = APIRouter(prefix="/chats", tags=["agent"])


@router.post(
    "/{chat_id}/agent/stream",
    status_code=HTTPStatus.OK,
    response_class=EventSourceResponse,
    dependencies=[Depends(RateLimitGuard("agent_message"))],
)
def stream_agent_message(
    turn: Annotated[AgentTurnStream, Depends(AgentStreamOpener())],
    state: State,
) -> Iterator[ServerSentEvent]:
    for step in turn.steps:
        yield ServerSentEvent(event=STEP_EVENT, data=StreamStepResponse(label=step))
    yield from reply_events(turn.replies, state)
