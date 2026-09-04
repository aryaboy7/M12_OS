from typing import Any

from services.music_recognition_service import MusicRecognitionService
from services.skills.base_skill import BaseSkill, SkillResult


class MusicRecognitionSkill(BaseSkill):
    """
    Recognizes music audible through the M12 microphone.

    Natural-language intent is resolved by the AI/Realtime layer.
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

        print(
            "[MusicRecognition] result:",
            result,
        )

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

        status = str(
            result.get("status", "")
        ).strip()

        if status == "not_configured":
            answer = (
                "Music recognition is not configured yet."
            )

        elif status == "not_recognized":
            answer = (
                "I couldn't identify that song. "
                "Please try again while the music is playing clearly."
            )

        elif status == "audio_file_not_found":
            answer = (
                "I couldn't capture enough audio to identify the song."
            )

        elif status == "network_error":
            answer = (
                "I couldn't reach the music recognition service. "
                "Please check the network connection and try again."
            )

        elif status == "http_error":
            answer = (
                "The music recognition service returned an error. "
                "Please try again."
            )

        elif status == "provider_error":
            answer = (
                "The music recognition service could not process "
                "the audio right now."
            )

        else:
            answer = (
                "I couldn't identify the song right now. "
                "Please try again."
            )

        return SkillResult(
            handled=True,
            answer=answer,
            confidence=1.0,
            action="recognize_music",
            data=result,
        )