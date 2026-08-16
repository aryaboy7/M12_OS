[app]
android.no-byte-compile-python = True
p4a.local_recipes = recipes

title = M12 OS

package.name = m12os
package.domain = com.m12os

source.dir = .
source.include_exts = py,kv,json,png,jpg,jpeg,atlas,wav,mp3,m4a,txt

# Keep local development/build folders out of the APK.
source.exclude_dirs = .git,.github,.venv,.buildozer,bin,backups,updates,__pycache__,current_phone_snapshot,phone_data_before_restore,recovered_m12_data,restore_payload

version = 0.5.3

# M12 Android dependencies.
# sounddevice and numpy are intentionally NOT included:
# Android voice uses native Android/SDL2 audio.
requirements = python3,kivy,pyjnius,openai,jiter,websockets

orientation = portrait
fullscreen = 0

# Core permissions needed by M12 voice/network.
# Media permissions support the Music/Video/File screens on recent Android.
android.permissions = INTERNET,RECORD_AUDIO,READ_MEDIA_AUDIO,READ_MEDIA_VIDEO,READ_MEDIA_IMAGES

android.api = 35
android.minapi = 24
android.archs = arm64-v8a

# SDL2 is the normal Kivy Android bootstrap and is also used by
# the Android Realtime PCM audio backend.
p4a.bootstrap = sdl2


[buildozer]

log_level = 2
warn_on_root = 1