"""
client-desktop/main.py

SEC -- glass UI desktop client. PySide6 + qasync.
Run: python main.py
"""

import sys
import os
import subprocess
import asyncio
import shutil
import webbrowser
import uuid as uuid_lib
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem, QScrollArea,
    QFrame, QDialog, QComboBox, QGridLayout, QMessageBox, QInputDialog,
    QCheckBox, QSizePolicy, QSpinBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
import assets
import qasync

from theme import STYLESHEET, avatar_color, ACCENT
from session import GuiSession, BUILT_IN_AVATARS, DATA_DIR
from crypto.vault import VaultError
import calling


def avatar_widget(user_id: str, avatar_id: str = "default", size: int = 36) -> QLabel:
    lbl = QLabel()
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setFixedSize(size, size)
    pm = assets.avatar_pixmap(avatar_id, size=size) if hasattr(assets, "avatar_pixmap") else None
    if pm is not None and not pm.isNull():
        lbl.setPixmap(pm)
        lbl.setStyleSheet(
            f"background-color: {avatar_color(user_id)}; border-radius: {size // 2}px;"
        )
    else:
        letter = (user_id[:1] or "?").upper()
        lbl.setText(letter)
        lbl.setStyleSheet(
            f"background-color: {avatar_color(user_id)}; border-radius: {size // 2}px; "
            f"font-size: {int(size * 0.45)}px; font-weight: 700; color: white;"
        )
    return lbl


class MessageBubble(QFrame):
    def __init__(self, sender: str, text: str, mine: bool):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(420)
        bubble.setMinimumWidth(0)
        bubble.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        bg = ACCENT if mine else "rgba(30, 50, 80, 200)"
        bubble.setStyleSheet(
            f"background-color: {bg}; color: white; border-radius: 14px; padding: 8px 12px;"
        )
        if mine:
            layout.addStretch()
            layout.addWidget(bubble)
        else:
            layout.addWidget(avatar_widget(sender, size=28))
            layout.addWidget(bubble)
            layout.addStretch()


class SystemNote(QFrame):
    def __init__(self, text: str):
        super().__init__()
        layout = QHBoxLayout(self)
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #5a7399; font-style: italic; font-size: 11px;")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)


class SettingsDialog(QDialog):
    def __init__(self, session: GuiSession, current_bio: str, current_avatar: str, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Profile Settings")
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Bio"))
        self.bio_input = QLineEdit(current_bio)
        layout.addWidget(self.bio_input)

        layout.addWidget(QLabel("Avatar"))
        grid = QGridLayout()
        self.selected_avatar = current_avatar
        self.avatar_buttons = {}
        for i, av in enumerate(BUILT_IN_AVATARS):
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setChecked(av == current_avatar)
            btn.setFixedSize(44, 44)
            ic = assets.avatar_icon(av) if hasattr(assets, "avatar_icon") else assets.icon(f"avatar_{av}")
            if ic:
                btn.setIcon(ic)
                btn.setIconSize(btn.size() * 0.7)
            else:
                btn.setText((av[:1] or "?").upper())
            btn.clicked.connect(lambda _, a=av: self._select_avatar(a))
            self.avatar_buttons[av] = btn
            grid.addWidget(btn, i // 5, i % 5)
        layout.addLayout(grid)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("AccentButton")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

    def _select_avatar(self, av):
        self.selected_avatar = av
        for a, btn in self.avatar_buttons.items():
            btn.setChecked(a == av)

    def _save(self):
        asyncio.ensure_future(self.session.update_profile(
            bio=self.bio_input.text(), avatar_id=self.selected_avatar,
        ))
        self.accept()


# ---------------------------------------------------------------------------
# Robust device enumeration helpers
# ---------------------------------------------------------------------------

def _ensure_calling_initialized():
    """Best-effort: call a module-level init hook if one exists."""
    for name in ("init", "initialize", "ensure_initialized",
                 "init_audio", "init_devices", "start"):
        fn = getattr(calling, name, None)
        if callable(fn):
            try:
                fn()
            except Exception as e:
                print(f"[calling] {name}() failed: {type(e).__name__}: {e}")
            return


def _normalize_devices(raw):
    """Normalise whatever ``calling.list_*`` returns into (name, value) pairs."""
    out = []
    if not raw:
        return out
    for d in raw:
        name = value = None
        if isinstance(d, str):
            name = value = d
        elif isinstance(d, dict):
            name = (d.get("name") or d.get("device_name")
                    or d.get("label") or d.get("id"))
            value = (d.get("name") or d.get("id")
                     or d.get("device_name") or name)
        elif isinstance(d, (tuple, list)):
            if not d:
                continue
            name = d[0]
            value = d[1] if len(d) >= 2 else d[0]
        else:
            name = getattr(d, "name", None) or getattr(d, "device_name", None)
            value = getattr(d, "id", None) or name
        if name is None:
            continue
        out.append((str(name), value))
    return out


def _safe_list(fn_name, *args, **kwargs):
    """Call a ``calling`` enumeration helper without raising into the UI."""
    fn = getattr(calling, fn_name, None)
    if not callable(fn):
        print(f"[calling] {fn_name}() missing from calling module")
        return []
    try:
        return fn(*args, **kwargs) or []
    except Exception as e:
        print(f"[calling] {fn_name}() failed: {type(e).__name__}: {e}")
        return []


def _default_device_name(*fn_names):
    """Return the first non-empty default device name from the given helpers."""
    for fn_name in fn_names:
        fn = getattr(calling, fn_name, None)
        if not callable(fn):
            continue
        try:
            result = fn()
        except Exception as e:
            print(f"[calling] {fn_name}() failed: {type(e).__name__}: {e}")
            continue
        if not result:
            continue
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return (result.get("name") or result.get("device_name")
                    or result.get("id"))
        return getattr(result, "name", None) or getattr(result, "id", None)
    return None


def _probe_hardware(kind: str) -> bool:
    """Actually try to open the device to force the OS permission prompt.

    On Windows/macOS the privacy toggle for an app only appears in the OS
    settings AFTER the app has requested access at least once.  Just visiting
    the settings page is not enough.  This function performs a minimal open
    so the OS registers the request and (on macOS) shows the Allow/Deny
    dialog automatically.

    Returns True if we managed to touch the hardware, False otherwise.
    """
    kind = kind.lower()

    # 1) Try the calling module's own probe/open helpers first
    probe_names = {
        "microphone": ("probe_microphone", "open_microphone", "test_microphone",
                       "probe_audio_input", "open_audio_input"),
        "camera":     ("probe_camera", "open_camera", "test_camera",
                       "probe_video", "open_video"),
    }.get(kind, ())
    for name in probe_names:
        fn = getattr(calling, name, None)
        if callable(fn):
            try:
                fn()
                return True
            except Exception as e:
                print(f"[probe] calling.{name}() failed: {type(e).__name__}: {e}")

    # 2) Fall back to direct library probes
    if kind == "camera":
        try:
            import cv2  # type: ignore
            cap = cv2.VideoCapture(0)
            opened = cap.isOpened()
            if opened:
                # Grab one frame so the OS prompt actually fires on macOS
                try:
                    cap.read()
                except Exception:
                    pass
            cap.release()
            return opened
        except Exception as e:
            print(f"[probe] cv2 camera probe failed: {type(e).__name__}: {e}")

    if kind == "microphone":
        # sounddevice is gentler than pyaudio and works cross-platform
        try:
            import sounddevice as sd  # type: ignore
            try:
                sd.query_devices()
            except Exception as e:
                print(f"[probe] sounddevice query failed: {type(e).__name__}: {e}")
            # Actually try to open a short stream to force the prompt
            try:
                with sd.InputStream(blocksize=512):
                    pass
                return True
            except Exception as e:
                print(f"[probe] sounddevice open failed: {type(e).__name__}: {e}")
        except Exception:
            pass
        try:
            import pyaudio  # type: ignore
            p = pyaudio.PyAudio()
            try:
                p.get_default_input_device_info()
            finally:
                p.terminate()
            return True
        except Exception as e:
            print(f"[probe] pyaudio mic probe failed: {type(e).__name__}: {e}")

    return False


def open_os_privacy_settings(kind: str) -> bool:
    """Open the OS privacy page for the given device kind.

    kind is one of: "microphone", "camera".
    Returns True if we launched something, False if we don't know how.
    """
    kind = kind.lower()
    system = sys.platform

    try:
        # ---------------- Windows ----------------
        if system.startswith("win"):
            uri = {
                "microphone": "ms-settings:privacy-microphone",
                "camera":     "ms-settings:privacy-webcam",
            }.get(kind)
            if uri:
                os.startfile(uri)  # type: ignore[attr-defined]
                return True

        # ---------------- macOS ----------------
        elif system == "darwin":
            anchor = {
                "microphone": "Privacy_Microphone",
                "camera":     "Privacy_Camera",
            }.get(kind)
            if anchor:
                subprocess.Popen([
                    "open",
                    f"x-apple.systempreferences:com.apple.preference.security?{anchor}",
                ])
                return True

        # ---------------- Linux ----------------
        else:
            if kind == "microphone":
                candidates = [
                    ["gnome-control-center", "sound"],
                    ["gnome-control-center", "privacy"],
                    ["kcmshell5", "kcm_pulseaudio"],
                    ["systemsettings5", "kcm_pulseaudio"],
                ]
            else:
                candidates = [
                    ["gnome-control-center", "privacy"],
                    ["gnome-control-center", "camera"],
                    ["kcmshell5", "kcm_kamera"],
                    ["systemsettings5", "kcm_kamera"],
                ]
            for cmd in candidates:
                try:
                    subprocess.Popen(cmd)
                    return True
                except FileNotFoundError:
                    continue
            webbrowser.open(
                "https://help.ubuntu.com/community/"
                + ("Sound" if kind == "microphone" else "Webcam")
            )
            return True

    except Exception as e:
        print(f"[settings] could not open {kind} settings: {type(e).__name__}: {e}")

    return False


class CallDialog(QDialog):
    def __init__(self, session: GuiSession, peer_id: str, incoming_offer: str | None, parent=None):
        super().__init__(parent)
        self.session = session
        self.peer_id = peer_id
        self.setWindowTitle(f"Call with {peer_id}")
        self.setMinimumSize(460, 560)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Call with {peer_id}"))

        form = QGridLayout()
        form.addWidget(QLabel("Microphone:"), 0, 0)
        self.mic_combo = QComboBox()
        form.addWidget(self.mic_combo, 0, 1)

        form.addWidget(QLabel("Speaker:"), 1, 0)
        self.speaker_combo = QComboBox()
        form.addWidget(self.speaker_combo, 1, 1)

        form.addWidget(QLabel("Camera:"), 2, 0)
        self.camera_combo = QComboBox()
        form.addWidget(self.camera_combo, 2, 1)

        layout.addLayout(form)

        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        self.refresh_btn = QPushButton("Refresh devices")
        self.refresh_btn.clicked.connect(self._populate_device_combos)
        refresh_row.addWidget(self.refresh_btn)
        layout.addLayout(refresh_row)

        self.device_hint = QLabel("")
        self.device_hint.setStyleSheet("color: #d08a8a; font-size: 11px;")
        self.device_hint.setWordWrap(True)
        layout.addWidget(self.device_hint)

        # ---- Fix-permissions buttons (always visible) -------------------
        fix_row = QHBoxLayout()
        fix_row.addStretch()

        self.fix_mic_btn = QPushButton("🔓 Fix microphone access")
        self.fix_mic_btn.setCursor(Qt.PointingHandCursor)
        self.fix_mic_btn.setFlat(True)
        self.fix_mic_btn.setStyleSheet(
            "color: #6fb6ff; text-decoration: underline; "
            "border: none; padding: 2px 4px; background: transparent;"
        )
        self.fix_mic_btn.setToolTip(
            "Forces the OS to ask for microphone permission and opens the "
            "privacy settings page.  We auto-detect when the device appears."
        )
        self.fix_mic_btn.clicked.connect(lambda: self._fix_access("microphone"))
        fix_row.addWidget(self.fix_mic_btn)

        self.fix_cam_btn = QPushButton("🔓 Fix camera access")
        self.fix_cam_btn.setCursor(Qt.PointingHandCursor)
        self.fix_cam_btn.setFlat(True)
        self.fix_cam_btn.setStyleSheet(
            "color: #6fb6ff; text-decoration: underline; "
            "border: none; padding: 2px 4px; background: transparent;"
        )
        self.fix_cam_btn.setToolTip(
            "Forces the OS to ask for camera permission and opens the "
            "privacy settings page.  We auto-detect when the device appears."
        )
        self.fix_cam_btn.clicked.connect(lambda: self._fix_access("camera"))
        fix_row.addWidget(self.fix_cam_btn)
        layout.addLayout(fix_row)

        self.auto_status = QLabel("")
        self.auto_status.setStyleSheet("color: #8aa4c8; font-size: 11px;")
        self.auto_status.setWordWrap(True)
        layout.addWidget(self.auto_status)

        self.status_label = QLabel("Ready to call" if not incoming_offer else "Incoming call...")
        self.status_label.setStyleSheet("color: #8aa4c8;")
        layout.addWidget(self.status_label)

        self.video_label = QLabel()
        self.video_label.setFixedSize(400, 260)
        self.video_label.setStyleSheet("background-color: #0b1220; border-radius: 8px;")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setText("No video")
        self.video_label.setVisible(False)
        layout.addWidget(self.video_label)

        btn_row = QHBoxLayout()
        if incoming_offer:
            accept_btn = QPushButton("Accept")
            accept_btn.setObjectName("AccentButton")
            accept_btn.clicked.connect(lambda: self._accept(incoming_offer))
            btn_row.addWidget(accept_btn)
        else:
            start_btn = QPushButton("Start Call")
            start_btn.setObjectName("AccentButton")
            start_btn.clicked.connect(self._start)
            btn_row.addWidget(start_btn)

        end_btn = QPushButton("Hang Up / Close")
        end_btn.clicked.connect(self._end)
        btn_row.addWidget(end_btn)
        layout.addLayout(btn_row)

        # Auto-detect timer
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1500)
        self._poll_timer.timeout.connect(self._auto_detect_tick)
        self._poll_remaining = 0

        # Populate the combos for the first time.
        self._populate_device_combos()

        self.call_manager = calling.CallManager(
            session,
            on_remote_track=lambda track: self.status_label.setText("Connected -- receiving media"),
            on_call_ended=self._on_call_ended,
            on_state_change=self._on_connection_state_change,
            on_video_frame=self._on_video_frame,
        )

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    def _populate_device_combos(self):
        """(Re)scan audio + camera devices and fill the combo boxes."""
        _ensure_calling_initialized()

        missing = []

        # --- Microphones -------------------------------------------------
        mics = _normalize_devices(_safe_list("list_audio_input_devices"))
        prev_mic = self.mic_combo.currentData()
        self.mic_combo.blockSignals(True)
        self.mic_combo.clear()
        if mics:
            for name, value in mics:
                self.mic_combo.addItem(name, value)
            default_mic = _default_device_name(
                "default_input_device_name", "default_input_device",
            )
            target = prev_mic or default_mic
            if target:
                idx = self.mic_combo.findData(target)
                if idx < 0:
                    idx = self.mic_combo.findText(str(target))
                if idx >= 0:
                    self.mic_combo.setCurrentIndex(idx)
            self.mic_combo.setEnabled(True)
        else:
            self.mic_combo.addItem("No microphones detected", None)
            self.mic_combo.setEnabled(False)
            missing.append("microphone")
        self.mic_combo.blockSignals(False)

        # --- Speakers ----------------------------------------------------
        speakers = _normalize_devices(_safe_list("list_audio_output_devices"))
        prev_speaker = self.speaker_combo.currentData()
        self.speaker_combo.blockSignals(True)
        self.speaker_combo.clear()
        if speakers:
            for name, value in speakers:
                self.speaker_combo.addItem(name, value)
            default_speaker = _default_device_name(
                "default_output_device_name", "default_output_device",
            )
            target = prev_speaker or default_speaker
            if target:
                idx = self.speaker_combo.findData(target)
                if idx < 0:
                    idx = self.speaker_combo.findText(str(target))
                if idx >= 0:
                    self.speaker_combo.setCurrentIndex(idx)
            self.speaker_combo.setEnabled(True)
        else:
            self.speaker_combo.addItem("No speakers detected", None)
            self.speaker_combo.setEnabled(False)
            missing.append("speaker")
        self.speaker_combo.blockSignals(False)

        # --- Cameras -----------------------------------------------------
        cams = _normalize_devices(_safe_list("list_camera_devices"))
        prev_cam = self.camera_combo.currentData()
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        self.camera_combo.addItem("No camera (voice only)", None)
        if cams:
            for name, value in cams:
                self.camera_combo.addItem(name, value)
            if prev_cam:
                idx = self.camera_combo.findData(prev_cam)
                if idx >= 0:
                    self.camera_combo.setCurrentIndex(idx)
            self.camera_combo.setEnabled(True)
        else:
            missing.append("camera")
        self.camera_combo.blockSignals(False)

        # ---- Hint -------------------------------------------------------
        if missing:
            self.device_hint.setText(
                "Could not detect: " + ", ".join(missing) + ". "
                "Click 'Fix microphone/camera access' below - it will "
                "trigger the OS permission prompt and start auto-detecting."
            )
        else:
            self.device_hint.setText("")

        return missing

    # ------------------------------------------------------------------
    # Permission fixing + auto detection
    # ------------------------------------------------------------------

    def _fix_access(self, kind: str):
        """Button handler: probe the device, open OS settings, start polling."""
        self.auto_status.setText(
            f"Requesting {kind} access...  A system dialog may appear. "
            f"If it doesn't, allow it in the settings window that just opened."
        )
        QApplication.processEvents()

        # 1) Try to actually open the device -- this triggers the OS prompt
        touched = _probe_hardware(kind)
        if touched:
            print(f"[fix] {kind} probe succeeded - OS should have prompted")
        else:
            print(f"[fix] {kind} probe did not succeed - falling back to settings page")

        # 2) Open the OS privacy settings as a backup path
        open_os_privacy_settings(kind)

        # 3) Start auto-detect polling for ~60 seconds
        self._poll_remaining = 40   # 40 ticks * 1.5s = 60s
        self._poll_timer.start()

    def _auto_detect_tick(self):
        """Called every 1.5s while we're waiting for the device to appear."""
        if self._poll_remaining <= 0:
            self._poll_timer.stop()
            self.auto_status.setText(
                "Still not detected.  Try a different USB port, close other apps "
                "that use the device, then click 'Refresh devices'."
            )
            return

        self._poll_remaining -= 1
        missing = self._populate_device_combos()

        if not missing:
            # Everything appeared - stop and confirm
            self._poll_timer.stop()
            self.auto_status.setText(
                "✅ Device detected and selected.  You can start the call now."
            )
            self.auto_status.setStyleSheet("color: #7ddc8a; font-size: 11px;")
            return

        # Partial success: mic/cam present but speaker still missing etc.
        self.auto_status.setText(
            f"Waiting for the OS to grant access... ({self._poll_remaining} tries left)  "
            f"Still missing: {', '.join(missing)}"
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_video_frame(self, pil_image):
        img = pil_image.convert("RGB")
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            self.video_label.width(), self.video_label.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self.video_label.setPixmap(pixmap)
        if not self.video_label.isVisible():
            self.video_label.setVisible(True)

    def _on_call_ended(self):
        self.status_label.setText("Call ended")

    def _on_connection_state_change(self, state):
        labels = {
            "new": "Initializing...",
            "connecting": "Connecting (negotiating network path)...",
            "connected": "Connected",
            "disconnected": "Disconnected",
            "failed": "Connection failed -- likely NAT/firewall blocking direct connection",
            "closed": "Call ended",
            "timeout": "Timed out after 20s -- check Windows Firewall allows the app",
        }
        self.status_label.setText(labels.get(state, state))

    def _start(self):
        mic = self.mic_combo.currentData()
        cam = self.camera_combo.currentData()
        speaker = self.speaker_combo.currentData()
        if mic is None:
            QMessageBox.warning(
                self, "No microphone",
                "No microphone is available. Click 'Fix microphone access' "
                "and allow the OS prompt, then try again.",
            )
            return
        self.status_label.setText("Calling...")
        asyncio.ensure_future(self.call_manager.start_call(
            self.peer_id, mic_device=mic, camera_device=cam, speaker_device=speaker
        ))

    def _accept(self, offer_payload):
        mic = self.mic_combo.currentData()
        cam = self.camera_combo.currentData()
        speaker = self.speaker_combo.currentData()
        self.status_label.setText("Connecting...")

        async def _do_accept():
            try:
                await self.call_manager.handle_offer(
                    self.peer_id, offer_payload,
                    mic_device=mic, camera_device=cam, speaker_device=speaker,
                )
            except calling.CallSecurityError as e:
                print(f"[calling] {e}")
                self.status_label.setText("Call rejected: could not verify caller identity.")
                QMessageBox.critical(
                    self, "Call security warning",
                    "This call's encryption could not be verified against the caller's known identity key.",
                )

        asyncio.ensure_future(_do_accept())

    def _end(self):
        if self._poll_timer.isActive():
            self._poll_timer.stop()
        asyncio.ensure_future(self.call_manager.end_call())
        self.close()


def wipe_local_account_database() -> None:
    data = Path(DATA_DIR)
    if data.exists():
        shutil.rmtree(data, ignore_errors=True)


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SEC -- Sign In")
        self.setMinimumWidth(380)
        self.result_user_id = None
        self.result_passphrase = None
        self.result_anonymous = False
        self.result_is_signup = False
        self.result_is_dev = False
        self.result_dev_password = None

        layout = QVBoxLayout(self)

        title = QLabel("SEC")
        title.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {ACCENT}; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Secure Encrypted Chat")
        sub.setStyleSheet("color: #8aa4c8; font-size: 11px;")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)

        layout.addSpacing(8)
        layout.addWidget(QLabel("User ID"))
        self.user_input = QLineEdit()
        layout.addWidget(self.user_input)

        layout.addWidget(QLabel("Vault Passphrase"))
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.pass_input)

        self.anon_check = QCheckBox("Anonymous mode (temporary identity, not saved to disk)")
        self.anon_check.stateChanged.connect(self._toggle_anon)
        layout.addWidget(self.anon_check)

        btn_row = QHBoxLayout()
        login_btn = QPushButton("Log In")
        login_btn.clicked.connect(self._submit_login)
        btn_row.addWidget(login_btn)

        signup_btn = QPushButton("Sign Up")
        signup_btn.setObjectName("AccentButton")
        signup_btn.clicked.connect(self._submit_signup)
        btn_row.addWidget(signup_btn)
        layout.addLayout(btn_row)

        wipe_btn = QPushButton("Wipe accounts on this PC")
        wipe_btn.setObjectName("DangerButton")
        ic = assets.icon("wipe")
        if ic:
            wipe_btn.setIcon(ic)
        wipe_btn.clicked.connect(self._wipe_accounts)
        layout.addWidget(wipe_btn)

        # Tiny DEV entry
        dev_row = QHBoxLayout()
        dev_row.addStretch()
        dev_btn = QPushButton("dev")
        dev_btn.setObjectName("DevButton")
        dev_btn.setToolTip("Developer access")
        dev_btn.clicked.connect(self._dev_entry)
        dev_row.addWidget(dev_btn)
        layout.addLayout(dev_row)

    def _toggle_anon(self, state):
        anon = bool(state)
        self.pass_input.setEnabled(not anon)
        if anon:
            self.user_input.setText("anon_" + uuid_lib.uuid4().hex[:8])

    def _dev_entry(self):
        pwd, ok = QInputDialog.getText(
            self, "Developer access", "Enter developer password:",
            QLineEdit.Password,
        )
        if not ok or not pwd:
            return
        self.result_dev_password = pwd
        dlg = DevLoginDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.result_user_id = dlg.result_user_id
            self.result_passphrase = dlg.result_passphrase
            self.result_anonymous = False
            self.result_is_signup = dlg.result_is_signup
            self.result_is_dev = True
            self.accept()

    def _wipe_accounts(self):
        r1 = QMessageBox.warning(
            self, "Are you sure?",
            "Are you sure?\n\nThis will permanently delete all SEC accounts stored on this PC.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if r1 != QMessageBox.Yes:
            return
        r2 = QMessageBox.critical(
            self, "Final confirmation",
            "Your accounts on this PC will be deleted.\n\n"
            "You will have to sign up again, and your local messages / sessions "
            "on this device will be gone.\n\nThis cannot be undone. Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if r2 != QMessageBox.Yes:
            return
        try:
            wipe_local_account_database()
            QMessageBox.information(self, "Done", "Local account database wiped.")
        except Exception as e:
            QMessageBox.critical(self, "Wipe failed", str(e))

    def _validate_common(self) -> bool:
        if not self.user_input.text().strip():
            QMessageBox.warning(self, "Missing info", "Enter a user ID.")
            return False
        if not self.anon_check.isChecked() and not self.pass_input.text():
            QMessageBox.warning(self, "Missing info", "Enter a vault passphrase.")
            return False
        return True

    def _submit_login(self):
        if not self._validate_common():
            return
        user_id = self.user_input.text().strip()
        is_anon = self.anon_check.isChecked()
        if not is_anon:
            probe = GuiSession(user_id, is_anonymous=False)
            if not probe.vault.exists():
                QMessageBox.warning(
                    self, "No account found",
                    f'No local account for "{user_id}" on this device.\n\n'
                    "Use Sign Up if this is a new ID.",
                )
                return
        self.result_user_id = user_id
        self.result_passphrase = self.pass_input.text()
        self.result_anonymous = is_anon
        self.result_is_signup = False
        self.result_is_dev = False
        self.accept()

    def _submit_signup(self):
        if not self._validate_common():
            return
        user_id = self.user_input.text().strip()
        is_anon = self.anon_check.isChecked()
        if not is_anon:
            probe = GuiSession(user_id, is_anonymous=False)
            if probe.vault.exists():
                QMessageBox.warning(
                    self, "Account already exists",
                    f'A local account for "{user_id}" already exists.\nUse Log In instead.',
                )
                return
        self.result_user_id = user_id
        self.result_passphrase = self.pass_input.text()
        self.result_anonymous = is_anon
        self.result_is_signup = True
        self.result_is_dev = False
        self.accept()


class DevLoginDialog(QDialog):
    """Second login form used only after dev password is entered locally."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SEC -- Developer Login")
        self.setMinimumWidth(360)
        self.result_user_id = None
        self.result_passphrase = None
        self.result_is_signup = False

        layout = QVBoxLayout(self)
        title = QLabel("Developer mode")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {ACCENT};")
        layout.addWidget(title)
        layout.addWidget(QLabel("Create or unlock a local vault marked as DEV on the server."))

        layout.addWidget(QLabel("Dev User ID"))
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("e.g. dev_admin")
        layout.addWidget(self.user_input)

        layout.addWidget(QLabel("Vault Passphrase"))
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.pass_input)

        row = QHBoxLayout()
        login_btn = QPushButton("Dev Log In")
        login_btn.clicked.connect(self._login)
        row.addWidget(login_btn)
        signup_btn = QPushButton("Dev Sign Up")
        signup_btn.setObjectName("AccentButton")
        signup_btn.clicked.connect(self._signup)
        row.addWidget(signup_btn)
        layout.addLayout(row)

    def _login(self):
        uid = self.user_input.text().strip()
        if not uid or not self.pass_input.text():
            QMessageBox.warning(self, "Missing", "User ID and passphrase required.")
            return
        probe = GuiSession(uid, is_anonymous=False)
        if not probe.vault.exists():
            QMessageBox.warning(self, "No account", "No local vault — use Dev Sign Up.")
            return
        self.result_user_id = uid
        self.result_passphrase = self.pass_input.text()
        self.result_is_signup = False
        self.accept()

    def _signup(self):
        uid = self.user_input.text().strip()
        if not uid or not self.pass_input.text():
            QMessageBox.warning(self, "Missing", "User ID and passphrase required.")
            return
        probe = GuiSession(uid, is_anonymous=False)
        if probe.vault.exists():
            QMessageBox.warning(self, "Exists", "Local vault already exists — use Dev Log In.")
            return
        self.result_user_id = uid
        self.result_passphrase = self.pass_input.text()
        self.result_is_signup = True
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, session: GuiSession, is_dev: bool = False, dev_password: str | None = None):
        super().__init__()
        self.session = session
        self.is_dev = is_dev
        self.dev_password = dev_password
        title = f"SEC -- {session.user_id}"
        if is_dev:
            title += " [DEV]"
        self.setWindowTitle(title)
        self.resize(1100, 680)

        self.active_peer = None
        self.contacts = {}
        self.groups = {}
        self.chat_history = {}
        self._open_call_dialogs = []
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._hide_live_notice)

        self._build_ui()
        self._wire_session_hooks()

        asyncio.ensure_future(self.session.list_contacts())
        asyncio.ensure_future(self.session.list_groups())
        if self.is_dev:
            asyncio.ensure_future(self._dev_refresh_users())

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.live_notice = QLabel("")
        self.live_notice.setObjectName("LiveNotice")
        self.live_notice.setAlignment(Qt.AlignCenter)
        self.live_notice.setWordWrap(True)
        self.live_notice.setVisible(False)
        outer.addWidget(self.live_notice)

        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        outer.addLayout(root, stretch=1)

        # --- Sidebar ---
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(300)
        sb_layout = QVBoxLayout(sidebar)

        profile_row = QHBoxLayout()
        self.my_avatar_lbl = avatar_widget(self.session.user_id, size=40)
        profile_row.addWidget(self.my_avatar_lbl)
        name_col = QVBoxLayout()
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(f"<b>{self.session.user_id}</b>"))
        if self.is_dev:
            badge = QLabel("DEV")
            badge.setObjectName("DevBadge")
            name_row.addWidget(badge)
        name_row.addStretch()
        name_col.addLayout(name_row)
        self.my_bio_lbl = QLabel("")
        self.my_bio_lbl.setStyleSheet("color: #8aa4c8; font-size: 11px;")
        name_col.addWidget(self.my_bio_lbl)
        profile_row.addLayout(name_col)
        profile_row.addStretch()
        settings_btn = QPushButton()
        ic = assets.icon("settings")
        if ic:
            settings_btn.setIcon(ic)
        settings_btn.setObjectName("IconButton")
        settings_btn.clicked.connect(self._open_settings)
        profile_row.addWidget(settings_btn)
        sb_layout.addLayout(profile_row)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search people...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        sb_layout.addWidget(self.search_input)

        self.search_results_list = QListWidget()
        self.search_results_list.setTextElideMode(Qt.ElideNone)
        self.search_results_list.setWordWrap(True)
        self.search_results_list.setMaximumHeight(120)
        self.search_results_list.setVisible(False)
        self.search_results_list.itemClicked.connect(self._on_search_result_clicked)
        sb_layout.addWidget(self.search_results_list)

        sb_layout.addWidget(self._section_label("FRIENDS"))
        self.friends_list = QListWidget()
        self.friends_list.setTextElideMode(Qt.ElideNone)
        self.friends_list.setWordWrap(True)
        self.friends_list.itemClicked.connect(self._on_friend_clicked)
        sb_layout.addWidget(self.friends_list, stretch=1)

        groups_header = QHBoxLayout()
        groups_header.addWidget(self._section_label("GROUPS"))
        groups_header.addStretch()
        new_group_btn = QPushButton("+ New")
        new_group_btn.clicked.connect(self._create_group_dialog)
        join_group_btn = QPushButton("Join")
        join_group_btn.clicked.connect(self._join_group_dialog)
        groups_header.addWidget(new_group_btn)
        groups_header.addWidget(join_group_btn)
        sb_layout.addLayout(groups_header)

        self.groups_list = QListWidget()
        self.groups_list.setTextElideMode(Qt.ElideNone)
        self.groups_list.setWordWrap(True)
        self.groups_list.itemClicked.connect(self._on_group_clicked)
        self.groups_list.setMaximumHeight(140)
        sb_layout.addWidget(self.groups_list)

        root.addWidget(sidebar)

        # --- Chat panel ---
        chat_panel = QWidget()
        chat_panel.setObjectName("ChatPanel")
        cp_layout = QVBoxLayout(chat_panel)
        cp_layout.setContentsMargins(0, 0, 0, 0)
        cp_layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("ChatHeader")
        header.setFixedHeight(56)
        h_layout = QHBoxLayout(header)
        name_col2 = QVBoxLayout()
        self.peer_name_lbl = QLabel("Select a contact")
        self.peer_name_lbl.setObjectName("PeerName")
        self.peer_sub_lbl = QLabel("")
        self.peer_sub_lbl.setObjectName("PeerSub")
        name_col2.addWidget(self.peer_name_lbl)
        name_col2.addWidget(self.peer_sub_lbl)
        h_layout.addLayout(name_col2)
        h_layout.addStretch()

        voice_btn = QPushButton()
        ic = assets.icon("call")
        if ic:
            voice_btn.setIcon(ic)
        voice_btn.setObjectName("IconButton")
        voice_btn.clicked.connect(lambda: self._open_call(video=False))
        h_layout.addWidget(voice_btn)
        cp_layout.addWidget(header)

        self.messages_scroll = QScrollArea()
        self.messages_scroll.setWidgetResizable(True)
        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.addStretch()
        self.messages_scroll.setWidget(self.messages_container)
        cp_layout.addWidget(self.messages_scroll, stretch=1)

        composer = QHBoxLayout()
        self.composer_input = QLineEdit()
        self.composer_input.setPlaceholderText("Message...")
        self.composer_input.setEnabled(False)
        self.composer_input.returnPressed.connect(self._send_message)
        composer.addWidget(self.composer_input)

        for key, reaction_text in [
            ("reaction_thumbs", "👍"),
            ("reaction_heart", "❤️"),
            ("reaction_laugh", "😂"),
        ]:
            btn = QPushButton()
            btn.setObjectName("ReactionButton")
            btn.setFixedSize(40, 36)
            ic = assets.icon(key)
            if ic:
                btn.setIcon(ic)
                btn.setIconSize(btn.size() * 0.65)
            else:
                btn.setText(reaction_text)
            btn.clicked.connect(lambda _, e=reaction_text: self._send_quick_reaction(e))
            composer.addWidget(btn)

        send_btn = QPushButton("Send")
        send_btn.setObjectName("AccentButton")
        ic = assets.icon("send")
        if ic:
            send_btn.setIcon(ic)
        send_btn.clicked.connect(self._send_message)
        composer.addWidget(send_btn)
        cp_layout.addLayout(composer)

        root.addWidget(chat_panel, stretch=1)

        # --- Dev side panel ---
        if self.is_dev:
            dev_panel = QWidget()
            dev_panel.setObjectName("DevPanel")
            dev_panel.setFixedWidth(260)
            dp = QVBoxLayout(dev_panel)

            dp.addWidget(self._section_label("ALL USERS"))
            self.dev_users_list = QListWidget()
            self.dev_users_list.setTextElideMode(Qt.ElideNone)
            self.dev_users_list.setWordWrap(True)
            dp.addWidget(self.dev_users_list, stretch=1)

            refresh_btn = QPushButton("Refresh users")
            refresh_btn.clicked.connect(lambda: asyncio.ensure_future(self._dev_refresh_users()))
            dp.addWidget(refresh_btn)

            dp.addWidget(self._section_label("LIVE NOTICE"))
            self.dev_notice_input = QLineEdit()
            self.dev_notice_input.setPlaceholderText("Message to all users...")
            dp.addWidget(self.dev_notice_input)

            dur_row = QHBoxLayout()
            dur_row.addWidget(QLabel("Seconds"))
            self.dev_notice_duration = QSpinBox()
            self.dev_notice_duration.setRange(3, 300)
            self.dev_notice_duration.setValue(10)
            dur_row.addWidget(self.dev_notice_duration)
            dp.addLayout(dur_row)

            send_notice = QPushButton("Send live notice")
            send_notice.setObjectName("AccentButton")
            send_notice.clicked.connect(lambda: asyncio.ensure_future(self._dev_send_notice()))
            dp.addWidget(send_notice)

            root.addWidget(dev_panel)

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("SectionLabel")
        return lbl

    def _show_live_notice(self, text: str, duration_sec: int = 10):
        self.live_notice.setText(text)
        self.live_notice.setVisible(True)
        self._notice_timer.stop()
        self._notice_timer.start(max(3, duration_sec) * 1000)

    def _hide_live_notice(self):
        self.live_notice.setVisible(False)
        self.live_notice.setText("")

    def _wire_session_hooks(self):
        s = self.session
        s.on_message = self._handle_incoming_message
        s.on_session_established = lambda peer: self._add_system_note(peer, f"Session established with {peer}")
        s.on_presence = self._handle_presence
        s.on_search_results = self._handle_search_results
        s.on_contacts_list = self._handle_contacts_list
        s.on_contact_added = self._handle_contact_added
        s.on_group_created = self._handle_group_created
        s.on_group_joined = self._handle_group_joined
        s.on_group_member_joined = lambda gid, uid: None
        s.on_groups_list = self._handle_groups_list
        s.on_rtc_signal = self._handle_rtc_signal
        s.on_error = lambda reason: QMessageBox.warning(self, "Error", reason)
        if hasattr(s, "on_live_notice"):
            s.on_live_notice = self._on_live_notice
        if hasattr(s, "on_all_users_list"):
            s.on_all_users_list = self._on_all_users_list

    def _on_live_notice(self, message: str, duration_sec: int):
        self._show_live_notice(message, duration_sec)

    def _on_all_users_list(self, users: list):
        if not hasattr(self, "dev_users_list"):
            return
        self.dev_users_list.clear()
        for u in users:
            online = "●" if u.get("online") else "○"
            dev = " [DEV]" if u.get("is_dev") else ""
            item = QListWidgetItem(f"{online} {u['id']}{dev}")
            item.setData(Qt.UserRole, u["id"])
            self.dev_users_list.addItem(item)

    async def _dev_refresh_users(self):
        if hasattr(self.session, "list_all_users"):
            await self.session.list_all_users()
        elif self.session.relay:
            await self.session.relay._send({"type": "list_all_users"})

    async def _dev_send_notice(self):
        text = self.dev_notice_input.text().strip()
        if not text:
            return
        duration = self.dev_notice_duration.value()
        if hasattr(self.session, "dev_broadcast"):
            await self.session.dev_broadcast(text, duration)
        elif self.session.relay:
            await self.session.relay._send({
                "type": "dev_broadcast",
                "message": text,
                "duration_sec": duration,
            })
        self.dev_notice_input.clear()

    def _on_search_text_changed(self, text):
        if len(text) >= 2:
            asyncio.ensure_future(self.session.search_users(text))
        else:
            self.search_results_list.setVisible(False)

    def _handle_search_results(self, results):
        self.search_results_list.clear()
        self.search_results_list.setVisible(bool(results))
        for r in results:
            item = QListWidgetItem(r["id"])
            item.setData(Qt.UserRole, r["id"])
            av = assets.avatar_icon(r.get("avatar_id", "default")) if hasattr(assets, "avatar_icon") else None
            if av:
                item.setIcon(av)
            self.search_results_list.addItem(item)

    def _on_search_result_clicked(self, item):
        contact_id = item.data(Qt.UserRole)
        asyncio.ensure_future(self.session.add_contact(contact_id))
        self.search_input.clear()
        self.search_results_list.setVisible(False)

    def _handle_contact_added(self, contact, online):
        self.contacts[contact["id"]] = {
            "bio": contact.get("bio", ""),
            "avatar_id": contact.get("avatar_id", "default"),
            "online": online,
        }
        self._refresh_friends_list()

    def _handle_contacts_list(self, contacts):
        for c in contacts:
            self.contacts[c["id"]] = {
                "bio": c.get("bio", ""),
                "avatar_id": c.get("avatar_id", "default"),
                "online": c.get("online", False),
            }
        self._refresh_friends_list()

    def _refresh_friends_list(self):
        self.friends_list.clear()
        for user_id, info in self.contacts.items():
            item = QListWidgetItem(user_id)
            item.setData(Qt.UserRole, user_id)
            av = assets.avatar_icon(info.get("avatar_id", "default")) if hasattr(assets, "avatar_icon") else None
            if av:
                item.setIcon(av)
            else:
                item.setText(("● " if info["online"] else "○ ") + user_id)
            self.friends_list.addItem(item)

    def _handle_presence(self, user_id, online):
        if user_id in self.contacts:
            self.contacts[user_id]["online"] = online
            self._refresh_friends_list()
            if self.active_peer == user_id:
                self._update_peer_header()

    def _on_friend_clicked(self, item):
        self._select_peer(item.data(Qt.UserRole))

    def _create_group_dialog(self):
        name, ok = QInputDialog.getText(self, "New Group", "Group name:")
        if ok and name.strip():
            asyncio.ensure_future(self.session.create_group(name.strip()))

    def _join_group_dialog(self):
        token, ok = QInputDialog.getText(self, "Join Group", "Paste invite link/code:")
        if ok and token.strip():
            asyncio.ensure_future(self.session.join_group(token.strip().split("/")[-1]))

    def _handle_group_created(self, group):
        self.groups[group["id"]] = {
            "name": group["name"],
            "members": [self.session.user_id],
            "invite_token": group["invite_token"],
        }
        self._refresh_groups_list()
        QMessageBox.information(
            self, "Group created",
            f"'{group['name']}' created.\nInvite:\nsec.store/invite/{group['invite_token']}",
        )

    def _handle_group_joined(self, group, members):
        self.groups[group["id"]] = {
            "name": group["name"],
            "members": members,
            "invite_token": group["invite_token"],
        }
        self._refresh_groups_list()

    def _handle_groups_list(self, groups):
        for g in groups:
            self.groups[g["id"]] = {
                "name": g["name"],
                "members": g.get("members", []),
                "invite_token": g["invite_token"],
            }
        self._refresh_groups_list()

    def _refresh_groups_list(self):
        self.groups_list.clear()
        for gid, info in self.groups.items():
            item = QListWidgetItem(f"# {info['name']} ({len(info['members'])})")
            item.setData(Qt.UserRole, gid)
            ic = assets.icon("group")
            if ic:
                item.setIcon(ic)
            self.groups_list.addItem(item)

    def _on_group_clicked(self, item):
        gid = item.data(Qt.UserRole)
        QMessageBox.information(
            self, self.groups[gid]["name"],
            f"Members: {', '.join(self.groups[gid]['members'])}\n"
            f"Invite: sec.store/invite/{self.groups[gid]['invite_token']}",
        )

    def _select_peer(self, peer_id):
        self.active_peer = peer_id
        self._update_peer_header()
        self.composer_input.setEnabled(True)
        self._rebuild_message_view()

    def _update_peer_header(self):
        info = self.contacts.get(self.active_peer, {})
        status = "Online" if info.get("online") else "Offline"
        self.peer_name_lbl.setText(self.active_peer)
        self.peer_sub_lbl.setText(status)

    def _clear_messages_layout(self):
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _rebuild_message_view(self):
        self._clear_messages_layout()
        for sender, text, mine in self.chat_history.get(self.active_peer, []):
            self.messages_layout.insertWidget(
                self.messages_layout.count() - 1, MessageBubble(sender, text, mine)
            )

    def _add_system_note(self, peer_id, text):
        self.chat_history.setdefault(peer_id, [])
        if peer_id == self.active_peer:
            self.messages_layout.insertWidget(
                self.messages_layout.count() - 1, SystemNote(text)
            )

    def _send_message(self):
        text = self.composer_input.text().strip()
        if not text or not self.active_peer:
            return
        self.composer_input.clear()
        asyncio.ensure_future(self._send_async(self.active_peer, text))

    def _send_quick_reaction(self, emoji):
        if self.active_peer:
            asyncio.ensure_future(self._send_async(self.active_peer, emoji))

    async def _send_async(self, peer_id, text):
        try:
            await self.session.send_to_peer(peer_id, text)
        except Exception as e:
            QMessageBox.warning(self, "Send failed", str(e))

    def _handle_incoming_message(self, peer_id, text, mine):
        self.chat_history.setdefault(peer_id, []).append(
            (peer_id if not mine else self.session.user_id, text, mine)
        )
        if peer_id == self.active_peer:
            self.messages_layout.insertWidget(
                self.messages_layout.count() - 1, MessageBubble(peer_id, text, mine)
            )
            self.messages_scroll.verticalScrollBar().setValue(
                self.messages_scroll.verticalScrollBar().maximum()
            )
        if peer_id not in self.contacts:
            self.contacts[peer_id] = {"bio": "", "avatar_id": "default", "online": True}
            self._refresh_friends_list()

    def _open_settings(self):
        dlg = SettingsDialog(self.session, self.my_bio_lbl.text(), "default", self)
        dlg.exec()

    def _open_call(self, video: bool):
        if not self.active_peer:
            QMessageBox.information(self, "No contact selected", "Select a friend to call first.")
            return
        dlg = CallDialog(self.session, self.active_peer, incoming_offer=None, parent=self)
        self._open_call_dialogs.append(dlg)
        dlg.finished.connect(
            lambda _: self._open_call_dialogs.remove(dlg) if dlg in self._open_call_dialogs else None
        )
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _handle_rtc_signal(self, kind, from_user, payload):
        if kind == "offer":
            dlg = CallDialog(self.session, from_user, incoming_offer=payload, parent=self)
            self._open_call_dialogs.append(dlg)
            dlg.finished.connect(
                lambda _: self._open_call_dialogs.remove(dlg) if dlg in self._open_call_dialogs else None
            )
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            return

        target_dlg = None
        for dlg in self._open_call_dialogs:
            if dlg.call_manager.peer_id == from_user:
                target_dlg = dlg
                break
        if target_dlg is None:
            print(f"[calling] received '{kind}' from {from_user} but no open dialog -- dropping")
            return

        if kind == "answer":
            async def _do_answer():
                try:
                    await target_dlg.call_manager.handle_answer(payload, from_user=from_user)
                except calling.CallSecurityError as e:
                    print(f"[calling] {e}")
                    target_dlg.status_label.setText("Call ended: identity check failed.")
                    asyncio.ensure_future(target_dlg.call_manager.end_call())
            asyncio.ensure_future(_do_answer())
        elif kind == "ice":
            asyncio.ensure_future(target_dlg.call_manager.handle_ice(payload))


async def do_connect(
    user_id: str,
    passphrase: str,
    is_anonymous: bool,
    is_signup: bool,
    session_holder: dict,
    is_dev: bool = False,
    dev_password: str | None = None,
):
    session = GuiSession(user_id, is_anonymous=is_anonymous)
    public_reg = None
    is_new_identity = False

    if is_anonymous or is_signup:
        public_reg = session.setup_new_identity(passphrase if not is_anonymous else None)
        is_new_identity = True
    else:
        try:
            session.unlock_existing_identity(passphrase)
        except VaultError as e:
            QMessageBox.critical(None, "Unlock failed", str(e))
            return
        session.device_id = session.load_device_id()

    await session.connect()

    relay = session.relay
    if relay is not None:
        @relay.on("live_notice")
        async def _(msg):
            if session.on_live_notice:
                session.on_live_notice(msg.get("message", ""), int(msg.get("duration_sec") or 10))

        @relay.on("all_users_list")
        async def _(msg):
            if session.on_all_users_list:
                session.on_all_users_list(msg.get("users", []))

        @relay.on("dev_session_ok")
        async def _(msg):
            print("[dev] server accepted developer session")

        @relay.on("dev_password_result")
        async def _(msg):
            print("[dev] password result", msg.get("ok"))

        if is_dev and dev_password:
            try:
                await relay._send({
                    "type": "dev_hello",
                    "user_id": user_id,
                    "password": dev_password,
                    "is_anonymous": is_anonymous,
                })
            except Exception as e:
                print("[dev] dev_hello failed:", e)

    if is_new_identity or not session.device_id:
        if public_reg is None:
            public_reg = session.rebuild_public_registration()
        await session.register(public_reg)

    session.on_live_notice = None
    session.on_all_users_list = None

    session_holder["session"] = session


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    app.setApplicationName("SEC")

    login = LoginDialog()
    if login.exec() != QDialog.Accepted:
        return

    user_id = login.result_user_id
    passphrase = login.result_passphrase
    is_anonymous = login.result_anonymous
    is_signup = login.result_is_signup
    is_dev = bool(login.result_is_dev)
    dev_password = login.result_dev_password

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    session_holder = {}
    with loop:
        try:
            loop.run_until_complete(
                do_connect(
                    user_id, passphrase, is_anonymous, is_signup, session_holder,
                    is_dev=is_dev, dev_password=dev_password,
                )
            )
        except Exception as e:
            import traceback
            print("REAL ERROR during connect/register:")
            traceback.print_exc()
            QMessageBox.critical(None, "Connection failed", f"{type(e).__name__}: {e}")
            return

        session = session_holder.get("session")
        if not session:
            print("No session created.")
            return

        window = MainWindow(session, is_dev=is_dev, dev_password=dev_password)
        window.show()
        loop.run_forever()


if __name__ == "__main__":
    main()