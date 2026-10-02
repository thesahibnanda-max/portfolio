class CodeforcesClientError(Exception):
    pass


class InvalidCodeforcesClientSettingError(CodeforcesClientError):
    pass


class InvalidCodeforcesArgumentError(CodeforcesClientError):
    pass


class CodeforcesRequestError(CodeforcesClientError):
    pass


class CodeforcesHTTPStatusError(CodeforcesClientError):
    def __init__(self, message: str, *, status_code: int, body: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class CodeforcesResponseError(CodeforcesClientError):
    pass
