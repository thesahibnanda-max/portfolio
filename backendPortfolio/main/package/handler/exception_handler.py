import logging
import math
from collections.abc import Mapping
from http import HTTPStatus

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from main.package.handler.dto import ErrorDetail, ErrorResponse
from main.package.handler.error_catalog import ErrorCatalog
from main.package.handler.responder import Responder
from main.package.ratelimiter import RateLimitExceededError
from main.package.service.contact import InvalidContactSubmissionError

_LOGGER = logging.getLogger(__name__)
_VALIDATION_CODE = "VALIDATION_ERROR"
_VALIDATION_MESSAGE = "The request is invalid"


class ExceptionHandler:
    def __init__(self, *, catalog: ErrorCatalog, responder: Responder) -> None:
        self._catalog = catalog
        self._responder = responder

    @property
    def handled_types(self) -> tuple[type[BaseException], ...]:
        return (RequestValidationError, HTTPException, *self._catalog.exception_types)

    async def __call__(self, request: Request, error: Exception) -> Response:
        return self.respond(error)

    def respond(self, error: BaseException) -> Response:
        body = self.describe(error)
        return self._responder.error(
            HTTPStatus(body.status),
            body.error,
            body.message,
            details=body.details,
            headers=self._headers(error),
        )

    def describe(self, error: BaseException) -> ErrorResponse:
        if isinstance(error, RequestValidationError):
            return self._responder.error_body(
                HTTPStatus.BAD_REQUEST,
                _VALIDATION_CODE,
                _VALIDATION_MESSAGE,
                [self._detail(item) for item in error.errors()],
            )

        if isinstance(error, HTTPException):
            status = HTTPStatus(error.status_code)
            message = error.detail if isinstance(error.detail, str) and error.detail else status.phrase
            return self._responder.error_body(status, status.name, message)

        rule = self._catalog.rule_for(error)
        if rule.status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            _LOGGER.error("Request failed with %s", type(error).__name__, exc_info=error)

        return self._responder.error_body(
            rule.status,
            rule.code,
            rule.public_message or str(error),
            self._details(error),
        )

    @staticmethod
    def _details(error: BaseException) -> tuple[ErrorDetail, ...]:
        if isinstance(error, InvalidContactSubmissionError):
            return (ErrorDetail(field=f"body.{error.field}", message=str(error)),)
        return ()

    @staticmethod
    def _detail(item: Mapping[str, object]) -> ErrorDetail:
        location = ".".join(str(part) for part in item.get("loc", ()))
        return ErrorDetail(field=location, message=str(item.get("msg", "")))

    @staticmethod
    def _headers(error: BaseException) -> Mapping[str, str] | None:
        if isinstance(error, RateLimitExceededError):
            return {"Retry-After": str(math.ceil(error.retry_after.total_seconds()))}

        if isinstance(error, HTTPException) and error.headers:
            return error.headers

        return None
