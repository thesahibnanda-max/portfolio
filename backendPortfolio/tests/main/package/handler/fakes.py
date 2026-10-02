import json
import socket
import threading
from collections.abc import Iterator
from dataclasses import replace
from http import HTTPStatus
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from main.config import AppConfig
from main.package.handler import ApplicationFactory, ServiceContainer, UpstreamTransports
from main.package.ratelimiter import RateLimitScope
from tests.main.package.ai.fakes import completion
from tests.main.package.clients.groq.sse import DONE, SSE_HEADERS, chunk
from tests.main.package.mail.fakes import FakeConnector
from tests.main.package.service.contact.fakes import FakeResolver
from tests.main.package.service.context.fakes import Upstream
from tests.support import wait_until

SESSION_HEADER = "X-Session-Id"
ANSWER = "He has a 1832 rating."
STREAM_BODY = chunk("He has ") + chunk("a 1832") + chunk(" rating.") + chunk(finish_reason="stop") + DONE


def decision(scope: str = "IN_SCOPE", contexts: tuple[str, ...] = ("CODEFORCES",)) -> str:
    return json.dumps({"scope": scope, "requiredContexts": list(contexts), "reason": "test"})


class GroqFake(httpx.MockTransport):
    def __init__(self) -> None:
        self.decision = decision()
        self.answer = ANSWER
        self.stream_body: Any = STREAM_BODY
        self.decision_status = HTTPStatus.OK
        self.answer_status = HTTPStatus.OK
        self.requests: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        with self._lock:
            self.requests.append(body)

        if "response_format" in body:
            return httpx.Response(self.decision_status, json=completion(self.decision))

        if body.get("stream"):
            return httpx.Response(self.answer_status, content=self.stream_body, headers=SSE_HEADERS)

        return httpx.Response(self.answer_status, json=completion(self.answer))


class BlockingStreamBody:
    def __init__(self) -> None:
        self.first_sent = threading.Event()
        self.closed = threading.Event()

    def __iter__(self) -> Iterator[bytes]:
        yield chunk("Partial").encode()
        self.first_sent.set()
        self.closed.wait(10)
        yield (chunk(" rest") + DONE).encode()


def rate_limited(config: AppConfig, api: str, limit: int, scope: RateLimitScope) -> AppConfig:
    rules = dict(config.rate_limit.rules)
    scoped = dict(rules[api])
    scoped[scope] = scoped[scope].model_copy(update={"limit": limit})
    rules[api] = scoped
    return config.model_copy(update={"rate_limit": config.rate_limit.model_copy(update={"rules": rules})})


def with_section(config: AppConfig, section: str, **values: Any) -> AppConfig:
    return config.model_copy(update={section: getattr(config, section).model_copy(update=values)})


class Harness:
    def __init__(self, tmp_path: Path, config: AppConfig | None = None) -> None:
        base = config or AppConfig.load()
        self.config = with_section(base, "repository", database_path=str(tmp_path / "api.sqlite3"))
        self.groq = GroqFake()
        self.upstream = Upstream()
        self.smtp = FakeConnector()
        self.dns = FakeResolver()
        self.containers: list[ServiceContainer] = []
        self.closed = threading.Event()

    def build_container(self, config: AppConfig) -> ServiceContainer:
        transports = UpstreamTransports(
            leetcode=self.upstream.leetcode,
            codeforces=self.upstream.codeforces,
            github=self.upstream.github,
            groq=self.groq,
            smtp=self.smtp,
            dns_resolver=self.dns,
        )
        container = ServiceContainer.from_config(config, transports)
        container = replace(container, closers=(*container.closers, self.closed.set))
        self.containers.append(container)
        return container

    def app(self) -> FastAPI:
        return ApplicationFactory(config=self.config, container_factory=self.build_container).create()

    def client(self) -> TestClient:
        return TestClient(self.app(), raise_server_exceptions=False)


def new_session(client: TestClient) -> str:
    return client.post("/sessions").json()["data"]["session_id"]


def new_chat(client: TestClient, session_id: str, title: str = "Ratings") -> str:
    response = client.post("/chats", json={"title": title}, headers={SESSION_HEADER: session_id})
    return response.json()["data"]["chat_id"]


def sse_events(text: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in text.split("\n\n"):
        lines = [line for line in block.splitlines() if not line.startswith(":")]
        fields = dict(line.split(": ", 1) for line in lines if ": " in line)
        if "event" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


class LiveServer:
    def __init__(self, app: FastAPI) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("127.0.0.1", 0))
        self.base_url = f"http://127.0.0.1:{self._socket.getsockname()[1]}"
        config = uvicorn.Config(app, loop="uvloop", http="httptools", lifespan="on", log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, kwargs={"sockets": [self._socket]}, daemon=True)

    def __enter__(self) -> "LiveServer":
        self._thread.start()
        if not wait_until(self._is_started, timeout=10):
            raise RuntimeError("uvicorn did not start")
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._server.should_exit = True
        self._thread.join(10)
        self._socket.close()

    def _is_started(self) -> bool:
        return self._server.started
