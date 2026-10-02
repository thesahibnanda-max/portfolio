from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum


class TTLKeyValueStoreImpl(StrEnum):
    IN_MEMORY = "in_memory"


class TTLKeyValueStore(ABC):
    @abstractmethod
    def get(self, key: str) -> str | None:
        ...

    @abstractmethod
    def set(self, key: str, value: str, expires_at: datetime) -> None:
        ...

    @abstractmethod
    def set_if_absent(self, key: str, value: str, expires_at: datetime) -> bool:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...
