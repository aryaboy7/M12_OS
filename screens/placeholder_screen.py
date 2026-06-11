from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from utils.ui_scale import font, height


class PlaceholderScreen(Screen):
    screen_title = "App"
    message = "This app will be added in the next update."

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        root = BoxLayout(
            orientation="vertical",
            padding=height(20),
            spacing=height(15)
        )

        title = Label(
            text=self.screen_title,
            font_size=font(46),
            bold=True,
            size_hint=(1, 0.22),
            halign="center",
            valign="middle"
        )
        title.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        root.add_widget(title)

        message = Label(
            text=self.message,
            font_size=font(32),
            size_hint=(1, 0.58),
            halign="center",
            valign="middle"
        )
        message.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - 20, val[1])))
        root.add_widget(message)

        back_btn = Button(
            text="< Back",
            font_size=font(30),
            size_hint=(1, 0.12),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        back_btn.bind(on_press=self.go_back)
        root.add_widget(back_btn)

        self.add_widget(root)

    def go_back(self, instance):
        self.manager.current = "home"