import threading
from collections.abc import Iterator

import pytest

from main.package.ai.common import ContextType
from main.package.service.context import (
    CodeforcesContextProvider,
    ContextAggregator,
    ContextError,
    ContextProvider,
    GitHubContextProvider,
    InvalidContextSettingError,
    LeetcodeContextProvider,
    PersonalityContextProvider,
    ProfileContextProvider,
)
from main.package.service.data import DataService, DataSourceUnavailableError
from main.package.static import StaticLoader
from main.package.ttl_key_value_store import TTLKeyValueStoreFactory
from tests.main.package.service.context.fakes import Upstream, aggregator, data_service, ttl_factory
from tests.support import ResponseSpec


class StaticProvider(ContextProvider):
    def __init__(self, context_type: ContextType, text: str, barrier: threading.Barrier | None = None) -> None:
        self._context_type = context_type
        self._text = text
        self._barrier = barrier

    @property
    def context_type(self) -> ContextType:
        return self._context_type

    def render(self) -> str:
        if self._barrier is not None:
            self._barrier.wait()
        return self._text


SPARSE_LEETCODE = {"data": {"matchedUser": {"username": "imsahibnanda"}}}
REAL_TYPES = [context for context in ContextType if context is not ContextType.NONE]


@pytest.fixture
def factory() -> Iterator[TTLKeyValueStoreFactory]:
    instance = ttl_factory()
    yield instance
    instance.close_all()


@pytest.fixture
def upstream() -> Upstream:
    return Upstream()


@pytest.fixture
def service(upstream: Upstream, factory: TTLKeyValueStoreFactory) -> Iterator[DataService]:
    instance = data_service(upstream, factory)
    yield instance
    instance.close()


def _render(provider: ContextProvider) -> str:
    return provider.render().strip()


def test_profile_context(service: DataService) -> None:
    text = _render(ProfileContextProvider(StaticLoader(), service))
    lines = text.splitlines()

    assert lines[:4] == ["PROFILE:", "Name: Sahib Nanda", "Email: sabbykabby12@gmail.com", "Country: India"]
    assert "LinkedIn: https://linkedin.com/in/sahib" in lines
    assert "Twitter: https://x.com/thesahibnanda" in lines
    assert "Websites: https://sahib.dev" in lines
    assert "GitHub usernames: thesahibnanda-max, thesahibnanda" in lines
    assert "LeetCode usernames: imsahibnanda" in lines
    assert "Codeforces usernames: shisukenohara" in lines
    assert "Skills:" in lines and any(line.startswith("- Backend: ") for line in lines)
    assert lines[lines.index("Experience:") + 1].startswith("- Software Development Engineer (SDE) at CheQ")
    assert "Education:" in lines and "Projects:" in lines
    assert any(line.startswith("- Relay - Multi-Agent Collaboration for AI Coding CLIs (2026, https://relay-sahib-nanda.vercel.app): ") for line in lines)
    assert "" not in lines


def test_profile_context_skips_blank_leetcode_fields(factory: TTLKeyValueStoreFactory) -> None:
    upstream = Upstream(leetcode_payload=SPARSE_LEETCODE)
    with data_service(upstream, factory) as service:
        text = _render(ProfileContextProvider(StaticLoader(), service))

    assert all(not line.startswith(prefix) for line in text.splitlines() for prefix in ("Country:", "LinkedIn:", "Twitter:", "Websites:"))


def test_personality_context(service: DataService) -> None:
    lines = _render(PersonalityContextProvider(StaticLoader(), service)).splitlines()

    assert lines[0] == "PERSONALITY:"
    assert lines[1] == "About me: Backend engineer"
    assert lines[2] == "Nationality: Indian, Gender: Male, Height: 6ft (183cm)"
    assert lines[3].startswith("Appearance: Athletic build, Masculine, Black Naturally wavy hair, Black eyes")
    assert "Sports: football (team: FC Barcelona, player: Lionel Messi); cricket (team: India, player: Virat Kohli)" in lines
    assert "Lifestyle: fitness-focused, sports enthusiast, technology enthusiast, continuous learner" in lines
    assert lines[-1].startswith("Languages: English (Professional)")
    assert "" not in lines


def test_personality_context_without_about_me(factory: TTLKeyValueStoreFactory) -> None:
    upstream = Upstream(leetcode_payload=SPARSE_LEETCODE)
    with data_service(upstream, factory) as service:
        lines = _render(PersonalityContextProvider(StaticLoader(), service)).splitlines()

    assert lines[1].startswith("Nationality:")


def test_github_context_lists_top_repositories_by_stars(service: DataService) -> None:
    text = _render(GitHubContextProvider(service, max_repositories=1))

    assert text.splitlines() == [
        "GITHUB (thesahibnanda-max): 15 public repos, 10 followers, 2 following. Bio: Builder",
        "Top repos: relay (Go) - 40 stars: relay repo",
        "GITHUB (thesahibnanda): 12 public repos, 10 followers, 2 following. Bio: Builder",
    ]


def test_github_context_shows_all_repositories_within_the_limit(service: DataService) -> None:
    text = _render(GitHubContextProvider(service, max_repositories=5))

    assert "Top repos: relay (Go) - 40 stars: relay repo; helios (Go) - 12 stars: helios repo" in text.splitlines()


def test_leetcode_context(service: DataService) -> None:
    assert _render(LeetcodeContextProvider(service)).splitlines() == [
        "LEETCODE (imsahibnanda): rank 41000, 674 solved (222 easy, 356 medium, 96 hard), contest rating 1650.5, current streak 9 days",
        "Badges: 50 Days Badge",
        "Languages used: Python3 400",
    ]


def test_codeforces_context_shows_recent_changes(service: DataService) -> None:
    assert _render(CodeforcesContextProvider(service, max_rating_changes=2)).splitlines() == [
        "CODEFORCES (shisukenohara): current rating 1832, max rating 1987, 3 rated contests",
        "Recent contests: Round 2 (rank 50): 1400->1987; Round 3 (rank 3000): 1987->1832",
    ]


def test_codeforces_context_without_contests(factory: TTLKeyValueStoreFactory) -> None:
    with data_service(Upstream(codeforces_payload={"status": "OK", "result": []}), factory) as service:
        assert _render(CodeforcesContextProvider(service, max_rating_changes=5)) == "CODEFORCES (shisukenohara): 0 rated contests"


def test_leetcode_context_with_sparse_data(factory: TTLKeyValueStoreFactory) -> None:
    upstream = Upstream(leetcode_payload=SPARSE_LEETCODE)
    with data_service(upstream, factory) as service:
        assert _render(LeetcodeContextProvider(service)) == "LEETCODE (imsahibnanda):"


def test_github_context_with_sparse_data(factory: TTLKeyValueStoreFactory) -> None:
    upstream = Upstream(
        github_routes={
            "/users/thesahibnanda-max": ResponseSpec(json={"login": "thesahibnanda-max"}),
            "/users/thesahibnanda-max/repos": ResponseSpec(json=[{"name": "bare"}]),
            "/users/thesahibnanda": ResponseSpec(json={"login": "thesahibnanda"}),
            "/users/thesahibnanda/repos": ResponseSpec(json=[]),
        }
    )
    with data_service(upstream, factory) as service:
        assert _render(GitHubContextProvider(service, max_repositories=5)).splitlines() == [
            "GITHUB (thesahibnanda-max):",
            "Top repos: bare - 0 stars",
            "GITHUB (thesahibnanda):",
        ]


def test_providers_report_their_types(service: DataService) -> None:
    loader = StaticLoader()
    providers = [
        ProfileContextProvider(loader, service),
        PersonalityContextProvider(loader, service),
        GitHubContextProvider(service, max_repositories=1),
        LeetcodeContextProvider(service),
        CodeforcesContextProvider(service, max_rating_changes=1),
    ]

    assert [provider.context_type for provider in providers] == [
        ContextType.PROFILE,
        ContextType.PERSONALITY,
        ContextType.GITHUB,
        ContextType.LEETCODE,
        ContextType.CODEFORCES,
    ]


@pytest.mark.parametrize("value", [0, -1, True, "5"])
def test_provider_limits_must_be_positive(service: DataService, value: object) -> None:
    with pytest.raises(InvalidContextSettingError):
        GitHubContextProvider(service, max_repositories=value)
    with pytest.raises(InvalidContextSettingError):
        CodeforcesContextProvider(service, max_rating_changes=value)


def test_provider_dependencies_must_have_the_right_types(service: DataService) -> None:
    with pytest.raises(InvalidContextSettingError, match="static_loader"):
        ProfileContextProvider(None, service)
    with pytest.raises(InvalidContextSettingError, match="data_service"):
        PersonalityContextProvider(StaticLoader(), None)
    with pytest.raises(InvalidContextSettingError, match="data_service"):
        LeetcodeContextProvider("service")


def test_aggregate_joins_blocks_in_canonical_order(service: DataService) -> None:
    with aggregator(service) as context:
        text = context.aggregate([ContextType.PERSONALITY, ContextType.CODEFORCES, ContextType.PROFILE, ContextType.PROFILE])

    headers = [line for line in text.splitlines() if line.startswith(("PROFILE:", "CODEFORCES (", "PERSONALITY:"))]
    assert headers == ["PROFILE:", "CODEFORCES (shisukenohara): current rating 1832, max rating 1987, 3 rated contests", "PERSONALITY:"]
    assert "\n\nCODEFORCES (" in text and "\n\nPERSONALITY:" in text


@pytest.mark.parametrize("contexts", [[], [ContextType.NONE], (ContextType.NONE, ContextType.NONE)])
def test_aggregate_without_real_contexts_is_empty(service: DataService, upstream: Upstream, contexts: list) -> None:
    with aggregator(service) as context:
        assert context.aggregate(contexts) == ""

    assert upstream.request_count() == 0


def test_aggregate_only_fetches_what_is_requested(service: DataService, upstream: Upstream) -> None:
    with aggregator(service) as context:
        context.aggregate([ContextType.CODEFORCES])

    assert (len(upstream.codeforces.requests), len(upstream.github.requests), len(upstream.leetcode.requests)) == (1, 0, 0)


def test_aggregate_skips_blank_blocks() -> None:
    providers = [StaticProvider(context, "" if context is ContextType.GITHUB else context.name) for context in REAL_TYPES]
    with ContextAggregator(providers=providers, max_workers=2) as context:
        assert context.aggregate(REAL_TYPES) == "PROFILE\n\nLEETCODE\n\nCODEFORCES\n\nPERSONALITY"


def test_aggregate_renders_in_parallel() -> None:
    barrier = threading.Barrier(len(REAL_TYPES), timeout=5)
    providers = [StaticProvider(context, context.name, barrier) for context in REAL_TYPES]
    with ContextAggregator(providers=providers, max_workers=len(REAL_TYPES)) as context:
        assert context.aggregate(REAL_TYPES).count("\n\n") == len(REAL_TYPES) - 1


def test_data_errors_pass_through(factory: TTLKeyValueStoreFactory) -> None:
    upstream = Upstream(github_routes={})
    with data_service(upstream, factory) as service, aggregator(service) as context:
        with pytest.raises(DataSourceUnavailableError):
            context.aggregate([ContextType.GITHUB])


@pytest.mark.parametrize("contexts", ["GITHUB", ["GITHUB"], [ContextType.GITHUB, 5]])
def test_aggregate_rejects_non_context_types(contexts: object) -> None:
    with ContextAggregator(providers=[StaticProvider(context, "x") for context in REAL_TYPES], max_workers=1) as context:
        with pytest.raises(InvalidContextSettingError):
            context.aggregate(contexts)


@pytest.mark.parametrize(
    "providers",
    [
        [StaticProvider(context, "x") for context in REAL_TYPES[:-1]],
        [*(StaticProvider(context, "x") for context in REAL_TYPES), StaticProvider(ContextType.GITHUB, "again")],
        [*(StaticProvider(context, "x") for context in REAL_TYPES), StaticProvider(ContextType.NONE, "none")],
        "providers",
        None,
        [*(StaticProvider(context, "x") for context in REAL_TYPES[:-1]), "not a provider"],
    ],
)
def test_aggregator_requires_exactly_one_provider_per_type(providers: object) -> None:
    with pytest.raises(InvalidContextSettingError):
        ContextAggregator(providers=providers, max_workers=1)


@pytest.mark.parametrize("max_workers", [0, True, "2"])
def test_aggregator_max_workers_must_be_positive(max_workers: object) -> None:
    with pytest.raises(InvalidContextSettingError):
        ContextAggregator(providers=[StaticProvider(context, "x") for context in REAL_TYPES], max_workers=max_workers)


def test_errors_share_the_base() -> None:
    assert issubclass(InvalidContextSettingError, ContextError)
