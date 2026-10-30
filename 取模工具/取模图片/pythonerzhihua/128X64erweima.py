import numpy as np
import cv2
import os

# --------------------------
# OLED取模函数 (保持原样)
# --------------------------
def img2oled(frame):
    oled_data = []
    for y in range(0, 64, 8):
        for x in range(128):
            byte = 0x00
            for bit in range(8):
                if frame[y + bit, x] == 0:
                    byte |= (1 << bit)
            oled_data.append(byte)
    return bytes(oled_data)

# --------------------------
# 生成纯数组格式 (模仿 ah[] 风格)
# --------------------------
def save_to_simple_array(data, array_name="my_img", filename="oled_array.c"):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, filename)

    with open(file_path, "w") as f:
        # 写入数组开头
        f.write(f"const uint8_t {array_name}[] = {{\n")

        # 写入数据
        for i in range(len(data)):
            # 每一行开头加缩进 (4个空格)
            if i % 16 == 0:
                f.write("    ")
            
            # 写入 0xXX, 
            f.write(f"0x{data[i]:02X},")
            
            # 每16个数据换一行
            if (i + 1) % 16 == 0:
                f.write("\n")
        
        # 写入数组结尾
        f.write("\n};\n")
    
    print(f"✅ 数组文件已生成: {file_path}")

# --------------------------
# 主程序
# --------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
img_path = os.path.join(current_dir, 'jige.jpg')

try:
    img = cv2.imread(img_path)
    if img is None:
        print("❌ 图片读取失败！")
        raise Exception("图片读取失败")

    # 图像处理
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)
    qr = cv2.resize(binary, (64, 64), interpolation=cv2.INTER_NEAREST)

    canvas = np.zeros((64, 128), dtype=np.uint8)
    canvas[0:64, 32:96] = qr

    # 取模
    oled_bytes = img2oled(canvas)
    
    # 生成文件 (你可以在这里修改数组名字，比如把 "my_img" 改成 "ah")
    save_to_simple_array(oled_bytes, array_name="my_img")

except Exception as e:
    print(f"❌ 处理出错: {e}")