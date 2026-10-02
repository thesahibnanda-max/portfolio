from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _GroqResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class _GroqRequestModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GroqFunctionCall(_GroqResponseModel):
    name: str | None = None
    arguments: str | None = None


class GroqToolCall(_GroqResponseModel):
    id: str | None = None
    type: str | None = None
    function: GroqFunctionCall | None = None


class GroqResponseMessage(_GroqResponseModel):
    role: str | None = None
    content: str | None = None
    tool_calls: tuple[GroqToolCall, ...] | None = None


class GroqDelta(_GroqResponseModel):
    role: str | None = None
    content: str | None = None
    tool_calls: tuple[GroqToolCall, ...] | None = None


class GroqChoice(_GroqResponseModel):
    index: int | None = None
    message: GroqResponseMessage | None = None
    delta: GroqDelta | None = None
    finish_reason: str | None = None
    logprobs: Any = None


class GroqUsage(_GroqResponseModel):
    queue_time: float | None = None
    prompt_tokens: int | None = None
    prompt_time: float | None = None
    completion_tokens: int | None = None
    completion_time: float | None = None
    total_tokens: int | None = None
    total_time: float | None = None


class GroqXGroq(_GroqResponseModel):
    id: str | None = None
    seed: int | None = None
    usage: GroqUsage | None = None


class GroqChatCompletion(_GroqResponseModel):
    id: str | None = None
    object: str | None = None
    created: int | None = None
    model: str | None = None
    choices: tuple[GroqChoice, ...] | None = None
    usage: GroqUsage | None = None
    system_fingerprint: str | None = None
    x_groq: GroqXGroq | None = None
    service_tier: str | None = None


class GroqToolFunction(_GroqRequestModel):
    name: Annotated[str, Field(min_length=1)]
    description: str | None = None
    parameters: Mapping[str, Any] | None = None


class GroqTool(_GroqRequestModel):
    type: Literal["function"] = "function"
    function: GroqToolFunction


class GroqMessage(_GroqRequestModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[GroqToolCall, ...] | None = None


class GroqJsonObjectResponseFormat(_GroqRequestModel):
    type: Literal["json_object"] = "json_object"


class GroqJsonSchema(_GroqRequestModel):
    model_config = ConfigDict(frozen=True, extra="forbid", validate_by_alias=True, validate_by_name=True)

    name: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]
    description: str | None = None
    schema_: Annotated[Mapping[str, Any], Field(alias="schema")]
    strict: bool = False


class GroqJsonSchemaResponseFormat(_GroqRequestModel):
    type: Literal["json_schema"] = "json_schema"
    json_schema: GroqJsonSchema


type GroqResponseFormat = Annotated[
    GroqJsonObjectResponseFormat | GroqJsonSchemaResponseFormat,
    Field(discriminator="type"),
]


class GroqChatCompletionRequest(_GroqRequestModel):
    messages: Annotated[tuple[GroqMessage, ...], Field(min_length=1)]
    model: Annotated[str, Field(min_length=1)]
    temperature: Annotated[float, Field(ge=0, le=2)] | None = None
    max_completion_tokens: Annotated[int, Field(ge=1)] | None = None
    top_p: Annotated[float, Field(ge=0, le=1)] | None = None
    stop: Annotated[tuple[str, ...], Field(max_length=4)] | None = None
    reasoning_effort: Annotated[str, Field(min_length=1)] | None = None
    tools: tuple[GroqTool, ...] | None = None
    response_format: GroqResponseFormat | None = None

    @model_validator(mode="after")
    def _reject_response_format_with_tools(self) -> "GroqChatCompletionRequest":
        if self.response_format is not None and self.tools:
            raise ValueError("response_format cannot be combined with tools; Groq does not support both")

        return self


class GroqTextDelta(_GroqResponseModel):
    text: str


class GroqStreamEnd(_GroqResponseModel):
    text: str
    finish_reason: str | None = None
    usage: GroqUsage | None = None


type GroqStreamEvent = GroqTextDelta | GroqStreamEnd
