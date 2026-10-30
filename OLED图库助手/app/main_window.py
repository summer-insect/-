"""主窗口。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import codegen, imaging, theme, toolchain
from .paths import DEFAULT_OUTPUT, CONFIG_PATH
from .imaging import Frame, RenderOptions
from .widgets import Card, Chip, Divider, DropArea, Logo, OledView, ParamSlider, Segmented, StatBlock, TaskThread, mono_pixmap

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff"}
MAX_GIF_FRAMES = 40


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OLED 图库助手 · EC11 旋转切图（不自动播放）· 128×64")
        self.setMinimumSize(1060, 660)
        self.setAcceptDrops(True)
        self._fit_to_screen()

        self.frames: list[Frame] = []
        self.current = 0
        self.output_root = DEFAULT_OUTPUT
        self.project_name = "OLED_Gallery"
        self.uv4: Path | None = toolchain.find_uv4()
        self.pack_version = toolchain.best_pack_version(self.uv4)
        self.last_result: codegen.GenerateResult | None = None
        self.thread: TaskThread | None = None
        self._busy = False
        self._loading = False
        self._dirty = True
        self._last_dir = str(Path.home())
        self._build_ui()
        self._apply_theme()
        self._load_config()
        self._refresh_keil_chip()
        self._update_pin_warnings()
        self._refresh_frames()
        self._refresh_preview()
        self._log("欢迎使用 OLED 图库助手，导入多张图片后烧录，旋转 EC11 即可切换。", "ok")
        QTimer.singleShot(0, self._apply_responsive)

    # ------------------------------------------------------------------ 界面
    def _fit_to_screen(self) -> None:
        """按当前屏幕可用空间决定窗口大小，避免小屏幕上被裁切。"""
        from PySide6.QtGui import QCursor, QGuiApplication

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        width = max(1060, min(1400, available.width() - 48))
        height = max(660, min(880, available.height() - 48))
        self.resize(width, height)
        self.move(available.x() + (available.width() - width) // 2,
                  available.y() + max(0, (available.height() - height) // 2))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive()

    def _apply_responsive(self) -> None:
        width = self.width()
        if hasattr(self, "device_chip"):
            self.device_chip.setVisible(width >= 1240)
            self.chip_mode.setVisible(width >= 1100)
            self.chip_state.setVisible(width >= 1060)
        if hasattr(self, "stack") and hasattr(self, "stat_size"):
            center_width = self.stack.width()
            self.stat_size.setVisible(center_width >= 430)
            self.export_button.setVisible(center_width >= 470)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._top_bar())

        body = QHBoxLayout()
        body.setContentsMargins(16, 14, 16, 10)
        body.setSpacing(12)
        body.addWidget(self._left_panel())
        body.addWidget(self._center_panel(), 1)
        body.addWidget(self._right_panel())
        outer.addLayout(body, 1)

        outer.addWidget(self._log_panel())
        outer.addWidget(self._status_bar())

        for sequence, slot in (("Ctrl+O", self._pick_images),
                               ("Ctrl+G", self._generate_and_report),
                               ("F5", self._generate_and_flash),
                               ("Ctrl+L", lambda: self.log_view.clear())):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(slot)

        delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.frame_list)
        delete_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete_shortcut.activated.connect(self._remove_frame)

    def _top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(64)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 0, 18, 0)
        layout.setSpacing(10)
        layout.addWidget(Logo(30))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("OLED 图库助手")
        title.setObjectName("AppTitle")
        sub = QLabel("SSD1306 · 128×64 · 多图存 Flash · 转 EC11 才换图，不会自动播放")
        sub.setObjectName("AppSub")
        titles.addWidget(title)
        titles.addWidget(sub)
        layout.addLayout(titles)
        layout.addStretch(1)
        self.chip_mode = Chip("EC11 手动切图")
        self.chip_mode.setToolTip("本软件生成的固件不会自动轮播：上电显示第 1 张，只有转动编码器才换图")
        layout.addWidget(self.chip_mode)
        self.device_chip = Chip("STM32F103C8T6")
        layout.addWidget(self.device_chip)
        self.chip_keil = Chip("Keil 检测中")
        layout.addWidget(self.chip_keil)
        self.chip_state = Chip("尚未生成工程")
        layout.addWidget(self.chip_state)
        return bar

    def _left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(308)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(10)

        # 导入
        import_card = Card("导入图片")
        self.drop = DropArea()
        self.drop.picked.connect(self._pick_images)
        import_card.add(self.drop)
        row = QHBoxLayout()
        row.setSpacing(8)
        pick = QPushButton("选择文件")
        pick.setObjectName("Ghost")
        pick.clicked.connect(self._pick_images)
        self.pick_button = pick
        self.pick_button = pick
        clear = QPushButton("清空")
        clear.setObjectName("Ghost")
        clear.clicked.connect(self._clear_frames)
        row.addWidget(pick, 1)
        row.addWidget(clear)
        import_card.add_layout(row)
        layout.addWidget(import_card)

        # 图库
        self.frames_card = Card("图库图片")
        self.frame_list = QListWidget()
        self.frame_list.setIconSize(QSize(64, 32))
        self.frame_list.setFixedHeight(156)
        self.frame_list.currentRowChanged.connect(self._on_frame_selected)
        self.frames_card.add(self.frame_list)

        self.capacity_bar = QProgressBar()
        self.capacity_bar.setTextVisible(False)
        self.capacity_bar.setFixedHeight(6)
        self.capacity_bar.setRange(0, codegen.MAX_IMAGES)
        self.capacity_bar.setValue(0)
        self.frames_card.add(self.capacity_bar)

        self.capacity_label = QLabel("")
        self.capacity_label.setObjectName("Hint")
        self.capacity_label.setWordWrap(True)
        self.frames_card.add(self.capacity_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        for text, slot in (("上移", lambda: self._move_frame(-1)), ("下移", lambda: self._move_frame(1)),
                           ("删除", self._remove_frame)):
            button = QPushButton(text)
            button.setObjectName("Ghost")
            button.clicked.connect(slot)
            buttons.addWidget(button)
        self.frames_card.add_layout(buttons)
        self.frames_hint = QLabel("")
        self.frames_hint.setObjectName("Hint")
        self.frames_card.header.addWidget(self.frames_hint)
        self.frames_card.setVisible(False)
        layout.addWidget(self.frames_card)

        layout.addWidget(self._tone_card())
        layout.addWidget(self._geometry_card())
        layout.addStretch(1)
        scroll.setWidget(container)
        return scroll

    def _tone_card(self) -> QWidget:
        """最常调的两件事：怎么二值化、阈值多少。"""
        card = Card("黑白取模")
        method_row = QHBoxLayout()
        method_row.setSpacing(8)
        method_label = QLabel("取模方式")
        method_label.setObjectName("FieldLabel")
        self.method_combo = QComboBox()
        for key in (imaging.METHOD_THRESHOLD, imaging.METHOD_BAYER, imaging.METHOD_FLOYD, imaging.METHOD_MEAN):
            self.method_combo.addItem(imaging.METHOD_LABELS[key], key)
        self.method_combo.setToolTip("阈值：纯色块；抖动：保留灰度层次；自适应：背景复杂的图")
        self.method_combo.currentIndexChanged.connect(self._on_params_changed)
        method_row.addWidget(method_label)
        method_row.addWidget(self.method_combo, 1)
        card.add_layout(method_row)

        self.threshold_slider = ParamSlider("阈值", 0, 255, 128)
        self.threshold_slider.valueChanged.connect(self._on_params_changed)
        card.add(self.threshold_slider)

        auto_row = QHBoxLayout()
        auto_row.setSpacing(8)
        self.threshold_hint = QLabel("阈值越低，点亮区域越少")
        self.threshold_hint.setObjectName("Hint")
        auto_button = QPushButton("自动取阈值")
        auto_button.setObjectName("Ghost")
        auto_button.setFixedHeight(26)
        auto_button.clicked.connect(self._auto_threshold)
        auto_row.addWidget(self.threshold_hint, 1)
        auto_row.addWidget(auto_button)
        card.add_layout(auto_row)

        self.invert_check = QCheckBox("反色（黑白反转）")
        self.invert_check.toggled.connect(self._on_params_changed)
        card.add(self.invert_check)

        self.sharpen_slider = ParamSlider("清晰度", 0, 100, 60)
        self.sharpen_slider.setToolTip(
            "大图缩到 128×64 时，细线和文字会被平均成浅灰而消失。"
            "调高会在缩放后做反锐化，把轮廓和细节拉回阈值以内；"
            "照片调到 30~60 已够，线稿/文字可到 80；0 = 关闭，最柔和。")
        self.sharpen_slider.valueChanged.connect(self._on_params_changed)
        card.add(self.sharpen_slider)

        self.autocrop_check = QCheckBox("自动裁掉白边")
        self.autocrop_check.setChecked(True)
        self.autocrop_check.toggled.connect(self._on_params_changed)
        self.nearest_check = QCheckBox("像素画模式（不插值）")
        self.nearest_check.toggled.connect(self._on_params_changed)
        return card

    def _geometry_card(self) -> QWidget:
        card = Card("画面调整")
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel("适应方式")
        label.setObjectName("FieldLabel")
        self.fit_combo = QComboBox()
        self.fit_combo.addItem("等比适应（完整显示）", "fit")
        self.fit_combo.addItem("裁剪填满（铺满屏幕）", "fill")
        self.fit_combo.addItem("拉伸铺满（会变形）", "stretch")
        self.fit_combo.currentIndexChanged.connect(self._on_params_changed)
        row.addWidget(label)
        row.addWidget(self.fit_combo, 1)
        card.add_layout(row)

        self.scale_slider = ParamSlider("缩放", 20, 150, 100, "%")
        self.scale_slider.valueChanged.connect(self._on_params_changed)
        card.add(self.scale_slider)

        offset_row = QHBoxLayout()
        offset_row.setSpacing(6)
        ox_label = QLabel("水平偏移")
        ox_label.setObjectName("FieldLabel")
        self.offset_x = QSpinBox()
        self.offset_x.setRange(-64, 64)
        self.offset_x.setFixedWidth(76)
        self.offset_x.valueChanged.connect(self._on_params_changed)
        oy_label = QLabel("垂直")
        oy_label.setObjectName("FieldLabel")
        self.offset_y = QSpinBox()
        self.offset_y.setRange(-32, 32)
        self.offset_y.setFixedWidth(76)
        self.offset_y.valueChanged.connect(self._on_params_changed)
        offset_row.addWidget(ox_label)
        offset_row.addWidget(self.offset_x)
        offset_row.addWidget(oy_label)
        offset_row.addWidget(self.offset_y)
        card.add_layout(offset_row)

        rotate_row = QHBoxLayout()
        rotate_row.setSpacing(8)
        rotate_label = QLabel("旋转")
        rotate_label.setObjectName("FieldLabel")
        self.rotate_combo = QComboBox()
        for text, value in (("0°", 0), ("90°", 90), ("180°", 180), ("270°", 270)):
            self.rotate_combo.addItem(text, value)
        self.rotate_combo.currentIndexChanged.connect(self._on_params_changed)
        rotate_row.addWidget(rotate_label)
        rotate_row.addWidget(self.rotate_combo, 1)
        card.add_layout(rotate_row)

        mirror_row = QHBoxLayout()
        mirror_row.setSpacing(16)
        self.flip_h = QCheckBox("水平镜像")
        self.flip_h.toggled.connect(self._on_params_changed)
        self.flip_v = QCheckBox("垂直镜像")
        self.flip_v.toggled.connect(self._on_params_changed)
        mirror_row.addWidget(self.flip_h)
        mirror_row.addWidget(self.flip_v)
        mirror_row.addStretch(1)
        card.add_layout(mirror_row)
        card.add(self.autocrop_check)
        card.add(self.nearest_check)

        card.add(Divider())
        self.brightness_slider = ParamSlider("亮度", -100, 100, 0)
        self.brightness_slider.valueChanged.connect(self._on_params_changed)
        card.add(self.brightness_slider)
        self.contrast_slider = ParamSlider("对比度", -100, 100, 0)
        self.contrast_slider.valueChanged.connect(self._on_params_changed)
        card.add(self.contrast_slider)

        reset = QPushButton("恢复默认参数")
        reset.setObjectName("Link")
        reset.clicked.connect(self._reset_params)
        card.add(reset)
        return card

    def _center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.segmented = Segmented([("image", "位图预览"), ("code", "代码预览")])
        self.segmented.changed.connect(self._switch_view)
        toolbar.addWidget(self.segmented)
        toolbar.addStretch(1)
        self.grid_check = QCheckBox("网格")
        self.grid_check.toggled.connect(lambda on: self.stage.set_grid(on))
        toolbar.addWidget(self.grid_check)
        self.zoom_combo = QComboBox()
        for text, value in (("自适应", 8), ("4×", 4), ("6×", 6), ("8×", 8)):
            self.zoom_combo.addItem(text, value)
        self.zoom_combo.setFixedWidth(88)
        self.zoom_combo.setToolTip("预览放大倍数")
        self.zoom_combo.currentIndexChanged.connect(
            lambda *_: self.stage.set_zoom_limit(int(self.zoom_combo.currentData())))
        toolbar.addWidget(self.zoom_combo)
        layout.addLayout(toolbar)

        self.stage = OledView()
        self.code_view = QPlainTextEdit()
        self.code_view.setObjectName("Code")
        self.code_view.setReadOnly(True)
        self.code_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.code_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.stage)
        self.stack.addWidget(self.code_view)
        layout.addWidget(self.stack, 1)

        stats_card = Card("")
        stats_row = QHBoxLayout()
        stats_row.setSpacing(18)
        self.stat_lit = StatBlock("点亮像素")
        self.stat_bytes = StatBlock("点阵数据")
        self.stat_size = StatBlock("原图尺寸")
        self.stat_frame = StatBlock("第几张")
        for block in (self.stat_lit, self.stat_bytes, self.stat_size, self.stat_frame):
            stats_row.addWidget(block)
        stats_row.addStretch(1)
        self.export_button = QPushButton("导出预览 PNG")
        self.export_button.setObjectName("Ghost")
        self.export_button.clicked.connect(self._export_png)
        stats_row.addWidget(self.export_button, 0, Qt.AlignmentFlag.AlignBottom)
        stats_card.add_layout(stats_row)
        layout.addWidget(stats_card)
        return panel

    def _right_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.setObjectName("SideTabs")
        tabs.addTab(self._scroll_page(self._pin_card(), self._encoder_card()), "接线")
        tabs.addTab(self._scroll_page(self._project_card()), "工程")
        layout.addWidget(tabs, 1)

        # 生成与烧录固定在最下方，任何窗口高度下都能点到
        layout.addWidget(self._action_card())
        container.setFixedWidth(320)
        return container

    def _scroll_page(self, *cards: QWidget) -> QWidget:
        """把若干卡片塞进一个可滚动页面，卡片再多也不会被裁掉。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 2, 2, 0)
        inner_layout.setSpacing(10)
        for card in cards:
            inner_layout.addWidget(card)
        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        return scroll

    def _pin_card(self) -> QWidget:
        card = Card("OLED 接线（I2C，软件模拟）")
        grid = QHBoxLayout()
        grid.setSpacing(8)
        scl_label = QLabel("SCL")
        scl_label.setObjectName("FieldLabel")
        self.scl_combo = QComboBox()
        self.sda_combo = QComboBox()
        for combo, default in ((self.scl_combo, "PB8"), (self.sda_combo, "PB9")):
            combo.addItems(codegen.PIN_CHOICES)
            combo.setCurrentText(default)
        sda_label = QLabel("SDA")
        sda_label.setObjectName("FieldLabel")
        col1 = QVBoxLayout()
        col1.setSpacing(4)
        col1.addWidget(scl_label)
        col1.addWidget(self.scl_combo)
        col2 = QVBoxLayout()
        col2.setSpacing(4)
        col2.addWidget(sda_label)
        col2.addWidget(self.sda_combo)
        grid.addLayout(col1, 1)
        grid.addLayout(col2, 1)
        card.add_layout(grid)

        adv = QHBoxLayout()
        adv.setSpacing(8)
        addr_col = QVBoxLayout()
        addr_col.setSpacing(4)
        addr_label = QLabel("I2C 地址")
        addr_label.setObjectName("FieldLabel")
        self.addr_combo = QComboBox()
        self.addr_combo.addItem("0x3C（0x78）", "0x78")
        self.addr_combo.addItem("0x3D（0x7A）", "0x7A")
        self.addr_combo.currentIndexChanged.connect(self._on_pin_changed)
        addr_col.addWidget(addr_label)
        addr_col.addWidget(self.addr_combo)
        offset_col = QVBoxLayout()
        offset_col.setSpacing(4)
        offset_label = QLabel("列偏移")
        offset_label.setObjectName("FieldLabel")
        self.col_offset = QSpinBox()
        self.col_offset.setRange(0, 4)
        self.col_offset.setFixedWidth(88)
        self.col_offset.valueChanged.connect(self._on_pin_changed)
        offset_col.addWidget(offset_label)
        offset_col.addWidget(self.col_offset)
        adv.addLayout(addr_col, 1)
        adv.addLayout(offset_col)
        card.add_layout(adv)

        self.pin_warning = QLabel("")
        self.pin_warning.setWordWrap(True)
        self.pin_warning.setVisible(False)
        card.add(self.pin_warning)
        self.scl_combo.currentTextChanged.connect(self._on_pin_changed)
        self.sda_combo.currentTextChanged.connect(self._on_pin_changed)
        return card

    def _encoder_card(self) -> QWidget:
        card = Card("EC11 编码器（A / B / C）")
        hint = QLabel("A/B 接任意 GPIO，C 与按键另一端接 GND")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        card.add(hint)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.enc_a_combo = QComboBox()
        self.enc_b_combo = QComboBox()
        for combo, default in ((self.enc_a_combo, "PA0"), (self.enc_b_combo, "PA1")):
            combo.addItems(codegen.PIN_CHOICES)
            combo.setCurrentText(default)
            combo.currentTextChanged.connect(self._on_pin_changed)
        col_a = QVBoxLayout()
        col_a.setSpacing(4)
        label_a = QLabel("A 相 → STM32")
        label_a.setObjectName("FieldLabel")
        col_a.addWidget(label_a)
        col_a.addWidget(self.enc_a_combo)
        col_b = QVBoxLayout()
        col_b.setSpacing(4)
        label_b = QLabel("B 相 → STM32")
        label_b.setObjectName("FieldLabel")
        col_b.addWidget(label_b)
        col_b.addWidget(self.enc_b_combo)
        row.addLayout(col_a, 1)
        row.addLayout(col_b, 1)
        card.add_layout(row)

        c_row = QHBoxLayout()
        c_row.setSpacing(6)
        c_label = QLabel("C 公共端 → GND")
        c_label.setObjectName("FieldLabel")
        c_value = QLabel("不接单片机")
        c_value.setObjectName("Hint")
        c_row.addWidget(c_label)
        c_row.addStretch(1)
        c_row.addWidget(c_value)
        card.add_layout(c_row)

        sw_row = QHBoxLayout()
        sw_row.setSpacing(8)
        self.enc_sw_check = QCheckBox("按键 SW")
        self.enc_sw_check.setChecked(True)
        self.enc_sw_check.setToolTip("EC11 自带的按压开关，按下时显示当前序号；没有按键的编码器取消勾选")
        self.enc_sw_check.toggled.connect(self._on_encoder_toggled)
        self.enc_sw_combo = QComboBox()
        self.enc_sw_combo.addItems(codegen.PIN_CHOICES)
        self.enc_sw_combo.setCurrentText("PA2")
        self.enc_sw_combo.currentTextChanged.connect(self._on_pin_changed)
        sw_row.addWidget(self.enc_sw_check)
        sw_row.addWidget(self.enc_sw_combo, 1)
        card.add_layout(sw_row)

        opt_row = QHBoxLayout()
        opt_row.setSpacing(8)
        steps_label = QLabel("每格脉冲")
        steps_label.setObjectName("FieldLabel")
        self.enc_steps = QComboBox()
        for text, value in (("4（标准）", 4), ("2（半周期）", 2), ("8（易多跳）", 8)):
            self.enc_steps.addItem(text, value)
        self.enc_steps.setToolTip("转一格跳两张改小，转了没反应改大")
        self.enc_steps.currentIndexChanged.connect(self._on_pin_changed)
        self.enc_reverse = QCheckBox("反向")
        self.enc_reverse.setToolTip("顺时针变成上一张")
        self.enc_reverse.toggled.connect(self._on_pin_changed)
        opt_row.addWidget(steps_label)
        opt_row.addWidget(self.enc_steps, 1)
        opt_row.addWidget(self.enc_reverse)
        card.add_layout(opt_row)
        return card

    def _on_encoder_toggled(self) -> None:
        self.enc_sw_combo.setEnabled(self.enc_sw_check.isChecked())
        self._on_pin_changed()

    def _project_card(self) -> QWidget:
        card = Card("Keil 工程")
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_label = QLabel("工程名")
        name_label.setObjectName("FieldLabel")
        self.name_edit = QLineEdit(self.project_name)
        self.name_edit.editingFinished.connect(self._on_name_changed)
        name_row.addWidget(name_label)
        name_row.addWidget(self.name_edit, 1)
        card.add_layout(name_row)

        out_row = QHBoxLayout()
        out_row.setSpacing(6)
        out_label = QLabel("输出目录")
        out_label.setObjectName("FieldLabel")
        self.out_edit = QLineEdit(str(self.output_root))
        self.out_edit.setCursorPosition(0)
        self.out_edit.setToolTip(str(self.output_root))
        self.out_edit.editingFinished.connect(self._on_output_changed)
        out_button = QPushButton("…")
        out_button.setObjectName("Ghost")
        out_button.setFixedWidth(34)
        out_button.clicked.connect(self._pick_output_dir)
        out_row.addWidget(out_label)
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(out_button)
        card.add_layout(out_row)

        keil_row = QHBoxLayout()
        keil_row.setSpacing(6)
        keil_label = QLabel("Keil")
        keil_label.setObjectName("FieldLabel")
        self.keil_edit = QLineEdit(str(self.uv4) if self.uv4 else "")
        self.keil_edit.setPlaceholderText("未检测到 UV4.exe")
        self.keil_edit.editingFinished.connect(self._on_keil_changed)
        keil_button = QPushButton("…")
        keil_button.setObjectName("Ghost")
        keil_button.setFixedWidth(34)
        keil_button.clicked.connect(self._pick_keil)
        detect = QPushButton("自动检测")
        detect.setObjectName("Ghost")
        detect.clicked.connect(self._detect_keil)
        keil_row.addWidget(keil_label)
        keil_row.addWidget(self.keil_edit, 1)
        keil_row.addWidget(keil_button)
        keil_row.addWidget(detect)
        card.add_layout(keil_row)

        # 这三个输入框不接收拖放，避免把图片路径当成文字插进去
        for widget in (self.name_edit, self.out_edit, self.keil_edit):
            widget.setAcceptDrops(False)

        flags = QHBoxLayout()
        flags.setSpacing(12)
        self.open_after = QCheckBox("生成后打开 Keil")
        self.auto_generate = QCheckBox("自动生成")
        self.auto_generate.setChecked(True)
        self.auto_generate.setToolTip("导入图片后自动重新生成工程")
        flags.addWidget(self.open_after)
        flags.addWidget(self.auto_generate)
        flags.addStretch(1)
        card.add_layout(flags)
        return card

    def _action_card(self) -> QWidget:
        card = Card("生成与烧录")
        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        self.flash_button = QPushButton("一键生成并烧录")
        self.flash_button.setObjectName("Primary")
        self.flash_button.clicked.connect(self._generate_and_flash)
        self.gen_button = QPushButton("仅生成")
        self.gen_button.setObjectName("Ghost")
        self.gen_button.setToolTip("只生成 Keil 工程，不下载")
        self.gen_button.clicked.connect(self._generate_and_report)
        button_row.addWidget(self.flash_button, 2)
        button_row.addWidget(self.gen_button, 1)
        card.add_layout(button_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        card.add(self.progress)
        self.task_label = QLabel("准备就绪")
        self.task_label.setObjectName("Hint")
        self.task_label.setWordWrap(True)
        card.add(self.task_label)

        links = QHBoxLayout()
        links.setSpacing(12)
        open_dir = QPushButton("打开工程目录")
        open_dir.setObjectName("Link")
        open_dir.clicked.connect(self._open_project_dir)
        open_keil = QPushButton("用 Keil 打开")
        open_keil.setObjectName("Link")
        open_keil.clicked.connect(self._open_in_keil)
        help_link = QPushButton("使用说明")
        help_link.setObjectName("Link")
        help_link.clicked.connect(self._show_help)
        self_test = QPushButton("EC11 自检")
        self_test.setObjectName("Link")
        self_test.setToolTip("烧一个只显示 A/B 电平和跳变次数的固件，用来判断是接线问题还是解码问题")
        self_test.clicked.connect(self._run_selftest)
        links.addWidget(open_dir)
        links.addWidget(open_keil)
        links.addWidget(self_test)
        links.addStretch(1)
        links.addWidget(help_link)
        card.add_layout(links)
        return card

    def _show_help(self) -> None:
        pins = self.pins()
        enc = self.encoder()
        sw = enc.button if enc.button_enabled else "未启用"
        rows = [
            ("OLED", "VCC", "3.3V"), ("OLED", "GND", "GND"),
            ("OLED", "SCL", pins.scl), ("OLED", "SDA", pins.sda),
            ("EC11", "A 相", enc.a), ("EC11", "B 相", enc.b),
            ("EC11", "C 公共端", "GND"), ("EC11", "按键 SW", sw),
        ]
        table = "".join(
            f"<tr><td width='54'>{m}</td><td width='66'>{p}</td><td width='16'>→</td>"
            f"<td><b>{t}</b></td></tr>" for m, p, t in rows)
        QMessageBox.information(
            self, "使用说明",
            "<b>当前接线（跟着右侧选择实时变）</b>"
            f"<table cellspacing='0' cellpadding='2'>{table}</table>"
            "EC11 的 A、B 任意 GPIO 都行（已开内部上拉），<b>C 是公共端，必须接 GND</b>；"
            "按键另一个脚也接 GND。模块内部一般自带 4.7k 上拉，整套只吃 3.3V，不要接 5V。<br>"
            "买到的若是 VCC / GND / CLK / DT / SW 五脚模块：CLK 当 A 相、DT 当 B 相、SW 当按键。<br><br>"
            "<b>流程</b><br>"
            "1. 导入多张图片（可多选，GIF 会自动拆帧，按列表顺序对应 1、2、3…）<br>"
            "2. 左边调阈值 / 反色 / 缩放，中间实时看效果<br>"
            "3. 点“一键生成并烧录”，软件生成完整 Keil 工程、编译并用 ST-Link 下载<br>"
            "4. 上电显示第 1 张，<b>拧 EC11 才换图</b>，按下编码器显示当前序号<br><br>"
            "<b>本软件不会自动播放</b><br>"
            "生成的 main.c 只有「读编码器 → 换图」两步，没有任何定时轮播代码；"
            "屏幕上图片自己在循环播放，说明烧进去的是别的工程，重新点一次“一键生成并烧录”即可。<br>"
            "另外：界面左边是“帧序列 / 帧间隔”的那个是<b>OLED 图像助手</b>，它会循环播放，也没有 EC11 配置；"
            "本软件的左边是“图库图片”，顶栏写着 EC11 手动切图。<br><br>"
            "<b>能存多少张</b><br>"
            f"图片以常量数组烧进 Flash，每张占 1 KB。STM32F103C8T6 有 64 KB，"
            f"程序约占 8 KB，因此上限约 <b>{codegen.MAX_IMAGES} 张</b>；"
            f"若用未注册的 MDK-Lite（32 KB 限制），上限约 <b>{codegen.LITE_MAX_IMAGES} 张</b>。<br><br>"
            "<b>EC11 转动手感不对时</b><br>"
            "转一格跳两张 → 把“每格脉冲”改小；转了没反应 → 改大；方向相反 → 勾“反向”。<br>"
            "<b>完全没反应</b>：点下面「EC11 自检」烧一个只显示 A/B 电平的固件——"
            "A/B 数字不随旋转变化就是接线或供电问题（C 接 GND 不行的话，少数下拉型模块要把 C 接 3.3V）；"
            "A/B 会变但 EDGE 不动是中断问题；EDGE 会变但 STEP 不动就把“每格脉冲”改成 2。<br>"
            "烧录时请确认 SWDIO / SWCLK / GND / 3.3V 与 ST-Link 一一对应。"
        )

    def _log_panel(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(16, 0, 16, 10)
        card = Card("")
        card.setFixedHeight(142)
        self.log_card = card
        header = QHBoxLayout()
        title = QLabel("运行日志")
        title.setObjectName("CardTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.log_toggle = QPushButton("折叠")
        self.log_toggle.setObjectName("Link")
        self.log_toggle.clicked.connect(self._toggle_log)
        header.addWidget(self.log_toggle)
        clear = QPushButton("清空")
        clear.setObjectName("Link")
        clear.clicked.connect(lambda: self.log_view.clear())
        header.addWidget(clear)
        card.add_layout(header)
        self.log_view = QTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        card.add(self.log_view)
        layout.addWidget(card)
        return wrapper

    def _status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(28)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 0, 18, 6)
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("Hint")
        right = QLabel("SSD1306 · 128×64 · 1 bpp · 软件 I2C")
        right.setObjectName("Hint")
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        layout.addWidget(right)
        return bar

    def _apply_theme(self) -> None:
        self.setStyleSheet(theme.qss())

    # ------------------------------------------------------------------ 数据
    def options(self) -> RenderOptions:
        return RenderOptions(
            fit=self.fit_combo.currentData(),
            scale=self.scale_slider.value() / 100,
            offset_x=self.offset_x.value(),
            offset_y=self.offset_y.value(),
            rotate=self.rotate_combo.currentData(),
            flip_h=self.flip_h.isChecked(),
            flip_v=self.flip_v.isChecked(),
            brightness=self.brightness_slider.value(),
            contrast=self.contrast_slider.value(),
            method=self.method_combo.currentData(),
            threshold=self.threshold_slider.value(),
            invert=self.invert_check.isChecked(),
            autocrop=self.autocrop_check.isChecked(),
            nearest=self.nearest_check.isChecked(),
            sharpen=self.sharpen_slider.value(),
        )

    def pins(self) -> codegen.PinConfig:
        return codegen.PinConfig(
            sda=self.sda_combo.currentText(),
            scl=self.scl_combo.currentText(),
            i2c_addr=self.addr_combo.currentData(),
            col_offset=self.col_offset.value(),
        )

    def encoder(self) -> codegen.EncoderConfig:
        return codegen.EncoderConfig(
            a=self.enc_a_combo.currentText(),
            b=self.enc_b_combo.currentText(),
            button=self.enc_sw_combo.currentText(),
            button_enabled=self.enc_sw_check.isChecked(),
            reverse=self.enc_reverse.isChecked(),
            steps_per_detent=int(self.enc_steps.currentData()),
            scan_ms=1,
        )

    # ------------------------------------------------------------------ 导入
    def _pick_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", self._last_dir,
            "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.gif *.tif *.tiff);;所有文件 (*.*)")
        if files:
            self._last_dir = str(Path(files[0]).parent)
            self.add_paths([Path(f) for f in files])

    def add_paths(self, paths: list[Path]) -> None:
        added: list[Frame] = []
        errors: list[str] = []
        for path in paths:
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                errors.append(f"{path.name}：不支持的格式")
                continue
            try:
                loaded = imaging.load_frames(path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{path.name}：{exc}")
                continue
            if len(loaded) > MAX_GIF_FRAMES:
                step = max(1, len(loaded) // MAX_GIF_FRAMES)
                loaded = loaded[::step][:MAX_GIF_FRAMES]
                self._log(f"{path.name} 帧数较多，已按 {step} 帧抽 1 帧", "warn")
            added.extend(loaded)
        if not added:
            if errors:
                self._log("；".join(errors), "err")
            return

        first_import = not self.frames
        self.frames.extend(added)
        if first_import:
            self._suggest_options(added[0])
        self.current = 0
        self._refresh_frames()
        self._on_frame_selected(0)
        self._log(f"已导入 {len(added)} 张（图库共 {len(self.frames)} 张）", "ok")
        self._dirty = True
        if self.auto_generate.isChecked():
            self._generate(silent=True)

    def _suggest_options(self, frame: Frame) -> None:
        opts = self.options()
        invert = imaging.auto_invert_suggestion(frame.image)
        self._loading = True
        self.invert_check.setChecked(invert)
        threshold = imaging.suggest_threshold(frame.image, opts.copy(invert=invert))
        self.threshold_slider.set_value(threshold)
        self._loading = False
        self._log(f"自动参数：反色={'开' if invert else '关'}，阈值={threshold}", "info")

    def _clear_frames(self) -> None:
        if not self.frames:
            return
        self.frames.clear()
        self.current = 0
        self._refresh_frames()
        self._refresh_preview()
        self.last_result = None
        self.chip_state.set_text("尚未生成工程")
        self.chip_state.set_state(None)
        self._log("已清空图片", "info")

    def _refresh_frames(self) -> None:
        self.frame_list.blockSignals(True)
        self.frame_list.clear()
        opts = self.options()
        for index, frame in enumerate(self.frames):
            if frame.mono is None or frame.data is None:
                mono = imaging.render(frame.image, opts)
                frame.mono, frame.data = mono, imaging.pack(mono)
            item = QListWidgetItem(QIcon(mono_pixmap(frame.mono)), f"  {index + 1}. {frame.name}")
            item.setToolTip(f"{frame.name}\n原图 {frame.size[0]}×{frame.size[1]}")
            self.frame_list.addItem(item)
        if self.frames:
            self.frame_list.setCurrentRow(min(self.current, len(self.frames) - 1))
        self.frame_list.blockSignals(False)
        self.frames_card.setVisible(bool(self.frames))
        self.drop.setVisible(not self.frames)
        self.pick_button.setText("添加图片" if self.frames else "选择文件")
        self._update_capacity()

    def _update_capacity(self) -> None:
        count = len(self.frames)
        over_hard = count > codegen.MAX_IMAGES
        over_lite = count > codegen.LITE_MAX_IMAGES

        self.capacity_bar.setValue(min(count, codegen.MAX_IMAGES))
        if over_hard:
            color, note = theme.ERR, "超出 64KB Flash，必须删减"
        elif over_lite:
            color, note = theme.WARN, f"超过 {codegen.LITE_MAX_IMAGES} 张，未注册的 Keil 会编译失败"
        else:
            color, note = theme.ACCENT, ""
        self.capacity_bar.setStyleSheet(
            f"QProgressBar{{background:#E6E9EE;border:none;border-radius:3px;}}"
            f"QProgressBar::chunk{{background:{color};border-radius:3px;}}")

        self.capacity_label.setText(
            f"{count} / {codegen.MAX_IMAGES} 张 · 占 {count} KB Flash" + (f"　{note}" if note else ""))
        self.capacity_label.setStyleSheet(f"color:{color};" if note else "")
        self.frames_hint.setText(f"{count} 张" if count else "")

    def _on_frame_selected(self, row: int) -> None:
        if row < 0 or row >= len(self.frames):
            return
        self.current = row
        self._refresh_preview()

    def _move_frame(self, delta: int) -> None:
        row = self.frame_list.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < len(self.frames)):
            return
        self.frames[row], self.frames[target] = self.frames[target], self.frames[row]
        self.current = target
        self._refresh_frames()
        self._refresh_preview()

    def _remove_frame(self) -> None:
        row = self.frame_list.currentRow()
        if row < 0:
            return
        self.frames.pop(row)
        self.current = max(0, row - 1)
        self._refresh_frames()
        self._refresh_preview()
        self._dirty = True

    # ------------------------------------------------------------------ 预览
    def _on_params_changed(self, *_) -> None:
        if self._loading:
            return
        self._dirty = True
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        if not hasattr(self, "_preview_timer"):
            self._preview_timer = QTimer(self)
            self._preview_timer.setSingleShot(True)
            self._preview_timer.setInterval(40)
            self._preview_timer.timeout.connect(self._refresh_preview)
        self._preview_timer.start()

    def _refresh_preview(self) -> None:
        if not self.frames:
            self.stage.set_mono(None)
            for block in (self.stat_lit, self.stat_bytes, self.stat_size, self.stat_frame):
                block.set_value("—")
            self.code_view.setPlainText("// 导入图片后，这里显示生成的 C 代码")
            return
        index = min(self.current, len(self.frames) - 1)
        frame = self.frames[index]
        opts = self.options()
        try:
            mono = imaging.render(frame.image, opts)
            data = imaging.pack(mono)
        except Exception as exc:  # noqa: BLE001
            self._log(f"处理失败：{exc}", "err")
            return
        frame.mono, frame.data = mono, data
        self.stage.set_mono(mono)
        lit = imaging.lit_count(mono)
        self.stat_lit.set_value(f"{lit} px")
        self.stat_lit.setToolTip(f"占整屏 {lit / (imaging.OLED_W * imaging.OLED_H) * 100:.1f}%")
        self.stat_bytes.set_value(f"{len(data)} B")
        self.stat_size.set_value(f"{frame.size[0]}×{frame.size[1]}")
        self.stat_frame.set_value(f"{index + 1} / {len(self.frames)}")
        # 列表缩略图跟随参数变化
        item = self.frame_list.item(index)
        if item is not None:
            item.setIcon(QIcon(mono_pixmap(mono)))
        if self.stack.currentIndex() == 1:
            self._update_code_view()
        self._update_status()

    def _update_status(self) -> None:
        bits = ["就绪"]
        if self.frames:
            bits.append(f"图库 {len(self.frames)} / {codegen.MAX_IMAGES} 张")
        if self._dirty:
            bits.append("参数已修改，需重新生成")
        self.status_label.setText("　·　".join(bits))

    def _switch_view(self, key: str) -> None:
        self.stack.setCurrentIndex(0 if key == "image" else 1)
        self.grid_check.setEnabled(key == "image")
        self.zoom_combo.setEnabled(key == "image")
        if key == "code":
            self._update_code_view()

    def _update_code_view(self) -> None:
        if not self.frames:
            self.code_view.setPlainText("// 导入图片后，这里显示生成的 C 代码")
            return
        frames = self.frames
        header = codegen.build_gallery_header(frames)
        if len(frames) > 1:
            cut = header.find("/* 第 2 张")
            table_at = header.find("const uint8_t *const GAL_ImageTable")
            if cut > 0 and table_at > cut:
                header = header[:cut] + f"/* … 其余 {len(frames) - 1} 张数据略 … */\n\n" + header[table_at:]

        out: list[str] = []
        hex_lines = 0
        for line in header.splitlines():
            if line.strip().startswith("0x"):
                hex_lines += 1
                if hex_lines > 6:
                    if hex_lines == 7:
                        out.append("\t/* … 其余 1016 字节略 … */")
                    continue
            out.append(line)
        text = "/* ===== User/OLED_Gallery.h ===== */\n" + "\n".join(out)
        text += "\n\n/* ===== User/main.c ===== */\n" + codegen.build_main_c(len(frames))
        self.code_view.setPlainText(text)

    def _export_png(self) -> None:
        if not self.frames:
            self._log("还没有可以导出的图片", "warn")
            return
        frame = self.frames[min(self.current, len(self.frames) - 1)]
        if frame.mono is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出预览", str(Path.home() / "oled_preview.png"),
                                              "PNG 图片 (*.png)")
        if not path:
            return
        image = frame.mono.convert("L").resize((imaging.OLED_W * 6, imaging.OLED_H * 6), Image.Resampling.NEAREST)
        image.save(path)
        self._log(f"预览已导出：{path}", "ok")

    # ------------------------------------------------------------------ 参数
    def _auto_threshold(self) -> None:
        if not self.frames:
            return
        frame = self.frames[min(self.current, len(self.frames) - 1)]
        value = imaging.suggest_threshold(frame.image, self.options())
        self.threshold_slider.set_value(value)
        self._log(f"自动阈值：{value}", "info")
        self._on_params_changed()

    def _reset_params(self) -> None:
        self._loading = True
        self.fit_combo.setCurrentIndex(0)
        self.scale_slider.set_value(100)
        self.offset_x.setValue(0)
        self.offset_y.setValue(0)
        self.rotate_combo.setCurrentIndex(0)
        self.flip_h.setChecked(False)
        self.flip_v.setChecked(False)
        self.brightness_slider.set_value(0)
        self.contrast_slider.set_value(0)
        self.method_combo.setCurrentIndex(0)
        self.threshold_slider.set_value(128)
        self.sharpen_slider.set_value(60)
        self.invert_check.setChecked(False)
        self.autocrop_check.setChecked(True)
        self.nearest_check.setChecked(False)
        self._loading = False
        if self.frames:
            self._suggest_options(self.frames[0])
        self._on_params_changed()
        self._refresh_frames()

    def _on_pin_changed(self, *_) -> None:
        self._update_pin_warnings()
        self._dirty = True

    def _update_pin_warnings(self) -> None:
        warnings = codegen.pin_warnings(self.pins(), self.encoder())
        if not warnings:
            self.pin_warning.setVisible(False)
            self.flash_button.setEnabled(not self._busy)
            return
        level, text = warnings[0]
        color = theme.ERR if level == "error" else theme.WARN
        self.pin_warning.setText("⚠ " + "；".join(t for _, t in warnings))
        self.pin_warning.setStyleSheet(f"color:{color}; font-size:11.5px;")
        self.pin_warning.setVisible(True)
        self.flash_button.setEnabled(level != "error" and not self._busy)

    # ------------------------------------------------------------------ 工程
    def _on_name_changed(self) -> None:
        name = codegen.sanitize_name(self.name_edit.text())
        self.project_name = name
        self.name_edit.setText(name)
        self._dirty = True

    def _on_output_changed(self) -> None:
        text = self.out_edit.text().strip()
        if text:
            self.output_root = Path(text)
            self._dirty = True

    def _pick_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录", str(self.output_root))
        if directory:
            self.output_root = Path(directory)
            self.out_edit.setText(directory)
            self._dirty = True

    def _pick_keil(self) -> None:
        start = str(self.uv4.parent) if self.uv4 else "C:/"
        path, _ = QFileDialog.getOpenFileName(self, "选择 UV4.exe", start, "UV4.exe (UV4.exe)")
        if path:
            self.uv4 = Path(path)
            self.keil_edit.setText(path)
            self.pack_version = toolchain.best_pack_version(self.uv4)
            self._refresh_keil_chip()

    def _on_keil_changed(self) -> None:
        text = self.keil_edit.text().strip()
        candidate = Path(text) if text else None
        self.uv4 = candidate if candidate and candidate.is_file() else None
        self.pack_version = toolchain.best_pack_version(self.uv4)
        self._refresh_keil_chip()

    def _detect_keil(self) -> None:
        self.uv4 = toolchain.find_uv4()
        self.pack_version = toolchain.best_pack_version(self.uv4)
        self.keil_edit.setText(str(self.uv4) if self.uv4 else "")
        self._refresh_keil_chip()
        self._log(f"Keil 检测：{self.uv4 or '未找到'}", "ok" if self.uv4 else "warn")

    def _refresh_keil_chip(self) -> None:
        if self.uv4:
            version = f" · DFP {self.pack_version}" if self.pack_version else ""
            self.chip_keil.set_text(f"Keil 已就绪{version}")
            self.chip_keil.set_state("ok")
            self.chip_keil.setToolTip(str(self.uv4))
        else:
            self.chip_keil.set_text("未检测到 Keil")
            self.chip_keil.set_state("err")
            self.chip_keil.setToolTip("请安装 Keil MDK 或在右侧手动指定 UV4.exe")

    def _generate(self, silent: bool = False) -> codegen.GenerateResult | None:
        if not self.frames:
            if not silent:
                self._log("请先导入图片", "warn")
            return None
        if len(self.frames) > codegen.MAX_IMAGES:
            self._log(f"图片太多：{len(self.frames)} 张，STM32F103C8T6 最多存 {codegen.MAX_IMAGES} 张，请删减", "err")
            return None
        opts = self.options()
        try:
            processed = imaging.process_all(self.frames, opts)
        except Exception as exc:  # noqa: BLE001
            self._log(f"取模失败：{exc}", "err")
            return None
        try:
            result = codegen.generate(self.output_root, self.project_name, processed, self.pins(),
                                      self.encoder(), self.pack_version)
        except Exception as exc:  # noqa: BLE001
            self._log(f"生成工程失败：{exc}", "err")
            return None
        self.last_result = result
        self._dirty = False
        self.chip_state.set_text(f"工程已生成 · {len(processed)} 张")
        self.chip_state.set_state("ok")
        self.chip_state.setToolTip(str(result.project_file))
        self.task_label.setText(f"已生成：{result.project_dir.name}")
        self._update_status()
        if not silent:
            self._log(f"工程已生成：{result.project_file}", "ok")
            self._log(f"图库 {result.image_count} 张，点阵 {result.total_bytes} 字节，"
                      f"SCL={self.pins().scl} / SDA={self.pins().sda}，"
                      f"EC11 A={self.encoder().a} B={self.encoder().b} C=GND、"
                      f"按键={self.encoder().button if self.encoder().button_enabled else '未启用'}", "info")
            self._log("固件不含自动播放：上电显示第 1 张，只有转动 EC11 才换图", "info")
        if self.open_after.isChecked() and self.uv4:
            toolchain.open_in_keil(self.uv4, result.project_file)
        return result

    def _generate_and_report(self) -> None:
        if self._busy:
            return
        result = self._generate()
        if result:
            self._log("可以点“一键生成并烧录”，或在 Keil 里打开工程自行下载", "info")

    def _generate_and_flash(self) -> None:
        if self._busy:
            return
        if not self.uv4:
            QMessageBox.warning(self, "找不到 Keil",
                                "没有检测到 UV4.exe。请安装 Keil MDK，或在右侧“Keil”一栏手动指定路径。")
            return
        result = self._generate()
        if not result:
            return
        uv4 = self.uv4
        project = result.project_file

        def work(log):
            log("开始编译…")
            build = toolchain.build(uv4, project, log)
            summary = toolchain.summary_from_log(build.log)
            if not build.ok:
                hint = toolchain.build_error_hint(build.log)
                raise RuntimeError(hint or ("编译失败：" + (summary or build.message)))
            log("编译成功" + (f"（{summary}）" if summary else ""))
            log("开始烧录，请确认 ST-Link 已连接…")
            flash = toolchain.flash(uv4, project, log)
            if not flash.ok:
                raise RuntimeError("烧录失败：" + flash.message + "。可先在 Keil 里手动 Download 确认硬件连接")
            log("烧录完成，程序已开始运行")
            return summary

        self._start_task(work, "烧录完成")

    def _run_selftest(self) -> None:
        if self._busy:
            return
        if not self.uv4:
            QMessageBox.warning(self, "找不到 Keil",
                                "没有检测到 UV4.exe。请安装 Keil MDK，或在右侧“Keil”一栏手动指定路径。")
            return
        answer = QMessageBox.question(
            self, "EC11 接线自检",
            "会烧一个自检固件进单片机（覆盖现在的图库程序），屏幕显示四行：<br>"
            "<b>A / B</b> 两相实时电平　<b>ISR</b> 1ms 中断次数<br>"
            "<b>EDGE</b> 两相跳变次数　<b>STEP</b> 解码出的步数<br><br>"
            "转动编码器看数字：<br>"
            "· A/B 会翻转、EDGE 跟着变 → 接线没问题，回去把「每格脉冲」调小<br>"
            "· A/B 一直不动 → 线没接对 / 模块没供电 / C 接错（换 3.3V 试试）<br>"
            "· A/B 会变但 EDGE 一直是 0 → 定时中断没跑<br>"
            "· EDGE 会变但 STEP 一直是 0 → 每格脉冲设大了，改成 2<br><br>"
            "看完再点一次「一键生成并烧录」，图库固件就写回去了。要继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = codegen.generate(self.output_root, "EC11_Test", [], self.pins(),
                                      self.encoder(), self.pack_version, selftest=True)
        except Exception as exc:  # noqa: BLE001
            self._log(f"生成自检工程失败：{exc}", "err")
            return
        self._log(f"自检工程：{result.project_dir}", "info")
        uv4 = self.uv4
        project = result.project_file

        def work(log):
            log("编译自检固件…")
            build = toolchain.build(uv4, project, log)
            if not build.ok:
                raise RuntimeError(toolchain.build_error_hint(build.log) or "编译失败")
            log("烧录自检固件…")
            flash = toolchain.flash(uv4, project, log)
            if not flash.ok:
                raise RuntimeError("烧录失败：" + flash.message)
            log("自检固件已运行：转动编码器，看屏幕 A / B 和 EDGE 有没有变化")
            return "自检固件运行中"

        self._start_task(work, "自检固件运行中")

    def _start_task(self, work, success_text: str) -> None:
        self._busy = True
        self._set_buttons_enabled(False)
        self.progress.setVisible(True)
        self.task_label.setText("正在执行…")
        self.thread = TaskThread(work, self)
        self.thread.line.connect(self._on_task_line)
        self.thread.done.connect(lambda payload: self._on_task_done(success_text, payload))
        self.thread.failed.connect(self._on_task_failed)
        self.thread.start()

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self.flash_button.setEnabled(enabled and self._pins_ok())
        self.gen_button.setEnabled(enabled)
        self.drop.setEnabled(enabled)

    def _pins_ok(self) -> bool:
        return all(level != "error" for level, _ in codegen.pin_warnings(self.pins(), self.encoder()))

    def _on_task_line(self, line: str) -> None:
        low = line.lower()
        if "error" in low or "错误" in line:
            self._log(line, "err")
        elif "warning" in low or "警告" in line:
            self._log(line, "warn")
        else:
            self._log(line, "raw")

    def _on_task_done(self, message: str, payload) -> None:
        self._busy = False
        self._set_buttons_enabled(True)
        self.progress.setVisible(False)
        self.task_label.setText(message)
        self.chip_state.set_text("烧录完成")
        self.chip_state.set_state("ok")
        self._log(message, "ok")

    def _on_task_failed(self, error: str) -> None:
        self._busy = False
        self._set_buttons_enabled(True)
        self.progress.setVisible(False)
        self.task_label.setText("失败，请查看日志")
        self.chip_state.set_text("生成/烧录失败")
        self.chip_state.set_state("err")
        self._log(error, "err")

    def _open_project_dir(self) -> None:
        target = self.last_result.project_dir if self.last_result else self.output_root / self.project_name
        if target.exists():
            toolchain.open_folder(target)
        else:
            self._log("工程目录还不存在，请先生成工程", "warn")

    def _open_in_keil(self) -> None:
        if not self.uv4:
            self._log("没有检测到 Keil", "warn")
            return
        project = (self.last_result.project_file if self.last_result
                   else self.output_root / self.project_name / f"{self.project_name}.uvprojx")
        if project.exists():
            toolchain.open_in_keil(self.uv4, project)
        else:
            self._log("工程文件还不存在，请先生成工程", "warn")

    # ------------------------------------------------------------------ 其他
    def _log(self, text: str, level: str = "info") -> None:
        colors = {"info": "#C3CCD7", "ok": "#6FD08C", "warn": "#E6B45E", "err": "#F07C7C", "raw": "#8A94A3"}
        color = colors.get(level, "#C3CCD7")
        stamp = time.strftime("%H:%M:%S")
        safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        self.log_view.append(f'<span style="color:#5B6675">[{stamp}]</span> '
                             f'<span style="color:{color}">{safe}</span>')
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def _toggle_log(self) -> None:
        visible = self.log_view.isVisible()
        self.log_view.setVisible(not visible)
        self.log_card.setFixedHeight(142 if visible else 50)
        self.log_toggle.setText("展开" if visible else "折叠")

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths and not self._busy:
            self.add_paths(paths)
            event.acceptProposedAction()

    # ------------------------------------------------------------------ 配置
    def _load_config(self) -> None:
        if not CONFIG_PATH.is_file():
            return
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return
        self._loading = True
        try:
            self.output_root = Path(data.get("output_root", self.output_root))
            self.out_edit.setText(str(self.output_root))
            self.project_name = codegen.sanitize_name(data.get("project_name", self.project_name))
            self.name_edit.setText(self.project_name)
            self.scl_combo.setCurrentText(data.get("scl", "PB8"))
            self.sda_combo.setCurrentText(data.get("sda", "PB9"))
            index = self.addr_combo.findData(data.get("i2c_addr", "0x78"))
            self.addr_combo.setCurrentIndex(max(0, index))
            self.col_offset.setValue(int(data.get("col_offset", 0)))
            self.enc_a_combo.setCurrentText(data.get("enc_a", "PA0"))
            self.enc_b_combo.setCurrentText(data.get("enc_b", "PA1"))
            self.enc_sw_combo.setCurrentText(data.get("enc_sw", "PA2"))
            self.enc_sw_check.setChecked(bool(data.get("enc_sw_enabled", True)))
            self.enc_reverse.setChecked(bool(data.get("enc_reverse", False)))
            steps_index = self.enc_steps.findData(int(data.get("enc_steps", 4)))
            self.enc_steps.setCurrentIndex(max(0, steps_index))
            self.auto_generate.setChecked(bool(data.get("auto_generate", True)))
            self.open_after.setChecked(bool(data.get("open_after", False)))
            self._last_dir = data.get("last_dir", self._last_dir)
            opts = data.get("options", {})
            self.fit_combo.setCurrentIndex(max(0, self.fit_combo.findData(opts.get("fit", "fit"))))
            self.scale_slider.set_value(int(float(opts.get("scale", 1.0)) * 100))
            self.offset_x.setValue(int(opts.get("offset_x", 0)))
            self.offset_y.setValue(int(opts.get("offset_y", 0)))
            rotate_index = self.rotate_combo.findData(int(opts.get("rotate", 0)))
            self.rotate_combo.setCurrentIndex(max(0, rotate_index))
            self.flip_h.setChecked(bool(opts.get("flip_h", False)))
            self.flip_v.setChecked(bool(opts.get("flip_v", False)))
            self.brightness_slider.set_value(int(opts.get("brightness", 0)))
            self.contrast_slider.set_value(int(opts.get("contrast", 0)))
            method_index = self.method_combo.findData(opts.get("method", imaging.METHOD_THRESHOLD))
            self.method_combo.setCurrentIndex(max(0, method_index))
            self.threshold_slider.set_value(int(opts.get("threshold", 128)))
            self.invert_check.setChecked(bool(opts.get("invert", False)))
            self.autocrop_check.setChecked(bool(opts.get("autocrop", True)))
            self.nearest_check.setChecked(bool(opts.get("nearest", False)))
            self.sharpen_slider.set_value(int(opts.get("sharpen", 60)))
            keil = data.get("keil")
            if keil and Path(keil).is_file():
                self.uv4 = Path(keil)
                self.pack_version = toolchain.best_pack_version(self.uv4)
                self.keil_edit.setText(keil)
        finally:
            self._loading = False

    def _save_config(self) -> None:
        opts = self.options()
        data = {
            "output_root": str(self.output_root),
            "project_name": self.project_name,
            "scl": self.pins().scl,
            "sda": self.pins().sda,
            "i2c_addr": self.pins().i2c_addr,
            "col_offset": self.col_offset.value(),
            "enc_a": self.encoder().a,
            "enc_b": self.encoder().b,
            "enc_sw": self.encoder().button,
            "enc_sw_enabled": self.enc_sw_check.isChecked(),
            "enc_reverse": self.enc_reverse.isChecked(),
            "enc_steps": self.encoder().steps_per_detent,
            "auto_generate": self.auto_generate.isChecked(),
            "open_after": self.open_after.isChecked(),
            "last_dir": self._last_dir,
            "keil": str(self.uv4) if self.uv4 else "",
            "options": {
                "fit": opts.fit, "scale": opts.scale, "offset_x": opts.offset_x,
                "offset_y": opts.offset_y, "rotate": opts.rotate, "flip_h": opts.flip_h,
                "flip_v": opts.flip_v, "brightness": opts.brightness, "contrast": opts.contrast,
                "method": opts.method, "threshold": opts.threshold, "invert": opts.invert,
                "autocrop": opts.autocrop, "nearest": opts.nearest, "sharpen": opts.sharpen,
            },
        }
        try:
            CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_config()
        if self.thread and self.thread.isRunning():
            self.thread.terminate()
            self.thread.wait(1000)
        super().closeEvent(event)
