from http import HTTPStatus

from fastapi import APIRouter

from main.package.handler.dto import ApiResponse, HealthResponse
from main.package.handler.json_response import PydanticJSONResponse
from main.package.handler.request_context import State

HEALTHY = "UP"

router = APIRouter(tags=["health"])


@router.get("/health", status_code=HTTPStatus.OK, response_model=ApiResponse[HealthResponse])
async def health(state: State) -> PydanticJSONResponse:
    return state.responder.ok(HealthResponse(status=HEALTHY))
