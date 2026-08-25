
import re
import threading
import time

from services.skills.base_skill import SkillResult


class SkillRegistry:
    def __init__(
        self,
        minimum_confidence=0.72,
    ):
        self.minimum_confidence = float(
            minimum_confidence
        )

        self._skills = []
        self._lock = threading.RLock()

        # ---------------------------------------------------------
        # Recent skill context
        #
        # Used for natural follow-up requests.
        #
        # Example:
        #
        #   Find contact Mozilla
        #   -> Contacts handles it
        #
        #   Mazilo
        #   -> treated as another contact search
        #
        # This context expires automatically.
        # ---------------------------------------------------------
        self._last_skill_name = None
        self._last_skill_time = 0.0

        self._followup_timeout = 60.0

    def register(
        self,
        skill,
    ):
        """
        Register or replace a skill.

        Skills with the same name are replaced.
        Lower priority numbers win when confidence is equal.
        """
        with self._lock:
            self._skills = [
                item
                for item in self._skills
                if item.name != skill.name
            ]

            self._skills.append(skill)

            self._skills.sort(
                key=lambda item: item.priority
            )

    def unregister(
        self,
        name,
    ):
        """
        Remove a skill by name.
        """
        target = str(name).strip()

        with self._lock:
            self._skills = [
                skill
                for skill in self._skills
                if skill.name != target
            ]

    def clear(
        self,
    ):
        """
        Remove all registered skills.
        """
        with self._lock:
            self._skills.clear()

        self.clear_followup_context()

    def list_names(
        self,
    ):
        """
        Return registered skill names.
        """
        with self._lock:
            return [
                skill.name
                for skill in self._skills
            ]

    def all_skills(
        self,
    ):
        """
        Return a copy of all registered skills.
        """
        with self._lock:
            return list(
                self._skills
            )

    def get(
        self,
        name,
    ):
        """
        Return a registered skill by name.
        """
        target = str(name).strip()

        with self._lock:
            for skill in self._skills:
                if skill.name == target:
                    return skill

        return None

    # =============================================================
    # FOLLOW-UP CONTEXT
    # =============================================================

    def clear_followup_context(self):
        """
        Forget the previously active skill.
        """
        self._last_skill_name = None
        self._last_skill_time = 0.0

    def _remember_skill(
        self,
        skill_name,
    ):
        """
        Remember the most recently handled skill.
        """
        self._last_skill_name = str(
            skill_name or ""
        ).strip()

        self._last_skill_time = time.monotonic()

    def _recent_skill(
        self,
    ):
        """
        Return the recently active skill name.

        Context automatically expires.
        """
        if not self._last_skill_name:
            return None

        age = (
            time.monotonic()
            - self._last_skill_time
        )

        if age > self._followup_timeout:
            self.clear_followup_context()
            return None

        return self._last_skill_name

    # =============================================================
    # CONTACT FOLLOW-UP DETECTION
    # =============================================================

    @staticmethod
    def _looks_like_contact_name(
        message,
    ):
        """
        Decide whether a short follow-up could reasonably
        be a person's/contact's name.

        This is deliberately conservative.

        Examples accepted:

            Mazilo
            mazilo
            Alex Mazilo
            Galina Ryaboy
            Галина
            Галины
            Алекс Мазило

        Examples rejected:

            Thank you
            Спасибо
            Why
            Привет
            OK
            What time is it
            Call him
        """
        text = str(
            message or ""
        ).strip()

        if not text:
            return False

        # Do not treat obvious questions as names.
        if "?" in text:
            return False

        # Remove ordinary ending punctuation.
        cleaned = text.strip(
            " \t\r\n.,!;:\"'()[]{}"
        )

        if not cleaned:
            return False

        lowered = cleaned.lower()

        # ---------------------------------------------------------
        # Common conversational words/phrases that must NEVER
        # become contact searches.
        # ---------------------------------------------------------
        blocked_exact = {
            # English
            "yes",
            "no",
            "ok",
            "okay",
            "thanks",
            "thank you",
            "why",
            "hello",
            "hi",
            "hey",
            "good",
            "great",
            "stop",
            "cancel",
            "continue",
            "again",
            "please",
            "what",
            "who",
            "where",
            "when",
            "how",
            "bye",
            "goodbye",

            # Russian
            "да",
            "нет",
            "ок",
            "хорошо",
            "спасибо",
            "пожалуйста",
            "почему",
            "привет",
            "здравствуй",
            "здравствуйте",
            "стоп",
            "остановись",
            "отмена",
            "продолжай",
            "ещё",
            "еще",
            "что",
            "кто",
            "где",
            "когда",
            "как",
            "пока",
        }

        if lowered in blocked_exact:
            return False

        # ---------------------------------------------------------
        # Command phrases should go through normal skill routing,
        # not the bare-contact follow-up.
        # ---------------------------------------------------------
        blocked_starts = (
            # English
            "find ",
            "show ",
            "open ",
            "look ",
            "call ",
            "dial ",
            "send ",
            "write ",
            "what ",
            "who ",
            "where ",
            "when ",
            "why ",
            "how ",

            # Russian
            "найди ",
            "найти ",
            "покажи ",
            "открой ",
            "позвони ",
            "набери ",
            "напиши ",
            "что ",
            "кто ",
            "где ",
            "когда ",
            "почему ",
            "как ",
        )

        if lowered.startswith(
            blocked_starts
        ):
            return False

        # ---------------------------------------------------------
        # Names should be short.
        # Allow:
        #   First
        #   First Last
        #   First Middle Last
        #   short business/contact labels
        # ---------------------------------------------------------
        words = cleaned.split()

        if len(words) > 4:
            return False

        # Reject digits. A phone number should not accidentally
        # become a name search.
        if re.search(
            r"\d",
            cleaned,
        ):
            return False

        # Only allow letters, spaces, apostrophes and hyphens.
        if not re.fullmatch(
            r"[A-Za-zА-Яа-яЁё"
            r"\u0400-\u04FF"
            r"\-' ]+",
            cleaned,
        ):
            return False

        # Avoid very tiny recognition fragments such as:
        # "а", "и", "я", etc.
        letters = re.sub(
            r"[^A-Za-zА-Яа-яЁё"
            r"\u0400-\u04FF]",
            "",
            cleaned,
        )

        if len(letters) < 3:
            return False

        return True

    def _try_contact_followup(
        self,
        text,
        context,
    ):
        """
        Try a bare contact-name follow-up.

        Returns:
            SkillResult if handled
            None otherwise
        """
        if self._recent_skill() != "contacts":
            return None

        if not self._looks_like_contact_name(
            text
        ):
            return None

        contacts_skill = self.get(
            "contacts"
        )

        if contacts_skill is None:
            return None

        print(
            "[SkillRegistry] "
            "Trying contacts follow-up: "
            f"{text}"
        )

        try:
            result = contacts_skill.handle(
                text,
                context,
            )

        except Exception as error:
            print(
                "Skill execution error "
                "[contacts follow-up]: "
                f"{type(error).__name__}: "
                f"{error}"
            )

            return None

        if not isinstance(
            result,
            SkillResult,
        ):
            result = SkillResult(
                handled=True,
                answer=str(result),
                confidence=1.0,
            )

        if not result.handled:
            return None

        try:
            result.confidence = max(
                float(
                    result.confidence
                ),
                0.95,
            )
        except (
            TypeError,
            ValueError,
        ):
            result.confidence = 0.95

        self._remember_skill(
            "contacts"
        )

        print(
            "[SkillRegistry] "
            "Handled by contacts follow-up"
        )

        return result

    # =============================================================
    # NORMAL DISPATCH
    # =============================================================

    def dispatch(
        self,
        message,
        context,
    ):
        """
        Find and execute the best available skill.

        Every matching skill is ranked by:

            1. Highest confidence
            2. Lowest priority number

        If one skill fails or returns handled=False,
        the registry automatically tries the next candidate.

        If no normal skill matches, a recent skill may receive
        a natural follow-up request.
        """
        text = str(
            message
        ).strip()

        if not text:
            return SkillResult(
                handled=False
            )

        with self._lock:
            skills = list(
                self._skills
            )

        candidates = []

        # ---------------------------------------------------------
        # Normal skill matching
        # ---------------------------------------------------------
        for skill in skills:
            try:
                confidence = float(
                    skill.can_handle(
                        text,
                        context,
                    )
                )

            except Exception as error:
                print(
                    f"Skill check error "
                    f"[{skill.name}]: "
                    f"{type(error).__name__}: "
                    f"{error}"
                )
                continue

            confidence = max(
                0.0,
                min(
                    1.0,
                    confidence,
                ),
            )

            print(
                f"[SkillRegistry] "
                f"{skill.name}: "
                f"{confidence:.2f}"
            )

            if (
                confidence
                < self.minimum_confidence
            ):
                continue

            candidates.append(
                (
                    confidence,
                    int(skill.priority),
                    skill,
                )
            )

        # ---------------------------------------------------------
        # No normal skill matched.
        #
        # Before giving up and allowing Realtime/OpenAI to answer,
        # check whether this is a natural follow-up to Contacts.
        # ---------------------------------------------------------
        if not candidates:
            followup_result = (
                self._try_contact_followup(
                    text,
                    context,
                )
            )

            if followup_result is not None:
                return followup_result

            return SkillResult(
                handled=False
            )

        candidates.sort(
            key=lambda item: (
                -item[0],
                item[1],
            )
        )

        # ---------------------------------------------------------
        # Execute matching skills
        # ---------------------------------------------------------
        for (
            confidence,
            priority,
            skill,
        ) in candidates:
            print(
                f"[SkillRegistry] Trying "
                f"{skill.name}: "
                f"{confidence:.2f}"
            )

            try:
                result = skill.handle(
                    text,
                    context,
                )

            except Exception as error:
                print(
                    f"Skill execution error "
                    f"[{skill.name}]: "
                    f"{type(error).__name__}: "
                    f"{error}"
                )

                # Try the next matching skill.
                continue

            if not isinstance(
                result,
                SkillResult,
            ):
                result = SkillResult(
                    handled=True,
                    answer=str(result),
                    confidence=confidence,
                )

            if not result.handled:
                print(
                    f"[SkillRegistry] "
                    f"{skill.name} "
                    f"declined request."
                )

                # Try the next matching skill.
                continue

            try:
                result.confidence = max(
                    float(
                        result.confidence
                    ),
                    confidence,
                )

            except (
                TypeError,
                ValueError,
            ):
                result.confidence = (
                    confidence
                )

            # -----------------------------------------------------
            # Remember Contacts as active conversational context.
            #
            # Other skills do not automatically erase it because
            # short Realtime conversation may occur between
            # contact searches.
            #
            # It expires after 60 seconds.
            # -----------------------------------------------------
            if skill.name == "contacts":
                self._remember_skill(
                    "contacts"
                )

            print(
                f"[SkillRegistry] Handled by "
                f"{skill.name}"
            )

            return result

        # ---------------------------------------------------------
        # Matching skills existed but they all declined/failed.
        # Try Contacts follow-up before finally returning False.
        # ---------------------------------------------------------
        followup_result = (
            self._try_contact_followup(
                text,
                context,
            )
        )

        if followup_result is not None:
            return followup_result

        return SkillResult(
            handled=False
        )


_shared_registry = None
_shared_lock = threading.Lock()


def get_skill_registry():
    """
    Return the shared SkillRegistry instance.
    """
    global _shared_registry

    if _shared_registry is None:
        with _shared_lock:
            if _shared_registry is None:
                _shared_registry = (
                    SkillRegistry()
                )

    return _shared_registry