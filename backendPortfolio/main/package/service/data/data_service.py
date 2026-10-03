from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from types import TracebackType
from typing import Self
from urllib.parse import urlsplit

from main.package.clients.codeforces import CodeforcesClient
from main.package.clients.github import GitHubClient
from main.package.clients.leetcode import LeetcodeClient
from main.package.service.data.cached_source import CachedDetailsSource
from main.package.service.data.dto import (
    CodeforcesDetails,
    GitHubDetails,
    LeetcodeDetails,
    PlatformAccount,
    ProfessionalDetails,
)
from main.package.service.data.exceptions import InvalidDataServiceSettingError
from main.package.service.data.sources import CodeforcesSource, DetailsSource, GitHubSource, LeetcodeSource
from main.package.ttl_key_value_store import (
    TTLKeyValueStore,
    TTLKeyValueStoreError,
    TTLKeyValueStoreFactory,
    TTLKeyValueStoreImpl,
)

_PROFILE_URL_PLACEHOLDERS = ("{base_url}", "{username}")


class DataService:
    def __init__(
        self,
        *,
        leetcode_client: LeetcodeClient,
        codeforces_client: CodeforcesClient,
        github_client: GitHubClient,
        ttl_key_value_store_factory: TTLKeyValueStoreFactory,
        cache_impl: TTLKeyValueStoreImpl,
        leetcode_accounts: Sequence[PlatformAccount],
        codeforces_accounts: Sequence[PlatformAccount],
        github_accounts: Sequence[PlatformAccount],
        profile_photo_links: Sequence[str],
        leetcode_profile_url_format: str,
        codeforces_profile_url_format: str,
        max_workers: int,
    ) -> None:
        self._require_instance("leetcode_client", leetcode_client, LeetcodeClient)
        self._require_instance("codeforces_client", codeforces_client, CodeforcesClient)
        self._require_instance("github_client", github_client, GitHubClient)
        self._require_instance("ttl_key_value_store_factory", ttl_key_value_store_factory, TTLKeyValueStoreFactory)

        self._leetcode_accounts = self._require_accounts("leetcode_accounts", leetcode_accounts)
        self._codeforces_accounts = self._require_accounts("codeforces_accounts", codeforces_accounts)
        self._github_accounts = self._require_accounts("github_accounts", github_accounts)
        self._profile_photo_links = tuple(
            self._require_http_url("profile_photo_links", link) for link in self._require_sequence("profile_photo_links", profile_photo_links)
        )
        self._leetcode_profile_url_format = self._require_url_format("leetcode_profile_url_format", leetcode_profile_url_format)
        self._codeforces_profile_url_format = self._require_url_format("codeforces_profile_url_format", codeforces_profile_url_format)
        self._leetcode_base_url = leetcode_client.base_url
        self._codeforces_base_url = codeforces_client.base_url

        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise InvalidDataServiceSettingError("max_workers must be a positive int")

        try:
            store = ttl_key_value_store_factory.get_ttl_key_value_store(cache_impl)
        except TTLKeyValueStoreError as error:
            raise InvalidDataServiceSettingError(f"cache_impl {cache_impl!r} is not available") from error

        self._leetcode = self._cached(LeetcodeSource(leetcode_client), store, self._leetcode_accounts)
        self._codeforces = self._cached(CodeforcesSource(codeforces_client), store, self._codeforces_accounts)
        self._github = self._cached(GitHubSource(github_client), store, self._github_accounts)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="data-service")

    @property
    def leetcode_accounts(self) -> tuple[PlatformAccount, ...]:
        return self._leetcode_accounts

    @property
    def codeforces_accounts(self) -> tuple[PlatformAccount, ...]:
        return self._codeforces_accounts

    @property
    def github_accounts(self) -> tuple[PlatformAccount, ...]:
        return self._github_accounts

    def get_leetcode_details(self) -> tuple[LeetcodeDetails, ...]:
        return self._results(self._submit_all(self._leetcode, self._leetcode_accounts))

    def get_codeforces_details(self) -> tuple[CodeforcesDetails, ...]:
        return self._results(self._submit_all(self._codeforces, self._codeforces_accounts))

    def get_github_details(self) -> tuple[GitHubDetails, ...]:
        return self._results(self._submit_all(self._github, self._github_accounts))

    def get_professional_details(self) -> ProfessionalDetails:
        primary_leetcode = self._executor.submit(self._leetcode.fetch, self._leetcode_accounts[0].username)
        github_futures = self._submit_all(self._github, self._github_accounts)
        leetcode = primary_leetcode.result()
        github = self._results(github_futures)

        return ProfessionalDetails(
            leetcode_links=self._profile_links(
                self._leetcode_profile_url_format, self._leetcode_base_url, self._leetcode_accounts
            ),
            codeforces_links=self._profile_links(
                self._codeforces_profile_url_format, self._codeforces_base_url, self._codeforces_accounts
            ),
            github_links=tuple(details.html_url for details in github if details.html_url),
            profile_photo_links=self._profile_photo_links,
            websites=leetcode.websites,
            twitter_url=leetcode.twitter_url,
        )

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _submit_all[T](self, source: DetailsSource[T], accounts: tuple[PlatformAccount, ...]) -> list[Future[T]]:
        return [self._executor.submit(source.fetch, account.username) for account in accounts]

    @staticmethod
    def _results[T](futures: list[Future[T]]) -> tuple[T, ...]:
        return tuple(future.result() for future in futures)

    @staticmethod
    def _cached[T](source: DetailsSource[T], store: TTLKeyValueStore, accounts: tuple[PlatformAccount, ...]) -> CachedDetailsSource[T]:
        return CachedDetailsSource(source, store, {account.username: account.cache_ttl for account in accounts})

    @staticmethod
    def _profile_links(url_format: str, base_url: str, accounts: tuple[PlatformAccount, ...]) -> tuple[str, ...]:
        return tuple(url_format.format(base_url=base_url, username=account.username) for account in accounts)

    @staticmethod
    def _require_instance(name: str, value: object, expected: type) -> None:
        if not isinstance(value, expected):
            raise InvalidDataServiceSettingError(f"{name} must be a {expected.__name__}")

    @staticmethod
    def _require_sequence(name: str, value: Sequence) -> Sequence:
        if isinstance(value, str) or not isinstance(value, Sequence):
            raise InvalidDataServiceSettingError(f"{name} must be a sequence")

        return value

    @classmethod
    def _require_accounts(cls, name: str, accounts: Sequence[PlatformAccount]) -> tuple[PlatformAccount, ...]:
        cls._require_sequence(name, accounts)
        if not accounts or not all(isinstance(account, PlatformAccount) for account in accounts):
            raise InvalidDataServiceSettingError(f"{name} must be a non-empty sequence of PlatformAccount")

        usernames = [account.username for account in accounts]
        if len(set(usernames)) != len(usernames):
            raise InvalidDataServiceSettingError(f"{name} usernames must be unique")

        return tuple(accounts)

    @staticmethod
    def _require_http_url(name: str, value: str) -> str:
        parts = urlsplit(value) if isinstance(value, str) else None
        if parts is None or parts.scheme not in {"http", "https"} or not parts.hostname:
            raise InvalidDataServiceSettingError(f"{name} must contain http or https URLs with a host")

        return value

    @staticmethod
    def _require_url_format(name: str, value: str) -> str:
        if not isinstance(value, str) or not all(placeholder in value for placeholder in _PROFILE_URL_PLACEHOLDERS):
            raise InvalidDataServiceSettingError(f"{name} must contain {{base_url}} and {{username}}")

        try:
            value.format(base_url="https://example.com", username="user")
        except (KeyError, IndexError, ValueError) as error:
            raise InvalidDataServiceSettingError(f"{name} may only use {{base_url}} and {{username}}") from error

        return value
