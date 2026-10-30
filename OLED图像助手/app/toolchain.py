"""Keil MDK 命令行调用：定位 UV4、编译、烧录、读日志。"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

EXIT_MESSAGES = {
    0: "成功",
    1: "成功（有警告）",
    2: "存在编译错误",
    3: "编译失败（致命错误）",
    11: "无法打开工程文件",
    12: "器件不存在",
    13: "无法连接调试器/目标板",
    15: "调试器初始化失败",
    20: "License 无效或已过期",
}

SIZE_RE = re.compile(r"Program Size:\s*(.+)")
SUMMARY_RE = re.compile(r"(\d+)\s+Error\(s\),\s*(\d+)\s+Warning\(s\)")


@dataclass
class CommandResult:
    ok: bool
    code: int
    log: str
    message: str


def _registry_paths() -> list[Path]:
    paths: list[Path] = []
    try:
        import winreg
    except ImportError:
        return paths
    keys = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Keil\Products\MDK"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Keil\Products\MDK"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Keil\Products\MDK"),
    )
    for root, key in keys:
        try:
            with winreg.OpenKey(root, key) as handle:
                value, _ = winreg.QueryValueEx(handle, "Path")
                paths.append(Path(value).parent / "UV4" / "UV4.exe")
        except OSError:
            continue
    return paths


def candidates() -> list[Path]:
    found = _registry_paths()
    for drive in ("C:", "D:", "E:", "F:"):
        for folder in ("Keil_v5", "Keil", "keil5", "MDK", "MDK-ARM"):
            found.append(Path(f"{drive}/{folder}/UV4/UV4.exe"))
    found.append(Path(r"C:\Program Files (x86)\UV4\UV4.exe"))
    found.append(Path(r"C:\Program Files\UV4\UV4.exe"))
    # 环境变量里如果直接加了 UV4 目录
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry and "UV4" in entry:
            found.append(Path(entry) / "UV4.exe")
    return found


def find_uv4() -> Path | None:
    for path in candidates():
        if path.is_file():
            return path
    return None


def keil_root(uv4: Path) -> Path:
    return uv4.resolve().parent.parent


def pack_versions(uv4: Path) -> list[str]:
    pack_dir = keil_root(uv4) / "ARM" / "PACK" / "Keil" / "STM32F1xx_DFP"
    if not pack_dir.is_dir():
        return []
    versions = []
    for item in pack_dir.iterdir():
        if item.is_dir() and re.fullmatch(r"\d+(\.\d+)*", item.name):
            versions.append(item.name)
    versions.sort(key=lambda v: tuple(int(p) for p in v.split(".")), reverse=True)
    return versions


def best_pack_version(uv4: Path | None) -> str | None:
    if not uv4:
        return None
    versions = pack_versions(uv4)
    return versions[0] if versions else None


def _stream_log(log_path: Path, on_line: Callable[[str], None], position: list[int]) -> None:
    try:
        if not log_path.is_file():
            return
        with open(log_path, "rb") as handle:
            handle.seek(position[0])
            chunk = handle.read()
            position[0] = handle.tell()
    except OSError:
        return
    if not chunk:
        return
    text = chunk.decode("gbk", errors="replace").replace("\x00", "")
    for line in text.splitlines():
        line = line.rstrip()
        if line:
            on_line(line)


def _run_uv4(uv4: Path, project_file: Path, action: str, on_line: Callable[[str], None] | None = None,
             timeout: int = 300) -> CommandResult:
    log_path = project_file.parent / ("flash.log" if action == "-f" else "build.log")
    try:
        if log_path.exists():
            log_path.unlink()
    except OSError:
        pass

    command = [str(uv4), action, project_file.name, "-j0", "-o", log_path.name]
    started = time.time()
    position = [0]
    process = subprocess.Popen(
        command,
        cwd=str(project_file.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    while process.poll() is None:
        _stream_log(log_path, on_line or (lambda _: None), position)
        if time.time() - started > timeout:
            process.kill()
            return CommandResult(False, -1, "", "操作超时，已强制结束 Keil 进程")
        time.sleep(0.15)
    _stream_log(log_path, on_line or (lambda _: None), position)
    time.sleep(0.1)
    _stream_log(log_path, on_line or (lambda _: None), position)

    code = process.returncode
    try:
        log_text = log_path.read_text(encoding="gbk", errors="replace")
    except OSError:
        log_text = ""

    ok = code in (0, 1)
    if action == "-b" and code == 1:
        # 退出码 1 可能是警告，也可能确实有错误，以日志为准
        ok = "0 Error(s)" in log_text
    if action == "-f":
        ok = code == 0
        message = flash_message(log_text, code)
    else:
        message = EXIT_MESSAGES.get(code, f"退出码 {code}")
    return CommandResult(ok, code, log_text, message)


def flash_message(log_text: str, code: int) -> str:
    low = log_text.lower()
    if "target dll has been cancelled" in low or "no ulink" in low or "no st-link" in low:
        return "未检测到 ST-Link，请检查 USB 连接和驱动"
    if "cannot access target" in low or "cannot load flash" in low:
        return "连不上芯片，检查 SWDIO/SWCLK/3V3/GND 和供电"
    if "flash download failed" in low:
        return "Flash 写入被拒绝，检查芯片型号与下载算法"
    if code == 0:
        return "烧录成功"
    return EXIT_MESSAGES.get(code, f"退出码 {code}")


def build(uv4: Path, project_file: Path, on_line: Callable[[str], None] | None = None) -> CommandResult:
    return _run_uv4(uv4, Path(project_file), "-b", on_line)


def flash(uv4: Path, project_file: Path, on_line: Callable[[str], None] | None = None) -> CommandResult:
    return _run_uv4(uv4, Path(project_file), "-f", on_line)


def summary_from_log(log_text: str) -> str:
    match = SUMMARY_RE.search(log_text)
    size = SIZE_RE.search(log_text)
    parts = []
    if match:
        errors, warnings = match.group(1), match.group(2)
        parts.append(f"{errors} 个错误 / {warnings} 个警告")
    if size:
        parts.append(size.group(1).strip())
    return " · ".join(parts)


def open_in_keil(uv4: Path, project_file: Path) -> None:
    subprocess.Popen([str(uv4), str(project_file)], cwd=str(Path(project_file).parent))


def open_folder(path: Path) -> None:
    os.startfile(str(path))  # noqa: S606
