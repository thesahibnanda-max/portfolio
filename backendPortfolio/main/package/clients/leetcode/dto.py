import json
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel


class _LeetcodeModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
    )


class LeetcodeProfile(_LeetcodeModel):
    real_name: str | None = None
    user_avatar: str | None = None
    about_me: str | None = None
    school: str | None = None
    websites: tuple[str, ...] | None = None
    country_name: str | None = None
    company: str | None = None
    job_title: str | None = None
    skill_tags: tuple[str, ...] | None = None
    ranking: int | None = None
    reputation: int | None = None
    star_rating: float | None = None
    post_view_count: int | None = None
    post_view_count_diff: int | None = None
    solution_count: int | None = None
    solution_count_diff: int | None = None
    category_discuss_count: int | None = None
    category_discuss_count_diff: int | None = None
    certification_level: str | None = None


class LeetcodeAcSubmissionNum(_LeetcodeModel):
    difficulty: str | None = None
    count: int | None = None
    submissions: int | None = None


class LeetcodeSubmitStatsGlobal(_LeetcodeModel):
    ac_submission_num: tuple[LeetcodeAcSubmissionNum, ...] | None = None


class LeetcodeBadge(_LeetcodeModel):
    id: str | None = None
    display_name: str | None = None
    icon: str | None = None
    creation_date: str | None = None


class LeetcodeLanguageProblemCount(_LeetcodeModel):
    language_name: str | None = None
    problems_solved: int | None = None


class LeetcodeTagProblemCount(_LeetcodeModel):
    tag_name: str | None = None
    problems_solved: int | None = None


class LeetcodeTagProblemCounts(_LeetcodeModel):
    advanced: tuple[LeetcodeTagProblemCount, ...] | None = None
    intermediate: tuple[LeetcodeTagProblemCount, ...] | None = None
    fundamental: tuple[LeetcodeTagProblemCount, ...] | None = None


class LeetcodeUserCalendar(_LeetcodeModel):
    active_years: tuple[int, ...] | None = None
    streak: int | None = None
    total_active_days: int | None = None
    submission_calendar: dict[int, int] | None = None

    @field_validator("submission_calendar", mode="before")
    @classmethod
    def _parse_submission_calendar(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        try:
            return json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("submissionCalendar is not valid JSON") from error


class LeetcodeMatchedUser(_LeetcodeModel):
    username: str | None = None
    github_url: str | None = None
    twitter_url: str | None = None
    linkedin_url: str | None = None
    profile: LeetcodeProfile | None = None
    submit_stats_global: LeetcodeSubmitStatsGlobal | None = None
    badges: tuple[LeetcodeBadge, ...] | None = None
    active_badge: LeetcodeBadge | None = None
    language_problem_count: tuple[LeetcodeLanguageProblemCount, ...] | None = None
    tag_problem_counts: LeetcodeTagProblemCounts | None = None
    user_calendar: LeetcodeUserCalendar | None = None


class LeetcodeContestBadge(_LeetcodeModel):
    name: str | None = None


class LeetcodeUserContestRanking(_LeetcodeModel):
    attended_contests_count: int | None = None
    rating: float | None = None
    global_ranking: int | None = None
    total_participants: int | None = None
    top_percentage: float | None = None
    badge: LeetcodeContestBadge | None = None


class LeetcodeContest(_LeetcodeModel):
    title: str | None = None
    start_time: int | None = None


class LeetcodeUserContestRankingHistory(_LeetcodeModel):
    attended: bool | None = None
    trend_direction: str | None = None
    problems_solved: int | None = None
    total_problems: int | None = None
    finish_time_in_seconds: int | None = None
    rating: float | None = None
    ranking: int | None = None
    contest: LeetcodeContest | None = None


class LeetcodeDataNode(_LeetcodeModel):
    matched_user: LeetcodeMatchedUser | None = None
    user_contest_ranking: LeetcodeUserContestRanking | None = None
    user_contest_ranking_history: tuple[LeetcodeUserContestRankingHistory, ...] | None = None


class LeetcodeUserProfileResponse(_LeetcodeModel):
    data: LeetcodeDataNode | None = None
    errors: tuple[dict[str, Any], ...] | None = None
