# M12 OS Settings Screen - shared UI scale version
# v0.4.25 - Storage Settings page improved for Android keyboard
from pathlib import Path
import json
import subprocess
import os

from kivy.utils import platform
from kivy.core.window import Window
from kivy.core.clipboard import Clipboard
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput
from kivy.graphics import Color, Rectangle

from utils.config_manager import ConfigManager
from services.api_key_manager import APIKeyManager
from services.audd_key_manager import AudDKeyManager
from services.spotify_client_manager import SpotifyClientManager
from utils.system_header import create_system_header
from utils.logger import log
from utils.text_editor_popup import open_text_editor
from utils.storage_roots import (
    load_storage_roots,
    save_storage_roots,
)
from utils.ui_scale import (
    title_font,
    button_font,
    text_font,
    status_font,
    row_height,
    button_height,
    padding_size,
    spacing_size,
)


try:
    if Window is not None:
        Window.softinput_mode = "resize"
except Exception:
    # Android may import screens before Kivy has created the Window.
    # The screen can still run; soft keyboard resize is optional here.
    pass


BASE_DIR = Path(__file__).resolve().parent.parent
AI_SETTINGS_FILE = BASE_DIR / "config" / "ai_settings.json"
LOG_FILE = BASE_DIR / "logs" / "m12_os.log"
COPY_FILE = BASE_DIR / "logs" / "copied_log_text.txt"

BG = (0.04, 0.07, 0.12, 1)
CARD = (0.08, 0.14, 0.24, 1)
CARD_ALT = (0.10, 0.18, 0.30, 1)
BLUE = (0.13, 0.28, 0.48, 1)
GREEN = (0.10, 0.45, 0.20, 1)
ORANGE = (0.45, 0.30, 0.10, 1)
RED = (0.50, 0.15, 0.15, 1)
DARK = (0.10, 0.15, 0.25, 1)
WHITE = (1, 1, 1, 1)


def settings_button_font():
    """Smaller Settings text on Android; desktop keeps shared UI scale."""
    if platform == "android":
        return max(18, int(button_font() * 0.68))
    return button_font()


def settings_text_font():
    if platform == "android":
        return max(16, int(text_font() * 0.72))
    return text_font()


def settings_status_font():
    if platform == "android":
        return max(14, int(status_font() * 0.76))
    return status_font()


def settings_button_height():
    if platform == "android":
        return max(54, int(button_height() * 0.76))
    return button_height()


def settings_row_height():
    if platform == "android":
        return max(48, int(row_height() * 0.76))
    return row_height()


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.config = ConfigManager()
        self.clear_log_pending = False
        self.selected_log_line = ""
        self.log_lines = []

        self.build_settings_view()

    def clear_screen(self):
        self.clear_widgets()

    def add_bg(self, widget):
        with widget.canvas.before:
            Color(*BG)
            rect = Rectangle(pos=widget.pos, size=widget.size)

        widget.bind(
            pos=lambda inst, val: setattr(rect, "pos", inst.pos),
            size=lambda inst, val: setattr(rect, "size", inst.size)
        )

    def get_system_status_text(self):
        if (
            self.manager
            and self.manager.has_screen("home")
        ):
            home = self.manager.get_screen("home")
            provider = getattr(
                home,
                "get_system_status_text",
                None,
            )

            if callable(provider):
                return provider()

        return "WiFi"

    def add_system_header(
        self,
        root,
        title,
        back_callback,
    ):
        header = create_system_header(
            title=title,
            back_callback=back_callback,
            status_provider=self.get_system_status_text,
            ai_active=False,
        )
        root.add_widget(header)
        self.system_header = header

    def make_title(self, text):
        return Label(
            text=text,
            font_size=title_font(),
            bold=True,
            color=WHITE,
            size_hint=(1, 0.10)
        )

    def make_subtitle(self, text):
        return Label(
            text=text,
            font_size=settings_text_font(),
            color=(0.70, 0.85, 1, 1),
            size_hint=(1, 0.06)
        )

    def make_section_label(self, text):
        return Label(
            text=text,
            font_size=settings_text_font(),
            bold=True,
            color=(0.80, 0.95, 1, 1),
            size_hint=(1, 0.07)
        )

    def make_button(self, text, color=BLUE):
        return Button(
            text=text,
            font_size=settings_button_font(),
            size_hint=(1, None),
            height=settings_button_height(),
            background_normal="",
            background_color=color,
            color=WHITE,
            bold=True
        )

    def make_small_button(self, text, color=BLUE):
        return Button(
            text=text,
            font_size=settings_button_font(),
            background_normal="",
            background_color=color,
            color=WHITE,
            bold=True
        )

    def make_spinner(self, text, values):
        return Spinner(
            text=text,
            values=values,
            font_size=settings_button_font(),
            size_hint=(1, None),
            height=settings_button_height(),
            background_normal="",
            background_color=BLUE,
            color=WHITE
        )

    def make_dashboard_card(
        self,
        title,
        subtitle,
        color=CARD,
    ):
        card = BoxLayout(
            orientation="vertical",
            spacing=spacing_size(),
            padding=spacing_size(),
            size_hint_y=None,
            height=max(
                int(settings_button_height() * 2.15),
                112 if platform == "android" else 150,
            ),
        )

        with card.canvas.before:
            Color(*color)
            rect = Rectangle(
                pos=card.pos,
                size=card.size,
            )

        card.bind(
            pos=lambda instance, value: setattr(
                rect,
                "pos",
                instance.pos,
            ),
            size=lambda instance, value: setattr(
                rect,
                "size",
                instance.size,
            ),
        )

        title_label = Label(
            text=str(title),
            font_size=settings_button_font(),
            bold=True,
            color=WHITE,
            size_hint=(1, 0.42),
            halign="center",
            valign="middle",
        )
        title_label.bind(
            size=lambda instance, value: setattr(
                instance,
                "text_size",
                value,
            )
        )
        card.add_widget(title_label)

        subtitle_label = Label(
            text=str(subtitle),
            font_size=settings_status_font(),
            color=(0.72, 0.84, 1, 1),
            size_hint=(1, 0.30),
            halign="center",
            valign="middle",
        )
        subtitle_label.bind(
            size=lambda instance, value: setattr(
                instance,
                "text_size",
                value,
            )
        )
        card.add_widget(subtitle_label)

        return card

    def add_dashboard_button(
        self,
        card,
        text,
        callback,
        color=BLUE,
    ):
        button = Button(
            text=text,
            font_size=settings_button_font(),
            bold=True,
            background_normal="",
            background_color=color,
            color=WHITE,
            size_hint=(1, 0.38),
        )
        button.bind(
            on_press=callback
        )
        card.add_widget(button)
        return button

    def build_settings_view(self, instance=None):
        self.clear_screen()
        self.config = ConfigManager()

        root = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size(),
        )
        self.add_bg(root)

        self.add_system_header(
            root=root,
            title="Settings",
            back_callback=self.go_back,
        )

        dashboard_scroll = ScrollView(
            size_hint=(1, 1),
            do_scroll_x=False,
            do_scroll_y=True,
        )

        dashboard = GridLayout(
            cols=2,
            spacing=spacing_size(),
            padding=(
                0,
                spacing_size(),
                0,
                spacing_size(),
            ),
            size_hint_y=None,
        )
        dashboard.bind(
            minimum_height=dashboard.setter(
                "height"
            )
        )

        weather_card = self.make_dashboard_card(
            "Weather",
            "Temperature unit",
            CARD_ALT,
        )

        self.unit_spinner = Spinner(
            text=self.config.get(
                "temperature_unit",
                "F",
            ),
            values=("F", "C"),
            font_size=settings_button_font(),
            bold=True,
            background_normal="",
            background_color=BLUE,
            color=WHITE,
            size_hint=(1, 0.38),
        )
        self.unit_spinner.bind(
            text=self.change_unit
        )
        weather_card.add_widget(
            self.unit_spinner
        )
        dashboard.add_widget(weather_card)

        updates_card = self.make_dashboard_card(
            "Automatic Updates",
            "Enable or disable update checks",
            CARD,
        )
        self.auto_btn = self.add_dashboard_button(
            updates_card,
            self.auto_update_text(),
            self.toggle_auto_update,
            GREEN
            if self.config.get(
                "auto_update",
                True,
            )
            else RED,
        )
        dashboard.add_widget(updates_card)

        updater_card = self.make_dashboard_card(
            "Updater",
            "Check and install a new M12OS version",
            CARD_ALT,
        )
        self.add_dashboard_button(
            updater_card,
            "Open Updater",
            self.open_updater,
            BLUE,
        )
        dashboard.add_widget(updater_card)

        backup_card = self.make_dashboard_card(
            "Backup",
            "Back up or restore M12OS data",
            CARD,
        )
        self.add_dashboard_button(
            backup_card,
            "Open Backup",
            self.open_backup,
            GREEN,
        )
        dashboard.add_widget(backup_card)

        bluetooth_card = self.make_dashboard_card(
            "Bluetooth",
            "Connect and manage speakers",
            CARD,
        )
        self.add_dashboard_button(
            bluetooth_card,
            "Open Bluetooth",
            self.open_bluetooth,
            BLUE,
        )
        dashboard.add_widget(bluetooth_card)

        storage_card = self.make_dashboard_card(
            "Storage",
            "Internal and external media locations",
            CARD_ALT,
        )
        self.add_dashboard_button(
            storage_card,
            "Open Storage",
            self.build_storage_view,
            BLUE,
        )
        dashboard.add_widget(storage_card)

        openai_key_configured = APIKeyManager.has_key()
        audd_key_configured = AudDKeyManager.has_key()
        spotify_key_configured = (
            SpotifyClientManager.has_client_id()
        )
        security_keys_configured = (
            openai_key_configured
            and audd_key_configured
            and spotify_key_configured
        )

        ai_card = self.make_dashboard_card(
            "Security Key Setup",
            (
                "OpenAI, AudD and Spotify configured"
                if security_keys_configured
                else "Configure API security keys"
            ),
            CARD,
        )

        self.add_dashboard_button(
            ai_card,
            "Open Security Key Setup",
            self.build_ai_setup_view,
            GREEN if security_keys_configured else ORANGE,
        )
        dashboard.add_widget(ai_card)

        echo_enabled = self.speaker_echo_protection_enabled()

        echo_card = self.make_dashboard_card(
            "AI Speaker Mode",
            (
                "Mic pauses while Ace speaks"
                if echo_enabled
                else "Full-duplex listening"
            ),
            CARD_ALT,
        )

        self.echo_protection_btn = self.add_dashboard_button(
            echo_card,
            self.speaker_echo_protection_text(),
            self.toggle_speaker_echo_protection,
            GREEN if echo_enabled else ORANGE,
        )
        dashboard.add_widget(echo_card)

        log_card = self.make_dashboard_card(
            "System Log",
            "Read, copy, or clear the M12OS log",
            CARD_ALT,
        )
        self.add_dashboard_button(
            log_card,
            "Open Log",
            self.build_log_view,
            ORANGE,
        )
        dashboard.add_widget(log_card)

        info_card = self.make_dashboard_card(
            "About Settings",
            "Changes are saved automatically",
            CARD,
        )
        info_label = Label(
            text="M12OS",
            font_size=settings_button_font(),
            bold=True,
            color=(0.72, 0.88, 1, 1),
            size_hint=(1, 0.38),
            halign="center",
            valign="middle",
        )
        info_label.bind(
            size=lambda instance, value: setattr(
                instance,
                "text_size",
                value,
            )
        )
        info_card.add_widget(info_label)
        dashboard.add_widget(info_card)

        dashboard_scroll.add_widget(
            dashboard
        )
        root.add_widget(
            dashboard_scroll
        )

        self.add_widget(root)

    def make_text_input(self, text):
        # Dark input with white text is much more reliable on Android.
        # Some Android/Kivy builds do not draw TextInput text clearly
        # until the field receives focus, so we also show current paths
        # in normal Labels above the fields.
        return TextInput(
            text=str(text),
            font_size=settings_text_font(),
            multiline=False,
            size_hint=(1, None),
            height=max(54, int(settings_button_height() * 1.05)),
            background_normal="",
            background_active="",
            background_color=(0.10, 0.15, 0.25, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(1, 1, 1, 1),
            hint_text_color=(0.75, 0.85, 1, 1),
            padding=(spacing_size(), spacing_size(), spacing_size(), spacing_size()),
            use_bubble=True,
            use_handles=True,
        )

    def build_ai_setup_view(
        self,
        instance=None,
    ):
        self.clear_screen()

        root = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size(),
        )
        self.add_bg(root)

        self.add_system_header(
            root=root,
            title="Security Key Setup",
            back_callback=self.build_settings_view,
        )

        openai_configured = APIKeyManager.has_key()
        audd_configured = AudDKeyManager.has_key()
        spotify_configured = (
            SpotifyClientManager.has_client_id()
        )

        self.security_key_status = Label(
            text=(
                "OpenAI: "
                + ("CONFIGURED" if openai_configured else "NOT CONFIGURED")
                + "\nAudD: "
                + ("CONFIGURED" if audd_configured else "NOT CONFIGURED")
                + "\nSpotify: "
                + ("CONFIGURED" if spotify_configured else "NOT CONFIGURED")
            ),
            font_size=settings_text_font(),
            color=(0.78, 0.88, 1, 1),
            size_hint=(1, None),
            height=max(
                96,
                int(settings_row_height() * 1.55),
            ),
            halign="center",
            valign="middle",
        )
        self.security_key_status.bind(
            size=lambda inst, val: setattr(
                inst,
                "text_size",
                val,
            )
        )
        root.add_widget(self.security_key_status)

        description = Label(
            text=(
                "Paste one API key below, then choose which service "
                "should save it. Keys are stored only in M12 private "
                "application storage."
            ),
            font_size=settings_status_font(),
            color=(0.78, 0.88, 1, 1),
            size_hint=(1, 0.15),
            halign="center",
            valign="middle",
        )
        description.bind(
            size=lambda inst, val: setattr(
                inst,
                "text_size",
                val,
            )
        )
        root.add_widget(description)

        self.security_key_input = self.make_text_input(
            ""
        )
        self.security_key_input.hint_text = "Paste OpenAI/AudD key or Spotify Client ID"
        self.security_key_input.password = False
        root.add_widget(self.security_key_input)

        save_openai_btn = self.make_button(
            "SAVE OpenAI Key",
            GREEN,
        )
        save_openai_btn.bind(
            on_press=self.save_ai_api_key
        )
        root.add_widget(save_openai_btn)

        save_audd_btn = self.make_button(
            "SAVE AudD Key",
            GREEN,
        )
        save_audd_btn.bind(
            on_press=self.save_audd_api_key
        )
        root.add_widget(save_audd_btn)

        save_spotify_btn = self.make_button(
            "SAVE Spotify Client ID",
            GREEN,
        )
        save_spotify_btn.bind(
            on_press=self.save_spotify_client_id
        )
        root.add_widget(save_spotify_btn)

        root.add_widget(
            BoxLayout(
                size_hint=(1, 1)
            )
        )

        self.add_widget(root)

    def _security_key_text(self):
        return str(
            self.security_key_input.text
        ).strip()

    def _refresh_security_key_status(self, message=None):
        openai_state = (
            "CONFIGURED"
            if APIKeyManager.has_key()
            else "NOT CONFIGURED"
        )
        audd_state = (
            "CONFIGURED"
            if AudDKeyManager.has_key()
            else "NOT CONFIGURED"
        )
        spotify_state = (
            "CONFIGURED"
            if SpotifyClientManager.has_client_id()
            else "NOT CONFIGURED"
        )

        status = (
            f"OpenAI: {openai_state}\n"
            f"AudD: {audd_state}\n"
            f"Spotify: {spotify_state}"
        )

        if message:
            status += f"\n{message}"

        self.security_key_status.text = status

    def save_ai_api_key(
        self,
        instance=None,
    ):
        key = self._security_key_text()

        if not key:
            self.security_key_status.text = (
                "Paste API key first."
            )
            self.security_key_status.color = (
                1.00,
                0.60,
                0.45,
                1,
            )
            return

        try:
            APIKeyManager.save_api_key(key)
            self.security_key_input.text = ""
            self.security_key_status.color = (
                0.60,
                1.00,
                0.70,
                1,
            )
            self._refresh_security_key_status(
                "OpenAI key saved."
            )
            log.info(
                "Settings: OpenAI API key saved "
                "to private application storage"
            )

        except Exception as error:
            self.security_key_status.text = (
                "Could not save OpenAI API key:\n"
                f"{type(error).__name__}: {error}"
            )
            self.security_key_status.color = (
                1.00,
                0.45,
                0.45,
                1,
            )
            log.error(
                "Settings: OpenAI API key save failed: "
                f"{type(error).__name__}: {error}"
            )

    def save_audd_api_key(
        self,
        instance=None,
    ):
        key = self._security_key_text()

        if not key:
            self.security_key_status.text = (
                "Paste API key first."
            )
            self.security_key_status.color = (
                1.00,
                0.60,
                0.45,
                1,
            )
            return

        try:
            AudDKeyManager.save_token(key)
            self.security_key_input.text = ""
            self.security_key_status.color = (
                0.60,
                1.00,
                0.70,
                1,
            )
            self._refresh_security_key_status(
                "AudD key saved."
            )
            log.info(
                "Settings: AudD API key saved "
                "to private application storage"
            )

        except Exception as error:
            self.security_key_status.text = (
                "Could not save AudD API key:\n"
                f"{type(error).__name__}: {error}"
            )
            self.security_key_status.color = (
                1.00,
                0.45,
                0.45,
                1,
            )
            log.error(
                "Settings: AudD API key save failed: "
                f"{type(error).__name__}: {error}"
            )

    def save_spotify_client_id(
        self,
        instance=None,
    ):
        client_id = self._security_key_text()

        if not client_id:
            self.security_key_status.text = (
                "Paste Spotify Client ID first."
            )
            self.security_key_status.color = (
                1.00,
                0.60,
                0.45,
                1,
            )
            return

        try:
            SpotifyClientManager.save_client_id(
                client_id
            )
            self.security_key_input.text = ""
            self.security_key_status.color = (
                0.60,
                1.00,
                0.70,
                1,
            )
            self._refresh_security_key_status(
                "Spotify Client ID saved."
            )
            log.info(
                "Settings: Spotify Client ID saved "
                "to private application storage"
            )

        except Exception as error:
            self.security_key_status.text = (
                "Could not save Spotify Client ID:\n"
                f"{type(error).__name__}: {error}"
            )
            self.security_key_status.color = (
                1.00,
                0.45,
                0.45,
                1,
            )
            log.error(
                "Settings: Spotify Client ID save failed: "
                f"{type(error).__name__}: {error}"
            )

    def make_path_row(self, text):
        row = Button(
            text=str(text),
            font_size=settings_status_font(),
            color=WHITE,
            size_hint=(1, None),
            height=max(48, int(settings_button_height() * 0.72)),
            background_normal="",
            background_color=(0.06, 0.11, 0.20, 1),
            halign="left",
            valign="middle"
        )
        row.bind(
            size=lambda inst, val: setattr(
                inst,
                "text_size",
                (val[0] - spacing_size(), val[1])
            )
        )
        return row

    def build_storage_view(self, instance=None):
        self.clear_screen()

        roots = load_storage_roots()
        internal_root_text = roots.get("internal_root", "/storage/emulated/0")
        external_root_text = roots.get("external_root", "/storage/0907-1477")

        root = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size()
        )
        self.add_bg(root)

        self.add_system_header(
            root=root,
            title="Storage Settings",
            back_callback=self.build_settings_view,
        )

        root.add_widget(Label(
            text="Internal Storage Root",
            font_size=settings_text_font(),
            bold=True,
            color=WHITE,
            size_hint=(1, 0.05)
        ))

        self.internal_path_view = self.make_path_row(internal_root_text)
        root.add_widget(self.internal_path_view)

        change_internal_btn = self.make_button("Change Internal Root", BLUE)
        change_internal_btn.bind(on_press=self.change_internal_root)
        root.add_widget(change_internal_btn)

        root.add_widget(Label(
            text="External SD Root",
            font_size=settings_text_font(),
            bold=True,
            color=WHITE,
            size_hint=(1, 0.05)
        ))

        self.external_path_view = self.make_path_row(external_root_text)
        root.add_widget(self.external_path_view)

        change_external_btn = self.make_button("Change External Root", BLUE)
        change_external_btn.bind(on_press=self.change_external_root)
        root.add_widget(change_external_btn)

        self.storage_status = Label(
            text="Music screen uses these roots for Internal / External storage.",
            font_size=settings_status_font(),
            color=WHITE,
            size_hint=(1, 0.12),
            halign="left",
            valign="middle"
        )
        self.storage_status.bind(
            size=lambda inst, val: setattr(inst, "text_size", (val[0], val[1]))
        )
        root.add_widget(self.storage_status)

        reset_btn = self.make_button("Reset Storage Defaults", ORANGE)
        reset_btn.bind(on_press=self.reset_storage_roots_clicked)
        root.add_widget(reset_btn)

        detect_btn = self.make_button("View Detected Storage Paths", BLUE)
        detect_btn.bind(on_press=self.build_storage_paths_view)
        root.add_widget(detect_btn)

        self.add_widget(root)

    def change_internal_root(self, instance):
        roots = load_storage_roots()
        current = roots.get("internal_root", "/storage/emulated/0")

        open_text_editor(
            title="Internal Storage Root",
            text=current,
            on_save=self.save_internal_root,
            multiline=False
        )

    def change_external_root(self, instance):
        roots = load_storage_roots()
        current = roots.get("external_root", "/storage/0907-1477")

        open_text_editor(
            title="External SD Root",
            text=current,
            on_save=self.save_external_root,
            multiline=False
        )

    def save_internal_root(self, text):
        try:
            roots = load_storage_roots()

            internal_root = text.strip() or "/storage/emulated/0"
            external_root = roots.get("external_root", "/storage/0907-1477")

            saved = save_storage_roots(internal_root, external_root)

            log.info("Settings: internal root saved " + str(saved))
            self.build_storage_view()

        except Exception as e:
            log.error(f"Settings: internal root save failed: {e}")

    def save_external_root(self, text):
        try:
            roots = load_storage_roots()

            internal_root = roots.get("internal_root", "/storage/emulated/0")
            external_root = text.strip() or "/storage/0907-1477"

            saved = save_storage_roots(internal_root, external_root)

            log.info("Settings: external root saved " + str(saved))
            self.build_storage_view()

        except Exception as e:
            log.error(f"Settings: external root save failed: {e}")

    def save_storage_roots_clicked(self, instance):
        # Kept for compatibility with older builds.
        roots = load_storage_roots()
        saved = save_storage_roots(
            roots.get("internal_root", "/storage/emulated/0"),
            roots.get("external_root", "/storage/0907-1477")
        )
        log.info("Settings: storage roots saved " + str(saved))
        self.build_storage_view()

    def save_storage_roots_clicked(self, instance):
        try:
            roots = save_storage_roots(
                self.internal_root_input.text,
                self.external_root_input.text
            )

            self.internal_path_view.text = roots.get("internal_root", "")
            self.external_path_view.text = roots.get("external_root", "")

            self.storage_status.text = (
                "Saved roots:\n"
                + "Internal: "
                + roots.get("internal_root", "")
                + "\nExternal: "
                + roots.get("external_root", "")
            )
            log.info("Settings: storage roots saved " + str(roots))

        except Exception as e:
            self.storage_status.text = f"Save failed: {e}"
            log.error(f"Settings: storage roots save failed: {e}")

    def reset_storage_roots_clicked(self, instance):
        try:
            roots = save_storage_roots(
                "/storage/emulated/0",
                "/storage/0907-1477"
            )

            log.info("Settings: storage roots reset " + str(roots))
            self.build_storage_view()

        except Exception as e:
            log.error(f"Settings: storage roots reset failed: {e}")

    def detect_storage_paths(self):
        paths = []

        paths.append(f"Platform: {platform}")
        paths.append("")

        if platform != "android":
            home = Path.home()

            desktop_candidates = [
                home,
                home / "Music",
                home / "Movies",
                home / "Videos",
                home / "Downloads",
                BASE_DIR,
                BASE_DIR / "media",
                BASE_DIR / "music",
                BASE_DIR / "videos",
            ]

            paths.append("Android storage detection works only on Android device.")
            paths.append("On Mac/Desktop this screen shows local folders only.")
            paths.append("")

            seen = set()
            for p in desktop_candidates:
                raw = str(p)
                if raw in seen:
                    continue
                seen.add(raw)

                try:
                    exists = p.exists()
                    is_dir = p.is_dir()
                except Exception:
                    exists = False
                    is_dir = False

                status = "OK" if exists and is_dir else "missing"
                label = f"{raw}  [{status}]"

                if exists and is_dir:
                    media_hits = []
                    for name in [
                        "Music", "Audio", "Movies", "Video",
                        "Videos", "Download", "Downloads", "DCIM"
                    ]:
                        try:
                            child = p / name
                            if child.exists() and child.is_dir():
                                media_hits.append(name)
                        except Exception:
                            pass

                    if media_hits:
                        label += "  media: " + ", ".join(media_hits)

                paths.append(label)

            return paths

        paths.append("Android storage paths:")
        paths.append("")

        candidates = [
            "/storage/emulated/0",
            "/sdcard",
            "/mnt/sdcard",
            "/storage/self/primary",
            "/storage/M12SD",
        ]

        try:
            storage_dir = Path("/storage")
            if storage_dir.exists() and storage_dir.is_dir():
                for item in storage_dir.iterdir():
                    try:
                        candidates.append(str(item))
                    except Exception:
                        pass
        except Exception as e:
            paths.append(f"/storage scan error: {e}")

        try:
            mnt_dir = Path("/mnt/media_rw")
            if mnt_dir.exists() and mnt_dir.is_dir():
                for item in mnt_dir.iterdir():
                    try:
                        candidates.append(str(item))
                    except Exception:
                        pass
        except Exception as e:
            paths.append(f"/mnt/media_rw scan error: {e}")

        seen = set()

        for raw in candidates:
            if not raw or raw in seen:
                continue

            seen.add(raw)
            p = Path(raw)

            try:
                exists = p.exists()
                is_dir = p.is_dir()
            except Exception:
                exists = False
                is_dir = False

            status = "OK" if exists and is_dir else "missing"
            label = f"{raw}  [{status}]"

            if exists and is_dir:
                media_hits = []
                for name in [
                    "Music", "Audio", "Movies", "Video",
                    "Download", "Downloads", "DCIM"
                ]:
                    try:
                        child = p / name
                        if child.exists() and child.is_dir():
                            media_hits.append(name)
                    except Exception:
                        pass

                if media_hits:
                    label += "  media: " + ", ".join(media_hits)

            paths.append(label)

        return paths

    def build_storage_paths_view(self, instance=None):
        self.clear_screen()

        root = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size()
        )
        self.add_bg(root)

        self.add_system_header(
            root=root,
            title="Detected Storage Paths",
            back_callback=self.build_storage_view,
        )

        root.add_widget(Label(
            text="View only. Use this list to find the real Internal or SD card root.",
            font_size=settings_status_font(),
            color=WHITE,
            size_hint=(1, 0.08),
            halign="center",
            valign="middle"
        ))

        buttons = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=settings_button_height()
        )

        refresh_btn = self.make_small_button("Refresh", BLUE)
        refresh_btn.bind(on_press=self.build_storage_paths_view)
        buttons.add_widget(refresh_btn)

        root.add_widget(buttons)

        scroll = ScrollView(
            size_hint=(1, 0.72),
            do_scroll_x=False,
            do_scroll_y=True
        )

        path_list = GridLayout(
            cols=1,
            spacing=spacing_size(),
            size_hint_y=None
        )
        path_list.bind(minimum_height=path_list.setter("height"))

        for line in self.detect_storage_paths():
            # Do not disable this button. Disabled buttons can show grey text on Android.
            btn = Button(
                text=line,
                font_size=settings_text_font(),
                size_hint_y=None,
                height=settings_row_height(),
                halign="left",
                valign="middle",
                background_normal="",
                background_color=DARK,
                color=WHITE
            )
            btn.bind(
                size=lambda inst, val: setattr(
                    inst,
                    "text_size",
                    (val[0] - spacing_size(), val[1])
                )
            )
            path_list.add_widget(btn)

        scroll.add_widget(path_list)
        root.add_widget(scroll)

        self.add_widget(root)

    def open_backup(self, instance):
        if self.manager and self.manager.has_screen("backup"):
            self.manager.current = "backup"
        else:
            log.error("Settings: backup screen missing")

    def open_bluetooth(self, instance):
        if self.manager and self.manager.has_screen("bluetooth"):
            self.manager.current = "bluetooth"
        else:
            log.error("Settings: bluetooth screen missing")

    def build_log_view(self, instance=None):
        self.clear_screen()

        root = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size()
        )
        self.add_bg(root)

        self.add_system_header(
            root=root,
            title="M12 OS Log",
            back_callback=self.build_settings_view,
        )

        self.log_status = Label(
            text="Tap a line, then Copy Line.",
            font_size=settings_status_font(),
            color=(0.80, 0.90, 1, 1),
            size_hint=(1, 0.09),
            halign="left",
            valign="middle"
        )
        self.log_status.bind(
            size=lambda inst, val: setattr(inst, "text_size", val)
        )
        root.add_widget(self.log_status)

        buttons1 = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=settings_button_height()
        )

        refresh_btn = self.make_small_button("Refresh", BLUE)
        refresh_btn.bind(on_press=self.refresh_log)
        buttons1.add_widget(refresh_btn)

        copy_line_btn = self.make_small_button("Copy Line", BLUE)
        copy_line_btn.bind(on_press=self.copy_selected_log_line)
        buttons1.add_widget(copy_line_btn)

        copy_all_btn = self.make_small_button("Copy All", BLUE)
        copy_all_btn.bind(on_press=self.copy_all_log)
        buttons1.add_widget(copy_all_btn)

        root.add_widget(buttons1)

        buttons2 = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=settings_button_height()
        )

        clear_btn = self.make_small_button("Clear Log", RED)
        clear_btn.bind(on_press=self.clear_log_confirm)
        buttons2.add_widget(clear_btn)

        root.add_widget(buttons2)

        self.log_scroll = ScrollView(
            size_hint=(1, 0.65),
            do_scroll_x=False,
            do_scroll_y=True
        )

        self.log_list = GridLayout(
            cols=1,
            spacing=spacing_size(),
            size_hint_y=None
        )
        self.log_list.bind(minimum_height=self.log_list.setter("height"))

        self.log_scroll.add_widget(self.log_list)
        root.add_widget(self.log_scroll)

        self.add_widget(root)

        self.clear_log_pending = False
        self.load_log_lines()

    def speaker_echo_protection_enabled(self):
        """Return the saved Speaker Echo Protection preference."""
        configured = self.config.get(
            "speaker_echo_protection",
            None,
        )

        if isinstance(configured, bool):
            return configured

        try:
            if AI_SETTINGS_FILE.exists():
                data = json.loads(
                    AI_SETTINGS_FILE.read_text(
                        encoding="utf-8"
                    )
                )

                if isinstance(data, dict):
                    value = data.get(
                        "speaker_echo_protection",
                        True,
                    )
                    return bool(value)
        except Exception as error:
            log.error(
                "Settings: could not read Speaker Echo Protection: "
                f"{type(error).__name__}: {error}"
            )

        return True

    def speaker_echo_protection_text(self):
        enabled = self.speaker_echo_protection_enabled()
        return (
            "Speaker Echo Protection: ON"
            if enabled
            else "Speaker Echo Protection: OFF"
        )

    def save_speaker_echo_protection(self, enabled):
        """Save Speaker Echo Protection as a persistent user preference."""
        value = bool(enabled)

        # ConfigManager is the single source of truth for user preferences.
        # On Android it writes to private app storage, which survives normal
        # APK updates installed with adb install -r.
        self.config.set(
            "speaker_echo_protection",
            value,
        )

    def toggle_speaker_echo_protection(self, instance=None):
        new_value = not self.speaker_echo_protection_enabled()

        try:
            self.save_speaker_echo_protection(
                new_value
            )

            if hasattr(self, "echo_protection_btn"):
                self.echo_protection_btn.text = (
                    self.speaker_echo_protection_text()
                )
                self.echo_protection_btn.background_color = (
                    GREEN if new_value else ORANGE
                )

            log.info(
                "Settings: speaker_echo_protection="
                f"{new_value}"
            )

        except Exception as error:
            log.error(
                "Settings: Speaker Echo Protection save failed: "
                f"{type(error).__name__}: {error}"
            )

    def auto_update_text(self):
        return "Auto Updates: ON" if self.config.get("auto_update", True) else "Auto Updates: OFF"

    def change_unit(self, instance, value):
        self.config.set("temperature_unit", value)
        self.config.set("last_temperature", 22 if value == "C" else 72)

        log.info(f"Settings: temperature_unit={value}")

        if self.manager and self.manager.has_screen("home"):
            home = self.manager.get_screen("home")
            if hasattr(home, "refresh_weather_card"):
                home.refresh_weather_card()

    def toggle_auto_update(self, instance):
        new_value = not self.config.get("auto_update", True)
        self.config.set("auto_update", new_value)

        self.auto_btn.text = self.auto_update_text()
        self.auto_btn.background_color = GREEN if new_value else RED

        log.info(f"Settings: auto_update={new_value}")

    def open_updater(self, instance):
        self.manager.current = "updater"

    def read_log_lines(self):
        if not LOG_FILE.exists():
            return [f"No log found: {LOG_FILE}"]

        try:
            text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return [f"Could not read log: {e}"]

        lines = text.splitlines()

        if len(lines) > 500:
            lines = lines[-500:]

        return lines

    def load_log_lines(self):
        self.selected_log_line = ""
        self.log_lines = self.read_log_lines()
        self.log_list.clear_widgets()

        for idx, line in enumerate(self.log_lines, start=1):
            self.add_log_line(idx, line)

        self.log_status.text = f"Lines: {len(self.log_lines)} | Tap a line, then Copy Line."
        self.log_scroll.scroll_y = 0

    def add_log_line(self, idx, line):
        display = line
        if len(display) > 320:
            display = display[:317] + "..."

        btn = Button(
            text=f"{idx}: {display}",
            font_size=settings_text_font(),
            size_hint_y=None,
            height=settings_row_height(),
            halign="left",
            valign="middle",
            background_normal="",
            background_color=DARK,
            color=WHITE
        )
        btn.bind(
            size=lambda inst, val: setattr(
                inst,
                "text_size",
                (val[0] - spacing_size(), val[1])
            )
        )
        btn.bind(
            on_press=lambda instance, text=line: self.select_log_line(text)
        )
        self.log_list.add_widget(btn)

    def select_log_line(self, line):
        self.selected_log_line = line
        self.clear_log_pending = False

        short = line
        if len(short) > 120:
            short = short[:117] + "..."

        self.log_status.text = f"Selected: {short}"

    def refresh_log(self, instance):
        self.clear_log_pending = False
        self.load_log_lines()

    def copy_selected_log_line(self, instance):
        if not self.selected_log_line:
            self.log_status.text = "Select a line first."
            return

        self.safe_copy_text(self.selected_log_line, "Selected line copied.")

    def copy_all_log(self, instance):
        if not self.log_lines:
            self.log_status.text = "No log lines."
            return

        self.safe_copy_text("\n".join(self.log_lines), "All visible log lines copied.")

    def safe_copy_text(self, text, success_message):
        copied = False

        if platform == "android":
            try:
                Clipboard.copy(str(text))
                copied = True
            except Exception as e:
                log.error(f"Android clipboard failed: {e}")

        elif platform == "macosx":
            try:
                subprocess.run(
                    ["pbcopy"],
                    input=text.encode("utf-8"),
                    check=True
                )
                copied = True
            except Exception as e:
                log.error(f"pbcopy failed: {e}")

        elif platform == "win":
            try:
                subprocess.run(
                    ["clip"],
                    input=text.encode("utf-16le"),
                    check=True
                )
                copied = True
            except Exception as e:
                log.error(f"clip failed: {e}")

        if copied:
            self.log_status.text = success_message
            log.info("Settings: log text copied")
            return

        try:
            COPY_FILE.parent.mkdir(parents=True, exist_ok=True)
            COPY_FILE.write_text(text, encoding="utf-8")
            self.log_status.text = f"Clipboard unavailable. Saved to: {COPY_FILE}"
            log.info(f"Settings: copied text saved to {COPY_FILE}")
        except Exception as e:
            self.log_status.text = f"Copy failed: {e}"
            log.error(f"Settings copy failed: {e}")

    def clear_log_confirm(self, instance):
        if not self.clear_log_pending:
            self.clear_log_pending = True
            self.log_status.text = "Press Clear Log again to erase log file."
            return

        self.clear_log_now()

    def clear_log_now(self):
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            LOG_FILE.write_text("", encoding="utf-8")
            self.clear_log_pending = False
            log.info("Settings: log cleared")
            self.load_log_lines()
            self.log_status.text = "Log cleared."
        except Exception as e:
            self.log_status.text = f"Clear log failed: {e}"
            log.error(f"Settings clear log failed: {e}")

    def go_back(self, instance=None):
        if self.manager and self.manager.has_screen("home"):
            home = self.manager.get_screen("home")
            if hasattr(home, "refresh_weather_card"):
                home.refresh_weather_card()

        self.manager.current = "home"