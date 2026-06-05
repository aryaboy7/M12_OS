from kivy.core.window import Window


def font(base):
    w = Window.width

    if w < 500:      # small M12
        return int(base * 2.2)
    elif w < 800:    # phone
        return int(base * 1.8)
    elif w < 1200:   # tablet
        return int(base * 1.4)

    return int(base)


def height(base):
    w = Window.width

    if w < 500:
        return int(base * 1.8)
    elif w < 800:
        return int(base * 1.5)
    elif w < 1200:
        return int(base * 1.25)

    return int(base)