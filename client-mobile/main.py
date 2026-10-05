"""
client-mobile/main.py

SEC -- mobile client (Kivy). Text messaging only for this pass
(no calling/groups yet -- deliberately scoped small to keep the first
mobile build simple to debug). Reuses the exact same E2EE session
engine (session.py) as the desktop client -- same X3DH + Double
Ratchet crypto, already tested extensively there.

The visual theme is a port of client-desktop/theme.py so the two
clients feel like one product: deep navy background, dodger-blue
accent, translucent glass panels.

ARCHITECTURE NOTE: Kivy has its own event loop (not asyncio-based).
websockets/async code runs on a background thread with its own
async loop. Any UI update from that thread MUST go through
Clock.schedule_once() to safely marshal back onto Kivy's main thread --
touching Kivy widgets directly from the background thread will crash
or corrupt the UI.

PLATFORM NOTE: calling.py depends on pyjnius, which only works on
Android. During desktop development (Windows / Linux / macOS) the
import is skipped and the call button is inert. Build the APK with
Buildozer for a real Android test:
    buildozer -v android debug

ICONS: No emoji anywhere -- emoji render as colored pictures on
Android/Windows and look inconsistent. Instead we use plain Unicode
symbols, and where a glyph has an emoji variant (like U+260E TELEPHONE)
we append U+FE0E (Variation Selector-15) to force text presentation.
"""

import asyncio
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.checkbox import CheckBox
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle

from session import GuiSession, DATA_DIR
from crypto import vault
from crypto.vault import VaultError

# calling.py imports pyjnius, which only exists on Android. Skip it on
# desktop dev environments so the rest of the app still runs.
try:
    import calling
    _HAS_CALLING = True
except Exception as _e:
    print(f"[main] calling unavailable on this platform: {type(_e).__name__}: {_e}")
    calling = None
    _HAS_CALLING = False


# =========================================================================
# Icons -- plain Unicode, no emoji.
#
# \uFE0E is VARIATION SELECTOR-15 ("text presentation"). Appending it to
# a glyph that has both an emoji and a text form tells the OS to render
# the monochrome text version. Supported on Android 4.4+ and modern
# Windows. Symbols that have no emoji variant are used bare.
# =========================================================================

ICON_MENU        = "\u2630"            # ☰ trigram (hamburger)
ICON_CALL        = "\u260E\uFE0E"      # ☎ telephone -> forced text
ICON_SEND        = "\u27A4"            # ➤ black rightwards arrowhead
ICON_ADD         = "\u271A"            # ✚ heavy greek cross
ICON_SEARCH      = "\u2315"            # ⌕ (circle with tail -- search-ish)
ICON_CLOSE       = "\u2715"            # ✕ multiplication X
ICON_LEFT        = "\u2190"            # ← leftwards arrow
ICON_SIGN_OUT    = "\u21E5"            # ⇥ rightwards arrow to bar
ICON_DOT_ONLINE  = "\u25CF"            # ● filled circle
ICON_DOT_OFFLINE = "\u25CB"            # ○ empty circle


# =========================================================================
# Theme -- mirrors client-desktop/theme.py, converted to Kivy float RGBA.
# =========================================================================

COL_BG_DEEPEST     = (0.043, 0.071, 0.125, 1.0)   # #0b1220
COL_BG_SIDEBAR     = (0.078, 0.157, 0.275, 1.0)   # ~rgba(20,40,70)
COL_BG_PANEL       = (0.071, 0.137, 0.235, 1.0)   # ~rgba(18,35,60)
COL_BG_INPUT       = (0.118, 0.216, 0.373, 1.0)   # ~rgba(30,55,95)
COL_BG_HOVER       = (0.157, 0.294, 0.510, 1.0)   # ~rgba(40,75,130)
COL_ACCENT         = (0.118, 0.565, 1.000, 1.0)   # #1e90ff
COL_ACCENT_BRIGHT  = (0.310, 0.765, 1.000, 1.0)   # #4fc3ff
COL_ACCENT_DIM     = (0.051, 0.310, 0.541, 1.0)   # #0d4f8a
COL_DANGER         = (0.627, 0.157, 0.157, 1.0)   # ~#a02828
COL_DANGER_BRIGHT  = (0.863, 0.149, 0.149, 1.0)   # ~#dc2626
COL_ONLINE         = (0.239, 0.839, 0.549, 1.0)   # #3dd68c
COL_TEXT_MAIN      = (0.910, 0.945, 1.000, 1.0)   # #e8f1ff
COL_TEXT_MUTED     = (0.541, 0.643, 0.784, 1.0)   # #8aa4c8
COL_TEXT_DIM       = (0.353, 0.451, 0.600, 1.0)   # #5a7399
COL_BORDER         = (0.314, 0.588, 1.000, 0.35)

# Hex strings for markup tags (Kivy's [color=#rrggbb] uses hex, not floats).
_HEX_ONLINE   = "#3dd68c"
_HEX_MUTED    = "#8aa4c8"
_HEX_ACCENT   = "#1e90ff"
_HEX_DANGER   = "#dc2626"

Window.clearcolor = COL_BG_DEEPEST


# =========================================================================
# Shared styling helpers
# =========================================================================

class GlassButton(Button):
    """Button with a rounded, translucent background -- the Kivy analog of
    the desktop's QPushButton + AccentButton / DangerButton styling."""

    def __init__(self, accent: bool = False, danger: bool = False,
                 radius: int = 10, tint=None, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_color = (0, 0, 0, 0)

        if tint is not None:
            bg = tint
        elif danger:
            bg = COL_DANGER
        elif accent:
            bg = COL_ACCENT
        else:
            bg = COL_BG_INPUT

        self._bg = bg
        with self.canvas.before:
            self._bg_color = Color(*bg)
            self._bg_rect = RoundedRectangle(
                pos=self.pos, size=self.size, radius=[radius]
            )
        self.bind(pos=self._sync_bg, size=self._sync_bg)
        self.bind(state=self._on_state)

    def _sync_bg(self, *_):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def _on_state(self, _inst, state):
        if state == "down":
            r, g, b, a = self._bg
            self._bg_color.rgba = (min(r + 0.08, 1.0),
                                   min(g + 0.08, 1.0),
                                   min(b + 0.08, 1.0), a)
        else:
            self._bg_color.rgba = self._bg


class GlassInput(TextInput):
    """TextInput themed like the desktop's QLineEdit (translucent blue)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("background_color", COL_BG_INPUT)
        kwargs.setdefault("foreground_color", COL_TEXT_MAIN)
        kwargs.setdefault("cursor_color", COL_ACCENT_BRIGHT)
        kwargs.setdefault("hint_text_color", COL_TEXT_DIM)
        kwargs.setdefault("padding", [12, 12, 12, 12])
        kwargs.setdefault("multiline", False)
        super().__init__(**kwargs)


def flat_bg(widget, color):
    """Solid rectangular background for containers/panels."""
    with widget.canvas.before:
        Color(*color)
        rect = Rectangle(pos=widget.pos, size=widget.size)

    def update(*_):
        rect.pos = widget.pos
        rect.size = widget.size

    widget.bind(pos=update, size=update)


def section_label(text):
    """Small uppercase section header, like QLabel#SectionLabel."""
    return Label(
        text=f"[b]{text}[/b]", markup=True,
        color=COL_TEXT_DIM, font_size=11,
        size_hint=(1, None), height=22,
        halign="left", valign="middle",
    )


# =========================================================================
# Async bridge (unchanged -- do not modify)
# =========================================================================

class AsyncBridge:
    """Runs an async event loop on a background thread and lets Kivy
    code schedule coroutines onto it safely."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run_coro(self, coro):
        """Schedule a coroutine on the background loop from Kivy's main thread."""
        return asyncio.run_coroutine_threadsafe(coro, self.loop)


# =========================================================================
# Remember-me helpers (mobile-safe)
# =========================================================================

def _try_save_remember_me(session, passphrase: str) -> bool:
    """Attempt to persist the vault passphrase for auto-login.

    Returns True on success, False if the platform keystore is
    unavailable or the call fails for any other reason. Never raises --
    a failure here must NOT break the login flow.
    """
    try:
        platform = vault.current_platform()
    except Exception as e:
        print(f"[remember-me] current_platform() failed: {type(e).__name__}: {e}")
        return False

    saved_any = False

    # Vault-level remember-me (unlocks the identity vault)
    try:
        if hasattr(session.vault, "save_remember_me"):
            session.vault.save_remember_me(passphrase, platform)
            saved_any = True
    except Exception as e:
        print(f"[remember-me] vault.save_remember_me failed: "
              f"{type(e).__name__}: {e}")

    # Session-store-level remember-me (unlocks the ratchet store)
    try:
        if hasattr(session, "session_store") and hasattr(session.session_store, "save_remember_me"):
            session.session_store.save_remember_me(passphrase, platform)
            saved_any = True
    except Exception as e:
        print(f"[remember-me] session_store.save_remember_me failed: "
              f"{type(e).__name__}: {e}")

    return saved_any


# =========================================================================
# Login
# =========================================================================

class LoginScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        root = BoxLayout(orientation="vertical", padding=24, spacing=14)
        flat_bg(root, COL_BG_DEEPEST)

        # -- Brand header -------------------------------------------------
        title = Label(
            text="[b]SEC[/b]", markup=True, font_size=34,
            color=COL_ACCENT, size_hint=(1, 0.14),
        )
        root.add_widget(title)

        sub = Label(
            text="Secure Encrypted Chat",
            color=COL_TEXT_MUTED, font_size=12, size_hint=(1, 0.05),
        )
        root.add_widget(sub)

        root.add_widget(BoxLayout(size_hint=(1, 0.03)))

        # -- Credentials --------------------------------------------------
        self.user_input = GlassInput(hint_text="User ID", size_hint=(1, 0.1))
        root.add_widget(self.user_input)

        self.pass_input = GlassInput(
            hint_text="Vault passphrase", password=True, size_hint=(1, 0.1),
        )
        root.add_widget(self.pass_input)

        # -- Options ------------------------------------------------------
        anon_row = BoxLayout(size_hint=(1, 0.07), spacing=8)
        self.anon_check = CheckBox(
            color=COL_ACCENT, size_hint=(None, 1), width=40,
        )
        anon_row.add_widget(self.anon_check)
        anon_row.add_widget(Label(
            text="Anonymous mode (temporary identity)",
            color=COL_TEXT_MUTED, font_size=12,
        ))
        root.add_widget(anon_row)

        remember_row = BoxLayout(size_hint=(1, 0.07), spacing=8)
        self.remember_check = CheckBox(
            color=COL_ACCENT, size_hint=(None, 1), width=40,
        )
        remember_row.add_widget(self.remember_check)
        remember_row.add_widget(Label(
            text="Stay signed in", color=COL_TEXT_MUTED, font_size=12,
        ))
        root.add_widget(remember_row)

        # -- Status + primary action -------------------------------------
        self.status_label = Label(
            text="", color=COL_TEXT_MUTED, font_size=12, size_hint=(1, 0.08),
        )
        root.add_widget(self.status_label)

        connect_btn = GlassButton(
            text="Connect", accent=True, bold=True,
            size_hint=(1, 0.11),
        )
        connect_btn.bind(on_release=self._connect)
        root.add_widget(connect_btn)

        root.add_widget(BoxLayout(size_hint=(1, 0.25)))

        self.add_widget(root)

    def _connect(self, *_):
        user_id = self.user_input.text.strip()
        passphrase = self.pass_input.text
        is_anon = self.anon_check.active
        remember_me = self.remember_check.active and not is_anon
        if not user_id:
            self.status_label.text = "Enter a user ID first."
            self.status_label.color = COL_DANGER_BRIGHT
            return
        self.status_label.color = COL_TEXT_MUTED
        self.status_label.text = "Connecting..."
        self.app.begin_login(
            user_id, passphrase, is_anon, self._on_result, remember_me=remember_me,
        )

    def _on_result(self, ok, error_message=None):
        def update(_dt):
            if ok:
                self.app.show_chat_screen()
            else:
                self.status_label.text = f"Failed: {error_message}"
                self.status_label.color = COL_DANGER_BRIGHT
        Clock.schedule_once(update)


# =========================================================================
# Friends panel (slide-in sidebar)
# =========================================================================

class FriendsPanel(FloatLayout):
    """Slide-in sidebar: search box + search results + friends list.
    Mirrors desktop's sidebar so the two clients behave the same way."""

    PANEL_WIDTH_FRAC = 0.8

    def __init__(self, app, on_friend_selected, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.on_friend_selected = on_friend_selected
        self.contacts = {}
        self._is_open = False

        panel_width = Window.width * self.PANEL_WIDTH_FRAC

        # Tap-outside-to-close scrim.
        self.scrim = Button(
            background_color=(0, 0, 0, 0), background_normal="",
            size_hint=(1, 1), opacity=0,
        )
        self.scrim.bind(on_release=lambda *_: self.close())

        self.panel = BoxLayout(
            orientation="vertical", padding=12, spacing=8,
            size_hint=(None, 1), width=panel_width,
            pos_hint={"top": 1},
        )
        self.panel.x = -panel_width
        flat_bg(self.panel, COL_BG_SIDEBAR)

        # -- Brand + search ----------------------------------------------
        header = Label(
            text="[b]SEC[/b]", markup=True, font_size=20,
            color=COL_ACCENT, size_hint=(1, None), height=32,
            halign="left", valign="middle",
        )
        header.bind(size=lambda i, *_: setattr(i, "text_size", (i.width, None)))
        self.panel.add_widget(header)

        search_row = BoxLayout(size_hint=(1, None), height=44, spacing=6)
        self.search_input = GlassInput(
            hint_text="Search people...", size_hint=(1, 1),
        )
        self.search_input.bind(text=self._on_search_text_changed)
        search_row.add_widget(self.search_input)

        add_btn = GlassButton(
            text=f"{ICON_ADD}  Add", accent=True, size_hint=(None, 1), width=80,
        )
        add_btn.bind(on_release=self._add_by_typed_name)
        search_row.add_widget(add_btn)
        self.panel.add_widget(search_row)

        # -- Search results dropdown -------------------------------------
        self.results_scroll = ScrollView(size_hint=(1, 0.22))
        self.results_box = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=2,
        )
        self.results_box.bind(minimum_height=self.results_box.setter("height"))
        self.results_scroll.add_widget(self.results_box)
        self.panel.add_widget(self.results_scroll)

        # -- Friends list -------------------------------------------------
        self.panel.add_widget(section_label("FRIENDS"))

        self.friends_scroll = ScrollView(size_hint=(1, 0.55))
        self.friends_box = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=3,
        )
        self.friends_box.bind(minimum_height=self.friends_box.setter("height"))
        self.friends_scroll.add_widget(self.friends_box)
        self.panel.add_widget(self.friends_scroll)

        self.status_label = Label(
            text="", color=COL_TEXT_MUTED, font_size=12,
            size_hint=(1, None), height=20,
        )
        self.panel.add_widget(self.status_label)

        self.add_widget(self.panel)

    # -- open / close -----------------------------------------------------

    def toggle(self):
        self.close() if self._is_open else self.open()

    def open(self):
        self._is_open = True
        if self.scrim.parent is None:
            self.add_widget(self.scrim, index=len(self.children))
        self.scrim.opacity = 1
        Animation(x=0, d=0.18, t="out_quad").start(self.panel)

    def close(self):
        self._is_open = False
        self.scrim.opacity = 0
        if self.scrim.parent is not None:
            self.remove_widget(self.scrim)
        Animation(x=-self.panel.width, d=0.18, t="in_quad").start(self.panel)

    # -- search -----------------------------------------------------------

    def _on_search_text_changed(self, _instance, text):
        text = text.strip()
        if len(text) >= 2:
            self.app.bridge.run_coro(self.app.session.search_users(text))
        else:
            self.results_box.clear_widgets()

    def show_search_results(self, results):
        self.results_box.clear_widgets()
        for r in results:
            btn = self._make_row(
                f"{r['id']}",
                on_press=lambda _i, uid=r["id"]: self._add_contact(uid),
            )
            self.results_box.add_widget(btn)

    def _add_contact(self, contact_id):
        self.app.bridge.run_coro(self.app.session.add_contact(contact_id))
        self.search_input.text = ""
        self.results_box.clear_widgets()

    def _add_by_typed_name(self, *_):
        name = self.search_input.text.strip()
        if name:
            self._add_contact(name)

    # -- friends list -----------------------------------------------------

    def update_contacts(self, contacts: dict):
        self.contacts = contacts
        self._refresh_friends_list()

    def _refresh_friends_list(self):
        self.friends_box.clear_widgets()
        for user_id, info in self.contacts.items():
            # Colored circle via markup, not emoji.
            if info.get("online"):
                dot_markup = f"[color={_HEX_ONLINE}]{ICON_DOT_ONLINE}[/color]"
            else:
                dot_markup = f"[color={_HEX_MUTED}]{ICON_DOT_OFFLINE}[/color]"
            btn = self._make_row(
                f"{dot_markup}  {user_id}",
                on_press=lambda _i, uid=user_id: self._select_friend(uid),
                markup=True,
            )
            self.friends_box.add_widget(btn)

    def _select_friend(self, user_id):
        self.on_friend_selected(user_id)
        self.close()

    def _make_row(self, text, on_press, markup: bool = False):
        btn = GlassButton(
            text=text, size_hint_y=None, height=46,
            halign="left", valign="middle",
            tint=COL_BG_PANEL,
        )
        btn.markup = markup
        btn.bind(size=lambda i, *_: setattr(i, "text_size", (i.width - 20, None)))
        btn.bind(on_release=on_press)
        return btn


# =========================================================================
# Chat screen
# =========================================================================

class ChatScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.active_peer = None
        self.chat_history = {}

        outer = FloatLayout()
        root = BoxLayout(orientation="vertical", padding=10, spacing=8)
        flat_bg(root, COL_BG_DEEPEST)

        # -- Header --------------------------------------------------------
        header = BoxLayout(size_hint=(1, 0.08), spacing=8)
        flat_bg(header, COL_BG_PANEL)

        menu_btn = GlassButton(
            text=ICON_MENU, size_hint=(0.12, 1), tint=COL_BG_INPUT,
            font_size=20,
        )
        menu_btn.bind(on_release=lambda *_: self.friends_panel.toggle())
        header.add_widget(menu_btn)

        self.peer_header_lbl = Label(
            text="Select a friend", color=COL_TEXT_MAIN,
            bold=True, font_size=15,
        )
        header.add_widget(self.peer_header_lbl)

        self.call_btn = GlassButton(
            text=ICON_CALL, size_hint=(0.12, 1), tint=COL_BG_INPUT,
            font_size=18, disabled=True,
        )
        self.call_btn.bind(on_release=lambda *_: self._start_call())
        header.add_widget(self.call_btn)

        logout_btn = GlassButton(
            text=f"{ICON_SIGN_OUT}  Sign out",
            size_hint=(0.32, 1), tint=COL_BG_INPUT,
        )
        logout_btn.bind(on_release=lambda *_: self.app.logout())
        header.add_widget(logout_btn)
        root.add_widget(header)

        # -- Messages ------------------------------------------------------
        self.scroll = ScrollView(size_hint=(1, 0.76))
        self.log_box = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=6, padding=6,
        )
        self.log_box.bind(minimum_height=self.log_box.setter("height"))
        self.scroll.add_widget(self.log_box)
        root.add_widget(self.scroll)

        # -- Composer ------------------------------------------------------
        composer = BoxLayout(size_hint=(1, 0.1), spacing=8)
        self.msg_input = GlassInput(
            hint_text="Message...", size_hint=(1, 1),
        )
        self.msg_input.bind(on_text_validate=self._send)
        composer.add_widget(self.msg_input)

        send_btn = GlassButton(
            text=f"Send  {ICON_SEND}", accent=True,
            size_hint=(None, 1), width=90,
        )
        send_btn.bind(on_release=self._send)
        composer.add_widget(send_btn)
        root.add_widget(composer)

        outer.add_widget(root)

        self.friends_panel = FriendsPanel(app, on_friend_selected=self._select_peer)
        outer.add_widget(self.friends_panel)

        self.add_widget(outer)

    # -- peer selection ---------------------------------------------------

    def _select_peer(self, peer_id):
        self.active_peer = peer_id
        self.peer_header_lbl.text = peer_id
        self.msg_input.disabled = False
        self.call_btn.disabled = not _HAS_CALLING
        self._rebuild_log()

    # -- calling ----------------------------------------------------------

    def _start_call(self):
        if not _HAS_CALLING:
            self.peer_header_lbl.text = f"{self.active_peer} (calling unavailable)"
            Clock.schedule_once(lambda _dt: self._reset_header_after_delay(), 2.0)
            return
        if not self.active_peer or not self.app.call_manager:
            return
        self.call_btn.disabled = True
        self.peer_header_lbl.text = f"{self.active_peer} (calling...)"
        self.app.bridge.run_coro(self.app.call_manager.start_call(self.active_peer))

    def _reset_header_after_delay(self):
        if self.active_peer:
            self.peer_header_lbl.text = self.active_peer

    def on_incoming_call(self, from_user):
        content = BoxLayout(orientation="vertical", spacing=10, padding=10)
        flat_bg(content, COL_BG_PANEL)
        content.add_widget(Label(
            text=f"Incoming call from {from_user}", color=COL_TEXT_MAIN,
        ))
        btn_row = BoxLayout(spacing=10, size_hint=(1, 0.4))
        popup = Popup(
            title="Incoming Call", content=content,
            size_hint=(0.8, 0.4), auto_dismiss=False,
            title_color=COL_ACCENT, separator_color=COL_ACCENT,
        )

        def accept(*_):
            popup.dismiss()
            if self.app.call_manager is None:
                return
            self.peer_header_lbl.text = f"{from_user} (connecting...)"
            self.app.bridge.run_coro(self.app._pending_offer_accept(from_user))

        def decline(*_):
            popup.dismiss()
            if self.app.call_manager is not None:
                self.app.bridge.run_coro(self.app.call_manager.end_call(notify_peer=True))

        accept_btn = GlassButton(text="Accept", accent=True)
        accept_btn.bind(on_release=accept)
        decline_btn = GlassButton(text="Decline", danger=True)
        decline_btn.bind(on_release=decline)
        btn_row.add_widget(accept_btn)
        btn_row.add_widget(decline_btn)
        content.add_widget(btn_row)
        popup.open()

    def on_call_state(self, state_str):
        self.peer_header_lbl.text = f"{self.active_peer} ({state_str.lower()})"
        if state_str in ("CONNECTED",):
            self.call_btn.disabled = False

    def on_call_ended(self):
        if self.active_peer:
            self.peer_header_lbl.text = self.active_peer
        self.call_btn.disabled = not _HAS_CALLING

    def _rebuild_log(self):
        self.log_box.clear_widgets()
        for sender, text, mine in self.chat_history.get(self.active_peer, []):
            self._append_widget(f"[You]: {text}" if mine else f"[{sender}]: {text}")

    def _append_widget(self, text):
        self.log_box.add_widget(Label(
            text=text, color=COL_TEXT_MAIN, size_hint_y=None,
            height=28, halign="left",
            text_size=(Window.width - 40, None),
        ))
        if self.log_box.children:
            self.scroll.scroll_to(self.log_box.children[0])

    # -- sending ----------------------------------------------------------

    def _send(self, *_):
        text = self.msg_input.text.strip()
        if not text or not self.active_peer:
            return
        self.msg_input.text = ""
        self.chat_history.setdefault(self.active_peer, []).append(
            (self.app.session.user_id, text, True)
        )
        if self.active_peer == self.active_peer:
            self._append_widget(f"[You]: {text}")
        self.app.send_message(self.active_peer, text)

    # -- incoming ---------------------------------------------------------

    def on_incoming_message(self, peer_id, text, mine):
        if mine:
            return
        self.chat_history.setdefault(peer_id, []).append((peer_id, text, False))
        if peer_id not in self.friends_panel.contacts:
            self.friends_panel.contacts[peer_id] = {
                "bio": "", "avatar_id": "default", "online": True,
            }
            self.friends_panel._refresh_friends_list()
        if peer_id == self.active_peer:
            self._append_widget(f"[{peer_id}]: {text}")

    def on_contacts_list(self, contacts):
        merged = dict(self.friends_panel.contacts)
        for c in contacts:
            merged[c["id"]] = {
                "bio": c.get("bio", ""),
                "avatar_id": c.get("avatar_id", "default"),
                "online": c.get("online", False),
            }
        self.friends_panel.update_contacts(merged)

    def on_contact_added(self, contact, online):
        if contact is None:
            self.friends_panel.status_label.text = "No user with that name."
            self.friends_panel.status_label.color = COL_DANGER_BRIGHT
            return
        merged = dict(self.friends_panel.contacts)
        merged[contact["id"]] = {
            "bio": contact.get("bio", ""),
            "avatar_id": contact.get("avatar_id", "default"),
            "online": online,
        }
        self.friends_panel.update_contacts(merged)
        self.friends_panel.status_label.text = ""

    def on_error(self, reason):
        if reason == "no_such_user":
            self.friends_panel.status_label.text = "No user with that name."
            self.friends_panel.status_label.color = COL_DANGER_BRIGHT

    def on_search_results(self, results):
        self.friends_panel.show_search_results(results)

    def on_presence(self, user_id, online):
        if user_id in self.friends_panel.contacts:
            self.friends_panel.contacts[user_id]["online"] = online
            self.friends_panel._refresh_friends_list()


# =========================================================================
# App
# =========================================================================

class SecApp(App):
    LAST_USER_PATH = DATA_DIR / "last_user.txt"

    def build(self):
        self.bridge = AsyncBridge()
        self.session: GuiSession | None = None
        self.call_manager = None
        self._pending_offer = None
        self.sm = ScreenManager()
        self.login_screen = LoginScreen(self, name="login")
        self.sm.add_widget(self.login_screen)
        self._try_saved_login()
        return self.sm

    def _hook_session_callbacks(self, session):
        session.on_message = self._on_message
        session.on_contacts_list = self._on_contacts_list
        session.on_contact_added = self._on_contact_added
        session.on_search_results = self._on_search_results
        session.on_presence = self._on_presence
        session.on_error = self._on_error
        session.on_rtc_signal = self._on_rtc_signal

        if _HAS_CALLING:
            self.call_manager = calling.CallManager(
                session, self.bridge,
                on_state_change=self._on_call_state,
                on_call_ended=self._on_call_ended,
            )
        else:
            self.call_manager = None

    def _try_saved_login(self):
        """Runs once at startup. Silent -- on any failure (no saved user,
        keystore unwrap fails, app reinstalled, etc.) it just leaves the
        normal passphrase login screen showing."""
        if not self.LAST_USER_PATH.exists():
            return
        try:
            user_id = self.LAST_USER_PATH.read_text().strip()
        except Exception as e:
            print(f"[auto-login] could not read {self.LAST_USER_PATH}: {e}")
            return
        if not user_id:
            return

        async def do_auto():
            try:
                session = GuiSession(user_id, is_anonymous=False)

                # Guard every keystore-touching call individually so a
                # missing backend can't take down the whole startup.
                try:
                    has_saved = session.has_remembered_login()
                except Exception as e:
                    print(f"[auto-login] has_remembered_login() failed: {e}")
                    return
                if not has_saved:
                    return

                try:
                    unlocked = session.try_auto_login()
                except Exception as e:
                    print(f"[auto-login] try_auto_login() failed: {e}")
                    return
                if not unlocked:
                    return

                session.device_id = session.load_device_id()
                await session.connect()
                self.session = session
                self._hook_session_callbacks(session)
                Clock.schedule_once(lambda _dt: self.show_chat_screen())
            except Exception as e:
                print(f"[auto-login] skipped, showing login screen: {e}")

        self.bridge.run_coro(do_auto())

    def begin_login(self, user_id, passphrase, is_anonymous, callback, remember_me=False):
        async def do_login():
            try:
                session = GuiSession(user_id, is_anonymous=is_anonymous)
                public_reg = None
                is_new_identity = False

                if not is_anonymous and session.vault.exists():
                    session.unlock_existing_identity(passphrase, remember_me=remember_me)
                    session.device_id = session.load_device_id()
                else:
                    public_reg = session.setup_new_identity(
                        passphrase if not is_anonymous else None
                    )
                    is_new_identity = True

                await session.connect()

                if is_new_identity or not session.device_id:
                    if public_reg is None:
                        public_reg = session.rebuild_public_registration()
                    await session.register(public_reg)

                # Only AFTER a successful login do we attempt to save the
                # remember-me token. Failure here must NOT mark the login
                # as failed -- the user is already in. We log it and skip
                # auto-login for next time.
                if remember_me and not is_anonymous:
                    saved = _try_save_remember_me(session, passphrase)
                    if saved:
                        try:
                            self.LAST_USER_PATH.parent.mkdir(parents=True, exist_ok=True)
                            self.LAST_USER_PATH.write_text(user_id)
                        except Exception as e:
                            print(f"[remember-me] could not write "
                                  f"{self.LAST_USER_PATH}: {e}")
                    else:
                        print("[remember-me] keystore unavailable on this "
                              "platform; user will need to sign in manually "
                              "next time.")

                self.session = session
                self._hook_session_callbacks(session)
                callback(True)
            except VaultError as e:
                callback(False, str(e))
            except Exception as e:
                callback(False, f"{type(e).__name__}: {e}")

        self.bridge.run_coro(do_login())

    def logout(self):
        if self.session:
            try:
                self.session.logout()
            except Exception as e:
                print(f"[logout] session.logout() failed: {e}")
        try:
            if self.LAST_USER_PATH.exists():
                self.LAST_USER_PATH.unlink()
        except Exception as e:
            print(f"[logout] could not delete {self.LAST_USER_PATH}: {e}")
        self.session = None
        if hasattr(self, "chat_screen"):
            self.sm.remove_widget(self.chat_screen)
            del self.chat_screen
        self.login_screen.status_label.text = "Signed out."
        self.login_screen.status_label.color = COL_TEXT_MUTED
        self.sm.current = "login"

    # -- callbacks from async thread --------------------------------------

    def _on_message(self, peer_id, text, mine):
        def update(_dt):
            if hasattr(self, "chat_screen"):
                self.chat_screen.on_incoming_message(peer_id, text, mine)
        Clock.schedule_once(update)

    def _on_contacts_list(self, contacts):
        def update(_dt):
            if hasattr(self, "chat_screen"):
                self.chat_screen.on_contacts_list(contacts)
        Clock.schedule_once(update)

    def _on_contact_added(self, contact, online):
        def update(_dt):
            if hasattr(self, "chat_screen"):
                self.chat_screen.on_contact_added(contact, online)
        Clock.schedule_once(update)

    def _on_search_results(self, results):
        def update(_dt):
            if hasattr(self, "chat_screen"):
                self.chat_screen.on_search_results(results)
        Clock.schedule_once(update)

    def _on_presence(self, user_id, online):
        def update(_dt):
            if hasattr(self, "chat_screen"):
                self.chat_screen.on_presence(user_id, online)
        Clock.schedule_once(update)

    def _on_error(self, reason):
        def update(_dt):
            if hasattr(self, "chat_screen"):
                self.chat_screen.on_error(reason)
        Clock.schedule_once(update)

    def _on_rtc_signal(self, kind, from_user, payload):
        def update(_dt):
            if kind == "offer":
                self._pending_offer = (from_user, payload)
                if hasattr(self, "chat_screen"):
                    self.chat_screen.on_incoming_call(from_user)
            elif kind == "answer":
                if self.call_manager is not None:
                    self.bridge.run_coro(self._handle_answer_safely(payload, from_user))
            elif kind == "ice":
                if self.call_manager is not None:
                    self.bridge.run_coro(self.call_manager.handle_ice(payload))
            elif kind == "end":
                if self.call_manager is not None:
                    self.bridge.run_coro(self.call_manager.end_call(notify_peer=False))
        Clock.schedule_once(update)

    async def _handle_answer_safely(self, payload, from_user):
        try:
            await self.call_manager.handle_answer(payload)
        except Exception as e:
            print(f"[calling] answer verification/handling failed: {e}")
            Clock.schedule_once(lambda _dt: self._show_call_security_warning())
            await self.call_manager.end_call(notify_peer=True)

    async def _pending_offer_accept(self, from_user):
        if not self._pending_offer or self._pending_offer[0] != from_user:
            return
        _, payload = self._pending_offer
        self._pending_offer = None
        try:
            await self.call_manager.handle_offer(from_user, payload)
        except Exception as e:
            print(f"[calling] offer verification/handling failed: {e}")
            Clock.schedule_once(lambda _dt: self._show_call_security_warning())

    def _show_call_security_warning(self):
        content = BoxLayout(orientation="vertical", spacing=10, padding=10)
        flat_bg(content, COL_BG_PANEL)
        content.add_widget(Label(
            text="This call's encryption could not be verified against the "
                 "other person's known identity key. It was ended -- this "
                 "may mean the server is tampering with the call.",
            color=COL_TEXT_MAIN,
        ))
        popup = Popup(
            title="Call security warning", content=content,
            size_hint=(0.85, 0.5),
            title_color=COL_DANGER_BRIGHT, separator_color=COL_DANGER_BRIGHT,
        )
        close_btn = GlassButton(text="OK", accent=True, size_hint=(1, 0.3))
        close_btn.bind(on_release=lambda *_: popup.dismiss())
        content.add_widget(close_btn)
        popup.open()

    def _on_call_state(self, state_str):
        Clock.schedule_once(
            lambda _dt: hasattr(self, "chat_screen") and self.chat_screen.on_call_state(state_str)
        )

    def _on_call_ended(self):
        Clock.schedule_once(
            lambda _dt: hasattr(self, "chat_screen") and self.chat_screen.on_call_ended()
        )

    def show_chat_screen(self):
        self.chat_screen = ChatScreen(self, name="chat")
        self.sm.add_widget(self.chat_screen)
        self.sm.current = "chat"
        self.bridge.run_coro(self.session.list_contacts())

    def send_message(self, peer_id, text):
        async def do_send():
            try:
                await self.session.send_to_peer(peer_id, text)
            except Exception as e:
                print(f"[send error] {e}")
        self.bridge.run_coro(do_send())


if __name__ == "__main__":
    SecApp().run()