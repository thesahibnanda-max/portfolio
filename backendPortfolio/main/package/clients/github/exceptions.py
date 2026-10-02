class GitHubClientError(Exception):
    pass


class InvalidGitHubClientSettingError(GitHubClientError):
    pass


class InvalidGitHubArgumentError(GitHubClientError):
    pass


class GitHubRequestError(GitHubClientError):
    pass


class GitHubHTTPStatusError(GitHubClientError):
    def __init__(self, message: str, *, status_code: int, body: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class GitHubRateLimitError(GitHubHTTPStatusError):
    pass


class GitHubResponseError(GitHubClientError):
    pass
