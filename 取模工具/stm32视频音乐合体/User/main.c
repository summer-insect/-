/**
  * @file    main.c
  * @brief   视频 + 落泪音乐同步播放器
  *
  * 硬件平台: STM32F103C8T6
  * 显示:     OLED 0.96寸 (I2C, 128x64)
  * 蜂鸣器:   PB12 (TIM3音调生成)
  *
  * 定时器:
  *   TIM2 → 1ms 系统节拍（视频帧计时 + 音乐时长计时）
  *   TIM3 → 蜂鸣器音调生成（可变频率方波）
  *
  * 行为:
  *   - 开机视频自动循环播放
  *   - 落泪自动开始播放一次，播完即停
  *   - 视频不受音乐影响，持续循环
  */

#include "stm32f10x.h"
#include "Delay.h"
#include "OLED.h"
#include "Showmp4.h"
#include "Timer.h"
#include "Buzzer.h"

/* ======================== 视频常量 ======================== */
#define FRAME_INTERVAL  175             // 帧切换间隔（ms）

/* ======================== 全局变量 ======================== */
uint8_t  Current_frame = 0;
uint16_t Frame_tick     = 0;

/* ======================== TIM2 中断服务函数 ======================== */

/**
  * @brief  TIM2 中断 (1ms周期)
  *         同时处理视频帧切换 + 音乐播放状态机
  */
void TIM2_IRQHandler(void)
{
    if (TIM_GetITStatus(TIM2, TIM_IT_Update) == SET)
    {
        /* 视频帧切换计时 */
        Frame_tick++;
        if (Frame_tick >= FRAME_INTERVAL)
        {
            Frame_tick = 0;
            Current_frame++;
            if (Current_frame >= ANIM_FRAME_COUNT)
            {
                Current_frame = 0;
            }
        }

        /* 音乐播放计时（非阻塞状态机） */
        Music_Process();

        TIM_ClearITPendingBit(TIM2, TIM_IT_Update);
    }
}

/* ======================== 主函数 ======================== */

int main(void)
{
    /* 模块初始化 */
    OLED_Init();
    Timer_Init();       // TIM2 1ms 节拍
    Buzzer_Init();      // TIM3 音调生成 + PB12
    OLED_ShowImage(0, 0, 128, 64, Anim_FrameTable[Current_frame]);
    /* 开机启动落泪 */
    Delay_ms(200);
    Music_Start();
    /* 主循环：渲染视频 + 叠加音乐状态 */
    while (1)
    {
        /* 绘制当前视频帧 */
        OLED_ShowImage(0, 0, 128, 64, Anim_FrameTable[Current_frame]);
        OLED_Update();
        OLED_Clear();
    }
}
