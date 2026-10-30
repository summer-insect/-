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

# ===================== 通用配置参数 =====================
FRAME_FOLDER = "月薪喵"    # 存放帧图片的文件夹名称
OUTPUT_FILE = "MaxShowmp4.h"  # 输出的C语言头文件名称
OLED_WIDTH = 128          # OLED屏幕宽度
OLED_HEIGHT = 64          # OLED屏幕高度
KEEP_EVERY_N_FRAME = 2    # 帧抽取间隔，每N帧保留1帧

# 图像二值化可调参数（解决画面扁平关键）
CONTRAST_FACTOR = 2.2     # 对比度增强，越大黑白分界越明显(推荐1.5~3.0)
FIX_THRESHOLD = 130        # 固定二值阈值，亮图调高，暗图调低(0~255)
USE_AUTO_THRESH = True     # True自适应阈值(推荐，层次感强) / False固定阈值
WHITE_BG_THRESH = 240      # 空白判定阈值：灰度≥该值视为纯白背景，会被裁剪
# ======================================================

# 自动裁剪空白，只保留画面主体
def crop_blank_border(gray_img):
    width, height = gray_img.size
    # 收集所有非空白像素坐标
    non_blank_points = []
    for x in range(width):
        for y in range(height):
            pix = gray_img.getpixel((x, y))
            if pix < WHITE_BG_THRESH:
                non_blank_points.append((x, y))
    # 图片全空白，不裁剪
    if not non_blank_points:
        return gray_img
    # 计算主体边界
    xs = [p[0] for p in non_blank_points]
    ys = [p[1] for p in non_blank_points]
    left = min(xs)
    right = max(xs)
    top = min(ys)
    bottom = max(ys)
    # 裁剪主体区域
    crop_box = (left, top, right + 1, bottom + 1)
    crop_img = gray_img.crop(crop_box)
    return crop_img

# 图片预处理+SSD1306标准取模（纵向8点，低位在前）
def image_to_oled_data(image):
    # 1. 先转为灰度图，裁剪空白边框
    gray_img = image.convert("L")
    gray_img = crop_blank_border(gray_img)
    
    # 2. 裁剪后放大铺满OLED屏幕，主体最大化
    img = gray_img.resize((OLED_WIDTH, OLED_HEIGHT), Image.Resampling.LANCZOS)
    
    # 3. 增强对比度，拉开明暗层次，解决画面扁平
    contrast_enhancer = ImageEnhance.Contrast(img)
    gray_img = contrast_enhancer.enhance(CONTRAST_FACTOR)

    # 4. 二值化处理二选一
    if USE_AUTO_THRESH:
        # 自适应阈值：局部画面单独计算阈值，明暗画面都保留细节，立体感强
        gray_img = gray_img.filter(ImageFilter.ModeFilter(size=3))  # 轻微降噪
        img_bin = gray_img.point(lambda x: 0 if x < FIX_THRESHOLD else 255, "1")
    else:
        # 全局固定阈值二值化
        img_bin = gray_img.point(lambda x: 0 if x < FIX_THRESHOLD else 255, "1")

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
    print("OLED动画帧通用取模工具 v3.0（自动裁空白+放大主体）")
    print("=" * 50)
    
    # 获取脚本绝对路径，兼容中文路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"📂 脚本所在目录：{script_dir}")
    
    # 拼接完整路径
    frame_folder_full = os.path.join(script_dir, FRAME_FOLDER)
    output_file_full = os.path.join(script_dir, OUTPUT_FILE)
    
    print(f"📂 图片文件夹路径：{frame_folder_full}")
    print(f"📄 输出头文件路径：{output_file_full}")
    print(f"⚙️  对比度增强系数：{CONTRAST_FACTOR}")
    print(f"⚙️  自适应二值化：{'开启' if USE_AUTO_THRESH else '关闭'}")
    print(f"⚙️  空白背景判定阈值：{WHITE_BG_THRESH}")
    print()
    
    # 校验图片文件夹是否存在
    if not os.path.isdir(frame_folder_full):
        print(f"❌ 错误：找不到文件夹 '{FRAME_FOLDER}'")
        print("请将bmp/png帧图片放入脚本同目录下该文件夹")
        input("按回车键退出...")
        return
    
    # 筛选图片文件
    frame_files = [f for f in os.listdir(frame_folder_full)
                   if f.lower().endswith(('.bmp', '.png'))]
    
    if not frame_files:
        print(f"❌ 错误：文件夹内未找到bmp/png图片")
        input("按回车键退出...")
        return
    
    print(f"✅ 读取到原始图片：{len(frame_files)} 张")
    
    # 按帧序号升序排序
    frame_files.sort(key=extract_number)
    print(f"✅ 帧图片按序号排序完成")
    
    # 间隔抽取帧
    selected_frames = frame_files[::KEEP_EVERY_N_FRAME]
    frame_count = len(selected_frames)
    single_frame_bytes = OLED_WIDTH * OLED_HEIGHT // 8
    print(f"✅ 筛选后保留动画总帧数：{frame_count} (每{KEEP_EVERY_N_FRAME}帧取1帧)")
    print(f"💾 动画单帧大小：{single_frame_bytes} 字节")
    print()
    
    # 生成标准C头文件
    print("🔄 正在生成动画数据头文件...")
    
    try:
        with open(output_file_full, 'w', encoding='utf-8') as f:
            # 头文件保护宏（通用命名）
            f.write("#ifndef ANIMATION_FRAMES_H\n")
            f.write("#define ANIMATION_FRAMES_H\n\n")
            f.write("#include \"stm32f10x.h\"\n\n")
            # 通用宏定义
            f.write(f"#define ANIM_FRAME_COUNT    {frame_count}    // 动画总帧数\n")
            f.write(f"#define ANIM_FRAME_BYTES    {single_frame_bytes}  // 单帧图像字节大小\n\n")

            # 逐帧生成像素数据数组
            for i, frame_file in enumerate(selected_frames):
                img_path = os.path.join(frame_folder_full, frame_file)
                print(f"  处理第 {i+1}/{frame_count} 帧：{frame_file}")
                
                img = Image.open(img_path)
                oled_data = image_to_oled_data(img)
                
                f.write(f"// 动画第{i}帧原始图：{frame_file}\n")
                f.write(f"const uint8_t Anim_Frame{i}[] = {{\n")
                # 每行输出16个十六进制字节
                for j in range(0, len(oled_data), 16):
                    line_data = oled_data[j:j+16]
                    f.write("    " + ", ".join([f"0x{b:02X}" for b in line_data]) + ",\n")
                f.write("};\n\n")

            # 帧指针索引表（统一管理所有动画帧）
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
    print("使用说明：")
    print("1. 将生成的.h文件复制到STM32工程目录")
    print("2. 在OLED驱动中 #include \"Showmp3.h\"")
    print("3. Anim_FrameTable[索引] 获取对应帧图像数据")
    print("4. ANIM_FRAME_COUNT 总帧数，用于循环播放判断")
    print()
    input("按回车键退出...")

if __name__ == "__main__":
    main()