"""
Pulls one JSON value out of free-form text, such as an LLM reply, and
validates it against a type.

Exports:
    JsonExtractor: a class with a single static method, extract.
    JsonExtractorError and its subclasses: the errors described under Errors.

JsonExtractor.extract(raw, target) -> target instance
    target is any type pydantic can validate: a BaseModel subclass,
    list[Model], dict[str, int], and so on. The value returned has already
    passed target's validation.

How it works:
    1. Candidates are gathered, in this order and without duplicates:
       the whole trimmed text;
       fenced blocks: ```json blocks if there are any, otherwise plain ```
       blocks, otherwise `inline` spans;
       every top-level {...} or [...] found by a bracket scanner that skips
       brackets inside JSON strings, understands escaped quotes, and drops a
       run whose brackets do not match.
    2. Strict pass: each candidate, in order, is parsed with json.loads,
       retried once with trailing commas removed (",}" and ",]"), and
       validated against target. The first that validates is returned.
    3. Repair pass, only when the strict pass found nothing: each candidate
       is run through json-repair (fixing single quotes, unquoted keys,
       missing closing brackets, Python True/False/None and similar LLM
       mistakes) and validated against target. The first that validates is
       returned.
    Strict comes first so a reply that is already valid JSON is never
    altered by repair. Validating every repaired result against target is
    what makes the repair pass safe: json-repair can turn almost any text
    into some JSON, and anything that does not fit target is discarded
    instead of being returned as a wrong answer.
    The pydantic TypeAdapter for each target is built once and cached.

Errors (all in exceptions.py, all subclasses of JsonExtractorError):
    EmptyJsonInputError: raw is not a str, or is empty or only whitespace.
    JsonExtractionError: no candidate validates against target. The last
    validation error, if any, is chained as __cause__.
    Catch JsonExtractorError to handle every failure at once.

Thread safety:
    extract keeps no state between calls and the adapter cache is a
    thread-safe functools.lru_cache, so it can be called from many threads
    at once on the free-threaded Python 3.14t build.

Dependencies:
    json-repair (pure Python) and pydantic (pydantic-core ships a cp314t
    wheel), so the GIL stays disabled.

Example:
    class Decision(BaseModel):
        reason: str

    JsonExtractor.extract('Sure! ```json\\n{"reason": "ok",}\\n```', Decision)
"""

from .exceptions import EmptyJsonInputError, JsonExtractionError, JsonExtractorError
from .json_extract import JsonExtractor

__all__ = ["JsonExtractor", "JsonExtractorError", "EmptyJsonInputError", "JsonExtractionError"]
