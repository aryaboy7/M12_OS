import json
import os
from pathlib import Path

from openai import OpenAI

from services.api_key_manager import APIKeyManager
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

        api_key = APIKeyManager.get_api_key()

        if not api_key:
            raise RuntimeError(
                "OpenAI API key is not configured. "
                "Open Settings -> AI Setup."
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

    def resolve_m12_action(
        self,
        user_message,
        available_skills,
    ):
        """
        Ask the model whether the current request needs an M12OS local skill.

        The model receives the same bounded conversation history used by normal
        chat, so references such as "these presidents", "him", or "the second
        one" can be resolved by the language model instead of Python phrase
        matching.

        Returns a dict:
            {
                "route": "ai" | "local",
                "skill": "<registered skill name or empty>",
                "command": "<standalone canonical command or empty>",
                "subjects": ["explicit image subject", ...],
            }

        On any routing error we fail open to normal AI conversation.
        """
        message = str(user_message).strip()

        if not message:
            return {
                "route": "ai",
                "skill": "",
                "command": "",
                "subjects": [],
            }

        skill_names = [
            str(name).strip()
            for name in (available_skills or [])
            if str(name).strip()
        ]

        skill_list = ", ".join(skill_names) if skill_names else "(none)"

        instructions = (
            "You are the semantic router for M12OS. "
            "Decide whether the user's newest message requires an installed "
            "local M12OS capability to execute something on the device/app, "
            "or whether it should simply be answered by the normal AI.\n\n"
            f"Installed local skill names: {skill_list}.\n\n"
            "Rules:\n"
            "1. route='ai' for ordinary conversation, explanations, facts, "
            "knowledge questions, writing, translation, and anything that "
            "does not require M12OS to execute a local capability.\n"
            "2. route='local' only when one of the installed local skills "
            "must actually do something for the user.\n"
            "3. Use the supplied conversation history to resolve pronouns and "
            "references naturally. Never require Python to know phrases such "
            "as 'this', 'these', 'them', singular/plural variants, or synonyms.\n"
            "4. For a local route, choose exactly one installed skill name and "
            "rewrite the request as a short standalone command with references "
            "resolved. Do not invent missing facts.\n"
            "5. For the image skill, put every distinct resolved image subject "
            "in subjects. Example: after an answer listing four presidents, "
            "'show me pictures of these presidents' should return skill='image' "
            "and the four president names in subjects.\n"
            "6. For non-image skills, subjects must be an empty array.\n"
            "7. If unsure whether a local action is appropriate, choose route='ai'."
        )

        schema = {
            "type": "object",
            "properties": {
                "route": {
                    "type": "string",
                    "enum": ["ai", "local"],
                },
                "skill": {
                    "type": "string",
                },
                "command": {
                    "type": "string",
                },
                "subjects": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                    "maxItems": 8,
                },
            },
            "required": [
                "route",
                "skill",
                "command",
                "subjects",
            ],
            "additionalProperties": False,
        }

        request = {
            "model": self.model,
            "instructions": instructions,
            "input": self._build_input(message),
            "reasoning": {
                "effort": "minimal",
            },
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "m12_semantic_route",
                    "strict": True,
                    "schema": schema,
                },
            },
            "max_output_tokens": 220,
        }

        try:
            try:
                response = self.client.responses.create(
                    **request
                )
            except Exception as error:
                error_text = str(error).lower()

                if (
                    "reasoning" not in error_text
                    and "unsupported parameter" not in error_text
                    and "unknown parameter" not in error_text
                ):
                    raise

                retry = dict(request)
                retry.pop("reasoning", None)

                response = self.client.responses.create(
                    **retry
                )

            raw = str(
                getattr(
                    response,
                    "output_text",
                    "",
                )
            ).strip()

            if not raw:
                return {
                    "route": "ai",
                    "skill": "",
                    "command": "",
                    "subjects": [],
                }

            result = json.loads(raw)

            route = str(
                result.get(
                    "route",
                    "ai",
                )
            ).strip().lower()

            skill = str(
                result.get(
                    "skill",
                    "",
                )
            ).strip()

            command = str(
                result.get(
                    "command",
                    "",
                )
            ).strip()

            subjects = result.get(
                "subjects",
                [],
            )

            if not isinstance(subjects, list):
                subjects = []

            subjects = [
                str(item).strip()
                for item in subjects
                if str(item).strip()
            ][:8]

            if (
                route != "local"
                or skill not in skill_names
            ):
                return {
                    "route": "ai",
                    "skill": "",
                    "command": "",
                    "subjects": [],
                }

            if skill != "image":
                subjects = []

            if not command:
                command = message

            return {
                "route": "local",
                "skill": skill,
                "command": command,
                "subjects": subjects,
            }

        except Exception as error:
            print(
                "AI semantic routing error: "
                f"{type(error).__name__}: {error}"
            )

            return {
                "route": "ai",
                "skill": "",
                "command": "",
                "subjects": [],
            }

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
                f"{self.language_instruction()}\n\n"
                f"{BRIEF_INSTRUCTIONS}"
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
                f"{self.language_instruction()}\n\n"
                f"{BRIEF_INSTRUCTIONS}"
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