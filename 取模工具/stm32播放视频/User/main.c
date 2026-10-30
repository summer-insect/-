#include "stm32f10x.h"                  // Device header
#include "Delay.h"
#include "OLED.h"
#include "Showmp4.h"
#include "Timer.h"

/**
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
  * 
  */

uint8_t Current_frame = 0;  // 当前显示帧
uint16_t Frame_tick = 0;    // 帧切换计数器
#define FRAME_INTERVAL 150    // 帧切换间隔（单位：ms，值越小动画越快）


int main(void)
{
	OLED_Init();
    Timer_Init();
	while (1)
	{
        OLED_ShowImage(0,0,128,64,Anim_FrameTable[Current_frame]);
        OLED_Update();
        OLED_Clear();
	}
}

void TIM2_IRQHandler()
{
	if (TIM_GetITStatus(TIM2, TIM_IT_Update) == SET)
	{
		        Frame_tick++;
		if(Frame_tick >= FRAME_INTERVAL)
		{
			Frame_tick = 0;
			Current_frame++;
			// 循环播放帧
			if(Current_frame >= ANIM_FRAME_COUNT)
			{
				Current_frame = 0;
			}
		}
		TIM_ClearITPendingBit(TIM2, TIM_IT_Update);
	}
}
