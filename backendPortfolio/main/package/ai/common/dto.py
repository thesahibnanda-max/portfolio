from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContextType(StrEnum):
    PROFILE = "PROFILE"
    GITHUB = "GITHUB"
    LEETCODE = "LEETCODE"
    CODEFORCES = "CODEFORCES"
    PERSONALITY = "PERSONALITY"
    NONE = "NONE"

    @property
    def description(self) -> str:
        return _CONTEXT_DESCRIPTIONS[self]


_CONTEXT_DESCRIPTIONS = MappingProxyType(
    {
        ContextType.PROFILE: (
            "Resume: experience, education, projects, technical skills, "
            "achievements, contact links, spoken languages"
        ),
        ContextType.GITHUB: "GitHub profile: repositories, languages used, stars, followers, bio",
        ContextType.LEETCODE: (
            "LeetCode competitive programming profile: rank, problems "
            "solved, contest rating, streak, languages used"
        ),
        ContextType.CODEFORCES: "Codeforces competitive programming profile: rating, contest history",
        ContextType.PERSONALITY: (
            "Non-technical personal profile: interests, hobbies, "
            "favorites (movies, games, sports), personality traits, "
            "appearance, spoken languages, working style"
        ),
        ContextType.NONE: "General question requiring no personal context",
    }
)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChatMessage(_FrozenModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, Field(min_length=1)]


class LLMModel(_FrozenModel):
    model_id: Annotated[str, Field(min_length=1)]
    weight: Annotated[int, Field(ge=1)]
    reasoning_effort: Annotated[str, Field(min_length=1)] | None = None
    supports_strict_json_schema: bool = False


class ModelChoice(_FrozenModel):
    model_id: str
    reasoning_effort: str | None
    supports_strict_json_schema: bool
    temperature: float
    top_p: float
