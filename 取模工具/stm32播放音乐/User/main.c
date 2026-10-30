/**
  * @file    main.c
  * @brief   音乐播放器 —— OLED菜单选择 + 蜂鸣器播放
  *
  * 硬件平台: STM32F103C8T6
  * 显示:     OLED 0.96寸 (I2C, 4针脚)
  * 蜂鸣器:   PB12 (TIM3音调生成)
  * 按键:
  *   PA5 → 选择键（接VCC，按下切换歌曲，OLED反色显示当前选中）
  *   PA3 → 确认键（接VCC，按下播放选中歌曲）
  *
  * 坐标轴定义：
  * 左上角为(0, 0)点
  * 横向向右为X轴，取值范围：0~127
  * 纵向向下为Y轴，取值范围：0~63
  *
  *       0             X轴           127
  *      .------------------------------->
  *    0 |
  *      |
  *      |
  *      |
  *  Y轴 |
  *      |
  *      |
  *      |
  *   63 |
  *      v
  */

#include "stm32f10x.h"                  // Device header
#include "Delay.h"
#include "OLED.h"
#include "Key.h"
#include "Buzzer.h"

/* ======================== 菜单常量 ======================== */

#define MENU_ITEM_Y     16      // 第一个菜单项的Y坐标
#define MENU_ITEM_H     16      // 每个菜单项高度（8x16字体）
#define MENU_ITEM_W     128     // 菜单项宽度（全屏）
#define STATUS_Y        48      // 播放状态文字Y坐标（8x16字体，占Y=48~63）

/* ======================== 函数声明 ======================== */

void Menu_Init(void);
void Menu_UpdateDisplay(uint8_t selection);
void Menu_HandleSelect(void);
void Menu_HandlePlay(void);

/* ======================== 全局变量 ======================== */

uint8_t g_selection = 0;        // 当前选中的歌曲索引 (0起风了 /1晴天 /2落泪)

/* ======================== 菜单初始化 ======================== */

/**
  * @brief  初始化并显示菜单界面
  * @note   绘制标题、歌曲列表、操作提示
  */
void Menu_Init(void)
{
    OLED_Clear();

    /* ---- 标题栏 ---- */
    OLED_ShowString(16, 0, "音乐播放器", OLED_8X16);

    /* ---- 分隔线 ---- */
    OLED_DrawLine(0, 15, 127, 15);

    /* ---- 歌曲列表（3首） ---- */
    OLED_ShowString(16, MENU_ITEM_Y,          "起风了", OLED_8X16);
    OLED_ShowString(16, MENU_ITEM_Y + 16,     "晴天",   OLED_8X16);
    OLED_ShowString(16, MENU_ITEM_Y + 32,     "落泪",   OLED_8X16);

    /* ---- 选中指示箭头和反色 ---- */
    OLED_ShowString(0, MENU_ITEM_Y + g_selection * MENU_ITEM_H, ">", OLED_8X16);

    /* 反色显示当前选中行 */
    OLED_ReverseArea(0, MENU_ITEM_Y + g_selection * MENU_ITEM_H, MENU_ITEM_W, MENU_ITEM_H);

    OLED_Update();
}

/* ======================== 更新菜单显示 ======================== */

/**
  * @brief  切换选中项时更新显示
  * @param  selection: 新的选中索引
  */
void Menu_UpdateDisplay(uint8_t selection)
{
    uint8_t oldSelection = g_selection;

    /* 先恢复旧选中行的正常显示（再次反色=还原） */
    OLED_ReverseArea(0, MENU_ITEM_Y + oldSelection * MENU_ITEM_H, MENU_ITEM_W, MENU_ITEM_H);

    /* 移动箭头指示器：清除旧箭头 */
    OLED_ShowString(0, MENU_ITEM_Y + oldSelection * MENU_ITEM_H, "  ", OLED_8X16);

    /* 更新选中索引 */
    g_selection = selection;

    /* 绘制新箭头 */
    OLED_ShowString(0, MENU_ITEM_Y + g_selection * MENU_ITEM_H, ">", OLED_8X16);

    /* 反色显示新选中行 */
    OLED_ReverseArea(0, MENU_ITEM_Y + g_selection * MENU_ITEM_H, MENU_ITEM_W, MENU_ITEM_H);

    /* 更新OLED — 覆盖所有歌曲行 */
    OLED_UpdateArea(0, MENU_ITEM_Y, MENU_ITEM_W, MENU_ITEM_H * SONG_COUNT);
}

/* ======================== 选择键处理 ======================== */

/**
  * @brief  处理PA5选择键：循环切换0→1→2→0
  */
void Menu_HandleSelect(void)
{
    uint8_t newSelection;

    newSelection = (g_selection + 1) % SONG_COUNT;

    Menu_UpdateDisplay(newSelection);
}

/* ======================== 播放键处理 ======================== */

/**
  * @brief  处理PA3确认键：播放选中歌曲
  */
void Menu_HandlePlay(void)
{
    /* ---- 显示播放状态 ---- */
    OLED_ClearArea(0, STATUS_Y, MENU_ITEM_W, 16);
    OLED_ShowString(0, STATUS_Y, "  播放中...       ", OLED_8X16);
    OLED_UpdateArea(0, STATUS_Y, MENU_ITEM_W, 16);

    /* ---- 播放歌曲（阻塞式） ---- */
    Music_Play(g_selection);

    /* ---- 播放完毕，恢复菜单 ---- */
    OLED_ClearArea(0, STATUS_Y, MENU_ITEM_W, 16);
    OLED_ShowString(0, STATUS_Y, "  播放完毕!       ", OLED_8X16);
    OLED_UpdateArea(0, STATUS_Y, MENU_ITEM_W, 16);
    Delay_ms(1000);

    /* ---- 恢复菜单显示（重新绘制完整菜单） ---- */
    Menu_Init();
}

/* ======================== 主函数 ======================== */

int main(void)
{
    uint8_t key;

    /* ---- 模块初始化 ---- */
    OLED_Init();            // OLED初始化
    Buzzer_Init();          // 蜂鸣器初始化（GPIO PB12 + TIM3，内含NVIC优先级分组）
    Key_Init();             // 按键初始化（PA5下拉、PA3下拉）

    /* ---- 显示菜单 ---- */
    Menu_Init();

    /* ---- 主循环：监听按键 ---- */
    while (1)
    {
        key = Key_GetNum();     // 阻塞等待按键（带消抖，松开后返回）

        if (key == KEY_SELECT)          // PA5: 切换选中歌曲
        {
            Menu_HandleSelect();
        }
        else if (key == KEY_CONFIRM)    // PA3: 播放选中歌曲
        {
            Menu_HandlePlay();
        }
    }
}
