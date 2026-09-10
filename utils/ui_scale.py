from kivy.core.window import Window
from kivy.utils import platform


# ============================================================
# M12 OS UNIFIED PROPORTIONAL UI SCALING
# ============================================================
#
# Scaling is based on the CURRENT usable Kivy Window size.
#
# There are only two reference layouts:
#
# Portrait reference:   640 x 1046
# Landscape reference:  900 x 650
#
# This is NOT device-specific sizing. Orientation is a layout
# property, not a device type.
#
# All scalable fonts, heights, padding, and spacing use the same
# fit/contain factor:
#
#     min(current_width / reference_width,
#         current_height / reference_height)
#
# That guarantees the complete reference layout fits inside the
# available window while preserving proportions.
#
# device_profile() remains available only for genuine layout /
# platform behavior decisions.
# ============================================================

PORTRAIT_REFERENCE_WIDTH = 640.0
PORTRAIT_REFERENCE_HEIGHT = 1046.0

LANDSCAPE_REFERENCE_WIDTH = 900.0
LANDSCAPE_REFERENCE_HEIGHT = 650.0


def window_size():
    """Return the current usable Kivy window size as floats."""
    width = max(1.0, float(Window.width or LANDSCAPE_REFERENCE_WIDTH))
    height = max(1.0, float(Window.height or LANDSCAPE_REFERENCE_HEIGHT))
    return width, height


def is_portrait_layout():
    width, height = window_size()
    return height > width


def reference_size():
    """
    Return the reference layout for the current orientation.

    Orientation may change the arrangement of the UI, but sizing is never
    selected from Linux/phone/tablet/M12 hard-coded values.
    """
    if is_portrait_layout():
        return PORTRAIT_REFERENCE_WIDTH, PORTRAIT_REFERENCE_HEIGHT

    return LANDSCAPE_REFERENCE_WIDTH, LANDSCAPE_REFERENCE_HEIGHT


def scale_factor():
    """
    Return one shared proportional fit factor for the current window.

    Using min(width scale, height scale) prevents controls or text from
    growing beyond the dimension that actually limits the layout.
    """
    width, height = window_size()
    reference_width, reference_height = reference_size()

    width_scale = width / reference_width
    height_scale = height / reference_height

    return max(0.10, min(width_scale, height_scale))


def scale(value):
    """Scale any numeric UI measurement with the shared factor."""
    return max(1, int(round(float(value) * scale_factor())))


# ------------------------------------------------------------
# Device/layout profile
# ------------------------------------------------------------

def device_profile():
    """
    Device profiles are kept ONLY for genuine layout/behavior choices.

    Never use these profiles for fonts, heights, padding, or spacing.
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
    return scale(base)


def height(base):
    return scale(base)


# ------------------------------------------------------------
# Standard semantic fonts
# ------------------------------------------------------------
#
# Portrait uses the existing M12 logical design values.
# Landscape uses the existing desktop logical design values.
#
# These are REFERENCE DESIGN values, not machine-specific values.
# ------------------------------------------------------------

def _reference_value(portrait_value, landscape_value):
    if is_portrait_layout():
        return portrait_value
    return landscape_value


def title_font():
    return font(_reference_value(32, 26))


def button_font():
    return font(_reference_value(30, 16))


def list_font():
    return font(_reference_value(32, 14))


def text_font():
    return font(_reference_value(22, 14))


def status_font():
    return font(_reference_value(20, 12))


def small_font():
    return font(_reference_value(18, 11))


def input_font():
    return font(_reference_value(30, 20))


def clock_time_font():
    return font(_reference_value(58, 52))


def clock_date_font():
    return font(_reference_value(24, 20))


# ------------------------------------------------------------
# Standard semantic heights
# ------------------------------------------------------------

def button_height():
    return height(_reference_value(66, 48))


def row_height():
    return height(_reference_value(96, 60))


def small_row_height():
    return height(_reference_value(66, 44))


def input_height():
    return height(_reference_value(72, 52))


def top_bar_height():
    return height(_reference_value(46, 34))


def padding_size():
    return scale(_reference_value(10, 10))


def spacing_size():
    return scale(_reference_value(8, 8))


# ------------------------------------------------------------
# AI screen sizing
# ------------------------------------------------------------

def ai_layout():
    """
    Central sizing source for screens/ai_screen.py.

    Relative vertical layout proportions remain unchanged.
    Every pixel/font measurement uses the same proportional scale factor.
    """
    if is_portrait_layout():
        values = {
            "screen_padding": 10,
            "screen_spacing": 7,
            "mode_font": 15,
            "section_font": 13,
            "chat_font": 17,
            "input_font": 17,
            "message_button_font": 13,
            "log_font": 11,
            "log_button_font": 12,
            "back_font": 15,
            "android_chat_font": 17,
        }
    else:
        values = {
            "screen_padding": 10,
            "screen_spacing": 7,
            "mode_font": 16,
            "section_font": 14,
            "chat_font": 17,
            "input_font": 17,
            "message_button_font": 14,
            "log_font": 11,
            "log_button_font": 13,
            "back_font": 16,
            "android_chat_font": 17,
        }

    return {
        "screen_padding": scale(values["screen_padding"]),
        "screen_spacing": scale(values["screen_spacing"]),

        "mode_hint": 0.070,
        "section_title_hint": 0.032,
        "chat_hint": 0.355,
        "input_hint": 0.110,
        "message_buttons_hint": 0.072,
        "log_hint": 0.110,
        "log_buttons_hint": 0.060,
        "back_hint": 0.055,

        "mode_font": font(values["mode_font"]),
        "section_font": font(values["section_font"]),
        "chat_font": font(values["chat_font"]),
        "input_font": font(values["input_font"]),
        "message_button_font": font(values["message_button_font"]),
        "log_font": font(values["log_font"]),
        "log_button_font": font(values["log_button_font"]),
        "back_font": font(values["back_font"]),
        "android_chat_font": font(values["android_chat_font"]),
    }