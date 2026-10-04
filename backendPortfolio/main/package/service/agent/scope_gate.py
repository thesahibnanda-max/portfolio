import re
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from main.package.ai.common import ContextType
from main.package.ai.orchestrator import QueryScope
from main.package.service.agent.dto import GateDecision
from main.package.service.agent.exceptions import InvalidAgentServiceSettingError


class ScopeGate:
    def __init__(
        self,
        *,
        injection_patterns: Sequence[str],
        off_topic_patterns: Sequence[str],
        context_keywords: Mapping[ContextType, Sequence[str]],
        default_contexts: Sequence[ContextType],
    ) -> None:
        self._injection_patterns = self._compile_patterns("injection_patterns", injection_patterns)
        self._off_topic_patterns = self._compile_patterns("off_topic_patterns", off_topic_patterns)
        self._context_keywords = self._compile_keywords(context_keywords)
        self._default_contexts = self._require_contexts("default_contexts", default_contexts)

    def check(self, question: str) -> GateDecision:
        if any(pattern.search(question) for pattern in self._injection_patterns):
            return GateDecision(scope=QueryScope.PROMPT_INJECTION, contexts=())

        if any(pattern.search(question) for pattern in self._off_topic_patterns):
            return GateDecision(scope=QueryScope.NOT_RELATED_TO_PORTFOLIO, contexts=())

        matched = {context for context, pattern in self._context_keywords.items() if pattern.search(question)}
        contexts = tuple(context for context in ContextType if context in matched) or self._default_contexts
        return GateDecision(scope=QueryScope.IN_SCOPE, contexts=contexts)

    @staticmethod
    def _compile_patterns(name: str, patterns: Sequence[str]) -> tuple[re.Pattern[str], ...]:
        if isinstance(patterns, str) or not isinstance(patterns, Sequence):
            raise InvalidAgentServiceSettingError(f"{name} must be a sequence of regular expressions")

        try:
            return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)
        except (re.error, TypeError) as error:
            raise InvalidAgentServiceSettingError(f"invalid pattern in {name}: {error}") from error

    @classmethod
    def _compile_keywords(cls, keywords: Mapping[ContextType, Sequence[str]]) -> Mapping[ContextType, re.Pattern[str]]:
        if not isinstance(keywords, Mapping):
            raise InvalidAgentServiceSettingError("context_keywords must map a ContextType to keywords")

        compiled = {}
        for context, words in keywords.items():
            cls._require_contexts("context_keywords", (context,))
            if isinstance(words, str) or not isinstance(words, Sequence) or not words:
                raise InvalidAgentServiceSettingError(f"context_keywords[{context}] must be a non-empty sequence")

            if not all(isinstance(word, str) and word.strip() for word in words):
                raise InvalidAgentServiceSettingError(f"context_keywords[{context}] must contain non-blank strings")

            alternatives = "|".join(re.escape(word.strip()) for word in words)
            compiled[context] = re.compile(rf"\b(?:{alternatives})", re.IGNORECASE)

        return MappingProxyType(compiled)

    @staticmethod
    def _require_contexts(name: str, contexts: Sequence[ContextType]) -> tuple[ContextType, ...]:
        if isinstance(contexts, str) or not isinstance(contexts, Sequence) or not contexts:
            raise InvalidAgentServiceSettingError(f"{name} must be a non-empty sequence of ContextType")

        if not all(isinstance(context, ContextType) and context is not ContextType.NONE for context in contexts):
            raise InvalidAgentServiceSettingError(f"{name} must contain ContextType members other than NONE")

        return tuple(contexts)
