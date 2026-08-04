from dataclasses import dataclass
from datetime import datetime


@dataclass
class AssistantContextSnapshot:
    current_screen: str
    return_screen: str
    mode: str
    language: str
    local_time: str
    local_date: str
    weekday: str
    voice_active: bool
    ai_busy: bool
    voice_busy: bool


class AssistantContext:
    """
    Read-only runtime context for Ace skills.
    """

    def __init__(self, ai_screen=None):
        self.ai_screen = ai_screen

    def bind_ai_screen(self, ai_screen):
        self.ai_screen = ai_screen

    def snapshot(self):
        now = datetime.now()
        screen = self.ai_screen

        current_screen = "unknown"
        return_screen = "home"
        mode = "AI"
        language = "English"
        voice_active = False
        ai_busy = False
        voice_busy = False

        if screen is not None:
            manager = getattr(screen, "manager", None)
            if manager is not None:
                current_screen = str(
                    getattr(manager, "current", "unknown")
                )

            return_screen = str(
                getattr(screen, "return_screen", "home")
            )

            mode = (
                "Control"
                if bool(getattr(screen, "control_mode", False))
                else "AI"
            )

            language_code = str(
                getattr(screen, "voice_language", "en")
            )
            language = {
                "en": "English",
                "ru": "Russian",
                "auto": "Auto",
            }.get(language_code, language_code)

            voice_active = bool(
                getattr(screen, "realtime_voice_active", False)
                or getattr(screen, "continuous_voice", False)
            )
            ai_busy = bool(
                getattr(screen, "ai_is_busy", False)
            )
            voice_busy = bool(
                getattr(screen, "voice_is_busy", False)
                or getattr(screen, "speech_is_busy", False)
            )

        return AssistantContextSnapshot(
            current_screen=current_screen,
            return_screen=return_screen,
            mode=mode,
            language=language,
            local_time=now.strftime("%I:%M %p").lstrip("0"),
            local_date=now.strftime("%B %d, %Y"),
            weekday=now.strftime("%A"),
            voice_active=voice_active,
            ai_busy=ai_busy,
            voice_busy=voice_busy,
        )

    def prompt_context(self):
        state = self.snapshot()

        return "\n".join(
            (
                "Current M12 context:",
                f"- screen: {state.current_screen}",
                f"- return screen: {state.return_screen}",
                f"- mode: {state.mode}",
                f"- language: {state.language}",
                (
                    f"- date: {state.weekday}, "
                    f"{state.local_date}"
                ),
                f"- local time: {state.local_time}",
                f"- voice active: {state.voice_active}",
            )
        )
