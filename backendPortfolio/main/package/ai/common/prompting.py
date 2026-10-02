from collections.abc import Sequence
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from main.package.ai.common.dto import ChatMessage
from main.package.clients.groq import GroqChatCompletion


def build_prompt_environment(directory: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(directory),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )


def require_conversation(
    message: str,
    history: Sequence[ChatMessage],
    error_type: type[Exception],
) -> tuple[ChatMessage, ...]:
    if not isinstance(message, str) or not message.strip():
        raise error_type("message must be a non-empty string")

    if isinstance(history, str) or not isinstance(history, Sequence):
        raise error_type("history must be a sequence of ChatMessage")

    if not all(isinstance(item, ChatMessage) for item in history):
        raise error_type("every history item must be a ChatMessage")

    return tuple(history)


def first_choice_content(completion: GroqChatCompletion) -> str | None:
    if not completion.choices:
        return None

    message = completion.choices[0].message
    if message is None or not message.content or not message.content.strip():
        return None

    return message.content
