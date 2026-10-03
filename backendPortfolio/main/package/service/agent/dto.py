from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from main.package.ai.common import ContextType
from main.package.ai.orchestrator import QueryScope
from main.package.service.chat import ChatReplyStream


class GateDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: QueryScope
    contexts: tuple[ContextType, ...]


@dataclass(frozen=True)
class AgentTurnStream:
    steps: tuple[str, ...]
    replies: ChatReplyStream
