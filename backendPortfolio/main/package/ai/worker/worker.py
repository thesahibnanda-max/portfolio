from collections.abc import Sequence
from pathlib import Path

from main.package.ai.common.dto import ChatMessage
from main.package.ai.common.model_selector import ModelSelector
from main.package.ai.common.prompting import build_prompt_environment, first_choice_content, require_conversation
from main.package.ai.worker.exceptions import InvalidWorkerInputError, InvalidWorkerSettingError, WorkerResponseError
from main.package.clients.groq import (
    GroqChatCompletionRequest,
    GroqChatCompletionStream,
    GroqClient,
    GroqMessage,
)

_PROMPT_DIRECTORY = Path(__file__).parent
_SYSTEM_TEMPLATE = "system.md"
_USER_TEMPLATE = "user.md"


class Worker:
    def __init__(
        self,
        groq_client: GroqClient,
        model_selector: ModelSelector,
        *,
        owner_name: str,
        max_completion_tokens: int,
    ) -> None:
        if not isinstance(groq_client, GroqClient):
            raise InvalidWorkerSettingError("groq_client must be a GroqClient")

        if not isinstance(model_selector, ModelSelector):
            raise InvalidWorkerSettingError("model_selector must be a ModelSelector")

        if not isinstance(owner_name, str):
            raise InvalidWorkerSettingError("owner_name must be a string")

        if isinstance(max_completion_tokens, bool) or not isinstance(max_completion_tokens, int) or max_completion_tokens < 1:
            raise InvalidWorkerSettingError("max_completion_tokens must be a positive int")

        self._groq_client = groq_client
        self._model_selector = model_selector
        self._max_completion_tokens = max_completion_tokens

        environment = build_prompt_environment(_PROMPT_DIRECTORY)
        self._system_prompt = environment.get_template(_SYSTEM_TEMPLATE).render(owner_name=owner_name)
        self._user_template = environment.get_template(_USER_TEMPLATE)

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def build_user_prompt(self, message: str, history: Sequence[ChatMessage] = (), context: str = "") -> str:
        checked_history = require_conversation(message, history, InvalidWorkerInputError)
        if not isinstance(context, str):
            raise InvalidWorkerInputError("context must be a string")

        return self._user_template.render(current_message=message, history=checked_history, context=context)

    def respond(self, message: str, history: Sequence[ChatMessage] = (), context: str = "") -> str:
        completion = self._groq_client.create_chat_completion(self._build_request(message, history, context))

        content = first_choice_content(completion)
        if content is None:
            raise WorkerResponseError("Worker model returned no content")

        return content

    def stream(self, message: str, history: Sequence[ChatMessage] = (), context: str = "") -> GroqChatCompletionStream:
        return self._groq_client.stream_chat_completion(self._build_request(message, history, context))

    def _build_request(self, message: str, history: Sequence[ChatMessage], context: str) -> GroqChatCompletionRequest:
        user_prompt = self.build_user_prompt(message, history, context)
        choice = self._model_selector.select()

        return GroqChatCompletionRequest(
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
