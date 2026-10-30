"""运行目录与资源目录（兼容 PyInstaller 打包后的路径）。"""

from __future__ import annotations

import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

# 可写目录：配置、输出工程都放这里
if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent

# 只读资源目录：模板工程、图标
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))

TEMPLATE_DIR = RESOURCE_DIR / "assets" / "template"
ICON_DIR = RESOURCE_DIR / "assets" / "icons"
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_OUTPUT = APP_DIR / "输出"
