"""client-desktop/theme.py -- SEC glass UI, blue accents matched to logo."""

BG_DEEPEST = "#0b1220"
BG_SIDEBAR = "rgba(20, 40, 70, 180)"
BG_PANEL = "rgba(18, 35, 60, 160)"
BG_INPUT = "rgba(30, 55, 95, 200)"
BG_HOVER = "rgba(40, 75, 130, 220)"
BG_GLASS = "rgba(25, 50, 90, 140)"
ACCENT = "#1e90ff"
ACCENT_BRIGHT = "#4fc3ff"
ACCENT_DIM = "#0d4f8a"
ACCENT_GLOW = "rgba(30, 144, 255, 80)"
ONLINE = "#3dd68c"
TEXT_MAIN = "#e8f1ff"
TEXT_MUTED = "#8aa4c8"
TEXT_DIM = "#5a7399"
BORDER = "rgba(80, 150, 255, 55)"
BORDER_STRONG = "rgba(100, 180, 255, 120)"

STYLESHEET = f"""
QWidget {{
    background-color: {BG_DEEPEST};
    color: {TEXT_MAIN};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
    outline: none;
}}
QMainWindow {{
    background-color: {BG_DEEPEST};
}}

#Sidebar {{
    background-color: rgba(15, 30, 55, 210);
    border-right: 1px solid {BORDER};
}}
#ChatPanel {{
    background-color: rgba(12, 22, 40, 230);
}}
#ChatHeader {{
    background-color: rgba(18, 35, 65, 200);
    border-bottom: 1px solid {BORDER};
}}

QLineEdit, QTextEdit {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 12px;
    color: {TEXT_MAIN};
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 1px solid {ACCENT_BRIGHT};
    background-color: rgba(35, 65, 110, 230);
}}

QPushButton {{
    background-color: rgba(35, 60, 100, 200);
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 14px;
    color: {TEXT_MAIN};
}}
QPushButton:hover {{
    background-color: {BG_HOVER};
    border: 1px solid {BORDER_STRONG};
}}
QPushButton:pressed {{
    background-color: {ACCENT_DIM};
    border: 1px solid {ACCENT};
}}
QPushButton:disabled {{
    background-color: rgba(30, 40, 55, 150);
    color: {TEXT_DIM};
}}

QPushButton#AccentButton {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT_BRIGHT};
    font-weight: 600;
    color: white;
}}
QPushButton#AccentButton:hover {{
    background-color: {ACCENT_BRIGHT};
    border: 1px solid #9ee0ff;
}}

QPushButton#DangerButton {{
    background-color: rgba(160, 40, 40, 200);
    border: 1px solid #e05555;
    font-weight: 600;
}}
QPushButton#DangerButton:hover {{
    background-color: #dc2626;
    border: 1px solid #ff7070;
}}

QPushButton#IconButton {{
    background-color: rgba(35, 60, 100, 180);
    border: 1px solid {BORDER};
    border-radius: 18px;
    min-width: 36px; max-width: 36px;
    min-height: 36px; max-height: 36px;
    padding: 4px;
}}
QPushButton#IconButton:hover {{
    background-color: {BG_HOVER};
    border: 1px solid {ACCENT};
}}

QPushButton#ReactionButton {{
    background-color: rgba(35, 60, 100, 180);
    border: 1px solid {BORDER};
    border-radius: 10px;
    min-width: 40px; max-width: 40px;
    min-height: 36px; max-height: 36px;
    padding: 4px;
}}
QPushButton#ReactionButton:hover {{
    background-color: {BG_HOVER};
    border: 1px solid {ACCENT};
}}

QPushButton#DevButton {{
    background-color: transparent;
    border: 1px solid rgba(80, 150, 255, 40);
    border-radius: 6px;
    color: {TEXT_DIM};
    font-size: 10px;
    padding: 2px 8px;
    min-height: 18px;
    max-height: 22px;
}}
QPushButton#DevButton:hover {{
    color: {ACCENT_BRIGHT};
    border: 1px solid {BORDER};
}}

QListWidget {{
    background-color: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    padding: 8px;
    border-radius: 8px;
    margin: 1px 4px;
    border: none;
}}
QListWidget::item:hover {{
    background-color: rgba(40, 75, 130, 160);
}}
QListWidget::item:selected {{
    background-color: {ACCENT};
    color: white;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: rgba(80, 140, 220, 120);
    border-radius: 4px;
    min-height: 24px;
    border: none;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; border: none; background: none; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QLabel#SectionLabel {{
    color: {TEXT_DIM};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    background: transparent;
}}
QLabel#PeerName {{ font-size: 15px; font-weight: 700; background: transparent; }}
QLabel#PeerSub {{ color: {TEXT_MUTED}; font-size: 11px; background: transparent; }}
QLabel#DevBadge {{
    background-color: {ACCENT};
    color: white;
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 10px;
    font-weight: 700;
}}
QLabel#LiveNotice {{
    background-color: rgba(30, 144, 255, 230);
    color: white;
    border-radius: 0px;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 600;
}}
QLabel {{ background: transparent; }}

QDialog {{
    background-color: rgba(14, 28, 50, 245);
    border: 1px solid {BORDER};
}}

QComboBox {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 10px;
}}
QComboBox:hover {{
    background-color: {BG_HOVER};
    border: 1px solid {BORDER_STRONG};
}}
QComboBox::drop-down {{
    border: none;
    background: transparent;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: rgba(20, 40, 70, 250);
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    outline: none;
}}

QCheckBox {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border-radius: 4px;
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT_BRIGHT};
}}

QMessageBox {{ background-color: rgba(14, 28, 50, 250); }}
QInputDialog {{ background-color: rgba(14, 28, 50, 250); }}

#DevPanel {{
    background-color: rgba(10, 25, 50, 230);
    border-left: 1px solid {BORDER};
}}
"""


def avatar_color(user_id: str) -> str:
    palette = [ACCENT, "#4fc3ff", "#3dd68c", "#f0b232", "#9b59b6", "#1abc9c", "#e67e22"]
    return palette[sum(ord(c) for c in user_id) % len(palette)]


AVATAR_EMOJI = {
    "default": "🙂", "red_fox": "🦊", "blue_wolf": "🐺", "green_frog": "🐸",
    "purple_owl": "🦉", "orange_cat": "🐱", "teal_bear": "🐻", "pink_bunny": "🐰",
    "yellow_duck": "🦆",
}