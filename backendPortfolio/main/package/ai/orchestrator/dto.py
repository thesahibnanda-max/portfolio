from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from main.package.ai.common.dto import ContextType


class QueryScope(StrEnum):
    IN_SCOPE = "IN_SCOPE"
    NOT_RELATED_TO_PORTFOLIO = "NOT_RELATED_TO_PORTFOLIO"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    UNSAFE = "UNSAFE"


class OrchestratorDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: QueryScope
    required_contexts: tuple[ContextType, ...]
    reason: str

    @property
    def is_in_scope(self) -> bool:
        return self.scope is QueryScope.IN_SCOPE

    @property
    def needs_context(self) -> bool:
        return self.is_in_scope and ContextType.NONE not in self.required_contexts
