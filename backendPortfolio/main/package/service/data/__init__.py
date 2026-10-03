"""
The portfolio data service: the owner's LeetCode, Codeforces and GitHub data,
fetched for every configured account, summarised, and cached in memory with a
time-to-live per account.

Exports:
    DataService: the single entry point (a facade) for callers.
    DetailsSource, LeetcodeSource, CodeforcesSource, GitHubSource: one
    strategy per platform.
    CachedDetailsSource: the caching decorator around any source.
    LeetcodeDetails, CodeforcesDetails (with CodeforcesRatingTransition),
    GitHubDetails (with GitHubRepositorySummary), ProfessionalDetails and
    PlatformAccount: the DTOs.
    DataServiceError and its subclasses: the errors described under Errors.

Design:
    Strategy: each DetailsSource knows exactly one platform's API. fetch(account)
    calls its client and maps the raw response to that platform's summary
    DTO, turning its client's errors into DataSourceUnavailableError. A new
    platform is a new source; nothing else changes.
    Decorator: CachedDetailsSource wraps any source with the same interface
    and adds caching, so caching is written once instead of in every source.
    Factory: the cache backend comes from
    TTLKeyValueStoreFactory.get_ttl_key_value_store(cache_impl). Values are
    stored as JSON strings, so switching cache_impl to a future Redis or
    Memcached implementation needs no change here.
    Facade: DataService hides the sources, the caches and the thread pool.
    Left out on purpose: Command (no undo, queueing or replay), a Template
    Method base class (composition is simpler), Observer (nothing reacts to
    changes), stale-while-revalidate and partial results (not needed).

Caching (CachedDetailsSource):
    Key: "data:<platform>:<account>", for example "data:github:thesahibnanda".
    A hit reads the stored JSON back into the DTO, so every caller gets its own
    copy. A miss calls the source and stores the DTO as JSON until now plus
    that account's cache_ttl. Defaults from config: LeetCode imsahibnanda 1h,
    Codeforces shisukenohara 80m, GitHub thesahibnanda-max 45m and
    thesahibnanda 120m.
    Single-flight: concurrent misses on the same key wait on one lock per key,
    so only one upstream call is made and the others read its result.
    Failures are never cached; the next call simply tries again.

Construction:
    DataService(
        *,
        leetcode_client, codeforces_client, github_client,
        ttl_key_value_store_factory, cache_impl,
        leetcode_accounts, codeforces_accounts, github_accounts,
        profile_photo_links,
        leetcode_profile_url_format, codeforces_profile_url_format,
        max_workers,
    )
    The clients are the ones in main.package.clients. The factory and
    cache_impl choose the cache backend. Each *_accounts is a non-empty
    sequence of PlatformAccount(username, cache_ttl) with unique usernames,
    in display order; the first LeetCode account is the primary one.
    profile_photo_links are http(s) URLs. The profile URL
    formats are str.format templates using {base_url} and {username}, for
    example "{base_url}/u/{username}/". max_workers sizes the thread pool.
    All of these come from main.config.AppConfig.data_service. A bad
    setting, or a cache_impl the factory does not offer, raises
    InvalidDataServiceSettingError.

Methods:
    get_leetcode_details(), get_codeforces_details(), get_github_details():
    a tuple with one DTO per configured account, in config order. Accounts
    are fetched in parallel on the service's thread pool, which runs truly in
    parallel on the free-threaded Python 3.14t build.
    get_professional_details() -> ProfessionalDetails: profile links built
    from the URL formats and the clients' base URLs, GitHub profile links,
    the photo links, and the websites and Twitter link from the
    primary LeetCode profile. It reuses the same cache entries.
    leetcode_accounts, codeforces_accounts, github_accounts: the configured
    accounts, in config order, as read-only properties.
    close() shuts the thread pool down; the service is also a context
    manager. The profile and personality JSON come from
    main.package.static.StaticLoader, not from here.

DTOs:
    Frozen pydantic models. LeetcodeDetails also carries about_me, websites,
    twitter_url, linkedin_url and country_name from the LeetCode profile, so
    other views need no second LeetCode call. CodeforcesDetails gives the
    current and maximum rating and every rating change (contests_count 0
    and no ratings when the handle has never competed). GitHubDetails holds
    the first page of repositories, most recently updated first.

Errors (all in exceptions.py, all subclasses of DataServiceError):
    InvalidDataServiceSettingError: a constructor setting is invalid, or an
    account has no cache TTL.
    DataSourceUnavailableError: a platform call failed (network, HTTP status,
    rate limit, bad response); platform and account name it and the
    client's error is chained as __cause__.
    DataSourceResponseError: the platform answered without the data needed,
    for example LeetCode returning no profile; it has platform and account.
    If any account fails, the whole call fails with its error. Accounts that
    succeeded are already cached, so a retry only fetches the failed one.

Thread safety:
    One DataService can be shared by every thread. Sources hold only their
    client, CachedDetailsSource guards its lock map with a lock, and the
    in-memory store is thread-safe.

Example:
    with DataService(**settings) as data:
        rating = data.get_codeforces_details()[0].current_rating
"""

from .cached_source import CachedDetailsSource
from .data_service import DataService
from .dto import (
    CodeforcesDetails,
    CodeforcesRatingTransition,
    GitHubDetails,
    GitHubRepositorySummary,
    LeetcodeDetails,
    PlatformAccount,
    ProfessionalDetails,
)
from .exceptions import (
    DataServiceError,
    DataSourceResponseError,
    DataSourceUnavailableError,
    InvalidDataServiceSettingError,
)
from .sources import CodeforcesSource, DetailsSource, GitHubSource, LeetcodeSource

__all__ = [
    "DataService",
    "DetailsSource",
    "LeetcodeSource",
    "CodeforcesSource",
    "GitHubSource",
    "CachedDetailsSource",
    "LeetcodeDetails",
    "CodeforcesDetails",
    "CodeforcesRatingTransition",
    "GitHubDetails",
    "GitHubRepositorySummary",
    "ProfessionalDetails",
    "PlatformAccount",
    "DataServiceError",
    "InvalidDataServiceSettingError",
    "DataSourceUnavailableError",
    "DataSourceResponseError",
]
