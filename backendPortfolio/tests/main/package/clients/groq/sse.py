import json
from typing import Any

SSE_HEADERS = {"content-type": "text/event-stream"}


def chunk(
    content: str | None = None,
    *,
    role: str | None = None,
    finish_reason: str | None = None,
    x_groq_usage: dict[str, Any] | None = None,
    usage: dict[str, Any] | None = None,
    with_choices: bool = True,
    with_delta: bool = True,
) -> str:
    body: dict[str, Any] = {"id": "chatcmpl-1", "object": "chat.completion.chunk", "model": "llama-3.3-70b-versatile"}
    if with_choices:
        choice: dict[str, Any] = {"index": 0, "finish_reason": finish_reason}
        if with_delta:
            choice["delta"] = {key: value for key, value in (("role", role), ("content", content)) if value is not None}
        body["choices"] = [choice]
    else:
        body["choices"] = []
    if x_groq_usage is not None:
        body["x_groq"] = {"id": "req_1", "usage": x_groq_usage}
    if usage is not None:
        body["usage"] = usage
    return f"data: {json.dumps(body)}\n\n"


DONE = "data: [DONE]\n\n"

FULL_STREAM = "".join(
    [
        chunk("", role="assistant"),
        ": ping\n\n",
        chunk("My rating"),
        chunk(" is"),
        chunk(" "),
        chunk("1832"),
        chunk("."),
        chunk(with_choices=False),
        chunk(finish_reason="stop", x_groq_usage={"prompt_tokens": 30, "completion_tokens": 12, "total_tokens": 42}),
        DONE,
    ]
)

FULL_TEXT = "My rating is 1832."
FULL_DELTAS = ["My rating", " is", " ", "1832", "."]
