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

        # One generic expected-follow-up state.
        #
        # The registry does not know what a "contact name", "city",
        # "duration", etc. means. The skill owns that meaning.
        self._pending_followup = None

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

            pending = self._pending_followup

            if (
                pending
                and pending.get("skill_name") == target
            ):
                self._pending_followup = None

    def clear(
        self,
    ):
        """
        Remove all registered skills and pending continuation state.
        """
        with self._lock:
            self._skills.clear()
            self._pending_followup = None

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
    # GENERIC EXPECTED FOLLOW-UP
    # =============================================================

    def clear_followup_context(self):
        """
        Clear any skill that is waiting for another user value.

        Kept with the old public method name so existing callers remain
        compatible.
        """
        with self._lock:
            self._pending_followup = None

    def _set_pending_followup(
        self,
        skill,
        result,
    ):
        """
        Store continuation state declared by a SkillResult.

        The registry stores only routing metadata. It never interprets
        the semantic meaning of expected_followup.
        """
        expected = str(
            result.expected_followup or ""
        ).strip()

        if not expected:
            with self._lock:
                self._pending_followup = None
            return

        try:
            timeout = float(
                result.followup_timeout
            )
        except (
            TypeError,
            ValueError,
        ):
            timeout = 120.0

        timeout = max(
            1.0,
            timeout,
        )

        followup_data = (
            dict(result.followup_data)
            if isinstance(
                result.followup_data,
                dict,
            )
            else {}
        )

        pending = {
            "skill_name": str(
                skill.name
            ),
            "expected_followup": expected,
            "followup_data": followup_data,
            "expires_at": (
                time.monotonic()
                + timeout
            ),
        }

        with self._lock:
            self._pending_followup = pending

        print(
            "[SkillRegistry] Waiting for "
            f"{expected} from {skill.name}"
        )

    def _get_pending_followup(self):
        """
        Return active continuation state or None when expired.
        """
        with self._lock:
            pending = self._pending_followup

            if not pending:
                return None

            expires_at = float(
                pending.get(
                    "expires_at",
                    0.0,
                )
            )

            if (
                expires_at > 0.0
                and time.monotonic() >= expires_at
            ):
                self._pending_followup = None
                return None

            return dict(
                pending
            )

    @staticmethod
    def _coerce_result(
        result,
        confidence=1.0,
    ):
        """
        Convert legacy string-like skill results to SkillResult.
        """
        if isinstance(
            result,
            SkillResult,
        ):
            return result

        return SkillResult(
            handled=True,
            answer=str(result),
            confidence=confidence,
        )

    def _dispatch_pending_followup(
        self,
        text,
        context,
    ):
        """
        Route the next utterance directly to the skill that explicitly
        requested it.

        Returns:
            SkillResult when a pending continuation existed.
            None when there is no active continuation.
        """
        pending = self._get_pending_followup()

        if pending is None:
            return None

        skill_name = str(
            pending.get(
                "skill_name",
                "",
            )
        ).strip()

        expected = str(
            pending.get(
                "expected_followup",
                "",
            )
        ).strip()

        followup_data = pending.get(
            "followup_data",
            {},
        )

        skill = self.get(
            skill_name
        )

        if skill is None:
            self.clear_followup_context()

            return SkillResult(
                handled=False
            )

        # Consume the previous expectation before execution. If the skill
        # still needs input, its returned SkillResult will explicitly create
        # a new expectation.
        self.clear_followup_context()

        print(
            "[SkillRegistry] Follow-up -> "
            f"{skill_name} ({expected}): {text}"
        )

        try:
            result = skill.handle_followup(
                message=text,
                context=context,
                expected_followup=expected,
                followup_data=followup_data,
            )

        except Exception as error:
            print(
                "Skill follow-up execution error "
                f"[{skill_name}]: "
                f"{type(error).__name__}: {error}"
            )

            return SkillResult(
                handled=False
            )

        result = self._coerce_result(
            result,
            confidence=1.0,
        )

        if result.handled:
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

            self._set_pending_followup(
                skill,
                result,
            )

            print(
                "[SkillRegistry] Follow-up handled by "
                f"{skill_name}"
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

        Routing order:

            1. Explicit expected follow-up, if one is active.
            2. Normal confidence-based skill routing.

        No skill-specific guessing exists in this registry.
        """
        text = str(
            message or ""
        ).strip()

        if not text:
            return SkillResult(
                handled=False
            )

        # ---------------------------------------------------------
        # Explicit continuation always wins.
        #
        # Example:
        #   User: Find contact
        #   Contacts: Tell me the contact name.
        #   User: Victoria Shpiller
        #
        # The second utterance goes directly back to ContactsSkill
        # without needing can_handle() to recognize a bare name.
        # ---------------------------------------------------------
        followup_result = (
            self._dispatch_pending_followup(
                text,
                context,
            )
        )

        if followup_result is not None:
            return followup_result

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

        if not candidates:
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

                continue

            result = self._coerce_result(
                result,
                confidence=confidence,
            )

            if not result.handled:
                print(
                    f"[SkillRegistry] "
                    f"{skill.name} "
                    "declined request."
                )
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
                result.confidence = confidence

            self._set_pending_followup(
                skill,
                result,
            )

            print(
                "[SkillRegistry] Handled by "
                f"{skill.name}"
            )

            return result

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