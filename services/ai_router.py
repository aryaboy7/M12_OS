import re
import unicodedata

from services.ai_plugin_manager import AIPluginManager
from services.ai_service import AIService
from services.internet_ai_service import InternetAIService
from services.m12_context import M12Context


class AIRouter:
    """
    Stable M12 router.

    AI Mode:
        normal questions -> normal AI
        current questions -> Internet AI
        short follow-ups -> same AI as previous answer

    Control Mode uses process_local() directly from AIScreen.
    """

    def __init__(self):
        self.ai_service = None
        self.internet_ai_service = None
        self.last_ai_route = None
        self.plugin_manager = AIPluginManager()

    def process(self, message, ai_screen):
        user_message = str(message).strip()

        if not user_message:
            return "Please enter a message."

        handled, response = self.process_local(
            message=user_message,
            ai_screen=ai_screen,
        )

        if handled:
            return response

        return self.process_ai(user_message)

    def process_ai(self, message):
        user_message = str(message).strip()

        if not user_message:
            return "Please enter a message."

        if self.needs_internet(user_message):
            return self.ask_internet(user_message)

        if (
            self.last_ai_route
            and self.is_follow_up(user_message)
        ):
            if self.last_ai_route == "internet":
                return self.ask_internet(user_message)

            return self.ask_openai(user_message)

        return self.ask_openai(user_message)

    def process_ai_stream(
        self,
        message,
        on_delta,
    ):
        """
        Stream from the selected AI service.

        Current questions use Internet AI. Short follow-ups stay with
        the service that answered the previous question.
        """
        user_message = str(message).strip()

        if not user_message:
            return "Please enter a message."

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
            self.last_ai_route
            and self.is_follow_up(
                user_message
            )
        ):
            if self.last_ai_route == "internet":
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

    def process_local(self, message, ai_screen):
        user_message = str(message).strip()

        if not user_message:
            return False, None

        context = M12Context(
            ai_screen=ai_screen,
            router=self,
        )

        return self.plugin_manager.process(
            message=user_message,
            context=context,
        )

    def ask_openai(self, message):
        self.last_ai_route = "normal"

        if self.ai_service is None:
            self.ai_service = AIService()

        return self.ai_service.ask(message)

    def ask_internet(self, message):
        self.last_ai_route = "internet"

        if self.internet_ai_service is None:
            self.internet_ai_service = (
                InternetAIService()
            )

        return self.internet_ai_service.ask(message)

    @classmethod
    def is_follow_up(cls, message):
        text = cls.normalize_text(message)

        exact_phrases = (
            "more",
            "more details",
            "please more details",
            "tell me more",
            "give me more details",
            "continue",
            "go on",
            "why",
            "why is that",
            "explain more",
            "what about tomorrow",
            "what about today",
            "and tomorrow",
            "and today",
            "how about tomorrow",
        )

        if text in exact_phrases:
            return True

        words = text.split()

        return len(words) <= 5 and any(
            word in words
            for word in (
                "more",
                "details",
                "continue",
                "why",
                "tomorrow",
                "today",
            )
        )

    @classmethod
    def needs_internet(cls, message):
        text = cls.normalize_text(message)

        if not text:
            return False

        explicit = (
            "search the web",
            "search online",
            "look it up",
            "check online",
            "use the internet",
            "browse the web",
            "web search",
        )

        if any(phrase in text for phrase in explicit):
            return True

        live_topics = (
            "weather",
            "forecast",
            "temperature",
            "news",
            "headline",
            "stock price",
            "share price",
            "bitcoin price",
            "crypto price",
            "exchange rate",
            "traffic",
            "flight status",
            "score",
            "standings",
            "iss",
            "international space station",
            "space station crew",
            "earthquake",
            "hurricane",
            "outage",
        )

        if any(topic in text for topic in live_topics):
            return True

        current_roles = (
            "president",
            "prime minister",
            "governor",
            "mayor",
            "ceo",
            "chief executive",
            "secretary of state",
            "senator",
            "representative",
            "speaker of the house",
            "supreme court",
            "pope",
        )

        if any(role in text for role in current_roles):
            return True

        current_words = (
            "now",
            "currently",
            "current",
            "today",
            "tonight",
            "latest",
            "recent",
            "live",
            "breaking",
            "updated",
            "this week",
            "this month",
            "this year",
            "yesterday",
            "tomorrow",
        )

        changing_events = (
            "election",
            "poll",
            "launch",
            "mission",
            "release date",
            "availability",
            "version",
        )

        has_current_word = any(
            word in text for word in current_words
        )

        return has_current_word and any(
            event in text for event in changing_events
        )

    @staticmethod
    def normalize_text(message):
        text = str(message).strip().lower().replace(
            "’",
            "'",
        )

        text = unicodedata.normalize(
            "NFKD",
            text,
        )

        text = "".join(
            character
            for character in text
            if not unicodedata.combining(character)
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
        return list(self.plugin_manager.load_errors)
