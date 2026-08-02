import json
import os
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from utils.clean_ai_answer import clean_ai_answer


BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_FILE = BASE_DIR / "config" / "ai_settings.json"


INTERNET_RULES = """
Answer only the exact question asked.
Give the current answer immediately.
Use one short sentence or compact data line when possible.

Do not add:
- background or history
- unrelated facts
- advice or suggestions
- recommendations
- follow-up questions
- source names
- citations
- website names
- URLs

For current weather, return only current conditions,
temperature, humidity, and wind unless more is requested.

When the user asks for details, explanation, a forecast,
comparison, or a list, provide only that requested information.
""".strip()


class InternetAIService:
    """
    Fast current-information answers using OpenAI web search.
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
                "web_search_model",
                settings.get(
                    "model",
                    "gpt-5-mini",
                ),
            )
        ).strip() or "gpt-5-mini"

        self.search_context_size = str(
            settings.get(
                "web_search_context_size",
                "low",
            )
        ).strip().lower()

        if self.search_context_size not in (
            "low",
            "medium",
            "high",
        ):
            self.search_context_size = "low"

        self.client = OpenAI(
            api_key=api_key,
            timeout=60.0,
        )

        self.previous_response_id = None

    @staticmethod
    def load_settings():
        defaults = {
            "provider": "OpenAI",
            "model": "gpt-5-mini",
            "web_search_model": "gpt-5-mini",
            "web_search_context_size": "low",
            "internet_search_enabled": True,
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
                "Internet AI settings error: "
                f"{type(error).__name__}: {error}"
            )

        return defaults

    def stream(
        self,
        message,
        on_delta,
    ):
        """
        Stream a live web-search answer as text becomes available.

        Returns the complete cleaned answer.
        """
        user_message = str(message).strip()

        if not user_message:
            return "Please enter a question."

        today = datetime.now().strftime(
            "%B %d, %Y"
        )

        instructions = (
            "You are M12 AI with live Internet access. "
            f"Today is {today}. "
            f"{INTERNET_RULES}"
        )

        request = {
            "model": self.model,
            "instructions": instructions,
            "input": user_message,
            "reasoning": {
                "effort": "minimal",
            },
            "text": {
                "verbosity": "low",
            },
            "tools": [
                {
                    "type": "web_search",
                    "search_context_size": (
                        self.search_context_size
                    ),
                }
            ],
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
                return self.ask(
                    user_message
                )

            if response_id:
                self.previous_response_id = (
                    response_id
                )

            return cleaned

        except Exception:
            return self.ask(
                user_message
            )

    def ask(self, message):
        user_message = str(message).strip()

        if not user_message:
            return "Please enter a question."

        today = datetime.now().strftime(
            "%B %d, %Y"
        )

        instructions = (
            "You are M12 AI with live Internet access. "
            f"Today is {today}. "
            f"{INTERNET_RULES}"
        )

        request = {
            "model": self.model,
            "instructions": instructions,
            "input": user_message,
            "reasoning": {
                "effort": "minimal",
            },
            "text": {
                "verbosity": "low",
            },
            "tools": [
                {
                    "type": "web_search",
                    "search_context_size": (
                        self.search_context_size
                    ),
                }
            ],
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
                    f"{user_message}\n\n"
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
                    "Internet AI could not produce a response. "
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
                "Internet AI error: "
                f"{type(error).__name__}: {error}"
            )

    def _create_response(self, request):
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
