from kivy.core.window import Window


def is_m12():
    return Window.width < 700


def is_android_tablet_or_phone():
    return 700 <= Window.width < 900


def font(base):
    """
    M12 OS global font scaling.

    Known logical widths:
    - M12: around 640
    - Samsung/Android tablet: around 800
    - Mac test window: around 900
    """
    w = Window.width

    if w < 700:
        scale = 1.35      # M12 readable
    elif w < 900:
        scale = 1.20      # Android phone/tablet
    elif w < 1200:
        scale = 1.00      # Mac test window
    else:
        scale = 1.00

    return max(12, int(base * scale))


def height(base):
    w = Window.width

    if w < 700:
        scale = 1.30
    elif w < 900:
        scale = 1.15
    elif w < 1200:
        scale = 1.00
    else:
        scale = 1.00

    return int(base * scale)
