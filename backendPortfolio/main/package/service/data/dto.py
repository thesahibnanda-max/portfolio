from datetime import datetime, timedelta
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _require_positive_duration(value: timedelta) -> timedelta:
    if value <= timedelta(0):
        raise ValueError("cache_ttl must be positive")

    return value


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PlatformAccount(_FrozenModel):
    username: Annotated[str, Field(min_length=1)]
    cache_ttl: Annotated[timedelta, AfterValidator(_require_positive_duration)]


class LeetcodeDetails(_FrozenModel):
    username: str
    ranking: int | None = None
    reputation: int | None = None
    total_solved: int | None = None
    easy_solved: int | None = None
    medium_solved: int | None = None
    hard_solved: int | None = None
    badges: tuple[str, ...] = ()
    language_problems_solved: dict[str, int] = Field(default_factory=dict)
    advanced_tags_solved: dict[str, int] = Field(default_factory=dict)
    intermediate_tags_solved: dict[str, int] = Field(default_factory=dict)
    fundamental_tags_solved: dict[str, int] = Field(default_factory=dict)
    contest_rating: float | None = None
    contest_global_ranking: int | None = None
    current_streak: int | None = None
    total_active_days: int | None = None
    about_me: str | None = None
    websites: tuple[str, ...] = ()
    twitter_url: str | None = None
    linkedin_url: str | None = None
    country_name: str | None = None


class CodeforcesRatingTransition(_FrozenModel):
    contest_name: str | None = None
    rank: int | None = None
    old_rating: int | None = None
    new_rating: int | None = None
    contest_time: datetime | None = None


class CodeforcesDetails(_FrozenModel):
    handle: str
    current_rating: int | None = None
    max_rating: int | None = None
    contests_count: int
    rating_history: tuple[CodeforcesRatingTransition, ...] = ()


class GitHubRepositorySummary(_FrozenModel):
    name: str | None = None
    description: str | None = None
    html_url: str | None = None
    language: str | None = None
    stars: int | None = None
    forks: int | None = None
    updated_at: datetime | None = None


class GitHubDetails(_FrozenModel):
    username: str
    name: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    public_repos: int | None = None
    followers: int | None = None
    following: int | None = None
    html_url: str | None = None
    repositories: tuple[GitHubRepositorySummary, ...] = ()


class ProfessionalDetails(_FrozenModel):
    leetcode_links: tuple[str, ...]
    codeforces_links: tuple[str, ...]
    github_links: tuple[str, ...]
    profile_photo_links: tuple[str, ...]
    websites: tuple[str, ...]
    twitter_url: str | None = None
