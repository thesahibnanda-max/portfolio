import random
from collections.abc import Sequence

from main.package.ai.common.dto import LLMModel, ModelChoice
from main.package.ai.common.exceptions import InvalidModelSelectorSettingError

_TEMPERATURE_BOUNDS = (0.0, 2.0)
_TOP_P_BOUNDS = (0.0, 1.0)


class ModelSelector:
    def __init__(
        self,
        *,
        models: Sequence[LLMModel],
        temperature_range: tuple[float, float],
        top_p_range: tuple[float, float],
    ) -> None:
        self._models = self._require_models(models)
        self._weights = tuple(model.weight for model in self._models)
        self._temperature_range = self._require_range("temperature_range", temperature_range, _TEMPERATURE_BOUNDS)
        self._top_p_range = self._require_range("top_p_range", top_p_range, _TOP_P_BOUNDS)

    @property
    def models(self) -> tuple[LLMModel, ...]:
        return self._models

    def select(self, *, temperature: float | None = None, top_p: float | None = None) -> ModelChoice:
        model = random.choices(self._models, weights=self._weights, k=1)[0]

        return ModelChoice(
            model_id=model.model_id,
            reasoning_effort=model.reasoning_effort,
            supports_strict_json_schema=model.supports_strict_json_schema,
            temperature=self._pick("temperature", temperature, self._temperature_range, _TEMPERATURE_BOUNDS),
            top_p=self._pick("top_p", top_p, self._top_p_range, _TOP_P_BOUNDS),
        )

    @staticmethod
    def _pick(name: str, value: float | None, value_range: tuple[float, float], bounds: tuple[float, float]) -> float:
        if value is None:
            low, high = value_range
            return low if low == high else random.uniform(low, high)

        if isinstance(value, bool) or not isinstance(value, int | float) or not bounds[0] <= value <= bounds[1]:
            raise InvalidModelSelectorSettingError(f"{name} must be a number from {bounds[0]} to {bounds[1]}")

        return float(value)

    @staticmethod
    def _require_models(models: Sequence[LLMModel]) -> tuple[LLMModel, ...]:
        if isinstance(models, str) or not isinstance(models, Sequence) or not models:
            raise InvalidModelSelectorSettingError("models must be a non-empty sequence of LLMModel")

        if not all(isinstance(model, LLMModel) for model in models):
            raise InvalidModelSelectorSettingError("every model must be an LLMModel")

        model_ids = [model.model_id for model in models]
        if len(set(model_ids)) != len(model_ids):
            raise InvalidModelSelectorSettingError("model ids must be unique")

        return tuple(models)

    @staticmethod
    def _require_range(name: str, value_range: tuple[float, float], bounds: tuple[float, float]) -> tuple[float, float]:
        if not isinstance(value_range, tuple | list) or len(value_range) != 2:
            raise InvalidModelSelectorSettingError(f"{name} must be a (min, max) pair")

        low, high = value_range
        if any(isinstance(item, bool) or not isinstance(item, int | float) for item in (low, high)):
            raise InvalidModelSelectorSettingError(f"{name} values must be numbers")

        if not bounds[0] <= low <= high <= bounds[1]:
            raise InvalidModelSelectorSettingError(
                f"{name} must satisfy {bounds[0]} <= min <= max <= {bounds[1]}"
            )

        return float(low), float(high)
