import json
import os
from pathlib import Path

from openai import OpenAI

from utils.clean_ai_answer import clean_ai_answer


BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_FILE = BASE_DIR / "config" / "ai_settings.json"


BRIEF_INSTRUCTIONS = """
You are M12 AI, the assistant built into M12OS.

Answer only the exact question asked.
Give the direct answer first.
Use one short sentence when possible.
Do not add background, history, suggestions, related facts,
follow-up questions, or offers to help unless requested.

If the user asks for details, explanation, examples, instructions,
comparison, a list, code, or a full file, provide the requested detail.

Do not claim an M12OS action was completed unless M12OS confirms it.
""".strip()


class AIService:
    """
    Fast normal AI conversation with retained context.
    """

    def __init__(self):
        settings = self.load_settings()

        saved_key = str(
            settings.get("api_key", "")
        ).strip()

        environment_key = os.getenv(
            "OPENAI_API_KEY",
            "",
        ).strip()

        api_key = saved_key or environment_key

        if not api_key:
            raise RuntimeError(
                "OpenAI API key is not configured."
            )

        self.model = str(
            settings.get(
                "model",
                "gpt-5-mini",
            )
        ).strip() or "gpt-5-mini"

        self.client = OpenAI(
            api_key=api_key,
            timeout=45.0,
        )

        self.previous_response_id = None

    @staticmethod
    def load_settings():
        defaults = {
            "provider": "OpenAI",
            "model": "gpt-5-mini",
            "api_key": "",
        }

        if not SETTINGS_FILE.exists():
            return defaults

        try:
            with SETTINGS_FILE.open(
                "r",
                encoding="utf-8",
            ) as file:
                loaded = json.load(file)

            if isinstance(loaded, dict):
                defaults.update(loaded)

        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            print(
                "AI settings read error: "
                f"{type(error).__name__}: {error}"
            )

        return defaults

    def stream(
        self,
        user_message,
        on_delta,
    ):
        """
        Stream visible text fragments as they arrive.

        Returns the complete cleaned answer.
        """
        message = str(user_message).strip()

        if not message:
            return "Please enter a message."

        request = {
            "model": self.model,
            "instructions": BRIEF_INSTRUCTIONS,
            "input": message,
            "reasoning": {
                "effort": "minimal",
            },
            "text": {
                "verbosity": "low",
            },
            "stream": True,
        }

        if self.previous_response_id:
            request["previous_response_id"] = (
                self.previous_response_id
            )

        complete_text = ""
        response_id = None

        try:
            event_stream = self._create_response(
                request
            )

            for event in event_stream:
                event_type = str(
                    getattr(
                        event,
                        "type",
                        "",
                    )
                )

                if event_type == (
                    "response.output_text.delta"
                ):
                    delta = str(
                        getattr(
                            event,
                            "delta",
                            "",
                        )
                    )

                    if delta:
                        complete_text += delta
                        on_delta(delta)

                elif event_type == (
                    "response.completed"
                ):
                    response = getattr(
                        event,
                        "response",
                        None,
                    )

                    response_id = getattr(
                        response,
                        "id",
                        None,
                    )

            cleaned = clean_ai_answer(
                complete_text
            )

            if not cleaned:
                return self.ask(message)

            if response_id:
                self.previous_response_id = (
                    response_id
                )

            return cleaned

        except Exception:
            # Reliable fallback to the normal non-streaming request.
            return self.ask(message)

    def ask(self, user_message):
        message = str(user_message).strip()

        if not message:
            return "Please enter a message."

        request = {
            "model": self.model,
            "instructions": BRIEF_INSTRUCTIONS,
            "input": message,
            "reasoning": {
                "effort": "minimal",
            },
            "text": {
                "verbosity": "low",
            },
        }

        if self.previous_response_id:
            request["previous_response_id"] = (
                self.previous_response_id
            )

        try:
            response = self._create_response(
                request
            )

            answer = str(
                getattr(
                    response,
                    "output_text",
                    "",
                )
            ).strip()

            if not answer:
                retry = dict(request)
                retry["input"] = (
                    f"{message}\n\n"
                    "Return a visible text answer."
                )
                response = self._create_response(
                    retry
                )
                answer = str(
                    getattr(
                        response,
                        "output_text",
                        "",
                    )
                ).strip()

            if not answer:
                return (
                    "The AI could not produce a response. "
                    "Please try again."
                )

            self.previous_response_id = getattr(
                response,
                "id",
                None,
            )

            return clean_ai_answer(answer)

        except Exception as error:
            return (
                "AI connection error: "
                f"{type(error).__name__}: {error}"
            )

    def _create_response(self, request):
        """
        Use fast GPT settings. Fall back if the selected model
        does not support them.
        """
        try:
            return self.client.responses.create(
                **request
            )

        except Exception as error:
            error_text = str(error).lower()

            unsupported_fast_option = any(
                phrase in error_text
                for phrase in (
                    "reasoning",
                    "verbosity",
                    "unknown parameter",
                    "unsupported parameter",
                )
            )

            if not unsupported_fast_option:
                raise

            fallback = dict(request)
            fallback.pop("reasoning", None)
            fallback.pop("text", None)

            return self.client.responses.create(
                **fallback
            )

    def clear_memory(self):
        self.previous_response_id = None
