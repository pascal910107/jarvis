from abc import ABC, abstractmethod
from typing import Any


class BaseSensoryMemory(ABC):
    @abstractmethod
    def add(self, data: Any) -> None:
        pass

    @abstractmethod
    def get(self) -> Any:
        pass
