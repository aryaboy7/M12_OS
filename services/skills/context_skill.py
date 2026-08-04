import re
import unicodedata

from services.skills.base_skill import BaseSkill, SkillResult


class ContextSkill(BaseSkill):
    name = "context"
    priority = 20

    @staticmethod
    def _normalize(message):
        text = unicodedata.normalize(
            "NFKD",
            str(message).lower(),
        )
        text = "".join(
            character
            for character in text
            if not unicodedata.combining(character)
        )
        text = re.sub(
            r"[^a-z0-9а-яё\s]+",
            " ",
            text,
        )
        return " ".join(text.split())

    def can_handle(self, message, context):
        text = self._normalize(message)

        exact = {
            "what screen am i on",
            "which screen am i on",
            "what is the current screen",
            "what mode am i in",
            "which mode am i in",
            "what language is selected",
            "which language is selected",
            "what time is it",
            "what is todays date",
            "what day is it",
            "where am i in m12",
            "какой экран открыт",
            "в каком я режиме",
            "какой язык выбран",
            "который час",
            "какая сегодня дата",
            "какой сегодня день",
        }

        if text in exact:
            return 1.0

        phrases = (
            "current screen",
            "screen am i",
            "mode am i",
            "language selected",
            "time is it",
            "todays date",
            "today date",
            "what day",
            "какой экран",
            "каком я режиме",
            "какой язык",
            "который час",
            "сегодня дата",
        )

        if any(phrase in text for phrase in phrases):
            return 0.86

        return 0.0

    def handle(self, message, context):
        state = context.snapshot()
        text = self._normalize(message)
        russian = bool(
            re.search(r"[а-яё]", str(message).lower())
        )

        if (
            "screen" in text
            or "экран" in text
            or "where am i" in text
        ):
            answer = (
                f"Сейчас открыт экран {state.current_screen}."
                if russian
                else f"The current screen is {state.current_screen}."
            )
        elif "mode" in text or "режим" in text:
            answer = (
                f"Сейчас включён режим {state.mode}."
                if russian
                else f"You are in {state.mode} Mode."
            )
        elif "language" in text or "язык" in text:
            answer = (
                f"Выбран язык: {state.language}."
                if russian
                else (
                    "The selected language is "
                    f"{state.language}."
                )
            )
        elif "time" in text or "час" in text:
            answer = (
                f"Сейчас {state.local_time}."
                if russian
                else f"It is {state.local_time}."
            )
        else:
            answer = (
                f"Today is {state.weekday}, {state.local_date}."
                if not russian
                else (
                    f"Сегодня {state.weekday}, "
                    f"{state.local_date}."
                )
            )

        return SkillResult(
            handled=True,
            answer=answer,
            confidence=1.0,
        )
