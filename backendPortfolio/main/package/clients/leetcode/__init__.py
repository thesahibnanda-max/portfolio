"""
Client for the LeetCode GraphQL API, used to fetch a user's public profile
statistics.

Exports:
    LeetcodeClient: the client.
    LeetcodeUserProfileResponse and the nested DTOs it is built from.
    LeetcodeClientError and its subclasses: the errors described under
    Errors.

Construction:
    LeetcodeClient(
        *,
        base_url,
        connect_timeout,
        read_timeout,
        write_timeout,
        pool_timeout,
        transport=None,
    )
    base_url: http or https URL with a host and no query or fragment, from
    main.config.AppConfig.leetcode.base_url (default "https://leetcode.com").
    A trailing slash is removed.
    connect_timeout, read_timeout, write_timeout, pool_timeout: positive
    timedeltas from main.config.AppConfig.http_client (defaults 10s, 60s, 60s,
    10s).
    transport: optional httpx transport, only for tests; it is not a config
    setting.
    Every setting is keyword-only and validated; a bad one raises
    InvalidLeetcodeClientSettingError.

    The client builds and owns one httpx.Client, so call close() when done,
    or use it as a context manager.

Methods:
    base_url: the configured base URL without a trailing slash, for building
    public profile links such as f"{client.base_url}/u/{username}/".

    get_user_profile(username) -> LeetcodeUserProfileResponse
        POST <base_url>/graphql with operationName "userPublicProfile" and
        one fixed query that always fetches every section: matchedUser
        (username and social links, profile, submitStatsGlobal, badges,
        activeBadge, languageProblemCount, tagProblemCounts, userCalendar),
        userContestRanking and userContestRankingHistory.
        The username is sent as a GraphQL variable ($username), never pasted
        into the query text, so it cannot change the query.

Response:
    LeetcodeUserProfileResponse.data is a LeetcodeDataNode with
    matched_user (LeetcodeMatchedUser), user_contest_ranking
    (LeetcodeUserContestRanking) and user_contest_ranking_history (a tuple of
    LeetcodeUserContestRankingHistory). Any of them is None when LeetCode has
    no data, for example a user who never joined a contest.
    LeetcodeUserCalendar.submission_calendar arrives from LeetCode as a JSON
    string and is parsed into dict[int, int], mapping a UTC day's epoch
    seconds to that day's submission count.

DTOs:
    Frozen pydantic models. JSON fields are camelCase and are read into
    snake_case attributes; unknown fields are ignored; every field is
    optional; lists are tuples.

Errors (all in exceptions.py, all subclasses of LeetcodeClientError):
    InvalidLeetcodeClientSettingError: a constructor setting is invalid.
    InvalidLeetcodeArgumentError: username is empty or whitespace-only.
    LeetcodeRequestError: the request failed before a response arrived
    (connection error, timeout); the httpx error is chained as __cause__.
    LeetcodeHTTPStatusError: a non-2xx response. It has status_code and body
    (first 500 characters).
    LeetcodeResponseError: the body is not valid JSON, does not match the DTO
    shape, or contains GraphQL errors (their messages joined with "; "), for
    example when the user does not exist.
    Catch LeetcodeClientError to handle every failure at once.

Thread safety:
    One instance can be shared across threads on the free-threaded Python
    3.14t build: it holds only immutable settings and an httpx.Client, whose
    connection pool is thread-safe.

Dependencies:
    httpx and pydantic. httpx and its dependencies are pure Python and
    pydantic-core ships a cp314t wheel, so the GIL stays disabled.

Example:
    with LeetcodeClient(
        base_url="https://leetcode.com",
        connect_timeout=timedelta(seconds=10),
        read_timeout=timedelta(seconds=60),
        write_timeout=timedelta(seconds=60),
        pool_timeout=timedelta(seconds=10),
    ) as client:
        stats = client.get_user_profile("imsahibnanda").data.matched_user.submit_stats_global
"""

from .dto import (
    LeetcodeAcSubmissionNum,
    LeetcodeBadge,
    LeetcodeContest,
    LeetcodeContestBadge,
    LeetcodeDataNode,
    LeetcodeLanguageProblemCount,
    LeetcodeMatchedUser,
    LeetcodeProfile,
    LeetcodeSubmitStatsGlobal,
    LeetcodeTagProblemCount,
    LeetcodeTagProblemCounts,
    LeetcodeUserCalendar,
    LeetcodeUserContestRanking,
    LeetcodeUserContestRankingHistory,
    LeetcodeUserProfileResponse,
)
from .exceptions import (
    InvalidLeetcodeArgumentError,
    InvalidLeetcodeClientSettingError,
    LeetcodeClientError,
    LeetcodeHTTPStatusError,
    LeetcodeRequestError,
    LeetcodeResponseError,
)
from .leetcode_client import LeetcodeClient

__all__ = [
    "LeetcodeClient",
    "LeetcodeUserProfileResponse",
    "LeetcodeDataNode",
    "LeetcodeMatchedUser",
    "LeetcodeProfile",
    "LeetcodeSubmitStatsGlobal",
    "LeetcodeAcSubmissionNum",
    "LeetcodeBadge",
    "LeetcodeLanguageProblemCount",
    "LeetcodeTagProblemCounts",
    "LeetcodeTagProblemCount",
    "LeetcodeUserCalendar",
    "LeetcodeUserContestRanking",
    "LeetcodeContestBadge",
    "LeetcodeUserContestRankingHistory",
    "LeetcodeContest",
    "LeetcodeClientError",
    "InvalidLeetcodeClientSettingError",
    "InvalidLeetcodeArgumentError",
    "LeetcodeRequestError",
    "LeetcodeHTTPStatusError",
    "LeetcodeResponseError",
]
