import threading
from datetime import timedelta

import httpx

from main.package.clients.codeforces import CodeforcesClient
from main.package.clients.github import GitHubClient
from main.package.clients.leetcode import LeetcodeClient
from main.package.service.data import PlatformAccount
from tests.conftest import HTTP_TIMEOUTS
from tests.support import RecordingTransport, ResponseSpec

LEETCODE_ACCOUNTS = (PlatformAccount(username="imsahibnanda", cache_ttl=timedelta(hours=1)),)
CODEFORCES_ACCOUNTS = (PlatformAccount(username="shisukenohara", cache_ttl=timedelta(minutes=80)),)
GITHUB_ACCOUNTS = (
    PlatformAccount(username="thesahibnanda-max", cache_ttl=timedelta(minutes=45)),
    PlatformAccount(username="thesahibnanda", cache_ttl=timedelta(minutes=120)),
)

LEETCODE_PROFILE = {
    "data": {
        "matchedUser": {
            "username": "imsahibnanda",
            "twitterUrl": "https://x.com/thesahibnanda",
            "linkedinUrl": "https://linkedin.com/in/sahib",
            "profile": {
                "ranking": 41000,
                "reputation": 12,
                "aboutMe": "Backend engineer",
                "websites": ["https://sahib.dev"],
                "countryName": "India",
            },
            "submitStatsGlobal": {
                "acSubmissionNum": [
                    {"difficulty": "All", "count": 674},
                    {"difficulty": "Easy", "count": 222},
                    {"difficulty": "Medium", "count": 356},
                    {"difficulty": "Hard", "count": 96},
                ]
            },
            "badges": [{"displayName": "50 Days Badge"}, {"displayName": None}],
            "languageProblemCount": [{"languageName": "Python3", "problemsSolved": 400}, {"languageName": None, "problemsSolved": 1}],
            "tagProblemCounts": {
                "advanced": [{"tagName": "Dynamic Programming", "problemsSolved": 80}],
                "intermediate": [{"tagName": "Hash Table", "problemsSolved": 120}],
                "fundamental": [{"tagName": "Array", "problemsSolved": 300}, {"tagName": "String", "problemsSolved": None}],
            },
            "userCalendar": {"streak": 9, "totalActiveDays": 51},
        },
        "userContestRanking": {"rating": 1650.5, "globalRanking": 120000},
    }
}

CODEFORCES_RATING = {
    "status": "OK",
    "result": [
        {"contestName": "Round 1", "rank": 900, "oldRating": 0, "newRating": 1400, "ratingUpdateTimeSeconds": 1700000000},
        {"contestName": "Round 2", "rank": 50, "oldRating": 1400, "newRating": 1987, "ratingUpdateTimeSeconds": 1710000000},
        {"contestName": "Round 3", "rank": 3000, "oldRating": 1987, "newRating": 1832, "ratingUpdateTimeSeconds": None},
    ],
}


def github_user(login: str, public_repos: int) -> dict:
    return {
        "login": login,
        "name": "Sahib Nanda",
        "avatar_url": f"https://avatars.test/{login}",
        "bio": "Builder",
        "public_repos": public_repos,
        "followers": 10,
        "following": 2,
        "html_url": f"https://github.com/{login}",
    }


def github_repo(name: str, stars: int) -> dict:
    return {
        "name": name,
        "description": f"{name} repo",
        "html_url": f"https://github.com/x/{name}",
        "language": "Go",
        "stargazers_count": stars,
        "forks_count": 1,
        "updated_at": "2026-09-01T00:00:00Z",
    }


GITHUB_ROUTES = {
    "/users/thesahibnanda-max": ResponseSpec(json=github_user("thesahibnanda-max", 15)),
    "/users/thesahibnanda-max/repos": ResponseSpec(json=[github_repo("relay", 40), github_repo("helios", 12)]),
    "/users/thesahibnanda": ResponseSpec(json=github_user("thesahibnanda", 12)),
    "/users/thesahibnanda/repos": ResponseSpec(json=[]),
}


class BarrierTransport(httpx.MockTransport):
    def __init__(self, parties: int, routes: dict[str, ResponseSpec]) -> None:
        self._barrier = threading.Barrier(parties, timeout=5)
        self._routes = routes
        self.blocked_paths: set[str] = {path for path in routes if path.count("/") == 2}
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in self.blocked_paths:
            self._barrier.wait()
        return self._routes[path].build()


def leetcode_client(transport: httpx.BaseTransport) -> LeetcodeClient:
    return LeetcodeClient(base_url="https://leetcode.com", transport=transport, **HTTP_TIMEOUTS)


def codeforces_client(transport: httpx.BaseTransport) -> CodeforcesClient:
    return CodeforcesClient(base_url="https://codeforces.com", transport=transport, **HTTP_TIMEOUTS)


def github_client(transport: httpx.BaseTransport) -> GitHubClient:
    return GitHubClient(base_url="https://api.github.com", api_version="2022-11-28", per_page=100, transport=transport, **HTTP_TIMEOUTS)


def leetcode_transport(payload: dict | None = None) -> RecordingTransport:
    return RecordingTransport(ResponseSpec(json=payload if payload is not None else LEETCODE_PROFILE))


def codeforces_transport(payload: dict | None = None) -> RecordingTransport:
    return RecordingTransport(ResponseSpec(json=payload if payload is not None else CODEFORCES_RATING))


def github_transport(routes: dict[str, ResponseSpec] | None = None) -> RecordingTransport:
    return RecordingTransport(routes=routes if routes is not None else GITHUB_ROUTES)
