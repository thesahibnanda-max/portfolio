from datetime import timedelta
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from main.package.clients.leetcode.dto import LeetcodeUserProfileResponse
from main.package.clients.leetcode.exceptions import (
    InvalidLeetcodeArgumentError,
    InvalidLeetcodeClientSettingError,
    LeetcodeHTTPStatusError,
    LeetcodeRequestError,
    LeetcodeResponseError,
)

_USER_PUBLIC_PROFILE_QUERY = """
query userPublicProfile($username: String!) {
  matchedUser(username: $username) {
    username
    githubUrl
    twitterUrl
    linkedinUrl
    profile {
      realName
      userAvatar
      aboutMe
      school
      websites
      countryName
      company
      jobTitle
      skillTags
      ranking
      reputation
      starRating
      postViewCount
      postViewCountDiff
      solutionCount
      solutionCountDiff
      categoryDiscussCount
      categoryDiscussCountDiff
      certificationLevel
    }
    submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
        submissions
      }
    }
    badges {
      id
      displayName
      icon
    }
    activeBadge {
      id
      displayName
      icon
    }
    languageProblemCount {
      languageName
      problemsSolved
    }
    tagProblemCounts {
      advanced {
        tagName
        problemsSolved
      }
      intermediate {
        tagName
        problemsSolved
      }
      fundamental {
        tagName
        problemsSolved
      }
    }
    userCalendar {
      activeYears
      streak
      totalActiveDays
      submissionCalendar
    }
  }
  userContestRanking(username: $username) {
    attendedContestsCount
    rating
    globalRanking
    totalParticipants
    topPercentage
    badge {
      name
    }
  }
  userContestRankingHistory(username: $username) {
    attended
    trendDirection
    problemsSolved
    totalProblems
    finishTimeInSeconds
    rating
    ranking
    contest {
      title
      startTime
    }
  }
}
"""


class LeetcodeClient:
    _GRAPHQL_PATH = "graphql"
    _OPERATION_NAME = "userPublicProfile"
    _ERROR_BODY_LIMIT = 500

    def __init__(
        self,
        *,
        base_url: str,
        connect_timeout: timedelta,
        read_timeout: timedelta,
        write_timeout: timedelta,
        pool_timeout: timedelta,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = self._require_http_url(base_url)
        timeout = httpx.Timeout(
            connect=self._require_positive_timeout("connect_timeout", connect_timeout),
            read=self._require_positive_timeout("read_timeout", read_timeout),
            write=self._require_positive_timeout("write_timeout", write_timeout),
            pool=self._require_positive_timeout("pool_timeout", pool_timeout),
        )
        self._http = httpx.Client(base_url=f"{self._base_url}/", timeout=timeout, transport=transport)

    @property
    def base_url(self) -> str:
        return self._base_url

    def get_user_profile(self, username: str) -> LeetcodeUserProfileResponse:
        self._require_non_blank("username", username)

        payload = self._post_json(
            self._GRAPHQL_PATH,
            body={
                "operationName": self._OPERATION_NAME,
                "query": _USER_PUBLIC_PROFILE_QUERY,
                "variables": {"username": username},
            },
        )
        try:
            profile_response = LeetcodeUserProfileResponse.model_validate(payload)
        except ValidationError as error:
            raise LeetcodeResponseError("Leetcode API response does not match the expected shape") from error

        if profile_response.errors:
            raise LeetcodeResponseError(
                "Leetcode API returned errors: "
                + "; ".join(str(error.get("message")) for error in profile_response.errors)
            )

        return profile_response

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _post_json(self, path: str, *, body: dict[str, Any]) -> Any:
        try:
            response = self._http.post(path, json=body)
        except httpx.RequestError as error:
            raise LeetcodeRequestError("Failed to call Leetcode API") from error

        if not response.is_success:
            response_body = response.text[:self._ERROR_BODY_LIMIT]
            raise LeetcodeHTTPStatusError(
                f"Leetcode API request failed. HTTP {response.status_code}: {response_body}",
                status_code=response.status_code,
                body=response_body,
            )

        try:
            return response.json()
        except ValueError as error:
            raise LeetcodeResponseError("Leetcode API returned invalid JSON") from error

    @staticmethod
    def _require_http_url(base_url: str) -> str:
        if not isinstance(base_url, str) or not base_url.strip():
            raise InvalidLeetcodeClientSettingError("base_url must be a non-empty string")

        parts = urlsplit(base_url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.query or parts.fragment:
            raise InvalidLeetcodeClientSettingError(
                "base_url must be an http or https URL with a host and no query or fragment"
            )

        return base_url.rstrip("/")

    @staticmethod
    def _require_positive_timeout(name: str, timeout: timedelta) -> float:
        if not isinstance(timeout, timedelta) or timeout <= timedelta(0):
            raise InvalidLeetcodeClientSettingError(f"{name} must be a positive timedelta")

        return timeout.total_seconds()

    @staticmethod
    def _require_non_blank(name: str, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise InvalidLeetcodeArgumentError(f"{name} is required")
