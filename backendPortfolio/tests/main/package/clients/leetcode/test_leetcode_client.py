import json
from datetime import timedelta
from functools import partial

import httpx
import pytest
from pydantic import ValidationError

from main.package.clients.leetcode import (
    InvalidLeetcodeArgumentError,
    InvalidLeetcodeClientSettingError,
    LeetcodeClient,
    LeetcodeClientError,
    LeetcodeHTTPStatusError,
    LeetcodeRequestError,
    LeetcodeResponseError,
    LeetcodeUserCalendar,
    LeetcodeUserProfileResponse,
)
from tests.conftest import HTTP_TIMEOUTS
from tests.support import ConcurrentRunner, RecordingTransport, ResponseSpec

BASE_URL = "https://leetcode.test"
PROFILE_OK = {
    "data": {
        "matchedUser": {
            "username": "imsahibnanda",
            "githubUrl": "https://github.com/x",
            "twitterUrl": None,
            "linkedinUrl": "https://linkedin.com/in/x",
            "profile": {"realName": "Sahib", "ranking": 5000, "starRating": 1.5, "websites": ["a.dev"], "skillTags": ["python"]},
            "submitStatsGlobal": {"acSubmissionNum": [{"difficulty": "All", "count": 674, "submissions": 900}]},
            "badges": [{"id": "1", "displayName": "50 Days", "icon": "i.png", "creationDate": "2026-01-01"}],
            "activeBadge": {"id": "1", "displayName": "50 Days", "icon": "i.png"},
            "languageProblemCount": [{"languageName": "Python3", "problemsSolved": 600}],
            "tagProblemCounts": {
                "advanced": [{"tagName": "Dynamic Programming", "problemsSolved": 80}],
                "intermediate": [],
                "fundamental": [{"tagName": "Array", "problemsSolved": 300}],
            },
            "userCalendar": {
                "activeYears": [2025, 2026],
                "streak": 7,
                "totalActiveDays": 51,
                "submissionCalendar": "{\"1700000000\": 2, \"1700086400\": 5}",
            },
            "unknownField": "ignored",
        },
        "userContestRanking": {
            "attendedContestsCount": 1,
            "rating": 1650.5,
            "globalRanking": 100000,
            "totalParticipants": 600000,
            "topPercentage": 17.2,
            "badge": {"name": "Knight"},
        },
        "userContestRankingHistory": [
            {
                "attended": True,
                "trendDirection": "UP",
                "problemsSolved": 3,
                "totalProblems": 4,
                "finishTimeInSeconds": 4200,
                "rating": 1650.5,
                "ranking": 2000,
                "contest": {"title": "Weekly Contest 1", "startTime": 1700000000},
            }
        ],
    }
}


def _client(transport: httpx.BaseTransport | None = None, **overrides: object) -> LeetcodeClient:
    return LeetcodeClient(**({"base_url": BASE_URL} | HTTP_TIMEOUTS | overrides), transport=transport)


def _call_many(client: LeetcodeClient, count: int) -> int:
    for _ in range(count):
        assert client.get_user_profile("imsahibnanda").data.matched_user.username == "imsahibnanda"
    return count


def test_posts_graphql_with_username_as_variable() -> None:
    transport = RecordingTransport(ResponseSpec(json=PROFILE_OK))
    username = 'evil") { injected }'
    with _client(transport) as client:
        client.get_user_profile(username)

    request = transport.last_request
    body = json.loads(request.content)
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/graphql"
    assert request.headers["content-type"] == "application/json"
    assert body["operationName"] == "userPublicProfile"
    assert body["variables"] == {"username": username}
    assert "query userPublicProfile($username: String!)" in body["query"]
    assert "injected" not in body["query"]


@pytest.mark.parametrize(
    "section",
    [
        "matchedUser(username: $username)",
        "profile {",
        "submitStatsGlobal {",
        "badges {",
        "activeBadge {",
        "languageProblemCount {",
        "tagProblemCounts {",
        "userCalendar {",
        "userContestRanking(username: $username)",
        "userContestRankingHistory(username: $username)",
    ],
)
def test_query_always_requests_every_section(section: str) -> None:
    transport = RecordingTransport(ResponseSpec(json=PROFILE_OK))
    with _client(transport) as client:
        client.get_user_profile("imsahibnanda")

    assert section in json.loads(transport.last_request.content)["query"]


def test_parses_profile_into_dtos() -> None:
    with _client(RecordingTransport(ResponseSpec(json=PROFILE_OK))) as client:
        response = client.get_user_profile("imsahibnanda")

    assert isinstance(response, LeetcodeUserProfileResponse)
    user = response.data.matched_user
    assert user.github_url == "https://github.com/x"
    assert user.twitter_url is None
    assert user.profile.star_rating == 1.5
    assert user.profile.websites == ("a.dev",)
    assert user.submit_stats_global.ac_submission_num[0].count == 674
    assert user.badges[0].creation_date == "2026-01-01"
    assert user.active_badge.display_name == "50 Days"
    assert user.language_problem_count[0].language_name == "Python3"
    assert user.tag_problem_counts.advanced[0].tag_name == "Dynamic Programming"
    assert user.tag_problem_counts.intermediate == ()
    assert response.data.user_contest_ranking.badge.name == "Knight"
    assert response.data.user_contest_ranking.top_percentage == 17.2
    assert response.data.user_contest_ranking_history[0].contest.start_time == 1700000000
    assert response.errors is None


def test_submission_calendar_string_is_parsed_into_dict() -> None:
    with _client(RecordingTransport(ResponseSpec(json=PROFILE_OK))) as client:
        calendar = client.get_user_profile("imsahibnanda").data.matched_user.user_calendar

    assert calendar.submission_calendar == {1700000000: 2, 1700086400: 5}
    assert calendar.active_years == (2025, 2026)


@pytest.mark.parametrize("value", [{"1": 2}, None])
def test_submission_calendar_accepts_object_or_null(value: object) -> None:
    calendar = LeetcodeUserCalendar.model_validate({"submissionCalendar": value})

    assert calendar.submission_calendar == ({1: 2} if value else None)


def test_missing_sections_are_none() -> None:
    with _client(RecordingTransport(ResponseSpec(json={"data": {"matchedUser": {"username": "u"}}}))) as client:
        response = client.get_user_profile("u")

    assert response.data.matched_user.profile is None
    assert response.data.user_contest_ranking is None
    assert response.data.user_contest_ranking_history is None


def test_dtos_are_frozen() -> None:
    with _client(RecordingTransport(ResponseSpec(json=PROFILE_OK))) as client:
        response = client.get_user_profile("imsahibnanda")

    with pytest.raises(ValidationError):
        response.data.matched_user.username = "other"


@pytest.mark.parametrize("base_url", [BASE_URL, f"{BASE_URL}/"])
def test_base_url_has_no_trailing_slash(base_url: str) -> None:
    with _client(base_url=base_url) as client:
        assert client.base_url == BASE_URL


def test_graphql_errors_raise_with_joined_messages() -> None:
    spec = ResponseSpec(json={"data": {"matchedUser": None}, "errors": [{"message": "That user does not exist."}, {"message": "Second"}]})
    with _client(RecordingTransport(spec)) as client, pytest.raises(LeetcodeResponseError) as error:
        client.get_user_profile("nobody")

    assert str(error.value) == "Leetcode API returned errors: That user does not exist.; Second"


def test_empty_errors_list_is_not_an_error() -> None:
    with _client(RecordingTransport(ResponseSpec(json=PROFILE_OK | {"errors": []}))) as client:
        assert client.get_user_profile("imsahibnanda").errors == ()


def test_http_error_carries_status_and_cut_body() -> None:
    with _client(RecordingTransport(ResponseSpec(503, text="x" * 2000))) as client, pytest.raises(LeetcodeHTTPStatusError) as error:
        client.get_user_profile("u")

    assert error.value.status_code == 503
    assert error.value.body == "x" * 500
    assert "HTTP 503" in str(error.value)


def test_invalid_json_raises() -> None:
    with _client(RecordingTransport(ResponseSpec(text="not json"))) as client, pytest.raises(LeetcodeResponseError, match="invalid JSON"):
        client.get_user_profile("u")


@pytest.mark.parametrize(
    "payload",
    [
        {"data": {"matchedUser": {"userCalendar": {"submissionCalendar": "{bad"}}}},
        {"data": {"matchedUser": {"profile": {"ranking": "first"}}}},
        {"data": "not an object"},
    ],
)
def test_unexpected_shape_raises(payload: object) -> None:
    with _client(RecordingTransport(ResponseSpec(json=payload))) as client, pytest.raises(LeetcodeResponseError) as error:
        client.get_user_profile("u")

    assert isinstance(error.value.__cause__, ValidationError)


@pytest.mark.parametrize("transport_error", [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError])
def test_transport_errors_raise_request_error(transport_error: type[httpx.TransportError]) -> None:
    with _client(RecordingTransport(error=transport_error)) as client, pytest.raises(LeetcodeRequestError) as error:
        client.get_user_profile("u")

    assert isinstance(error.value.__cause__, transport_error)


@pytest.mark.parametrize("username", ["", "  ", None])
def test_blank_username_is_rejected(username: object) -> None:
    transport = RecordingTransport(ResponseSpec(json=PROFILE_OK))
    with _client(transport) as client, pytest.raises(InvalidLeetcodeArgumentError):
        client.get_user_profile(username)

    assert transport.requests == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"base_url": ""},
        {"base_url": "leetcode.com"},
        {"base_url": "https://"},
        {"base_url": "https://leetcode.com?x=1"},
        {"connect_timeout": timedelta(0)},
        {"read_timeout": None},
        {"write_timeout": "60s"},
        {"pool_timeout": timedelta(seconds=-1)},
    ],
)
def test_invalid_settings_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidLeetcodeClientSettingError):
        _client(**overrides)


def test_closed_client_cannot_send() -> None:
    client = _client(RecordingTransport(ResponseSpec(json=PROFILE_OK)))
    client.close()

    with pytest.raises(RuntimeError):
        client.get_user_profile("u")


def test_one_client_is_safe_across_threads() -> None:
    with _client(RecordingTransport(ResponseSpec(json=PROFILE_OK))) as client:
        runner = ConcurrentRunner(partial(_call_many, client, 50)).run()

    assert runner.errors == []
    assert runner.results == [50] * 16


@pytest.mark.parametrize(
    "error_type",
    [
        InvalidLeetcodeClientSettingError,
        InvalidLeetcodeArgumentError,
        LeetcodeRequestError,
        LeetcodeHTTPStatusError,
        LeetcodeResponseError,
    ],
)
def test_errors_share_the_client_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, LeetcodeClientError)
