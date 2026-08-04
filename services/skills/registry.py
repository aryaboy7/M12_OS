import threading

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
                    f"Skill check error [{skill.name}]: "
                    f"{type(error).__name__}: {error}"
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

            if confidence < self.minimum_confidence:
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
                    f"{type(error).__name__}: {error}"
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
                    f"{skill.name} declined request."
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
                result.confidence = confidence

            print(
                f"[SkillRegistry] Handled by "
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