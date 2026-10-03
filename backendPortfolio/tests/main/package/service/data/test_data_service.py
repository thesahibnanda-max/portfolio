from collections.abc import Iterator
from datetime import timedelta
from functools import partial

import httpx
import pytest

from main.config import AppConfig
from main.package.clients.codeforces import CodeforcesClient
from main.package.clients.github import GitHubClient
from main.package.clients.leetcode import LeetcodeClient
from main.package.service.data import (
    DataService,
    DataServiceError,
    DataSourceResponseError,
    DataSourceUnavailableError,
    InvalidDataServiceSettingError,
    PlatformAccount,
    ProfessionalDetails,
)
from main.package.ttl_key_value_store import TTLKeyValueStoreFactory, TTLKeyValueStoreImpl
from tests.main.package.service.data.fakes import (
    CODEFORCES_ACCOUNTS,
    GITHUB_ACCOUNTS,
    GITHUB_ROUTES,
    LEETCODE_ACCOUNTS,
    BarrierTransport,
    codeforces_client,
    codeforces_transport,
    github_client,
    github_transport,
    leetcode_client,
    leetcode_transport,
)
from tests.support import ConcurrentRunner, RecordingTransport, ResponseSpec

PHOTOS = ("https://storage.test/1.png", "https://storage.test/2.png")


class RecordingFactory(TTLKeyValueStoreFactory):
    def __init__(self) -> None:
        super().__init__({TTLKeyValueStoreImpl.IN_MEMORY: timedelta(minutes=20)})
        self.requested: list[object] = []

    def get_ttl_key_value_store(self, impl):
        self.requested.append(impl)
        return super().get_ttl_key_value_store(impl)


class Upstream:
    def __init__(
        self,
        leetcode: httpx.BaseTransport | None = None,
        codeforces: httpx.BaseTransport | None = None,
        github: httpx.BaseTransport | None = None,
    ) -> None:
        self.leetcode = leetcode or leetcode_transport()
        self.codeforces = codeforces or codeforces_transport()
        self.github = github or github_transport()


@pytest.fixture
def factory() -> Iterator[RecordingFactory]:
    instance = RecordingFactory()
    yield instance
    instance.close_all()


def _settings(upstream: Upstream, factory: TTLKeyValueStoreFactory, **overrides: object) -> dict:
    return {
        "leetcode_client": leetcode_client(upstream.leetcode),
        "codeforces_client": codeforces_client(upstream.codeforces),
        "github_client": github_client(upstream.github),
        "ttl_key_value_store_factory": factory,
        "cache_impl": TTLKeyValueStoreImpl.IN_MEMORY,
        "leetcode_accounts": LEETCODE_ACCOUNTS,
        "codeforces_accounts": CODEFORCES_ACCOUNTS,
        "github_accounts": GITHUB_ACCOUNTS,
        "profile_photo_links": PHOTOS,
        "leetcode_profile_url_format": "{base_url}/u/{username}/",
        "codeforces_profile_url_format": "{base_url}/profile/{username}",
        "max_workers": 8,
    } | overrides


def _service(upstream: Upstream, factory: TTLKeyValueStoreFactory, **overrides: object) -> DataService:
    return DataService(**_settings(upstream, factory, **overrides))


def _read_everything(service: DataService) -> int:
    service.get_leetcode_details()
    service.get_codeforces_details()
    service.get_github_details()
    service.get_professional_details()
    return 1


def test_cache_backend_comes_from_the_factory(factory: RecordingFactory) -> None:
    with _service(Upstream(), factory):
        assert factory.requested == [TTLKeyValueStoreImpl.IN_MEMORY]


def test_unknown_cache_impl_is_rejected(factory: RecordingFactory) -> None:
    with pytest.raises(InvalidDataServiceSettingError, match="cache_impl"):
        _service(Upstream(), factory, cache_impl="redis")


def test_details_come_back_in_config_order(factory: RecordingFactory) -> None:
    with _service(Upstream(), factory) as service:
        assert [details.username for details in service.get_github_details()] == ["thesahibnanda-max", "thesahibnanda"]
        assert service.get_leetcode_details()[0].total_solved == 674
        assert service.get_codeforces_details()[0].current_rating == 1832


def test_second_calls_are_served_from_cache(factory: RecordingFactory) -> None:
    upstream = Upstream()
    with _service(upstream, factory) as service:
        _read_everything(service)
        counts = (len(upstream.leetcode.requests), len(upstream.codeforces.requests), len(upstream.github.requests))
        _read_everything(service)

    assert counts == (1, 1, 4)
    assert (len(upstream.leetcode.requests), len(upstream.codeforces.requests), len(upstream.github.requests)) == counts


def test_cache_entries_use_the_configured_ttls(factory: RecordingFactory) -> None:
    with _service(Upstream(), factory) as service:
        _read_everything(service)
    store = factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY)

    assert sorted(store._entries) == [
        "data:codeforces:shisukenohara",
        "data:github:thesahibnanda",
        "data:github:thesahibnanda-max",
        "data:leetcode:imsahibnanda",
    ]
    lifetimes = {key: expires_at for key, (_, expires_at) in store._entries.items()}
    assert lifetimes["data:github:thesahibnanda"] - lifetimes["data:github:thesahibnanda-max"] == pytest.approx(
        timedelta(minutes=75), abs=timedelta(seconds=5)
    )


def test_accounts_are_fetched_in_parallel(factory: RecordingFactory) -> None:
    transport = BarrierTransport(len(GITHUB_ACCOUNTS), GITHUB_ROUTES)
    with _service(Upstream(github=transport), factory) as service:
        assert len(service.get_github_details()) == 2


def test_one_failing_account_fails_the_call_and_keeps_others_cached(factory: RecordingFactory) -> None:
    routes = dict(GITHUB_ROUTES) | {"/users/thesahibnanda": ResponseSpec(500, text="down")}
    transport = RecordingTransport(routes=routes)
    with _service(Upstream(github=transport), factory) as service:
        with pytest.raises(DataSourceUnavailableError) as error:
            service.get_github_details()
        requests_after_failure = len(transport.requests)
        with pytest.raises(DataSourceUnavailableError):
            service.get_github_details()

    assert (error.value.platform, error.value.account) == ("github", "thesahibnanda")
    assert len(transport.requests) == requests_after_failure + 1


def test_response_errors_pass_through(factory: RecordingFactory) -> None:
    with _service(Upstream(leetcode=leetcode_transport({"data": {"matchedUser": None}})), factory) as service:
        with pytest.raises(DataSourceResponseError):
            service.get_leetcode_details()


def test_professional_details(factory: RecordingFactory) -> None:
    with _service(Upstream(), factory) as service:
        details = service.get_professional_details()

    assert details == ProfessionalDetails(
        leetcode_links=("https://leetcode.com/u/imsahibnanda/",),
        codeforces_links=("https://codeforces.com/profile/shisukenohara",),
        github_links=("https://github.com/thesahibnanda-max", "https://github.com/thesahibnanda"),
        profile_photo_links=PHOTOS,
        websites=("https://sahib.dev",),
        twitter_url="https://x.com/thesahibnanda",
    )


def test_professional_details_skip_missing_github_links(factory: RecordingFactory) -> None:
    user = {"login": "thesahibnanda", "html_url": None}
    routes = dict(GITHUB_ROUTES) | {"/users/thesahibnanda": ResponseSpec(json=user)}
    with _service(Upstream(github=RecordingTransport(routes=routes)), factory) as service:
        assert service.get_professional_details().github_links == ("https://github.com/thesahibnanda-max",)


def test_professional_details_use_the_primary_leetcode_account(factory: RecordingFactory) -> None:
    accounts = (*LEETCODE_ACCOUNTS, PlatformAccount(username="second", cache_ttl=timedelta(hours=1)))
    upstream = Upstream()
    with _service(upstream, factory, leetcode_accounts=accounts) as service:
        details = service.get_professional_details()

    assert details.leetcode_links == ("https://leetcode.com/u/imsahibnanda/", "https://leetcode.com/u/second/")
    assert len(upstream.leetcode.requests) == 1


def test_one_service_is_safe_across_threads(factory: RecordingFactory) -> None:
    upstream = Upstream()
    with _service(upstream, factory) as service:
        runner = ConcurrentRunner(partial(_read_everything, service)).run()

    assert runner.errors == []
    assert (len(upstream.leetcode.requests), len(upstream.codeforces.requests), len(upstream.github.requests)) == (1, 1, 4)


@pytest.mark.parametrize(
    "overrides",
    [
        {"leetcode_client": None},
        {"codeforces_client": "client"},
        {"github_client": 5},
        {"ttl_key_value_store_factory": {}},
        {"leetcode_accounts": ()},
        {"leetcode_accounts": "imsahibnanda"},
        {"codeforces_accounts": ({"username": "x", "cache_ttl": 1},)},
        {"github_accounts": (GITHUB_ACCOUNTS[0], GITHUB_ACCOUNTS[0])},
        {"profile_photo_links": "https://x.test/1.png"},
        {"profile_photo_links": ("ftp://x.test/1.png",)},
        {"leetcode_profile_url_format": "{base_url}/u/"},
        {"codeforces_profile_url_format": "{base_url}/{username}/{other}"},
        {"codeforces_profile_url_format": "{base_url}/{username}/{0}"},
        {"leetcode_profile_url_format": None},
        {"max_workers": 0},
        {"max_workers": True},
    ],
)
def test_invalid_settings_are_rejected(factory: RecordingFactory, overrides: dict) -> None:
    with pytest.raises(InvalidDataServiceSettingError):
        _service(Upstream(), factory, **overrides)


def test_settings_are_keyword_only(factory: RecordingFactory) -> None:
    with pytest.raises(TypeError):
        DataService(*_settings(Upstream(), factory).values())


def test_platform_account_validation() -> None:
    with pytest.raises(ValueError):
        PlatformAccount(username="x", cache_ttl=timedelta(0))
    with pytest.raises(ValueError):
        PlatformAccount(username="", cache_ttl=timedelta(hours=1))


def test_close_stops_the_pool(factory: RecordingFactory) -> None:
    service = _service(Upstream(), factory)
    service.close()

    with pytest.raises(RuntimeError):
        service.get_codeforces_details()


@pytest.mark.parametrize("error_type", [InvalidDataServiceSettingError, DataSourceUnavailableError, DataSourceResponseError])
def test_errors_share_the_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, DataServiceError)


def test_builds_from_app_config(config_env: str, factory: RecordingFactory) -> None:
    config = AppConfig.load()
    data = config.data_service
    timeouts = config.http_client.model_dump()
    with (
        LeetcodeClient(base_url=config.leetcode.base_url, transport=leetcode_transport(), **timeouts) as leetcode,
        CodeforcesClient(base_url=config.codeforces.base_url, transport=codeforces_transport(), **timeouts) as codeforces,
        GitHubClient(
            base_url=config.github.base_url,
            api_version=config.github.api_version,
            per_page=config.github.per_page,
            transport=github_transport(),
            **timeouts,
        ) as github,
        DataService(
            leetcode_client=leetcode,
            codeforces_client=codeforces,
            github_client=github,
            ttl_key_value_store_factory=factory,
            cache_impl=data.cache_impl,
            leetcode_accounts=[PlatformAccount(**account.model_dump()) for account in data.leetcode_accounts],
            codeforces_accounts=[PlatformAccount(**account.model_dump()) for account in data.codeforces_accounts],
            github_accounts=[PlatformAccount(**account.model_dump()) for account in data.github_accounts],
            profile_photo_links=data.profile_photo_links,
            leetcode_profile_url_format=data.leetcode_profile_url_format,
            codeforces_profile_url_format=data.codeforces_profile_url_format,
            max_workers=data.max_workers,
        ) as service,
    ):
        assert [details.username for details in service.get_github_details()] == ["thesahibnanda-max", "thesahibnanda"]


def test_accounts_are_exposed_in_config_order(factory: RecordingFactory) -> None:
    with _service(Upstream(), factory) as service:
        assert service.leetcode_accounts == LEETCODE_ACCOUNTS
        assert service.codeforces_accounts == CODEFORCES_ACCOUNTS
        assert service.github_accounts == GITHUB_ACCOUNTS
