# 先检查依赖
try:
    from PIL import Image, ImageEnhance, ImageFilter
except ImportError:
    print("❌ 错误：没有安装PIL库！")
    print("请在命令行执行：pip install pillow")
    input("按回车键退出...")
    exit(1)

import os
import re

# ===================== 通用配置参数（全部可调） =====================
FRAME_FOLDER = "篮球"    # 存放帧图片的文件夹名称
OUTPUT_FILE = "Showmp4.h"  # 输出的C语言头文件名称
OLED_WIDTH = 128          # OLED屏幕宽度
OLED_HEIGHT = 64          # OLED屏幕高度
KEEP_EVERY_N_FRAME = 1    # 帧抽取间隔，每N帧保留1帧

# 画面缩放控制宏：0.1~1.0，1.0=最大铺满，0.7适中，0.5偏小
SCALE_RATIO = 1.0

# 主体填充开关：0=仅轮廓不填充；1=填充主体内部
FILL_SUBJECT = 1

# 图像二值化可调参数（解决画面扁平关键）
CONTRAST_FACTOR = 1.8     # 对比度增强，越大黑白分界越明显(推荐1.5~3.0)
FIX_THRESHOLD = 130        # 固定二值阈值，亮图调高，暗图调低(0~255)
USE_AUTO_THRESH = True     # True自适应阈值 / False固定阈值
WHITE_BG_THRESH = 240      # 空白判定阈值：灰度≥该值视为纯白背景，会被裁剪
# ===================================================================

# 自动裁剪空白，只保留画面主体
def crop_blank_border(gray_img):
    width, height = gray_img.size
    non_blank_points = []
    for x in range(width):
        for y in range(height):
            pix = gray_img.getpixel((x, y))
            if pix < WHITE_BG_THRESH:
                non_blank_points.append((x, y))
    # 图片全空白，不裁剪
    if not non_blank_points:
        return gray_img
    xs = [p[0] for p in non_blank_points]
    ys = [p[1] for p in non_blank_points]
    left = min(xs)
    right = max(xs)
    top = min(ys)
    bottom = max(ys)
    crop_box = (left, top, right + 1, bottom + 1)
    crop_img = gray_img.crop(crop_box)
    return crop_img

# 图片预处理+SSD1306标准取模（纵向8点，低位在前）
def image_to_oled_data(image):
    # 1. 转灰度 + 裁掉四周空白
    gray_img = image.convert("L")
    crop_img = crop_blank_border(gray_img)
    crop_w, crop_h = crop_img.size

    # 2. 等比例缩放主体，由SCALE_RATIO控制大小
    # 计算原图主体能铺满屏幕的最大尺寸
    max_w = OLED_WIDTH * SCALE_RATIO
    max_h = OLED_HEIGHT * SCALE_RATIO
    scale = min(max_w / crop_w, max_h / crop_h)
    new_w = int(crop_w * scale)
    new_h = int(crop_h * scale)
    resized_subject = crop_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # 3. 创建全屏白底画布，缩放后的主体居中放置
    canvas = Image.new("L", (OLED_WIDTH, OLED_HEIGHT), 255)
    offset_x = (OLED_WIDTH - new_w) // 2
    offset_y = (OLED_HEIGHT - new_h) // 2
    canvas.paste(resized_subject, (offset_x, offset_y))

    # 4. 增强对比度
    contrast_enhancer = ImageEnhance.Contrast(canvas)
    gray_img = contrast_enhancer.enhance(CONTRAST_FACTOR)

    # 5. 二值化处理二选一
    if USE_AUTO_THRESH:
        gray_img = gray_img.filter(ImageFilter.ModeFilter(size=3))
        img_bin = gray_img.point(lambda x: 0 if x < FIX_THRESHOLD else 255, "1")
    else:
        img_bin = gray_img.point(lambda x: 0 if x < FIX_THRESHOLD else 255, "1")

    # ========== 新增填充逻辑 ==========
    if FILL_SUBJECT == 1:
        # 反转像素：原本线条黑(0)变白，空白白(255)变黑，实现主体填充
        img_bin = img_bin.point(lambda x: 255 if x == 0 else 0, "1")

    data = []
    # SSD1306分页取模逻辑不变
    for page in range(OLED_HEIGHT // 8):
        for x in range(OLED_WIDTH):
            byte = 0
            for bit in range(8):
                y = page * 8 + bit
                # 黑色像素点亮屏幕，白色熄灭
                if img_bin.getpixel((x, y)) == 0:
                    byte |= (1 << bit)
            data.append(byte)
    return data

# 提取文件名数字用于帧顺序排序
def extract_number(filename):
    match = re.search(r'\d+', filename)
    return int(match.group()) if match else 0

# 主处理函数
def main():
    print("=" * 50)
    print("OLED动画帧通用取模工具 v4.0（缩放可控+自动裁空白）")
    print("=" * 50)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"📂 脚本所在目录：{script_dir}")
    
    frame_folder_full = os.path.join(script_dir, FRAME_FOLDER)
    output_file_full = os.path.join(script_dir, OUTPUT_FILE)
    
    print(f"📂 图片文件夹路径：{frame_folder_full}")
    print(f"📄 输出头文件路径：{output_file_full}")
    print(f"⚙️  主体缩放比例：{SCALE_RATIO} (1.0=最大，0.7适中)")
    print(f"⚙️  主体填充模式：{'填充猫咪' if FILL_SUBJECT == 1 else '仅轮廓不填充'}")
    print(f"⚙️  对比度增强系数：{CONTRAST_FACTOR}")
    print(f"⚙️  自适应二值化：{'开启' if USE_AUTO_THRESH else '关闭'}")
    print(f"⚙️  空白背景判定阈值：{WHITE_BG_THRESH}")
    print()
    
    if not os.path.isdir(frame_folder_full):
        print(f"❌ 错误：找不到文件夹 '{FRAME_FOLDER}'")
        print("请将bmp/png帧图片放入脚本同目录下该文件夹")
        input("按回车键退出...")
        return
    
    frame_files = [f for f in os.listdir(frame_folder_full)
                   if f.lower().endswith(('.bmp', '.png'))]
    
    if not frame_files:
        print(f"❌ 错误：文件夹内未找到bmp/png图片")
        input("按回车键退出...")
        return
    
    print(f"✅ 读取到原始图片：{len(frame_files)} 张")
    frame_files.sort(key=extract_number)
    print(f"✅ 帧图片按序号排序完成")
    
    selected_frames = frame_files[::KEEP_EVERY_N_FRAME]
    frame_count = len(selected_frames)
    single_frame_bytes = OLED_WIDTH * OLED_HEIGHT // 8
    print(f"✅ 筛选后保留动画总帧数：{frame_count} (每{KEEP_EVERY_N_FRAME}帧取1帧)")
    print(f"💾 动画单帧大小：{single_frame_bytes} 字节")
    print()
    
    print("🔄 正在生成动画数据头文件...")
    try:
        with open(output_file_full, 'w', encoding='utf-8') as f:
            f.write("#ifndef ANIMATION_FRAMES_H\n")
            f.write("#define ANIMATION_FRAMES_H\n\n")
            f.write("#include \"stm32f10x.h\"\n\n")
            f.write(f"#define ANIM_FRAME_COUNT    {frame_count}    // 动画总帧数\n")
            f.write(f"#define ANIM_FRAME_BYTES    {single_frame_bytes}  // 单帧图像字节大小\n\n")

            for i, frame_file in enumerate(selected_frames):
                img_path = os.path.join(frame_folder_full, frame_file)
                print(f"  处理第 {i+1}/{frame_count} 帧：{frame_file}")
                
                img = Image.open(img_path)
                oled_data = image_to_oled_data(img)
                
                f.write(f"// 动画第{i}帧原始图：{frame_file}\n")
                f.write(f"const uint8_t Anim_Frame{i}[] = {{\n")
                for j in range(0, len(oled_data), 16):
                    line_data = oled_data[j:j+16]
                    f.write("    " + ", ".join([f"0x{b:02X}" for b in line_data]) + ",\n")
                f.write("};\n\n")

            f.write("// 动画帧指针索引表，循环播放直接遍历此数组\n")
            f.write("const uint8_t *const Anim_FrameTable[] = {\n")
            for i in range(frame_count):
                f.write(f"    Anim_Frame{i},\n")
            f.write("};\n\n")
            f.write("#endif // ANIMATION_FRAMES_H\n")
    
    except PermissionError:
        print(f"❌ 权限错误：无法写入 {OUTPUT_FILE}")
        print("关闭正在使用该文件的软件后重试")
        input("按回车键退出...")
        return
    except Exception as e:
        print(f"❌ 文件生成失败：{e}")
        input("按回车键退出...")
        return
    
    print()
    print("🎉 头文件生成完成！")
    print(f"📄 文件保存路径：{output_file_full}")
    print()
    print("调节说明：")
    print("  1. 修改 SCALE_RATIO 调整画面大小 1.0最大 / 0.7适中 / 0.5偏小")
    print("  2. 修改 FILL_SUBJECT 切换填充：0=轮廓不填充，1=填充猫咪主体")
    print()
    input("按回车键退出...")

if __name__ == "__main__":
    main()