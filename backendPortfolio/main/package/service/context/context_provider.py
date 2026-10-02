from abc import ABC, abstractmethod

from main.package.ai.common import ContextType


class ContextProvider(ABC):
    @property
    @abstractmethod
    def context_type(self) -> ContextType:
        ...

    @abstractmethod
    def render(self) -> str:
        ...
