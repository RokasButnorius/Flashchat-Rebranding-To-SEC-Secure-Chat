"""
client-desktop/assets.py

Icons from source/icons/, sounds from source/sounds/.
Sounds DISABLED for now.

Put emoji-style PNGs in source/icons/ with these names:
  settings, call, send, search, online, offline, group, add, wipe,
  avatar_default, avatar_red_fox, avatar_blue_wolf, avatar_green_frog,
  avatar_purple_owl, avatar_orange_cat, avatar_teal_bear, avatar_pink_bunny,
  avatar_yellow_duck,
  reaction_thumbs, reaction_heart, reaction_laugh
"""

from pathlib import Path

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt

SOURCE_DIR = Path(__file__).parent / "source"
ICONS_DIR = SOURCE_DIR / "icons"
SOUNDS_DIR = SOURCE_DIR / "sounds"

_ICON_EXTS = (".png", ".jpg", ".jpeg", ".svg")

_icon_cache: dict[str, QIcon | None] = {}
_pixmap_cache: dict[str, QPixmap | None] = {}


def icon(name: str) -> QIcon | None:
    if name in _icon_cache:
        return _icon_cache[name]
    found = None
    for ext in _ICON_EXTS:
        p = ICONS_DIR / f"{name}{ext}"
        if p.exists():
            found = QIcon(str(p))
            break
    _icon_cache[name] = found
    return found


def pixmap(name: str, size: int | None = None) -> QPixmap | None:
    cache_key = f"{name}:{size}"
    if cache_key in _pixmap_cache:
        return _pixmap_cache[cache_key]
    found = None
    for ext in _ICON_EXTS:
        p = ICONS_DIR / f"{name}{ext}"
        if p.exists():
            pm = QPixmap(str(p))
            if size and not pm.isNull():
                pm = pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            found = pm
            break
    _pixmap_cache[cache_key] = found
    return found


def avatar_icon(avatar_id: str) -> QIcon | None:
    return icon(f"avatar_{avatar_id}")


def avatar_pixmap(avatar_id: str, size: int = 36) -> QPixmap | None:
    return pixmap(f"avatar_{avatar_id}", size=size)


class _SilentSound:
    def stop(self):
        pass


def play_sound(name: str):
    return None


def play_looping(name: str) -> _SilentSound:
    return _SilentSound()