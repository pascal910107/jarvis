import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    @abstractmethod
    def think(self, input_data: Any) -> Any:
        ...

    @abstractmethod
    def act(self, action: Any) -> Any:
        ...
