"""界面基础组件。"""

from __future__ import annotations

from typing import Callable

from PIL import Image
from PySide6.QtCore import QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .imaging import OLED_H, OLED_W


class Logo(QWidget):
    """应用图标：一块点亮的 OLED 屏幕。"""

    def __init__(self, size: int = 30, parent: QWidget | None = None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), 8, 8)
        painter.fillPath(path, QColor("#14181E"))
        cell = self._size / 10
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        lit = [(2, 2), (3, 2), (6, 2), (7, 2), (2, 3), (5, 3), (7, 3), (4, 4), (5, 4), (6, 4),
               (2, 6), (3, 6), (6, 6), (7, 6), (2, 7), (3, 7), (5, 7), (7, 7)]
        for cx, cy in lit:
            painter.drawRoundedRect(cx * cell, cy * cell, cell * 0.72, cell * 0.72, 1.2, 1.2)
        painter.end()


class Chip(QFrame):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Chip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 4, 11, 4)
        layout.setSpacing(6)
        self._dot = QLabel()
        self._dot.setFixedSize(7, 7)
        self._text = QLabel(text)
        self._text.setStyleSheet("font-size:12px;")
        layout.addWidget(self._dot)
        layout.addWidget(self._text)
        self.set_state(None)

    def set_state(self, state: str | None) -> None:
        color = {"ok": theme.OK, "warn": theme.WARN, "err": theme.ERR}.get(state or "", "#AEB6C2")
        self._dot.setStyleSheet(f"background:{color}; border-radius:3px;")
        if state == "err":
            self.setStyleSheet("QFrame#Chip{border-color:#F3C6C6;background:#FDF5F5;}")
        elif state == "warn":
            self.setStyleSheet("QFrame#Chip{border-color:#F0DAB4;background:#FEFAF3;}")
        else:
            self.setStyleSheet("QFrame#Chip{border-color:#E3E7ED;background:#FFFFFF;}")

    def set_text(self, text: str) -> None:
        self._text.setText(text)


class Card(QFrame):
    """白底圆角卡片，带标题行。"""

    def __init__(self, title: str = "", parent: QWidget | None = None, spacing: int = 10):
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 12)
        outer.setSpacing(8)
        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        self.header.addWidget(self.title)
        self.header.addStretch(1)
        if title:
            outer.addLayout(self.header)
        self.body = QVBoxLayout()
        self.body.setSpacing(spacing)
        outer.addLayout(self.body)

    def add(self, widget: QWidget) -> QWidget:
        self.body.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self.body.addLayout(layout)


class DropArea(QFrame):
    picked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(100)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        self.setStyleSheet(
            "QFrame{background:#FAFBFD;border:1.5px dashed #CBD5E1;border-radius:11px;}"
        )

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.setStyleSheet("QFrame{background:#F4F8FF;border:1.5px dashed #2E6BFF;border-radius:11px;}")
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.setStyleSheet("QFrame{background:#FAFBFD;border:1.5px dashed #CBD5E1;border-radius:11px;}")
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.picked.emit()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() / 2
        # 圆形加号
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#EAF0FF"))
        painter.drawEllipse(int(cx - 15), 12, 30, 30)
        pen = QPen(QColor(theme.ACCENT), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(cx - 6), 27, int(cx + 6), 27)
        painter.drawLine(int(cx), 21, int(cx), 33)

        font = QFont(self.font())
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(0, 50, self.width(), 20, Qt.AlignmentFlag.AlignHCenter, "拖入图片 / GIF，或点击选择")

        font2 = QFont(self.font())
        font2.setPointSize(8)
        painter.setFont(font2)
        painter.setPen(QColor("#8A929E"))
        painter.drawText(0, 70, self.width(), 18, Qt.AlignmentFlag.AlignHCenter, "PNG · JPG · BMP · WEBP · GIF")
        painter.end()


class OledView(QWidget):
    """按整数倍缩放的 128x64 单色预览，自带深色舞台背景。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._data: bytes | None = None
        self._grid = False
        self._zoom_limit = 8
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_mono(self, mono: Image.Image | None) -> None:
        self._data = mono.convert("L").tobytes() if mono is not None else None
        self.update()

    def set_grid(self, enabled: bool) -> None:
        self._grid = enabled
        self.update()

    def set_zoom_limit(self, zoom: int) -> None:
        self._zoom_limit = zoom
        self.update()

    def _image(self) -> QImage | None:
        if not self._data:
            return None
        image = QImage(self._data, OLED_W, OLED_H, OLED_W, QImage.Format.Format_Grayscale8)
        return image.copy()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), 14, 14)
        painter.fillPath(path, QColor(theme.STAGE))
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        if self._data is None:
            painter.setPen(QPen(QColor("#2A303A"), 1, Qt.PenStyle.DashLine))
            inner = rect.adjusted(18, 18, -18, -18)
            painter.drawRoundedRect(inner, 8, 8)
            painter.setPen(QColor("#5A6472"))
            font = QFont(self.font())
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(inner, Qt.AlignmentFlag.AlignCenter, "导入图片后，这里会显示 128×64 的实际效果")
            painter.end()
            return

        available_w = self.width() - 32
        available_h = self.height() - 32
        zoom = max(1, min(self._zoom_limit, int(min(available_w / OLED_W, available_h / OLED_H))))
        draw_w, draw_h = zoom * OLED_W, zoom * OLED_H
        x = (self.width() - draw_w) // 2
        y = (self.height() - draw_h) // 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#000000"))
        painter.drawRect(x, y, draw_w, draw_h)

        image = self._image()
        if image is not None:
            painter.drawImage(QRectF(x, y, draw_w, draw_h), image)

        if self._grid and zoom >= 4:
            painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
            for col in range(1, OLED_W):
                painter.drawLine(x + col * zoom, y, x + col * zoom, y + draw_h)
            for row in range(1, OLED_H):
                painter.drawLine(x, y + row * zoom, x + draw_w, y + row * zoom)

        painter.setPen(QPen(QColor("#2A303A"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(x, y, draw_w, draw_h)
        painter.end()


def QRectFCompat(x, y, w, h):
    return QRectF(x, y, w, h)


def mono_pixmap(mono: Image.Image, width: int = 64, height: int = 32) -> QPixmap:
    data = mono.convert("L").tobytes()
    image = QImage(data, OLED_W, OLED_H, OLED_W, QImage.Format.Format_Grayscale8).copy()
    image = image.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.FastTransformation)
    return QPixmap.fromImage(image)


class ParamSlider(QWidget):
    """标签 + 数值 + 滑块的紧凑控件。"""

    valueChanged = Signal(int)

    def __init__(self, label: str, minimum: int, maximum: int, value: int,
                 suffix: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._suffix = suffix
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel(label)
        self._label.setObjectName("FieldLabel")
        self._value = QLabel()
        self._value.setObjectName("Hint")
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self._label)
        top.addStretch(1)
        top.addWidget(self._value)
        layout.addLayout(top)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(minimum, maximum)
        self._slider.setValue(value)
        self._slider.valueChanged.connect(self._on_change)
        layout.addWidget(self._slider)
        self._update_text(value)

    def _on_change(self, value: int) -> None:
        self._update_text(value)
        self.valueChanged.emit(value)

    def _update_text(self, value: int) -> None:
        self._value.setText(f"{value}{self._suffix}")

    def value(self) -> int:
        return self._slider.value()

    def set_value(self, value: int) -> None:
        blocked = self._slider.blockSignals(True)
        self._slider.setValue(value)
        self._slider.blockSignals(blocked)
        self._update_text(self._slider.value())


class Segmented(QFrame):
    changed = Signal(str)

    def __init__(self, items: list[tuple[str, str]], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for index, (key, text) in enumerate(items):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(index == 0)
            button.clicked.connect(lambda _checked=False, k=key: self.changed.emit(k))
            self._group.addButton(button)
            layout.addWidget(button)
            self._buttons[key] = button
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_current(self, key: str) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)


class TaskThread(QThread):
    """在后台执行耗时任务，期间把日志逐行发回界面。"""

    line = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, work: Callable[[Callable[[str], None]], object], parent: QWidget | None = None):
        super().__init__(parent)
        self._work = work

    def run(self) -> None:  # noqa: D401
        try:
            result = self._work(self.line.emit)
            self.done.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class StatBlock(QWidget):
    def __init__(self, label: str, value: str = "—", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._value = QLabel(value)
        self._value.setObjectName("StatValue")
        caption = QLabel(label)
        caption.setObjectName("Hint")
        layout.addWidget(self._value)
        layout.addWidget(caption)

    def set_value(self, text: str) -> None:
        self._value.setText(text)


def elide(text: str, limit: int = 26) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def icon_pixmap(mono: Image.Image) -> QPixmap:
    return mono_pixmap(mono)


__all__ = [
    "Card", "Chip", "Divider", "DropArea", "Logo", "OledView", "ParamSlider",
    "Segmented", "StatBlock", "TaskThread", "elide", "icon_pixmap", "mono_pixmap", "QSize",
]
