[app]

android.no-byte-compile-python = True
p4a.local_recipes = recipes

title = M12 OS

package.name = m12os
package.domain = com.m12os

source.dir = .
source.include_exts = py,kv,json,png,jpg,jpeg,atlas,wav,mp3,m4a,txt,aar,xml

# Keep local development/build folders out of the APK.
source.exclude_dirs = .git,.github,.venv,.buildozer,bin,backups,updates,__pycache__,current_phone_snapshot,phone_data_before_restore,recovered_m12_data,restore_payload

version = 0.5.3

# M12 Android dependencies.
# sounddevice and numpy are intentionally NOT included:
# Android voice uses native Android/SDL2 audio.
requirements = python3,kivy,pyjnius,openai==3.0.0,httpx2==2.10.0,jiter,websockets

orientation = portrait
fullscreen = 0

# Core permissions needed by M12 voice/network.
# Timer/Clock/Calendar permissions support notifications,
# vibration, wake locks and exact alarms.
android.permissions = INTERNET,RECORD_AUDIO,READ_MEDIA_AUDIO,READ_MEDIA_VIDEO,READ_MEDIA_IMAGES,READ_CONTACTS,POST_NOTIFICATIONS,SCHEDULE_EXACT_ALARM,VIBRATE,WAKE_LOCK

android.api = 35
android.minapi = 24
android.archs = arm64-v8a

# SDL2 is the normal Kivy Android bootstrap and is also used by
# the Android Realtime PCM audio backend.
p4a.bootstrap = sdl2
p4a.branch = develop
p4a.hook = tools/p4a_hooks.py

# Compile M12 native Android Java sources.
android.add_src = android_src

# Spotify Android App Remote SDK.
android.add_aars = android_libs/spotify-app-remote-release-0.8.0.aar

# Spotify App Remote dependency.
android.gradle_dependencies = com.google.code.gson:gson:2.10.1

# Allow Gradle to resolve local AAR files copied into libs/.
android.add_gradle_repositories = flatDir { dirs 'libs' }

[buildozer]

log_level = 2
warn_on_root = 1