from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from main.package.ai.orchestrator import QueryScope


class AnswerStyle(StrEnum):
    CONCISE = "concise"
    DETAILED = "detailed"


class AgentMode(StrEnum):
    ANSWER = "answer"
    PLAN = "plan"


class PlanStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    command: Annotated[str, Field(min_length=1, max_length=200)]
    reason: Annotated[str, Field(max_length=300)] = ""


class AgentPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    scope: QueryScope = QueryScope.IN_SCOPE
    summary: Annotated[str, Field(max_length=300)] = ""
    steps: tuple[PlanStep, ...] = ()
