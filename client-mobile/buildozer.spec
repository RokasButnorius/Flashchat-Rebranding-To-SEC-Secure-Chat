[app]
title = SEC
package.name = securechat
package.domain = store.sec

source.dir = .
source.include_exts = py,png,jpg,kv,atlas
icon.filename = %(source.dir)s/secicon.png

version = 0.3

# Text messaging only for this build. Add aiortc/webrtc deps when
# calling is actually ported to the mobile client.
requirements = python3,kivy,pynacl,websockets,cffi,pycparser,certifi

orientation = portrait
fullscreen = 0

# Only what the websocket relay connection needs.
android.permissions = INTERNET, ACCESS_NETWORK_STATE

# --- when you ship calling, uncomment these ---
# android.permissions = INTERNET, ACCESS_NETWORK_STATE, RECORD_AUDIO, MODIFY_AUDIO_SETTINGS, CAMERA
# android.gradle_dependencies = io.github.webrtc-sdk:android:144.7559.09
# android.enable_androidx = True
# ---------------------------------------------

android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1