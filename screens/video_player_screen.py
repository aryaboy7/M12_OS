# M12 OS Video Player Screen
from pathlib import Path

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.utils import platform

from utils.logger import log
from utils.ui_scale import (
    title_font,
    button_font,
    text_font,
    status_font,
    button_height,
    padding_size,
    spacing_size,
)

try:
    from jnius import autoclass, PythonJavaClass, java_method
except Exception:
    autoclass = None
    PythonJavaClass = object

    def java_method(signature):
        def deco(func):
            return func
        return deco

try:
    from android.runnable import run_on_ui_thread
except Exception:
    def run_on_ui_thread(func):
        return func


class AndroidVideoBackListener(PythonJavaClass):
    __javainterfaces__ = ["android/view/View$OnKeyListener"]
    __javacontext__ = "app"

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    @java_method("(Landroid/view/View;ILandroid/view/KeyEvent;)Z")
    def onKey(self, view, key_code, event):
        try:
            # Android KEYCODE_BACK = 4, ACTION_UP = 1
            if int(key_code) == 4 and event.getAction() == 1:
                self.callback()
                return True
        except Exception as e:
            log.error(f"VideoPlayer: Android back failed {e}")

        return False


class VideoPlayerScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.video_path = None
        self.return_screen = "music"
        self.video_overlay = None
        self.video_view = None
        self.back_listener = None

        root = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size(),
        )

        self.title_label = Label(
            text="Video Player",
            font_size=title_font(),
            bold=True,
            size_hint=(1, 0.16),
        )
        root.add_widget(self.title_label)

        self.info_label = Label(
            text="No video selected",
            font_size=text_font(),
            size_hint=(1, 0.48),
            halign="center",
            valign="middle",
        )
        self.info_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        root.add_widget(self.info_label)

        self.status_label = Label(
            text="",
            font_size=status_font(),
            size_hint=(1, 0.16),
            halign="center",
            valign="middle",
        )
        self.status_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        root.add_widget(self.status_label)

        back_btn = Button(
            text="< Back to Music",
            font_size=button_font(),
            size_hint=(1, None),
            height=button_height(),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1),
        )
        back_btn.bind(on_press=self.go_back)
        root.add_widget(back_btn)

        self.add_widget(root)

        try:
            Window.bind(on_keyboard=self.on_keyboard)
        except Exception:
            pass

    def set_video(self, path, return_screen="music"):
        self.video_path = str(path)
        self.return_screen = return_screen or "music"

        name = Path(path).name if path else "No video selected"
        self.info_label.text = name
        self.status_label.text = "Ready"

    def on_enter(self):
        if not self.video_path:
            self.status_label.text = "No video selected."
            return

        self.info_label.text = Path(self.video_path).name

        if platform == "android":
            self.status_label.text = "Opening Android video..."
            self.start_android_video()
        elif platform == "macosx":
            self.status_label.text = "Mac video opens from Music screen."
        else:
            self.status_label.text = "Video playback not available on this platform yet."

    def on_leave(self):
        self.stop_android_video()

    def on_keyboard(self, window, key, scancode, codepoint, modifiers):
        if self.manager and self.manager.current == self.name:
            if key in (27, 1001):
                self.go_back(None)
                return True

        return False

    def go_back(self, instance):
        self.stop_android_video()

        if self.manager:
            self.manager.current = self.return_screen

    @run_on_ui_thread
    def set_landscape(self):
        if platform != "android" or autoclass is None:
            return

        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            ActivityInfo = autoclass("android.content.pm.ActivityInfo")
            PythonActivity.mActivity.setRequestedOrientation(
                ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
            )
        except Exception as e:
            log.error(f"VideoPlayer: set landscape failed {e}")

    @run_on_ui_thread
    def restore_orientation(self):
        if platform != "android" or autoclass is None:
            return

        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            ActivityInfo = autoclass("android.content.pm.ActivityInfo")
            PythonActivity.mActivity.setRequestedOrientation(
                ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            )
        except Exception as e:
            log.error(f"VideoPlayer: restore orientation failed {e}")

    @run_on_ui_thread
    def enter_fullscreen(self):
        if platform != "android" or autoclass is None:
            return

        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            View = autoclass("android.view.View")

            decor = PythonActivity.mActivity.getWindow().getDecorView()
            flags = (
                View.SYSTEM_UI_FLAG_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            )
            decor.setSystemUiVisibility(flags)
        except Exception as e:
            log.error(f"VideoPlayer: enter fullscreen failed {e}")

    @run_on_ui_thread
    def exit_fullscreen(self):
        if platform != "android" or autoclass is None:
            return

        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            decor = PythonActivity.mActivity.getWindow().getDecorView()
            decor.setSystemUiVisibility(0)
        except Exception as e:
            log.error(f"VideoPlayer: exit fullscreen failed {e}")

    def start_android_video(self):
        self.set_landscape()
        Clock.schedule_once(lambda dt: self._start_android_video_after_rotate(), 0.8)

    @run_on_ui_thread
    def _start_android_video_after_rotate(self):
        if platform != "android" or autoclass is None:
            Clock.schedule_once(lambda dt: self._set_status("Android VideoView API not available."), 0)
            return

        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            FrameLayout = autoclass("android.widget.FrameLayout")
            VideoView = autoclass("android.widget.VideoView")
            MediaController = autoclass("android.widget.MediaController")
            Color = autoclass("android.graphics.Color")
            Gravity = autoclass("android.view.Gravity")
            LayoutParams = autoclass("android.widget.FrameLayout$LayoutParams")

            activity = PythonActivity.mActivity

            self._remove_video_overlay_only()
            self.enter_fullscreen()

            overlay = FrameLayout(activity)
            overlay.setBackgroundColor(Color.BLACK)
            overlay.setClickable(True)
            overlay.setFocusable(True)
            overlay.setFocusableInTouchMode(True)

            video = VideoView(activity)
            controller = MediaController(activity)
            controller.setAnchorView(video)
            video.setMediaController(controller)
            video.setVideoPath(self.video_path)

            params = LayoutParams(-1, -1)
            params.gravity = Gravity.CENTER
            overlay.addView(video, params)

            self.back_listener = AndroidVideoBackListener(lambda: self._android_back_to_music())
            overlay.setOnKeyListener(self.back_listener)

            activity.addContentView(overlay, LayoutParams(-1, -1))

            self.video_overlay = overlay
            self.video_view = video

            overlay.requestFocus()
            video.requestFocus()
            video.start()

            Clock.schedule_once(lambda dt: self._set_status("Video playing. Use Android Back to return."), 0)
            log.info(f"VideoPlayer: Android VideoView started {self.video_path}")

        except Exception as e:
            Clock.schedule_once(lambda dt: self._set_status(f"VideoView failed:\n{e}"), 0)
            log.error(f"VideoPlayer: Android VideoView failed {e}")

    def _android_back_to_music(self):
        Clock.schedule_once(lambda dt: self.go_back(None), 0)

    def _set_status(self, text):
        self.status_label.text = text

    @run_on_ui_thread
    def _remove_video_overlay_only(self):
        try:
            if self.video_view:
                try:
                    self.video_view.stopPlayback()
                except Exception:
                    pass

            if self.video_overlay:
                try:
                    parent = self.video_overlay.getParent()
                    if parent:
                        parent.removeView(self.video_overlay)
                except Exception:
                    pass

        except Exception as e:
            log.error(f"VideoPlayer: remove overlay failed {e}")

        self.video_view = None
        self.video_overlay = None

    @run_on_ui_thread
    def stop_android_video(self):
        if platform != "android":
            return

        self._remove_video_overlay_only()
        self.exit_fullscreen()
        self.restore_orientation()
