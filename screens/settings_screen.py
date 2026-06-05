from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner

from config.version import version_text
from utils.config_manager import ConfigManager
from utils.logger import log
from utils.ui_scale import font


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = ConfigManager()

        root = BoxLayout(orientation="vertical", padding=15, spacing=12)

        root.add_widget(Label(text="Settings", font_size=font(34), bold=True, size_hint=(1, 0.13)))
        root.add_widget(Label(text=version_text(), font_size=font(22), size_hint=(1, 0.09)))

        self.theme_spinner = Spinner(
            text=self.config.get("theme", "dark"),
            values=("dark", "light"),
            font_size=font(22),
            size_hint=(1, 0.12),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        self.theme_spinner.bind(text=self.change_theme)
        root.add_widget(self.theme_spinner)

        self.unit_spinner = Spinner(
            text=self.config.get("temperature_unit", "F"),
            values=("F", "C"),
            font_size=font(22),
            size_hint=(1, 0.12),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        self.unit_spinner.bind(text=self.change_unit)
        root.add_widget(self.unit_spinner)

        self.channel_spinner = Spinner(
            text=self.config.get("update_channel", "stable"),
            values=("stable", "beta"),
            font_size=font(22),
            size_hint=(1, 0.12),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        self.channel_spinner.bind(text=self.change_channel)
        root.add_widget(self.channel_spinner)

        self.auto_btn = Button(
            text=self.auto_update_text(),
            font_size=font(22),
            size_hint=(1, 0.12),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        self.auto_btn.bind(on_press=self.toggle_auto_update)
        root.add_widget(self.auto_btn)

        updater_btn = Button(
            text="Open Updater",
            font_size=font(22),
            size_hint=(1, 0.12),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        updater_btn.bind(on_press=self.open_updater)
        root.add_widget(updater_btn)

        back_btn = Button(text="< Back", font_size=font(22), size_hint=(1, 0.12))
        back_btn.bind(on_press=self.go_back)
        root.add_widget(back_btn)

        self.add_widget(root)

    def auto_update_text(self):
        return "Auto update check: ON" if self.config.get("auto_update", True) else "Auto update check: OFF"

    def change_theme(self, instance, value):
        self.config.set("theme", value)
        log.info(f"Settings: theme={value}")

    def change_unit(self, instance, value):
        self.config.set("temperature_unit", value)
        log.info(f"Settings: temperature_unit={value}")

    def change_channel(self, instance, value):
        self.config.set("update_channel", value)
        log.info(f"Settings: update_channel={value}")

    def toggle_auto_update(self, instance):
        new_value = not self.config.get("auto_update", True)
        self.config.set("auto_update", new_value)
        self.auto_btn.text = self.auto_update_text()
        log.info(f"Settings: auto_update={new_value}")

    def open_updater(self, instance):
        self.manager.current = "updater"

    def go_back(self, instance):
        self.manager.current = "home"
