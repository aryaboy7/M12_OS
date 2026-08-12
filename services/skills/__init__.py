from services.skills.alarm_skill import AlarmSkill
from services.skills.calculator_skill import CalculatorSkill
from services.skills.calendar_skill import CalendarSkill
from services.skills.context_skill import ContextSkill
from services.skills.music_skill import MusicSkill
from services.skills.note_skill import NotesSkill
from services.skills.reminder_skill import ReminderSkill
from services.skills.stopwatch_skill import StopwatchSkill
from services.skills.timer_skill import TimerSkill
from services.skills.time_skill import TimeSkill
from services.skills.weather_skill import WeatherSkill

from services.skills.registry import get_skill_registry


def register_default_skills():
    """
    Explicitly register all built-in M12 skills.

    Android/python-for-android may not reliably discover packaged
    *_skill.py files using filesystem globbing, so core M12 skills
    are registered explicitly.

    Dynamic discovery can still be used separately for optional
    or future skills.
    """
    registry = get_skill_registry()

    skill_classes = (
        AlarmSkill,
        CalculatorSkill,
        CalendarSkill,
        ContextSkill,
        MusicSkill,
        NotesSkill,
        ReminderSkill,
        StopwatchSkill,
        TimerSkill,
        TimeSkill,
        WeatherSkill,
    )

    loaded = []
    errors = []

    for skill_class in skill_classes:
        try:
            skill = skill_class()

            registry.register(
                skill
            )

            loaded.append(
                skill.name
            )

            print(
                "[BuiltInSkills] Loaded "
                f"{skill_class.__name__} "
                f"as '{skill.name}'"
            )

        except Exception as error:
            message = (
                f"{skill_class.__name__}: "
                f"{type(error).__name__}: "
                f"{error}"
            )

            errors.append(
                message
            )

            print(
                "[BuiltInSkills] Load failed: "
                f"{message}"
            )

    print(
        "[BuiltInSkills] Ready: "
        f"{len(loaded)} skill(s), "
        f"{len(errors)} error(s)."
    )

    return {
        "loaded": loaded,
        "errors": errors,
    }