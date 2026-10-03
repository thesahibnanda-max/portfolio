import json
import tomllib
from importlib import resources
from pathlib import Path

import pytest

from main.package.ai.agent import Agent, AgentError, InvalidAgentInputError, InvalidAgentSettingError
from main.package.ai.common import ChatMessage
from main.package.ai.orchestrator import QueryScope
from main.package.clients.groq import GroqChatCompletionStream, GroqStreamEnd, GroqTextDelta
from tests.main.package.ai.agent.fakes import MARKERS, agent, streaming
from tests.main.package.ai.fakes import OWNER_NAME, groq_client, selector

HISTORY = (ChatMessage(role="user", content="Who is he?"), ChatMessage(role="assistant", content="An engineer."))


def test_prompts_are_embedded_md_files() -> None:
    package = resources.files("main.package.ai.agent")

    assert "Portfolio Agent" in package.joinpath("system.md").read_text()
    assert "Current message:" in package.joinpath("user.md").read_text()


def test_system_prompt_names_the_owner_and_every_marker() -> None:
    prompt = agent().system_prompt

    assert prompt.startswith(f"You are the Portfolio Agent: a command-line assistant inside {OWNER_NAME}'s portfolio terminal.")
    assert "never hallucinate" in prompt
    for marker in MARKERS.values():
        assert f"reply with exactly {marker} and nothing else" in prompt
    assert "nothing to do with" in prompt and "change your rules" in prompt and "harmful" in prompt
    assert "{%" not in prompt and "{{" not in prompt and "\n\n\n" not in prompt
    assert agent().markers == MARKERS


def test_user_prompt_has_context_history_and_question() -> None:
    prompt = agent().build_user_prompt("Rating?", HISTORY, "PROFILE:\nName: Sahib")

    assert prompt == "Context:\nPROFILE:\nName: Sahib\n\nConversation so far:\nUSER: Who is he?\nASSISTANT: An engineer.\n\nCurrent message:\nRating?"
    assert agent().build_user_prompt("Rating?") == "Current message:\nRating?"


def test_stream_sends_one_streamed_request_with_the_agent_limits() -> None:
    transport = streaming("He ", "builds systems.")
    stream = agent(transport).stream("Who?", HISTORY, "ctx")

    assert isinstance(stream, GroqChatCompletionStream)
    with stream:
        events = list(stream)

    assert [event.text for event in events if isinstance(event, GroqTextDelta)] == ["He ", "builds systems."]
    assert isinstance(events[-1], GroqStreamEnd)
    body = json.loads(transport.last_request.content)
    assert body["stream"] is True
    assert body["max_completion_tokens"] == 600
    assert [message["role"] for message in body["messages"]] == ["system", "user"]
    assert body["messages"][0]["content"] == agent().system_prompt
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"owner_name": "  "},
        {"owner_name": None},
        {"max_completion_tokens": 0},
        {"max_completion_tokens": True},
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
    with pytest.raises(InvalidAgentSettingError, match="groq_client"):
        Agent("client", selector(), owner_name=OWNER_NAME, markers=MARKERS, max_completion_tokens=1)
    with pytest.raises(InvalidAgentSettingError, match="model_selector"):
        Agent(groq_client(streaming()), "selector", owner_name=OWNER_NAME, markers=MARKERS, max_completion_tokens=1)


@pytest.mark.parametrize(
    ("message", "history", "context"),
    [("", (), ""), ("Hi", "history", ""), ("Hi", ("not a message",), ""), ("Hi", (), None)],
)
def test_invalid_input_raises(message, history, context) -> None:
    with pytest.raises(InvalidAgentInputError):
        agent().build_user_prompt(message, history, context)


def test_errors_share_the_agent_base() -> None:
    assert issubclass(InvalidAgentSettingError, AgentError)
    assert issubclass(InvalidAgentInputError, AgentError)


def test_package_data_ships_the_prompts() -> None:
    pyproject = Path(__file__).parents[5] / "pyproject.toml"
    package_data = tomllib.loads(pyproject.read_text())["tool"]["setuptools"]["package-data"]

    assert package_data["main.package.ai.agent"] == ["*.md"]
