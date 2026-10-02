from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import UTC, datetime

from main.package.clients.codeforces import CodeforcesClient, CodeforcesClientError, CodeforcesRatingChange
from main.package.clients.github import GitHubClient, GitHubClientError, GitHubRepository
from main.package.clients.leetcode import (
    LeetcodeAcSubmissionNum,
    LeetcodeBadge,
    LeetcodeClient,
    LeetcodeClientError,
    LeetcodeLanguageProblemCount,
    LeetcodeMatchedUser,
    LeetcodeTagProblemCount,
    LeetcodeUserContestRanking,
    LeetcodeUserProfileResponse,
)
from main.package.service.data.dto import (
    CodeforcesDetails,
    CodeforcesRatingTransition,
    GitHubDetails,
    GitHubRepositorySummary,
    LeetcodeDetails,
)
from main.package.service.data.exceptions import DataSourceResponseError, DataSourceUnavailableError

_DIFFICULTY_ALL = "All"
_DIFFICULTY_EASY = "Easy"
_DIFFICULTY_MEDIUM = "Medium"
_DIFFICULTY_HARD = "Hard"


class DetailsSource[T](ABC):
    @property
    @abstractmethod
    def platform(self) -> str:
        ...

    @property
    @abstractmethod
    def details_type(self) -> type[T]:
        ...

    @abstractmethod
    def fetch(self, account: str) -> T:
        ...


def _solved_count(submissions: Sequence[LeetcodeAcSubmissionNum] | None, difficulty: str) -> int | None:
    for submission in submissions or ():
        if submission.difficulty == difficulty:
            return submission.count

    return None


def _badge_names(badges: Sequence[LeetcodeBadge] | None) -> tuple[str, ...]:
    return tuple(badge.display_name for badge in badges or () if badge.display_name)


def _language_counts(counts: Sequence[LeetcodeLanguageProblemCount] | None) -> dict[str, int]:
    return {
        count.language_name: count.problems_solved
        for count in counts or ()
        if count.language_name and count.problems_solved is not None
    }


def _tag_counts(tags: Sequence[LeetcodeTagProblemCount] | None) -> dict[str, int]:
    return {tag.tag_name: tag.problems_solved for tag in tags or () if tag.tag_name and tag.problems_solved is not None}


def _contest_value(ranking: LeetcodeUserContestRanking | None, field: str) -> float | int | None:
    return getattr(ranking, field) if ranking is not None else None


class LeetcodeSource(DetailsSource[LeetcodeDetails]):
    def __init__(self, client: LeetcodeClient) -> None:
        self._client = client

    @property
    def platform(self) -> str:
        return "leetcode"

    @property
    def details_type(self) -> type[LeetcodeDetails]:
        return LeetcodeDetails

    def fetch(self, account: str) -> LeetcodeDetails:
        try:
            response = self._client.get_user_profile(account)
        except LeetcodeClientError as error:
            raise DataSourceUnavailableError(
                f"LeetCode data for {account} is unavailable", platform=self.platform, account=account
            ) from error

        return self._map(account, response)

    def _map(self, account: str, response: LeetcodeUserProfileResponse) -> LeetcodeDetails:
        user = response.data.matched_user if response.data is not None else None
        if user is None:
            raise DataSourceResponseError(
                f"LeetCode returned no profile for {account}", platform=self.platform, account=account
            )

        return self._details(account, user, response.data.user_contest_ranking)

    @staticmethod
    def _details(account: str, user: LeetcodeMatchedUser, ranking: LeetcodeUserContestRanking | None) -> LeetcodeDetails:
        profile = user.profile
        submissions = user.submit_stats_global.ac_submission_num if user.submit_stats_global else None
        tags = user.tag_problem_counts
        calendar = user.user_calendar

        return LeetcodeDetails(
            username=user.username or account,
            ranking=profile.ranking if profile else None,
            reputation=profile.reputation if profile else None,
            total_solved=_solved_count(submissions, _DIFFICULTY_ALL),
            easy_solved=_solved_count(submissions, _DIFFICULTY_EASY),
            medium_solved=_solved_count(submissions, _DIFFICULTY_MEDIUM),
            hard_solved=_solved_count(submissions, _DIFFICULTY_HARD),
            badges=_badge_names(user.badges),
            language_problems_solved=_language_counts(user.language_problem_count),
            advanced_tags_solved=_tag_counts(tags.advanced if tags else None),
            intermediate_tags_solved=_tag_counts(tags.intermediate if tags else None),
            fundamental_tags_solved=_tag_counts(tags.fundamental if tags else None),
            contest_rating=_contest_value(ranking, "rating"),
            contest_global_ranking=_contest_value(ranking, "global_ranking"),
            current_streak=calendar.streak if calendar else None,
            total_active_days=calendar.total_active_days if calendar else None,
            about_me=profile.about_me if profile else None,
            websites=profile.websites or () if profile else (),
            twitter_url=user.twitter_url,
            linkedin_url=user.linkedin_url,
            country_name=profile.country_name if profile else None,
        )


def _rating_transition(change: CodeforcesRatingChange) -> CodeforcesRatingTransition:
    seconds = change.rating_update_time_seconds

    return CodeforcesRatingTransition(
        contest_name=change.contest_name,
        rank=change.rank,
        old_rating=change.old_rating,
        new_rating=change.new_rating,
        contest_time=datetime.fromtimestamp(seconds, UTC) if seconds is not None else None,
    )


class CodeforcesSource(DetailsSource[CodeforcesDetails]):
    def __init__(self, client: CodeforcesClient) -> None:
        self._client = client

    @property
    def platform(self) -> str:
        return "codeforces"

    @property
    def details_type(self) -> type[CodeforcesDetails]:
        return CodeforcesDetails

    def fetch(self, account: str) -> CodeforcesDetails:
        try:
            response = self._client.get_user_rating(account)
        except CodeforcesClientError as error:
            raise DataSourceUnavailableError(
                f"Codeforces data for {account} is unavailable", platform=self.platform, account=account
            ) from error

        history = response.result or ()
        ratings = [change.new_rating for change in history if change.new_rating is not None]

        return CodeforcesDetails(
            handle=account,
            current_rating=history[-1].new_rating if history else None,
            max_rating=max(ratings) if ratings else None,
            contests_count=len(history),
            rating_history=tuple(_rating_transition(change) for change in history),
        )


def _repository_summary(repository: GitHubRepository) -> GitHubRepositorySummary:
    return GitHubRepositorySummary(
        name=repository.name,
        description=repository.description,
        html_url=repository.html_url,
        language=repository.language,
        stars=repository.stargazers_count,
        forks=repository.forks_count,
        updated_at=repository.updated_at,
    )


class GitHubSource(DetailsSource[GitHubDetails]):
    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    @property
    def platform(self) -> str:
        return "github"

    @property
    def details_type(self) -> type[GitHubDetails]:
        return GitHubDetails

    def fetch(self, account: str) -> GitHubDetails:
        try:
            user = self._client.get_user(account)
            repositories = self._client.list_user_repositories(account)
        except GitHubClientError as error:
            raise DataSourceUnavailableError(
                f"GitHub data for {account} is unavailable", platform=self.platform, account=account
            ) from error

        return GitHubDetails(
            username=user.login or account,
            name=user.name,
            avatar_url=user.avatar_url,
            bio=user.bio,
            public_repos=user.public_repos,
            followers=user.followers,
            following=user.following,
            html_url=user.html_url,
            repositories=tuple(_repository_summary(repository) for repository in repositories),
        )
