from main.package.ai.agent import Agent, AnswerStyle
from main.package.ai.orchestrator import QueryScope
from main.package.clients.groq import GroqChatCompletionStream
from tests.main.package.ai.fakes import OWNER_NAME, groq_client, selector
from tests.main.package.clients.groq.sse import DONE, SSE_HEADERS, chunk
from tests.support import RecordingTransport, ResponseSpec

MARKERS = {
    QueryScope.NOT_RELATED_TO_PORTFOLIO: "⟂OOS",
    QueryScope.PROMPT_INJECTION: "⟂INJ",
    QueryScope.UNSAFE: "⟂UNS",
}
FALLBACKS = {
    QueryScope.NOT_RELATED_TO_PORTFOLIO: "Only portfolio questions, please.",
    QueryScope.PROMPT_INJECTION: "I can't change how I work.",
    QueryScope.UNSAFE: "I can't help with that.",
}
STYLE_TOKENS = {AnswerStyle.CONCISE: 600, AnswerStyle.DETAILED: 1100}
USAGE = {"prompt_tokens": 900, "completion_tokens": 40, "total_tokens": 940}


def streaming(*deltas: str, usage: dict | None = None, done: bool = True) -> RecordingTransport:
    body = "".join(chunk(delta) for delta in deltas)
    body += chunk(finish_reason="stop", x_groq_usage=usage or USAGE)
    if done:
        body += DONE
    return RecordingTransport(ResponseSpec(content=body.encode(), headers=SSE_HEADERS))


def agent(transport: RecordingTransport | None = None, **overrides: object) -> Agent:
    settings = {"owner_name": OWNER_NAME, "markers": MARKERS, "style_tokens": STYLE_TOKENS, "plan_tokens": 700} | overrides
    return Agent(groq_client(transport or streaming("Hi")), selector(), **settings)


def groq_stream(*deltas: str, **options: object) -> GroqChatCompletionStream:
    return agent(streaming(*deltas, **options)).stream("Who is he?")
