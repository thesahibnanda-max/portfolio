from collections.abc import Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from main.package.ai.common.dto import ChatMessage, ContextType, ModelChoice
from main.package.ai.common.model_selector import ModelSelector
from main.package.ai.common.prompting import build_prompt_environment, first_choice_content, require_conversation
from main.package.ai.orchestrator.dto import OrchestratorDecision, QueryScope
from main.package.ai.orchestrator.exceptions import (
    InvalidOrchestratorInputError,
    InvalidOrchestratorSettingError,
    OrchestratorResponseError,
)
from main.package.clients.groq import (
    GroqChatCompletionRequest,
    GroqClient,
    GroqJsonObjectResponseFormat,
    GroqJsonSchema,
    GroqJsonSchemaResponseFormat,
    GroqMessage,
    GroqResponseFormat,
)
from main.package.json_extract import JsonExtractor, JsonExtractorError

_PROMPT_DIRECTORY = Path(__file__).parent
_SYSTEM_TEMPLATE = "system.md"
_USER_TEMPLATE = "user.md"
_DECISION_SCHEMA_NAME = "orchestrator_decision"
_DECISION_SCHEMA = MappingProxyType(
    {
        "type": "object",
        "properties": {
            "scope": {"type": "string", "enum": [scope.value for scope in QueryScope]},
            "requiredContexts": {
                "type": "array",
                "items": {"type": "string", "enum": [context.name for context in ContextType]},
            },
            "reason": {"type": "string"},
        },
        "required": ["scope", "requiredContexts", "reason"],
        "additionalProperties": False,
    }
)
_STRICT_DECISION_FORMAT = GroqJsonSchemaResponseFormat(
    json_schema=GroqJsonSchema(name=_DECISION_SCHEMA_NAME, schema=_DECISION_SCHEMA, strict=True)
)
_JSON_OBJECT_FORMAT = GroqJsonObjectResponseFormat()


def _normalise_enum_name(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


class _RawDecision(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_by_alias=True, validate_by_name=True)

    scope: Annotated[QueryScope, BeforeValidator(_normalise_enum_name)]
    required_contexts: Annotated[
        list[Annotated[ContextType, BeforeValidator(_normalise_enum_name)]],
        Field(alias="requiredContexts"),
    ]
    reason: str = ""


class Orchestrator:
    def __init__(
        self,
        groq_client: GroqClient,
        model_selector: ModelSelector,
        *,
        owner_name: str,
        temperature: float,
        top_p: float,
        max_completion_tokens: int,
    ) -> None:
        if not isinstance(groq_client, GroqClient):
            raise InvalidOrchestratorSettingError("groq_client must be a GroqClient")

        if not isinstance(model_selector, ModelSelector):
            raise InvalidOrchestratorSettingError("model_selector must be a ModelSelector")

        if not isinstance(owner_name, str):
            raise InvalidOrchestratorSettingError("owner_name must be a string")

        self._groq_client = groq_client
        self._model_selector = model_selector
        self._temperature = self._require_number("temperature", temperature, 0.0, 2.0)
        self._top_p = self._require_number("top_p", top_p, 0.0, 1.0)
        self._max_completion_tokens = self._require_positive_int("max_completion_tokens", max_completion_tokens)

        environment = build_prompt_environment(_PROMPT_DIRECTORY)
        self._system_prompt = environment.get_template(_SYSTEM_TEMPLATE).render(
            owner_name=owner_name,
            context_types=tuple(ContextType),
        )
        self._user_template = environment.get_template(_USER_TEMPLATE)

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def build_user_prompt(self, message: str, history: Sequence[ChatMessage] = ()) -> str:
        checked_history = require_conversation(message, history, InvalidOrchestratorInputError)

        return self._user_template.render(current_message=message, history=checked_history)

    def route(self, message: str, history: Sequence[ChatMessage] = ()) -> OrchestratorDecision:
        user_prompt = self.build_user_prompt(message, history)
        choice = self._model_selector.select(temperature=self._temperature, top_p=self._top_p)
        request = GroqChatCompletionRequest(
            model=choice.model_id,
            messages=(
                GroqMessage(role="system", content=self._system_prompt),
                GroqMessage(role="user", content=user_prompt),
            ),
            temperature=choice.temperature,
            top_p=choice.top_p,
            max_completion_tokens=self._max_completion_tokens,
            reasoning_effort=choice.reasoning_effort,
            response_format=self._response_format(choice),
        )

        content = first_choice_content(self._groq_client.create_chat_completion(request))
        if content is None:
            raise OrchestratorResponseError("Orchestrator model returned no content")

        try:
            raw_decision = JsonExtractor.extract(content, _RawDecision)
        except JsonExtractorError as error:
            raise OrchestratorResponseError("Orchestrator model did not return a valid routing decision") from error

        return OrchestratorDecision(
            scope=raw_decision.scope,
            required_contexts=self._normalise(raw_decision.scope, raw_decision.required_contexts),
            reason=raw_decision.reason.strip(),
        )

    @staticmethod
    def _response_format(choice: ModelChoice) -> GroqResponseFormat:
        return _STRICT_DECISION_FORMAT if choice.supports_strict_json_schema else _JSON_OBJECT_FORMAT

    @staticmethod
    def _normalise(scope: QueryScope, contexts: list[ContextType]) -> tuple[ContextType, ...]:
        if scope is not QueryScope.IN_SCOPE:
            return ()

        requested = set(contexts)
        ordered = tuple(context for context in ContextType if context in requested)

        if len(ordered) > 1:
            ordered = tuple(context for context in ordered if context is not ContextType.NONE)

        return ordered or (ContextType.NONE,)

    @staticmethod
    def _require_number(name: str, value: float, low: float, high: float) -> float:
        if isinstance(value, bool) or not isinstance(value, int | float) or not low <= value <= high:
            raise InvalidOrchestratorSettingError(f"{name} must be a number from {low} to {high}")

        return float(value)

    @staticmethod
    def _require_positive_int(name: str, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InvalidOrchestratorSettingError(f"{name} must be a positive int")

        return value
