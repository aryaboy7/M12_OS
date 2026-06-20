# M12 OS Video Player Screen - Android VideoView double-tap close
from pathlib import Path
import time

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.utils import platform

from utils.logger import log
from utils.ui_scale import (
    title_font,
    text_font,
    status_font,
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


class AndroidDoubleTapListener(PythonJavaClass):
    __javainterfaces__ = ["android/view/View$OnTouchListener"]
    __javacontext__ = "app"

    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.last_tap_time = 0

    @java_method("(Landroid/view/View;Landroid/view/MotionEvent;)Z")
    def onTouch(self, view, event):
        try:
            MotionEvent = autoclass("android.view.MotionEvent")

            if event.getAction() == MotionEvent.ACTION_UP:
                now = int(time.time() * 1000)

                if now - self.last_tap_time < 450:
                    self.last_tap_time = 0
                    self.callback()
                    return True

                self.last_tap_time = now

        except Exception as e:
            log.error(f"VideoPlayer: double tap failed {e}")

        # Return False so normal VideoView controls still work.
        return False


class VideoPlayerScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.video_path = None
        self.return_screen = "music"
        self.video_overlay = None
        self.video_view = None
        self.double_tap_listener = None
        self.closing = False

        root = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size(),
        )

        self.title_label = Label(
            text="Video Player",
            font_size=title_font(),
            bold=True,
            size_hint=(1, 0.10),
        )
        root.add_widget(self.title_label)

        self.info_label = Label(
            text="No video selected",
            font_size=text_font(),
            size_hint=(1, 0.60),
            halign="center",
            valign="middle",
        )
        self.info_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        root.add_widget(self.info_label)

        self.status_label = Label(
            text="",
            font_size=status_font(),
            size_hint=(1, 0.10),
            halign="center",
            valign="middle",
        )
        self.status_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        root.add_widget(self.status_label)

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
        self.closing = False

        if not self.video_path:
            self.status_label.text = "No video selected."
            return

        self.info_label.text = Path(self.video_path).name

        if platform == "android":
            self.status_label.text = "Opening video. Double tap video to return."
            self.start_android_video()
        else:
            self.status_label.text = "Video playback for Android only in this version."

    def on_leave(self):
        # Do not aggressively remove native view here; go_back handles it.
        pass

    def on_keyboard(self, window, key, scancode, codepoint, modifiers):
        if self.manager and self.manager.current == self.name:
            if key in (27, 1001):
                self.go_back(None)
                return True

        return False

    def go_back(self, instance):
        if self.closing:
            return

        self.closing = True
        self.status_label.text = "Closing video..."

        if platform == "android":
            self.close_android_video_safe()
        else:
            Clock.schedule_once(self.return_to_music, 0.1)

    def close_from_double_tap(self):
        Clock.schedule_once(lambda dt: self.go_back(None), 0)

    def return_to_music(self, dt):
        self.closing = False

        if self.manager:
            if self.manager.has_screen(self.return_screen):
                self.manager.current = self.return_screen
            else:
                self.manager.current = "music"

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

    def start_android_video(self):
        # Same working approach as before: rotate, then add native VideoView.
        self.set_landscape()
        Clock.schedule_once(lambda dt: self.open_android_video_overlay(), 0.8)

    @run_on_ui_thread
    def open_android_video_overlay(self):
        if platform != "android" or autoclass is None:
            Clock.schedule_once(lambda dt: self.set_status("Android VideoView API not available."), 0)
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

            video_params = LayoutParams(-1, -1)
            video_params.gravity = Gravity.CENTER
            overlay.addView(video, video_params)

            self.double_tap_listener = AndroidDoubleTapListener(lambda: self.close_from_double_tap())
            overlay.setOnTouchListener(self.double_tap_listener)
            video.setOnTouchListener(self.double_tap_listener)

            activity.addContentView(overlay, LayoutParams(-1, -1))

            self.video_overlay = overlay
            self.video_view = video

            overlay.requestFocus()
            video.requestFocus()
            video.start()

            Clock.schedule_once(lambda dt: self.set_status("Video playing. Double tap video to return."), 0)
            log.info(f"VideoPlayer: Android VideoView started {self.video_path}")

        except Exception as e:
            Clock.schedule_once(lambda dt: self.set_status(f"VideoView failed:\n{e}"), 0)
            log.error(f"VideoPlayer: Android VideoView failed {e}")

    @run_on_ui_thread
    def hide_android_video_overlay(self):
        try:
            View = autoclass("android.view.View")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")

            activity = PythonActivity.mActivity
            local_video = self.video_view
            local_overlay = self.video_overlay

            if local_video:
                # Hide the SurfaceView/VideoView first. Android can leave SurfaceView
                # painted on top unless the view itself is hidden before removal.
                try:
                    local_video.setVisibility(View.GONE)
                except Exception:
                    pass

                try:
                    local_video.pause()
                except Exception:
                    pass

                try:
                    local_video.stopPlayback()
                except Exception:
                    pass

                # VideoView has suspend() on Android and it helps release the surface.
                try:
                    local_video.suspend()
                except Exception:
                    pass

                try:
                    local_video.destroyDrawingCache()
                except Exception:
                    pass

            if local_overlay:
                try:
                    local_overlay.setVisibility(View.GONE)
                except Exception:
                    pass

                try:
                    local_overlay.removeAllViews()
                except Exception:
                    pass

                try:
                    parent = local_overlay.getParent()
                    if parent:
                        parent.removeView(local_overlay)

                        try:
                            parent.requestLayout()
                        except Exception:
                            pass

                        try:
                            parent.invalidate()
                        except Exception:
                            pass
                except Exception as e:
                    log.error(f"VideoPlayer: remove overlay failed {e}")

            # Force Android decor redraw. This is what happens naturally when
            # user goes to desktop and returns; we request it immediately.
            try:
                decor = activity.getWindow().getDecorView()
                decor.requestLayout()
                decor.invalidate()
            except Exception:
                pass

        except Exception as e:
            log.error(f"VideoPlayer: hide overlay failed {e}")

        self.video_view = None
        self.video_overlay = None


    def close_android_video_safe(self):
        # Staged close:
        # 1. Hide/remove native Android VideoView.
        # 2. Wait for Android to finish cleanup.
        # 3. Restore orientation.
        # 4. Return to Music only after cleanup.
        self.hide_android_video_overlay()
        Clock.schedule_once(lambda dt: self.restore_orientation(), 0.75)
        Clock.schedule_once(self.return_to_music, 2.00)

    def set_status(self, text):
        self.status_label.text = text
