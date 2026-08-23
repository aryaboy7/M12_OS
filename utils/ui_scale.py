from kivy.core.window import Window
from kivy.utils import platform


def device_profile():
    """
    M12 OS device profiles.

    Known logical screen sizes:
    - Mac test:        900 x 650
    - Linux laptop:    desktop/laptop window
    - M12 device:      640 x 1046
    - Android tablet:  800 x 1280
    - Android phone:   1080 x 2123
    """
    w = Window.width
    h = Window.height

    if platform == "linux":
        return "linux"

    if h >= 1800:
        return "phone"

    if w < 700 and h >= 900:
        return "m12"

    if h >= 1100:
        return "tablet"

    return "desktop"


def is_mobile():
    return device_profile() in ("m12", "tablet", "phone")


def is_m12():
    return device_profile() == "m12"


def is_phone():
    return device_profile() == "phone"


def is_tablet():
    return device_profile() == "tablet"


def is_linux():
    return device_profile() == "linux"


# ------------------------------------------------------------
# Basic scale helpers
# ------------------------------------------------------------

def font(base):
    profile = device_profile()

    if profile == "phone":
        scale = 2.05
    elif profile == "tablet":
        scale = 1.45
    elif profile == "m12":
        scale = 1.45
    elif profile == "linux":
        scale = 1.10
    else:
        scale = 1.00

    return max(12, int(base * scale))


def height(base):
    profile = device_profile()

    if profile == "phone":
        scale = 1.90
    elif profile == "tablet":
        scale = 1.35
    elif profile == "m12":
        scale = 1.35
    elif profile == "linux":
        scale = 1.05
    else:
        scale = 1.00

    return int(base * scale)


# ------------------------------------------------------------
# M12 OS standard fonts
# ------------------------------------------------------------

def title_font():
    profile = device_profile()

    if profile == "phone":
        return 58
    if profile == "tablet":
        return 40
    if profile == "m12":
        return 32
    if profile == "linux":
        return 30

    return font(26)


def button_font():
    profile = device_profile()

    if profile == "phone":
        return 58
    if profile == "tablet":
        return 40
    if profile == "m12":
        return 30
    if profile == "linux":
        return 18

    return font(16)


def list_font():
    profile = device_profile()

    if profile == "phone":
        return 64
    if profile == "tablet":
        return 44
    if profile == "m12":
        return 32
    if profile == "linux":
        return 17

    return font(14)


def text_font():
    profile = device_profile()

    if profile == "phone":
        return 44
    if profile == "tablet":
        return 30
    if profile == "m12":
        return 22
    if profile == "linux":
        return 16

    return font(14)


def status_font():
    profile = device_profile()

    if profile == "phone":
        return 28
    if profile == "tablet":
        return 22
    if profile == "m12":
        return 20
    if profile == "linux":
        return 14

    return font(12)


def small_font():
    profile = device_profile()

    if profile == "phone":
        return 28
    if profile == "tablet":
        return 22
    if profile == "m12":
        return 18
    if profile == "linux":
        return 13

    return font(11)


def input_font():
    profile = device_profile()

    if profile == "phone":
        return 56
    if profile == "tablet":
        return 38
    if profile == "m12":
        return 30
    if profile == "linux":
        return 18

    return font(20)


def clock_time_font():
    profile = device_profile()

    if profile == "phone":
        return 96
    if profile == "tablet":
        return 72
    if profile == "m12":
        return 58
    if profile == "linux":
        return 52

    return font(52)


def clock_date_font():
    profile = device_profile()

    if profile == "phone":
        return 44
    if profile == "tablet":
        return 32
    if profile == "m12":
        return 24
    if profile == "linux":
        return 20

    return font(20)


# ------------------------------------------------------------
# M12 OS standard heights
# ------------------------------------------------------------

def button_height():
    profile = device_profile()

    if profile == "phone":
        return 112
    if profile == "tablet":
        return 78
    if profile == "m12":
        return 66
    if profile == "linux":
        return 52

    return height(48)


def row_height():
    profile = device_profile()

    if profile == "phone":
        return 158
    if profile == "tablet":
        return 118
    if profile == "m12":
        return 96
    if profile == "linux":
        return 64

    return height(60)


def small_row_height():
    profile = device_profile()

    if profile == "phone":
        return 108
    if profile == "tablet":
        return 78
    if profile == "m12":
        return 66
    if profile == "linux":
        return 48

    return height(44)


def input_height():
    profile = device_profile()

    if profile == "phone":
        return 120
    if profile == "tablet":
        return 86
    if profile == "m12":
        return 72
    if profile == "linux":
        return 56

    return height(52)


def top_bar_height():
    profile = device_profile()

    if profile == "phone":
        return 72
    if profile == "tablet":
        return 54
    if profile == "m12":
        return 46
    if profile == "linux":
        return 40

    return height(34)


def padding_size():
    profile = device_profile()

    if profile == "phone":
        return 22
    if profile == "tablet":
        return 16
    if profile == "m12":
        return 10
    if profile == "linux":
        return 10

    return 10


def spacing_size():
    profile = device_profile()

    if profile == "phone":
        return 14
    if profile == "tablet":
        return 10
    if profile == "m12":
        return 8
    if profile == "linux":
        return 8

    return 8


# ------------------------------------------------------------
# AI screen sizing
# ------------------------------------------------------------

def ai_layout():
    """
    Central sizing source for screens/ai_screen.py.

    All AI-screen device/profile sizes live here.
    """
    profile = device_profile()

    if profile == "phone":
        return {
            "screen_padding": 12,
            "screen_spacing": 7,
            "mode_hint": 0.065,
            "section_title_hint": 0.030,
            "chat_hint": 0.365,
            "input_hint": 0.105,
            "message_buttons_hint": 0.070,
            "log_hint": 0.105,
            "log_buttons_hint": 0.060,
            "back_hint": 0.055,
            "mode_font": font(16),
            "section_font": font(14),
            "chat_font": font(22),
            "input_font": font(18),
            "message_button_font": font(14),
            "log_font": font(16),
            "log_button_font": font(13),
            "back_font": font(16),
            "android_chat_font": font(22),
        }

    if profile == "tablet":
        return {
            "screen_padding": 12,
            "screen_spacing": 8,
            "mode_hint": 0.070,
            "section_title_hint": 0.032,
            "chat_hint": 0.355,
            "input_hint": 0.110,
            "message_buttons_hint": 0.072,
            "log_hint": 0.110,
            "log_buttons_hint": 0.060,
            "back_hint": 0.055,
            "mode_font": font(16),
            "section_font": font(14),
            "chat_font": font(18),
            "input_font": font(18),
            "message_button_font": font(14),
            "log_font": font(12),
            "log_button_font": font(13),
            "back_font": font(16),
            "android_chat_font": font(18),
        }

    if profile == "m12":
        return {
            "screen_padding": 10,
            "screen_spacing": 7,
            "mode_hint": 0.070,
            "section_title_hint": 0.032,
            "chat_hint": 0.350,
            "input_hint": 0.115,
            "message_buttons_hint": 0.075,
            "log_hint": 0.105,
            "log_buttons_hint": 0.060,
            "back_hint": 0.055,
            "mode_font": font(15),
            "section_font": font(13),
            "chat_font": font(17),
            "input_font": font(17),
            "message_button_font": font(13),
            "log_font": font(11),
            "log_button_font": font(12),
            "back_font": font(15),
            "android_chat_font": font(17),
        }

    if profile == "linux":
        return {
            "screen_padding": 8,
            "screen_spacing": 5,
            "mode_hint": 0.060,
            "section_title_hint": 0.036,
            "chat_hint": 0.390,
            "input_hint": 0.100,
            "message_buttons_hint": 0.060,
            "log_hint": 0.120,
            "log_buttons_hint": 0.052,
            "back_hint": 0.048,
            "mode_font": 22,
            "section_font": 24,
            "chat_font": 30,
            "input_font": 25,
            "message_button_font": 21,
            "log_font": 23,
            "log_button_font": 20,
            "back_font": 21,
            "android_chat_font": 30,
        }

    return {
        "screen_padding": 10,
        "screen_spacing": 7,
        "mode_hint": 0.070,
        "section_title_hint": 0.032,
        "chat_hint": 0.355,
        "input_hint": 0.110,
        "message_buttons_hint": 0.072,
        "log_hint": 0.110,
        "log_buttons_hint": 0.060,
        "back_hint": 0.055,
        "mode_font": font(16),
        "section_font": font(14),
        "chat_font": font(17),
        "input_font": font(17),
        "message_button_font": font(14),
        "log_font": font(11),
        "log_button_font": font(13),
        "back_font": font(16),
        "android_chat_font": font(17),
    }