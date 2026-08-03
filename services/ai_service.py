import json
import os
from pathlib import Path

from openai import OpenAI

from services.ai_session_memory import (
    get_ai_session_memory,
)
from utils.clean_ai_answer import clean_ai_answer


BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_FILE = BASE_DIR / "config" / "ai_settings.json"


BRIEF_INSTRUCTIONS = """
You are Ace, the M12 AI assistant built into M12OS.

Answer only the exact question asked.
Give the direct answer first.
Use one short sentence when possible.
Do not add background, history, suggestions, related facts,
follow-up questions, or offers to help unless requested.

If the user asks for details, explanation, examples, instructions,
comparison, a list, code, or a full file, provide the requested detail.

Use the supplied conversation history to understand follow-up questions
and remembered information.

Do not claim an M12OS action was completed unless M12OS confirms it.
""".strip()


class AIService:
    """
    Fast normal AI conversation using shared persistent session memory.

    Normal AI and Internet AI both read and write the same bounded
    conversation history through AISessionMemory.
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
                "model",
                "gpt-5-mini",
            )
        ).strip() or "gpt-5-mini"

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
            timeout=45.0,
        )

        self.memory = (
            get_ai_session_memory()
        )

    @staticmethod
    def load_settings():
        defaults = {
            "provider": "OpenAI",
            "model": "gpt-5-mini",
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
                "AI settings read error: "
                f"{type(error).__name__}: {error}"
            )

        return defaults

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

    def _save_exchange(
        self,
        user_message,
        assistant_answer,
    ):
        """
        Persist only a completed successful exchange.
        """
        self.memory.add_user(
            user_message,
            route="normal",
        )

        self.memory.add_assistant(
            assistant_answer,
            route="normal",
        )

    def stream(
        self,
        user_message,
        on_delta,
    ):
        """
        Stream visible text fragments as they arrive.

        Returns the complete cleaned answer.
        """
        message = str(
            user_message
        ).strip()

        if not message:
            return "Please enter a message."

        request = {
            "model": self.model,
            "instructions": (
                BRIEF_INSTRUCTIONS
            ),
            "input": self._build_input(
                message
            ),
            "reasoning": {
                "effort": "minimal",
            },
            "text": {
                "verbosity": "low",
            },
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
                    message
                )

            self._save_exchange(
                user_message=message,
                assistant_answer=cleaned,
            )

            return cleaned

        except Exception as error:
            print(
                "AI streaming error: "
                f"{type(error).__name__}: {error}"
            )

            return self.ask(
                message
            )

    def ask(
        self,
        user_message,
    ):
        """
        Send one non-streaming request using shared persistent history.
        """
        message = str(
            user_message
        ).strip()

        if not message:
            return "Please enter a message."

        request = {
            "model": self.model,
            "instructions": (
                BRIEF_INSTRUCTIONS
            ),
            "input": self._build_input(
                message
            ),
            "reasoning": {
                "effort": "minimal",
            },
            "text": {
                "verbosity": "low",
            },
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
                        message
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
                    "The AI could not produce a response. "
                    "Please try again."
                )

            cleaned = clean_ai_answer(
                answer
            )

            if not cleaned:
                return (
                    "The AI could not produce a response. "
                    "Please try again."
                )

            self._save_exchange(
                user_message=message,
                assistant_answer=cleaned,
            )

            return cleaned

        except Exception as error:
            return (
                "AI connection error: "
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
