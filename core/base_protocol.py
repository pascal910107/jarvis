import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseProtocol(ABC):
    @abstractmethod
    def encode(self, data: Any) -> str:
        ...

    @abstractmethod
    def decode(self, data: str) -> Any:
        ...
