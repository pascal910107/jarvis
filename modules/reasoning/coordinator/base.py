from abc import ABC, abstractmethod
from typing import Any


class BaseCoordinator(ABC):
    @abstractmethod
    def coordinate(self, input_data: Any) -> Any:
        pass
