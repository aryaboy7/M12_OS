import json
import os
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from services.ai_session_memory import (
    get_ai_session_memory,
)
from services.memory_manager import get_memory_manager
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

Use the supplied conversation history to understand follow-up questions
and remembered information.
""".strip()


class InternetAIService:
    """
    Current-information answers using web search and the same persistent
    session memory used by normal AI.
    """

    def __init__(self):
        settings = self.load_settings()

        saved_key = str(
            settings.get(
                "api_key",
                "",
            )
        ).strip()

        environment_key = os.getenv(
            "OPENAI_API_KEY",
            "",
        ).strip()

        api_key = (
            saved_key
            or environment_key
        )

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

        self.history_limit = max(
            4,
            int(
                settings.get(
                    "ai_history_messages",
                    24,
                )
            ),
        )

        self.client = OpenAI(
            api_key=api_key,
            timeout=60.0,
        )

        self.memory = (
            get_ai_session_memory()
        )

        self.permanent_memory = (
            get_memory_manager()
        )

    @staticmethod
    def load_settings():
        defaults = {
            "provider": "OpenAI",
            "model": "gpt-5-mini",
            "web_search_model": "gpt-5-mini",
            "web_search_context_size": "low",
            "internet_search_enabled": True,
            "ai_history_messages": 24,
            "api_key": "",
        }

        if not SETTINGS_FILE.exists():
            return defaults

        try:
            with SETTINGS_FILE.open(
                "r",
                encoding="utf-8",
            ) as file:
                loaded = json.load(
                    file
                )

            if isinstance(
                loaded,
                dict,
            ):
                defaults.update(
                    loaded
                )

        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            print(
                "Internet AI settings error: "
                f"{type(error).__name__}: {error}"
            )

        return defaults

    def get_response_language(
        self,
    ):
        """
        Return the response language selected on the AI screen.
        """
        settings = self.load_settings()

        language = str(
            settings.get(
                "voice_language",
                "en",
            )
        ).strip().lower()

        aliases = {
            "english": "en",
            "russian": "ru",
            "automatic": "auto",
        }

        language = aliases.get(
            language,
            language,
        )

        if language not in {
            "en",
            "ru",
            "auto",
        }:
            language = "en"

        return language

    def language_instruction(
        self,
    ):
        language = self.get_response_language()

        if language == "ru":
            return (
                "Answer in Russian. "
                "Do not switch to English unless the user asks."
            )

        if language == "auto":
            return (
                "Answer in the same language as the user's "
                "most recent message."
            )

        return (
            "Answer in English. "
            "Do not switch to Russian unless the user asks."
        )

    def _build_input(
        self,
        message,
    ):
        """
        Return shared history followed by the current user message.
        """
        conversation = (
            self.memory.get_openai_messages(
                limit=self.history_limit,
                include_system=False,
            )
        )

        conversation.append(
            {
                "role": "user",
                "content": message,
            }
        )

        return conversation

    def _instructions(
        self,
    ):
        today = datetime.now().strftime(
            "%B %d, %Y"
        )

        permanent_context = (
            self.permanent_memory.get_prompt_context(
                limit=50
            )
        )

        instructions = (
            "You are Ace, the M12 AI assistant "
            "with live Internet access. "
            f"Today is {today}. "
            f"{self.language_instruction()} "
            f"{INTERNET_RULES}"
        )

        if permanent_context:
            instructions += (
                "\n\n"
                + permanent_context
                + "\n\nUse permanent memory when relevant. "
                "Do not mention the memory system unless asked."
            )

        return instructions

    def _save_exchange(
        self,
        user_message,
        assistant_answer,
    ):
        self.memory.add_user(
            user_message,
            route="internet",
        )

        self.memory.add_assistant(
            assistant_answer,
            route="internet",
        )

    def stream(
        self,
        message,
        on_delta,
    ):
        """
        Stream a live web-search answer as text becomes available.
        """
        user_message = str(
            message
        ).strip()

        if not user_message:
            return "Please enter a question."

        request = {
            "model": self.model,
            "instructions": (
                self._instructions()
            ),
            "input": self._build_input(
                user_message
            ),
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

        complete_text = ""

        try:
            event_stream = (
                self._create_response(
                    request
                )
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

            cleaned = clean_ai_answer(
                complete_text
            )

            if not cleaned:
                return self.ask(
                    user_message
                )

            self._save_exchange(
                user_message=user_message,
                assistant_answer=cleaned,
            )

            return cleaned

        except Exception as error:
            print(
                "Internet AI streaming error: "
                f"{type(error).__name__}: {error}"
            )

            return self.ask(
                user_message
            )

    def ask(
        self,
        message,
    ):
        """
        Send one non-streaming live-information request.
        """
        user_message = str(
            message
        ).strip()

        if not user_message:
            return "Please enter a question."

        request = {
            "model": self.model,
            "instructions": (
                self._instructions()
            ),
            "input": self._build_input(
                user_message
            ),
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

        try:
            response = (
                self._create_response(
                    request
                )
            )

            answer = str(
                getattr(
                    response,
                    "output_text",
                    "",
                )
            ).strip()

            if not answer:
                retry = dict(
                    request
                )

                retry["input"] = (
                    self._build_input(
                        user_message
                    )
                    + [
                        {
                            "role": "user",
                            "content": (
                                "Return a visible text "
                                "answer to my previous "
                                "request."
                            ),
                        }
                    ]
                )

                response = (
                    self._create_response(
                        retry
                    )
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

            cleaned = clean_ai_answer(
                answer
            )

            if not cleaned:
                return (
                    "Internet AI could not produce a response. "
                    "Please try again."
                )

            self._save_exchange(
                user_message=user_message,
                assistant_answer=cleaned,
            )

            return cleaned

        except Exception as error:
            return (
                "Internet AI error: "
                f"{type(error).__name__}: {error}"
            )

    def _create_response(
        self,
        request,
    ):
        """
        Use fast GPT settings, with a compatibility fallback.
        """
        try:
            return (
                self.client.responses.create(
                    **request
                )
            )

        except Exception as error:
            error_text = str(
                error
            ).lower()

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

            fallback = dict(
                request
            )

            fallback.pop(
                "reasoning",
                None,
            )

            fallback.pop(
                "text",
                None,
            )

            return (
                self.client.responses.create(
                    **fallback
                )
            )

    def clear_memory(
        self,
    ):
        """
        Clear the one shared persistent AI session.
        """
        self.memory.clear()
