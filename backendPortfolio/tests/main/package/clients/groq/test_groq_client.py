import json
import random
from datetime import timedelta
from functools import partial

import httpx
import pytest
from pydantic import ValidationError

from main.config import AppConfig
from main.package.clients.groq import (
    GroqChatCompletion,
    GroqChatCompletionRequest,
    GroqChatCompletionStream,
    GroqClient,
    GroqClientError,
    GroqHTTPStatusError,
    GroqJsonObjectResponseFormat,
    GroqJsonSchema,
    GroqJsonSchemaResponseFormat,
    GroqJsonValidationError,
    GroqMessage,
    GroqRateLimitError,
    GroqRequestError,
    GroqResponseError,
    GroqStreamCancelledError,
    GroqStreamIncompleteError,
    GroqStreamStateError,
    GroqTool,
    GroqToolCall,
    GroqToolFunction,
    InvalidGroqClientSettingError,
    InvalidGroqRequestError,
)
from tests.conftest import HTTP_TIMEOUTS
from tests.main.package.clients.groq.sse import FULL_STREAM, FULL_TEXT, SSE_HEADERS
from tests.support import ConcurrentRunner, RecordingTransport, ResponseSpec

BASE_URL = "https://groq.test"
API_KEYS = ("key-one", "key-two", "key-three")
REQUEST = GroqChatCompletionRequest(
    model="llama-3.3-70b-versatile",
    messages=[GroqMessage(role="system", content="Be brief."), GroqMessage(role="user", content="Rating?")],
    temperature=0.8,
)
COMPLETION = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 1700000000,
    "model": "llama-3.3-70b-versatile",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "It is 1832."}, "finish_reason": "stop", "logprobs": None}],
    "usage": {"prompt_tokens": 30, "completion_tokens": 5, "total_tokens": 35, "queue_time": 0.01},
    "system_fingerprint": "fp_1",
    "x_groq": {"id": "req_1", "seed": 7},
    "service_tier": "on_demand",
    "unknown_field": True,
}


class FixedChoice:
    def __init__(self, index: int) -> None:
        self._index = index

    def __call__(self, options):
        return options[self._index]


def _client(transport: httpx.BaseTransport | None = None, **overrides: object) -> GroqClient:
    settings = {"base_url": BASE_URL, "api_keys": API_KEYS} | HTTP_TIMEOUTS | overrides
    return GroqClient(**settings, transport=transport)


def _completion_transport() -> RecordingTransport:
    return RecordingTransport(ResponseSpec(json=COMPLETION))


def _call_many(client: GroqClient, count: int) -> int:
    for _ in range(count):
        assert client.create_chat_completion(REQUEST).choices[0].message.content == "It is 1832."
    return count


def _stream_many(client: GroqClient, count: int) -> int:
    for _ in range(count):
        with client.stream_chat_completion(REQUEST) as stream:
            list(stream)
            assert stream.text == FULL_TEXT
    return count


def test_posts_to_chat_completions_with_bearer_key() -> None:
    transport = _completion_transport()
    with _client(transport) as client:
        client.create_chat_completion(REQUEST)

    request = transport.last_request
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/openai/v1/chat/completions"
    assert request.headers["authorization"] in {f"Bearer {key}" for key in API_KEYS}
    assert request.headers["content-type"] == "application/json"


@pytest.mark.parametrize("index", [0, 1, 2])
def test_each_request_uses_a_randomly_chosen_key(monkeypatch: pytest.MonkeyPatch, index: int) -> None:
    monkeypatch.setattr(random, "choice", FixedChoice(index))
    transport = _completion_transport()
    with _client(transport) as client:
        client.create_chat_completion(REQUEST)

    assert transport.last_request.headers["authorization"] == f"Bearer {API_KEYS[index]}"


def test_body_has_stream_false_and_omits_unset_fields() -> None:
    transport = _completion_transport()
    with _client(transport) as client:
        client.create_chat_completion(REQUEST)

    assert json.loads(transport.last_request.content) == {
        "messages": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Rating?"}],
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.8,
        "stream": False,
    }


def test_body_serialises_every_option_and_tools() -> None:
    request = GroqChatCompletionRequest(
        model="openai/gpt-oss-20b",
        messages=[
            GroqMessage(role="user", content="Weather?"),
            GroqMessage(role="assistant", tool_calls=[GroqToolCall.model_validate({"id": "c1", "type": "function", "function": {"name": "weather", "arguments": "{}"}})]),
            GroqMessage(role="tool", content="sunny", tool_call_id="c1"),
        ],
        temperature=0,
        max_completion_tokens=256,
        top_p=0.9,
        stop=["END"],
        reasoning_effort="medium",
        tools=[GroqTool(function=GroqToolFunction(name="weather", description="Get weather", parameters={"type": "object"}))],
    )
    transport = _completion_transport()
    with _client(transport) as client:
        client.create_chat_completion(request)

    body = json.loads(transport.last_request.content)
    assert body["max_completion_tokens"] == 256
    assert body["top_p"] == 0.9
    assert body["stop"] == ["END"]
    assert body["reasoning_effort"] == "medium"
    assert body["temperature"] == 0
    assert body["tools"] == [{"type": "function", "function": {"name": "weather", "description": "Get weather", "parameters": {"type": "object"}}}]
    assert body["messages"][1]["tool_calls"][0]["function"] == {"name": "weather", "arguments": "{}"}
    assert body["messages"][2] == {"role": "tool", "content": "sunny", "tool_call_id": "c1"}


def test_parses_completion() -> None:
    with _client(_completion_transport()) as client:
        completion = client.create_chat_completion(REQUEST)

    assert isinstance(completion, GroqChatCompletion)
    assert completion.choices[0].message.content == "It is 1832."
    assert completion.choices[0].finish_reason == "stop"
    assert completion.usage.total_tokens == 35
    assert completion.x_groq.seed == 7
    assert completion.service_tier == "on_demand"


def test_completion_is_frozen() -> None:
    with _client(_completion_transport()) as client:
        completion = client.create_chat_completion(REQUEST)

    with pytest.raises(ValidationError):
        completion.model = "other"


@pytest.mark.parametrize(("status", "error_type"), [(400, GroqHTTPStatusError), (401, GroqHTTPStatusError), (429, GroqRateLimitError), (500, GroqHTTPStatusError)])
def test_error_statuses_raise(status: int, error_type: type[Exception]) -> None:
    with _client(RecordingTransport(ResponseSpec(status, text="x" * 2000))) as client, pytest.raises(error_type) as error:
        client.create_chat_completion(REQUEST)

    assert type(error.value) is error_type
    assert error.value.status_code == status
    assert error.value.body == "x" * 500


def test_rate_limit_message_says_so() -> None:
    with _client(RecordingTransport(ResponseSpec(429, json={"error": "slow"}))) as client, pytest.raises(GroqRateLimitError, match="rate limit"):
        client.create_chat_completion(REQUEST)


@pytest.mark.parametrize("spec", [ResponseSpec(text="<html>"), ResponseSpec(json={"choices": "nope"}), ResponseSpec(json=[1, 2])])
def test_invalid_response_raises(spec: ResponseSpec) -> None:
    with _client(RecordingTransport(spec)) as client, pytest.raises(GroqResponseError) as error:
        client.create_chat_completion(REQUEST)

    assert isinstance(error.value.__cause__, ValidationError)


@pytest.mark.parametrize("transport_error", [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError])
def test_transport_errors_raise_request_error(transport_error: type[httpx.TransportError]) -> None:
    with _client(RecordingTransport(error=transport_error)) as client, pytest.raises(GroqRequestError) as error:
        client.create_chat_completion(REQUEST)

    assert isinstance(error.value.__cause__, transport_error)


@pytest.mark.parametrize("request_value", [{"model": "m", "messages": []}, None, "hello"])
@pytest.mark.parametrize("method", ["create_chat_completion", "stream_chat_completion"])
def test_request_must_be_the_request_dto(request_value: object, method: str) -> None:
    transport = _completion_transport()
    with _client(transport) as client, pytest.raises(InvalidGroqRequestError):
        getattr(client, method)(request_value)

    assert transport.requests == []


@pytest.mark.parametrize(
    "fields",
    [
        {"messages": [], "model": "m"},
        {"messages": [{"role": "user", "content": "x"}], "model": ""},
        {"messages": [{"role": "robot", "content": "x"}], "model": "m"},
        {"messages": [{"role": "user", "content": "x"}], "model": "m", "temperature": 2.5},
        {"messages": [{"role": "user", "content": "x"}], "model": "m", "top_p": 1.5},
        {"messages": [{"role": "user", "content": "x"}], "model": "m", "max_completion_tokens": 0},
        {"messages": [{"role": "user", "content": "x"}], "model": "m", "stop": ["a", "b", "c", "d", "e"]},
        {"messages": [{"role": "user", "content": "x"}], "model": "m", "stream": True},
        {"messages": [{"role": "user", "content": "x"}], "model": "m", "tools": [{"type": "retrieval", "function": {"name": "f"}}]},
    ],
)
def test_invalid_requests_are_rejected_when_built(fields: dict) -> None:
    with pytest.raises(ValidationError):
        GroqChatCompletionRequest.model_validate(fields)


def test_stream_returns_unsent_stream_object() -> None:
    transport = RecordingTransport(ResponseSpec(content=FULL_STREAM.encode(), headers=SSE_HEADERS))
    with _client(transport) as client:
        stream = client.stream_chat_completion(REQUEST)
        assert isinstance(stream, GroqChatCompletionStream)
        assert transport.requests == []

        with stream:
            list(stream)

    request = transport.last_request
    assert json.loads(request.content)["stream"] is True
    assert request.headers["accept"] == "text/event-stream"
    assert request.headers["authorization"] in {f"Bearer {key}" for key in API_KEYS}


@pytest.mark.parametrize("base_url", [BASE_URL, f"{BASE_URL}/"])
def test_base_url_has_no_trailing_slash(base_url: str) -> None:
    with _client(base_url=base_url) as client:
        assert client.base_url == BASE_URL


@pytest.mark.parametrize(
    "overrides",
    [
        {"api_keys": []},
        {"api_keys": ()},
        {"api_keys": "single-key-as-string"},
        {"api_keys": None},
        {"api_keys": ["ok", " "]},
        {"api_keys": ["ok", ""]},
        {"api_keys": ["ok", 5]},
        {"base_url": ""},
        {"base_url": "groq.com"},
        {"base_url": "https://"},
        {"base_url": "https://api.groq.com?x=1"},
        {"base_url": None},
        {"connect_timeout": timedelta(0)},
        {"read_timeout": 60},
        {"write_timeout": None},
        {"pool_timeout": timedelta(seconds=-1)},
    ],
)
def test_invalid_settings_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidGroqClientSettingError):
        _client(**overrides)


def test_settings_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        GroqClient(BASE_URL, API_KEYS, *HTTP_TIMEOUTS.values())


def test_api_keys_never_appear_in_repr_or_errors() -> None:
    with _client(RecordingTransport(ResponseSpec(401, json={"error": "invalid key"}))) as client:
        with pytest.raises(GroqHTTPStatusError) as error:
            client.create_chat_completion(REQUEST)
        text = f"{client!r} {error.value} {error.value.body}"

    assert all(key not in text for key in API_KEYS)


def test_closed_client_cannot_send() -> None:
    client = _client(_completion_transport())
    client.close()

    with pytest.raises(RuntimeError):
        client.create_chat_completion(REQUEST)


def test_one_client_is_safe_across_threads_for_both_methods() -> None:
    transport = RecordingTransport(
        routes={"/openai/v1/chat/completions": ResponseSpec(json=COMPLETION)},
    )
    stream_transport = RecordingTransport(ResponseSpec(content=FULL_STREAM.encode(), headers=SSE_HEADERS))
    with _client(transport) as plain, _client(stream_transport) as streaming:
        plain_runner = ConcurrentRunner(partial(_call_many, plain, 25), thread_count=8)
        stream_runner = ConcurrentRunner(partial(_stream_many, streaming, 25), thread_count=8)
        plain_runner.run()
        stream_runner.run()

    assert plain_runner.errors == [] and plain_runner.results == [25] * 8
    assert stream_runner.errors == [] and stream_runner.results == [25] * 8


def test_builds_from_app_config(config_env: str) -> None:
    config = AppConfig.load()
    with GroqClient(
        base_url=config.groq.base_url,
        api_keys=[key.get_secret_value() for key in config.groq.api_keys],
        **config.http_client.model_dump(),
    ) as client:
        assert client.base_url == "https://api.groq.com"


@pytest.mark.parametrize(
    "error_type",
    [
        InvalidGroqClientSettingError,
        InvalidGroqRequestError,
        GroqRequestError,
        GroqHTTPStatusError,
        GroqRateLimitError,
        GroqResponseError,
        GroqStreamIncompleteError,
        GroqStreamCancelledError,
        GroqStreamStateError,
    ],
)
def test_errors_share_the_client_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, GroqClientError)


def test_rate_limit_and_incomplete_errors_have_specific_parents() -> None:
    assert issubclass(GroqRateLimitError, GroqHTTPStatusError)
    assert issubclass(GroqStreamIncompleteError, GroqResponseError)


STRICT_FORMAT = GroqJsonSchemaResponseFormat(
    json_schema=GroqJsonSchema(
        name="decision",
        description="A routing decision",
        schema={"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"], "additionalProperties": False},
        strict=True,
    )
)


def test_json_schema_response_format_is_sent_in_groq_shape() -> None:
    transport = _completion_transport()
    request = REQUEST.model_copy(update={"response_format": STRICT_FORMAT})
    with _client(transport) as client:
        client.create_chat_completion(request)

    assert json.loads(transport.last_request.content)["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "decision",
            "description": "A routing decision",
            "schema": {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"], "additionalProperties": False},
            "strict": True,
        },
    }


def test_json_object_response_format_is_sent_in_groq_shape() -> None:
    transport = _completion_transport()
    with _client(transport) as client:
        client.create_chat_completion(REQUEST.model_copy(update={"response_format": GroqJsonObjectResponseFormat()}))

    assert json.loads(transport.last_request.content)["response_format"] == {"type": "json_object"}


def test_response_format_is_left_out_when_unset() -> None:
    transport = _completion_transport()
    with _client(transport) as client:
        client.create_chat_completion(REQUEST)

    assert "response_format" not in json.loads(transport.last_request.content)


def test_schema_description_is_optional_and_strict_defaults_to_false() -> None:
    schema = GroqJsonSchema(name="d", schema={"type": "object"})

    assert schema.strict is False
    assert schema.description is None
    assert GroqJsonSchema(name="d", schema_={"type": "object"}).schema_ == {"type": "object"}


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        ({"type": "json_object"}, GroqJsonObjectResponseFormat),
        ({"type": "json_schema", "json_schema": {"name": "d", "schema": {}, "strict": True}}, GroqJsonSchemaResponseFormat),
    ],
)
def test_response_format_parses_by_type(payload: dict, expected_type: type) -> None:
    request = GroqChatCompletionRequest.model_validate(
        {"model": "m", "messages": [{"role": "user", "content": "x"}], "response_format": payload}
    )

    assert isinstance(request.response_format, expected_type)


@pytest.mark.parametrize(
    "response_format",
    [
        {"type": "text"},
        {"type": "json_schema"},
        {"type": "json_schema", "json_schema": {"name": "bad name!", "schema": {}}},
        {"type": "json_schema", "json_schema": {"name": "x" * 65, "schema": {}}},
        {"type": "json_schema", "json_schema": {"name": "d"}},
        {"type": "json_object", "extra": 1},
    ],
)
def test_invalid_response_formats_are_rejected(response_format: dict) -> None:
    with pytest.raises(ValidationError):
        GroqChatCompletionRequest.model_validate(
            {"model": "m", "messages": [{"role": "user", "content": "x"}], "response_format": response_format}
        )


def test_response_format_with_tools_is_rejected() -> None:
    with pytest.raises(ValidationError, match="tools"):
        GroqChatCompletionRequest(
            model="m",
            messages=[GroqMessage(role="user", content="x")],
            tools=[GroqTool(function=GroqToolFunction(name="f"))],
            response_format=GroqJsonObjectResponseFormat(),
        )


@pytest.mark.parametrize("response_format", [GroqJsonObjectResponseFormat(), STRICT_FORMAT])
def test_structured_output_cannot_be_streamed(response_format) -> None:
    transport = _completion_transport()
    with _client(transport) as client, pytest.raises(InvalidGroqRequestError, match="streamed"):
        client.stream_chat_completion(REQUEST.model_copy(update={"response_format": response_format}))

    assert transport.requests == []


def test_json_validate_failed_raises_json_validation_error() -> None:
    body = {"error": {"message": "Generated JSON does not match the expected schema.", "type": "invalid_request_error", "code": "json_validate_failed", "failed_generation": "x" * 2000}}
    with _client(RecordingTransport(ResponseSpec(400, json=body))) as client, pytest.raises(GroqJsonValidationError) as error:
        client.create_chat_completion(REQUEST.model_copy(update={"response_format": STRICT_FORMAT}))

    assert isinstance(error.value, GroqHTTPStatusError)
    assert error.value.status_code == 400
    assert len(error.value.body) == 500
    assert "requested schema" in str(error.value)


@pytest.mark.parametrize(
    "spec",
    [
        ResponseSpec(400, json={"error": {"code": "invalid_api_request"}}),
        ResponseSpec(400, json={"error": "plain string"}),
        ResponseSpec(400, json=["not", "an", "object"]),
        ResponseSpec(400, json={"error": {"code": 5}}),
        ResponseSpec(400, text="not json"),
        ResponseSpec(422, json={"error": {"code": "json_validate_failed"}}),
    ],
)
def test_other_errors_are_not_json_validation_errors(spec: ResponseSpec) -> None:
    with _client(RecordingTransport(spec)) as client, pytest.raises(GroqHTTPStatusError) as error:
        client.create_chat_completion(REQUEST)

    assert type(error.value) is GroqHTTPStatusError


def test_json_validation_error_shares_the_status_base() -> None:
    assert issubclass(GroqJsonValidationError, GroqHTTPStatusError)
