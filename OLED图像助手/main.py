"""OLED 图像助手 入口。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QIcon, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.main_window import MainWindow  # noqa: E402
from app.paths import APP_DIR, RESOURCE_DIR  # noqa: E402
from app.widgets import Logo  # noqa: E402


def _install_excepthook() -> None:
    """打包成 exe 后没有控制台，出错时把堆栈写到文件里方便排查。"""
    import traceback

    def hook(exc_type, exc_value, exc_tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            (APP_DIR / "错误日志.txt").write_text(text, encoding="utf-8")
        except OSError:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = hook


def _app_icon() -> QIcon:
    icon_path = RESOURCE_DIR / "assets" / "app.png"
    if icon_path.is_file():
        return QIcon(str(icon_path))
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    Logo(64).render(pixmap)
    return QIcon(pixmap)


def main() -> int:
    _install_excepthook()
    app = QApplication(sys.argv)
    app.setApplicationName("OLED 图像助手")
    app.setApplicationDisplayName("OLED 图像助手")
    app.setWindowIcon(_app_icon())

    window = MainWindow()
    window.show()

    args = sys.argv[1:]
    if "--demo" in args:
        demo_dir = Path(__file__).resolve().parent.parent / "取模工具" / "月薪喵"
        if demo_dir.is_dir():
            window.add_paths(sorted(demo_dir.glob("frame_00*.bmp"))[:4])
    if "--screenshot" in args:
        target = Path(args[args.index("--screenshot") + 1]).resolve()

        def capture() -> None:
            window.grab().save(str(target))
            app.quit()

        QTimer.singleShot(1500, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
