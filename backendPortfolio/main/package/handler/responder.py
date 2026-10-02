from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from http import HTTPStatus

from pydantic import BaseModel
from starlette.responses import Response

from main.package.handler.dto import ApiResponse, ErrorDetail, ErrorResponse
from main.package.handler.json_response import PydanticJSONResponse


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Responder:
    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock

    def envelope[T: BaseModel](self, data: T, *, status: HTTPStatus = HTTPStatus.OK) -> ApiResponse[T]:
        return ApiResponse[type(data)](status=status, timestamp=self._clock(), data=data)

    def ok(self, data: BaseModel, *, status: HTTPStatus = HTTPStatus.OK) -> PydanticJSONResponse:
        return PydanticJSONResponse(self.envelope(data, status=status), status_code=status)

    def no_content(self) -> Response:
        return Response(status_code=HTTPStatus.NO_CONTENT)

    def error_body(
        self,
        status: HTTPStatus,
        code: str,
        message: str,
        details: Sequence[ErrorDetail] = (),
    ) -> ErrorResponse:
        return ErrorResponse(
            status=status,
            timestamp=self._clock(),
            error=code,
            message=message,
            details=tuple(details),
        )

    def error(
        self,
        status: HTTPStatus,
        code: str,
        message: str,
        *,
        details: Sequence[ErrorDetail] = (),
        headers: Mapping[str, str] | None = None,
    ) -> PydanticJSONResponse:
        return PydanticJSONResponse(
            self.error_body(status, code, message, details),
            status_code=status,
            headers=dict(headers) if headers else None,
        )
