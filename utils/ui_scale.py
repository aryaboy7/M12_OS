from kivy.core.window import Window


def device_profile():
    """
    Known M12 OS logical screen sizes:
    - Mac test:       900 x 650
    - M12:            640 x 1046
    - Android tablet: 800 x 1280
    - Phone:         1080 x 2123
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


def font(base):
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