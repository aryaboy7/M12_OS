from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from config.version import VERSION
from utils.config_manager import ConfigManager
from utils.updater import Updater
from utils.ui_scale import font


class UpdaterScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = ConfigManager()
        self.updater = Updater(config=self.config)
        self.latest_info = None
        self.downloaded_zip = None

        root = BoxLayout(orientation="vertical", padding=15, spacing=10)

        root.add_widget(Label(text="Updater", font_size=font(34), bold=True, size_hint=(1, 0.12)))

        self.status_label = Label(
            text=f"Current version: {VERSION}\nReady.",
            font_size=font(20),
            size_hint=(1, 0.31)
        )
        root.add_widget(self.status_label)

        check_btn = Button(
            text="1. Check for Update",
            font_size=font(22),
            size_hint=(1, 0.105),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        check_btn.bind(on_press=self.check_update)
        root.add_widget(check_btn)

        self.download_btn = Button(
            text="2. Download Update",
            font_size=font(22),
            size_hint=(1, 0.105),
            disabled=True,
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        self.download_btn.bind(on_press=self.download_update)
        root.add_widget(self.download_btn)

        self.install_btn = Button(
            text="3. Install Downloaded Update",
            font_size=font(22),
            size_hint=(1, 0.105),
            disabled=True,
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        self.install_btn.bind(on_press=self.install_update)
        root.add_widget(self.install_btn)

        self.restart_btn = Button(
            text="4. Restart M12 OS",
            font_size=font(22),
            size_hint=(1, 0.105),
            disabled=True,
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        self.restart_btn.bind(on_press=self.restart_app)
        root.add_widget(self.restart_btn)

        back_btn = Button(text="< Back", font_size=font(22), size_hint=(1, 0.105))
        back_btn.bind(on_press=self.go_back)
        root.add_widget(back_btn)

        self.add_widget(root)

    def check_update(self, instance):
        self.status_label.text = "Checking GitHub update.json..."
        self.download_btn.disabled = True
        self.install_btn.disabled = True
        self.restart_btn.disabled = True
        Clock.schedule_once(lambda dt: self._do_check(), 0.1)

    def _do_check(self):
        info = self.updater.check()
        self.latest_info = info

        if info.get("error"):
            self.status_label.text = "Update check failed:\n" + info.get("error", "Unknown error")
            return

        remote = info.get("version", "unknown")
        message = info.get("message") or info.get("notes") or ""

        if info.get("update_available"):
            self.status_label.text = f"Update available!\nCurrent: {VERSION}\nNew: {remote}\n\n{message}"
            self.download_btn.disabled = False
        else:
            self.status_label.text = f"No update available.\nCurrent: {VERSION}\nRemote: {remote}"

    def download_update(self, instance):
        if not self.latest_info:
            self.status_label.text = "Check update first."
            return

        url = self.latest_info.get("zip_url") or self.latest_info.get("file_url")
        if not url:
            self.status_label.text = "No zip_url found in update.json."
            return

        self.status_label.text = "Downloading update ZIP..."
        self.download_btn.disabled = True
        Clock.schedule_once(lambda dt: self._do_download(url), 0.1)

    def _do_download(self, url):
        result = self.updater.download(url)

        if result.get("ok"):
            self.downloaded_zip = result.get("path")
            self.status_label.text = "Downloaded:\n" + self.downloaded_zip + "\n\nNow press Install."
            self.install_btn.disabled = False
        else:
            self.status_label.text = "Download failed:\n" + result.get("error", "Unknown error")
            self.download_btn.disabled = False

    def install_update(self, instance):
        self.status_label.text = "Installing...\nCreating backup first."
        self.install_btn.disabled = True
        Clock.schedule_once(lambda dt: self._do_install(), 0.1)

    def _do_install(self):
        result = self.updater.install_zip(self.downloaded_zip)

        if result.get("ok"):
            self.status_label.text = (
                "Update installed.\n"
                f"Files copied: {result.get('files_copied')}\n"
                f"Backup: {result.get('backup')}\n\n"
                "Press Restart M12 OS."
            )
            self.restart_btn.disabled = False
        else:
            self.status_label.text = "Install failed:\n" + result.get("error", "Unknown error")
            self.install_btn.disabled = False

    def restart_app(self, instance):
        self.status_label.text = "Restarting..."
        Clock.schedule_once(lambda dt: self.updater.restart_app(), 0.2)

    def go_back(self, instance):
        self.manager.current = "settings"
