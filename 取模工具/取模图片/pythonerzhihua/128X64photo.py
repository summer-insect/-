import cv2

# 只保留最核心的取模函数
def img2oled(frame):
    oled_data = []
    for y in range(0, 64, 8):
        for x in range(128):
            byte = 0x00
            for bit in range(8):
                if frame[y + bit, x] == 0:
                    byte |= (1 << bit)
            oled_data.append(byte)
    return oled_data

# 直接写死所有路径
img_path = "F:\\pythonerzhihua\\xinlv.jpg"
output_path = "F:\\pythonerzhihua\\xinlv.txt"

# 1. 读取图片
img = cv2.imread(img_path, 0)  # 直接以灰度模式读取
if img is None:
    print("❌ 错误：找不到图片！请确认图片路径是 F:\\pythonerzhihua\\xiaogou.jpg")
    exit()

# 2. 强制缩放到128x64
img = cv2.resize(img, (128, 64))

# 3. 简单二值化
_, binary = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY_INV)

# 4. 取模
data = img2oled(binary)

# 5. 保存文件
with open(output_path, "w") as f:
    f.write("const uint8_t xiaogou[] = {\n")
    for i in range(len(data)):
        if i % 16 == 0:
            f.write("    ")
        f.write(f"0x{data[i]:02X},")
        if (i + 1) % 16 == 0:
            f.write("\n")
    f.write("\n};\n")

print("✅ 成功！文件已生成：F:\\pythonerzhihua\\xiaogou.c")