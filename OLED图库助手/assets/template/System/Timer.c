#include "stm32f10x.h"                  // Device header

void Timer_Init()
{
	//开启时钟
	RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2, ENABLE);	//通用定时器有TIM2、3、4、5，这里选择是tim2，tim2在apb1总线上，所以是apb1总线的时钟	
	
	//时基单元初始化
	TIM_InternalClockConfig(TIM2);		//配置tim2的时钟源，选择内部时钟72Mhz
	TIM_TimeBaseInitTypeDef TIM_TimeBaseInitStructure;	  	
	TIM_TimeBaseInitStructure.TIM_ClockDivision = TIM_CKD_DIV1;		//时钟分频，用来配置滤波器的，这里选择不分频
	TIM_TimeBaseInitStructure.TIM_CounterMode = TIM_CounterMode_Up;	  //向上计数模式
	
	/*定时频率公式=72M / (PSC + 1) / (ARR + 1)，那想定时1s也就是定时频率为1hz
	1 = 72,000,000 / [(PSC + 1) × (ARR + 1)]变形后(PSC + 1) × (ARR + 1) = 72,000,000，就算出能够定时1ms需要的值*/
	TIM_TimeBaseInitStructure.TIM_Period = 100 - 1;		//计数阈值，ARR		
	TIM_TimeBaseInitStructure.TIM_Prescaler = 720 - 1;		//预分频器，PSC		
	TIM_TimeBaseInitStructure.TIM_RepetitionCounter = 0;		//高级定时器才会用到重复计数器，我们选的是tim2，是普通定时器	
	TIM_TimeBaseInit(TIM2, &TIM_TimeBaseInitStructure);				
	
	TIM_ClearFlag(TIM2, TIM_FLAG_Update);	//清除tim2更新中断标志位，
											//因为上面TimeBaseInit结束后会自动进入中断让给的设置生效，会让更新标志位置1，然后程序就会在初始化完后立马执行中断函数		
	TIM_ITConfig(TIM2, TIM_IT_Update, ENABLE);		//开启TIM2的更新中断（就是一个中断信号），让中断能够进入nvic			
	
	//NVIC配置
	NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);		//NVIC中断分组
	NVIC_InitTypeDef NVIC_InitStructure;						
	NVIC_InitStructure.NVIC_IRQChannel = TIM2_IRQn;		//tim2在nvic里的通道（跳转到定义里去找）		
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;				
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 2;	
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;			
	NVIC_Init(&NVIC_InitStructure);	
	
	//启动定时器
	TIM_Cmd(TIM2, ENABLE);			
}

/* 定时器中断函数
void TIM2_IRQHandler()
{
	if (TIM_GetITStatus(TIM2, TIM_IT_Update) == SET)
	{
		
		TIM_ClearITPendingBit(TIM2, TIM_IT_Update);
	}
}
*/
