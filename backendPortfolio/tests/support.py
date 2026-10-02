import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Self

import httpx


@dataclass(frozen=True)
class ResponseSpec:
    status_code: int = 200
    json: Any = None
    text: str | None = None
    content: bytes | None = None
    headers: Mapping[str, str] = field(default_factory=dict)

    def build(self) -> httpx.Response:
        if self.content is not None:
            return httpx.Response(self.status_code, content=self.content, headers=dict(self.headers))

        if self.text is not None:
            return httpx.Response(self.status_code, text=self.text, headers=dict(self.headers))

        return httpx.Response(self.status_code, json=self.json, headers=dict(self.headers))


class RecordingTransport(httpx.MockTransport):
    def __init__(
        self,
        default: ResponseSpec | None = None,
        *,
        routes: Mapping[str, ResponseSpec] | None = None,
        error: type[httpx.TransportError] | None = None,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self._default = default
        self._routes = dict(routes or {})
        self._error = error
        super().__init__(self._handle)

    @property
    def last_request(self) -> httpx.Request:
        return self.requests[-1]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)

        if self._error is not None:
            raise self._error("simulated transport failure", request=request)

        raw_path = request.url.raw_path.split(b"?")[0].decode("ascii")
        spec = self._routes.get(raw_path, self._default)
        if spec is None:
            return httpx.Response(404, json={"message": "Not Found"})

        return spec.build()


class ConcurrentRunner:
    def __init__(self, target: Callable[[], Any], thread_count: int = 16) -> None:
        self._target = target
        self._thread_count = thread_count
        self._barrier = threading.Barrier(thread_count)
        self._lock = threading.Lock()
        self.results: list[Any] = []
        self.errors: list[BaseException] = []

    def run(self) -> Self:
        threads = [threading.Thread(target=self._work) for _ in range(self._thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        return self

    def _work(self) -> None:
        self._barrier.wait()
        try:
            result = self._target()
        except Exception as error:
            with self._lock:
                self.errors.append(error)
        else:
            with self._lock:
                self.results.append(result)


def wait_until(condition: Callable[[], bool], timeout: float = 2.0, interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)

    return condition()
