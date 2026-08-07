from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from config.version import VERSION
from utils.ui_scale import font, height


SYSTEM_BG = (0.06, 0.10, 0.18, 1)
BACK_BG = (0.10, 0.15, 0.25, 1)
AI_BG = (0.20, 0.35, 0.85, 0.96)
AI_ACTIVE_BG = (0.38, 0.24, 0.72, 1)


class M12SystemHeader(BoxLayout):
    """
    Permanent two-row M12OS header.

    Row 1:
        M12 OS version | system status | time | AI

    Row 2:
        Back | centered screen title | balanced empty area
    """

    def __init__(
        self,
        title,
        back_callback,
        status_provider=None,
        ai_active=False,
        **kwargs,
    ):
        super().__init__(
            orientation="vertical",
            spacing=height(4),
            size_hint=(1, None),
            height=height(94),
            **kwargs,
        )

        self.status_provider = status_provider
        self.ai_active = bool(ai_active)

        self._build_system_row()
        self._build_screen_row(
            title=title,
            back_callback=back_callback,
        )

        self._clock_event = Clock.schedule_interval(
            self.refresh,
            1,
        )
        self.refresh(0)

    def _build_system_row(self):
        row = BoxLayout(
            orientation="horizontal",
            spacing=height(6),
            padding=(height(8), height(2)),
            size_hint=(1, 0.48),
        )

        self.version_label = Label(
            text=f"M12 OS {VERSION}",
            font_size=font(16),
            color=(0.75, 0.85, 1, 1),
            halign="left",
            valign="middle",
            size_hint=(0.22, 1),
        )

        self.status_label = Label(
            text="WiFi",
            font_size=font(16),
            color=(0.75, 1, 0.80, 1),
            halign="center",
            valign="middle",
            size_hint=(0.48, 1),
        )

        self.time_label = Label(
            text="--:--:--",
            font_size=font(16),
            color=(1, 1, 1, 1),
            halign="right",
            valign="middle",
            size_hint=(0.18, 1),
        )

        self.ai_button = Button(
            text="AI",
            font_size=font(19),
            bold=True,
            size_hint=(0.12, 1),
            background_normal="",
            background_down="",
            background_color=(
                AI_ACTIVE_BG
                if self.ai_active
                else AI_BG
            ),
            color=(1, 1, 1, 1),
            disabled=self.ai_active,
        )
        self.ai_button.bind(
            on_release=self.open_ai
        )

        for widget in (
            self.version_label,
            self.status_label,
            self.time_label,
        ):
            widget.bind(
                size=lambda instance, value: setattr(
                    instance,
                    "text_size",
                    value,
                )
            )

        row.add_widget(self.version_label)
        row.add_widget(self.status_label)
        row.add_widget(self.time_label)
        row.add_widget(self.ai_button)

        self.add_widget(row)

    def _build_screen_row(
        self,
        title,
        back_callback,
    ):
        row = BoxLayout(
            orientation="horizontal",
            spacing=height(8),
            size_hint=(1, 0.52),
        )

        self.back_button = Button(
            text="< Back",
            font_size=font(22),
            background_normal="",
            background_color=BACK_BG,
            size_hint=(0.22, 1),
        )
        self.back_button.bind(
            on_release=back_callback
        )

        self.title_label = Label(
            text=str(title),
            font_size=font(30),
            bold=True,
            halign="center",
            valign="middle",
            size_hint=(0.56, 1),
        )
        self.title_label.bind(
            size=lambda instance, value: setattr(
                instance,
                "text_size",
                value,
            )
        )

        right_spacer = Label(
            text="",
            size_hint=(0.22, 1),
        )

        row.add_widget(self.back_button)
        row.add_widget(self.title_label)
        row.add_widget(right_spacer)

        self.add_widget(row)

    def open_ai(self, instance=None):
        app = App.get_running_app()

        if app is not None:
            callback = getattr(
                app,
                "open_global_ai",
                None,
            )

            if callable(callback):
                callback()

    def refresh(self, dt=0):
        self.time_label.text = (
            datetime.now().strftime("%H:%M:%S")
        )

        if not callable(self.status_provider):
            return

        try:
            text = str(
                self.status_provider() or "WiFi"
            ).strip()

            self.status_label.text = text or "WiFi"

        except Exception as error:
            self.status_label.text = "WiFi"
            print(
                "System header status error: "
                f"{type(error).__name__}: {error}"
            )

    def set_ai_active(self, active):
        self.ai_active = bool(active)
        self.ai_button.disabled = self.ai_active
        self.ai_button.background_color = (
            AI_ACTIVE_BG
            if self.ai_active
            else AI_BG
        )

    def on_parent(self, instance, parent):
        if parent is None and self._clock_event is not None:
            self._clock_event.cancel()
            self._clock_event = None


def create_system_header(
    title,
    back_callback,
    status_provider=None,
    ai_active=False,
):
    return M12SystemHeader(
        title=title,
        back_callback=back_callback,
        status_provider=status_provider,
        ai_active=ai_active,
    )
