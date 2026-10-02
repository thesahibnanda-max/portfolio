from datetime import UTC, datetime, timedelta
from functools import partial

import httpx
import pytest
from pydantic import ValidationError

from main.package.clients.github import (
    GitHubClient,
    GitHubClientError,
    GitHubCommit,
    GitHubHTTPStatusError,
    GitHubRateLimitError,
    GitHubRepository,
    GitHubRequestError,
    GitHubResponseError,
    GitHubUser,
    InvalidGitHubArgumentError,
    InvalidGitHubClientSettingError,
)
from tests.conftest import HTTP_TIMEOUTS
from tests.support import ConcurrentRunner, RecordingTransport, ResponseSpec

BASE_URL = "https://github.test"
USER = {
    "login": "octocat",
    "id": 1,
    "node_id": "MDQ6",
    "type": "User",
    "site_admin": False,
    "public_repos": 8,
    "created_at": "2011-01-25T18:44:36Z",
    "updated_at": "2026-01-02T03:04:05Z",
    "plan": {"name": "free", "private_repos": 3},
    "unknown_field": True,
}
REPOSITORY = {
    "id": 9,
    "name": "hello",
    "full_name": "octocat/hello",
    "owner": USER,
    "private": False,
    "fork": False,
    "language": "Python",
    "stargazers_count": 42,
    "pushed_at": "2026-01-01T00:00:00Z",
    "topics": ["api", "python"],
    "license": {"key": "mit", "spdx_id": "MIT"},
    "permissions": {"admin": False, "pull": True},
}
COMMIT = {
    "sha": "abc123",
    "html_url": "https://github.com/octocat/hello/commit/abc123",
    "commit": {
        "message": "Initial commit",
        "comment_count": 0,
        "author": {"name": "Octo", "email": "o@example.com", "date": "2026-02-02T10:00:00Z"},
        "committer": {"name": "Octo", "date": "2026-02-02T10:00:00Z"},
        "tree": {"sha": "t1"},
        "verification": {"verified": True, "reason": "valid"},
    },
    "author": USER,
    "parents": [{"sha": "p1"}],
    "stats": {"additions": 2, "deletions": 1, "total": 3},
    "files": [{"filename": "a.py", "status": "added", "additions": 2, "changes": 2, "patch": "@@"}],
}
ROUTES = {
    "/users/octocat": ResponseSpec(json=USER),
    "/users/octocat/repos": ResponseSpec(json=[REPOSITORY, REPOSITORY]),
    "/repos/octocat/hello/commits": ResponseSpec(json=[COMMIT]),
    "/repos/octocat/hello/commits/abc123": ResponseSpec(json=COMMIT),
    "/repos/octo%2Fcat/hel%20lo/commits": ResponseSpec(json=[]),
    "/users/empty/repos": ResponseSpec(json=[]),
}


def _client(transport: httpx.BaseTransport | None = None, **overrides: object) -> GitHubClient:
    settings = {"base_url": BASE_URL, "api_version": "2022-11-28", "per_page": 50} | HTTP_TIMEOUTS | overrides
    return GitHubClient(**settings, transport=transport)


def _routed() -> RecordingTransport:
    return RecordingTransport(routes=ROUTES)


def _call_many(client: GitHubClient, count: int) -> int:
    for _ in range(count):
        assert client.get_user("octocat").login == "octocat"
        assert len(client.list_user_repositories("octocat")) == 2
    return count


def test_every_request_sends_accept_and_api_version_headers() -> None:
    transport = _routed()
    with _client(transport, api_version="2099-01-01") as client:
        client.get_user("octocat")

    headers = transport.last_request.headers
    assert headers["accept"] == "application/vnd.github+json"
    assert headers["x-github-api-version"] == "2099-01-01"


def test_get_user_parses_profile() -> None:
    transport = _routed()
    with _client(transport) as client:
        user = client.get_user("octocat")

    assert transport.last_request.method == "GET"
    assert isinstance(user, GitHubUser)
    assert user.login == "octocat"
    assert user.created_at == datetime(2011, 1, 25, 18, 44, 36, tzinfo=UTC)
    assert user.plan.private_repos == 3


def test_list_user_repositories_sends_sort_and_paging() -> None:
    transport = _routed()
    with _client(transport) as client:
        repositories = client.list_user_repositories("octocat", page=3)

    params = transport.last_request.url.params
    assert (params["sort"], params["direction"], params["per_page"], params["page"]) == ("updated", "desc", "50", "3")
    assert isinstance(repositories, tuple)
    assert len(repositories) == 2
    repository = repositories[0]
    assert isinstance(repository, GitHubRepository)
    assert repository.is_private is False
    assert repository.topics == ("api", "python")
    assert repository.license.spdx_id == "MIT"
    assert repository.permissions.pull is True
    assert repository.owner.login == "octocat"
    assert repository.pushed_at == datetime(2026, 1, 1, tzinfo=UTC)


def test_list_user_repositories_defaults_to_page_one() -> None:
    transport = _routed()
    with _client(transport) as client:
        client.list_user_repositories("octocat")

    assert transport.last_request.url.params["page"] == "1"


def test_empty_page_is_empty_tuple() -> None:
    with _client(_routed()) as client:
        assert client.list_user_repositories("empty", page=99) == ()


def test_list_commits_by_author_sends_author_and_paging() -> None:
    transport = _routed()
    with _client(transport) as client:
        commits = client.list_commits_by_author("octocat", "hello", "octo", page=2)

    params = transport.last_request.url.params
    assert (params["author"], params["per_page"], params["page"]) == ("octo", "50", "2")
    assert isinstance(commits[0], GitHubCommit)
    assert commits[0].commit.verification.verified is True
    assert commits[0].commit.author.date == datetime(2026, 2, 2, 10, tzinfo=UTC)


def test_path_segments_are_escaped() -> None:
    transport = _routed()
    with _client(transport) as client:
        assert client.list_commits_by_author("octo/cat", "hel lo", "me") == ()

    assert transport.last_request.url.raw_path.startswith(b"/repos/octo%2Fcat/hel%20lo/commits?")


def test_get_commit_parses_stats_and_files() -> None:
    with _client(_routed()) as client:
        commit = client.get_commit("octocat", "hello", "abc123")

    assert commit.stats.total == 3
    assert commit.files[0].filename == "a.py"
    assert commit.parents[0].sha == "p1"
    assert commit.commit.tree.sha == "t1"


def test_repository_accepts_is_private_by_name() -> None:
    assert GitHubRepository.model_validate({"is_private": True}).is_private is True


def test_dtos_are_frozen() -> None:
    with _client(_routed()) as client:
        user = client.get_user("octocat")

    with pytest.raises(ValidationError):
        user.login = "other"


@pytest.mark.parametrize("base_url", [BASE_URL, f"{BASE_URL}/"])
def test_base_url_has_no_trailing_slash(base_url: str) -> None:
    with _client(base_url=base_url) as client:
        assert client.base_url == BASE_URL


def test_base_url_with_path_prefix_is_kept() -> None:
    transport = RecordingTransport(ResponseSpec(json=USER))
    with _client(transport, base_url="https://ghe.test/api/v3/") as client:
        client.get_user("octocat")

    assert str(transport.last_request.url) == "https://ghe.test/api/v3/users/octocat"


def test_not_found_raises_status_error_with_body() -> None:
    with _client(_routed()) as client, pytest.raises(GitHubHTTPStatusError) as error:
        client.get_user("ghost")

    assert type(error.value) is GitHubHTTPStatusError
    assert error.value.status_code == 404
    assert "Not Found" in error.value.body


@pytest.mark.parametrize(
    "spec",
    [
        ResponseSpec(403, json={"message": "rate limit"}, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1999999999"}),
        ResponseSpec(429, json={"message": "slow down"}, headers={"retry-after": "60"}),
        ResponseSpec(403, json={"message": "secondary"}, headers={"retry-after": "30"}),
    ],
)
def test_rate_limit_raises_rate_limit_error(spec: ResponseSpec) -> None:
    with _client(RecordingTransport(spec)) as client, pytest.raises(GitHubRateLimitError) as error:
        client.get_user("octocat")

    assert isinstance(error.value, GitHubHTTPStatusError)
    assert error.value.status_code == spec.status_code
    assert "rate limit exceeded" in str(error.value)


def test_rate_limit_message_includes_reset_time() -> None:
    spec = ResponseSpec(403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1999999999"}, json={})
    with _client(RecordingTransport(spec)) as client, pytest.raises(GitHubRateLimitError, match="1999999999"):
        client.get_user("octocat")


@pytest.mark.parametrize(
    "spec",
    [
        ResponseSpec(403, json={"message": "forbidden"}),
        ResponseSpec(403, json={"message": "forbidden"}, headers={"x-ratelimit-remaining": "10"}),
        ResponseSpec(500, text="x" * 2000),
    ],
)
def test_other_errors_are_plain_status_errors(spec: ResponseSpec) -> None:
    with _client(RecordingTransport(spec)) as client, pytest.raises(GitHubHTTPStatusError) as error:
        client.get_user("octocat")

    assert type(error.value) is GitHubHTTPStatusError
    assert len(error.value.body) <= 500


def test_invalid_json_raises() -> None:
    with _client(RecordingTransport(ResponseSpec(text="<html>"))) as client, pytest.raises(GitHubResponseError, match="invalid JSON"):
        client.get_user("octocat")


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        ("get_user", {"id": "not-an-int"}),
        ("get_user", ["not", "an", "object"]),
        ("list_user_repositories", {"not": "a list"}),
        ("list_user_repositories", [{"stargazers_count": "many"}]),
    ],
)
def test_unexpected_shape_raises(method: str, payload: object) -> None:
    with _client(RecordingTransport(ResponseSpec(json=payload))) as client, pytest.raises(GitHubResponseError) as error:
        getattr(client, method)("octocat")

    assert isinstance(error.value.__cause__, ValidationError)


@pytest.mark.parametrize("transport_error", [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError])
def test_transport_errors_raise_request_error(transport_error: type[httpx.TransportError]) -> None:
    with _client(RecordingTransport(error=transport_error)) as client, pytest.raises(GitHubRequestError) as error:
        client.get_user("octocat")

    assert isinstance(error.value.__cause__, transport_error)


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("get_user", ("",)),
        ("get_user", (None,)),
        ("list_user_repositories", (" ",)),
        ("list_user_repositories", ("octocat", 0)),
        ("list_user_repositories", ("octocat", -1)),
        ("list_user_repositories", ("octocat", True)),
        ("list_user_repositories", ("octocat", "2")),
        ("list_commits_by_author", ("", "hello", "me")),
        ("list_commits_by_author", ("octocat", "", "me")),
        ("list_commits_by_author", ("octocat", "hello", " ")),
        ("list_commits_by_author", ("octocat", "hello", "me", 0)),
        ("get_commit", ("", "hello", "abc")),
        ("get_commit", ("octocat", " ", "abc")),
        ("get_commit", ("octocat", "hello", "")),
    ],
)
def test_invalid_arguments_are_rejected_before_sending(method: str, args: tuple) -> None:
    transport = _routed()
    with _client(transport) as client, pytest.raises(InvalidGitHubArgumentError):
        getattr(client, method)(*args)

    assert transport.requests == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"base_url": "github.com"},
        {"base_url": ""},
        {"base_url": "https://api.github.com#x"},
        {"api_version": ""},
        {"api_version": None},
        {"per_page": 0},
        {"per_page": 101},
        {"per_page": True},
        {"per_page": "100"},
        {"connect_timeout": timedelta(0)},
        {"read_timeout": 60},
    ],
)
def test_invalid_settings_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidGitHubClientSettingError):
        _client(**overrides)


@pytest.mark.parametrize("per_page", [1, 100])
def test_per_page_bounds_are_accepted(per_page: int) -> None:
    transport = _routed()
    with _client(transport, per_page=per_page) as client:
        client.list_user_repositories("octocat")

    assert transport.last_request.url.params["per_page"] == str(per_page)


def test_closed_client_cannot_send() -> None:
    client = _client(_routed())
    with client:
        client.get_user("octocat")

    with pytest.raises(RuntimeError):
        client.get_user("octocat")


def test_one_client_is_safe_across_threads() -> None:
    with _client(_routed()) as client:
        runner = ConcurrentRunner(partial(_call_many, client, 50)).run()

    assert runner.errors == []
    assert runner.results == [50] * 16


@pytest.mark.parametrize(
    "error_type",
    [
        InvalidGitHubClientSettingError,
        InvalidGitHubArgumentError,
        GitHubRequestError,
        GitHubHTTPStatusError,
        GitHubRateLimitError,
        GitHubResponseError,
    ],
)
def test_errors_share_the_client_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, GitHubClientError)
