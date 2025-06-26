from abc import ABC, abstractmethod
from typing import Any


class BaseSystem1(ABC):
    @abstractmethod
    def reason(self, input_data: Any) -> Any:
        pass
