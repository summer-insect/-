"""把处理好的点阵生成一套可直接编译的 Keil 工程。"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .imaging import Frame
from .paths import TEMPLATE_DIR

PORTS = {"A": "GPIOA", "B": "GPIOB", "C": "GPIOC"}
CLOCKS = {"A": "RCC_APB2Periph_GPIOA", "B": "RCC_APB2Periph_GPIOB", "C": "RCC_APB2Periph_GPIOC"}

# 可用的引脚：GPIOA/GPIOB 全部，GPIOC 只有 13~15
PIN_CHOICES: list[str] = [f"P{p}{n}" for p in ("A", "B") for n in range(16)] + [f"PC{n}" for n in (13, 14, 15)]

PIN_NOTES = {
    "PA13": ("error", "SWDIO，接 SWD 调试器，占用后无法烧录"),
    "PA14": ("error", "SWCLK，接 SWD 调试器，占用后无法烧录"),
    "PA15": ("warn", "JTAG 引脚，生成代码会自动关闭 JTAG（保留 SWD）"),
    "PB3": ("warn", "JTAG 引脚，生成代码会自动关闭 JTAG（保留 SWD）"),
    "PB4": ("warn", "JTAG 引脚，生成代码会自动关闭 JTAG（保留 SWD）"),
    "PA9": ("warn", "USART1 TX，若同时使用串口会冲突"),
    "PA10": ("warn", "USART1 RX，若同时使用串口会冲突"),
    "PA11": ("info", "USB DM"),
    "PA12": ("info", "USB DP"),
    "PB2": ("info", "BOOT1，复位时电平会影响启动方式"),
    "PC13": ("info", "C 口引脚驱动能力较弱，但驱动 OLED 足够"),
    "PC14": ("info", "接 32.768kHz 晶振（若板上有）"),
    "PC15": ("info", "接 32.768kHz 晶振（若板上有）"),
}

FLASH_LIMIT_WARN = 30 * 1024  # MDK-Lite 32K 限制，留一点余量


@dataclass
class PinConfig:
    sda: str = "PB9"
    scl: str = "PB8"
    i2c_addr: str = "0x78"   # 0x78 = 0x3C<<1
    col_offset: int = 0      # SSD1306 0.96 寸为 0，SH1106 1.3 寸为 2


@dataclass
class GenerateResult:
    project_file: Path
    project_dir: Path
    header_file: Path
    main_file: Path
    total_bytes: int
    warnings: list[str] = field(default_factory=list)


def pin_parts(pin: str) -> tuple[str, str, str]:
    """'PB9' -> ('GPIOB', 'GPIO_Pin_9', 'RCC_APB2Periph_GPIOB')"""
    match = re.fullmatch(r"P([ABC])(\d{1,2})", pin.strip().upper())
    if not match:
        raise ValueError(f"无法识别的引脚：{pin}")
    port, number = match.group(1), int(match.group(2))
    return PORTS[port], f"GPIO_Pin_{number}", CLOCKS[port]


def sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", name.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "OLED_Image"
    if cleaned[0].isdigit():
        cleaned = "P" + cleaned
    return cleaned[:32]


def pin_warnings(pins: PinConfig) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if pins.sda == pins.scl:
        result.append(("error", "SDA 与 SCL 不能使用同一个引脚"))
    for pin in (pins.scl, pins.sda):
        note = PIN_NOTES.get(pin)
        if note:
            result.append(note)
    return result


def _header_comment() -> str:
    return f"由 OLED 图像助手 于 {datetime.now():%Y-%m-%d %H:%M} 生成"


def _format_bytes(data: bytes, per_line: int = 16) -> str:
    lines = []
    for i in range(0, len(data), per_line):
        chunk = data[i:i + per_line]
        lines.append("    " + ", ".join(f"0x{b:02X}" for b in chunk) + ",")
    return "\n".join(lines)


def build_image_header(frames: list[Frame], interval_ms: int) -> str:
    count = len(frames)
    arrays = []
    for index, frame in enumerate(frames):
        data = frame.data or b""
        arrays.append(
            f"/* 第 {index} 帧：{_cn(frame.name)} */\n"
            f"const uint8_t IMG_Frame{index}[IMG_FRAME_BYTES] = {{\n"
            f"{_format_bytes(data)}\n"
            f"}};\n"
        )
    table = ",\n".join(f"    IMG_Frame{i}" for i in range(count))
    return (
        "/*\n"
        f" * OLED_Image.h - 128x64 单色点阵数据\n"
        f" * {_header_comment()}\n"
        " * 数据格式：纵向 8 点一页，低位在上（bit0 为页内第一行），bit=1 点亮\n"
        " * 注意：本文件只应被 main.c 包含一次\n"
        " */\n\n"
        "#ifndef OLED_IMAGE_H\n"
        "#define OLED_IMAGE_H\n\n"
        '#include "stm32f10x.h"\n\n'
        "#define IMG_WIDTH             128\n"
        "#define IMG_HEIGHT            64\n"
        "#define IMG_FRAME_BYTES       1024\n"
        f"#define IMG_FRAME_COUNT       {count}\n"
        f"#define IMG_FRAME_INTERVAL_MS {interval_ms}\n\n"
        + "\n".join(arrays)
        + "\nconst uint8_t *const IMG_FrameTable[IMG_FRAME_COUNT] = {\n"
        f"{table}\n"
        "};\n\n"
        "#endif /* OLED_IMAGE_H */\n"
    )


def build_main_c(frame_count: int, interval_ms: int) -> str:
    head = (
        "/*\n"
        " * main.c - STM32F103C8T6 + SSD1306 (128x64, 软件 I2C)\n"
        f" * {_header_comment()}\n"
        " */\n\n"
        '#include "stm32f10x.h"\n'
        '#include "Delay.h"\n'
        '#include "OLED.h"\n'
        '#include "OLED_Image.h"\n\n'
    )
    if frame_count <= 1:
        body = (
            "int main(void)\n"
            "{\n"
            "\tOLED_Init();\n\n"
            "\t/* 整屏显示一张图片 */\n"
            "\tOLED_ShowImage(0, 0, IMG_WIDTH, IMG_HEIGHT, IMG_FrameTable[0]);\n"
            "\tOLED_Update();\n\n"
            "\twhile (1)\n"
            "\t{\n"
            "\t}\n"
            "}\n"
        )
    else:
        body = (
            "int main(void)\n"
            "{\n"
            "\tuint16_t i = 0;\n\n"
            "\tOLED_Init();\n\n"
            "\twhile (1)\n"
            "\t{\n"
            "\t\tOLED_ShowImage(0, 0, IMG_WIDTH, IMG_HEIGHT, IMG_FrameTable[i]);\n"
            "\t\tOLED_Update();\n"
            "\t\tOLED_Clear();\n\n"
            "\t\tif (++i >= IMG_FRAME_COUNT)\n"
            "\t\t{\n"
            "\t\t\ti = 0;\n"
            "\t\t}\n"
            f"\t\tDelay_ms(IMG_FRAME_INTERVAL_MS);\n"
            "\t}\n"
            "}\n"
        )
    return head + body


def build_oled_config(pins: PinConfig) -> str:
    scl_port, scl_pin, scl_clk = pin_parts(pins.scl)
    sda_port, sda_pin, sda_clk = pin_parts(pins.sda)
    return (
        "/*\n"
        " * oled_config.h - OLED 引脚与通信参数\n"
        f" * {_header_comment()}\n"
        " * 需要改接线时可直接改这里，重新编译即可\n"
        " */\n\n"
        "#ifndef OLED_CONFIG_H\n"
        "#define OLED_CONFIG_H\n\n"
        '#include "stm32f10x.h"\n\n'
        f"/* SCL 接 {pins.scl} */\n"
        f"#define OLED_SCL_PORT        {scl_port}\n"
        f"#define OLED_SCL_PIN         {scl_pin}\n"
        f"#define OLED_SCL_CLK         {scl_clk}\n\n"
        f"/* SDA 接 {pins.sda} */\n"
        f"#define OLED_SDA_PORT        {sda_port}\n"
        f"#define OLED_SDA_PIN         {sda_pin}\n"
        f"#define OLED_SDA_CLK         {sda_clk}\n\n"
        "/* I2C 从机地址：0x78 = 0x3C<<1（模块背面默认 0x3C），0x7A = 0x3D<<1 */\n"
        f"#define OLED_I2C_ADDR        {pins.i2c_addr}\n\n"
        "/* 列偏移：SSD1306（0.96 寸）填 0；SH1106（1.3 寸）填 2 */\n"
        f"#define OLED_COL_OFFSET      {pins.col_offset}\n\n"
        "#endif /* OLED_CONFIG_H */\n"
    )


def build_oled_c(pins: PinConfig) -> str:
    template = (TEMPLATE_DIR / "Hardware" / "OLED.c.tpl").read_text(encoding="utf-8")
    jtag_pins = {"PA15", "PB3", "PB4"}
    if {pins.scl, pins.sda} & jtag_pins:
        jtag = (
            "\t/* 用到了 JTAG 引脚，关闭 JTAG 只保留 SWD */\n"
            "\tRCC_APB2PeriphClockCmd(RCC_APB2Periph_AFIO, ENABLE);\n"
            "\tGPIO_PinRemapConfig(GPIO_Remap_SWJ_JTAGDisable, ENABLE);\n"
        )
    else:
        jtag = ""
    return template.replace("{{JTAG_REMAP}}", jtag)


def _cn(text: str) -> str:
    """C 注释里的中文无害，这里只做换行/星号转义。"""
    return text.replace("*/", "* /").replace("\n", " ")


def _patch_uvprojx(path: Path, project_name: str, pack_version: str | None) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    text = text.replace("<OutputName>Project</OutputName>", f"<OutputName>{project_name}</OutputName>")
    text = text.replace("<CreateHexFile>0</CreateHexFile>", "<CreateHexFile>1</CreateHexFile>")
    if pack_version:
        text = re.sub(r"<PackID>Keil\.STM32F1xx_DFP[^<]*</PackID>",
                      f"<PackID>Keil.STM32F1xx_DFP.{pack_version}</PackID>", text)
    path.write_text(text, encoding="utf-8")


def estimate_flash(total_bytes: int) -> bool:
    """大致估算是否超出 MDK-Lite 的体积限制。"""
    base = 16 * 1024  # 库 + 字库 + 驱动
    return base + total_bytes > FLASH_LIMIT_WARN


def generate(out_dir: Path, project_name: str, frames: list[Frame], pins: PinConfig,
             interval_ms: int = 100, pack_version: str | None = None) -> GenerateResult:
    if not frames:
        raise ValueError("没有可用的图片")
    name = sanitize_name(project_name)
    out_dir = Path(out_dir)
    if out_dir.name != name:
        out_dir = out_dir / name
    project_dir = out_dir
    project_dir.mkdir(parents=True, exist_ok=True)

    # 1. 拷贝基础工程（库、启动文件、驱动）
    for folder in ("Library", "Start", "System", "User", "Hardware"):
        src = TEMPLATE_DIR / folder
        dst = project_dir / folder
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    # 2. 覆盖生成的文件
    config_file = project_dir / "Hardware" / "oled_config.h"
    config_file.write_text(build_oled_config(pins), encoding="utf-8")

    oled_c = project_dir / "Hardware" / "OLED.c"
    oled_c.write_text(build_oled_c(pins), encoding="utf-8")

    header_file = project_dir / "User" / "OLED_Image.h"
    total_bytes = sum(len(f.data or b"") for f in frames)
    header_file.write_text(build_image_header(frames, interval_ms), encoding="utf-8")

    main_file = project_dir / "User" / "main.c"
    main_file.write_text(build_main_c(len(frames), interval_ms), encoding="utf-8")

    # 3. 工程文件
    project_file = project_dir / f"{name}.uvprojx"
    opt_file = project_dir / f"{name}.uvoptx"
    for src, dst in ((TEMPLATE_DIR / "Project.uvprojx", project_file),
                     (TEMPLATE_DIR / "Project.uvoptx", opt_file),
                     (TEMPLATE_DIR / "keilkill.bat", project_dir / "keilkill.bat")):
        if dst.exists():
            dst.unlink()
        shutil.copy2(src, dst)
    _patch_uvprojx(project_file, name, pack_version)
    # uvoptx 里没有项目名引用，直接可用

    warnings = [text for _, text in pin_warnings(pins)]
    return GenerateResult(
        project_file=project_file,
        project_dir=project_dir,
        header_file=header_file,
        main_file=main_file,
        total_bytes=total_bytes,
        warnings=warnings,
    )
