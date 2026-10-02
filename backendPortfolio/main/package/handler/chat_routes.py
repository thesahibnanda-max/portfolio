from collections.abc import Iterator
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent
from starlette.responses import Response

from main.package.handler.dto import (
    ApiResponse,
    ChatListResponse,
    ChatReplyResponse,
    ChatResponse,
    ChatSummaryResponse,
    CreateChatRequest,
    RenameChatRequest,
    SendMessageRequest,
    StreamTokenResponse,
)
from main.package.handler.json_response import PydanticJSONResponse
from main.package.handler.request_context import ChatStreamOpener, RateLimitGuard, SessionId, State
from main.package.service.chat import ChatReplyStream, ChatTokenEvent

TOKEN_EVENT = "token"
DONE_EVENT = "done"
ERROR_EVENT = "error"

router = APIRouter(prefix="/chats", tags=["chats"])
_read_limit = Depends(RateLimitGuard("chat_read"))
_write_limit = Depends(RateLimitGuard("chat_write"))
_message_limit = Depends(RateLimitGuard("chat_message"))


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[ChatSummaryResponse],
    dependencies=[_write_limit],
)
def create_chat(session_id: SessionId, state: State, body: CreateChatRequest | None = None) -> PydanticJSONResponse:
    repository = state.container.repository
    if body is None or body.title is None:
        chat = repository.create_chat(session_id)
    else:
        chat = repository.create_chat(session_id, body.title)

    return state.responder.ok(ChatSummaryResponse.model_validate(chat), status=HTTPStatus.CREATED)


@router.get("", status_code=HTTPStatus.OK, response_model=ApiResponse[ChatListResponse], dependencies=[_read_limit])
def list_chats(session_id: SessionId, state: State) -> PydanticJSONResponse:
    chats = state.container.repository.list_chats(session_id)
    return state.responder.ok(ChatListResponse(chats=tuple(ChatSummaryResponse.model_validate(chat) for chat in chats)))


@router.get("/{chat_id}", status_code=HTTPStatus.OK, response_model=ApiResponse[ChatResponse], dependencies=[_read_limit])
def get_chat(chat_id: str, session_id: SessionId, state: State) -> PydanticJSONResponse:
    chat = state.container.repository.get_chat(session_id, chat_id)
    return state.responder.ok(ChatResponse.model_validate(chat))


@router.patch(
    "/{chat_id}",
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[ChatSummaryResponse],
    dependencies=[_write_limit],
)
def rename_chat(chat_id: str, body: RenameChatRequest, session_id: SessionId, state: State) -> PydanticJSONResponse:
    chat = state.container.repository.rename_chat(session_id, chat_id, body.title)
    return state.responder.ok(ChatSummaryResponse.model_validate(chat))


@router.delete("/{chat_id}", status_code=HTTPStatus.NO_CONTENT, response_class=Response, dependencies=[_write_limit])
def delete_chat(chat_id: str, session_id: SessionId, state: State) -> Response:
    state.container.repository.delete_chat(session_id, chat_id)
    return state.responder.no_content()


@router.post(
    "/{chat_id}/messages",
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[ChatReplyResponse],
    dependencies=[_message_limit],
)
def send_message(chat_id: str, body: SendMessageRequest, session_id: SessionId, state: State) -> PydanticJSONResponse:
    reply = state.container.chat_service.send_message(session_id, chat_id, body.message)
    return state.responder.ok(ChatReplyResponse.model_validate(reply))


@router.post(
    "/{chat_id}/messages/stream",
    status_code=HTTPStatus.OK,
    response_class=EventSourceResponse,
    dependencies=[_message_limit],
)
def stream_message(
    stream: Annotated[ChatReplyStream, Depends(ChatStreamOpener())],
    state: State,
) -> Iterator[ServerSentEvent]:
    try:
        for event in stream:
            if isinstance(event, ChatTokenEvent):
                yield ServerSentEvent(event=TOKEN_EVENT, data=StreamTokenResponse(text=event.text))
            else:
                reply = ChatReplyResponse.model_validate(event.reply)
                yield ServerSentEvent(event=DONE_EVENT, data=state.responder.envelope(reply))
    except Exception as error:
        yield ServerSentEvent(event=ERROR_EVENT, data=state.exception_handler.describe(error))
