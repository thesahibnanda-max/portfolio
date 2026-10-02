import runpy
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path

import anyio.to_thread
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException
from starlette.requests import Request

import main.app
from main.config import AppConfig
from main.package.handler import (
    ApiResponse,
    ApplicationFactory,
    ClientIpResolver,
    ErrorCatalog,
    ErrorRule,
    ExceptionHandler,
    FastUvicornWorker,
    GunicornSettings,
    HandlerError,
    HealthResponse,
    InvalidHandlerSettingError,
    PydanticJSONResponse,
    RequestBodyTooLargeError,
    Responder,
    ServiceContainer,
    UpstreamTransports,
)
from main.package.handler.middleware import BodySizeLimitMiddleware, UnhandledErrorMiddleware
from main.package.ratelimiter import RateLimitExceededError, RateLimitScope
from main.package.repository import RepositoryError
from main.package.service.chat import ChatServiceError, EmptyChatMessageError
from tests.main.package.handler.fakes import Harness, with_section
from tests.support import RecordingTransport, ResponseSpec

FIXED_TIME = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def _fixed_clock() -> datetime:
    return FIXED_TIME


def _request(headers: dict[str, str] | None = None, client: tuple[str, int] | None = ("127.0.0.1", 5000)) -> Request:
    raw = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw, "client": client})


def test_pydantic_response_renders_with_the_rust_serializer() -> None:
    model = HealthResponse(status="UP")

    response = PydanticJSONResponse(model)

    assert response.body == model.model_dump_json().encode()
    assert response.headers["content-type"] == "application/json"


def test_responder_envelopes_use_its_clock() -> None:
    responder = Responder(clock=_fixed_clock)

    envelope = responder.envelope(HealthResponse(status="UP"), status=HTTPStatus.CREATED)
    error = responder.error(HTTPStatus.CONFLICT, "CHAT_FULL", "full", headers={"X-Test": "1"})

    assert isinstance(envelope, ApiResponse)
    assert (envelope.status, envelope.timestamp) == (HTTPStatus.CREATED, FIXED_TIME)
    assert (error.status_code, error.headers["x-test"]) == (HTTPStatus.CONFLICT, "1")
    assert responder.no_content().status_code == HTTPStatus.NO_CONTENT


def test_catalog_matches_along_the_mro_and_falls_back() -> None:
    catalog = ErrorCatalog.default()

    assert catalog.rule_for(EmptyChatMessageError("x")).status is HTTPStatus.BAD_REQUEST
    assert catalog.rule_for(ChatServiceError("x")).status is HTTPStatus.INTERNAL_SERVER_ERROR
    assert catalog.rule_for(KeyError("x")).code == "INTERNAL_ERROR"
    assert RepositoryError not in catalog.exception_types


def test_catalog_rejects_bad_rules() -> None:
    rule = ErrorRule(ValueError, HTTPStatus.BAD_REQUEST, "BAD")

    with pytest.raises(InvalidHandlerSettingError):
        ErrorCatalog((rule, rule), fallback=rule)
    with pytest.raises(InvalidHandlerSettingError):
        ErrorCatalog(("not a rule",), fallback=rule)
    assert issubclass(InvalidHandlerSettingError, HandlerError)


def test_handler_describes_http_errors_and_rate_limits() -> None:
    handler = ExceptionHandler(catalog=ErrorCatalog.default(), responder=Responder(clock=_fixed_clock))

    teapot = handler.describe(HTTPException(status_code=HTTPStatus.IM_A_TEAPOT, detail={"x": 1}))
    limited = handler.respond(RateLimitExceededError("slow down", api="chat", scope=RateLimitScope.IP, retry_after=timedelta(seconds=7)))
    too_large = handler.respond(RequestBodyTooLargeError(max_body_bytes=10))

    assert (teapot.error, teapot.message) == ("IM_A_TEAPOT", HTTPStatus.IM_A_TEAPOT.phrase)
    assert (limited.status_code, limited.headers["retry-after"]) == (HTTPStatus.TOO_MANY_REQUESTS, "7")
    assert too_large.status_code == HTTPStatus.CONTENT_TOO_LARGE


@pytest.mark.parametrize(
    ("trust", "headers", "client", "expected"),
    [
        (True, {"X-Forwarded-For": "203.0.113.9, 10.0.0.1"}, ("127.0.0.1", 1), "203.0.113.9"),
        (True, {"X-Forwarded-For": " , 10.0.0.1"}, ("127.0.0.1", 1), "127.0.0.1"),
        (True, {}, ("127.0.0.1", 1), "127.0.0.1"),
        (False, {"X-Forwarded-For": "203.0.113.9"}, ("127.0.0.1", 1), "127.0.0.1"),
        (False, {}, None, None),
    ],
)
def test_client_ip_resolver(trust: bool, headers: dict[str, str], client, expected: str | None) -> None:
    assert ClientIpResolver(trust_forwarded_for=trust).resolve(_request(headers, client)) == expected


@pytest.mark.parametrize("value", [0, -1, True, "10", None])
def test_body_limit_rejects_bad_settings(value: object) -> None:
    handler = ExceptionHandler(catalog=ErrorCatalog.default(), responder=Responder())

    with pytest.raises(InvalidHandlerSettingError):
        BodySizeLimitMiddleware(FastAPI(), max_body_bytes=value, exception_handler=handler)


class RecordingApp:
    def __init__(self, *, fail_after_start: bool = False) -> None:
        self.fail_after_start = fail_after_start
        self.calls = 0

    async def __call__(self, scope, receive, send) -> None:
        self.calls += 1
        if self.fail_after_start:
            await send({"type": "http.response.start", "status": HTTPStatus.OK, "headers": []})
            raise RuntimeError("after start")


class Collector:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)


async def _receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


@pytest.mark.anyio
async def test_middlewares_pass_non_http_scopes_through() -> None:
    handler = ExceptionHandler(catalog=ErrorCatalog.default(), responder=Responder())
    inner = RecordingApp()

    await BodySizeLimitMiddleware(inner, max_body_bytes=5, exception_handler=handler)({"type": "websocket"}, _receive, Collector())
    await UnhandledErrorMiddleware(inner, exception_handler=handler)({"type": "websocket"}, _receive, Collector())

    assert inner.calls == 2


@pytest.mark.anyio
async def test_unparseable_content_length_is_treated_as_unknown() -> None:
    handler = ExceptionHandler(catalog=ErrorCatalog.default(), responder=Responder())
    inner = RecordingApp()
    scope = {"type": "http", "headers": [(b"content-length", b"abc")]}

    await BodySizeLimitMiddleware(inner, max_body_bytes=5, exception_handler=handler)(scope, _receive, Collector())

    assert inner.calls == 1


@pytest.mark.anyio
async def test_errors_after_the_response_started_are_reraised() -> None:
    handler = ExceptionHandler(catalog=ErrorCatalog.default(), responder=Responder())
    middleware = UnhandledErrorMiddleware(RecordingApp(fail_after_start=True), exception_handler=handler)
    collector = Collector()

    with pytest.raises(RuntimeError, match="after start"):
        await middleware({"type": "http", "headers": []}, _receive, collector)

    assert collector.messages[0]["status"] == HTTPStatus.OK


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_lifespan_sets_the_threadpool_and_closes_the_container(config_env: str, tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.config = with_section(harness.config, "app", thread_pool_size=13)

    with harness.client() as client:
        assert client.portal.call(_thread_tokens) == 13
        assert not harness.closed.is_set()

    assert harness.closed.is_set()


async def _thread_tokens() -> float:
    return anyio.to_thread.current_default_thread_limiter().total_tokens


def test_container_closes_what_it_built_when_building_fails(config_env: str, tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    config = with_section(AppConfig.load(), "repository", database_path=str(blocker / "db.sqlite3"))
    groq = ClosingTransport()

    with pytest.raises(Exception):
        ServiceContainer.from_config(config, UpstreamTransports(groq=groq))

    assert groq.closed


class ClosingTransport(RecordingTransport):
    def __init__(self) -> None:
        super().__init__(ResponseSpec())
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_gunicorn_settings_come_from_config(config_env: str) -> None:
    config = AppConfig.load()

    settings = GunicornSettings.from_config(config)

    assert settings == GunicornSettings(
        wsgi_app="main.app:create_app()",
        bind="0.0.0.0:8080",
        workers=1,
        worker_class="main.package.handler.worker.FastUvicornWorker",
        timeout=180,
        graceful_timeout=30,
        keepalive=5,
    )


def test_gunicorn_conf_file_exposes_the_settings(config_env: str) -> None:
    values = runpy.run_path(str(Path(main.app.__file__).parent.parent / "gunicorn.conf.py"))

    assert (values["wsgi_app"], values["workers"], values["worker_class"]) == (
        "main.app:create_app()",
        1,
        "main.package.handler.worker.FastUvicornWorker",
    )


def test_worker_pins_the_fast_loop_and_parser() -> None:
    assert FastUvicornWorker.CONFIG_KWARGS == {
        "loop": "uvloop",
        "http": "httptools",
        "lifespan": "on",
        "proxy_headers": False,
        "server_header": False,
    }


def test_create_app_builds_the_application(config_env: str) -> None:
    app = main.app.create_app()

    assert isinstance(app, FastAPI)
    assert app.title == "Backend Portfolio"


def test_application_factory_accepts_custom_parts(config_env: str, tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    factory = ApplicationFactory(
        config=harness.config,
        container_factory=harness.build_container,
        responder=Responder(clock=_fixed_clock),
        catalog=ErrorCatalog((), fallback=ErrorRule(Exception, HTTPStatus.SERVICE_UNAVAILABLE, "DOWN", "down")),
    )

    with TestClient(factory.create()) as client:
        body = client.get("/health").json()

    assert body["timestamp"].startswith("2026-10-02T12:00:00")
