from datetime import timedelta
from functools import partial

import httpx
import pytest
from pydantic import ValidationError

from main.package.clients.codeforces import (
    CodeforcesClient,
    CodeforcesClientError,
    CodeforcesHTTPStatusError,
    CodeforcesRatingChange,
    CodeforcesRequestError,
    CodeforcesResponseError,
    CodeforcesUserRatingResponse,
    InvalidCodeforcesArgumentError,
    InvalidCodeforcesClientSettingError,
)
from tests.conftest import HTTP_TIMEOUTS
from tests.support import ConcurrentRunner, RecordingTransport, ResponseSpec

BASE_URL = "https://codeforces.test"
RATING_OK = {
    "status": "OK",
    "result": [
        {
            "contestId": 1,
            "contestName": "Round 1",
            "handle": "tourist",
            "rank": 10,
            "ratingUpdateTimeSeconds": 1700000000,
            "oldRating": 0,
            "newRating": 1400,
            "unknownField": True,
        },
        {"contestId": 2, "contestName": "Round 2", "handle": "tourist", "rank": 3, "oldRating": 1400, "newRating": 1650},
    ],
}


def _client(transport: httpx.BaseTransport | None = None, **overrides: object) -> CodeforcesClient:
    return CodeforcesClient(**({"base_url": BASE_URL} | HTTP_TIMEOUTS | overrides), transport=transport)


def _call_many(client: CodeforcesClient, count: int) -> int:
    for _ in range(count):
        assert client.get_user_rating("tourist").status == "OK"
    return count


def test_sends_get_with_handle_query() -> None:
    transport = RecordingTransport(ResponseSpec(json=RATING_OK))
    with _client(transport) as client:
        client.get_user_rating("tou rist/x")

    request = transport.last_request
    assert request.method == "GET"
    assert str(request.url).startswith(f"{BASE_URL}/api/user.rating?")
    assert request.url.params["handle"] == "tou rist/x"


def test_parses_rating_history_into_dtos() -> None:
    with _client(RecordingTransport(ResponseSpec(json=RATING_OK))) as client:
        response = client.get_user_rating("tourist")

    assert isinstance(response, CodeforcesUserRatingResponse)
    assert isinstance(response.result, tuple)
    assert response.result[0] == CodeforcesRatingChange(
        contest_id=1,
        contest_name="Round 1",
        handle="tourist",
        rank=10,
        rating_update_time_seconds=1700000000,
        old_rating=0,
        new_rating=1400,
    )
    assert response.result[1].rating_update_time_seconds is None


def test_dtos_are_frozen() -> None:
    with _client(RecordingTransport(ResponseSpec(json=RATING_OK))) as client:
        response = client.get_user_rating("tourist")

    with pytest.raises(ValidationError):
        response.status = "FAILED"


@pytest.mark.parametrize("base_url", [BASE_URL, f"{BASE_URL}/"])
def test_base_url_has_no_trailing_slash(base_url: str) -> None:
    with _client(base_url=base_url) as client:
        assert client.base_url == BASE_URL


def test_http_error_uses_codeforces_comment() -> None:
    spec = ResponseSpec(400, json={"status": "FAILED", "comment": "handle: User with handle x not found"})
    with _client(RecordingTransport(spec)) as client, pytest.raises(CodeforcesHTTPStatusError) as error:
        client.get_user_rating("x")

    assert error.value.status_code == 400
    assert "User with handle x not found" in str(error.value)
    assert "FAILED" in error.value.body


def test_http_error_without_comment_uses_cut_body() -> None:
    with _client(RecordingTransport(ResponseSpec(502, text="x" * 2000))) as client, pytest.raises(CodeforcesHTTPStatusError) as error:
        client.get_user_rating("x")

    assert error.value.status_code == 502
    assert error.value.body == "x" * 500


@pytest.mark.parametrize("payload", [{"status": "FAILED"}, ["not", "an", "object"], {"comment": ""}, {"comment": 5}])
def test_http_error_with_json_but_no_comment_uses_body(payload: object) -> None:
    with _client(RecordingTransport(ResponseSpec(500, json=payload))) as client, pytest.raises(CodeforcesHTTPStatusError) as error:
        client.get_user_rating("x")

    assert error.value.body in str(error.value)


def test_non_ok_status_raises_with_comment() -> None:
    spec = ResponseSpec(json={"status": "FAILED", "comment": "Call limit exceeded"})
    with _client(RecordingTransport(spec)) as client, pytest.raises(CodeforcesResponseError, match="^Call limit exceeded$"):
        client.get_user_rating("x")


def test_non_ok_status_without_comment_names_the_status() -> None:
    with _client(RecordingTransport(ResponseSpec(json={"status": "FAILED"}))) as client, pytest.raises(CodeforcesResponseError, match="FAILED"):
        client.get_user_rating("x")


def test_invalid_json_raises() -> None:
    with _client(RecordingTransport(ResponseSpec(text="<html>"))) as client, pytest.raises(CodeforcesResponseError, match="invalid JSON"):
        client.get_user_rating("x")


def test_unexpected_shape_raises() -> None:
    spec = ResponseSpec(json={"status": "OK", "result": [{"rank": "first"}]})
    with _client(RecordingTransport(spec)) as client, pytest.raises(CodeforcesResponseError) as error:
        client.get_user_rating("x")

    assert isinstance(error.value.__cause__, ValidationError)


@pytest.mark.parametrize("transport_error", [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError])
def test_transport_errors_raise_request_error(transport_error: type[httpx.TransportError]) -> None:
    with _client(RecordingTransport(error=transport_error)) as client, pytest.raises(CodeforcesRequestError) as error:
        client.get_user_rating("x")

    assert isinstance(error.value.__cause__, transport_error)


@pytest.mark.parametrize("handle", ["", "   ", None, 5])
def test_blank_handle_is_rejected(handle: object) -> None:
    transport = RecordingTransport(ResponseSpec(json=RATING_OK))
    with _client(transport) as client, pytest.raises(InvalidCodeforcesArgumentError):
        client.get_user_rating(handle)

    assert transport.requests == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"base_url": ""},
        {"base_url": "codeforces.com"},
        {"base_url": "ftp://codeforces.com"},
        {"base_url": "https://"},
        {"base_url": "https://codeforces.com?x=1"},
        {"base_url": "https://codeforces.com#top"},
        {"base_url": None},
        {"connect_timeout": timedelta(0)},
        {"read_timeout": timedelta(seconds=-1)},
        {"write_timeout": 60},
        {"pool_timeout": None},
    ],
)
def test_invalid_settings_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidCodeforcesClientSettingError):
        _client(**overrides)


def test_settings_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        CodeforcesClient(BASE_URL, *HTTP_TIMEOUTS.values())


def test_closed_client_cannot_send() -> None:
    client = _client(RecordingTransport(ResponseSpec(json=RATING_OK)))
    with client:
        client.get_user_rating("tourist")

    with pytest.raises(RuntimeError):
        client.get_user_rating("tourist")


def test_one_client_is_safe_across_threads() -> None:
    with _client(RecordingTransport(ResponseSpec(json=RATING_OK))) as client:
        runner = ConcurrentRunner(partial(_call_many, client, 50)).run()

    assert runner.errors == []
    assert runner.results == [50] * 16


@pytest.mark.parametrize(
    "error_type",
    [
        InvalidCodeforcesClientSettingError,
        InvalidCodeforcesArgumentError,
        CodeforcesRequestError,
        CodeforcesHTTPStatusError,
        CodeforcesResponseError,
    ],
)
def test_errors_share_the_client_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, CodeforcesClientError)
