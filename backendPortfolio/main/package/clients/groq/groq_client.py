import random
from collections.abc import Sequence
from datetime import timedelta
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from main.package.clients.groq.dto import GroqChatCompletion, GroqChatCompletionRequest
from main.package.clients.groq.exceptions import (
    GroqRequestError,
    GroqResponseError,
    InvalidGroqClientSettingError,
    InvalidGroqRequestError,
)
from main.package.clients.groq.groq_stream import GroqChatCompletionStream, build_status_error


class GroqClient:
    _CHAT_COMPLETIONS_PATH = "openai/v1/chat/completions"
    _ERROR_BODY_LIMIT = 500

    def __init__(
        self,
        *,
        base_url: str,
        api_keys: Sequence[str],
        connect_timeout: timedelta,
        read_timeout: timedelta,
        write_timeout: timedelta,
        pool_timeout: timedelta,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = self._require_http_url(base_url)
        self._api_keys = self._require_api_keys(api_keys)
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

    def create_chat_completion(self, request: GroqChatCompletionRequest) -> GroqChatCompletion:
        http_request = self._build_request(request, stream=False)

        try:
            response = self._http.send(http_request)
        except httpx.RequestError as error:
            raise GroqRequestError("Failed to call Groq API") from error

        if not response.is_success:
            raise build_status_error(response.status_code, response.text, self._ERROR_BODY_LIMIT)

        try:
            return GroqChatCompletion.model_validate_json(response.content)
        except ValidationError as error:
            raise GroqResponseError("Groq API returned a response that is not a valid chat completion") from error

    def stream_chat_completion(self, request: GroqChatCompletionRequest) -> GroqChatCompletionStream:
        self._require_request(request)
        if request.response_format is not None:
            raise InvalidGroqRequestError(
                "response_format cannot be streamed; Groq does not support structured outputs with streaming"
            )

        return GroqChatCompletionStream(
            self._http,
            self._build_request(request, stream=True),
            error_body_limit=self._ERROR_BODY_LIMIT,
        )

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

    def _build_request(self, request: GroqChatCompletionRequest, *, stream: bool) -> httpx.Request:
        self._require_request(request)
        body: dict[str, Any] = request.model_dump(mode="json", exclude_none=True, by_alias=True) | {"stream": stream}
        headers = {"Authorization": f"Bearer {random.choice(self._api_keys)}"}
        if stream:
            headers["Accept"] = "text/event-stream"

        return self._http.build_request("POST", self._CHAT_COMPLETIONS_PATH, json=body, headers=headers)

    @staticmethod
    def _require_request(request: GroqChatCompletionRequest) -> None:
        if not isinstance(request, GroqChatCompletionRequest):
            raise InvalidGroqRequestError("request must be a GroqChatCompletionRequest")

    @staticmethod
    def _require_http_url(base_url: str) -> str:
        if not isinstance(base_url, str) or not base_url.strip():
            raise InvalidGroqClientSettingError("base_url must be a non-empty string")

        parts = urlsplit(base_url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.query or parts.fragment:
            raise InvalidGroqClientSettingError(
                "base_url must be an http or https URL with a host and no query or fragment"
            )

        return base_url.rstrip("/")

    @staticmethod
    def _require_api_keys(api_keys: Sequence[str]) -> tuple[str, ...]:
        if isinstance(api_keys, str) or not isinstance(api_keys, Sequence) or not api_keys:
            raise InvalidGroqClientSettingError("api_keys must be a non-empty sequence of strings")

        if any(not isinstance(key, str) or not key.strip() for key in api_keys):
            raise InvalidGroqClientSettingError("every api key must be a non-empty string")

        return tuple(api_keys)

    @staticmethod
    def _require_positive_timeout(name: str, timeout: timedelta) -> float:
        if not isinstance(timeout, timedelta) or timeout <= timedelta(0):
            raise InvalidGroqClientSettingError(f"{name} must be a positive timedelta")

        return timeout.total_seconds()
