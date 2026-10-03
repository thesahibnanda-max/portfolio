from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from main.package.ai.agent.exceptions import InvalidAgentInputError, InvalidAgentSettingError
from main.package.ai.common.dto import ChatMessage
from main.package.ai.common.model_selector import ModelSelector
from main.package.ai.common.prompting import build_prompt_environment, require_conversation
from main.package.ai.orchestrator import QueryScope
from main.package.clients.groq import GroqChatCompletionRequest, GroqChatCompletionStream, GroqClient, GroqMessage

_PROMPT_DIRECTORY = Path(__file__).parent
_SYSTEM_TEMPLATE = "system.md"
_USER_TEMPLATE = "user.md"


class Agent:
    def __init__(
        self,
        groq_client: GroqClient,
        model_selector: ModelSelector,
        *,
        owner_name: str,
        markers: Mapping[QueryScope, str],
        max_completion_tokens: int,
    ) -> None:
        if not isinstance(groq_client, GroqClient):
            raise InvalidAgentSettingError("groq_client must be a GroqClient")

        if not isinstance(model_selector, ModelSelector):
            raise InvalidAgentSettingError("model_selector must be a ModelSelector")

        if not isinstance(owner_name, str) or not owner_name.strip():
            raise InvalidAgentSettingError("owner_name must be a non-blank string")

        if isinstance(max_completion_tokens, bool) or not isinstance(max_completion_tokens, int) or max_completion_tokens < 1:
            raise InvalidAgentSettingError("max_completion_tokens must be a positive int")

        self._groq_client = groq_client
        self._model_selector = model_selector
        self._markers = self._require_markers(markers)
        self._max_completion_tokens = max_completion_tokens

        environment = build_prompt_environment(_PROMPT_DIRECTORY)
        self._system_prompt = environment.get_template(_SYSTEM_TEMPLATE).render(
            owner_name=owner_name.strip(),
            markers=self._markers,
        )
        self._user_template = environment.get_template(_USER_TEMPLATE)

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @property
    def markers(self) -> Mapping[QueryScope, str]:
        return self._markers

    def build_user_prompt(self, message: str, history: Sequence[ChatMessage] = (), context: str = "") -> str:
        checked_history = require_conversation(message, history, InvalidAgentInputError)
        if not isinstance(context, str):
            raise InvalidAgentInputError("context must be a string")

        return self._user_template.render(current_message=message, history=checked_history, context=context)

    def stream(self, message: str, history: Sequence[ChatMessage] = (), context: str = "") -> GroqChatCompletionStream:
        user_prompt = self.build_user_prompt(message, history, context)
        choice = self._model_selector.select()

        return self._groq_client.stream_chat_completion(
            GroqChatCompletionRequest(
                model=choice.model_id,
                messages=(
                    GroqMessage(role="system", content=self._system_prompt),
                    GroqMessage(role="user", content=user_prompt),
                ),
                temperature=choice.temperature,
                top_p=choice.top_p,
                max_completion_tokens=self._max_completion_tokens,
                reasoning_effort=choice.reasoning_effort,
            )
        )

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
