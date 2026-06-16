from kivy.core.window import Window


def device_profile():
    """
    M12 OS device profiles.

    Known logical screen sizes:
    - Mac test:        900 x 650
    - M12 device:      640 x 1046
    - Android tablet:  800 x 1280
    - Android phone:  1080 x 2123
    """
    w = Window.width
    h = Window.height

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


# ------------------------------------------------------------
# Basic scale helpers
# ------------------------------------------------------------

def font(base):
    """
    General font scaling.
    Use this for custom sizes only.
    For normal screens, prefer:
    title_font(), button_font(), list_font(), text_font(), small_font()
    """
    profile = device_profile()

    if profile == "phone":
        scale = 2.05
    elif profile == "tablet":
        scale = 1.45
    elif profile == "m12":
        scale = 1.45
    else:
        scale = 1.00

    return max(12, int(base * scale))


def height(base):
    """
    General height scaling.
    Use this for custom sizes only.
    For normal widgets, prefer:
    button_height(), row_height(), input_height()
    """
    profile = device_profile()

    if profile == "phone":
        scale = 1.90
    elif profile == "tablet":
        scale = 1.35
    elif profile == "m12":
        scale = 1.35
    else:
        scale = 1.00

    return int(base * scale)


# ------------------------------------------------------------
# M12 OS standard fonts
# These are based on the File Manager screen, which is the
# current visual standard for Android phone readability.
# ------------------------------------------------------------

def title_font():
    profile = device_profile()

    if profile == "phone":
        return 58
    if profile == "tablet":
        return 40
    if profile == "m12":
        return 32

    return font(26)


def button_font():
    profile = device_profile()

    if profile == "phone":
        return 58
    if profile == "tablet":
        return 40
    if profile == "m12":
        return 30

    return font(16)


def list_font():
    profile = device_profile()

    if profile == "phone":
        return 64
    if profile == "tablet":
        return 44
    if profile == "m12":
        return 32

    return font(14)


def text_font():
    profile = device_profile()

    if profile == "phone":
        return 44
    if profile == "tablet":
        return 30
    if profile == "m12":
        return 22

    return font(14)


def status_font():
    profile = device_profile()

    if profile == "phone":
        return 28
    if profile == "tablet":
        return 22
    if profile == "m12":
        return 20

    return font(12)


def small_font():
    profile = device_profile()

    if profile == "phone":
        return 28
    if profile == "tablet":
        return 22
    if profile == "m12":
        return 18

    return font(11)


def input_font():
    profile = device_profile()

    if profile == "phone":
        return 56
    if profile == "tablet":
        return 38
    if profile == "m12":
        return 30

    return font(20)


def clock_time_font():
    profile = device_profile()

    if profile == "phone":
        return 96
    if profile == "tablet":
        return 72
    if profile == "m12":
        return 58

    return font(52)


def clock_date_font():
    profile = device_profile()

    if profile == "phone":
        return 44
    if profile == "tablet":
        return 32
    if profile == "m12":
        return 24

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

    return height(48)


def row_height():
    profile = device_profile()

    if profile == "phone":
        return 158
    if profile == "tablet":
        return 118
    if profile == "m12":
        return 96

    return height(60)


def small_row_height():
    profile = device_profile()

    if profile == "phone":
        return 108
    if profile == "tablet":
        return 78
    if profile == "m12":
        return 66

    return height(44)


def input_height():
    profile = device_profile()

    if profile == "phone":
        return 120
    if profile == "tablet":
        return 86
    if profile == "m12":
        return 72

    return height(52)


def top_bar_height():
    profile = device_profile()

    if profile == "phone":
        return 72
    if profile == "tablet":
        return 54
    if profile == "m12":
        return 46

    return height(34)


def padding_size():
    profile = device_profile()

    if profile == "phone":
        return 22
    if profile == "tablet":
        return 16
    if profile == "m12":
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

    return 8
