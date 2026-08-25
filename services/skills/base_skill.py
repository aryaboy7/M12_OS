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

    # Generic conversational continuation.
    #
    # When a skill needs another user value, it sets expected_followup
    # to a semantic field name such as:
    #
    #     "contact_name"
    #     "timer_duration"
    #     "note_body"
    #     "city"
    #
    # SkillRegistry then routes the next utterance directly back to the
    # same skill instead of trying to guess what the utterance means.
    expected_followup: Optional[str] = None

    # Optional state a skill wants returned with the follow-up.
    followup_data: Optional[dict[str, Any]] = None

    # How long the expected follow-up remains active.
    followup_timeout: float = 120.0


class BaseSkill(ABC):
    name = "base"
    priority = 100

    @abstractmethod
    def can_handle(self, message: str, context: Any) -> float:
        pass

    @abstractmethod
    def handle(self, message: str, context: Any) -> SkillResult:
        pass

    def handle_followup(
        self,
        message: str,
        context: Any,
        expected_followup: str,
        followup_data: Optional[dict[str, Any]] = None,
    ) -> SkillResult:
        """
        Default follow-up behavior.

        Skills that need special handling can override this method.
        Otherwise, the follow-up is simply passed to handle().
        """
        return self.handle(
            message,
            context,
        )