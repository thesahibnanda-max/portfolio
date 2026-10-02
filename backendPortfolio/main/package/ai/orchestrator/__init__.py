"""
The Orchestrator AI: the guardrail and router of the portfolio assistant. It
reads a visitor's message and the conversation so far, decides whether the
message is in scope for a portfolio assistant at all, and if it is, which
knowledge domains are needed to answer it. It never answers the question
itself; the Worker AI does that with the context the orchestrator asked for.

Exports:
    Orchestrator: classifies and routes a message.
    OrchestratorDecision: the result.
    QueryScope: the guardrail verdict.
    OrchestratorError and its subclasses: the errors described under Errors.

Prompts (embedded in this package, the only place the prompt text lives):
    system.md: the role; the highest-priority rule never to refuse a
    question about the owner (when unsure, choose IN_SCOPE); the
    no-hallucination rule; what each QueryScope covers; every ContextType
    with its description in canonical order; the domain rules; and the exact
    JSON shape to reply with:
    {"scope": "IN_SCOPE", "requiredContexts": ["DOMAIN_NAME", ...], "reason": "..."}.
    user.md: "Conversation so far:" with one "ROLE: content" line per
    earlier message (only when there is history), then "Current message:".
    Both are Jinja2 templates loaded with StrictUndefined, so a misspelled
    variable fails loudly instead of rendering as blank. The system prompt
    is rendered once in the constructor; the user prompt per call.

Construction:
    Orchestrator(
        groq_client,
        model_selector,
        *,
        owner_name,
        temperature,
        top_p,
        max_completion_tokens,
    )
    groq_client: main.package.clients.groq.GroqClient.
    model_selector: main.package.ai.common.ModelSelector; picks the model
    for each call.
    owner_name: the portfolio owner's name, shown in the system prompt; at
    startup this comes from StaticLoader().get_profile().profile_details.name.
    temperature (0 to 2) and top_p (0 to 1): fixed for every routing call,
    from main.config.AppConfig.orchestrator (defaults 0.0 and 1.0), so the
    same question is routed the same way.
    max_completion_tokens: positive int, from AppConfig.llm.
    A bad setting raises InvalidOrchestratorSettingError.

route(message, history=()) -> OrchestratorDecision
    message: non-empty str. history: sequence of
    main.package.ai.common.ChatMessage, oldest first. Anything else raises
    InvalidOrchestratorInputError.
    Sends the system and user prompts to Groq with the selected model, its
    reasoning_effort, the fixed temperature and top_p and
    max_completion_tokens, and Groq's JSON enforcement:
        on a model with supports_strict_json_schema (openai/gpt-oss-20b and
        openai/gpt-oss-120b by default), a strict json_schema named
        orchestrator_decision: an object with scope (one of the QueryScope
        values), requiredContexts (an array whose items must be ContextType
        names) and reason (a string), all required and nothing else
        allowed. Groq then
        guarantees the reply has exactly that shape;
        on any other model (llama-3.3-70b-versatile by default), json_object
        mode, which guarantees valid JSON but not its shape.
    The decision is then pulled out of the reply with
    main.package.json_extract.JsonExtractor and validated, as a final check
    that matters most in json_object mode; a reply wrapped in prose or a
    code fence, or with small JSON mistakes, still works. Context names are
    read in any letter case and the reason defaults to "".
    The decision is normalised so callers never have to second-guess it: a
    scope other than IN_SCOPE always has no contexts; for IN_SCOPE,
    duplicates are removed, contexts are sorted into ContextType order, NONE
    is dropped when any other context is present, and an empty list becomes
    (NONE,). The scope is read in any letter case; a missing or unknown
    scope is not a valid decision.
    system_prompt and build_user_prompt(message, history) expose the exact
    prompts, for logging and tests.

OrchestratorDecision:
    Frozen, with scope (QueryScope), required_contexts (a tuple of
    ContextType) and reason. is_in_scope is True only for IN_SCOPE.
    needs_context is True only for IN_SCOPE with real contexts.

Errors (all in exceptions.py, all subclasses of OrchestratorError):
    InvalidOrchestratorSettingError: a constructor setting is invalid.
    InvalidOrchestratorInputError: message or history is invalid.
    OrchestratorResponseError: the model returned no content, or no valid
    routing decision could be extracted (the extractor's error is chained as
    __cause__).
    Errors from Groq itself are main.package.clients.groq.GroqClientError
    and are not wrapped, including GroqJsonValidationError.

QueryScope (StrEnum):
    IN_SCOPE: anything about the owner, how the owner relates to a topic,
    greetings, thanks, questions about the assistant, and follow-ups. Only
    this scope goes on to the Worker AI, with or without context.
    NOT_RELATED_TO_PORTFOLIO: no connection to the owner at all, such as
    general knowledge or the visitor's own homework.
    PROMPT_INJECTION: attempts to change the rules or role or reveal the
    prompt.
    UNSAFE: harmful, hateful, harassing or dangerous requests.
    The prompt is written so a genuine question about the owner is never
    blocked: borderline messages are IN_SCOPE. A new verdict is a new member
    here, a new line in system.md and a new fallback message in config.

Thread safety:
    After construction an Orchestrator holds only the rendered system
    prompt, a compiled template and the thread-safe Groq client and model
    selector, so one instance can serve every thread on the free-threaded
    Python 3.14t build.

Example:
    decision = orchestrator.route("What is his Codeforces rating?", history)
    decision.required_contexts == (ContextType.CODEFORCES,)
"""

from .dto import OrchestratorDecision, QueryScope
from .exceptions import (
    InvalidOrchestratorInputError,
    InvalidOrchestratorSettingError,
    OrchestratorError,
    OrchestratorResponseError,
)
from .orchestrator import Orchestrator

__all__ = [
    "Orchestrator",
    "OrchestratorDecision",
    "QueryScope",
    "OrchestratorError",
    "InvalidOrchestratorSettingError",
    "InvalidOrchestratorInputError",
    "OrchestratorResponseError",
]
