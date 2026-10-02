import json
from typing import Any

import httpx

from main.package.ai.common import LLMModel, ModelSelector
from main.package.clients.groq import GroqClient
from tests.conftest import HTTP_TIMEOUTS
from tests.support import RecordingTransport, ResponseSpec

OWNER_NAME = "Sahib Nanda"
MODELS = (
    LLMModel(model_id="llama-3.3-70b-versatile", weight=1),
    LLMModel(model_id="openai/gpt-oss-20b", weight=1, reasoning_effort="medium", supports_strict_json_schema=True),
)


def completion(content: str | None) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant"}
    if content is not None:
        message["content"] = content
    return {"id": "c1", "choices": [{"index": 0, "message": message, "finish_reason": "stop"}]}


def answering(content: str | None) -> RecordingTransport:
    return RecordingTransport(ResponseSpec(json=completion(content)))


def groq_client(transport: httpx.BaseTransport) -> GroqClient:
    return GroqClient(base_url="https://groq.test", api_keys=["key"], transport=transport, **HTTP_TIMEOUTS)


def selector(**overrides: object) -> ModelSelector:
    settings = {"models": MODELS, "temperature_range": (0.8, 1.4), "top_p_range": (0.9, 1.0)} | overrides
    return ModelSelector(**settings)


def sent_body(transport: RecordingTransport) -> dict[str, Any]:
    return json.loads(transport.last_request.content)
