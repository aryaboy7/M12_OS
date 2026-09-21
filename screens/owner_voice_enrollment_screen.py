import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import Screen

from services.owner_voice_enrollment import (
    OwnerVoiceEnrollmentService,
)


class OwnerVoiceEnrollmentScreen(Screen):
    """
    First-run owner voice enrollment screen.

    M12 sends the user here automatically whenever owner.npy is missing.
    Recording runs on a worker thread so the Kivy UI remains responsive.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.service = OwnerVoiceEnrollmentService()
        self._running = False

        root = BoxLayout(
            orientation="vertical",
            padding=30,
            spacing=18,
        )

        title = Label(
            text="[b]Owner Voice Enrollment[/b]",
            markup=True,
            font_size="30sp",
            size_hint_y=None,
            height=60,
        )

        instructions = Label(
            text=(
                "M12 needs to learn your voice before Voice Mode can start.\n\n"
                "You will record 5 short voice samples.\n"
                "Each sample is 5 seconds.\n\n"
                "Speak in your normal voice. You may speak English, Russian, "
                "or both.\n"
                "Try to sit at your normal distance from the microphone.\n\n"
                "Press Start Enrollment when you are ready."
            ),
            halign="center",
            valign="middle",
            font_size="20sp",
        )
        instructions.bind(
            size=lambda instance, value: setattr(
                instance,
                "text_size",
                value,
            )
        )

        self.status_label = Label(
            text="Ready to enroll.",
            font_size="22sp",
            size_hint_y=None,
            height=70,
        )

        self.progress = ProgressBar(
            max=5,
            value=0,
            size_hint_y=None,
            height=24,
        )

        self.start_button = Button(
            text="Start Enrollment",
            font_size="22sp",
            size_hint_y=None,
            height=64,
        )
        self.start_button.bind(
            on_release=self._start_enrollment
        )

        root.add_widget(title)
        root.add_widget(instructions)
        root.add_widget(self.status_label)
        root.add_widget(self.progress)
        root.add_widget(self.start_button)

        self.add_widget(root)

    def on_pre_enter(self, *args):
        if self.service.profile_exists():
            Clock.schedule_once(
                self._continue_to_home,
                0,
            )

    def _start_enrollment(self, *args):
        if self._running:
            return

        self._running = True
        self.progress.value = 0
        self.start_button.disabled = True
        self.start_button.text = "Enrollment in progress..."
        self.status_label.text = "Preparing microphone..."

        thread = threading.Thread(
            target=self._enrollment_worker,
            name="M12OwnerVoiceEnrollment",
            daemon=True,
        )
        thread.start()

    def _enrollment_worker(self):
        try:
            self.service.enroll(
                on_status=self._thread_status,
                on_countdown=self._thread_countdown,
                on_sample_complete=self._thread_sample_complete,
            )

            Clock.schedule_once(
                self._enrollment_success,
                0,
            )

        except Exception as error:
            message = (
                f"Enrollment failed: "
                f"{type(error).__name__}: {error}"
            )
            Clock.schedule_once(
                lambda dt, message=message: (
                    self._enrollment_failed(
                        message
                    )
                ),
                0,
            )

    def _thread_status(self, text):
        Clock.schedule_once(
            lambda dt, text=str(text): self._set_status(
                text
            ),
            0,
        )

    def _thread_countdown(
        self,
        sample_number,
        number,
    ):
        text = (
            f"Sample {sample_number} of 5 "
            f"starts in {number}..."
        )

        Clock.schedule_once(
            lambda dt, text=text: self._set_status(
                text
            ),
            0,
        )

    def _thread_sample_complete(
        self,
        sample_number,
        total,
    ):
        Clock.schedule_once(
            lambda dt, value=sample_number: (
                self._set_progress(
                    value
                )
            ),
            0,
        )

    def _set_status(self, text):
        self.status_label.text = str(text)

    def _set_progress(self, value):
        self.progress.value = value

    def _enrollment_success(self, dt=0):
        self._running = False
        self.progress.value = 5
        self.status_label.text = (
            "Enrollment complete. Starting M12..."
        )
        self.start_button.disabled = True

        Clock.schedule_once(
            self._continue_to_home,
            1.0,
        )

    def _enrollment_failed(self, message):
        self._running = False
        self.status_label.text = message
        self.start_button.disabled = False
        self.start_button.text = "Try Again"

    def _continue_to_home(self, dt=0):
        app = App.get_running_app()

        if (
            app is not None
            and app.screen_manager is not None
            and app.screen_manager.has_screen("home")
        ):
            app.screen_manager.current = "home"
