from collections.abc import Iterator
from datetime import datetime
from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main.package.ai.orchestrator import QueryScope
from tests.main.package.handler.fakes import (
    ANSWER,
    SESSION_HEADER,
    Harness,
    decision,
    new_chat,
    new_session,
    with_section,
)
from tests.support import RecordingTransport, ResponseSpec

UNKNOWN_UUID7 = "01a0f968-0e19-7511-abcd-35c8c266e97e"


@pytest.fixture
def harness(config_env: str, tmp_path: Path) -> Harness:
    return Harness(tmp_path)


@pytest.fixture
def client(harness: Harness) -> Iterator[TestClient]:
    with harness.client() as test_client:
        yield test_client


@pytest.fixture
def session_id(client: TestClient) -> str:
    return new_session(client)


@pytest.fixture
def headers(session_id: str) -> dict[str, str]:
    return {SESSION_HEADER: session_id}


@pytest.fixture
def chat_id(client: TestClient, session_id: str) -> str:
    return new_chat(client, session_id)


def _assert_envelope(response, status: HTTPStatus) -> dict:
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"status", "timestamp", "data"}
    assert body["status"] == status
    assert datetime.fromisoformat(body["timestamp"]).tzinfo is not None
    return body["data"]


def _assert_error(response, status: HTTPStatus, code: str) -> dict:
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"status", "timestamp", "error", "message", "details"}
    assert (body["status"], body["error"]) == (status, code)
    assert body["message"]
    return body


def test_health(client: TestClient) -> None:
    assert _assert_envelope(client.get("/health"), HTTPStatus.OK) == {"status": "UP"}


def test_create_session(client: TestClient) -> None:
    data = _assert_envelope(client.post("/sessions"), HTTPStatus.CREATED)

    assert set(data) == {"session_id", "created_at", "expires_at"}
    assert datetime.fromisoformat(data["expires_at"]) > datetime.fromisoformat(data["created_at"])


def test_chat_lifecycle(client: TestClient, headers: dict[str, str]) -> None:
    created = _assert_envelope(client.post("/chats", json={"title": "Ratings"}, headers=headers), HTTPStatus.CREATED)
    assert set(created) == {"chat_id", "title", "created_at", "updated_at", "origin"}
    assert created["origin"] == "chat"
    chat_id = created["chat_id"]

    default = _assert_envelope(client.post("/chats", headers=headers), HTTPStatus.CREATED)
    untitled = _assert_envelope(client.post("/chats", json={}, headers=headers), HTTPStatus.CREATED)
    assert default["title"] == untitled["title"] == "New chat"

    listed = _assert_envelope(client.get("/chats", headers=headers), HTTPStatus.OK)
    assert {chat["chat_id"] for chat in listed["chats"]} == {chat_id, default["chat_id"], untitled["chat_id"]}

    renamed = _assert_envelope(client.patch(f"/chats/{chat_id}", json={"title": "  Contests "}, headers=headers), HTTPStatus.OK)
    assert renamed["title"] == "Contests"

    fetched = _assert_envelope(client.get(f"/chats/{chat_id}", headers=headers), HTTPStatus.OK)
    assert (fetched["title"], fetched["messages"]) == ("Contests", [])
    assert "session_id" not in fetched

    deleted = client.delete(f"/chats/{chat_id}", headers=headers)
    assert (deleted.status_code, deleted.content) == (HTTPStatus.NO_CONTENT, b"")
    _assert_error(client.get(f"/chats/{chat_id}", headers=headers), HTTPStatus.NOT_FOUND, "CHAT_NOT_FOUND")


def test_chats_record_their_origin(client: TestClient, headers: dict[str, str]) -> None:
    cli = _assert_envelope(client.post("/chats", json={"title": "Terminal", "origin": "cli"}, headers=headers), HTTPStatus.CREATED)
    untitled_cli = _assert_envelope(client.post("/chats", json={"origin": "cli"}, headers=headers), HTTPStatus.CREATED)
    chat = _assert_envelope(client.post("/chats", json={"origin": "chat"}, headers=headers), HTTPStatus.CREATED)

    assert (cli["origin"], untitled_cli["origin"], chat["origin"]) == ("cli", "cli", "chat")
    assert untitled_cli["title"] == "New chat"
    listed = _assert_envelope(client.get("/chats", headers=headers), HTTPStatus.OK)["chats"]
    assert {item["chat_id"]: item["origin"] for item in listed} == {
        cli["chat_id"]: "cli",
        untitled_cli["chat_id"]: "cli",
        chat["chat_id"]: "chat",
    }
    _assert_error(client.post("/chats", json={"origin": "web"}, headers=headers), HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR")


def test_send_message_answers_and_saves(client: TestClient, headers: dict[str, str], chat_id: str) -> None:
    data = _assert_envelope(client.post(f"/chats/{chat_id}/messages", json={"message": " rating? "}, headers=headers), HTTPStatus.OK)

    assert (data["answer"], data["scope"], data["required_contexts"]) == (ANSWER, "IN_SCOPE", ["CODEFORCES"])
    assert [(message["role"], message["content"]) for message in data["chat"]["messages"]] == [
        ("user", "rating?"),
        ("assistant", ANSWER),
    ]


@pytest.mark.parametrize("scope", [QueryScope.NOT_RELATED_TO_PORTFOLIO, QueryScope.PROMPT_INJECTION, QueryScope.UNSAFE])
def test_flagged_message_gets_the_configured_fallback(harness: Harness, client: TestClient, headers: dict[str, str], chat_id: str, scope: QueryScope) -> None:
    harness.groq.decision = decision(scope, ())

    data = _assert_envelope(client.post(f"/chats/{chat_id}/messages", json={"message": "hi"}, headers=headers), HTTPStatus.OK)

    assert data["answer"] == harness.config.chat.fallback_messages[scope]
    assert data["scope"] == scope


@pytest.mark.parametrize(
    ("path", "key"),
    [
        ("/details/professional", "github_links"),
        ("/details/leetcode", "accounts"),
        ("/details/codeforces", "accounts"),
        ("/details/github", "accounts"),
        ("/details/profile", "profile_details"),
        ("/details/personality", "personal_profile"),
    ],
)
def test_details(client: TestClient, path: str, key: str) -> None:
    data = _assert_envelope(client.get(path), HTTPStatus.OK)

    assert key in data


def test_cli_manifest_lists_skills_plugins_settings_and_fortunes(client: TestClient) -> None:
    data = _assert_envelope(client.get("/details/cli"), HTTPStatus.OK)

    assert set(data) == {"plugins", "skills", "settings", "fortunes"}
    assert {"name", "aliases", "usage", "summary", "group", "plugin", "arg_source"} == set(data["skills"][0])
    assert {plugin["name"] for plugin in data["plugins"]} >= {"core", "extras"}
    assert data["settings"][0]["key"] == "mode"
    assert data["fortunes"]


def test_personality_never_exposes_private_details(client: TestClient) -> None:
    data = _assert_envelope(client.get("/details/personality"), HTTPStatus.OK)

    assert set(data["personal_profile"]) == {"personality", "interests", "favorites", "lifestyle", "languages"}
    assert "physical_appearance" not in str(data) and "basic_info" not in str(data)
    assert data["personal_profile"]["favorites"]["sports_icons"]["football"]


def test_details_list_every_configured_account(harness: Harness, client: TestClient) -> None:
    data = _assert_envelope(client.get("/details/github"), HTTPStatus.OK)

    assert [account["username"] for account in data["accounts"]] == [
        account.username for account in harness.config.data_service.github_accounts
    ]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/chats", {"title": 5}),
        ("post", "/chats", {"title": "x", "extra": 1}),
        ("post", "/chats", ["not", "an", "object"]),
        ("patch", "/chats/{chat_id}", {}),
        ("patch", "/chats/{chat_id}", {"title": None}),
        ("post", "/chats/{chat_id}/messages", {}),
        ("post", "/chats/{chat_id}/messages", {"message": 1}),
        ("post", "/chats/{chat_id}/messages", {"message": "hi", "role": "system"}),
        ("post", "/chats/{chat_id}/messages/stream", {"text": "hi"}),
    ],
)
def test_invalid_bodies_are_400_with_details(client: TestClient, headers: dict[str, str], chat_id: str, method: str, path: str, body: object) -> None:
    response = getattr(client, method)(path.format(chat_id=chat_id), json=body, headers=headers)

    error = _assert_error(response, HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR")
    assert error["details"]
    assert all(detail["field"].startswith("body") for detail in error["details"])


def test_invalid_json_is_400(client: TestClient, headers: dict[str, str], chat_id: str) -> None:
    response = client.post(f"/chats/{chat_id}/messages", content=b"{nope", headers={**headers, "content-type": "application/json"})

    _assert_error(response, HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/chats"), ("post", "/chats"), ("get", f"/chats/{UNKNOWN_UUID7}"), ("delete", f"/chats/{UNKNOWN_UUID7}")],
)
def test_missing_session_header_is_400(client: TestClient, method: str, path: str) -> None:
    error = _assert_error(getattr(client, method)(path), HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR")

    assert error["details"][0]["field"] == f"header.{SESSION_HEADER}"


def test_malformed_ids_are_400(client: TestClient, headers: dict[str, str]) -> None:
    _assert_error(client.get("/chats", headers={SESSION_HEADER: "not-a-uuid"}), HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR")
    _assert_error(client.get("/chats/abc", headers=headers), HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR")


@pytest.mark.parametrize("message", ["", "   ", "x" * 4001])
def test_invalid_messages_are_400(client: TestClient, headers: dict[str, str], chat_id: str, message: str) -> None:
    response = client.post(f"/chats/{chat_id}/messages", json={"message": message}, headers=headers)

    _assert_error(response, HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR")


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_invalid_titles_are_400(client: TestClient, headers: dict[str, str], chat_id: str, title: str) -> None:
    _assert_error(client.post("/chats", json={"title": title}, headers=headers), HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR")
    _assert_error(client.patch(f"/chats/{chat_id}", json={"title": title}, headers=headers), HTTPStatus.BAD_REQUEST, "VALIDATION_ERROR")


def test_unknown_session_is_401(client: TestClient) -> None:
    _assert_error(client.get("/chats", headers={SESSION_HEADER: UNKNOWN_UUID7}), HTTPStatus.UNAUTHORIZED, "SESSION_EXPIRED")


def test_foreign_chat_is_404(client: TestClient, chat_id: str) -> None:
    other = {SESSION_HEADER: new_session(client)}

    _assert_error(client.get(f"/chats/{chat_id}", headers=other), HTTPStatus.NOT_FOUND, "CHAT_NOT_FOUND")
    _assert_error(client.post(f"/chats/{chat_id}/messages", json={"message": "hi"}, headers=other), HTTPStatus.NOT_FOUND, "CHAT_NOT_FOUND")


def test_unknown_route_is_404(client: TestClient) -> None:
    _assert_error(client.get("/nope"), HTTPStatus.NOT_FOUND, "NOT_FOUND")


def test_wrong_method_is_405_with_allow(client: TestClient) -> None:
    response = client.put("/health")

    _assert_error(response, HTTPStatus.METHOD_NOT_ALLOWED, "METHOD_NOT_ALLOWED")
    assert "GET" in response.headers["allow"]


def test_full_chat_is_409(config_env: str, tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.config = with_section(harness.config, "chat", max_messages_per_chat=2)

    with harness.client() as client:
        headers = {SESSION_HEADER: new_session(client)}
        chat_id = new_chat(client, headers[SESSION_HEADER])
        client.post(f"/chats/{chat_id}/messages", json={"message": "one"}, headers=headers)

        response = client.post(f"/chats/{chat_id}/messages", json={"message": "two"}, headers=headers)

    _assert_error(response, HTTPStatus.CONFLICT, "CHAT_FULL")


def test_declared_body_over_the_limit_is_413(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post("/chats", content=b"x" * 262145, headers={**headers, "content-type": "application/json"})

    _assert_error(response, HTTPStatus.CONTENT_TOO_LARGE, "CONTENT_TOO_LARGE")


def test_chunked_body_over_the_limit_is_413(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(
        "/chats",
        content=iter([b"x" * 200000, b"x" * 200000]),
        headers={**headers, "content-type": "application/json"},
    )

    _assert_error(response, HTTPStatus.CONTENT_TOO_LARGE, "CONTENT_TOO_LARGE")


def test_body_at_the_limit_is_accepted(client: TestClient, headers: dict[str, str]) -> None:
    title = "x" * 100
    body = f'{{"title": "{title}"}}'.encode().ljust(262144, b" ")

    response = client.post("/chats", content=body, headers={**headers, "content-type": "application/json"})

    assert response.status_code == HTTPStatus.CREATED


def test_upstream_failure_is_502_without_leaking(config_env: str, tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.upstream.codeforces = RecordingTransport(ResponseSpec(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, text="secret upstream trace"))

    with harness.client() as client:
        response = client.get("/details/codeforces")

    error = _assert_error(response, HTTPStatus.BAD_GATEWAY, "UPSTREAM_ERROR")
    assert "secret" not in response.text and "codeforces.com" not in error["message"]


@pytest.mark.parametrize(("status", "expected", "code"), [(HTTPStatus.INTERNAL_SERVER_ERROR, HTTPStatus.BAD_GATEWAY, "UPSTREAM_ERROR"), (HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE, "UPSTREAM_BUSY")])
def test_groq_failures_map_to_gateway_statuses(harness: Harness, client: TestClient, headers: dict[str, str], chat_id: str, status: int, expected: HTTPStatus, code: str) -> None:
    harness.groq.answer_status = status

    response = client.post(f"/chats/{chat_id}/messages", json={"message": "rating?"}, headers=headers)

    _assert_error(response, expected, code)
    assert _assert_envelope(client.get(f"/chats/{chat_id}", headers=headers), HTTPStatus.OK)["messages"] == []


def test_unexpected_errors_are_500_logged_and_hidden(harness: Harness, client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    container = harness.containers[0]
    monkeypatch.setattr(type(container.repository), "create_session", _explode)

    response = client.post("/sessions")

    error = _assert_error(response, HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
    assert "kaboom" not in response.text
    assert error["message"] == "Something went wrong on our side; please try again"
    assert "RuntimeError" in caplog.text


def _explode(*args: object) -> None:
    raise RuntimeError("kaboom")


def test_errors_carry_cors_headers(client: TestClient, harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    origin = {"Origin": "https://sahibnanda.net"}
    monkeypatch.setattr(type(harness.containers[0].repository), "create_session", _explode)

    for response in (client.get("/chats", headers=origin), client.get("/nope", headers=origin), client.post("/sessions", headers=origin)):
        assert response.headers["access-control-allow-origin"] == "*"


def test_cors_preflight_allows_the_session_header(client: TestClient) -> None:
    response = client.options(
        "/chats",
        headers={
            "Origin": "https://sahibnanda.net",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": SESSION_HEADER,
        },
    )

    assert response.status_code == HTTPStatus.OK
    assert response.headers["access-control-max-age"] == "3600"


def test_openapi_documents_the_envelopes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert {"/health", "/sessions", "/chats", "/chats/{chat_id}", "/chats/{chat_id}/messages", "/chats/{chat_id}/messages/stream"} <= set(schema["paths"])
    assert "ApiResponse_ChatReplyResponse_" in schema["components"]["schemas"]
