# 先检查依赖
try:
    import cv2
    import numpy as np
except ImportError:
    print("❌ 错误：没有安装OpenCV库！")
    print("请在命令行执行：pip install opencv-python numpy")
    input("按回车键退出...")
    exit(1)

import os

# ===================== 配置参数 =====================
VIDEO_FILE = "打篮球.mp4"          # 输入的MP4视频文件名（放在脚本同目录下）
FRAME_FOLDER = "篮球"              # 输出帧图片文件夹名称
OLED_WIDTH = 128                   # 输出图片宽度
OLED_HEIGHT = 64                  # 输出图片高度
KEEP_EVERY_N_FRAME = 70            # 每N帧保留1帧
OUTPUT_GRAYSCALE = True            # 是否输出灰度图
# ===================================================

# 兼容中文路径的图片保存函数
def imwrite_cn(file_path, img):
    """支持中文路径的图片保存，替代原生cv2.imwrite"""
    try:
        # 获取文件后缀
        ext = os.path.splitext(file_path)[1]
        # 编码到内存
        success, buf = cv2.imencode(ext, img)
        if success:
            # 二进制方式写入文件（支持中文路径）
            with open(file_path, 'wb') as f:
                buf.tofile(f)
            return True
        return False
    except Exception:
        return False

# 主函数
def main():
    print("=" * 50)
    print("视频转OLED帧BMP提取工具 v1.2 (自动清理旧帧)")
    print("=" * 50)
    
    # 获取脚本所在的绝对路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"📂 脚本所在目录：{script_dir}")
    
    # 拼接完整路径
    video_full_path = os.path.join(script_dir, VIDEO_FILE)
    frame_folder_full = os.path.join(script_dir, FRAME_FOLDER)
    
    print(f"🎞️  输入视频路径：{video_full_path}")
    print(f"📂 输出帧文件夹：{frame_folder_full}")
    print()
    
    # 检查视频文件是否存在
    if not os.path.isfile(video_full_path):
        print(f"❌ 错误：找不到视频文件 '{VIDEO_FILE}'")
        print(f"请将MP4视频放在脚本同一目录下，并修改配置中的 VIDEO_FILE 为你的文件名")
        input("按回车键退出...")
        return
    
    # 创建输出文件夹
    os.makedirs(frame_folder_full, exist_ok=True)

    # 自动清理文件夹内所有旧bmp图片
    clear_count = 0
    for file_name in os.listdir(frame_folder_full):
        if file_name.lower().endswith(".bmp"):
            file_full = os.path.join(frame_folder_full, file_name)
            os.remove(file_full)
            clear_count += 1
    if clear_count > 0:
        print(f"🗑️  已清理上一轮旧帧图片：{clear_count} 张")
    else:
        print("📭 文件夹无旧帧图片，无需清理")
    print()
    
    # 打开视频流（兼容中文路径）
    cap = cv2.VideoCapture(video_full_path)
    if not cap.isOpened():
        print("❌ 错误：无法打开视频文件")
        print("可能原因：文件损坏、格式不支持、中文路径兼容问题")
        print("建议：先把视频改成纯英文文件名（如 basketball.mp4）再试")
        input("按回车键退出...")
        return
    
    # 获取视频基础信息（修复双层get错误）
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    if total_frames <= 0:
        print("❌ 错误：未读取到有效视频帧，请检查视频文件是否正常")
        cap.release()
        input("按回车键退出...")
        return
    
    print(f"✅ 视频打开成功")
    print(f"  原始总帧数：{total_frames} 帧")
    print(f"  原始帧率：{fps:.2f} FPS")
    print(f"  输出尺寸：{OLED_WIDTH} × {OLED_HEIGHT}")
    print(f"  抽帧间隔：每 {KEEP_EVERY_N_FRAME} 帧保留1帧")
    
    # 计算预计输出帧数
    expected_output = total_frames // KEEP_EVERY_N_FRAME
    print(f"  预计输出帧数：{expected_output} 张BMP图片")
    print()
    
    # 开始逐帧处理
    print("🔄 正在提取帧并保存BMP...")
    
    frame_idx = 0    # 原始视频帧计数器
    save_idx = 0     # 保存成功计数器
    fail_count = 0   # 保存失败计数器
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break  # 视频读取结束
        
        # 按间隔保留帧
        if frame_idx % KEEP_EVERY_N_FRAME == 0:
            # 缩放到OLED分辨率
            resized_frame = cv2.resize(
                frame, 
                (OLED_WIDTH, OLED_HEIGHT), 
                interpolation=cv2.INTER_AREA
            )
            
            # 转灰度图
            if OUTPUT_GRAYSCALE:
                resized_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2GRAY)
            
            # 生成文件名
            output_filename = f"frame_{save_idx:04d}.bmp"
            output_path = os.path.join(frame_folder_full, output_filename)
            
            # 保存BMP图片（使用中文路径兼容版）
            save_ok = imwrite_cn(output_path, resized_frame)
            
            if save_ok:
                print(f"  已保存第 {save_idx+1}/{expected_output} 帧：{output_filename}")
                save_idx += 1
            else:
                print(f"  ⚠️  第 {save_idx+1} 帧保存失败：{output_filename}")
                fail_count += 1
        
        frame_idx += 1
    
    # 释放视频资源
    cap.release()
    
    print()
    print("=" * 50)
    print(f"✅ 处理完成！成功保存 {save_idx} 张，失败 {fail_count} 张")
    print(f"📂 图片保存位置：{frame_folder_full}")
    print("=" * 50)
    
    if save_idx == 0:
        print()
        print("⚠️  警告：没有成功生成任何图片")
        print("排查建议：")
        print("1. 把视频文件名和文件夹名都改成纯英文（如 video.mp4、frames）")
        print("2. 确认视频可以正常播放，没有损坏")
        print("3. 检查视频是否有画面（不是纯音频文件）")
    
    print()
    input("按回车键退出...")

if __name__ == "__main__":
    main()