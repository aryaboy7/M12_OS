from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from utils.ui_scale import font


class PlaceholderScreen(Screen):
    screen_title = "App"
    message = "This app will be added in the next update."

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        root = BoxLayout(orientation="vertical", padding=15, spacing=12)
        root.add_widget(Label(text=self.screen_title, font_size=font(36), bold=True, size_hint=(1, 0.25)))
        root.add_widget(Label(text=self.message, font_size=font(24), size_hint=(1, 0.55)))

        back_btn = Button(text="< Back", font_size=font(24), size_hint=(1, 0.15))
        back_btn.bind(on_press=self.go_back)
        root.add_widget(back_btn)

        self.add_widget(root)

    def go_back(self, instance):
        self.manager.current = "home"
