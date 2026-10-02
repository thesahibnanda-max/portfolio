from functools import partial
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest

from main.config import AppConfig
from main.package.ratelimiter import RateLimitScope
from tests.main.package.handler.fakes import (
    SESSION_HEADER,
    Harness,
    LiveServer,
    new_chat,
    new_session,
    rate_limited,
    with_section,
)
from tests.support import ConcurrentRunner


def _harness(tmp_path: Path, config: AppConfig | None = None) -> Harness:
    return Harness(tmp_path, config)


def _ip(address: str) -> dict[str, str]:
    return {"X-Forwarded-For": f"{address}, 10.0.0.1"}


def test_chat_messages_are_limited_per_ip_with_retry_after(config_env: str, tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    with harness.client() as client:
        headers = {SESSION_HEADER: new_session(client)}
        chat_id = new_chat(client, headers[SESSION_HEADER])
        statuses = [client.post(f"/chats/{chat_id}/messages", json={"message": "hi"}, headers=headers).status_code for _ in range(5)]
        groq_calls = len(harness.groq.requests)

        refused = client.post(
            f"/chats/{chat_id}/messages",
            json={"message": "hi"},
            headers={**headers, "Origin": "https://sahibnanda.net"},
        )

    assert statuses == [HTTPStatus.OK] * 5
    assert refused.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert refused.json()["error"] == "RATE_LIMITED"
    assert 1 <= int(refused.headers["retry-after"]) <= 60
    assert refused.headers["access-control-expose-headers"] == "Retry-After"
    assert len(harness.groq.requests) == groq_calls


def test_refused_requests_are_not_validated(config_env: str, tmp_path: Path) -> None:
    harness = _harness(tmp_path, rate_limited(AppConfig.load(), "chat_write", 1, RateLimitScope.IP))
    with harness.client() as client:
        headers = {SESSION_HEADER: new_session(client)}
        client.post("/chats", headers=headers)

        response = client.post("/chats", json={"title": 5}, headers=headers)

    assert response.status_code == HTTPStatus.TOO_MANY_REQUESTS


def test_forwarded_ips_get_their_own_budget(config_env: str, tmp_path: Path) -> None:
    harness = _harness(tmp_path, rate_limited(AppConfig.load(), "create_session", 1, RateLimitScope.IP))
    with harness.client() as client:
        first = client.post("/sessions", headers=_ip("203.0.113.1"))
        second = client.post("/sessions", headers=_ip("203.0.113.2"))
        repeat = client.post("/sessions", headers=_ip("203.0.113.1"))

    assert (first.status_code, second.status_code, repeat.status_code) == (HTTPStatus.CREATED, HTTPStatus.CREATED, HTTPStatus.TOO_MANY_REQUESTS)


def test_forwarded_for_is_ignored_when_not_trusted(config_env: str, tmp_path: Path) -> None:
    config = with_section(rate_limited(AppConfig.load(), "create_session", 1, RateLimitScope.IP), "app", trust_forwarded_for=False)
    harness = _harness(tmp_path, config)
    with harness.client() as client:
        client.post("/sessions", headers=_ip("203.0.113.1"))

        response = client.post("/sessions", headers=_ip("203.0.113.2"))

    assert response.status_code == HTTPStatus.TOO_MANY_REQUESTS


def test_sessions_are_limited_across_ips(config_env: str, tmp_path: Path) -> None:
    harness = _harness(tmp_path, rate_limited(AppConfig.load(), "chat_read", 2, RateLimitScope.SESSION))
    with harness.client() as client:
        session_id = new_session(client)
        statuses = [
            client.get("/chats", headers={SESSION_HEADER: session_id, **_ip(f"198.51.100.{index}")}).status_code
            for index in range(3)
        ]

    assert statuses == [HTTPStatus.OK, HTTPStatus.OK, HTTPStatus.TOO_MANY_REQUESTS]


def test_malformed_session_headers_do_not_create_session_counters(config_env: str, tmp_path: Path) -> None:
    harness = _harness(tmp_path, rate_limited(AppConfig.load(), "chat_read", 1, RateLimitScope.SESSION))
    with harness.client() as client:
        statuses = [client.get("/chats", headers={SESSION_HEADER: "garbage"}).status_code for _ in range(3)]

    assert statuses == [HTTPStatus.BAD_REQUEST] * 3


def test_global_budget_is_shared_by_everyone(config_env: str, tmp_path: Path) -> None:
    harness = _harness(tmp_path, rate_limited(AppConfig.load(), "details", 2, RateLimitScope.GLOBAL))
    with harness.client() as client:
        statuses = [client.get("/details/profile", headers=_ip(f"192.0.2.{index}")).status_code for index in range(3)]

    assert statuses == [HTTPStatus.OK, HTTPStatus.OK, HTTPStatus.TOO_MANY_REQUESTS]


def test_health_is_never_limited(config_env: str, tmp_path: Path) -> None:
    with _harness(tmp_path).client() as client:
        assert {client.get("/health").status_code for _ in range(50)} == {HTTPStatus.OK}


def _get(base_url: str, path: str, headers: dict[str, str]) -> int:
    return httpx.get(f"{base_url}{path}", headers=headers, timeout=10).status_code


def test_concurrent_requests_on_a_live_server(config_env: str, tmp_path: Path) -> None:
    config = rate_limited(AppConfig.load(), "details", 7, RateLimitScope.IP)
    harness = _harness(tmp_path, config)

    with LiveServer(harness.app()) as server:
        session_id = httpx.post(f"{server.base_url}/sessions", timeout=10).json()["data"]["session_id"]
        reads = ConcurrentRunner(partial(_get, server.base_url, "/chats", {SESSION_HEADER: session_id})).run()
        limited = ConcurrentRunner(partial(_get, server.base_url, "/details/profile", _ip("192.0.2.77"))).run()

    assert reads.errors == [] and reads.results == [HTTPStatus.OK] * 16
    assert sorted(limited.results).count(HTTPStatus.OK) == 7
    assert sorted(limited.results).count(HTTPStatus.TOO_MANY_REQUESTS) == 9
    assert harness.closed.is_set()
