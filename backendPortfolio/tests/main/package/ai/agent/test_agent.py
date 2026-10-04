import json
import tomllib
from importlib import resources
from pathlib import Path

import pytest

from main.package.ai.agent import (
    Agent,
    AgentError,
    AgentPlan,
    AgentResponseError,
    AnswerStyle,
    InvalidAgentInputError,
    InvalidAgentSettingError,
    PlanStep,
)
from main.package.ai.common import ChatMessage, LLMModel
from main.package.ai.orchestrator import QueryScope
from main.package.clients.groq import GroqChatCompletionStream, GroqStreamEnd, GroqTextDelta
from tests.main.package.ai.agent.fakes import MARKERS, STYLE_TOKENS, agent, streaming
from tests.main.package.ai.fakes import OWNER_NAME, answering, completion, groq_client, selector
from tests.support import RecordingTransport, ResponseSpec

HISTORY = (ChatMessage(role="user", content="Who is he?"), ChatMessage(role="assistant", content="An engineer."))
SURFACE = "Surface: Portfolio Agent CLI terminal at /cli\n\n"
PLAN_JSON = json.dumps(
    {
        "scope": "IN_SCOPE",
        "summary": "Shows his backend work",
        "steps": [{"command": "/projects relay", "reason": "his flagship Go project"}],
    }
)


def _with_usage(content: str) -> dict:
    return completion(content) | {"usage": {"prompt_tokens": 800, "completion_tokens": 60, "total_tokens": 860}}


def test_prompts_are_embedded_md_files() -> None:
    package = resources.files("main.package.ai.agent")

    assert "Portfolio Agent" in package.joinpath("system.md").read_text()
    assert "Current message:" in package.joinpath("user.md").read_text()
    assert "planner" in package.joinpath("plan.md").read_text()


def test_system_prompt_names_the_owner_and_every_marker() -> None:
    prompt = agent().system_prompt

    assert prompt.startswith(f"You are the Portfolio Agent: a command-line assistant inside {OWNER_NAME}'s portfolio terminal.")
    assert "never hallucinate" in prompt
    for marker in MARKERS.values():
        assert f"reply with exactly {marker} and nothing else" in prompt
    assert "follow the answer style" in prompt
    assert "{%" not in prompt and "{{" not in prompt and "\n\n\n" not in prompt
    assert agent().markers == MARKERS


def test_plan_prompt_asks_for_known_commands_only() -> None:
    prompt = agent().plan_prompt

    assert prompt.startswith(f"You are the planner of the Portfolio Agent: a command-line assistant inside {OWNER_NAME}'s")
    assert "Never invent a command" in prompt and "{{" not in prompt


def test_user_prompt_has_surface_context_history_style_and_question() -> None:
    prompt = agent().build_user_prompt("Rating?", HISTORY, "PROFILE:\nName: Sahib")

    assert prompt == (
        SURFACE
        + "Context:\nPROFILE:\nName: Sahib\n\nConversation so far:\nUSER: Who is he?\nASSISTANT: An engineer.\n\n"
        + "Answer style: concise -- lead with the answer, at most about 120 words.\nCurrent message:\nRating?"
    )
    assert "Answer style: detailed" in agent().build_user_prompt("Rating?", style=AnswerStyle.DETAILED)
    assert agent().build_user_prompt("Rating?", style=None) == SURFACE + "Current message:\nRating?"


@pytest.mark.parametrize(("style", "tokens"), [(AnswerStyle.CONCISE, 600), (AnswerStyle.DETAILED, 1100)])
def test_stream_uses_the_style_token_limit(style: AnswerStyle, tokens: int) -> None:
    transport = streaming("He ", "builds systems.")
    stream = agent(transport).stream("Who?", HISTORY, "ctx", style)

    assert isinstance(stream, GroqChatCompletionStream)
    with stream:
        events = list(stream)

    assert [event.text for event in events if isinstance(event, GroqTextDelta)] == ["He ", "builds systems."]
    assert isinstance(events[-1], GroqStreamEnd)
    body = json.loads(transport.last_request.content)
    assert body["stream"] is True
    assert body["max_completion_tokens"] == tokens
    assert "response_format" not in body
    assert body["messages"][0]["content"] == agent().system_prompt
    assert len(transport.requests) == 1


def test_plan_makes_one_strict_json_call() -> None:
    transport = RecordingTransport(ResponseSpec(json=_with_usage(PLAN_JSON)))
    one_model = selector(models=(LLMModel(model_id="openai/gpt-oss-20b", weight=1, supports_strict_json_schema=True),))
    plan_agent = Agent(groq_client(transport), one_model, owner_name=OWNER_NAME, markers=MARKERS, style_tokens=STYLE_TOKENS, plan_tokens=700)

    plan, usage = plan_agent.plan("Show his backend work", HISTORY, "SITE:\n- /projects")

    assert plan == AgentPlan(
        scope=QueryScope.IN_SCOPE,
        summary="Shows his backend work",
        steps=(PlanStep(command="/projects relay", reason="his flagship Go project"),),
    )
    assert usage.total_tokens == 860
    body = json.loads(transport.last_request.content)
    assert body["stream"] is False
    assert body["max_completion_tokens"] == 700
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["messages"][0]["content"] == plan_agent.plan_prompt
    assert "Answer style" not in body["messages"][1]["content"]


def test_plan_falls_back_to_json_object_mode() -> None:
    transport = RecordingTransport(ResponseSpec(json=completion(f"```json\n{PLAN_JSON}\n```")))
    llama = selector(models=(LLMModel(model_id="llama-3.3-70b-versatile", weight=1),))
    plan_agent = Agent(groq_client(transport), llama, owner_name=OWNER_NAME, markers=MARKERS, style_tokens=STYLE_TOKENS, plan_tokens=700)

    plan, usage = plan_agent.plan("Show his work")

    assert plan.steps[0].command == "/projects relay"
    assert usage is None
    assert json.loads(transport.last_request.content)["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("content", [None, "  ", "not json", '{"steps": "nope"}'])
def test_bad_plans_raise(content: str | None) -> None:
    with pytest.raises(AgentResponseError):
        agent(answering(content)).plan("Show his work")


@pytest.mark.parametrize(
    "overrides",
    [
        {"owner_name": "  "},
        {"owner_name": None},
        {"style_tokens": {AnswerStyle.CONCISE: 600}},
        {"style_tokens": "600"},
        {"style_tokens": {AnswerStyle.CONCISE: 0, AnswerStyle.DETAILED: 1}},
        {"style_tokens": {AnswerStyle.CONCISE: True, AnswerStyle.DETAILED: 1}},
        {"plan_tokens": 0},
        {"markers": {}},
        {"markers": "⟂OOS"},
        {"markers": {QueryScope.IN_SCOPE: "⟂IN"}},
        {"markers": {"NOT_RELATED_TO_PORTFOLIO": "⟂OOS"}},
        {"markers": {QueryScope.UNSAFE: ""}},
        {"markers": {QueryScope.UNSAFE: " ⟂UNS"}},
        {"markers": {QueryScope.UNSAFE: 1}},
        {"markers": {QueryScope.UNSAFE: "⟂X", QueryScope.PROMPT_INJECTION: "⟂X"}},
        {"markers": {QueryScope.UNSAFE: "⟂X", QueryScope.PROMPT_INJECTION: "⟂XY"}},
    ],
)
def test_invalid_settings_raise(overrides: dict) -> None:
    with pytest.raises(InvalidAgentSettingError):
        agent(**overrides)


def test_collaborators_are_type_checked() -> None:
    settings = {"owner_name": OWNER_NAME, "markers": MARKERS, "style_tokens": STYLE_TOKENS, "plan_tokens": 1}
    with pytest.raises(InvalidAgentSettingError, match="groq_client"):
        Agent("client", selector(), **settings)
    with pytest.raises(InvalidAgentSettingError, match="model_selector"):
        Agent(groq_client(streaming()), "selector", **settings)


@pytest.mark.parametrize(
    ("message", "history", "context", "style"),
    [
        ("", (), "", AnswerStyle.CONCISE),
        ("Hi", "history", "", AnswerStyle.CONCISE),
        ("Hi", ("not a message",), "", AnswerStyle.CONCISE),
        ("Hi", (), None, AnswerStyle.CONCISE),
        ("Hi", (), "", "concise"),
    ],
)
def test_invalid_input_raises(message, history, context, style) -> None:
    with pytest.raises(InvalidAgentInputError):
        agent().build_user_prompt(message, history, context, style)


def test_errors_share_the_agent_base() -> None:
    for error in (InvalidAgentSettingError, InvalidAgentInputError, AgentResponseError):
        assert issubclass(error, AgentError)


def test_package_data_ships_the_prompts() -> None:
    pyproject = Path(__file__).parents[5] / "pyproject.toml"
    package_data = tomllib.loads(pyproject.read_text())["tool"]["setuptools"]["package-data"]

    assert package_data["main.package.ai.agent"] == ["*.md"]
