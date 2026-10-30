# OLED 图像助手

把任意图片 / GIF 转成 SSD1306（128×64）单色点阵，自动生成可直接编译的 Keil 工程，并通过 ST-Link 一键烧录到 STM32F103C8T6。

- 导入即预览，128×64 所见即所得（预览和点阵用同一份数据）
- 四种取模算法（固定阈值 / 有序抖动 / 误差扩散 / 自适应）+ Otsu 自动阈值
- SCL、SDA 引脚任意选，JTAG 引脚自动避让，SWD 引脚直接拦截
- 生成完整 Keil 工程（标准外设库 + 江协 OLED 驱动），命令行编译、烧录、日志实时回显

## 快速开始

**直接用（推荐）**

到 [Releases](https://github.com/summer-insect/-/releases) 下载 `OLED-Image-Assistant-v1.0-win64.zip`，解压到任意目录，双击 `OLED图像助手.exe`。

免安装，自带 Python 3.13 与 Qt 6 运行时，不需要装任何东西。

**从源码跑**

```bash
pip install -r OLED图像助手/requirements.txt
python OLED图像助手/main.py
```

## 文档

👉 **[交接文档](OLED图像助手/交接文档.md)** —— 目录结构、数据流、关键设计（为什么要用模板工程、引脚参数化怎么做的、编译烧录怎么调的）、验证状态、常见问题排查表、二次开发指引。

## 目录

| 路径 | 说明 |
|---|---|
| `OLED图像助手/` | 工具本体（PySide6 桌面程序 + Keil 工程模板） |
| `取模工具/` | 早期参考实现：原始 Keil 工程、示例图片与视频素材 |

> 打包好的 exe 不在仓库里，通过 [Releases](https://github.com/summer-insect/-/releases) 分发。源码本身约 3MB；Git 仓库数据约 70MB，体积几乎全部来自 `取模工具/` 里的演示视频，与代码无关。

## 使用环境

### 一、运行环境（把软件跑起来）

| 项目 | 要求 | 说明 |
|---|---|---|
| 操作系统 | Windows 10 / 11（64 位） | 依赖 Qt 6，且用注册表定位 Keil；未在 32 位系统与 Win7 上测试 |
| 运行方式 A | 直接运行 exe，**无需装 Python** | Release 包自带 Python 3.13 与 Qt 运行时 |
| 运行方式 B | Python 3.10 及以上 | `pip install -r OLED图像助手/requirements.txt`，依赖 PySide6-Essentials ≥ 6.6、Pillow ≥ 10 |
| 屏幕分辨率 | 建议 1366×768 及以上 | 窗口最小尺寸 1060×660，再小会显示不全 |
| 磁盘空间 | 约 300MB | 解压后 exe 目录 131MB，另加每个生成的 Keil 工程约 2MB |

### 二、编译烧录环境（点「一键生成并烧录」时需要）

| 项目 | 要求 | 说明 |
|---|---|---|
| Keil MDK | 5.x，需含 `UV4.exe` | 自动从注册表及 `C:\Keil_v5`、`D:\keil5`、`E:\…` 等常见路径查找，找不到可在界面手动指定 |
| 编译器 | ARMCC V5.06（AC5） | 模板工程按 AC5 配置；若要用 AC6 需在 Keil 里改 Target 设置 |
| 器件包 | Keil.STM32F1xx_DFP ≥ 2.2.0 | 生成时自动读取本机已装版本并写进工程，换电脑不用改代码 |
| 调试器 | ST-Link（SWD 模式） | 模板 `uvoptx` 预置的是 ST-Link；用 J-Link / DAP-Link 需在 Keil 里改一次 Debug 选项 |
| 驱动 | ST-Link USB 驱动 | 安装 STM32CubeProgrammer 或 ST-Link Utility 时会一并装好 |

> 只点「仅生成工程」的话，Keil、ST-Link 都不是必需的——生成的工程可以拷到别的机器上编译。

### 三、硬件环境（决定显示效果）

| 项目 | 要求 |
|---|---|
| 单片机 | STM32F103C8T6（64KB Flash / 20KB RAM） |
| 显示屏 | SSD1306，128×64，I2C 四针（VCC / GND / SCL / SDA） |
| 屏幕兼容 | 1.3 寸 SH1106 也可用，但需把「列偏移」改成 2，否则画面左移两列 |
| 默认接线 | SCL→PB8，SDA→PB9；可在界面改成 PA0~PA15、PB0~PB15、PC13~PC15 任意组合 |
| 烧录接口 | SWD：SWDIO(PA13)、SWCLK(PA14)、GND、3V3 |
| 供电 | 3.3V；OLED 模块若标称 5V 供电，模块一般自带稳压，可直接接 5V |

### 四、不需要准备什么

- 不需要联网（首次安装 Python 依赖除外）
- 不需要装 Python（使用 exe 时）
- 不需要单独装驱动（已装过 Keil + ST-Link 的机器通常已具备）

## 已知限制

- MDK-Lite 有 32KB 代码限制，每帧占 1KB，建议不超过 12 帧
- 仅支持单色 128×64；驱动为软件 I2C，动画帧率上限约 20fps
- 每次生成会覆盖同名工程目录

## 说明

- 可执行程序通过 [Releases](https://github.com/summer-insect/-/releases) 分发，**不占仓库体积**；每次重新打包只需新发一个 Release 版本，Git 历史不会被二进制文件撑大
- `取模工具/取模视频/打篮球.mp4`（71.8MB）超过 GitHub 推荐的 50MB 单文件大小，首次克隆会慢一些
