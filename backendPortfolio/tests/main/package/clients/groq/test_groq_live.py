import json
import os
import random
from collections.abc import Iterator
from datetime import timedelta

import pytest

from main.package.clients.groq import (
    GroqChatCompletionRequest,
    GroqClient,
    GroqHTTPStatusError,
    GroqJsonObjectResponseFormat,
    GroqJsonSchema,
    GroqJsonSchemaResponseFormat,
    GroqMessage,
    GroqStreamEnd,
    GroqTextDelta,
)

GROQ_API_KEYS = tuple(key.strip() for key in os.environ.get("GROQ_API_KEYS", "").split(",") if key.strip())

pytestmark = pytest.mark.skipif(not GROQ_API_KEYS, reason="GROQ_API_KEYS is not set; real Groq tests are skipped")

MODEL = "llama-3.3-70b-versatile"
REQUEST = GroqChatCompletionRequest(
    model=MODEL,
    messages=[
        GroqMessage(role="system", content="Answer with one short sentence."),
        GroqMessage(role="user", content="Say hello to Sahib."),
    ],
    temperature=0,
    max_completion_tokens=40,
)


@pytest.fixture
def client() -> Iterator[GroqClient]:
    with GroqClient(
        base_url="https://api.groq.com",
        api_keys=[random.choice(GROQ_API_KEYS)],
        connect_timeout=timedelta(seconds=10),
        read_timeout=timedelta(seconds=60),
        write_timeout=timedelta(seconds=60),
        pool_timeout=timedelta(seconds=10),
    ) as groq_client:
        yield groq_client


def test_create_chat_completion(client: GroqClient) -> None:
    completion = client.create_chat_completion(REQUEST)

    assert completion.choices[0].message.content.strip()
    assert completion.choices[0].finish_reason in {"stop", "length"}
    assert completion.usage.total_tokens > 0


def test_stream_chat_completion(client: GroqClient) -> None:
    with client.stream_chat_completion(REQUEST) as stream:
        events = list(stream)

    deltas = [event for event in events if isinstance(event, GroqTextDelta)]
    end = events[-1]
    assert deltas
    assert isinstance(end, GroqStreamEnd)
    assert end.text == "".join(delta.text for delta in deltas)
    assert end.text.strip()
    assert end.finish_reason in {"stop", "length"}
    assert stream.completed is True


def test_unknown_model_is_an_http_error(client: GroqClient) -> None:
    request = REQUEST.model_copy(update={"model": "this-model-does-not-exist"})

    with pytest.raises(GroqHTTPStatusError) as error:
        client.create_chat_completion(request)

    assert 400 <= error.value.status_code < 500


def test_strict_json_schema_is_enforced(client: GroqClient) -> None:
    schema = {
        "type": "object",
        "properties": {"greeting": {"type": "string"}, "count": {"type": "integer"}},
        "required": ["greeting", "count"],
        "additionalProperties": False,
    }
    request = GroqChatCompletionRequest(
        model="openai/gpt-oss-20b",
        messages=[GroqMessage(role="user", content="Return a JSON greeting for Sahib and the number 3.")],
        reasoning_effort="low",
        max_completion_tokens=300,
        response_format=GroqJsonSchemaResponseFormat(json_schema=GroqJsonSchema(name="greeting", schema=schema, strict=True)),
    )

    payload = json.loads(client.create_chat_completion(request).choices[0].message.content)

    assert set(payload) == {"greeting", "count"}
    assert isinstance(payload["greeting"], str) and isinstance(payload["count"], int)


def test_json_object_mode_returns_json(client: GroqClient) -> None:
    request = REQUEST.model_copy(
        update={
            "messages": (GroqMessage(role="user", content='Reply with a JSON object {"ok": true}.'),),
            "response_format": GroqJsonObjectResponseFormat(),
        }
    )

    assert isinstance(json.loads(client.create_chat_completion(request).choices[0].message.content), dict)
