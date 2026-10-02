import random
from collections import Counter
from functools import partial

import pytest
from pydantic import ValidationError

from main.package.ai.common import (
    AiCommonError,
    ChatMessage,
    ContextType,
    InvalidModelSelectorSettingError,
    LLMModel,
    ModelChoice,
    ModelSelector,
    first_choice_content,
    require_conversation,
)
from main.package.clients.groq import GroqChatCompletion
from tests.support import ConcurrentRunner

MODELS = (
    LLMModel(model_id="llama", weight=50),
    LLMModel(model_id="gpt-oss-20b", weight=20, reasoning_effort="medium"),
    LLMModel(model_id="model-c", weight=20, reasoning_effort="low", supports_strict_json_schema=True),
    LLMModel(model_id="gpt-oss-120b", weight=10, reasoning_effort="medium"),
)


class PickIndex:
    def __init__(self, index: int) -> None:
        self._index = index
        self.weights: list | None = None

    def __call__(self, population, weights, k):
        self.weights = list(weights)
        return [population[self._index]]


def _selector(**overrides: object) -> ModelSelector:
    settings = {"models": MODELS, "temperature_range": (0.8, 1.4), "top_p_range": (0.9, 1.0)} | overrides
    return ModelSelector(**settings)


def _select_many(selector: ModelSelector, count: int) -> int:
    for _ in range(count):
        choice = selector.select()
        assert 0.8 <= choice.temperature <= 1.4
    return count


def test_context_types_are_in_canonical_order() -> None:
    assert list(ContextType) == [
        ContextType.PROFILE,
        ContextType.GITHUB,
        ContextType.LEETCODE,
        ContextType.CODEFORCES,
        ContextType.PERSONALITY,
        ContextType.NONE,
    ]


@pytest.mark.parametrize(
    ("context_type", "starts_with"),
    [
        (ContextType.PROFILE, "Resume:"),
        (ContextType.GITHUB, "GitHub profile:"),
        (ContextType.LEETCODE, "LeetCode competitive programming profile:"),
        (ContextType.CODEFORCES, "Codeforces competitive programming profile:"),
        (ContextType.PERSONALITY, "Non-technical personal profile:"),
        (ContextType.NONE, "General question requiring no personal context"),
    ],
)
def test_every_context_type_has_a_description(context_type: ContextType, starts_with: str) -> None:
    assert context_type.description.startswith(starts_with)
    assert context_type == context_type.name


@pytest.mark.parametrize("fields", [{"role": "system", "content": "x"}, {"role": "user", "content": ""}, {"role": "user"}, {"role": "user", "content": "x", "extra": 1}])
def test_invalid_chat_messages_are_rejected(fields: dict) -> None:
    with pytest.raises(ValidationError):
        ChatMessage.model_validate(fields)


def test_chat_message_is_frozen() -> None:
    message = ChatMessage(role="user", content="hi")

    with pytest.raises(ValidationError):
        message.content = "changed"


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_select_uses_weighted_choice(monkeypatch: pytest.MonkeyPatch, index: int) -> None:
    picker = PickIndex(index)
    monkeypatch.setattr(random, "choices", picker)
    choice = _selector().select()

    assert picker.weights == [50, 20, 20, 10]
    assert choice.model_id == MODELS[index].model_id
    assert choice.reasoning_effort == MODELS[index].reasoning_effort
    assert choice.supports_strict_json_schema == MODELS[index].supports_strict_json_schema


def test_strict_json_schema_flag_defaults_to_false() -> None:
    assert LLMModel(model_id="x", weight=1).supports_strict_json_schema is False


def test_weights_hold_over_many_picks() -> None:
    selector = _selector()
    counts = Counter(selector.select().model_id for _ in range(10_000))

    assert counts["llama"] == pytest.approx(5000, abs=300)
    assert counts["gpt-oss-20b"] == pytest.approx(2000, abs=250)
    assert counts["model-c"] == pytest.approx(2000, abs=250)
    assert counts["gpt-oss-120b"] == pytest.approx(1000, abs=200)


def test_random_sampling_stays_in_range() -> None:
    selector = _selector()
    choices = [selector.select() for _ in range(500)]

    assert all(0.8 <= choice.temperature <= 1.4 for choice in choices)
    assert all(0.9 <= choice.top_p <= 1.0 for choice in choices)
    assert len({choice.temperature for choice in choices}) > 1


def test_fixed_sampling_overrides_the_range() -> None:
    choice = _selector().select(temperature=0, top_p=1)

    assert isinstance(choice, ModelChoice)
    assert (choice.temperature, choice.top_p) == (0.0, 1.0)


def test_single_value_range_returns_that_value() -> None:
    choice = _selector(temperature_range=(1.0, 1.0), top_p_range=(0.5, 0.5)).select()

    assert (choice.temperature, choice.top_p) == (1.0, 0.5)


@pytest.mark.parametrize(("field", "value"), [("temperature", 2.5), ("temperature", -0.1), ("top_p", 1.1), ("top_p", True), ("temperature", "0")])
def test_fixed_sampling_out_of_bounds_is_rejected(field: str, value: object) -> None:
    with pytest.raises(InvalidModelSelectorSettingError):
        _selector().select(**{field: value})


@pytest.mark.parametrize(
    "overrides",
    [
        {"models": ()},
        {"models": "llama"},
        {"models": None},
        {"models": ({"model_id": "x", "weight": 1},)},
        {"models": (LLMModel(model_id="same", weight=1), LLMModel(model_id="same", weight=2))},
        {"temperature_range": (1.4, 0.8)},
        {"temperature_range": (0.0, 2.5)},
        {"temperature_range": (0.5,)},
        {"temperature_range": "0.8-1.4"},
        {"top_p_range": (0.9, 1.1)},
        {"top_p_range": (True, 1.0)},
    ],
)
def test_invalid_settings_are_rejected(overrides: dict) -> None:
    with pytest.raises(InvalidModelSelectorSettingError):
        _selector(**overrides)


def test_llm_model_validation() -> None:
    with pytest.raises(ValidationError):
        LLMModel(model_id="x", weight=0)
    with pytest.raises(ValidationError):
        LLMModel(model_id="", weight=1)


def test_models_property_returns_a_tuple() -> None:
    assert _selector(models=list(MODELS)).models == MODELS


def test_selector_is_safe_across_threads() -> None:
    runner = ConcurrentRunner(partial(_select_many, _selector(), 200)).run()

    assert runner.errors == []
    assert runner.results == [200] * 16


def test_require_conversation_returns_a_tuple() -> None:
    history = [ChatMessage(role="user", content="hi")]

    assert require_conversation("question", history, ValueError) == tuple(history)


@pytest.mark.parametrize(("message", "history"), [("", ()), ("  ", ()), (None, ()), ("q", "not a list"), ("q", None), ("q", [{"role": "user", "content": "hi"}])])
def test_require_conversation_raises_the_given_error(message: object, history: object) -> None:
    with pytest.raises(LookupError):
        require_conversation(message, history, LookupError)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"choices": [{"message": {"content": "answer"}}]}, "answer"),
        ({"choices": []}, None),
        ({}, None),
        ({"choices": [{"delta": {"content": "x"}}]}, None),
        ({"choices": [{"message": {"content": "  "}}]}, None),
        ({"choices": [{"message": {"role": "assistant"}}]}, None),
    ],
)
def test_first_choice_content(payload: dict, expected: str | None) -> None:
    assert first_choice_content(GroqChatCompletion.model_validate(payload)) == expected


def test_errors_share_the_base() -> None:
    assert issubclass(InvalidModelSelectorSettingError, AiCommonError)
