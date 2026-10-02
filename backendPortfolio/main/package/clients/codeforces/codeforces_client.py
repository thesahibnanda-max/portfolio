from datetime import timedelta
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from main.package.clients.codeforces.dto import CodeforcesUserRatingResponse
from main.package.clients.codeforces.exceptions import (
    CodeforcesHTTPStatusError,
    CodeforcesRequestError,
    CodeforcesResponseError,
    InvalidCodeforcesArgumentError,
    InvalidCodeforcesClientSettingError,
)


class CodeforcesClient:
    _USER_RATING_PATH = "api/user.rating"
    _STATUS_OK = "OK"
    _ERROR_BODY_LIMIT = 500

    def __init__(
        self,
        *,
        base_url: str,
        connect_timeout: timedelta,
        read_timeout: timedelta,
        write_timeout: timedelta,
        pool_timeout: timedelta,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = self._require_http_url(base_url)
        timeout = httpx.Timeout(
            connect=self._require_positive_timeout("connect_timeout", connect_timeout),
            read=self._require_positive_timeout("read_timeout", read_timeout),
            write=self._require_positive_timeout("write_timeout", write_timeout),
            pool=self._require_positive_timeout("pool_timeout", pool_timeout),
        )
        self._http = httpx.Client(base_url=f"{self._base_url}/", timeout=timeout, transport=transport)

    @property
    def base_url(self) -> str:
        return self._base_url

    def get_user_rating(self, handle: str) -> CodeforcesUserRatingResponse:
        self._require_non_blank("handle", handle)

        payload = self._get_json(self._USER_RATING_PATH, params={"handle": handle})
        try:
            rating_response = CodeforcesUserRatingResponse.model_validate(payload)
        except ValidationError as error:
            raise CodeforcesResponseError("Codeforces API response does not match the expected shape") from error

        if rating_response.status != self._STATUS_OK:
            raise CodeforcesResponseError(
                rating_response.comment or f"Codeforces API returned a non-OK status: {rating_response.status}"
            )

        return rating_response

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

    def _get_json(self, path: str, *, params: dict[str, str]) -> Any:
        try:
            response = self._http.get(path, params=params)
        except httpx.RequestError as error:
            raise CodeforcesRequestError("Failed to call Codeforces API") from error

        if not response.is_success:
            body = response.text[:self._ERROR_BODY_LIMIT]
            detail = self._extract_comment(response) or body
            raise CodeforcesHTTPStatusError(
                f"Codeforces API request failed. HTTP {response.status_code}: {detail}",
                status_code=response.status_code,
                body=body,
            )

        try:
            return response.json()
        except ValueError as error:
            raise CodeforcesResponseError("Codeforces API returned invalid JSON") from error

    @staticmethod
    def _extract_comment(response: httpx.Response) -> str | None:
        try:
            data = response.json()
        except ValueError:
            return None

        comment = data.get("comment") if isinstance(data, dict) else None
        return comment if isinstance(comment, str) and comment else None

    @staticmethod
    def _require_http_url(base_url: str) -> str:
        if not isinstance(base_url, str) or not base_url.strip():
            raise InvalidCodeforcesClientSettingError("base_url must be a non-empty string")

        parts = urlsplit(base_url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.query or parts.fragment:
            raise InvalidCodeforcesClientSettingError(
                "base_url must be an http or https URL with a host and no query or fragment"
            )

        return base_url.rstrip("/")

    @staticmethod
    def _require_positive_timeout(name: str, timeout: timedelta) -> float:
        if not isinstance(timeout, timedelta) or timeout <= timedelta(0):
            raise InvalidCodeforcesClientSettingError(f"{name} must be a positive timedelta")

        return timeout.total_seconds()

    @staticmethod
    def _require_non_blank(name: str, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise InvalidCodeforcesArgumentError(f"{name} is required")
