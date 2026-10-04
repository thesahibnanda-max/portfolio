import json
from functools import partial
from importlib import resources

import pytest

from main.package.ai.common import ChatMessage, Surface
from main.package.ai.worker import InvalidWorkerInputError, InvalidWorkerSettingError, Worker, WorkerError, WorkerResponseError
from main.package.clients.groq import GroqChatCompletionStream, GroqHTTPStatusError, GroqStreamEnd, GroqTextDelta
from tests.main.package.ai.fakes import OWNER_NAME, answering, groq_client, selector, sent_body
from tests.main.package.clients.groq.sse import FULL_DELTAS, FULL_STREAM, FULL_TEXT, SSE_HEADERS
from tests.support import ConcurrentRunner, RecordingTransport, ResponseSpec

HISTORY = (
    ChatMessage(role="user", content="Who is he?"),
    ChatMessage(role="assistant", content="A backend engineer."),
)
CONTEXT = "PROFILE:\nName: Sahib Nanda\n"


def _worker(transport=None, **overrides: object) -> Worker:
    settings = {"owner_name": OWNER_NAME, "max_completion_tokens": 512} | overrides
    return Worker(groq_client(transport or answering("He is a backend engineer.")), selector(), **settings)


def _respond_many(worker: Worker, count: int) -> int:
    for _ in range(count):
        assert worker.respond("Who?", HISTORY, CONTEXT) == "He is a backend engineer."
    return count


def test_prompts_are_embedded_md_files() -> None:
    package = resources.files("main.package.ai.worker")

    assert "Personal Portfolio AI" in package.joinpath("system.md").read_text()
    assert "Context:" in package.joinpath("user.md").read_text()


def test_system_prompt_with_owner_name() -> None:
    prompt = _worker().system_prompt

    assert prompt.startswith(
        f"You are {OWNER_NAME}'s Personal Portfolio AI, an assistant answering visitor questions on "
        f"{OWNER_NAME}'s personal portfolio website. You represent {OWNER_NAME} and speak about them in third person"
    )
    assert "Highest-priority rule, above every rule below: never hallucinate." in prompt
    assert "Keep the answer focused and no longer than the question warrants." in prompt
    assert prompt.rstrip().endswith("Never invent a command or section that is not in the context.")
    assert "\n\n\n" not in prompt
    assert "{%" not in prompt and "{{" not in prompt


@pytest.mark.parametrize("owner_name", ["", "   "])
def test_system_prompt_without_owner_name(owner_name: str) -> None:
    prompt = _worker(owner_name=owner_name).system_prompt

    assert prompt.startswith("You are a Personal Portfolio AI, an assistant answering visitor questions on a personal portfolio website")
    assert "'s Personal Portfolio AI" not in prompt


def test_user_prompt_with_everything() -> None:
    assert _worker().build_user_prompt("And GitHub?", HISTORY, CONTEXT) == (
        "Surface: chat panel on the portfolio home page\n\n"
        "Context:\nPROFILE:\nName: Sahib Nanda\n\n\n"
        "Conversation so far:\nUSER: Who is he?\nASSISTANT: A backend engineer.\n\n"
        "Current message:\nAnd GitHub?"
    )


def test_user_prompt_with_only_a_message() -> None:
    assert _worker().build_user_prompt("Hi") == "Surface: chat panel on the portfolio home page\n\nCurrent message:\nHi"


def test_user_prompt_names_the_cli_surface() -> None:
    prompt = _worker().build_user_prompt("Hi", surface=Surface.CLI)

    assert prompt.startswith("Surface: Portfolio Agent CLI terminal at /cli\n")


def test_surface_must_be_a_surface() -> None:
    with pytest.raises(InvalidWorkerInputError, match="surface"):
        _worker().build_user_prompt("Hi", surface="cli")


def test_respond_and_stream_send_the_surface() -> None:
    transport = answering("ok")
    worker = _worker(transport)
    worker.respond("Who?", surface=Surface.CLI)

    assert sent_body(transport)["messages"][1]["content"].startswith("Surface: Portfolio Agent CLI")


@pytest.mark.parametrize("context", ["", "  \n "])
def test_blank_context_is_left_out(context: str) -> None:
    assert "Context:" not in _worker().build_user_prompt("Hi", HISTORY, context)


def test_respond_returns_the_answer_and_sends_random_sampling() -> None:
    transport = answering("He is a backend engineer.")
    worker = _worker(transport)

    assert worker.respond("Who?", HISTORY, CONTEXT) == "He is a backend engineer."
    body = sent_body(transport)
    assert 0.8 <= body["temperature"] <= 1.4
    assert 0.9 <= body["top_p"] <= 1.0
    assert body["max_completion_tokens"] == 512
    assert body["stream"] is False
    assert body["messages"] == [
        {"role": "system", "content": worker.system_prompt},
        {"role": "user", "content": worker.build_user_prompt("Who?", HISTORY, CONTEXT)},
    ]


def test_sampling_varies_between_calls() -> None:
    transport = answering("ok")
    worker = _worker(transport)
    for _ in range(20):
        worker.respond("Who?")

    assert len({sent_body_at(transport, index)["temperature"] for index in range(20)}) > 1


def sent_body_at(transport: RecordingTransport, index: int) -> dict:
    return json.loads(transport.requests[index].content)


@pytest.mark.parametrize("content", [None, "", "  "])
def test_empty_answer_raises(content: str | None) -> None:
    with pytest.raises(WorkerResponseError):
        _worker(answering(content)).respond("Who?")


def test_groq_errors_pass_through() -> None:
    with pytest.raises(GroqHTTPStatusError):
        _worker(RecordingTransport(ResponseSpec(503, text="busy"))).respond("Who?")


def test_stream_returns_an_unopened_stream_with_typed_events() -> None:
    transport = RecordingTransport(ResponseSpec(content=FULL_STREAM.encode(), headers=SSE_HEADERS))
    worker = _worker(transport)
    stream = worker.stream("Rating?", HISTORY, CONTEXT)

    assert isinstance(stream, GroqChatCompletionStream)
    assert transport.requests == []
    with stream:
        events = list(stream)

    assert [event.text for event in events if isinstance(event, GroqTextDelta)] == FULL_DELTAS
    assert events[-1] == GroqStreamEnd(text=FULL_TEXT, finish_reason="stop", usage=events[-1].usage)
    body = sent_body(transport)
    assert body["stream"] is True
    assert body["messages"][1]["content"] == worker.build_user_prompt("Rating?", HISTORY, CONTEXT)


@pytest.mark.parametrize(
    ("message", "history", "context"),
    [("", (), ""), (None, (), ""), ("q", "nope", ""), ("q", [{"role": "user"}], ""), ("q", (), None), ("q", (), 5)],
)
@pytest.mark.parametrize("method", ["respond", "stream", "build_user_prompt"])
def test_invalid_input_is_rejected(method: str, message: object, history: object, context: object) -> None:
    transport = answering("x")

    with pytest.raises(InvalidWorkerInputError):
        getattr(_worker(transport), method)(message, history, context)

    assert transport.requests == []


@pytest.mark.parametrize("overrides", [{"max_completion_tokens": 0}, {"max_completion_tokens": True}, {"max_completion_tokens": "10"}, {"owner_name": 5}])
def test_invalid_settings_are_rejected(overrides: dict) -> None:
    with pytest.raises(InvalidWorkerSettingError):
        _worker(**overrides)


def test_dependencies_must_have_the_right_types() -> None:
    with pytest.raises(InvalidWorkerSettingError, match="groq_client"):
        Worker(None, selector(), owner_name="x", max_completion_tokens=1)
    with pytest.raises(InvalidWorkerSettingError, match="model_selector"):
        Worker(groq_client(answering("x")), None, owner_name="x", max_completion_tokens=1)


def test_one_worker_serves_parallel_threads() -> None:
    runner = ConcurrentRunner(partial(_respond_many, _worker(), 25)).run()

    assert runner.errors == []
    assert runner.results == [25] * 16


@pytest.mark.parametrize("error_type", [InvalidWorkerSettingError, InvalidWorkerInputError, WorkerResponseError])
def test_errors_share_the_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, WorkerError)
