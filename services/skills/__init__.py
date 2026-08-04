from services.skills.context_skill import ContextSkill
from services.skills.registry import get_skill_registry


def register_default_skills():
    registry = get_skill_registry()
    registry.register(ContextSkill())
    return registry
