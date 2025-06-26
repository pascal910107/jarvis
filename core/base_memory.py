import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BaseMemory(ABC):
    @abstractmethod
    def store(self, key: str, value: Any) -> bool:
        ...

    @abstractmethod
    def retrieve(self, key: str) -> Optional[Any]:
        ...
