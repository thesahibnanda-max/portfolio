from functools import partial

import pytest
from pydantic import BaseModel

import main.package.json_extract.json_extract as extract_module
from main.package.json_extract import EmptyJsonInputError, JsonExtractionError, JsonExtractor, JsonExtractorError
from tests.support import ConcurrentRunner


class Decision(BaseModel):
    contexts: list[str]
    reason: str


class Flag(BaseModel):
    enabled: bool
    note: str | None


class Repairer:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, candidate: str, return_objects: bool) -> object:
        self.calls += 1
        raise RecursionError("repair blew up")


def _decision(contexts: list[str], reason: str) -> Decision:
    return Decision(contexts=contexts, reason=reason)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"contexts": ["A"], "reason": "raw"}', _decision(["A"], "raw")),
        ('   \n{"contexts": [], "reason": "padded"}\n  ', _decision([], "padded")),
        ('Sure!\n```json\n{"contexts": ["B"], "reason": "json fence"}\n```\nDone.', _decision(["B"], "json fence")),
        ('```\n{"contexts": ["C"], "reason": "plain fence"}\n```', _decision(["C"], "plain fence")),
        ('Use `{"contexts": ["D"], "reason": "inline"}` please', _decision(["D"], "inline")),
        ('Here you go: {"contexts": ["E"], "reason": "prose"} hope it helps', _decision(["E"], "prose")),
        ('{"contexts": ["F"], "reason": "a } and { and [ ] inside"}', _decision(["F"], "a } and { and [ ] inside")),
        ('x {"contexts": ["G"], "reason": "escaped \\" quote }"} y', _decision(["G"], 'escaped " quote }')),
        ('{"contexts": ["H",], "reason": "trailing",}', _decision(["H"], "trailing")),
    ],
)
def test_strict_pass_finds_valid_json(raw: str, expected: Decision) -> None:
    assert JsonExtractor.extract(raw, Decision) == expected


def test_json_fence_wins_over_plain_fence() -> None:
    raw = '```\n{"contexts": ["PLAIN"], "reason": "p"}\n```\n```json\n{"contexts": ["JSON"], "reason": "j"}\n```'

    assert JsonExtractor.extract(raw, Decision).contexts == ["JSON"]
    assert extract_module._fenced_candidates(raw) == ['{"contexts": ["JSON"], "reason": "j"}']


def test_skips_objects_that_do_not_fit_the_target() -> None:
    raw = 'first {"other": 1} then {"contexts": ["SECOND"], "reason": "fits"}'

    assert JsonExtractor.extract(raw, Decision) == _decision(["SECOND"], "fits")


def test_first_fitting_object_wins() -> None:
    raw = '{"contexts": ["ONE"], "reason": "1"} and {"contexts": ["TWO"], "reason": "2"}'

    assert JsonExtractor.extract(raw, Decision).contexts == ["ONE"]


def test_nested_objects_and_arrays_are_kept_whole() -> None:
    raw = 'result: {"contexts": ["A", "B"], "reason": "nested", "extra": {"deep": [1, {"x": [2]}]}}'

    assert JsonExtractor.extract(raw, Decision) == _decision(["A", "B"], "nested")


def test_mismatched_brackets_are_dropped() -> None:
    assert extract_module._bracketed_candidates('{"a": [1, 2}] then {"b": 2}') == ['{"b": 2}']


def test_quotes_outside_brackets_do_not_start_strings() -> None:
    assert extract_module._bracketed_candidates('He said "hi" then {"a": "}"}') == ['{"a": "}"}']


@pytest.mark.parametrize(
    "raw",
    [
        "{'contexts': ['A'], 'reason': 'single quotes'}",
        '{contexts: ["A"], reason: "unquoted keys"}',
        '{"contexts": ["A"], "reason": "missing brace"',
        'answer: {"contexts": ["A"], "reason": "unterminated',
    ],
)
def test_repair_pass_fixes_common_llm_mistakes(raw: str) -> None:
    assert JsonExtractor.extract(raw, Decision).contexts == ["A"]


def test_repair_pass_handles_python_literals() -> None:
    assert JsonExtractor.extract('{"enabled": True, "note": None}', Flag) == Flag(enabled=True, note=None)


def test_valid_json_is_never_altered_by_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    repairer = Repairer()
    monkeypatch.setattr(extract_module, "repair_json", repairer)

    assert JsonExtractor.extract('{"contexts": ["A"], "reason": "ok"}', Decision).reason == "ok"
    assert repairer.calls == 0


def test_repair_errors_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extract_module, "repair_json", Repairer())

    with pytest.raises(JsonExtractionError):
        JsonExtractor.extract("{not: valid", Decision)


def test_repaired_output_that_does_not_fit_is_rejected() -> None:
    with pytest.raises(JsonExtractionError) as error:
        JsonExtractor.extract('{"something": "else"', Decision)

    assert error.value.__cause__ is not None


@pytest.mark.parametrize("raw", ["no json here at all", "just words { and more words"])
def test_text_without_json_raises(raw: str) -> None:
    with pytest.raises(JsonExtractionError, match="Decision"):
        JsonExtractor.extract(raw, Decision)


@pytest.mark.parametrize("raw", ["", "   ", "\n\t", None, 42, b"{}"])
def test_empty_or_non_string_input_raises(raw: object) -> None:
    with pytest.raises(EmptyJsonInputError):
        JsonExtractor.extract(raw, Decision)


def test_list_and_plain_types_are_supported() -> None:
    assert JsonExtractor.extract("Items: [1, 2, 3]", list[int]) == [1, 2, 3]
    assert JsonExtractor.extract('{"a": 1}', dict[str, int]) == {"a": 1}
    assert JsonExtractor.extract('[{"contexts": [], "reason": "r"}]', list[Decision]) == [_decision([], "r")]


def test_adapters_are_cached_per_target() -> None:
    assert extract_module._adapter(Decision) is extract_module._adapter(Decision)


def test_parallel_extraction() -> None:
    raw = 'Sure ```json\n{"contexts": ["A"], "reason": "threads",}\n```'
    runner = ConcurrentRunner(partial(JsonExtractor.extract, raw, Decision)).run()

    assert runner.errors == []
    assert runner.results == [_decision(["A"], "threads")] * 16


@pytest.mark.parametrize("error_type", [EmptyJsonInputError, JsonExtractionError])
def test_errors_share_the_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, JsonExtractorError)
