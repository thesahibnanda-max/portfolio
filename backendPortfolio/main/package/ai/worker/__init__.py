"""
The Worker AI: answers a visitor's message about the portfolio owner using
only the context it is given. It never decides what context to load; the
Orchestrator AI does that, and the caller formats that context and passes it
in.

Exports:
    Worker: answers a message, all at once or as a stream.
    WorkerError and its subclasses: the errors described under Errors.

Prompts (embedded in this package, the only place the prompt text lives):
    system.md: the assistant's role, speaking about the owner in the third
    person (a generic portfolio-assistant wording when the owner name is
    blank), the never-hallucinate rule including hedged guesses, and the
    rule never to mention context, routing or how it knows things.
    user.md: "Context:" with the supplied text (only when it is not blank),
    "Conversation so far:" with one "ROLE: content" line per earlier message
    (only when there is history), then "Current message:".
    Both are Jinja2 templates loaded with StrictUndefined. The system prompt
    is rendered once in the constructor; the user prompt per call.

Construction:
    Worker(groq_client, model_selector, *, owner_name, max_completion_tokens)
    groq_client: main.package.clients.groq.GroqClient.
    model_selector: main.package.ai.common.ModelSelector. The worker passes
    no fixed sampling, so every answer gets a random temperature and top_p
    inside the configured ranges, as in the Java service.
    owner_name: the portfolio owner's name; may be blank.
    max_completion_tokens: positive int, from main.config.AppConfig.llm.
    A bad setting raises InvalidWorkerSettingError.

respond(message, history=(), context="") -> str
    Returns the whole answer. message must be a non-empty str, history a
    sequence of main.package.ai.common.ChatMessage, and context a str (blank
    means no context block); anything else raises InvalidWorkerInputError.
    A reply with no content raises WorkerResponseError.

stream(message, history=(), context="") -> GroqChatCompletionStream
    Returns Groq's stream object without sending anything yet:

        with worker.stream(message, history, context) as stream:
            for event in stream:
                ...

    It yields GroqTextDelta events and then one GroqStreamEnd, supports
    cancel() from another thread, and raises if the stream ends without
    Groq's [DONE] marker; see main.package.clients.groq.

    system_prompt and build_user_prompt(message, history, context) expose the
    exact prompts, for logging and tests.

Errors (all in exceptions.py, all subclasses of WorkerError):
    InvalidWorkerSettingError: a constructor setting is invalid.
    InvalidWorkerInputError: message, history or context is invalid.
    WorkerResponseError: the model returned no content.
    Errors from Groq itself are main.package.clients.groq.GroqClientError
    and are not wrapped.

Thread safety:
    One Worker can serve every thread on the free-threaded Python 3.14t
    build; each stream it returns belongs to the thread reading it.
"""

from .exceptions import InvalidWorkerInputError, InvalidWorkerSettingError, WorkerError, WorkerResponseError
from .worker import Worker

__all__ = ["Worker", "WorkerError", "InvalidWorkerSettingError", "InvalidWorkerInputError", "WorkerResponseError"]
