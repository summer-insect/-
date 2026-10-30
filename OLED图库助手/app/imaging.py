"""图像处理引擎：把任意图片处理成 SSD1306 的 128x64 单色点阵。

坐标与驱动保持一致：左上角 (0,0)，X 向右 0~127，Y 向下 0~63。
数据格式：纵向 8 点一页，低位在上（bit0 是该页最上面那一行），
bit=1 表示该像素点亮。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageSequence

OLED_W = 128
OLED_H = 64
FRAME_BYTES = OLED_W * OLED_H // 8  # 1024

# 抖动算法
METHOD_THRESHOLD = "threshold"
METHOD_BAYER = "bayer"
METHOD_FLOYD = "floyd"
METHOD_MEAN = "mean"

METHOD_LABELS = {
    METHOD_THRESHOLD: "固定阈值",
    METHOD_BAYER: "有序抖动 4x4",
    METHOD_FLOYD: "误差扩散 Floyd",
    METHOD_MEAN: "自适应均值",
}

FIT_LABELS = {"fit": "等比适应", "fill": "裁剪填满", "stretch": "拉伸铺满"}

BAYER4 = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


@dataclass
class RenderOptions:
    fit: str = "fit"
    scale: float = 1.0
    offset_x: int = 0
    offset_y: int = 0
    rotate: int = 0
    flip_h: bool = False
    flip_v: bool = False
    brightness: int = 0      # -100 ~ 100
    contrast: int = 0        # -100 ~ 100
    method: str = METHOD_THRESHOLD
    threshold: int = 128     # 0 ~ 255
    invert: bool = False
    autocrop: bool = True
    nearest: bool = False
    sharpen: int = 60        # 收缩放后的锐化强度 0~100：大图缩小时把细节找回来

    def copy(self, **kw) -> "RenderOptions":
        return replace(self, **kw)


@dataclass
class Frame:
    """一个待显示的帧。"""

    path: Path | None
    image: Image.Image
    name: str
    mono: Image.Image | None = None   # 处理后的 128x64，模式 "1"，255=点亮
    data: bytes | None = None         # 处理后的点阵数据

    @property
    def size(self) -> tuple[int, int]:
        return self.image.size


def load_frames(path: str | Path) -> list[Frame]:
    """读取图片；GIF 会拆成多帧。"""
    path = Path(path)
    frames: list[Frame] = []
    img = Image.open(path)
    if getattr(img, "is_animated", False):
        for index, part in enumerate(ImageSequence.Iterator(img)):
            frames.append(Frame(path=path, image=part.convert("RGBA"), name=f"{path.stem} #{index + 1}"))
    else:
        frames.append(Frame(path=path, image=img.convert("RGBA"), name=path.stem))
    return frames


def _flatten(img: Image.Image) -> Image.Image:
    """把透明背景铺成纯色后转灰度。

    默认铺白底（大多数贴图是深色内容），但如果图片大半透明、
    且可见部分是浅色的（白色图标、发光字），就铺黑底，否则会整张消失。
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    background = (255, 255, 255, 255)
    # 只看缩小后的缩略图，避免大图逐像素统计
    thumb = img.copy()
    thumb.thumbnail((96, 96))
    alpha = list(thumb.getchannel("A").getdata())
    total = max(1, len(alpha))
    transparent = sum(1 for a in alpha if a < 24) / total
    if transparent > 0.15:
        gray = list(thumb.convert("L").getdata())
        visible = [v for v, a in zip(gray, alpha) if a >= 24]
        if visible and sum(visible) / len(visible) > 170:
            background = (0, 0, 0, 255)

    canvas = Image.new("RGBA", img.size, background)
    canvas.alpha_composite(img)
    return canvas.convert("L")


def _autocrop(gray: Image.Image, bg_threshold: int = 246) -> Image.Image:
    """裁掉四周纯白留白，只保留画面主体。"""
    mask = gray.point(lambda v: 0 if v >= bg_threshold else 255)
    box = mask.getbbox()
    if not box:
        return gray
    # 四周留 1 像素余量，避免裁剪到笔画边缘
    left, top, right, bottom = box
    left = max(0, left - 1)
    top = max(0, top - 1)
    right = min(gray.width, right + 1)
    bottom = min(gray.height, bottom + 1)
    if right - left < 2 or bottom - top < 2:
        return gray
    return gray.crop((left, top, right, bottom))


def _progressive_resize(gray: Image.Image, size: tuple[int, int]) -> Image.Image:
    """逐级减半，缩到约 1~2 倍目标尺寸。

    一次性把 4000px 的图用 LANCZOS 缩到 128px，插值核会跨几十个像素取样，
    结果是振铃 + 细节被平均成一团灰。每步减半都是面积平均（BOX），
    等价于对整块像素求均值，色调最忠实，也不会产生振铃。
    """
    tw, th = size
    cur = gray
    while cur.width > tw * 2 and cur.height > th * 2:
        cur = cur.resize((max(tw, cur.width // 2), max(th, cur.height // 2)), Image.Resampling.BOX)
    return cur


def _fit_into_canvas(gray: Image.Image, opts: RenderOptions) -> Image.Image:
    """按适应方式缩放到 128x64 画布，居中并应用偏移。"""
    w, h = gray.size
    scale = max(0.05, min(2.0, opts.scale))
    if opts.fit == "stretch":
        new_w = max(1, round(OLED_W * scale))
        new_h = max(1, round(OLED_H * scale))
    else:
        ratio = min(OLED_W / w, OLED_H / h) if opts.fit == "fit" else max(OLED_W / w, OLED_H / h)
        ratio *= scale
        new_w = max(1, round(w * ratio))
        new_h = max(1, round(h * ratio))

    if opts.nearest:
        # 像素画模式：不插值、不锐化，保住原始色块
        fitted = gray.resize((new_w, new_h), Image.Resampling.NEAREST) if (new_w, new_h) != (w, h) else gray
    elif new_w > w or new_h > h:
        # 放大：LANCZOS 比面积平均平滑
        fitted = gray.resize((new_w, new_h), Image.Resampling.LANCZOS)
    elif (new_w, new_h) != (w, h):
        small = _progressive_resize(gray, (new_w, new_h))
        fitted = small.resize((new_w, new_h), Image.Resampling.BOX)
    else:
        fitted = gray

    if opts.sharpen > 0 and not opts.nearest:
        # 面积平均会把边缘磨钝，缩放后补一次反锐化掩模：大图缩小时，
        # 原本被平均成浅灰的细线会被拉回阈值以下，重新变成看得见的笔画
        percent = min(250, round(opts.sharpen * 2.2))
        fitted = fitted.filter(ImageFilter.UnsharpMask(radius=1.0, percent=percent, threshold=3))

    canvas = Image.new("L", (OLED_W, OLED_H), 255)
    x = (OLED_W - new_w) // 2 + opts.offset_x
    y = (OLED_H - new_h) // 2 + opts.offset_y
    canvas.paste(fitted, (x, y))
    return canvas


def _ordered_dither(pixels: list[int], threshold: int) -> list[bool]:
    bits: list[bool] = []
    bias = (threshold - 128) * 0.6
    for y in range(OLED_H):
        row = y * OLED_W
        matrix = BAYER4[y & 3]
        for x in range(OLED_W):
            limit = (matrix[x & 3] + 0.5) * 16.0 + bias
            bits.append(pixels[row + x] < limit)
    return bits


def _floyd_steinberg(pixels: list[int], threshold: int) -> list[bool]:
    buf = [float(v) for v in pixels]
    bits: list[bool] = [False] * (OLED_W * OLED_H)
    for y in range(OLED_H):
        for x in range(OLED_W):
            i = y * OLED_W + x
            old = buf[i]
            new = 255.0 if old >= threshold else 0.0
            bits[i] = new == 0.0  # 变黑的像素作为“墨点”点亮屏幕
            err = old - new
            if x + 1 < OLED_W:
                buf[i + 1] += err * 7 / 16
            if y + 1 < OLED_H:
                if x > 0:
                    buf[i + OLED_W - 1] += err * 3 / 16
                buf[i + OLED_W] += err * 5 / 16
                if x + 1 < OLED_W:
                    buf[i + OLED_W + 1] += err / 16
    return bits


def _mean_adaptive(gray: Image.Image, threshold: int) -> list[bool]:
    # 用局部均值做参考，偏移量由阈值滑块控制（阈值越大越亮）
    blurred = gray.filter(ImageFilter.BoxBlur(6))
    src = list(gray.getdata())
    ref = list(blurred.getdata())
    delta = (128 - threshold) * 0.35
    return [src[i] < ref[i] - 6 - delta for i in range(len(src))]


def _prepare(img: Image.Image, opts: RenderOptions) -> Image.Image:
    """旋转、裁剪、缩放、调色，得到准备量化的 128x64 灰度画布。"""
    gray = _flatten(img)

    if opts.rotate:
        gray = gray.rotate(-opts.rotate, expand=True)
    if opts.flip_h:
        gray = ImageOps.mirror(gray)
    if opts.flip_v:
        gray = ImageOps.flip(gray)

    if opts.autocrop:
        gray = _autocrop(gray)

    gray = _fit_into_canvas(gray, opts)

    if opts.brightness:
        gray = ImageEnhance.Brightness(gray).enhance(max(0.0, 1 + opts.brightness / 100))
    if opts.contrast:
        gray = ImageEnhance.Contrast(gray).enhance(max(0.0, 1 + opts.contrast / 100))
    return gray


def prepare_gray(img: Image.Image, opts: RenderOptions) -> Image.Image:
    return _prepare(img, opts)


def render(img: Image.Image, opts: RenderOptions) -> Image.Image:
    """返回模式为 "1" 的 128x64 图像，255 表示点亮。"""
    gray = _prepare(img, opts)
    pixels = list(gray.getdata())
    if opts.invert:
        pixels = [255 - v for v in pixels]

    if opts.method == METHOD_BAYER:
        bits = _ordered_dither(pixels, opts.threshold)
    elif opts.method == METHOD_FLOYD:
        bits = _floyd_steinberg(pixels, opts.threshold)
    elif opts.method == METHOD_MEAN:
        bits = _mean_adaptive(gray, opts.threshold)
        if opts.invert:
            bits = [not b for b in bits]
    else:
        bits = [v < opts.threshold for v in pixels]

    mono = Image.new("1", (OLED_W, OLED_H), 0)
    mono.putdata([255 if b else 0 for b in bits])
    return mono


def otsu_threshold(gray: Image.Image) -> int:
    """大津法自动阈值：让文字/线稿/卡通图自动分出黑白。"""
    hist = gray.convert("L").histogram()
    total = sum(hist)
    if total == 0:
        return 128
    sum_all = sum(i * hist[i] for i in range(256))
    weight_bg = 0
    sum_bg = 0
    best_var = -1.0
    best_t = 128
    for t in range(256):
        weight_bg += hist[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += t * hist[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_all - sum_bg) / weight_fg
        var = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if var > best_var:
            best_var = var
            best_t = t
    return best_t


def suggest_threshold(img: Image.Image, opts: RenderOptions) -> int:
    return otsu_threshold(prepare_gray(img, opts))


def pack(mono: Image.Image) -> bytes:
    """按 SSD1306 页格式打包：8 页 x 128 列，bit0 为页内最上一行。"""
    px = mono.load()
    data = bytearray()
    for page in range(8):
        base = page * 8
        for x in range(OLED_W):
            byte = 0
            for bit in range(8):
                if px[x, base + bit]:
                    byte |= 1 << bit
            data.append(byte)
    return bytes(data)


def unpack(data: bytes) -> Image.Image:
    mono = Image.new("1", (OLED_W, OLED_H), 0)
    px = mono.load()
    for page in range(8):
        for x in range(OLED_W):
            byte = data[page * OLED_W + x]
            for bit in range(8):
                if byte & (1 << bit):
                    px[x, page * 8 + bit] = 255
    return mono


def lit_count(mono: Image.Image) -> int:
    return sum(1 for v in mono.getdata() if v)


def auto_invert_suggestion(img: Image.Image) -> bool:
    """判断是否需要反色。

    处理时按“取暗部点亮”的方式取模：白底黑线的图（截图、线稿、表情包）
    直接取暗部就是主体，无需反色；黑底亮主体的图才需要先反色。
    """
    gray = _flatten(img)
    w, h = gray.size
    # 取最外一圈像素估计背景色
    px = gray.load()
    samples = [px[x, 0] for x in range(w)] + [px[x, h - 1] for x in range(w)]
    samples += [px[0, y] for y in range(h)] + [px[w - 1, y] for y in range(h)]
    border = sum(samples) / max(1, len(samples))
    return border < 110


def process_frame(frame: Frame, opts: RenderOptions) -> Frame:
    mono = render(frame.image, opts)
    data = pack(mono)
    return replace(frame, mono=mono, data=data)


def process_all(frames: list[Frame], opts: RenderOptions) -> list[Frame]:
    return [process_frame(f, opts) for f in frames]
