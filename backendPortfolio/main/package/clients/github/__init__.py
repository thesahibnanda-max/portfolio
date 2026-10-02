"""
Client for the public GitHub REST API, used to fetch user profiles,
repositories and commits.

Exports:
    GitHubClient: the client.
    GitHubUser, GitHubRepository, GitHubCommit and the nested DTOs they are
    built from.
    GitHubClientError and its subclasses: the errors described under Errors.

Construction:
    GitHubClient(
        *,
        base_url,
        api_version,
        per_page,
        connect_timeout,
        read_timeout,
        write_timeout,
        pool_timeout,
        transport=None,
    )
    base_url: http or https URL with a host and no query or fragment, from
    main.config.AppConfig.github.base_url (default "https://api.github.com").
    A trailing slash is removed.
    api_version: non-empty value of the X-GitHub-Api-Version header, from
    main.config.AppConfig.github.api_version (default "2022-11-28").
    per_page: int from 1 to 100 (GitHub's maximum), the page size for list
    calls, from main.config.AppConfig.github.per_page (default 100).
    connect_timeout, read_timeout, write_timeout, pool_timeout: positive
    timedeltas from main.config.AppConfig.http_client (defaults 10s, 60s, 60s,
    10s).
    transport: optional httpx transport, only for tests; it is not a config
    setting.
    Every setting is keyword-only and validated; a bad one raises
    InvalidGitHubClientSettingError.

    Every request sends Accept: application/vnd.github+json and the API
    version header. The client builds and owns one httpx.Client, so call
    close() when done, or use it as a context manager.

Methods:
    base_url: the configured base URL without a trailing slash.
    get_user(username) -> GitHubUser
        GET users/{username}.
    list_user_repositories(username, page=1) -> tuple[GitHubRepository, ...]
        GET users/{username}/repos, most recently updated first
        (sort=updated, direction=desc), per_page results per page.
    list_commits_by_author(owner, repo, author, page=1)
        -> tuple[GitHubCommit, ...]
        GET repos/{owner}/{repo}/commits filtered by author, per_page results
        per page. List entries do not include stats or files; use get_commit
        for those.
    get_commit(owner, repo, commit_sha) -> GitHubCommit
        GET repos/{owner}/{repo}/commits/{commit_sha}, with stats and files.
    Path values are URL-escaped, so a value such as "a/b" cannot change the
    path. page must be an int of at least 1. An empty page past the end is
    an empty tuple, not an error.

DTOs:
    Frozen pydantic models matching GitHub's snake_case JSON; unknown fields
    are ignored; every field is optional; lists are tuples; timestamps are
    timezone-aware datetimes. GitHubRepository.is_private is read from the
    JSON field "private", which is a Python keyword.

Errors (all in exceptions.py, all subclasses of GitHubClientError):
    InvalidGitHubClientSettingError: a constructor setting is invalid.
    InvalidGitHubArgumentError: an argument is empty or whitespace-only, or
    page is not an int of at least 1.
    GitHubRequestError: the request failed before a response arrived
    (connection error, timeout); the httpx error is chained as __cause__.
    GitHubHTTPStatusError: a non-2xx response, for example 404 for an unknown
    user. It has status_code and body (first 500 characters).
    GitHubRateLimitError: a GitHubHTTPStatusError for HTTP 403 or 429 when
    x-ratelimit-remaining is 0 or retry-after is set. Unauthenticated
    callers get 60 requests an hour; the message includes the reset epoch.
    GitHubResponseError: the body is not valid JSON or does not match the DTO
    shape.
    Catch GitHubClientError to handle every failure at once.

Thread safety:
    One instance can be shared across threads on the free-threaded Python
    3.14t build: it holds only immutable settings and an httpx.Client, whose
    connection pool is thread-safe. The list parsers are module-level
    pydantic TypeAdapters, built once and only read.

Dependencies:
    httpx and pydantic. httpx and its dependencies are pure Python and
    pydantic-core ships a cp314t wheel, so the GIL stays disabled.

Example:
    with GitHubClient(
        base_url="https://api.github.com",
        api_version="2022-11-28",
        per_page=100,
        connect_timeout=timedelta(seconds=10),
        read_timeout=timedelta(seconds=60),
        write_timeout=timedelta(seconds=60),
        pool_timeout=timedelta(seconds=10),
    ) as client:
        repos = client.list_user_repositories("octocat")
"""

from .dto import (
    GitHubCommit,
    GitHubCommitDetail,
    GitHubCommitParent,
    GitHubCommitStats,
    GitHubCommitTree,
    GitHubCommitVerification,
    GitHubDiffEntry,
    GitHubGitAuthor,
    GitHubRepository,
    GitHubRepositoryLicense,
    GitHubRepositoryPermissions,
    GitHubUser,
    GitHubUserPlan,
)
from .exceptions import (
    GitHubClientError,
    GitHubHTTPStatusError,
    GitHubRateLimitError,
    GitHubRequestError,
    GitHubResponseError,
    InvalidGitHubArgumentError,
    InvalidGitHubClientSettingError,
)
from .github_client import GitHubClient

__all__ = [
    "GitHubClient",
    "GitHubUser",
    "GitHubUserPlan",
    "GitHubRepository",
    "GitHubRepositoryPermissions",
    "GitHubRepositoryLicense",
    "GitHubCommit",
    "GitHubCommitDetail",
    "GitHubGitAuthor",
    "GitHubCommitTree",
    "GitHubCommitVerification",
    "GitHubCommitParent",
    "GitHubCommitStats",
    "GitHubDiffEntry",
    "GitHubClientError",
    "InvalidGitHubClientSettingError",
    "InvalidGitHubArgumentError",
    "GitHubRequestError",
    "GitHubHTTPStatusError",
    "GitHubRateLimitError",
    "GitHubResponseError",
]
