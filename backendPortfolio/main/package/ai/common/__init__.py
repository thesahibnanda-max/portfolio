"""
Types and model selection shared by the AI orchestrator and the AI worker.

Exports:
    ContextType: the knowledge domains a question can need.
    ChatMessage: one earlier message in a conversation.
    LLMModel: one Groq model the selector may pick, with its weight.
    ModelChoice: the model and sampling picked for one call.
    ModelSelector: picks a model and sampling values for each call.
    build_prompt_environment, require_conversation, first_choice_content:
    helpers the orchestrator and worker share, described under Prompting.
    AiCommonError and InvalidModelSelectorSettingError: the errors.

ContextType (StrEnum, in canonical order):
    PROFILE, GITHUB, LEETCODE, CODEFORCES, PERSONALITY, SITE, NONE. Each
    member has a description of what it covers, shown to the orchestrator
    in its prompt.
    NONE means a general question that needs no personal context and is
    never combined with another member. The declared order is the order
    contexts are listed and aggregated in.

Surface (StrEnum): CHAT or CLI, where a visitor is talking to the AI (the
    chat panel or the /cli terminal). Its label is printed as the first line
    of every orchestrator, worker and agent user prompt, so each model knows
    the context of the question. Services derive it from the stored chat's
    origin, never from the client.

ChatMessage:
    Frozen, with role "user" or "assistant" and non-empty content. Prompts
    print the role in upper case, for example "USER: hi".

ModelSelector(*, models, temperature_range, top_p_range)
    models: non-empty sequence of LLMModel (model_id, weight of at least 1,
    optional reasoning_effort sent to Groq for models that accept it, and
    supports_strict_json_schema, True when Groq can enforce a strict JSON
    Schema on that model), with unique model ids. From
    main.config.AppConfig.llm.models.
    temperature_range: (min, max) with 0 <= min <= max <= 2.
    top_p_range: (min, max) with 0 <= min <= max <= 1.
    Both from AppConfig.llm. A bad setting raises
    InvalidModelSelectorSettingError.

    select(*, temperature=None, top_p=None) -> ModelChoice
        Picks a model at random in proportion to its weight; the choice
        carries that model's reasoning_effort and supports_strict_json_schema. Uses the given
        temperature and top_p, or a random value inside the configured range
        when one is None (the range's single value when min equals max). A
        given value outside 0..2 or 0..1 raises
        InvalidModelSelectorSettingError. The orchestrator passes fixed
        values (0 and 1 by default) for repeatable routing; the worker
        passes none, so answers vary within the range.

Prompting (prompting.py):
    build_prompt_environment(directory) returns the Jinja2 Environment used
    to load a package's .md prompts: StrictUndefined (a missing variable
    fails), no HTML escaping, and trim_blocks with lstrip_blocks so a line
    holding only a {% %} tag leaves no blank line behind.
    require_conversation(message, history, error_type) checks that message
    is a non-empty str and history a sequence of ChatMessage, raising the
    calling package's own error_type, and returns history as a tuple.
    first_choice_content(completion) returns the first choice's message
    text, or None when there is no choice or the text is empty.

Thread safety:
    Everything here is immutable after construction, and the random module
    is thread-safe on the free-threaded Python 3.14t build, so one selector
    can serve every thread.
"""

from .dto import ChatMessage, ContextType, LLMModel, ModelChoice, Surface
from .exceptions import AiCommonError, InvalidModelSelectorSettingError
from .model_selector import ModelSelector
from .prompting import build_prompt_environment, first_choice_content, require_conversation

__all__ = [
    "ContextType",
    "Surface",
    "ChatMessage",
    "LLMModel",
    "ModelChoice",
    "ModelSelector",
    "build_prompt_environment",
    "require_conversation",
    "first_choice_content",
    "AiCommonError",
    "InvalidModelSelectorSettingError",
]
