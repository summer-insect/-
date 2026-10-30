import numpy as np
import cv2
import serial
import time
import os

# --------------------------
# OLED取模函数
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
# 串口初始化
# --------------------------
serial_port = None
try:
    serial_port = serial.Serial('COM6', 921600, timeout=1)
    print("✅ 串口打开成功")
except Exception as e:
    print(f"❌ 串口打开失败: {e}")
    exit()

# --------------------------
# 读取并处理图片（只执行1次）
# --------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
img_path = os.path.join(current_dir, 'tup.jpg')

try:
    img = cv2.imread(img_path)
    if img is None:
        print("❌ 图片读取失败！")
        raise Exception("图片读取失败")

    # 图像处理（只处理1次）
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)
    qr = cv2.resize(binary, (64, 64), interpolation=cv2.INTER_NEAREST)

    canvas = np.zeros((64, 128), dtype=np.uint8)
    canvas[0:64, 32:96] = qr

    cv2.imshow("QR Preview", canvas)
    cv2.waitKey(0)

    # 🔥 核心：只发送【1次】数据，之后永不发送 = 屏幕绝对不刷新
    oled_bytes = img2oled(canvas)
    serial_port.write(b'\xAA' + oled_bytes)
    print("✅ 静态二维码已发送，OLED 永久静止显示！")

except Exception as e:
    print(f"❌ 处理出错: {e}")

# --------------------------
# 程序挂起：不执行任何操作，不发数据，屏幕静止
# --------------------------
cv2.destroyAllWindows()
print("🔒 OLED 已锁定静态画面，按 Ctrl+C 退出程序")
try:
    while True:
        # 只休眠，不做任何事 → 屏幕绝对不刷新
        time.sleep(3600)
except KeyboardInterrupt:
    serial_port.close()
    print("\n👋 程序退出")