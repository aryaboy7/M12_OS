"""
Automatic skill discovery for M12OS.

A skill module is loaded when:

1. It is inside services/skills.
2. Its filename ends with ``_skill.py``.
3. It contains a concrete subclass of BaseSkill.
4. The class is defined in that module.

A skill class may set ``auto_load = False`` to disable automatic loading.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Iterable

from services.skills.base_skill import BaseSkill


SKILLS_PACKAGE = "services.skills"
SKILLS_DIRECTORY = Path(__file__).resolve().parent

# Framework modules are never treated as user-facing skills.
EXCLUDED_FILES = {
    "base_skill.py",
}


def discover_skill_modules() -> list[str]:
    """Return importable module names for every ``*_skill.py`` file."""
    module_names: list[str] = []

    for path in sorted(SKILLS_DIRECTORY.glob("*_skill.py")):
        if path.name in EXCLUDED_FILES:
            continue

        if path.name.startswith("_"):
            continue

        module_names.append(
            f"{SKILLS_PACKAGE}.{path.stem}"
        )

    return module_names


def discover_skill_classes(module) -> Iterable[type[BaseSkill]]:
    """Yield concrete BaseSkill subclasses defined by one module."""
    for _, candidate in inspect.getmembers(
        module,
        inspect.isclass,
    ):
        if candidate is BaseSkill:
            continue

        if candidate.__module__ != module.__name__:
            continue

        if not issubclass(candidate, BaseSkill):
            continue

        if inspect.isabstract(candidate):
            continue

        if getattr(candidate, "auto_load", True) is False:
            continue

        yield candidate


def load_all_skills(registry) -> dict:
    """
    Discover, instantiate, and register all available skills.

    One broken skill does not prevent M12OS from starting. The returned
    dictionary is useful for diagnostics and startup logging.
    """
    loaded: list[str] = []
    errors: list[str] = []

    for module_name in discover_skill_modules():
        try:
            module = importlib.import_module(module_name)
        except Exception as error:
            message = (
                f"{module_name}: "
                f"{type(error).__name__}: {error}"
            )
            errors.append(message)
            print(f"[SkillLoader] Import failed: {message}")
            continue

        found_class = False

        for skill_class in discover_skill_classes(module):
            found_class = True

            try:
                skill = skill_class()
                registry.register(skill)
                loaded.append(skill.name)
                print(
                    f"[SkillLoader] Loaded "
                    f"{skill_class.__name__} "
                    f"as '{skill.name}'"
                )
            except Exception as error:
                message = (
                    f"{module_name}.{skill_class.__name__}: "
                    f"{type(error).__name__}: {error}"
                )
                errors.append(message)
                print(f"[SkillLoader] Load failed: {message}")

        if not found_class:
            print(
                f"[SkillLoader] No concrete BaseSkill "
                f"class found in {module_name}"
            )

    print(
        f"[SkillLoader] Ready: {len(loaded)} skill(s), "
        f"{len(errors)} error(s)."
    )

    return {
        "loaded": loaded,
        "errors": errors,
    }
