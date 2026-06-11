from kivy.core.window import Window


def font(base):
    w = Window.width

    # M12 / small Android
    if w < 700:
        scale = 1.15

    # Android phone / tablet
    elif w < 900:
        scale = 1.20

    # Mac test window 900x650
    elif w < 1200:
        scale = 1.00

    else:
        scale = 1.00

    return int(base * scale)


def height(base):
    w = Window.width

    if w < 700:
        scale = 1.20
    elif w < 900:
        scale = 1.15
    elif w < 1200:
        scale = 1.00
    else:
        scale = 1.00

    return int(base * scale)