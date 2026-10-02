from functools import partial
from importlib import resources

import pytest
from jinja2 import UndefinedError

from main.package.ai.common import ChatMessage, ContextType
from main.package.ai.common.prompting import build_prompt_environment
from main.package.ai.orchestrator import (
    InvalidOrchestratorInputError,
    InvalidOrchestratorSettingError,
    Orchestrator,
    OrchestratorDecision,
    OrchestratorError,
    OrchestratorResponseError,
    QueryScope,
)
from main.package.ai.orchestrator import orchestrator as orchestrator_module
from main.package.clients.groq import GroqHTTPStatusError, GroqJsonValidationError
from main.package.json_extract import JsonExtractionError
from tests.main.package.ai.fakes import OWNER_NAME, answering, groq_client, selector, sent_body
from tests.support import ConcurrentRunner, RecordingTransport, ResponseSpec

HISTORY = (
    ChatMessage(role="user", content="Who is he?"),
    ChatMessage(role="assistant", content="A backend engineer."),
)


def _orchestrator(transport=None, **overrides: object) -> Orchestrator:
    settings = {"owner_name": OWNER_NAME, "temperature": 0.0, "top_p": 1.0, "max_completion_tokens": 2048} | overrides
    return Orchestrator(groq_client(transport or answering('{"scope": "IN_SCOPE", "requiredContexts": ["NONE"], "reason": "r"}')), selector(), **settings)


def _route_many(orchestrator: Orchestrator, count: int) -> int:
    for _ in range(count):
        assert orchestrator.route("rating?").required_contexts == (ContextType.CODEFORCES,)
    return count


def test_prompts_are_embedded_md_files() -> None:
    package = resources.files("main.package.ai.orchestrator")

    assert package.joinpath("system.md").read_text().startswith("You are the Orchestrator AI")
    assert "Current message:" in package.joinpath("user.md").read_text()


def test_system_prompt_names_owner_and_lists_every_domain_in_order() -> None:
    prompt = _orchestrator().system_prompt
    domain_block = prompt.split("Available knowledge domains:\n", 1)[1].split("\n\n", 1)[0]
    domain_lines = domain_block.splitlines()

    assert prompt.startswith(f"You are the Orchestrator AI inside {OWNER_NAME}'s Personal Portfolio AI system")
    assert domain_lines == [f"- {context.name}: {context.description}" for context in ContextType]
    assert prompt.rstrip().endswith('{"scope": "IN_SCOPE", "requiredContexts": ["DOMAIN_NAME", ...], "reason": "short explanation of why"}')
    assert "Never select NONE together with any other domain." in prompt
    assert "\n\n\n" not in prompt
    assert "{{" not in prompt and "{%" not in prompt


def test_user_prompt_without_history() -> None:
    assert _orchestrator().build_user_prompt("What is his rating?") == "Current message:\nWhat is his rating?"


def test_user_prompt_with_history() -> None:
    assert _orchestrator().build_user_prompt("And GitHub?", HISTORY) == (
        "Conversation so far:\nUSER: Who is he?\nASSISTANT: A backend engineer.\n\nCurrent message:\nAnd GitHub?"
    )


def test_route_sends_fixed_sampling_selected_model_and_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = answering('{"scope": "IN_SCOPE", "requiredContexts": ["PROFILE"], "reason": "resume"}')
    orchestrator = _orchestrator(transport)
    orchestrator.route("Where does he work?", HISTORY)
    body = sent_body(transport)

    assert body["temperature"] == 0.0
    assert body["top_p"] == 1.0
    assert body["max_completion_tokens"] == 2048
    assert body["stream"] is False
    assert body["model"] in {"llama-3.3-70b-versatile", "openai/gpt-oss-20b"}
    assert body.get("reasoning_effort") == ("medium" if body["model"] == "openai/gpt-oss-20b" else None)
    assert body["messages"] == [
        {"role": "system", "content": orchestrator.system_prompt},
        {"role": "user", "content": orchestrator.build_user_prompt("Where does he work?", HISTORY)},
    ]


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ('{"scope": "IN_SCOPE", "requiredContexts": ["CODEFORCES"], "reason": "rating"}', (ContextType.CODEFORCES,)),
        ('```json\n{"scope": "IN_SCOPE", "requiredContexts": ["GITHUB"], "reason": "repos"}\n```', (ContextType.GITHUB,)),
        ('Routing: {"scope": "IN_SCOPE", "requiredContexts": ["leetcode", " Codeforces "], "reason": "cp"} ok', (ContextType.LEETCODE, ContextType.CODEFORCES)),
        ("{'scope': 'IN_SCOPE', 'requiredContexts': ['PERSONALITY'], 'reason': 'hobbies'}", (ContextType.PERSONALITY,)),
        ('{"scope": " in_scope ", "required_contexts": ["PROFILE"], "reason": "snake case keys"}', (ContextType.PROFILE,)),
    ],
)
def test_route_parses_decisions_in_many_shapes(reply: str, expected: tuple) -> None:
    decision = _orchestrator(answering(reply)).route("q")

    assert isinstance(decision, OrchestratorDecision)
    assert decision.required_contexts == expected


@pytest.mark.parametrize(
    ("contexts", "expected"),
    [
        (["PERSONALITY", "PROFILE", "PROFILE"], (ContextType.PROFILE, ContextType.PERSONALITY)),
        (["CODEFORCES", "GITHUB", "LEETCODE"], (ContextType.GITHUB, ContextType.LEETCODE, ContextType.CODEFORCES)),
        (["NONE", "GITHUB"], (ContextType.GITHUB,)),
        (["NONE", "NONE"], (ContextType.NONE,)),
        ([], (ContextType.NONE,)),
    ],
)
def test_route_normalises_the_decision(contexts: list[str], expected: tuple) -> None:
    reply = f'{{"scope": "IN_SCOPE", "requiredContexts": {contexts!r}, "reason": "r"}}'.replace("'", '"')

    assert _orchestrator(answering(reply)).route("q").required_contexts == expected


def test_reason_is_stripped_and_defaults_to_empty() -> None:
    assert _orchestrator(answering('{"scope": "IN_SCOPE", "requiredContexts": ["NONE"], "reason": "  why  "}')).route("q").reason == "why"
    assert _orchestrator(answering('{"scope": "IN_SCOPE", "requiredContexts": ["NONE"]}')).route("q").reason == ""


def test_needs_context() -> None:
    assert OrchestratorDecision(scope=QueryScope.IN_SCOPE, required_contexts=(ContextType.NONE,), reason="").needs_context is False
    assert OrchestratorDecision(scope=QueryScope.IN_SCOPE, required_contexts=(ContextType.GITHUB,), reason="").needs_context is True
    assert OrchestratorDecision(scope=QueryScope.UNSAFE, required_contexts=(), reason="").needs_context is False


@pytest.mark.parametrize("reply", ["I think you need the profile.", '{"scope": "IN_SCOPE", "requiredContexts": ["SALARY"], "reason": "x"}', '{"reason": "no contexts"}'])
def test_unusable_reply_raises_response_error(reply: str) -> None:
    with pytest.raises(OrchestratorResponseError) as error:
        _orchestrator(answering(reply)).route("q")

    assert isinstance(error.value.__cause__, JsonExtractionError)


@pytest.mark.parametrize("content", [None, "", "   "])
def test_empty_reply_raises_response_error(content: str | None) -> None:
    with pytest.raises(OrchestratorResponseError, match="no content"):
        _orchestrator(answering(content)).route("q")


def test_no_choices_raises_response_error() -> None:
    with pytest.raises(OrchestratorResponseError):
        _orchestrator(RecordingTransport(ResponseSpec(json={"choices": []}))).route("q")


def test_groq_errors_pass_through() -> None:
    with pytest.raises(GroqHTTPStatusError):
        _orchestrator(RecordingTransport(ResponseSpec(500, text="down"))).route("q")


@pytest.mark.parametrize(("message", "history"), [("", ()), ("   ", ()), (None, ()), ("q", "history"), ("q", [{"role": "user", "content": "x"}])])
def test_invalid_input_is_rejected_before_calling_groq(message: object, history: object) -> None:
    transport = answering("{}")

    with pytest.raises(InvalidOrchestratorInputError):
        _orchestrator(transport).route(message, history)

    assert transport.requests == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"temperature": 2.5},
        {"temperature": -1},
        {"temperature": True},
        {"top_p": 1.5},
        {"top_p": "1"},
        {"max_completion_tokens": 0},
        {"max_completion_tokens": 1.5},
        {"max_completion_tokens": True},
        {"owner_name": None},
    ],
)
def test_invalid_settings_are_rejected(overrides: dict) -> None:
    with pytest.raises(InvalidOrchestratorSettingError):
        _orchestrator(**overrides)


def test_dependencies_must_have_the_right_types() -> None:
    with pytest.raises(InvalidOrchestratorSettingError, match="groq_client"):
        Orchestrator("client", selector(), owner_name="x", temperature=0, top_p=1, max_completion_tokens=1)
    with pytest.raises(InvalidOrchestratorSettingError, match="model_selector"):
        Orchestrator(groq_client(answering("{}")), "selector", owner_name="x", temperature=0, top_p=1, max_completion_tokens=1)


def test_templates_fail_loudly_on_missing_variables() -> None:
    template = build_prompt_environment(orchestrator_module._PROMPT_DIRECTORY).get_template("user.md")

    with pytest.raises(UndefinedError):
        template.render(history=())


def test_one_orchestrator_serves_parallel_threads() -> None:
    orchestrator = _orchestrator(answering('{"scope": "IN_SCOPE", "requiredContexts": ["CODEFORCES"], "reason": "r"}'))
    runner = ConcurrentRunner(partial(_route_many, orchestrator, 25)).run()

    assert runner.errors == []
    assert runner.results == [25] * 16


@pytest.mark.parametrize("error_type", [InvalidOrchestratorSettingError, InvalidOrchestratorInputError, OrchestratorResponseError])
def test_errors_share_the_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, OrchestratorError)


class PickModel:
    def __init__(self, model_id: str) -> None:
        self._model_id = model_id

    def __call__(self, population, weights, k):
        return [next(model for model in population if model.model_id == self._model_id)]


EXPECTED_STRICT_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "orchestrator_decision",
        "schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["IN_SCOPE", "NOT_RELATED_TO_PORTFOLIO", "PROMPT_INJECTION", "UNSAFE"]},
                "requiredContexts": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["PROFILE", "GITHUB", "LEETCODE", "CODEFORCES", "PERSONALITY", "NONE"]},
                },
                "reason": {"type": "string"},
            },
            "required": ["scope", "requiredContexts", "reason"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


def test_strict_capable_model_gets_strict_json_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("random.choices", PickModel("openai/gpt-oss-20b"))
    transport = answering('{"scope": "IN_SCOPE", "requiredContexts": ["GITHUB"], "reason": "repos"}')

    assert _orchestrator(transport).route("Show his repos").required_contexts == (ContextType.GITHUB,)
    body = sent_body(transport)
    assert body["model"] == "openai/gpt-oss-20b"
    assert body["response_format"] == EXPECTED_STRICT_FORMAT


def test_other_models_get_json_object_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("random.choices", PickModel("llama-3.3-70b-versatile"))
    transport = answering('```json\n{"scope": "IN_SCOPE", "requiredContexts": ["PROFILE"], "reason": "resume"}\n```')

    assert _orchestrator(transport).route("Where did he study?").required_contexts == (ContextType.PROFILE,)
    body = sent_body(transport)
    assert body["model"] == "llama-3.3-70b-versatile"
    assert body["response_format"] == {"type": "json_object"}


def test_schema_enum_lists_every_context_type() -> None:
    enum = orchestrator_module._DECISION_SCHEMA["properties"]["requiredContexts"]["items"]["enum"]

    assert enum == [context.name for context in ContextType]


def test_decision_schema_is_read_only() -> None:
    with pytest.raises(TypeError):
        orchestrator_module._DECISION_SCHEMA["type"] = "array"


def test_system_prompt_still_asks_for_json_for_json_object_mode() -> None:
    assert "JSON" in _orchestrator().system_prompt


def test_json_validation_errors_pass_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("random.choices", PickModel("openai/gpt-oss-20b"))
    transport = RecordingTransport(ResponseSpec(400, json={"error": {"code": "json_validate_failed", "message": "no match"}}))

    with pytest.raises(GroqJsonValidationError):
        _orchestrator(transport).route("q")


@pytest.mark.parametrize("scope", [QueryScope.NOT_RELATED_TO_PORTFOLIO, QueryScope.PROMPT_INJECTION, QueryScope.UNSAFE])
def test_out_of_scope_verdicts_have_no_contexts(scope: QueryScope) -> None:
    reply = f'{{"scope": "{scope.value}", "requiredContexts": ["PROFILE", "GITHUB"], "reason": "off topic"}}'
    decision = _orchestrator(answering(reply)).route("Explain taxes")

    assert decision.scope is scope
    assert decision.is_in_scope is False
    assert decision.required_contexts == ()
    assert decision.needs_context is False


def test_in_scope_without_contexts_becomes_none() -> None:
    decision = _orchestrator(answering('{"scope": "IN_SCOPE", "requiredContexts": [], "reason": "greeting"}')).route("hi")

    assert decision.is_in_scope is True
    assert decision.required_contexts == (ContextType.NONE,)


@pytest.mark.parametrize("scope_text", ["in_scope", " In_Scope ", "IN_SCOPE"])
def test_scope_is_read_in_any_case(scope_text: str) -> None:
    reply = f'{{"scope": "{scope_text}", "requiredContexts": ["GITHUB"], "reason": "r"}}'

    assert _orchestrator(answering(reply)).route("repos?").scope is QueryScope.IN_SCOPE


@pytest.mark.parametrize(
    "reply",
    [
        '{"requiredContexts": ["GITHUB"], "reason": "no scope"}',
        '{"scope": "MAYBE", "requiredContexts": [], "reason": "unknown scope"}',
        '{"scope": 5, "requiredContexts": [], "reason": "not a string"}',
    ],
)
def test_missing_or_unknown_scope_is_not_a_decision(reply: str) -> None:
    with pytest.raises(OrchestratorResponseError):
        _orchestrator(answering(reply)).route("q")


def test_prompt_defines_every_scope_and_the_bias_rule() -> None:
    prompt = _orchestrator().system_prompt

    assert all(f"- {scope.value}:" in prompt for scope in QueryScope)
    assert "never refuse a question that is about Sahib Nanda" in prompt
    assert "Whenever you are unsure, choose IN_SCOPE." in prompt
    assert prompt.index("Highest-priority rule") < prompt.index("Step 1")
    assert "requiredContexts must be an empty list" in prompt


def test_query_scope_values() -> None:
    assert [scope.value for scope in QueryScope] == ["IN_SCOPE", "NOT_RELATED_TO_PORTFOLIO", "PROMPT_INJECTION", "UNSAFE"]
