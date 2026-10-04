from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from main.package.ai.agent.dto import AgentPlan, AnswerStyle
from main.package.ai.agent.exceptions import AgentResponseError, InvalidAgentInputError, InvalidAgentSettingError
from main.package.ai.common.dto import ChatMessage, ModelChoice, Surface
from main.package.ai.common.model_selector import ModelSelector
from main.package.ai.common.prompting import build_prompt_environment, first_choice_content, require_conversation
from main.package.ai.orchestrator import QueryScope
from main.package.clients.groq import (
    GroqChatCompletionRequest,
    GroqChatCompletionStream,
    GroqClient,
    GroqJsonObjectResponseFormat,
    GroqJsonSchema,
    GroqJsonSchemaResponseFormat,
    GroqMessage,
    GroqResponseFormat,
    GroqUsage,
)
from main.package.json_extract import JsonExtractor, JsonExtractorError

_PROMPT_DIRECTORY = Path(__file__).parent
_SYSTEM_TEMPLATE = "system.md"
_PLAN_TEMPLATE = "plan.md"
_USER_TEMPLATE = "user.md"
_PLAN_SCHEMA_NAME = "agent_plan"
_PLAN_SCHEMA = MappingProxyType(
    {
        "type": "object",
        "properties": {
            "scope": {"type": "string", "enum": [scope.value for scope in QueryScope]},
            "summary": {"type": "string"},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}, "reason": {"type": "string"}},
                    "required": ["command", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["scope", "summary", "steps"],
        "additionalProperties": False,
    }
)
_STRICT_PLAN_FORMAT = GroqJsonSchemaResponseFormat(
    json_schema=GroqJsonSchema(name=_PLAN_SCHEMA_NAME, schema=_PLAN_SCHEMA, strict=True)
)
_JSON_OBJECT_FORMAT = GroqJsonObjectResponseFormat()


class Agent:
    def __init__(
        self,
        groq_client: GroqClient,
        model_selector: ModelSelector,
        *,
        owner_name: str,
        markers: Mapping[QueryScope, str],
        style_tokens: Mapping[AnswerStyle, int],
        plan_tokens: int,
    ) -> None:
        if not isinstance(groq_client, GroqClient):
            raise InvalidAgentSettingError("groq_client must be a GroqClient")

        if not isinstance(model_selector, ModelSelector):
            raise InvalidAgentSettingError("model_selector must be a ModelSelector")

        if not isinstance(owner_name, str) or not owner_name.strip():
            raise InvalidAgentSettingError("owner_name must be a non-blank string")

        self._groq_client = groq_client
        self._model_selector = model_selector
        self._markers = self._require_markers(markers)
        self._style_tokens = self._require_style_tokens(style_tokens)
        self._plan_tokens = self._require_positive_int("plan_tokens", plan_tokens)

        environment = build_prompt_environment(_PROMPT_DIRECTORY)
        self._system_prompt = environment.get_template(_SYSTEM_TEMPLATE).render(
            owner_name=owner_name.strip(),
            markers=self._markers,
        )
        self._plan_prompt = environment.get_template(_PLAN_TEMPLATE).render(owner_name=owner_name.strip())
        self._user_template = environment.get_template(_USER_TEMPLATE)

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @property
    def plan_prompt(self) -> str:
        return self._plan_prompt

    @property
    def markers(self) -> Mapping[QueryScope, str]:
        return self._markers

    def build_user_prompt(
        self,
        message: str,
        history: Sequence[ChatMessage] = (),
        context: str = "",
        style: AnswerStyle | None = AnswerStyle.CONCISE,
    ) -> str:
        checked_history = require_conversation(message, history, InvalidAgentInputError)
        if not isinstance(context, str):
            raise InvalidAgentInputError("context must be a string")

        if style is not None and not isinstance(style, AnswerStyle):
            raise InvalidAgentInputError("style must be an AnswerStyle or None")

        return self._user_template.render(
            current_message=message,
            history=checked_history,
            context=context,
            surface=Surface.CLI,
            style="" if style is None else style.value,
        )

    def stream(
        self,
        message: str,
        history: Sequence[ChatMessage] = (),
        context: str = "",
        style: AnswerStyle = AnswerStyle.CONCISE,
    ) -> GroqChatCompletionStream:
        user_prompt = self.build_user_prompt(message, history, context, style)
        choice = self._model_selector.select()
        return self._groq_client.stream_chat_completion(
            self._request(choice, self._system_prompt, user_prompt, self._style_tokens[style], None)
        )

    def plan(self, message: str, history: Sequence[ChatMessage] = (), context: str = "") -> tuple[AgentPlan, GroqUsage | None]:
        user_prompt = self.build_user_prompt(message, history, context, None)
        choice = self._model_selector.select()
        response_format = _STRICT_PLAN_FORMAT if choice.supports_strict_json_schema else _JSON_OBJECT_FORMAT
        completion = self._groq_client.create_chat_completion(
            self._request(choice, self._plan_prompt, user_prompt, self._plan_tokens, response_format)
        )

        content = first_choice_content(completion)
        if content is None:
            raise AgentResponseError("Agent model returned no plan")

        try:
            return JsonExtractor.extract(content, AgentPlan), completion.usage
        except JsonExtractorError as error:
            raise AgentResponseError("Agent model did not return a valid plan") from error

    @staticmethod
    def _request(
        choice: ModelChoice,
        system_prompt: str,
        user_prompt: str,
        max_completion_tokens: int,
        response_format: GroqResponseFormat | None,
    ) -> GroqChatCompletionRequest:
        return GroqChatCompletionRequest(
            model=choice.model_id,
            messages=(
                GroqMessage(role="system", content=system_prompt),
                GroqMessage(role="user", content=user_prompt),
            ),
            temperature=choice.temperature,
            top_p=choice.top_p,
            max_completion_tokens=max_completion_tokens,
            reasoning_effort=choice.reasoning_effort,
            response_format=response_format,
        )

    @staticmethod
    def _require_positive_int(name: str, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InvalidAgentSettingError(f"{name} must be a positive int")

        return value

    @classmethod
    def _require_style_tokens(cls, style_tokens: Mapping[AnswerStyle, int]) -> Mapping[AnswerStyle, int]:
        if not isinstance(style_tokens, Mapping) or set(style_tokens) != set(AnswerStyle):
            raise InvalidAgentSettingError(f"style_tokens must map exactly {sorted(AnswerStyle)} to token limits")

        return MappingProxyType({style: cls._require_positive_int(f"style_tokens[{style}]", tokens) for style, tokens in style_tokens.items()})

    @staticmethod
    def _require_markers(markers: Mapping[QueryScope, str]) -> Mapping[QueryScope, str]:
        if not isinstance(markers, Mapping) or not markers:
            raise InvalidAgentSettingError("markers must be a non-empty mapping of QueryScope to marker")

        if not all(isinstance(scope, QueryScope) and scope is not QueryScope.IN_SCOPE for scope in markers):
            raise InvalidAgentSettingError("marker scopes must be QueryScope members other than IN_SCOPE")

        if not all(isinstance(marker, str) and marker.strip() == marker and marker for marker in markers.values()):
            raise InvalidAgentSettingError("every marker must be a non-empty string without surrounding whitespace")

        values = list(markers.values())
        if any(first != second and second.startswith(first) for first in values for second in values) or len(set(values)) != len(values):
            raise InvalidAgentSettingError("markers must be unique and none may be a prefix of another")

        return MappingProxyType(dict(markers))
