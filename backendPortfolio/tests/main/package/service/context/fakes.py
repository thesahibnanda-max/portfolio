from datetime import timedelta

from main.package.service.context import (
    CodeforcesContextProvider,
    ContextAggregator,
    GitHubContextProvider,
    LeetcodeContextProvider,
    PersonalityContextProvider,
    ProfileContextProvider,
    SiteContextProvider,
)
from main.package.service.data import DataService
from main.package.static import StaticLoader
from main.package.ttl_key_value_store import TTLKeyValueStoreFactory, TTLKeyValueStoreImpl
from tests.support import ResponseSpec
from tests.main.package.service.data.fakes import (
    CODEFORCES_ACCOUNTS,
    GITHUB_ACCOUNTS,
    LEETCODE_ACCOUNTS,
    codeforces_client,
    codeforces_transport,
    github_client,
    github_transport,
    leetcode_client,
    leetcode_transport,
)


class Upstream:
    def __init__(
        self,
        *,
        leetcode_payload: dict | None = None,
        codeforces_payload: dict | None = None,
        github_routes: dict[str, ResponseSpec] | None = None,
    ) -> None:
        self.leetcode = leetcode_transport(leetcode_payload)
        self.codeforces = codeforces_transport(codeforces_payload)
        self.github = github_transport(github_routes)

    def request_count(self) -> int:
        return len(self.leetcode.requests) + len(self.codeforces.requests) + len(self.github.requests)


def data_service(upstream: Upstream, factory: TTLKeyValueStoreFactory) -> DataService:
    return DataService(
        leetcode_client=leetcode_client(upstream.leetcode),
        codeforces_client=codeforces_client(upstream.codeforces),
        github_client=github_client(upstream.github),
        ttl_key_value_store_factory=factory,
        cache_impl=TTLKeyValueStoreImpl.IN_MEMORY,
        leetcode_accounts=LEETCODE_ACCOUNTS,
        codeforces_accounts=CODEFORCES_ACCOUNTS,
        github_accounts=GITHUB_ACCOUNTS,
        profile_photo_links=(),
        leetcode_profile_url_format="{base_url}/u/{username}/",
        codeforces_profile_url_format="{base_url}/profile/{username}",
        max_workers=4,
    )


def ttl_factory() -> TTLKeyValueStoreFactory:
    return TTLKeyValueStoreFactory({TTLKeyValueStoreImpl.IN_MEMORY: timedelta(minutes=20)})


def aggregator(service: DataService, *, max_repositories: int = 5, max_rating_changes: int = 5) -> ContextAggregator:
    loader = StaticLoader()
    return ContextAggregator(
        providers=[
            ProfileContextProvider(loader, service),
            PersonalityContextProvider(loader, service),
            GitHubContextProvider(service, max_repositories=max_repositories),
            LeetcodeContextProvider(service),
            CodeforcesContextProvider(service, max_rating_changes=max_rating_changes),
            SiteContextProvider(loader),
        ],
        max_workers=5,
    )
