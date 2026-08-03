import re
import unicodedata

from services.ai_plugin_manager import AIPluginManager
from services.ai_service import AIService
from services.internet_ai_service import InternetAIService
from services.m12_context import M12Context
from services.memory_manager import get_memory_manager

# Important architecture rule:
# AIRouter may import AIService, but AIService must never import AIRouter.


class AIRouter:
    """
    M12 AI router with reliable permanent-memory handling.
    """

    def __init__(self):
        self.ai_service = None
        self.internet_ai_service = None
        self.last_ai_route = None
        self.plugin_manager = AIPluginManager()
        self.memory_manager = get_memory_manager()

    def process(
        self,
        message,
        ai_screen,
    ):
        user_message = str(message).strip()

        if not user_message:
            return "Please enter a message."

        handled, answer = self.process_local(
            user_message,
            ai_screen,
        )

        if handled:
            return answer

        return self.process_ai(
            user_message
        )

    def process_ai(
        self,
        message,
    ):
        user_message = str(message).strip()

        if not user_message:
            return "Please enter a message."

        handled, answer = (
            self.process_memory(
                user_message
            )
        )

        if handled:
            return answer

        self.capture_automatic_fact(
            user_message
        )

        if self.needs_internet(
            user_message
        ):
            return self.ask_internet(
                user_message
            )

        if (
            self.last_ai_route
            and self.is_follow_up(
                user_message
            )
        ):
            if self.last_ai_route == "internet":
                return self.ask_internet(
                    user_message
                )

        return self.ask_openai(
            user_message
        )

    def process_ai_stream(
        self,
        message,
        on_delta,
    ):
        user_message = str(message).strip()

        if not user_message:
            return "Please enter a message."

        handled, answer = (
            self.process_memory(
                user_message
            )
        )

        if handled:
            on_delta(answer)
            return answer

        self.capture_automatic_fact(
            user_message
        )

        if self.needs_internet(
            user_message
        ):
            self.last_ai_route = "internet"

            if self.internet_ai_service is None:
                self.internet_ai_service = (
                    InternetAIService()
                )

            return self.internet_ai_service.stream(
                user_message,
                on_delta,
            )

        if (
            self.last_ai_route == "internet"
            and self.is_follow_up(
                user_message
            )
        ):
            if self.internet_ai_service is None:
                self.internet_ai_service = (
                    InternetAIService()
                )

            return self.internet_ai_service.stream(
                user_message,
                on_delta,
            )

        self.last_ai_route = "normal"

        if self.ai_service is None:
            self.ai_service = AIService()

        return self.ai_service.stream(
            user_message,
            on_delta,
        )

    def process_memory(
        self,
        message,
    ):
        # Reload from disk before every memory request so application
        # restarts and external updates can never leave a stale cache.
        self.memory_manager.load()

        original = str(message).strip()
        text = self.normalize_text(original)
        russian = bool(
            re.search(
                r"[а-яё]",
                original.lower(),
            )
        )

        diagnostic_commands = {
            "memory diagnostics",
            "show memory diagnostics",
            "permanent memory diagnostics",
        }

        if text in diagnostic_commands:
            diagnostics = (
                self.memory_manager.diagnostics()
            )

            facts = diagnostics.get(
                "facts",
                [],
            )

            lines = [
                "Permanent memory diagnostics:",
                (
                    "File: "
                    + str(
                        diagnostics.get(
                            "memory_file",
                            ""
                        )
                    )
                ),
                (
                    "Facts: "
                    + str(
                        diagnostics.get(
                            "fact_count",
                            0,
                        )
                    )
                ),
            ]

            for fact in facts:
                lines.append(
                    (
                        f"- {fact.get('category')}."
                        f"{fact.get('key')}: "
                        f"{fact.get('value')}"
                    )
                )

            return True, "\n".join(lines)

        show_commands = {
            "what do you know about me",
            "what do you remember about me",
            "what do you remember",
            "show my memory",
            "что ты знаешь обо мне",
            "что ты помнишь обо мне",
            "что ты помнишь",
        }

        if text in show_commands:
            facts = (
                self.memory_manager.list_facts()
            )

            if not facts:
                return (
                    True,
                    (
                        "Я пока ничего не сохранил о вас."
                        if russian
                        else "I do not have any permanent facts about you yet."
                    ),
                )

            heading = (
                "Я помню:"
                if russian
                else "I remember:"
            )

            lines = [heading]

            for fact in facts:
                lines.append(
                    f"- {fact['value']}"
                )

            return True, "\n".join(lines)

        remember_match = re.match(
            (
                r"^(?:please\s+)?remember(?:\s+that)?\s+(.+)$"
                r"|^запомни(?:\s+что)?\s+(.+)$"
            ),
            original,
            flags=re.IGNORECASE,
        )

        if remember_match:
            statement = next(
                group
                for group in remember_match.groups()
                if group
            ).strip(" .!?")

            fact = self.parse_fact(
                statement
            )

            self.memory_manager.save_fact(
                fact["category"],
                fact["key"],
                fact["value"],
            )

            return (
                True,
                (
                    f"Я запомнил: {fact['value']}"
                    if russian
                    else f"I remembered: {fact['value']}"
                ),
            )

        direct = self.direct_memory_answer(
            text,
            russian,
        )

        if direct is not None:
            return True, direct

        return False, None

    def capture_automatic_fact(
        self,
        message,
    ):
        """
        Automatically save clear first-person facts and preferences.

        Examples:
            I like tennis.
            My favorite language is Python.
            My name is Anatoliy.
            I live in Brooklyn.
        """
        self.memory_manager.load()

        statement = str(message).strip(
            " .!?"
        )

        patterns = (
            r"^i like .+$",
            r"^i love .+$",
            r"^my favorite .+ is .+$",
            r"^my name is .+$",
            r"^i live in .+$",
            r"^мне нравится .+$",
            r"^я люблю .+$",
            r"^мой любимый .+ .+$",
            r"^моя любимая .+ .+$",
            r"^меня зовут .+$",
            r"^я живу в .+$",
        )

        if not any(
            re.match(
                pattern,
                statement,
                flags=re.IGNORECASE,
            )
            for pattern in patterns
        ):
            return False

        fact = self.parse_fact(
            statement
        )

        self.memory_manager.save_fact(
            fact["category"],
            fact["key"],
            fact["value"],
        )

        return True

    def parse_fact(
        self,
        statement,
    ):
        value = str(statement).strip(
            " .!?"
        )
        lower = value.lower()

        match = re.match(
            r"^my name is (.+)$",
            value,
            flags=re.IGNORECASE,
        )

        if match:
            return {
                "category": "profile",
                "key": "name",
                "value": match.group(1).strip(),
            }

        match = re.match(
            r"^меня зовут (.+)$",
            value,
            flags=re.IGNORECASE,
        )

        if match:
            return {
                "category": "profile",
                "key": "name",
                "value": match.group(1).strip(),
            }

        match = re.match(
            r"^i live in (.+)$",
            value,
            flags=re.IGNORECASE,
        )

        if match:
            return {
                "category": "profile",
                "key": "location",
                "value": match.group(1).strip(),
            }

        match = re.match(
            r"^my favorite (.+?) is (.+)$",
            value,
            flags=re.IGNORECASE,
        )

        if match:
            subject = (
                self.memory_manager.normalize_name(
                    match.group(1)
                )
            )

            return {
                "category": "preferences",
                "key": "favorite_" + subject,
                "value": match.group(2).strip(),
            }

        match = re.match(
            r"^i (?:like|love) (.+)$",
            value,
            flags=re.IGNORECASE,
        )

        if match:
            preference = match.group(1).strip()
            key = self.memory_manager.normalize_name(
                preference
            )

            return {
                "category": "likes",
                "key": key,
                "value": preference,
            }

        match = re.match(
            r"^(?:мне нравится|я люблю) (.+)$",
            value,
            flags=re.IGNORECASE,
        )

        if match:
            preference = match.group(1).strip()
            key = self.memory_manager.normalize_name(
                preference
            )

            return {
                "category": "likes",
                "key": key,
                "value": preference,
            }

        key = self.memory_manager.normalize_name(
            " ".join(
                self.normalize_text(
                    value
                ).split()[:8]
            )
        ) or "fact"

        return {
            "category": "general",
            "key": key,
            "value": value,
        }

    def direct_memory_answer(
        self,
        text,
        russian=False,
    ):
        name_questions = {
            "what is my name",
            "whats my name",
            "who am i",
            "как меня зовут",
            "кто я",
        }

        if text in name_questions:
            value = self.memory_manager.get_fact(
                "profile",
                "name",
            )

            if value:
                return (
                    f"Вас зовут {value}."
                    if russian
                    else f"Your name is {value}."
                )

        favorite_match = re.match(
            r"^what is my favorite (.+)$",
            text,
        )

        if favorite_match:
            subject = (
                self.memory_manager.normalize_name(
                    favorite_match.group(1)
                )
            )

            value = self.memory_manager.get_fact(
                "preferences",
                "favorite_" + subject,
            )

            if value:
                return (
                    f"Your favorite {favorite_match.group(1)} is {value}."
                )

        like_questions = {
            "what do i like",
            "what things do i like",
            "что мне нравится",
            "что я люблю",
        }

        if text in like_questions:
            facts = self.memory_manager.list_facts(
                "likes"
            )

            if facts:
                values = [
                    fact["value"]
                    for fact in facts
                ]

                joined = ", ".join(values)

                return (
                    f"Вам нравится: {joined}."
                    if russian
                    else f"You like: {joined}."
                )

        tennis_questions = {
            "do i like tennis",
            "what sport do i like",
            "what sports do i like",
            "мне нравится теннис",
            "какой спорт мне нравится",
        }

        if text in tennis_questions:
            tennis = self.memory_manager.get_fact(
                "likes",
                "tennis",
            )

            if tennis:
                return (
                    "Да, вам нравится теннис."
                    if russian
                    else "Yes, you like tennis."
                )

        return None

    def process_local(
        self,
        message,
        ai_screen,
    ):
        context = M12Context(
            ai_screen=ai_screen,
            router=self,
        )

        return self.plugin_manager.process(
            message=message,
            context=context,
        )

    def ask_openai(
        self,
        message,
    ):
        self.last_ai_route = "normal"

        if self.ai_service is None:
            self.ai_service = AIService()

        return self.ai_service.ask(message)

    def ask_internet(
        self,
        message,
    ):
        self.last_ai_route = "internet"

        if self.internet_ai_service is None:
            self.internet_ai_service = (
                InternetAIService()
            )

        return self.internet_ai_service.ask(
            message
        )

    @classmethod
    def is_follow_up(
        cls,
        message,
    ):
        text = cls.normalize_text(message)

        phrases = {
            "more",
            "more details",
            "please more details",
            "tell me more",
            "continue",
            "go on",
            "why",
            "and tomorrow",
            "what about tomorrow",
        }

        return (
            text in phrases
            or (
                len(text.split()) <= 5
                and any(
                    word in text.split()
                    for word in (
                        "more",
                        "details",
                        "continue",
                        "why",
                        "tomorrow",
                    )
                )
            )
        )

    @classmethod
    def needs_internet(
        cls,
        message,
    ):
        text = cls.normalize_text(message)

        live_topics = (
            "weather",
            "forecast",
            "temperature",
            "news",
            "headline",
            "stock price",
            "bitcoin price",
            "exchange rate",
            "traffic",
            "flight status",
            "score",
            "standings",
            "iss",
            "international space station",
            "president",
            "prime minister",
            "governor",
            "mayor",
            "ceo",
            "pope",
        )

        return any(
            topic in text
            for topic in live_topics
        )

    @staticmethod
    def normalize_text(
        message,
    ):
        text = str(message).strip().lower()
        text = unicodedata.normalize(
            "NFKD",
            text,
        )
        text = "".join(
            character
            for character in text
            if not unicodedata.combining(
                character
            )
        )
        text = re.sub(
            r"[^a-z0-9а-яё\s']+",
            " ",
            text,
        )

        return " ".join(text.split())

    def clear_memory(self):
        if self.ai_service is not None:
            self.ai_service.clear_memory()

        if self.internet_ai_service is not None:
            self.internet_ai_service.clear_memory()

        self.last_ai_route = None

    def reset_service(self):
        self.ai_service = None
        self.internet_ai_service = None
        self.last_ai_route = None

    def reload_plugins(self):
        self.plugin_manager.reload_plugins()

    def get_loaded_plugins(self):
        return self.plugin_manager.get_plugin_names()

    def get_plugin_errors(self):
        return list(
            self.plugin_manager.load_errors
        )
