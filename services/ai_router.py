import hashlib
import re
import unicodedata

from services.skills import register_default_skills
from services.ai_plugin_manager import AIPluginManager
from services.ai_service import AIService
from services.internet_ai_service import InternetAIService
from services.m12_context import M12Context
from services.memory_manager import get_memory_manager
from services.skills.loader import load_all_skills
from services.skills.registry import get_skill_registry


class AIRouter:
    """
    M12 AI router with reliable permanent-memory handling.
    """

    def __init__(self):
        self.ai_service = None
        self.internet_ai_service = None
        self.last_ai_route = None

        # Remember the most recent request handled by an M12 local skill.
        self.last_local_message = None
        self.last_local_answer = None
        self.last_skill_result = None

        self.plugin_manager = AIPluginManager()
        self.memory_manager = get_memory_manager()

        # Shared skill registry.
        self.skill_registry = get_skill_registry()

        # Explicit built-in registration.
        # This is important for Android, where filesystem glob discovery
        # may not reliably find packaged *_skill.py files.
        self.builtin_skill_report = (
            register_default_skills()
        )

        # Keep dynamic discovery too for Linux/macOS and future optional skills.
        # Duplicate names are safely replaced by SkillRegistry.register().
        self.skill_load_report = load_all_skills(
            self.skill_registry
        )

        print(
            "[AIRouter] Built-in skills: "
            f"{self.builtin_skill_report}"
        )

        print(
            "[AIRouter] Dynamic skills: "
            f"{self.skill_load_report}"
        )

        print(
            "[AIRouter] Registered skills: "
            f"{self.skill_registry.list_names()}"
        )

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
                r"^(?:please\s+)?remember"
                r"(?:\s+that)?[\s,:;.!?-]+(.+)$"
                r"|^запомни"
                r"(?:\s+что)?[\s,:;.!?-]+(.+)$"
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

            result = self.memory_manager.save_fact(
                fact["category"],
                fact["key"],
                fact["value"],
            )

            saved_value = result[
                "fact"
            ]["value"]

            return (
                True,
                (
                    f"Я запомнил: {saved_value}"
                    if russian
                    else f"I remembered: {saved_value}"
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

        # Realtime may pass explicit memory requests as a full sentence.
        # Remove the command prefix before parsing the actual fact.
        statement = re.sub(
            (
                r"^(?:please\s+)?remember"
                r"(?:\s+that)?[\s,:;.!?-]+"
                r"|^запомни"
                r"(?:\s+что)?[\s,:;.!?-]+"
            ),
            "",
            statement,
            flags=re.IGNORECASE,
        ).strip(" .!?,:;-")

        patterns = (
            r"^i like .+$",
            r"^i love .+$",
            r"^my favorite .+ is .+$",
            r"^my name is .+$",
            r"^my .+?(?:'s name)? is .+$",
            r"^i live in .+$",
            r"^мне нравится .+$",
            r"^я люблю .+$",
            r"^мой любимый .+ .+$",
            r"^моя любимая .+ .+$",
            r"^меня зовут .+$",
            r"^(?:мою|моего|моя|мой) .+ зовут .+$",
            r"^(?:моя|мой) .+ .+$",
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

        generic_personal_match = re.match(
            r"^my\s+(.+?)(?:'s name)?\s+is\s+(.+)$",
            value,
            flags=re.IGNORECASE,
        )

        if generic_personal_match:
            subject_text = (
                generic_personal_match
                .group(1)
                .strip()
            )
            fact_value = (
                generic_personal_match
                .group(2)
                .strip()
            )

            family_subjects = {
                "wife",
                "husband",
                "daughter",
                "son",
                "mother",
                "father",
                "sister",
                "brother",
                "granddaughter",
                "grandson",
                "grandmother",
                "grandfather",
                "aunt",
                "uncle",
                "niece",
                "nephew",
                "partner",
            }

            normalized_subject = (
                self.memory_manager
                .normalize_name(
                    subject_text
                )
            )

            if (
                normalized_subject
                and fact_value
                and normalized_subject
                not in family_subjects
            ):
                return {
                    "category": "personal",
                    "key": normalized_subject,
                    "value": fact_value,
                }

        english_family = {
            "wife",
            "husband",
            "daughter",
            "son",
            "mother",
            "father",
            "sister",
            "brother",
            "granddaughter",
            "grandson",
            "grandmother",
            "grandfather",
            "aunt",
            "uncle",
            "niece",
            "nephew",
            "partner",
        }

        match = re.match(
            r"^my (.+?)(?:'s name)? is (.+)$",
            value,
            flags=re.IGNORECASE,
        )

        if match:
            relationship = (
                self.memory_manager.normalize_name(
                    match.group(1)
                )
            )
            person_name = match.group(2).strip()

            if relationship in english_family:
                return {
                    "category": "family",
                    "key": relationship + "_name",
                    "value": person_name,
                }

        russian_family = {
            "жена": "wife",
            "жену": "wife",
            "муж": "husband",
            "мужа": "husband",
            "дочь": "daughter",
            "дочку": "daughter",
            "сын": "son",
            "сына": "son",
            "мама": "mother",
            "маму": "mother",
            "отец": "father",
            "папа": "father",
            "сестра": "sister",
            "сестру": "sister",
            "брат": "brother",
            "брата": "brother",
            "внучка": "granddaughter",
            "внук": "grandson",
        }

        match = re.match(
            (
                r"^(?:мою|моего|моя|мой)\s+"
                r"([^\s]+)\s+(?:зовут|это)\s+(.+)$"
            ),
            value,
            flags=re.IGNORECASE,
        )

        if match:
            relationship = russian_family.get(
                match.group(1).lower()
            )

            if relationship:
                return {
                    "category": "family",
                    "key": relationship + "_name",
                    "value": match.group(2).strip(),
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

        # Generic personal fact:
        #   My daughter's husband is Alexey.
        #   My son-in-law is Aleksey.
        #
        # The key identifies the subject only. The name/value is never part
        # of the key, so future corrections update one unique record.
        generic_match = re.match(
            r"^my\s+(.+?)(?:'s name)?\s+is\s+(.+)$",
            value,
            flags=re.IGNORECASE,
        )

        if generic_match:
            subject_text = generic_match.group(1).strip()
            fact_value = generic_match.group(2).strip()

            aliases = {
                "daughter's husband": "son_in_law",
                "daughter husband": "son_in_law",
                "son-in-law": "son_in_law",
                "son in law": "son_in_law",
                "wife's husband": "husband",
                "husband's wife": "wife",
            }

            normalized_subject = self.normalize_text(
                subject_text
            )

            subject = aliases.get(
                normalized_subject,
                self.memory_manager.normalize_name(
                    subject_text
                ),
            )

            if subject and fact_value:
                return {
                    "category": "profile",
                    "key": subject,
                    "value": fact_value,
                }

        russian_match = re.match(
            (
                r"^(?:мой|моя|моё|мои)\s+"
                r"(.+?)\s*(?:это|—|-|–|:)\s*(.+)$"
            ),
            value,
            flags=re.IGNORECASE,
        )

        if russian_match:
            subject_text = russian_match.group(1).strip()
            fact_value = russian_match.group(2).strip()

            russian_aliases = {
                "зять": "son_in_law",
                "муж дочери": "son_in_law",
                "муж моей дочери": "son_in_law",
            }

            normalized_subject = self.normalize_text(
                subject_text
            )

            subject = russian_aliases.get(
                normalized_subject,
                self.memory_manager.normalize_name(
                    subject_text
                ),
            )

            if subject and fact_value:
                return {
                    "category": "profile",
                    "key": subject,
                    "value": fact_value,
                }

        # Universal fallback:
        # Every explicit Remember command must be saved even when no
        # specialized parser understands the subject.
        #
        # The short hash gives the same statement a stable key, so saying
        # it again updates the existing record instead of creating duplicates.
        normalized_value = self.normalize_text(
            value
        )

        digest = hashlib.sha1(
            normalized_value.encode(
                "utf-8"
            )
        ).hexdigest()[:12]

        return {
            "category": "personal",
            "key": "fact_" + digest,
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

        family_questions = {
            "wife": {
                "what is my wife name",
                "whats my wife name",
                "who is my wife",
            },
            "daughter": {
                "what is my daughter name",
                "whats my daughter name",
                "who is my daughter",
            },
            "son": {
                "what is my son name",
                "whats my son name",
                "who is my son",
            },
            "husband": {
                "what is my husband name",
                "whats my husband name",
                "who is my husband",
            },
        }

        russian_family_questions = {
            "wife": {
                "как зовут мою жену",
                "кто моя жена",
            },
            "daughter": {
                "как зовут мою дочь",
                "кто моя дочь",
            },
            "son": {
                "как зовут моего сына",
                "кто мой сын",
            },
            "husband": {
                "как зовут моего мужа",
                "кто мой муж",
            },
        }

        family_labels = {
            "wife": ("wife", "жену"),
            "daughter": ("daughter", "дочь"),
            "son": ("son", "сына"),
            "husband": ("husband", "мужа"),
        }

        for relationship, questions in family_questions.items():
            if text in questions:
                value = self.memory_manager.get_fact(
                    "family",
                    relationship + "_name",
                )

                if value:
                    label = family_labels[
                        relationship
                    ][0]
                    return (
                        f"Your {label}'s name is {value}."
                    )

        for relationship, questions in russian_family_questions.items():
            if text in questions:
                value = self.memory_manager.get_fact(
                    "family",
                    relationship + "_name",
                )

                if value:
                    label = family_labels[
                        relationship
                    ][1]
                    return (
                        f"Вашу {label} зовут {value}."
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

        # Generic unique-key profile lookup.
        generic_questions = {
            "who is my son in law": "son_in_law",
            "who is my son-in-law": "son_in_law",
            "what is my son in law name": "son_in_law",
            "what is my son-in-law name": "son_in_law",
            "who is my daughters husband": "son_in_law",
            "what is my daughters husband name": "son_in_law",
            "как зовут моего зятя": "son_in_law",
            "кто мой зять": "son_in_law",
            "как зовут мужа моей дочери": "son_in_law",
        }

        profile_key = generic_questions.get(
            text
        )

        if profile_key:
            value = self.memory_manager.get_fact(
                "profile",
                profile_key,
            )

            if value:
                return value

        generic_personal_question = re.match(
            (
                r"^(?:who|what)\s+is\s+my\s+(.+?)(?:\s+name)?$"
            ),
            text,
            flags=re.IGNORECASE,
        )

        if generic_personal_question:
            subject = (
                self.memory_manager
                .normalize_name(
                    generic_personal_question
                    .group(1)
                )
            )

            value = self.memory_manager.get_fact(
                "personal",
                subject,
            )

            if value:
                return (
                    f"Your "
                    f"{generic_personal_question.group(1)} "
                    f"is {value}."
                )

        # Universal personal-memory lookup.
        # Search all stored facts using meaningful words from the question.
        stop_words = {
            "what",
            "who",
            "is",
            "are",
            "my",
            "the",
            "name",
            "do",
            "you",
            "know",
            "about",
            "как",
            "кто",
            "что",
            "мой",
            "моя",
            "моего",
            "мою",
            "зовут",
        }

        query_words = [
            word
            for word in text.split()
            if (
                len(word) >= 3
                and word not in stop_words
            )
        ]

        if query_words:
            facts = self.memory_manager.list_facts()

            for fact in reversed(facts):
                searchable = self.normalize_text(
                    (
                        f"{fact['category']} "
                        f"{fact['key']} "
                        f"{fact['value']}"
                    )
                )

                if all(
                    word in searchable
                    for word in query_words
                ):
                    return fact["value"]

        return None

    def process_local(
        self,
        message,
        ai_screen,
    ):
        original_message = str(message).strip()

        # Expose the complete SkillResult to AIScreen when a local
        # capability returns structured UI data such as an image.
        self.last_skill_result = None

        context = M12Context(
            ai_screen=ai_screen,
            router=self,
        )

        # Short follow-ups must never be appended to the previous command.
        # Doing that corrupts parsers such as WeatherSkill's city extractor.
        if (
            self.last_ai_route == "local"
            and self.last_local_message
            and self.is_follow_up(original_message)
        ):
            follow_up = self.normalize_text(original_message)

            # For "more details" style requests, let OpenAI elaborate on the
            # already-fetched local result. The prompt includes the actual
            # local answer, so OpenAI does not need to invent live data.
            detail_followups = {
                "more",
                "more details",
                "please more details",
                "tell me more",
                "continue",
                "go on",
                "why",
            }

            if follow_up in detail_followups and self.last_local_answer:
                prompt = (
                    "The previous user request was:\n"
                    f"{self.last_local_message}\n\n"
                    "M12 local data answered:\n"
                    f"{self.last_local_answer}\n\n"
                    "The user now says:\n"
                    f"{original_message}\n\n"
                    "Answer the follow-up using the local data above. "
                    "Do not claim you cannot access live data. "
                    "Do not invent measurements that are not present."
                )

                answer = self.ask_openai(prompt)
                return True, answer

            # Other short follow-ups (for example "what about tomorrow?")
            # are not merged into the city/location text. If the local skill
            # cannot understand the follow-up by itself, normal AI fallback
            # remains available.
            skill_result = self.skill_registry.dispatch(
                message=original_message,
                context=context,
            )

            if skill_result.handled:
                self.last_skill_result = skill_result
                self.last_local_message = original_message
                self.last_local_answer = str(
                    skill_result.answer or ""
                ).strip()
                self.last_ai_route = "local"
                return True, skill_result.answer

            return False, None

        skill_result = self.skill_registry.dispatch(
            message=original_message,
            context=context,
        )

        if skill_result.handled:
            self.last_skill_result = skill_result
            self.last_local_message = original_message
            self.last_local_answer = str(
                skill_result.answer or ""
            ).strip()
            self.last_ai_route = "local"
            return True, skill_result.answer

        plugin_result = self.plugin_manager.process(
            message=original_message,
            context=context,
        )

        try:
            plugin_handled, plugin_answer = plugin_result
        except Exception:
            return plugin_result

        if plugin_handled:
            self.last_local_message = original_message
            self.last_local_answer = str(
                plugin_answer or ""
            ).strip()
            self.last_ai_route = "local"

        return plugin_handled, plugin_answer

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
        self.last_local_message = None
        self.last_local_answer = None
        self.last_skill_result = None

    def reset_service(self):
        self.ai_service = None
        self.internet_ai_service = None
        self.last_ai_route = None
        self.last_local_message = None
        self.last_local_answer = None
        self.last_skill_result = None

    def reload_plugins(self):
        self.plugin_manager.reload_plugins()

    def get_loaded_plugins(self):
        return self.plugin_manager.get_plugin_names()

    def get_plugin_errors(self):
        return list(
            self.plugin_manager.load_errors
        )