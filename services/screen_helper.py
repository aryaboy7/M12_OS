from typing import Any


class ScreenHelper:
    """Safe access to M12OS screens from AI skills."""

    @staticmethod
    def open_screen(context: Any, screen_name: str) -> bool:
        method = getattr(context, "open_screen", None)
        if not callable(method):
            return False

        try:
            return bool(method(screen_name))
        except Exception as error:
            print(
                "ScreenHelper open_screen error: "
                f"{type(error).__name__}: {error}"
            )
            return False

    @staticmethod
    def get_screen(context: Any, screen_name: str):
        method = getattr(context, "get_screen", None)
        if not callable(method):
            return None

        try:
            return method(screen_name)
        except Exception as error:
            print(
                "ScreenHelper get_screen error: "
                f"{type(error).__name__}: {error}"
            )
            return None

    @classmethod
    def find_screen(cls, context: Any, names, open_it: bool = False):
        if isinstance(names, str):
            names = (names,)

        for name in tuple(names or ()):
            if open_it and not cls.open_screen(context, name):
                continue

            screen = cls.get_screen(context, name)
            if screen is not None:
                return True, screen, name

        return False, None, None

    @staticmethod
    def call(screen: Any, method_name: str, *args, **kwargs):
        method = getattr(screen, method_name, None)
        if not callable(method):
            return False, None

        try:
            return True, method(*args, **kwargs)
        except TypeError:
            try:
                return True, method()
            except Exception as error:
                print(
                    "ScreenHelper call error: "
                    f"{type(error).__name__}: {error}"
                )
                return False, None
        except Exception as error:
            print(
                "ScreenHelper call error: "
                f"{type(error).__name__}: {error}"
            )
            return False, None


def open_screen(context: Any, screen_name: str) -> bool:
    return ScreenHelper.open_screen(context, screen_name)


def get_screen(context: Any, screen_name: str):
    return ScreenHelper.get_screen(context, screen_name)
