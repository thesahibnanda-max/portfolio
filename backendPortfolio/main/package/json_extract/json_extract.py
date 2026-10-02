import json
import re
from functools import lru_cache
from typing import Any

from json_repair import repair_json
from pydantic import TypeAdapter, ValidationError

from main.package.json_extract.exceptions import EmptyJsonInputError, JsonExtractionError

_TRAILING_COMMA = re.compile(r",(\s*[}\]])")
_JSON_FENCE = re.compile(r"(?is)```json\s*\n?(.*?)\n?\s*```")
_PLAIN_FENCE = re.compile(r"(?s)```\s*\n?(.*?)\n?\s*```")
_INLINE_SPAN = re.compile(r"(?s)`([^`]*?)`")
_OPENERS = {"{": "}", "[": "]"}
_CLOSERS = frozenset(_OPENERS.values())


@lru_cache(maxsize=256)
def _adapter(target: Any) -> TypeAdapter:
    return TypeAdapter(target)


def _fenced_candidates(raw: str) -> list[str]:
    for pattern in (_JSON_FENCE, _PLAIN_FENCE, _INLINE_SPAN):
        found = [match.strip() for match in pattern.findall(raw) if match.strip()]
        if found:
            return found

    return []


def _bracketed_candidates(raw: str) -> list[str]:
    candidates: list[str] = []
    stack: list[str] = []
    start = -1
    in_string = False
    escaped = False

    for index, char in enumerate(raw):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"' and stack:
            in_string = True
        elif char in _OPENERS:
            if not stack:
                start = index
            stack.append(_OPENERS[char])
        elif char in _CLOSERS and stack:
            if char != stack[-1]:
                stack.clear()
                continue
            stack.pop()
            if not stack:
                candidates.append(raw[start:index + 1])

    return candidates


def _unique(candidates: list[str]) -> list[str]:
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _strict_parse(candidate: str, adapter: TypeAdapter) -> tuple[bool, Any, ValidationError | None]:
    texts = [candidate]
    without_trailing_commas = _TRAILING_COMMA.sub(r"\1", candidate)
    if without_trailing_commas != candidate:
        texts.append(without_trailing_commas)

    last_error: ValidationError | None = None
    for text in texts:
        try:
            value = json.loads(text)
        except ValueError:
            continue
        try:
            return True, adapter.validate_python(value), None
        except ValidationError as error:
            last_error = error

    return False, None, last_error


def _repaired_parse(candidate: str, adapter: TypeAdapter) -> tuple[bool, Any, ValidationError | None]:
    try:
        value = repair_json(candidate, return_objects=True)
    except Exception:
        return False, None, None

    if value == "":
        return False, None, None

    try:
        return True, adapter.validate_python(value), None
    except ValidationError as error:
        return False, None, error


class JsonExtractor:
    @staticmethod
    def extract[T](raw: str, target: type[T]) -> T:
        if not isinstance(raw, str) or not raw.strip():
            raise EmptyJsonInputError("Cannot extract JSON from empty input")

        text = raw.strip()
        adapter = _adapter(target)
        candidates = _unique([text, *_fenced_candidates(text), *_bracketed_candidates(text)])
        last_error: ValidationError | None = None

        for candidate in candidates:
            found, value, error = _strict_parse(candidate, adapter)
            if found:
                return value
            last_error = error or last_error

        for candidate in candidates:
            found, value, error = _repaired_parse(candidate, adapter)
            if found:
                return value
            last_error = error or last_error

        raise JsonExtractionError(
            f"No JSON matching {getattr(target, '__name__', target)!s} found in {len(candidates)} candidates"
        ) from last_error
