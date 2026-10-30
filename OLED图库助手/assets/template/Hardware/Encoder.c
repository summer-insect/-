/**
  ******************************************************************************
  * @file    Encoder.c
  * @brief   EC11 旋转编码器驱动（TIM3 定时扫描 + 正交状态机）
  *
  * 解码原理：
  *   A/B 两相相差 90°，旋转时产生正交脉冲。每 1ms 采样一次两相电平，
  *   查表得到本次跳变的方向，累加到 s_acc；
  *   累加满 ENC_STEPS_PER_DETENT 个边沿才输出一步，因此抖动会被自动抵消。
  *
  * 按键：
  *   同一中断里做 20ms 消抖，松手瞬间产生一次事件（按一下算一次，长按不重复）。
  *
  * 所有引脚与参数都在 oled_config.h 里，本文件通常不需要改动。
  ******************************************************************************
  */

#include "stm32f10x.h"
#include "misc.h"
#include "oled_config.h"
#include "Encoder.h"

#define ENC_READ_A()          GPIO_ReadInputDataBit(ENC_A_PORT, ENC_A_PIN)
#define ENC_READ_B()          GPIO_ReadInputDataBit(ENC_B_PORT, ENC_B_PIN)

#define ENC_BTN_DEBOUNCE_MS   20

/* 索引 = (上一状态 << 2) | 当前状态，值 = 本次跳变的方向 */
static const int8_t ENC_TABLE[16] = {
     0, -1,  1,  0,
     1,  0,  0, -1,
    -1,  0,  0,  1,
     0,  1, -1,  0
};

static volatile int8_t s_acc  = 0;
static uint8_t         s_prev = 0;

/* 自检统计：中断跑了多少次、两相一共跳变多少次 */
static volatile uint32_t s_isr_cnt  = 0;
static volatile int32_t  s_edge_cnt = 0;

#if ENC_SW_ENABLE
static volatile uint8_t s_btn_cnt   = 0;
static volatile uint8_t s_btn_event = 0;
#endif

/**
  * @brief  初始化编码器引脚与 1ms 扫描定时器
  */
void Encoder_Init(void)
{
	GPIO_InitTypeDef GPIO_InitStructure;
	TIM_TimeBaseInitTypeDef TIM_TimeBaseStructure;
	NVIC_InitTypeDef NVIC_InitStructure;

	RCC_APB2PeriphClockCmd(ENC_A_CLK | ENC_B_CLK, ENABLE);

	/* A/B 相接上拉输入：编码器公共端接地，内部上拉保证空闲为高 */
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPU;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_InitStructure.GPIO_Pin = ENC_A_PIN;
	GPIO_Init(ENC_A_PORT, &GPIO_InitStructure);
	GPIO_InitStructure.GPIO_Pin = ENC_B_PIN;
	GPIO_Init(ENC_B_PORT, &GPIO_InitStructure);

#if ENC_SW_ENABLE
	RCC_APB2PeriphClockCmd(ENC_SW_CLK, ENABLE);
	GPIO_InitStructure.GPIO_Pin = ENC_SW_PIN;
	GPIO_Init(ENC_SW_PORT, &GPIO_InitStructure);
#endif

	s_prev = (uint8_t)((ENC_READ_A() << 1) | ENC_READ_B());
	s_acc = 0;

	/* TIM3：72MHz / 72 = 1MHz，计数 ENC_SCAN_MS*1000 次溢出一次 */
	RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM3, ENABLE);
	TIM_TimeBaseStructure.TIM_Period = ENC_SCAN_MS * 1000 - 1;
	TIM_TimeBaseStructure.TIM_Prescaler = 72 - 1;
	TIM_TimeBaseStructure.TIM_ClockDivision = TIM_CKD_DIV1;
	TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up;
	TIM_TimeBaseStructure.TIM_RepetitionCounter = 0;
	TIM_TimeBaseInit(TIM3, &TIM_TimeBaseStructure);

	TIM_ClearITPendingBit(TIM3, TIM_IT_Update);
	TIM_ITConfig(TIM3, TIM_IT_Update, ENABLE);

	NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);
	NVIC_InitStructure.NVIC_IRQChannel = TIM3_IRQn;
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 2;
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 0;
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
	NVIC_Init(&NVIC_InitStructure);

	TIM_Cmd(TIM3, ENABLE);
}

/**
  * @brief  定时扫描：正交解码 + 按键消抖
  */
void TIM3_IRQHandler(void)
{
	uint8_t cur;

	if (TIM_GetITStatus(TIM3, TIM_IT_Update) == RESET)
	{
		return;
	}
	TIM_ClearITPendingBit(TIM3, TIM_IT_Update);

	s_isr_cnt++;

	cur = (uint8_t)((ENC_READ_A() << 1) | ENC_READ_B());
	if (cur != s_prev)
	{
		int8_t delta = ENC_TABLE[(s_prev << 2) | cur];

		s_acc      += delta;
		s_edge_cnt += delta;
		s_prev      = cur;
	}

#if ENC_SW_ENABLE
	if (GPIO_ReadInputDataBit(ENC_SW_PORT, ENC_SW_PIN) == Bit_RESET)
	{
		if (s_btn_cnt < ENC_BTN_DEBOUNCE_MS)
		{
			s_btn_cnt++;
		}
	}
	else
	{
		if (s_btn_cnt >= ENC_BTN_DEBOUNCE_MS)
		{
			s_btn_event = 1;
		}
		s_btn_cnt = 0;
	}
#endif
}

/**
  * @brief  取一次旋转步进：+1 顺时针一格，-1 逆时针一格，0 无动作
  * @note   主循环里反复调用即可，不阻塞
  */
int8_t Encoder_GetStep(void)
{
	int8_t step = 0;

	__disable_irq();
	if (s_acc >= ENC_STEPS_PER_DETENT)
	{
		step = 1;
		s_acc = 0;
	}
	else if (s_acc <= -ENC_STEPS_PER_DETENT)
	{
		step = -1;
		s_acc = 0;
	}
	__enable_irq();

	return step;
}

/**
  * @brief  取一次按键事件：1 表示刚按下并松开过一次
  */
uint8_t Encoder_ButtonEvent(void)
{
#if ENC_SW_ENABLE
	uint8_t event;

	__disable_irq();
	event = s_btn_event;
	s_btn_event = 0;
	__enable_irq();

	return event;
#else
	return 0;
#endif
}

/* ---------------------------------------------------------------- 自检接口
 * 只给“接线自检”固件用：把 A/B 电平和跳变次数直接显示在屏幕上，
 * 用来区分「线没接对」和「解码阈值太大」。
 */
uint8_t Encoder_ReadAB(void)
{
	return (uint8_t)((ENC_READ_A() << 1) | ENC_READ_B());
}

uint32_t Encoder_GetIsrCount(void)
{
	return s_isr_cnt;
}

int32_t Encoder_GetEdgeCount(void)
{
	return s_edge_cnt;
}

void Encoder_ResetStat(void)
{
	__disable_irq();
	s_edge_cnt = 0;
	s_isr_cnt  = 0;
	__enable_irq();
}
