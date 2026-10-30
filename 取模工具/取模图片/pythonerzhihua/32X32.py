import numpy as np
import cv2
import os

# --------------------------
# 【修改】OLED取模函数：针对 32x32
# --------------------------
def img2oled_32x32(frame):
    oled_data = []
    # 32行高，分为 4 页 (32/8=4)
    for y in range(0, 32, 8):
        # 32列宽
        for x in range(32):
            byte = 0x00
            for bit in range(8):
                if frame[y + bit, x] == 0:
                    byte |= (1 << bit)
            oled_data.append(byte)
    return bytes(oled_data)

# --------------------------
# 生成纯数组格式
# --------------------------
def save_to_simple_array(data, array_name="img_32x32", filename="oled_array_32.c"):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, filename)

    with open(file_path, "w") as f:
        f.write(f"const uint8_t {array_name}[] = {{\n")
        for i in range(len(data)):
            if i % 16 == 0:
                f.write("    ")
            f.write(f"0x{data[i]:02X},")
            if (i + 1) % 16 == 0:
                f.write("\n")
        f.write("\n};\n")
    print(f"✅ 32x32数组已生成: {file_path}")

# --------------------------
# 主程序
# --------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
img_path = os.path.join(current_dir, 'weixin.jpg')

try:
    img = cv2.imread(img_path)
    if img is None:
        print("❌ 图片读取失败！")
        raise Exception("图片读取失败")

    # 【修改】图像处理：直接缩放到 32x32
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)
    
    # 直接变成 32x32
    img_32 = cv2.resize(binary, (32, 32), interpolation=cv2.INTER_NEAREST)

    # 显示预览
    cv2.imshow("32x32 Preview", img_32)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    # 取模
    oled_bytes = img2oled_32x32(img_32)
    
    # 生成文件
    save_to_simple_array(oled_bytes)

except Exception as e:
    print(f"❌ 处理出错: {e}")