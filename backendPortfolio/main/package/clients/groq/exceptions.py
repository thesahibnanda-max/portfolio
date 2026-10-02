class GroqClientError(Exception):
    pass


class InvalidGroqClientSettingError(GroqClientError):
    pass


class InvalidGroqRequestError(GroqClientError):
    pass


class GroqRequestError(GroqClientError):
    pass


class GroqHTTPStatusError(GroqClientError):
    def __init__(self, message: str, *, status_code: int, body: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class GroqRateLimitError(GroqHTTPStatusError):
    pass


class GroqJsonValidationError(GroqHTTPStatusError):
    pass


class GroqResponseError(GroqClientError):
    pass


class GroqStreamIncompleteError(GroqResponseError):
    def __init__(self, message: str, *, partial_text: str) -> None:
        super().__init__(message)
        self.partial_text = partial_text


class GroqStreamCancelledError(GroqClientError):
    def __init__(self, message: str, *, partial_text: str) -> None:
        super().__init__(message)
        self.partial_text = partial_text


class GroqStreamStateError(GroqClientError):
    pass
