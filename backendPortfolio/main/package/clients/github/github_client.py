from datetime import timedelta
from types import TracebackType
from typing import Any, NoReturn, Self
from urllib.parse import quote, urlsplit

import httpx
from pydantic import TypeAdapter, ValidationError

from main.package.clients.github.dto import GitHubCommit, GitHubRepository, GitHubUser
from main.package.clients.github.exceptions import (
    GitHubHTTPStatusError,
    GitHubRateLimitError,
    GitHubRequestError,
    GitHubResponseError,
    InvalidGitHubArgumentError,
    InvalidGitHubClientSettingError,
)

_USER_ADAPTER = TypeAdapter(GitHubUser)
_REPOSITORIES_ADAPTER = TypeAdapter(tuple[GitHubRepository, ...])
_COMMIT_ADAPTER = TypeAdapter(GitHubCommit)
_COMMITS_ADAPTER = TypeAdapter(tuple[GitHubCommit, ...])


class GitHubClient:
    _ACCEPT = "application/vnd.github+json"
    _API_VERSION_HEADER = "X-GitHub-Api-Version"
    _RATE_LIMIT_REMAINING_HEADER = "x-ratelimit-remaining"
    _RATE_LIMIT_RESET_HEADER = "x-ratelimit-reset"
    _RETRY_AFTER_HEADER = "retry-after"
    _RATE_LIMIT_STATUSES = frozenset({403, 429})
    _MAX_PER_PAGE = 100
    _ERROR_BODY_LIMIT = 500

    def __init__(
        self,
        *,
        base_url: str,
        api_version: str,
        per_page: int,
        connect_timeout: timedelta,
        read_timeout: timedelta,
        write_timeout: timedelta,
        pool_timeout: timedelta,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = self._require_http_url(base_url)
        self._per_page = self._require_per_page(per_page)
        timeout = httpx.Timeout(
            connect=self._require_positive_timeout("connect_timeout", connect_timeout),
            read=self._require_positive_timeout("read_timeout", read_timeout),
            write=self._require_positive_timeout("write_timeout", write_timeout),
            pool=self._require_positive_timeout("pool_timeout", pool_timeout),
        )
        self._http = httpx.Client(
            base_url=f"{self._base_url}/",
            timeout=timeout,
            headers={
                "Accept": self._ACCEPT,
                self._API_VERSION_HEADER: self._require_api_version(api_version),
            },
            transport=transport,
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    def get_user(self, username: str) -> GitHubUser:
        self._require_non_blank("username", username)

        return self._get(self._path("users", username), _USER_ADAPTER)

    def list_user_repositories(self, username: str, page: int = 1) -> tuple[GitHubRepository, ...]:
        self._require_non_blank("username", username)
        self._require_page(page)

        return self._get(
            self._path("users", username, "repos"),
            _REPOSITORIES_ADAPTER,
            params={
                "sort": "updated",
                "direction": "desc",
                "per_page": self._per_page,
                "page": page,
            },
        )

    def list_commits_by_author(self, owner: str, repo: str, author: str, page: int = 1) -> tuple[GitHubCommit, ...]:
        self._require_non_blank("owner", owner)
        self._require_non_blank("repo", repo)
        self._require_non_blank("author", author)
        self._require_page(page)

        return self._get(
            self._path("repos", owner, repo, "commits"),
            _COMMITS_ADAPTER,
            params={"author": author, "per_page": self._per_page, "page": page},
        )

    def get_commit(self, owner: str, repo: str, commit_sha: str) -> GitHubCommit:
        self._require_non_blank("owner", owner)
        self._require_non_blank("repo", repo)
        self._require_non_blank("commit_sha", commit_sha)

        return self._get(self._path("repos", owner, repo, "commits", commit_sha), _COMMIT_ADAPTER)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _get[T](self, path: str, adapter: TypeAdapter[T], *, params: dict[str, Any] | None = None) -> T:
        payload = self._get_json(path, params=params)
        try:
            return adapter.validate_python(payload)
        except ValidationError as error:
            raise GitHubResponseError("GitHub API response does not match the expected shape") from error

    def _get_json(self, path: str, *, params: dict[str, Any] | None) -> Any:
        try:
            response = self._http.get(path, params=params)
        except httpx.RequestError as error:
            raise GitHubRequestError(f"Failed to call GitHub API at {path}") from error

        if not response.is_success:
            self._raise_status_error(path, response)

        try:
            return response.json()
        except ValueError as error:
            raise GitHubResponseError("GitHub API returned invalid JSON") from error

    def _raise_status_error(self, path: str, response: httpx.Response) -> NoReturn:
        body = response.text[:self._ERROR_BODY_LIMIT]
        message = f"GitHub API call to {path} failed. HTTP {response.status_code}: {body}"

        if self._is_rate_limited(response):
            reset = response.headers.get(self._RATE_LIMIT_RESET_HEADER)
            raise GitHubRateLimitError(
                f"GitHub API rate limit exceeded (resets at epoch {reset}). {message}",
                status_code=response.status_code,
                body=body,
            )

        raise GitHubHTTPStatusError(message, status_code=response.status_code, body=body)

    def _is_rate_limited(self, response: httpx.Response) -> bool:
        if response.status_code not in self._RATE_LIMIT_STATUSES:
            return False

        return (
            response.headers.get(self._RATE_LIMIT_REMAINING_HEADER) == "0"
            or self._RETRY_AFTER_HEADER in response.headers
        )

    @staticmethod
    def _path(*segments: str) -> str:
        return "/".join(quote(segment, safe="") for segment in segments)

    @staticmethod
    def _require_http_url(base_url: str) -> str:
        if not isinstance(base_url, str) or not base_url.strip():
            raise InvalidGitHubClientSettingError("base_url must be a non-empty string")

        parts = urlsplit(base_url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.query or parts.fragment:
            raise InvalidGitHubClientSettingError(
                "base_url must be an http or https URL with a host and no query or fragment"
            )

        return base_url.rstrip("/")

    @staticmethod
    def _require_api_version(api_version: str) -> str:
        if not isinstance(api_version, str) or not api_version.strip():
            raise InvalidGitHubClientSettingError("api_version must be a non-empty string")

        return api_version

    @classmethod
    def _require_per_page(cls, per_page: int) -> int:
        if not isinstance(per_page, int) or isinstance(per_page, bool) or not 1 <= per_page <= cls._MAX_PER_PAGE:
            raise InvalidGitHubClientSettingError(f"per_page must be an int from 1 to {cls._MAX_PER_PAGE}")

        return per_page

    @staticmethod
    def _require_positive_timeout(name: str, timeout: timedelta) -> float:
        if not isinstance(timeout, timedelta) or timeout <= timedelta(0):
            raise InvalidGitHubClientSettingError(f"{name} must be a positive timedelta")

        return timeout.total_seconds()

    @staticmethod
    def _require_non_blank(name: str, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise InvalidGitHubArgumentError(f"{name} is required")

    @staticmethod
    def _require_page(page: int) -> None:
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise InvalidGitHubArgumentError("page must be an int of at least 1")
