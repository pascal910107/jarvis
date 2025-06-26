import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        ...
