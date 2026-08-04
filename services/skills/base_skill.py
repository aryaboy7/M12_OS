from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class SkillResult:
    handled: bool
    answer: str = ""
    confidence: float = 0.0
    action: Optional[str] = None
    data: Optional[dict[str, Any]] = None


class BaseSkill(ABC):
    name = "base"
    priority = 100

    @abstractmethod
    def can_handle(self, message: str, context: Any) -> float:
        pass

    @abstractmethod
    def handle(self, message: str, context: Any) -> SkillResult:
        pass
