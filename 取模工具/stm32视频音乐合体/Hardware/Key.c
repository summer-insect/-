/**
  * @file    Key.c
  * @brief   按键驱动模块
  *
  * 硬件连接:
  *   PA5 → 选择键（一端接PA5，另一端接VCC，按下为高电平）
  *   PA3 → 确认键（一端接PA3，另一端接VCC，按下为高电平）
  *
  * PA5/PA3 使用下拉输入模式（IPD），按下检测高电平
  */

#include "stm32f10x.h"                  // Device header
#include "Delay.h"
#include "Key.h"

/**
  * @brief  按键初始化
  * @note   PA5/PA3配置为下拉输入（接VCC的按键）
  */
void Key_Init(void)
{
    /* ---- GPIOA时钟：PA5、PA3 ---- */
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);

    GPIO_InitTypeDef GPIO_InitStructure;

    /* PA5：下拉输入（按键接VCC，按下=高电平） */
    GPIO_InitStructure.GPIO_Mode  = GPIO_Mode_IPD;
    GPIO_InitStructure.GPIO_Pin   = GPIO_Pin_5;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStructure);

    /* PA3：下拉输入（按键接VCC，按下=高电平） */
    GPIO_InitStructure.GPIO_Mode  = GPIO_Mode_IPD;
    GPIO_InitStructure.GPIO_Pin   = GPIO_Pin_3;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStructure);
}

/**
  * @brief  获取按键键值（带消抖，等待按键松开后返回）
  * @retval KEY_NONE(0)  无按键
  *         KEY_SELECT(1) PA5 选择键按下
  *         KEY_CONFIRM(2) PA3 确认键按下
  */
uint8_t Key_GetNum(void)
{
    uint8_t KeyNum = KEY_NONE;

    /* ---- 检测PA5 选择键（接VCC，按下为高电平） ---- */
    if (GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_5) == 1)
    {
        Delay_ms(20);                                           // 消抖
        if (GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_5) == 1)     // 再次确认
        {
            while (GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_5) == 1); // 等待松开
            Delay_ms(20);                                       // 松开消抖
            KeyNum = KEY_SELECT;
        }
    }

    /* ---- 检测PA3 确认键（接VCC，按下为高电平） ---- */
    if (GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_3) == 1)
    {
        Delay_ms(20);                                           // 消抖
        if (GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_3) == 1)     // 再次确认
        {
            while (GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_3) == 1); // 等待松开
            Delay_ms(20);                                       // 松开消抖
            KeyNum = KEY_CONFIRM;
        }
    }

    return KeyNum;
}

/**
  * @brief  获取按键实时状态（不消抖，不等待松开）
  * @retval KEY_NONE(0)  无按键按下
  *         KEY_SELECT(1) PA5 正在按下
  *         KEY_CONFIRM(2) PA3 正在按下
  */
uint8_t Key_GetState(void)
{
    if (GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_5) == 1)
    {
        return KEY_SELECT;
    }
    if (GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_3) == 1)
    {
        return KEY_CONFIRM;
    }
    return KEY_NONE;
}
