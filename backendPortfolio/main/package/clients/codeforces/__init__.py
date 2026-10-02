"""
Client for the public Codeforces API, used to fetch a user's contest rating
history.

Exports:
    CodeforcesClient: the client.
    CodeforcesUserRatingResponse, CodeforcesRatingChange: response DTOs.
    CodeforcesClientError and its subclasses: the errors described under
    Errors.

Construction:
    CodeforcesClient(
        *,
        base_url,
        connect_timeout,
        read_timeout,
        write_timeout,
        pool_timeout,
        transport=None,
    )
    base_url: http or https URL with a host and no query or fragment, from
    main.config.AppConfig.codeforces.base_url (default "https://codeforces.com").
    A trailing slash is removed.
    connect_timeout, read_timeout, write_timeout, pool_timeout: positive
    timedeltas from main.config.AppConfig.http_client (defaults 10s, 60s, 60s,
    10s). Pool timeout is how long to wait for a free pooled connection.
    transport: optional httpx transport, only for tests (for example
    httpx.MockTransport); it is not a config setting.
    Every setting is keyword-only and validated; a bad one raises
    InvalidCodeforcesClientSettingError.

    The client builds and owns one httpx.Client, so call close() when done,
    or use it as a context manager: with CodeforcesClient(...) as client.

Methods:
    base_url: the configured base URL without a trailing slash, for building
    public profile links such as f"{client.base_url}/profile/{handle}".

    get_user_rating(handle) -> CodeforcesUserRatingResponse
        GET <base_url>/api/user.rating?handle=<handle>.
        Returns status "OK" with result, a tuple of CodeforcesRatingChange
        (contest_id, contest_name, handle, rank, rating_update_time_seconds,
        old_rating, new_rating), oldest contest first.

DTOs:
    Frozen pydantic models. JSON fields are camelCase and are read into
    snake_case attributes; unknown fields are ignored; every field is
    optional; lists are tuples, so a response is fully immutable.

Errors (all in exceptions.py, all subclasses of CodeforcesClientError):
    InvalidCodeforcesClientSettingError: a constructor setting is invalid.
    InvalidCodeforcesArgumentError: handle is empty or whitespace-only.
    CodeforcesRequestError: the request failed before a response arrived
    (connection error, timeout); the httpx error is chained as __cause__.
    CodeforcesHTTPStatusError: a non-2xx response. It has status_code and
    body (first 500 characters). Codeforces answers an unknown handle with
    HTTP 400 and a JSON comment such as "handle: User with handle x not
    found"; that comment is used as the message when present.
    CodeforcesResponseError: the body is not valid JSON, does not match the
    DTO shape, or status is not "OK" (the API's comment is the message).
    Catch CodeforcesClientError to handle every failure at once.

Thread safety:
    One instance can be shared across threads on the free-threaded Python
    3.14t build: it holds only immutable settings and an httpx.Client, whose
    connection pool is thread-safe.

Dependencies:
    httpx and pydantic. httpx and its dependencies are pure Python and
    pydantic-core ships a cp314t wheel, so the GIL stays disabled.

Example:
    with CodeforcesClient(
        base_url="https://codeforces.com",
        connect_timeout=timedelta(seconds=10),
        read_timeout=timedelta(seconds=60),
        write_timeout=timedelta(seconds=60),
        pool_timeout=timedelta(seconds=10),
    ) as client:
        history = client.get_user_rating("tourist").result
"""

from .codeforces_client import CodeforcesClient
from .dto import CodeforcesRatingChange, CodeforcesUserRatingResponse
from .exceptions import (
    CodeforcesClientError,
    CodeforcesHTTPStatusError,
    CodeforcesRequestError,
    CodeforcesResponseError,
    InvalidCodeforcesArgumentError,
    InvalidCodeforcesClientSettingError,
)

__all__ = [
    "CodeforcesClient",
    "CodeforcesUserRatingResponse",
    "CodeforcesRatingChange",
    "CodeforcesClientError",
    "InvalidCodeforcesClientSettingError",
    "InvalidCodeforcesArgumentError",
    "CodeforcesRequestError",
    "CodeforcesHTTPStatusError",
    "CodeforcesResponseError",
]
