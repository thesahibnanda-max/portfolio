from datetime import timedelta

from main.package.ratelimiter.dto import RateLimitScope


class RateLimiterError(Exception):
    pass


class InvalidRateLimiterSettingError(RateLimiterError):
    pass


class InvalidRateLimitArgumentError(RateLimiterError):
    pass


class RateLimitExceededError(RateLimiterError):
    def __init__(self, message: str, *, api: str, scope: RateLimitScope, retry_after: timedelta) -> None:
        super().__init__(message)
        self.api = api
        self.scope = scope
        self.retry_after = retry_after
