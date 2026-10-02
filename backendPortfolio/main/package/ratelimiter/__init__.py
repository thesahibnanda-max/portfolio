"""
Per-API rate limiting by client IP, by session and globally, on the limits
library (the engine behind Flask-Limiter and SlowAPI).

Exports:
    RateLimiter: checks and counts one request against an API's rules.
    RateLimitScope: IP, SESSION, GLOBAL.
    RateLimitRule: limit requests per window.
    RateLimiterError and its subclasses: the errors described under Errors.

Algorithm:
    Sliding window counter (limits' SlidingWindowCounterRateLimiter). The
    count is the current window's hits plus the previous window's hits
    weighted by how much of it still overlaps the last window length. Unlike
    a fixed window (which the Java service used) a client cannot send twice
    the limit around a window edge, and unlike a moving window log memory
    stays at two counters per key.

Scopes and order:
    Every API has exactly one RateLimitRule per scope:
        IP: per client IP address, so one visitor cannot flood an API.
        SESSION: per anonymous session id, so one session cannot either,
        whatever IPs it comes from.
        GLOBAL: one budget for the API across all visitors, to protect the
        upstreams (Groq, LeetCode, Codeforces, GitHub) and the server.
    check() hits them in that order, most specific first, and stops at the
    first refusal. A request refused for its IP or session therefore never
    uses up the global budget, so one abusive visitor cannot lock everyone
    else out; the global rule should allow far more than the per-visitor
    rules. A client_ip or session_id of None skips that scope (for example
    no session exists yet when a session is created); GLOBAL always applies.

Keys:
    "<key_prefix>/<api>/<scope>/<identifier>/<limit>/<seconds>/second", with
    "all" as the GLOBAL identifier, for example
    "rate_limit/chat_message/ip/203.0.113.7/5/60/second". The sliding window
    keeps one counter per key for the current and the previous window.

Construction:
    RateLimiter(*, storage_uri, key_prefix, rules)
    storage_uri: a limits storage URI. "memory://" keeps counters in this
    process; "redis://host:6379" (or memcached://, mongodb://) shares them
    between processes once that backend's client library is installed, with
    no code change. async+ URIs are rejected.
    key_prefix: non-empty namespace for every key.
    rules: non-empty mapping of api name ([a-z0-9_]+) to a mapping with
    exactly one RateLimitRule for each RateLimitScope.
    RateLimitRule(limit, window): limit is an int of at least 1 and window a
    positive timedelta of whole seconds; anything else raises pydantic's
    ValidationError. Every other bad setting raises
    InvalidRateLimiterSettingError. All of it comes from
    main.config.AppConfig.rate_limit.

Methods:
    check(api, *, client_ip, session_id) -> None: counts one request, or
    raises RateLimitExceededError without counting it in the refused or any
    later scope.
    remaining(api, *, client_ip, session_id) -> Mapping[RateLimitScope, int]:
    requests left in each applicable scope, for X-RateLimit-Remaining style
    headers; it counts nothing.
    reset(): clears every counter in the storage.
    apis: the configured api names.

Errors (all in exceptions.py, all subclasses of RateLimiterError):
    InvalidRateLimiterSettingError: a constructor setting is invalid, or the
    storage URI is unknown or its client library is missing (limits' error is
    chained as __cause__).
    InvalidRateLimitArgumentError: an api with no rules (an endpoint is never
    silently left unlimited), or a client_ip or session_id that is not a
    non-empty string or None.
    RateLimitExceededError: has api, scope and retry_after, a timedelta of
    whole seconds from 1 up to the window, for a Retry-After header.

Thread safety:
    One RateLimiter can serve every thread on the free-threaded Python 3.14t
    build and never lets more requests through than a limit. limits' memory
    storage is not safe for concurrent use of one key (get() can drop a
    counter another thread has just created, and per-key locks can be
    replaced while held), which over-admitted badly under free threading. So
    every hit and stats read takes one of 64 striped locks chosen by
    (api, scope, identifier): calls on the same key are serialised, calls on
    different keys mostly run in parallel, and memory stays bounded however
    many IPs or sessions arrive. reset() takes every stripe. The rules are
    immutable. limits is pure Python and keeps the GIL disabled.

Example:
    limiter = RateLimiter(
        storage_uri="memory://",
        key_prefix="rate_limit",
        rules={"chat_message": {
            RateLimitScope.IP: RateLimitRule(limit=5, window=timedelta(minutes=1)),
            RateLimitScope.SESSION: RateLimitRule(limit=5, window=timedelta(minutes=1)),
            RateLimitScope.GLOBAL: RateLimitRule(limit=60, window=timedelta(minutes=1)),
        }},
    )
    try:
        limiter.check("chat_message", client_ip=ip, session_id=session_id)
    except RateLimitExceededError as error:
        respond_429(retry_after=error.retry_after)
"""

from .dto import RateLimitRule, RateLimitScope
from .exceptions import (
    InvalidRateLimitArgumentError,
    InvalidRateLimiterSettingError,
    RateLimiterError,
    RateLimitExceededError,
)
from .ratelimiter import RateLimiter

__all__ = [
    "RateLimiter",
    "RateLimitScope",
    "RateLimitRule",
    "RateLimiterError",
    "InvalidRateLimiterSettingError",
    "InvalidRateLimitArgumentError",
    "RateLimitExceededError",
]
