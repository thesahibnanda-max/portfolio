"""
The Portfolio Agent AI behind the /cli terminal: one streamed Groq call per
question that both decides scope and answers, so the terminal costs half the
calls of the chat (which routes with the Orchestrator first, then answers
with the Worker).

Exports:
    Agent: builds the prompts and opens the answer stream.
    MarkedAnswerStream: wraps that stream and turns a scope marker at the
    start of the answer into the configured fallback message.
    AgentError and its subclasses: the errors described under Errors.

Prompts (embedded in this package, the only place the prompt text lives):
    system.md: the agent's role (third person about the owner), the
    never-hallucinate rule, one marker rule per configured scope, and the
    terminal style (short, plain markdown, no tables or HTML).
    user.md: "Context:" (only when not blank), "Conversation so far:" (only
    when there is history), then "Current message:".
    Both are Jinja2 templates loaded with StrictUndefined. The system prompt
    is rendered once in the constructor and comes first in every request, so
    Groq's prompt cache can reuse it.

Agent(groq_client, model_selector, *, owner_name, markers, max_completion_tokens)
    markers maps a QueryScope other than IN_SCOPE to the exact text the
    model must reply with for that kind of message, for example
    NOT_RELATED_TO_PORTFOLIO -> "⟂OOS". Markers must be unique, non-empty,
    free of surrounding whitespace, and none may be a prefix of another, so
    the first characters of an answer identify at most one marker.
    stream(message, history=(), context="") -> GroqChatCompletionStream,
    not yet sent; enter it with a with block. build_user_prompt and
    system_prompt expose the exact prompts for tests and logging.
    A bad setting raises InvalidAgentSettingError; a bad message, history or
    context raises InvalidAgentInputError.

MarkedAnswerStream(stream, *, markers, fallback_messages)
    Iterates like the Groq stream (GroqTextDelta events, then one
    GroqStreamEnd) and supports with, cancel() and close(). It holds back
    the first deltas only while they could still be the start of a marker,
    then releases them as one delta and passes the rest straight through,
    so a normal answer streams with no visible delay.
    When the answer starts with a marker (leading whitespace ignored, the
    marker may be split across deltas), it cancels the Groq stream at once
    and yields the scope's fallback message as one delta and the end event.
    scope is IN_SCOPE or the matched scope; usage is Groq's token usage once
    the stream ended normally (None when it was diverted or cancelled).
    Cancelling raises GroqStreamCancelledError from the next read, exactly
    like the wrapped stream, so ChatReplyStream treats both the same.

Errors (all in exceptions.py, all subclasses of AgentError):
    InvalidAgentSettingError, InvalidAgentInputError, and
    AgentStreamStateError for an event type the stream does not know.
    Groq errors are main.package.clients.groq.GroqClientError, not wrapped.

Thread safety:
    Agent keeps only immutable state after construction and can serve every
    thread on the free-threaded build. A MarkedAnswerStream belongs to one
    request; only cancel() may be called from another thread.
"""

from .agent import Agent
from .exceptions import AgentError, AgentStreamStateError, InvalidAgentInputError, InvalidAgentSettingError
from .marked_answer_stream import MarkedAnswerStream

__all__ = [
    "Agent",
    "MarkedAnswerStream",
    "AgentError",
    "InvalidAgentSettingError",
    "InvalidAgentInputError",
    "AgentStreamStateError",
]
