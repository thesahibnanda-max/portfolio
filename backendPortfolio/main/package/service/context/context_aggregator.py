from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from types import TracebackType
from typing import Self

from main.package.ai.common import ContextType
from main.package.service.context.context_provider import ContextProvider
from main.package.service.context.exceptions import InvalidContextSettingError

_BLOCK_SEPARATOR = "\n\n"


class ContextAggregator:
    def __init__(self, *, providers: Sequence[ContextProvider], max_workers: int) -> None:
        self._providers = self._index(providers)

        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise InvalidContextSettingError("max_workers must be a positive int")

        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="context-aggregator")

    def aggregate(self, contexts: Sequence[ContextType]) -> str:
        if isinstance(contexts, str) or not all(isinstance(context, ContextType) for context in contexts):
            raise InvalidContextSettingError("contexts must be a sequence of ContextType")

        requested = set(contexts)
        needed = [context for context in ContextType if context in requested and context is not ContextType.NONE]
        futures = [self._executor.submit(self._providers[context].render) for context in needed]
        blocks = (future.result().strip() for future in futures)

        return _BLOCK_SEPARATOR.join(block for block in blocks if block)

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @staticmethod
    def _index(providers: Sequence[ContextProvider]) -> dict[ContextType, ContextProvider]:
        if isinstance(providers, str) or not isinstance(providers, Sequence):
            raise InvalidContextSettingError("providers must be a sequence of ContextProvider")

        if not all(isinstance(provider, ContextProvider) for provider in providers):
            raise InvalidContextSettingError("every provider must be a ContextProvider")

        types = [provider.context_type for provider in providers]
        if len(set(types)) != len(types):
            raise InvalidContextSettingError("each ContextType may have only one provider")

        expected = set(ContextType) - {ContextType.NONE}
        if set(types) != expected:
            missing = sorted(expected - set(types))
            raise InvalidContextSettingError(f"providers must cover every ContextType except NONE; missing {missing}")

        return {provider.context_type: provider for provider in providers}
