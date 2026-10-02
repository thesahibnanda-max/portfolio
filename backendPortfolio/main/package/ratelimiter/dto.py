from datetime import timedelta
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _require_whole_positive_seconds(value: timedelta) -> timedelta:
    if value <= timedelta(0) or value % timedelta(seconds=1):
        raise ValueError("window must be a positive whole number of seconds")

    return value


class RateLimitScope(StrEnum):
    IP = "ip"
    SESSION = "session"
    GLOBAL = "global"


class RateLimitRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    limit: Annotated[int, Field(strict=True, ge=1)]
    window: Annotated[timedelta, AfterValidator(_require_whole_positive_seconds)]
