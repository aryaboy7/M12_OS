import threading

from services.skills.base_skill import SkillResult


class SkillRegistry:
    def __init__(self, minimum_confidence=0.72):
        self.minimum_confidence = float(minimum_confidence)
        self._skills = []
        self._lock = threading.RLock()

    def register(self, skill):
        with self._lock:
            self._skills = [
                item for item in self._skills
                if item.name != skill.name
            ]
            self._skills.append(skill)
            self._skills.sort(key=lambda item: item.priority)

    def list_names(self):
        with self._lock:
            return [skill.name for skill in self._skills]

    def dispatch(self, message, context):
        text = str(message).strip()
        if not text:
            return SkillResult(handled=False)

        with self._lock:
            skills = list(self._skills)

        winner = None
        winner_confidence = 0.0

        for skill in skills:
            try:
                confidence = float(skill.can_handle(text, context))
            except Exception as error:
                print(
                    f"Skill check error [{skill.name}]: "
                    f"{type(error).__name__}: {error}"
                )
                continue

            confidence = max(0.0, min(1.0, confidence))

            if (
                confidence > winner_confidence
                or (
                    confidence == winner_confidence
                    and winner is not None
                    and skill.priority < winner.priority
                )
            ):
                winner = skill
                winner_confidence = confidence

        if (
            winner is None
            or winner_confidence < self.minimum_confidence
        ):
            return SkillResult(handled=False)

        try:
            result = winner.handle(text, context)
        except Exception as error:
            return SkillResult(
                handled=True,
                answer=(
                    f"{winner.name} skill error: "
                    f"{type(error).__name__}: {error}"
                ),
                confidence=winner_confidence,
            )

        if not isinstance(result, SkillResult):
            result = SkillResult(
                handled=True,
                answer=str(result),
                confidence=winner_confidence,
            )

        result.handled = True
        result.confidence = max(
            result.confidence,
            winner_confidence,
        )
        return result


_shared_registry = None
_shared_lock = threading.Lock()


def get_skill_registry():
    global _shared_registry

    if _shared_registry is None:
        with _shared_lock:
            if _shared_registry is None:
                _shared_registry = SkillRegistry()

    return _shared_registry
