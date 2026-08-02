import re
import unicodedata

from kivy.clock import Clock


class AIActions:
    """Execute safe local M12OS navigation actions."""

    SCREEN_ALIASES = {
        "home": {"home", "home screen", "main screen", "main menu", "launcher"},
        "notes": {"note", "notes", "my note", "my notes", "notes app", "заметка", "заметки"},
        "calendar": {"calendar", "kalendar", "kalender", "calender", "my calendar", "appointments", "events", "calendar app", "календарь", "календар"},
        "music": {"music", "music player", "audio", "audio player", "songs", "музыка", "музыку"},
        "video_player": {"video", "videos", "video player", "movie", "movies", "видео"},
        "files": {"file", "files", "file manager", "my files", "файл", "файлы"},
        "weather": {"weather", "forecast", "weather app", "погода"},
        "calculator": {"calculator", "converter", "calculator converter", "calculator and converter", "калькулятор", "калкулятор"},
        "clock": {"clock", "clok", "klok", "clock app", "часы"},
        "alarm": {"alarm", "alarms", "alarm clock", "будильник"},
        "timer": {"timer", "countdown", "таймер"},
        "stopwatch": {"stopwatch", "stop watch", "секундомер"},
        "settings": {"settings", "setting", "preferences", "configuration", "настройки"},
        "drawing": {"drawing", "draw", "drawing app", "drowing", "droing", "дроинг", "дроуинг", "дроуінг", "рисование", "рисунок"},
        "backup": {"backup", "backups", "backup restore", "backup and restore", "резервная копия"},
        "updater": {"updater", "update", "updates", "system update", "habdater", "апдейтер", "обновление"},
        "bluetooth": {"bluetooth", "bluetooth settings", "bluetooth devices", "блютуз"},
        "ai": {"ai", "assistant", "ai assistant", "m12 ai"},
    }

    BACK_COMMANDS = {
        "back", "go back", "please go back", "take me back", "return",
        "return back", "previous screen", "go to previous screen",
    }

    STOP_LISTENING_COMMANDS = {
        "stop listening", "stop voice", "stop voice mode", "stop conversation",
        "finish listening", "exit voice", "close voice",
    }

    POLITE_WORDS = {"please", "pls", "kindly", "now", "for me"}

    COMMAND_PREFIXES = (
        "open", "show", "show me", "go to", "go", "launch", "start",
        "display", "take me to", "bring up", "switch to", "let me see",
        "i want to see", "i would like to see", "can you open",
        "could you open", "would you open", "can you show",
        "could you show", "would you show",
    )

    @classmethod
    def execute(cls, message, ai_screen):
        command = cls.normalize_command(message)

        if not command:
            return False, ""

        if command in cls.STOP_LISTENING_COMMANDS:
            return cls.stop_listening_and_go_back(ai_screen)

        if command in cls.BACK_COMMANDS:
            return cls.go_back(ai_screen)

        target_screen = cls.find_target_screen(command)

        if target_screen is None:
            return False, ""

        return cls.open_screen(target_screen, ai_screen)

    @classmethod
    def stop_listening_and_go_back(cls, ai_screen):
        cls.stop_voice(ai_screen)
        handled, _ = cls.go_back(ai_screen)
        return handled, "Stopping voice and going back..."

    @classmethod
    def go_back(cls, ai_screen):
        manager = getattr(ai_screen, "manager", None)

        if manager is None:
            return True, "Unable to access the M12OS screen manager."

        history = getattr(ai_screen, "navigation_history", None)

        if history is None:
            history = []
            ai_screen.navigation_history = history

        current = manager.current

        if not history:
            initial = getattr(ai_screen, "return_screen", "home")
            if initial and initial != "ai":
                history.append(initial)

        if current != "ai" and (not history or history[-1] != current):
            history.append(current)

        if len(history) > 1:
            history.pop()
            target = history[-1]
        else:
            target = getattr(ai_screen, "return_screen", "home")

        if (
            not target
            or target == "ai"
            or not manager.has_screen(target)
        ):
            target = "home"

        Clock.schedule_once(
            lambda dt: cls.change_screen(manager, target),
            0.25,
        )

        return True, f"Going back to {cls.display_name(target)}..."

    @classmethod
    def open_screen(cls, target_screen, ai_screen):
        manager = getattr(ai_screen, "manager", None)

        if manager is None:
            return True, "Unable to access the M12OS screen manager."

        if not manager.has_screen(target_screen):
            return (
                True,
                f"{cls.display_name(target_screen)} is not available "
                "on this device.",
            )

        history = getattr(ai_screen, "navigation_history", None)

        if history is None:
            history = []
            ai_screen.navigation_history = history

        current = manager.current

        # The AI screen itself is not part of app navigation history.
        if not history:
            initial = getattr(ai_screen, "return_screen", "home")
            if initial and initial != "ai":
                history.append(initial)

        if current != "ai" and (not history or history[-1] != current):
            history.append(current)

        if target_screen == "home":
            history[:] = ["home"]
        elif not history or history[-1] != target_screen:
            history.append(target_screen)

        Clock.schedule_once(
            lambda dt: cls.change_screen(manager, target_screen),
            0.35,
        )

        return True, f"Opening {cls.display_name(target_screen)}..."

    @staticmethod
    def stop_voice(ai_screen):
        ai_screen.continuous_voice = False

        voice_btn = getattr(ai_screen, "voice_btn", None)
        if voice_btn is not None:
            voice_btn.text = "Voice"

        voice_status = getattr(ai_screen, "voice_status", None)
        if voice_status is not None:
            voice_status.text = "Voice ready"

    @staticmethod
    def change_screen(manager, target_screen):
        try:
            manager.current = target_screen
        except Exception as error:
            print(
                "AI screen-change error: "
                f"{type(error).__name__}: {error}"
            )

    @classmethod
    def find_target_screen(cls, command):
        cleaned = cls.remove_polite_words(command)
        direct = cls.match_alias(cleaned)

        if direct:
            return direct

        for prefix in sorted(cls.COMMAND_PREFIXES, key=len, reverse=True):
            if cleaned.startswith(prefix + " "):
                requested = cls.remove_leading_articles(
                    cleaned[len(prefix):].strip()
                )
                target = cls.match_alias(requested)

                if target:
                    return target

        return None

    @classmethod
    def match_alias(cls, text):
        normalized = cls.remove_leading_articles(
            cls.remove_polite_words(text)
        )

        for screen_name, aliases in cls.SCREEN_ALIASES.items():
            for alias in aliases:
                if normalized == cls.normalize_command(alias):
                    return screen_name

        return None

    @classmethod
    def normalize_command(cls, message):
        command = str(message).strip().lower().replace("’", "'")

        # Speech recognition may return accented characters,
        # for example "kalendár" instead of "calendar".
        # Remove accents before matching local commands.
        command = unicodedata.normalize("NFKD", command)
        command = "".join(
            character
            for character in command
            if not unicodedata.combining(character)
        )

        command = re.sub(r"[.,!?;:]+", " ", command)
        return " ".join(command.split())

    @classmethod
    def remove_polite_words(cls, command):
        result = cls.normalize_command(command)
        changed = True

        while changed:
            changed = False

            for word in sorted(cls.POLITE_WORDS, key=len, reverse=True):
                if result == word:
                    return ""

                if result.startswith(word + " "):
                    result = result[len(word):].strip()
                    changed = True

                if result.endswith(" " + word):
                    result = result[:-len(word)].strip()
                    changed = True

        return result

    @staticmethod
    def remove_leading_articles(text):
        result = str(text).strip()
        changed = True

        while changed:
            changed = False

            for article in ("the ", "my ", "a ", "an "):
                if result.startswith(article):
                    result = result[len(article):].strip()
                    changed = True

        return result

    @staticmethod
    def display_name(screen_name):
        names = {
            "home": "Home",
            "notes": "Notes",
            "calendar": "Calendar",
            "music": "Music",
            "video_player": "Video Player",
            "files": "Files",
            "weather": "Weather",
            "calculator": "Calculator",
            "clock": "Clock",
            "alarm": "Alarm",
            "timer": "Timer",
            "stopwatch": "Stopwatch",
            "settings": "Settings",
            "drawing": "Drawing",
            "backup": "Backup and Restore",
            "updater": "Updater",
            "bluetooth": "Bluetooth",
            "ai": "AI Assistant",
        }

        return names.get(
            screen_name,
            screen_name.replace("_", " ").title(),
        )