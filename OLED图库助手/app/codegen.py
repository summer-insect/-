"""把处理好的点阵生成一套可直接编译的 Keil 图库工程。"""

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

# ---------------------------------------------------------------- 容量约束
# STM32F103C8T6：64KB Flash。点阵以 const 数组编译进固件，占用的是 Flash 而非 RAM。
FLASH_TOTAL = 64 * 1024
PROGRAM_RESERVE = 8 * 1024          # 库 + 驱动 + 字库 + EC11 解码，实测约 4.5KB，留余量
MAX_IMAGES = (FLASH_TOTAL - PROGRAM_RESERVE) // 1024 - 1   # 55 张
LITE_MAX_IMAGES = (32 * 1024 - PROGRAM_RESERVE) // 1024 - 1  # 23 张（MDK-Lite 32KB 限制）

JTAG_PINS = {"PA15", "PB3", "PB4"}
SWD_PINS = {"PA13", "PA14"}


@dataclass
class PinConfig:
    sda: str = "PB9"
    scl: str = "PB8"
    i2c_addr: str = "0x78"   # 0x78 = 0x3C<<1
    col_offset: int = 0      # SSD1306 0.96 寸为 0，SH1106 1.3 寸为 2


@dataclass
class EncoderConfig:
    a: str = "PA0"
    b: str = "PA1"
    button: str = "PA2"
    button_enabled: bool = True
    reverse: bool = False
    steps_per_detent: int = 4
    scan_ms: int = 1


@dataclass
class GenerateResult:
    project_file: Path
    project_dir: Path
    header_file: Path
    main_file: Path
    total_bytes: int
    warnings: list[str] = field(default_factory=list)
    image_count: int = 0


def pin_parts(pin: str) -> tuple[str, str, str]:
    """'PB9' -> ('GPIOB', 'GPIO_Pin_9', 'RCC_APB2Periph_GPIOB')"""
    match = re.fullmatch(r"P([ABC])(\d{1,2})", pin.strip().upper())
    if not match:
        raise ValueError(f"无法识别的引脚：{pin}")
    port, number = match.group(1), int(match.group(2))
    if port == "C" and number not in (13, 14, 15):
        raise ValueError(f"GPIOC 只能用 13~15：{pin}")
    return PORTS[port], f"GPIO_Pin_{number}", CLOCKS[port]


def sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff-]", "_", name.strip())
    return cleaned or "OLED_Gallery"


def _all_pins(pins: PinConfig, encoder: EncoderConfig) -> list[tuple[str, str]]:
    """返回 [(引脚, 用途描述)]"""
    items = [(pins.scl, "OLED SCL"), (pins.sda, "OLED SDA"),
             (encoder.a, "编码器 A"), (encoder.b, "编码器 B")]
    if encoder.button_enabled:
        items.append((encoder.button, "编码器按键"))
    return items


def pin_warnings(pins: PinConfig, encoder: EncoderConfig) -> list[tuple[str, str]]:
    """检查引脚冲突，返回 [(level, 说明)]，level 为 error / warn / info"""
    items: list[tuple[str, str]] = []
    all_pins = _all_pins(pins, encoder)
    names = [p for p, _ in all_pins]

    seen: set[str] = set()
    for pin, usage in all_pins:
        if names.count(pin) > 1 and pin not in seen:
            seen.add(pin)
            uses = "、".join(u for p, u in all_pins if p == pin)
            items.append(("error", f"{pin} 被多个功能占用：{uses}"))

    for pin, usage in all_pins:
        if pin in SWD_PINS:
            items.append(("error", f"{pin} 是 SWD 调试口（{usage}），占用后无法再烧录"))
        elif pin in JTAG_PINS:
            items.append(("warn", f"{pin} 是 JTAG 引脚（{usage}），生成代码会自动关闭 JTAG 保留 SWD"))
        elif pin in ("PA9", "PA10"):
            items.append(("info", f"{pin} 同时是 USART1，若用串口会冲突（{usage}）"))
        elif pin in ("PC13", "PC14", "PC15"):
            items.append(("info", f"{pin} 驱动能力较弱，但接编码器足够（{usage}）"))

    return items


def _header_comment() -> str:
    return f"由 OLED 图库助手 于 {datetime.now():%Y-%m-%d %H:%M} 生成"


def _format_bytes(data: bytes, per_line: int = 16) -> str:
    lines = []
    for i in range(0, len(data), per_line):
        chunk = data[i:i + per_line]
        lines.append("\t" + ", ".join(f"0x{b:02X}" for b in chunk) + ",")
    return "\n".join(lines)


def build_gallery_header(frames: list[Frame]) -> str:
    per_frame = 128 * 64 // 8
    count = len(frames)
    arrays = []
    for index, frame in enumerate(frames):
        data = frame.data or b""
        arrays.append(
            f"/* 第 {index + 1} 张：{frame.size[0]}x{frame.size[1]} 原图，占 {len(data)} 字节 */\n"
            f"const uint8_t GAL_Frame{index:02d}[GAL_BYTES_PER] = {{\n"
            f"{_format_bytes(data)}\n"
            f"}};\n"
        )
    table = ",\n".join(f"\tGAL_Frame{i:02d}" for i in range(count))
    return (
        "/*\n"
        " * OLED_Gallery.h - 图库点阵数据\n"
        f" * {_header_comment()}\n"
        f" * 共 {count} 张，每张 {per_frame} 字节，合计 {count * per_frame} 字节（{count}KB）\n"
        " * 数据格式：纵向 8 点一页，低位在上（bit0 为页内第一行），bit=1 点亮\n"
        " * 注意：本文件只应被 main.c 包含一次\n"
        " */\n\n"
        "#ifndef OLED_GALLERY_H\n"
        "#define OLED_GALLERY_H\n\n"
        '#include "stm32f10x.h"\n\n'
        "#define GAL_WIDTH             128\n"
        "#define GAL_HEIGHT            64\n"
        f"#define GAL_BYTES_PER         {per_frame}\n"
        f"#define GAL_COUNT             {count}\n\n"
        + "\n".join(arrays)
        + "\n"
        "const uint8_t *const GAL_ImageTable[GAL_COUNT] = {\n"
        f"{table}\n"
        "};\n\n"
        "#endif\n"
    )


def build_main_c(count: int) -> str:
    return (
        "/*\n"
        " * main.c - 图库模式：EC11 旋转编码器切换图片\n"
        f" * {_header_comment()}\n"
        " *\n"
        " * 上电显示第 1 张，之后只有转动编码器才换图；\n"
        " * 本文件没有任何定时轮播 / 自动播放代码。\n"
        " *\n"
        " * 操作：\n"
        " *   旋转编码器     上一张 / 下一张（到头后回到另一端）\n"
        " *   按下编码器     显示当前序号 1 秒，期间旋转可直接切图\n"
        " */\n\n"
        '#include "stm32f10x.h"\n'
        '#include "Delay.h"\n'
        '#include "OLED.h"\n'
        '#include "oled_config.h"\n'
        '#include "Encoder.h"\n'
        '#include "OLED_Gallery.h"\n\n'
        "/* 当前显示到第几张 */\n"
        "static uint16_t s_index = 0;\n\n"
        "/* 显示第 index 张 */\n"
        "static void Gallery_Show(uint16_t index)\n"
        "{\n"
        "\tOLED_ShowImage(0, 0, GAL_WIDTH, GAL_HEIGHT, GAL_ImageTable[index]);\n"
        "\tOLED_Update();\n"
        "}\n\n"
        "/* 显示「序号/总数」提示页 */\n"
        "static void Gallery_ShowInfo(void)\n"
        "{\n"
        "\tOLED_Clear();\n"
        '\tOLED_ShowString(36, 8, "GALLERY", OLED_8X16);\n'
        "\tOLED_ShowNum(44, 32, (uint32_t)(s_index + 1), 2, OLED_8X16);\n"
        '\tOLED_ShowString(60, 32, "/", OLED_8X16);\n'
        "\tOLED_ShowNum(68, 32, GAL_COUNT, 2, OLED_8X16);\n"
        "\tOLED_Update();\n"
        "}\n\n"
        "/* 切换 step 张，越界时首尾循环 */\n"
        "static void Gallery_Step(int8_t step)\n"
        "{\n"
        "\tint16_t next = (int16_t)s_index + (int16_t)step * ENC_DIR;\n\n"
        "\twhile (next < 0)\n"
        "\t{\n"
        "\t\tnext += GAL_COUNT;\n"
        "\t}\n"
        "\twhile (next >= GAL_COUNT)\n"
        "\t{\n"
        "\t\tnext -= GAL_COUNT;\n"
        "\t}\n\n"
        "\ts_index = (uint16_t)next;\n"
        "\tGallery_Show(s_index);\n"
        "}\n\n"
        "int main(void)\n"
        "{\n"
        "\tint8_t step;\n\n"
        "\tOLED_Init();\n"
        "\tEncoder_Init();\n\n"
        "\tOLED_Clear();\n"
        "\tGallery_Show(0);\n\n"
        "\twhile (1)\n"
        "\t{\n"
        "\t\t/* 主循环只做一件事：有旋转步进才切图，否则保持当前画面 */\n"
        "\t\tstep = Encoder_GetStep();\n"
        "\t\tif (step != 0)\n"
        "\t\t{\n"
        "\t\t\tGallery_Step(step);\n"
        "\t\t}\n\n"
        "\t\tif (Encoder_ButtonEvent() != 0)\n"
        "\t\t{\n"
        "\t\t\tuint16_t waited = 0;\n\n"
        "\t\t\tGallery_ShowInfo();\n"
        "\t\t\twhile (waited < 1000)\n"
        "\t\t\t{\n"
        "\t\t\t\tstep = Encoder_GetStep();\n"
        "\t\t\t\tif (step != 0)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tGallery_Step(step);\n"
        "\t\t\t\t\tbreak;\n"
        "\t\t\t\t}\n"
        "\t\t\t\tDelay_ms(10);\n"
        "\t\t\t\twaited += 10;\n"
        "\t\t\t}\n"
        "\t\t\tif (waited >= 1000)\n"
        "\t\t\t{\n"
        "\t\t\t\tGallery_Show(s_index);\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t}\n"
        "}\n"
    )


def build_selftest_main_c() -> str:
    return (
        "/*\n"
        " * main.c - EC11 接线自检（不含图库数据）\n"
        f" * {_header_comment()}\n"
        " *\n"
        " * 屏幕上四行：\n"
        " *   A / B    编码器两相实时电平，静止时通常都是 1，转动时应各自翻转\n"
        " *   ISR      1ms 定时中断执行次数，正常会飞快增长\n"
        " *   EDGE     两相跳变累计数，转动时应有增减\n"
        " *   STEP     解码出来的步数，转动时每格 +1 / -1\n"
        " *\n"
        " * 判读方法：\n"
        " *   A/B 会翻转、EDGE 会变、STEP 也会变  -> 接线正常\n"
        " *   A/B 一直不变                        -> 线没接对 / 模块没供电 / C 接错\n"
        " *   A/B 会变但 EDGE 一直是 0            -> 定时中断没跑（软件问题）\n"
        " *   EDGE 会变但 STEP 一直是 0           -> 每格脉冲数设大了，改成 2\n"
        " */\n\n"
        '#include "stm32f10x.h"\n'
        '#include "Delay.h"\n'
        '#include "OLED.h"\n'
        '#include "oled_config.h"\n'
        '#include "Encoder.h"\n\n'
        "int main(void)\n"
        "{\n"
        "\tuint8_t  ab = 0;\n"
        "\tint8_t   step;\n"
        "\tint32_t  steps = 0;\n\n"
        "\tOLED_Init();\n"
        "\tEncoder_Init();\n"
        "\tEncoder_ResetStat();\n\n"
        "\tOLED_Clear();\n"
        '\tOLED_ShowString(0, 0, "EC11 SELF TEST", OLED_8X16);\n\n'
        "\twhile (1)\n"
        "\t{\n"
        "\t\tstep = Encoder_GetStep();\n"
        "\t\tif (step != 0)\n"
        "\t\t{\n"
        "\t\t\tsteps += step;\n"
        "\t\t}\n\n"
        "\t\tab = Encoder_ReadAB();\n\n"
        '\t\tOLED_ShowString(0, 16, "A", OLED_8X16);\n'
        "\t\tOLED_ShowNum(8, 16, (uint32_t)((ab >> 1) & 1), 1, OLED_8X16);\n"
        '\t\tOLED_ShowString(24, 16, "B", OLED_8X16);\n'
        "\t\tOLED_ShowNum(32, 16, (uint32_t)(ab & 1), 1, OLED_8X16);\n"
        '\t\tOLED_ShowString(48, 16, "ISR", OLED_8X16);\n'
        "\t\tOLED_ShowNum(72, 16, Encoder_GetIsrCount() % 10000, 4, OLED_8X16);\n\n"
        '\t\tOLED_ShowString(0, 32, "EDGE", OLED_8X16);\n'
        "\t\tOLED_ShowSignedNum(40, 32, Encoder_GetEdgeCount() % 10000, 4, OLED_8X16);\n"
        '\t\tOLED_ShowString(0, 48, "STEP", OLED_8X16);\n'
        "\t\tOLED_ShowSignedNum(40, 48, steps % 10000, 4, OLED_8X16);\n\n"
        "\t\tOLED_Update();\n"
        "\t\tDelay_ms(50);\n"
        "\t}\n"
        "}\n"
    )


def _pin_macro(prefix: str, pin: str) -> str:
    port, pin_name, clk = pin_parts(pin)
    return (
        f"#define {prefix}_PORT        {port}\n"
        f"#define {prefix}_PIN         {pin_name}\n"
        f"#define {prefix}_CLK         {clk}\n"
    )


def build_oled_config(pins: PinConfig, encoder: EncoderConfig) -> str:
    return (
        "/*\n"
        " * oled_config.h - OLED 与 EC11 的引脚、通信参数\n"
        f" * {_header_comment()}\n"
        " * 需要改接线时直接改这里，重新编译即可\n"
        " */\n\n"
        "#ifndef OLED_CONFIG_H\n"
        "#define OLED_CONFIG_H\n\n"
        '#include "stm32f10x.h"\n\n'
        "/* ===== OLED（软件 I2C）===== */\n"
        f"/* SCL 接 {pins.scl} */\n"
        + _pin_macro("OLED_SCL", pins.scl)
        + f"\n/* SDA 接 {pins.sda} */\n"
        + _pin_macro("OLED_SDA", pins.sda)
        + "\n/* I2C 从机地址：0x78 = 0x3C<<1（模块默认 0x3C），0x7A = 0x3D<<1 */\n"
        f"#define OLED_I2C_ADDR        {pins.i2c_addr}\n\n"
        "/* 列偏移：SSD1306（0.96 寸）填 0；SH1106（1.3 寸）填 2 */\n"
        f"#define OLED_COL_OFFSET      {pins.col_offset}\n\n"
        "/* ===== EC11 旋转编码器 ===== */\n"
        "/* C（公共端）接 GND，不接单片机；A/B 用内部上拉，空闲为高 */\n"
        f"/* A 相接 {encoder.a} */\n"
        + _pin_macro("ENC_A", encoder.a)
        + f"\n/* B 相接 {encoder.b} */\n"
        + _pin_macro("ENC_B", encoder.b)
        + (
            f"\n/* 按键接 {encoder.button}；不用按键时把 ENC_SW_ENABLE 改成 0 */\n"
            "#define ENC_SW_ENABLE        1\n"
            + _pin_macro("ENC_SW", encoder.button)
            if encoder.button_enabled
            else "\n/* 未启用按键 */\n#define ENC_SW_ENABLE        0\n"
        )
        + "\n/* 旋转方向：1 = 顺时针切下一张，-1 = 反过来 */\n"
        f"#define ENC_DIR              ({-1 if encoder.reverse else 1})\n\n"
        "/* 每格脉冲数：4 = 完整正交周期（多数 EC11 模块），2 = 半周期\n"
        " * 转一格跳两张就把这个值改小，转了没反应就改大 */\n"
        f"#define ENC_STEPS_PER_DETENT {encoder.steps_per_detent}\n\n"
        "/* 扫描周期（毫秒），一般不用改 */\n"
        f"#define ENC_SCAN_MS          {encoder.scan_ms}\n\n"
        "#endif /* OLED_CONFIG_H */\n"
    )


def build_oled_c(pins: PinConfig, encoder: EncoderConfig) -> str:
    template = (TEMPLATE_DIR / "Hardware" / "OLED.c.tpl").read_text(encoding="utf-8")
    used = {pins.scl, pins.sda, encoder.a, encoder.b}
    if encoder.button_enabled:
        used.add(encoder.button)

    if used & JTAG_PINS:
        jtag = (
            "\t/* 用到了 JTAG 引脚，关闭 JTAG 只保留 SWD */\n"
            "\tRCC_APB2PeriphClockCmd(RCC_APB2Periph_AFIO, ENABLE);\n"
            "\tGPIO_PinRemapConfig(GPIO_Remap_SWJ_JTAGDisable, ENABLE);\n"
        )
    else:
        jtag = ""
    return template.replace("{{JTAG_REMAP}}", jtag)


def _patch_uvprojx(path: Path, project_name: str, pack_version: str | None) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n")

    text = text.replace("<OutputName>Project</OutputName>", f"<OutputName>{project_name}</OutputName>")
    text = text.replace("<CreateHexFile>0</CreateHexFile>", "<CreateHexFile>1</CreateHexFile>")
    if pack_version:
        text = re.sub(r"<PackID>Keil\.STM32F1xx_DFP[^<]*</PackID>",
                      f"<PackID>Keil.STM32F1xx_DFP.{pack_version}</PackID>", text)

    # 模板里遗留的 Showmp4.h 引用（文件已不存在），清掉避免 Keil 报找不到文件
    text = text.replace(
        "            <File>\n"
        "              <FileName>Showmp4.h</FileName>\n"
        "              <FileType>5</FileType>\n"
        "              <FilePath>.\\Hardware\\Showmp4.h</FilePath>\n"
        "            </File>\n", "")

    # 把 Encoder.c/.h 挂进 Hardware 分组
    oled_block = (
        "            <File>\n"
        "              <FileName>OLED.c</FileName>\n"
        "              <FileType>1</FileType>\n"
        "              <FilePath>.\\Hardware\\OLED.c</FilePath>\n"
        "            </File>\n")
    encoder_block = (
        oled_block
        + "            <File>\n"
        "              <FileName>Encoder.c</FileName>\n"
        "              <FileType>1</FileType>\n"
        "              <FilePath>.\\Hardware\\Encoder.c</FilePath>\n"
        "            </File>\n"
        "            <File>\n"
        "              <FileName>Encoder.h</FileName>\n"
        "              <FileType>5</FileType>\n"
        "              <FilePath>.\\Hardware\\Encoder.h</FilePath>\n"
        "            </File>\n")
    if "Encoder.c" not in text:
        text = text.replace(oled_block, encoder_block)

    with open(path, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(text)


def estimate_rom(total_bytes: int) -> int:
    """粗略估算编译后的 Flash 占用（字节），用于提前拦截明显超限。"""
    return PROGRAM_RESERVE + total_bytes


def generate(out_dir: Path, project_name: str, frames: list[Frame], pins: PinConfig,
             encoder: EncoderConfig, pack_version: str | None = None,
             selftest: bool = False) -> GenerateResult:
    if not frames and not selftest:
        raise ValueError("没有可用的图片")

    name = sanitize_name(project_name)
    out_dir = Path(out_dir)
    if out_dir.name != name:
        out_dir = out_dir / name
    project_dir = out_dir
    project_dir.mkdir(parents=True, exist_ok=True)

    # 1. 拷贝基础工程（库、启动文件、驱动、EC11 驱动）
    for folder in ("Library", "Start", "System", "User", "Hardware"):
        src = TEMPLATE_DIR / folder
        dst = project_dir / folder
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    # 2. 覆盖生成的文件
    (project_dir / "Hardware" / "oled_config.h").write_text(
        build_oled_config(pins, encoder), encoding="utf-8")

    (project_dir / "Hardware" / "OLED.c").write_text(
        build_oled_c(pins, encoder), encoding="utf-8")

    header_file = project_dir / "User" / "OLED_Gallery.h"
    total_bytes = sum(len(f.data or b"") for f in frames)
    if selftest:
        header_file.write_text(
            "/* 自检固件不包含图库数据 */\n"
            "#ifndef OLED_GALLERY_H\n#define OLED_GALLERY_H\n#endif\n",
            encoding="utf-8")
    else:
        header_file.write_text(build_gallery_header(frames), encoding="utf-8")

    main_file = project_dir / "User" / "main.c"
    main_file.write_text(build_selftest_main_c() if selftest else build_main_c(len(frames)),
                         encoding="utf-8")

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

    warnings = [text for _, text in pin_warnings(pins, encoder)]
    return GenerateResult(
        project_file=project_file,
        project_dir=project_dir,
        header_file=header_file,
        main_file=main_file,
        total_bytes=total_bytes,
        warnings=warnings,
        image_count=len(frames),
    )
