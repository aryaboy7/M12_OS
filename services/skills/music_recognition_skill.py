from typing import Any

from services.music_recognition_service import MusicRecognitionService
from services.skills.base_skill import BaseSkill, SkillResult


class MusicRecognitionSkill(BaseSkill):
    """
    Recognizes music audible through the M12 microphone.

    Natural-language intent is resolved by the AI/Realtme layer.
    This skill handles only the internal structured command.
    """

    name = "music_recognition"
    priority = 15

    COMMAND = "__M12_RECOGNIZE_MUSIC__"

    def __init__(self):
        self.service = MusicRecognitionService()

    def can_handle(self, message: str, context: Any) -> float:
        if str(message).strip() == self.COMMAND:
            return 1.0

        return 0.0

    def handle(
        self,
        message: str,
        context: Any,
    ) -> SkillResult:
        result = self.service.recognize()

        if result.get("success"):
            title = str(result.get("title", "")).strip()
            artist = str(result.get("artist", "")).strip()

            if title and artist:
                answer = f"This is {title} by {artist}."
            elif title:
                answer = f"This is {title}."
            else:
                answer = "I recognized the music."

            return SkillResult(
                handled=True,
                answer=answer,
                confidence=1.0,
                action="recognize_music",
                data=result,
            )

        return SkillResult(
            handled=True,
            answer=(
                "Music recognition is ready, "
                "but the recognition provider is not configured yet."
            ),
            confidence=1.0,
            action="recognize_music",
            data=result,
        )
