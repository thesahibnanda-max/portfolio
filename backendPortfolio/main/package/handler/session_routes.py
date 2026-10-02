from http import HTTPStatus

from fastapi import APIRouter, Depends

from main.package.handler.dto import ApiResponse, SessionResponse
from main.package.handler.json_response import PydanticJSONResponse
from main.package.handler.request_context import RateLimitGuard, State

router = APIRouter(tags=["sessions"])


@router.post(
    "/sessions",
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[SessionResponse],
    dependencies=[Depends(RateLimitGuard("create_session"))],
)
def create_session(state: State) -> PydanticJSONResponse:
    session = state.container.repository.create_session()
    return state.responder.ok(SessionResponse.model_validate(session), status=HTTPStatus.CREATED)
