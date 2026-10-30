"""界面配色与样式表。"""

from __future__ import annotations

from .paths import ICON_DIR

ACCENT = "#2E6BFF"
ACCENT_DARK = "#1F55D8"
TEXT = "#1B2027"
MUTED = "#7A828E"
BORDER = "#E3E7ED"
PANEL = "#FFFFFF"
BG = "#F2F4F7"
OK = "#12A150"
WARN = "#C2760A"
ERR = "#D93B3B"
STAGE = "#0A0C10"


def qss() -> str:
    check = (ICON_DIR / "check.svg").as_posix()
    chevron = (ICON_DIR / "chevron-down.svg").as_posix()
    return f"""
* {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
#Root {{
    background: {BG};
}}
QToolTip {{
    background: #22262E;
    color: #F2F4F7;
    border: none;
    padding: 5px 8px;
    border-radius: 6px;
}}

/* ---------- 卡片 ---------- */
QFrame#Card {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#Card QFrame#Card {{
    border: none;
    background: transparent;
}}
QLabel#CardTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel#Hint {{
    color: {MUTED};
    font-size: 11.5px;
}}
QLabel#FieldLabel {{
    color: #5A626D;
    font-size: 12px;
}}
QFrame#Divider {{
    background: {BORDER};
    border: none;
    max-height: 1px;
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    border-radius: 8px;
    padding: 7px 12px;
    background: #F4F6F9;
    border: 1px solid transparent;
}}
QPushButton:hover {{
    background: #EAEEF5;
}}
QPushButton:pressed {{
    background: #DFE5EF;
}}
QPushButton#Primary {{
    background: {ACCENT};
    color: #FFFFFF;
    font-weight: 600;
    padding: 11px 14px;
    font-size: 13.5px;
}}
QPushButton#Primary:hover {{
    background: {ACCENT_DARK};
}}
QPushButton#Primary:disabled {{
    background: #B7C5E8;
    color: #F4F7FF;
}}
QPushButton#Dark {{
    background: #1B2027;
    color: #FFFFFF;
    font-weight: 600;
    padding: 10px 14px;
}}
QPushButton#Dark:hover {{
    background: #2A303A;
}}
QPushButton#Dark:disabled {{
    background: #C3C8D0;
    color: #F2F4F7;
}}
QPushButton#Ghost {{
    background: #FFFFFF;
    border: 1px solid #DCE1E8;
    color: #3C434C;
}}
QPushButton#Ghost:hover {{
    background: #F5F7FA;
    border-color: #C9D1DD;
}}
QPushButton#Ghost:checked {{
    background: #EAF0FF;
    border-color: #B9CBFB;
    color: {ACCENT_DARK};
    font-weight: 600;
}}
QPushButton#Link {{
    background: transparent;
    border: none;
    color: {ACCENT};
    padding: 4px 2px;
    text-align: left;
}}
QPushButton#Link:hover {{
    color: {ACCENT_DARK};
}}

/* ---------- 输入控件 ---------- */
QComboBox, QLineEdit, QSpinBox {{
    background: #FFFFFF;
    border: 1px solid #DCE1E8;
    border-radius: 8px;
    padding: 6px 8px;
    min-height: 18px;
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
}}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover {{
    border-color: #C6CEDA;
}}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: url({chevron});
    width: 12px;
    height: 12px;
}}
QComboBox QAbstractItemView {{
    background: #FFFFFF;
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: #EAF0FF;
    selection-color: {TEXT};
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 16px;
    border: none;
    background: transparent;
}}
QCheckBox {{
    spacing: 8px;
    color: #3C434C;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid #C9D0DA;
    border-radius: 5px;
    background: #FFFFFF;
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url({check});
}}

/* ---------- 滑块 ---------- */
QSlider::groove:horizontal {{
    height: 4px;
    background: #E3E7ED;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 13px;
    height: 13px;
    margin: -5px 0;
    border-radius: 7px;
    background: #FFFFFF;
    border: 2px solid {ACCENT};
}}
QSlider::handle:horizontal:hover {{
    background: #EAF0FF;
}}

/* ---------- 列表 ---------- */
QListWidget {{
    background: #FAFBFC;
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 4px;
    border-radius: 8px;
    margin: 1px 0;
}}
QListWidget::item:selected {{
    background: #EAF0FF;
    color: {TEXT};
}}
QListWidget::item:hover {{
    background: #F1F4F9;
}}

/* ---------- 滚动条 ---------- */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px 2px 2px 0;
}}
QScrollBar::handle:vertical {{
    background: #CDD4DE;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #B4BDCA;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: #CDD4DE;
    border-radius: 4px;
    min-width: 30px;
}}

/* ---------- 舞台 / 日志 ---------- */
QFrame#Stage {{
    background: {STAGE};
    border-radius: 14px;
}}
QTextEdit#Log {{
    background: #0E1116;
    border: none;
    border-radius: 10px;
    color: #C3CCD7;
    font-family: "Consolas", "Cascadia Mono", monospace;
    font-size: 12px;
    padding: 8px 10px;
}}
QPlainTextEdit#Code {{
    background: #0E1116;
    border: none;
    border-radius: 10px;
    color: #C3CCD7;
    font-family: "Consolas", "Cascadia Mono", monospace;
    font-size: 12px;
    padding: 10px;
    selection-background-color: #2E6BFF;
}}

/* ---------- 其他 ---------- */
QProgressBar {{
    background: #E8ECF2;
    border: none;
    border-radius: 2px;
    height: 4px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 2px;
}}
QLabel#Chip {{
    background: #FFFFFF;
    border: 1px solid {BORDER};
    border-radius: 11px;
    padding: 4px 10px;
    color: #4B5563;
    font-size: 12px;
}}
QFrame#TopBar {{
    background: #FFFFFF;
    border-bottom: 1px solid {BORDER};
}}
QLabel#AppTitle {{
    font-size: 16px;
    font-weight: 700;
    color: #14181E;
}}
QLabel#AppSub {{
    font-size: 11.5px;
    color: {MUTED};
}}
QFrame#Segmented {{
    background: #F1F3F7;
    border-radius: 9px;
    border: 1px solid #E7EBF1;
}}
QFrame#Segmented QPushButton {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 6px 11px;
    color: #5A626D;
}}
QFrame#Segmented QPushButton:checked {{
    background: #FFFFFF;
    color: {TEXT};
    font-weight: 600;
}}
QLabel#StatValue {{
    font-size: 15px;
    font-weight: 600;
    color: {TEXT};
}}
"""
