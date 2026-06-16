from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from config.version import VERSION
from utils.config_manager import ConfigManager
from utils.updater import Updater
from utils.ui_scale import (
    title_font,
    button_font,
    text_font,
    button_height,
    padding_size,
    spacing_size,
)


class UpdaterScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.config = ConfigManager()
        self.updater = Updater(config=self.config)

        self.latest_info = None
        self.downloaded_zip = None

        root = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size(),
        )

        root.add_widget(
            Label(
                text="Updater",
                font_size=title_font(),
                bold=True,
                size_hint=(1, 0.11),
            )
        )

        self.scroll = ScrollView(
            size_hint=(1, 0.42),
            do_scroll_x=False,
            do_scroll_y=True,
        )

        self.status = Label(
            text=(
                f"Current version: {VERSION}\n\n"
                "Updater uses GitHub Releases.\n\n"
                "Release tag example:\n"
                "M12_OS0.4.17\n\n"
                "ZIP asset example:\n"
                "M12_OS0_4_17.zip"
            ),
            font_size=text_font(),
            size_hint_y=None,
            halign="left",
            valign="top",
            padding=(padding_size(), padding_size()),
        )

        self.status.bind(
            width=lambda inst, val: setattr(inst, "text_size", (val - padding_size(), None))
        )

        self.status.bind(
            texture_size=lambda inst, val: setattr(inst, "height", val[1] + padding_size())
        )

        self.scroll.add_widget(self.status)
        root.add_widget(self.scroll)

        check_btn = Button(
            text="1. Check Latest Release",
            font_size=button_font(),
            size_hint=(1, None),
            height=button_height(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
        )
        check_btn.bind(on_press=self.check_update)
        root.add_widget(check_btn)

        self.download_btn = Button(
            text="2. Download ZIP",
            font_size=button_font(),
            size_hint=(1, None),
            height=button_height(),
            disabled=True,
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1),
        )
        self.download_btn.bind(on_press=self.download_update)
        root.add_widget(self.download_btn)

        self.install_btn = Button(
            text="3. Install ZIP",
            font_size=button_font(),
            size_hint=(1, None),
            height=button_height(),
            disabled=True,
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1),
        )
        self.install_btn.bind(on_press=self.install_update)
        root.add_widget(self.install_btn)

        self.restart_btn = Button(
            text="4. Restart M12 OS",
            font_size=button_font(),
            size_hint=(1, None),
            height=button_height(),
            disabled=True,
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1),
        )
        self.restart_btn.bind(on_press=self.restart_app)
        root.add_widget(self.restart_btn)

        back_btn = Button(
            text="< Back",
            font_size=button_font(),
            size_hint=(1, None),
            height=button_height(),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1),
        )
        back_btn.bind(on_press=self.go_back)
        root.add_widget(back_btn)

        self.add_widget(root)

    def set_status(self, text):
        self.status.text = text
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 1), 0.05)

    def check_update(self, instance):
        self.set_status("Checking latest GitHub Release...")

        self.download_btn.disabled = True
        self.install_btn.disabled = True
        self.restart_btn.disabled = True

        Clock.schedule_once(lambda dt: self._do_check(), 0.1)

    def _do_check(self):
        info = self.updater.check()
        self.latest_info = info

        if info.get("error"):
            self.set_status(
                "Update check failed:\n\n"
                + info.get("error", "Unknown error")
            )
            return

        remote = info.get("version", "unknown")
        tag = info.get("tag", "")
        asset = info.get("asset_name", "")
        message = info.get("notes") or info.get("message") or ""

        if info.get("update_available"):
            self.set_status(
                "Update Available\n\n"
                f"Current: {VERSION}\n"
                f"Latest: {remote}\n\n"
                f"Tag:\n{tag}\n\n"
                f"Asset:\n{asset}\n\n"
                f"{message}\n\n"
                "Press Download ZIP."
            )
            self.download_btn.disabled = False
        else:
            self.set_status(
                "No update available.\n\n"
                f"Current: {VERSION}\n"
                f"Latest: {remote}\n\n"
                f"Tag:\n{tag}\n\n"
                f"Asset:\n{asset}"
            )

    def download_update(self, instance):
        if not self.latest_info:
            self.set_status("Check latest release first.")
            return

        file_url = self.latest_info.get("file_url")

        if not file_url:
            self.set_status(
                "No ZIP asset found in latest GitHub Release.\n\n"
                "Release must contain asset like:\n"
                "M12_OS0_4_17.zip"
            )
            return

        self.set_status("Downloading update ZIP...")
        self.download_btn.disabled = True

        Clock.schedule_once(lambda dt: self._do_download(file_url), 0.1)

    def _do_download(self, file_url):
        result = self.updater.download(file_url)

        if result.get("ok"):
            self.downloaded_zip = result.get("path")
            filename = self.downloaded_zip.split("/")[-1]

            self.set_status(
                "Download complete.\n\n"
                f"File:\n{filename}\n\n"
                "Press Install ZIP."
            )

            self.install_btn.disabled = False
        else:
            self.set_status(
                "Download failed:\n\n"
                + result.get("error", "Unknown error")
            )

            self.download_btn.disabled = False

    def install_update(self, instance):
        self.set_status(
            "Installing update...\n\n"
            "Creating backup first."
        )

        self.install_btn.disabled = True

        Clock.schedule_once(lambda dt: self._do_install(), 0.1)

    def _do_install(self):
        result = self.updater.install_zip(self.downloaded_zip)

        if result.get("ok"):
            self.set_status(
                "Update installed.\n\n"
                f"Files copied: {result.get('files_copied')}\n"
                f"Files skipped: {result.get('files_skipped')}\n\n"
                "Backup created.\n\n"
                "Press Restart M12 OS."
            )

            self.restart_btn.disabled = False
        else:
            self.set_status(
                "Install failed:\n\n"
                + result.get("error", "Unknown error")
            )

            self.install_btn.disabled = False

    def restart_app(self, instance):
        self.set_status(
            "Restarting M12 OS...\n\n"
            "On Android, fully close and reopen app if restart does not happen."
        )

        Clock.schedule_once(lambda dt: self.updater.restart_app(), 0.2)

    def go_back(self, instance):
        self.manager.current = "settings"
