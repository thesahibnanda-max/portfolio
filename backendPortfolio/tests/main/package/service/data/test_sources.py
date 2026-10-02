from datetime import UTC, datetime

import pytest

from main.package.service.data import (
    CodeforcesDetails,
    CodeforcesSource,
    DataSourceResponseError,
    DataSourceUnavailableError,
    DetailsSource,
    GitHubDetails,
    GitHubSource,
    LeetcodeDetails,
    LeetcodeSource,
)
from tests.main.package.service.data.fakes import (
    codeforces_client,
    codeforces_transport,
    github_client,
    github_transport,
    leetcode_client,
    leetcode_transport,
)
from tests.support import RecordingTransport, ResponseSpec


def test_sources_implement_the_strategy_interface() -> None:
    sources = [
        LeetcodeSource(leetcode_client(leetcode_transport())),
        CodeforcesSource(codeforces_client(codeforces_transport())),
        GitHubSource(github_client(github_transport())),
    ]

    assert all(isinstance(source, DetailsSource) for source in sources)
    assert [source.platform for source in sources] == ["leetcode", "codeforces", "github"]
    assert [source.details_type for source in sources] == [LeetcodeDetails, CodeforcesDetails, GitHubDetails]


def test_leetcode_mapping() -> None:
    details = LeetcodeSource(leetcode_client(leetcode_transport())).fetch("imsahibnanda")

    assert (details.username, details.ranking, details.reputation) == ("imsahibnanda", 41000, 12)
    assert (details.total_solved, details.easy_solved, details.medium_solved, details.hard_solved) == (674, 222, 356, 96)
    assert details.badges == ("50 Days Badge",)
    assert details.language_problems_solved == {"Python3": 400}
    assert details.advanced_tags_solved == {"Dynamic Programming": 80}
    assert details.intermediate_tags_solved == {"Hash Table": 120}
    assert details.fundamental_tags_solved == {"Array": 300}
    assert (details.contest_rating, details.contest_global_ranking) == (1650.5, 120000)
    assert (details.current_streak, details.total_active_days) == (9, 51)
    assert details.about_me == "Backend engineer"
    assert details.websites == ("https://sahib.dev",)
    assert (details.twitter_url, details.linkedin_url, details.country_name) == ("https://x.com/thesahibnanda", "https://linkedin.com/in/sahib", "India")


def test_leetcode_mapping_tolerates_missing_sections() -> None:
    payload = {"data": {"matchedUser": {}}}
    details = LeetcodeSource(leetcode_client(leetcode_transport(payload))).fetch("someone")

    assert details.username == "someone"
    assert (details.ranking, details.total_solved, details.contest_rating, details.current_streak) == (None, None, None, None)
    assert (details.badges, details.websites, details.language_problems_solved, details.advanced_tags_solved) == ((), (), {}, {})


@pytest.mark.parametrize("payload", [{"data": {"matchedUser": None}}, {"data": None}, {}])
def test_leetcode_without_profile_raises_response_error(payload: dict) -> None:
    with pytest.raises(DataSourceResponseError) as error:
        LeetcodeSource(leetcode_client(leetcode_transport(payload))).fetch("ghost")

    assert (error.value.platform, error.value.account) == ("leetcode", "ghost")


def test_leetcode_client_errors_become_unavailable() -> None:
    with pytest.raises(DataSourceUnavailableError) as error:
        LeetcodeSource(leetcode_client(RecordingTransport(ResponseSpec(503, text="down")))).fetch("imsahibnanda")

    assert (error.value.platform, error.value.account) == ("leetcode", "imsahibnanda")
    assert error.value.__cause__ is not None


def test_codeforces_mapping() -> None:
    details = CodeforcesSource(codeforces_client(codeforces_transport())).fetch("shisukenohara")

    assert (details.handle, details.current_rating, details.max_rating, details.contests_count) == ("shisukenohara", 1832, 1987, 3)
    assert details.rating_history[0].contest_time == datetime.fromtimestamp(1700000000, UTC)
    assert details.rating_history[2].contest_time is None
    assert [transition.new_rating for transition in details.rating_history] == [1400, 1987, 1832]


def test_codeforces_without_contests() -> None:
    details = CodeforcesSource(codeforces_client(codeforces_transport({"status": "OK", "result": []}))).fetch("newbie")

    assert (details.current_rating, details.max_rating, details.contests_count, details.rating_history) == (None, None, 0, ())


def test_codeforces_ratings_ignore_missing_values() -> None:
    payload = {"status": "OK", "result": [{"contestName": "R", "newRating": None}]}
    details = CodeforcesSource(codeforces_client(codeforces_transport(payload))).fetch("h")

    assert (details.current_rating, details.max_rating, details.contests_count) == (None, None, 1)


def test_codeforces_client_errors_become_unavailable() -> None:
    with pytest.raises(DataSourceUnavailableError) as error:
        CodeforcesSource(codeforces_client(codeforces_transport({"status": "FAILED", "comment": "no"}))).fetch("h")

    assert error.value.platform == "codeforces"


def test_github_mapping() -> None:
    transport = github_transport()
    details = GitHubSource(github_client(transport)).fetch("thesahibnanda-max")

    assert (details.username, details.public_repos, details.followers, details.html_url) == (
        "thesahibnanda-max",
        15,
        10,
        "https://github.com/thesahibnanda-max",
    )
    assert [(repo.name, repo.stars, repo.language) for repo in details.repositories] == [("relay", 40, "Go"), ("helios", 12, "Go")]
    assert details.repositories[0].updated_at == datetime(2026, 9, 1, tzinfo=UTC)
    assert [request.url.path for request in transport.requests] == ["/users/thesahibnanda-max", "/users/thesahibnanda-max/repos"]


def test_github_with_no_repositories() -> None:
    assert GitHubSource(github_client(github_transport())).fetch("thesahibnanda").repositories == ()


def test_github_client_errors_become_unavailable() -> None:
    with pytest.raises(DataSourceUnavailableError) as error:
        GitHubSource(github_client(github_transport())).fetch("unknown-user")

    assert (error.value.platform, error.value.account) == ("github", "unknown-user")
