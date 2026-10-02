class LeetcodeClientError(Exception):
    pass


class InvalidLeetcodeClientSettingError(LeetcodeClientError):
    pass


class InvalidLeetcodeArgumentError(LeetcodeClientError):
    pass


class LeetcodeRequestError(LeetcodeClientError):
    pass


class LeetcodeHTTPStatusError(LeetcodeClientError):
    def __init__(self, message: str, *, status_code: int, body: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class LeetcodeResponseError(LeetcodeClientError):
    pass
