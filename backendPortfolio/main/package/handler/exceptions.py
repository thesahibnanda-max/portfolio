from http import HTTPStatus

from starlette.exceptions import HTTPException


class HandlerError(Exception):
    pass


class InvalidHandlerSettingError(HandlerError):
    pass


class RequestBodyTooLargeError(HTTPException):
    def __init__(self, *, max_body_bytes: int) -> None:
        super().__init__(
            status_code=HTTPStatus.CONTENT_TOO_LARGE,
            detail=f"Request body must not be larger than {max_body_bytes} bytes",
        )
        self.max_body_bytes = max_body_bytes
