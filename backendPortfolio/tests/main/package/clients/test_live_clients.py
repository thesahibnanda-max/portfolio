from collections.abc import Iterator

import pytest

from main.config import AppConfig
from main.package.clients.codeforces import CodeforcesClient, CodeforcesHTTPStatusError
from main.package.clients.github import GitHubClient
from main.package.clients.leetcode import LeetcodeClient
from main.package.service.data import DataService, PlatformAccount
from main.package.ttl_key_value_store import TTLKeyValueStoreFactory

pytestmark = pytest.mark.live

LEETCODE_USERNAME = "imsahibnanda"
CODEFORCES_HANDLE = "shisukenohara"
GITHUB_USERNAME = "thesahibnanda-max"


@pytest.fixture
def config(config_env: str) -> AppConfig:
    return AppConfig.load()


@pytest.fixture
def leetcode(config: AppConfig) -> Iterator[LeetcodeClient]:
    with LeetcodeClient(base_url=config.leetcode.base_url, **config.http_client.model_dump()) as client:
        yield client


@pytest.fixture
def codeforces(config: AppConfig) -> Iterator[CodeforcesClient]:
    with CodeforcesClient(base_url=config.codeforces.base_url, **config.http_client.model_dump()) as client:
        yield client


@pytest.fixture
def github(config: AppConfig) -> Iterator[GitHubClient]:
    with GitHubClient(
        base_url=config.github.base_url,
        api_version=config.github.api_version,
        per_page=config.github.per_page,
        **config.http_client.model_dump(),
    ) as client:
        yield client


def test_leetcode_profile(leetcode: LeetcodeClient) -> None:
    data = leetcode.get_user_profile(LEETCODE_USERNAME).data
    user = data.matched_user

    assert user.username == LEETCODE_USERNAME
    assert {entry.difficulty for entry in user.submit_stats_global.ac_submission_num} >= {"All", "Easy", "Medium", "Hard"}
    assert all(isinstance(day, int) and isinstance(count, int) for day, count in (user.user_calendar.submission_calendar or {}).items())
    assert isinstance(data.user_contest_ranking_history, tuple | None)


def test_codeforces_rating_history(codeforces: CodeforcesClient) -> None:
    response = codeforces.get_user_rating(CODEFORCES_HANDLE)

    assert response.status == "OK"
    assert response.result
    assert all(change.handle.lower() == CODEFORCES_HANDLE for change in response.result)


def test_codeforces_invalid_handle_reports_api_comment(codeforces: CodeforcesClient) -> None:
    with pytest.raises(CodeforcesHTTPStatusError) as error:
        codeforces.get_user_rating("this_handle_should_not_exist_zz9")

    assert error.value.status_code == 400
    assert "handle" in str(error.value)


def test_github_user_repositories_and_commits(github: GitHubClient) -> None:
    user = github.get_user(GITHUB_USERNAME)
    repositories = github.list_user_repositories(GITHUB_USERNAME)

    assert user.login == GITHUB_USERNAME
    assert repositories
    assert all(repository.owner.login == GITHUB_USERNAME for repository in repositories)

    newest = repositories[0]
    commits = github.list_commits_by_author(GITHUB_USERNAME, newest.name, GITHUB_USERNAME)
    if commits:
        commit = github.get_commit(GITHUB_USERNAME, newest.name, commits[0].sha)
        assert commit.sha == commits[0].sha
        assert commit.stats is not None


def test_data_service_end_to_end(config: AppConfig, leetcode: LeetcodeClient, codeforces: CodeforcesClient, github: GitHubClient) -> None:
    data = config.data_service
    factory = TTLKeyValueStoreFactory(config.ttl_key_value_store.sweep_intervals)
    service = DataService(
        leetcode_client=leetcode,
        codeforces_client=codeforces,
        github_client=github,
        ttl_key_value_store_factory=factory,
        cache_impl=data.cache_impl,
        leetcode_accounts=[PlatformAccount(**account.model_dump()) for account in data.leetcode_accounts],
        codeforces_accounts=[PlatformAccount(**account.model_dump()) for account in data.codeforces_accounts],
        github_accounts=[PlatformAccount(**account.model_dump()) for account in data.github_accounts],
        resume_link=data.resume_link,
        profile_photo_links=data.profile_photo_links,
        leetcode_profile_url_format=data.leetcode_profile_url_format,
        codeforces_profile_url_format=data.codeforces_profile_url_format,
        max_workers=data.max_workers,
    )
    try:
        assert service.get_leetcode_details()[0].total_solved > 0
        assert service.get_codeforces_details()[0].contests_count > 0
        assert [details.username for details in service.get_github_details()] == [account.username for account in data.github_accounts]
        professional = service.get_professional_details()
        assert professional.leetcode_links[0].startswith("https://leetcode.com/u/")
        assert len(professional.github_links) == len(data.github_accounts)
        store = factory.get_ttl_key_value_store(data.cache_impl)
        assert store.get(f"data:github:{data.github_accounts[0].username}") is not None
    finally:
        service.close()
        factory.close_all()
