/**
  * @file    Buzzer.c
  * @brief   蜂鸣器音乐播放模块（非阻塞版 — 仅落泪）
  *
  * 硬件连接: PB12 → 蜂鸣器
  * 定时器:   TIM3用于音调生成（中断中翻转蜂鸣器引脚）
  *           TIM2用于音乐时长计时（1ms tick，在main.c中调用Music_Process()）
  *
  * 架构: 非阻塞状态机，由 TIM2 中断每1ms驱动一次
  */

#include "stm32f10x.h"
#include "Buzzer.h"

/* ======================== 音调表 ======================== */
static const uint16_t TONE_ARR[49] = {
        0,     // [ 0] 休止符
     2070,     // [ 1] L1
     1958,     // [ 2] L1_
     1844,     // [ 3] L2
     1744,     // [ 4] L2_
     1643,     // [ 5] L3
     1554,     // [ 6] L4
     1464,     // [ 7] L4_
     1384,     // [ 8] L5
     1307,     // [ 9] L5_
     1232,     // [10] L6
     1163,     // [11] L6_
     1098,     // [12] L7
     1037,     // [13] M1
      979,     // [14] M1_
      924,     // [15] M2
      872,     // [16] M2_
      823,     // [17] M3
      776,     // [18] M4
      733,     // [19] M4_
      692,     // [20] M5
      653,     // [21] M5_
      616,     // [22] M6
      581,     // [23] M6_
      549,     // [24] M7
      518,     // [25] H1
      489,     // [26] H1_
      462,     // [27] H2
      436,     // [28] H2_
      411,     // [29] H3
      388,     // [30] H4
      366,     // [31] H4_
      346,     // [32] H5
      325,     // [33] H5#
      308,     // [34] H6
      290,     // [35] H6_
      274,     // [36] H7
      259,     // [37]
      245,     // [38]
      231,     // [39]
      218,     // [40]
      205,     // [41]
      194,     // [42]
      183,     // [43]
      172,     // [44]
      162,     // [45]
      154,     // [46]
      145,     // [47]
      136,     // [48]
};

/* ======================== 落泪 乐谱 ======================== */
static const uint8_t MUSIC_LUOLUO[][2] = {
    // 第一段：5 5 5 5 4 4 3
    {M5_,3},{M5_,3},{M5_,3},{M5_,3},{M4_,3},{M4_,3},{M3,3},{P,1},

    // 第二段：5 5 5 5 i 7 i
    {M5_,3},{M5_,3},{M5_,3},{M5_,3},{H1_,3},{M7,3},{H1_,3},{P,1},

    // 第三段：5 5 5 5 4 4 3
    {M5_,3},{M5_,3},{M5_,3},{M5_,3},{M4_,3},{M4_,3},{M3,3},{P,1},
    {P,2},  // 段落长停顿

    // 第四段：i i 1 1 5 3 3
    {H1_,3},{H1_,3},{M1_,3},{M1_,3},{M5_,3},{M3,3},{M3,3},{P,1},

    // 第五段：5 5 5 5 4 4 3
    {M5_,3},{M5_,3},{M5_,3},{M5_,3},{M4_,3},{M4_,3},{M3,3},{P,1},

    // 第六段：5 5 5 5 i 7 i
    {M5_,3},{M5_,3},{M5_,3},{M5_,3},{H1_,3},{M7,3},{H1_,3},{P,1},

    // 第七段：5 5 7 i 5 5 5 5 5 i i
    {M5_,3},{M5_,3},{M7,3},{H1_,3},{M5_,3},{M5_,3},{M5_,3},{M5_,3},{M5_,3},{H1_,3},{H1_,3},
    {M5_,3},{M5_,3},{M5_,3},{M5_,3},{M5_,3},{M5_,3},{H1,3},{H1_,3},
    {P,4},  // 结尾长停顿
    {0xFF,0xFF}  // 乐曲结束标记
};

/* ======================== 非阻塞播放状态机 ======================== */

typedef enum {
    MUSIC_IDLE = 0,
    MUSIC_NOTE_START,
    MUSIC_NOTE_PLAYING,
    MUSIC_NOTE_GAP,
    MUSIC_REST,
    MUSIC_END_DELAY,
    MUSIC_FINISHED
} MusicPlayState;

static MusicPlayState   music_state        = MUSIC_IDLE;
static uint16_t         music_tick_count   = 0;
static uint16_t         music_duration_ms  = 0;
static uint8_t          music_curr_note    = 0;
static uint8_t          music_curr_time    = 0;
static uint16_t         music_note_index   = 0;

/* ======================== 蜂鸣器硬件初始化 ======================== */
void Buzzer_Init(void)
{
    NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);

    /* PB12 GPIO */
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE);
    GPIO_InitTypeDef GPIO_InitStructure;
    GPIO_InitStructure.GPIO_Mode  = GPIO_Mode_Out_PP;
    GPIO_InitStructure.GPIO_Pin   = GPIO_Pin_12;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOB, &GPIO_InitStructure);

    /* TIM3 1MHz */
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM3, ENABLE);
    TIM_TimeBaseInitTypeDef TIM_TimeBaseInitStructure;
    TIM_TimeBaseInitStructure.TIM_ClockDivision     = TIM_CKD_DIV1;
    TIM_TimeBaseInitStructure.TIM_CounterMode       = TIM_CounterMode_Up;
    TIM_TimeBaseInitStructure.TIM_Period            = 1000 - 1;
    TIM_TimeBaseInitStructure.TIM_Prescaler         = 72 - 1;
    TIM_TimeBaseInitStructure.TIM_RepetitionCounter = 0;
    TIM_TimeBaseInit(TIM3, &TIM_TimeBaseInitStructure);

    TIM_ClearFlag(TIM3, TIM_FLAG_Update);
    TIM_ITConfig(TIM3, TIM_IT_Update, ENABLE);

    NVIC_InitTypeDef NVIC_InitStructure;
    NVIC_InitStructure.NVIC_IRQChannel                   = TIM3_IRQn;
    NVIC_InitStructure.NVIC_IRQChannelCmd                = ENABLE;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority  = 1;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority         = 1;
    NVIC_Init(&NVIC_InitStructure);

    TIM_Cmd(TIM3, DISABLE);
    GPIO_ResetBits(GPIOB, GPIO_Pin_12);
}

void Buzzer_Off(void)
{
    TIM_Cmd(TIM3, DISABLE);
    GPIO_ResetBits(GPIOB, GPIO_Pin_12);
}

/* ======================== 非阻塞音乐播放 API ======================== */

/**
  * @brief  启动落泪播放（非阻塞）
  */
void Music_Start(void)
{
    music_note_index  = 0;
    music_state       = MUSIC_NOTE_START;
    music_tick_count  = 0;
    music_duration_ms = 0;

    TIM_Cmd(TIM3, DISABLE);
    GPIO_ResetBits(GPIOB, GPIO_Pin_12);
}

/**
  * @brief  音乐状态机处理（每1ms调用一次，由TIM2中断驱动）
  */
void Music_Process(void)
{
    if (music_state == MUSIC_IDLE || music_state == MUSIC_FINISHED)
        return;

    music_tick_count++;

    switch (music_state)
    {
        case MUSIC_NOTE_START:
        {
            music_curr_note = MUSIC_LUOLUO[music_note_index][0];
            music_curr_time = MUSIC_LUOLUO[music_note_index][1];

            if (music_curr_note == 0x00)        // 休止符
            {
                TIM_Cmd(TIM3, DISABLE);
                GPIO_ResetBits(GPIOB, GPIO_Pin_12);
                music_duration_ms = music_curr_time * 100;
                music_tick_count  = 0;
                music_state = MUSIC_REST;
            }
            else if (music_curr_note == 0xFF)   // 乐曲结束
            {
                TIM_Cmd(TIM3, DISABLE);
                GPIO_ResetBits(GPIOB, GPIO_Pin_12);
                music_duration_ms = 1500;
                music_tick_count  = 0;
                music_state = MUSIC_END_DELAY;
            }
            else                                // 有效音符
            {
                TIM_SetAutoreload(TIM3, TONE_ARR[music_curr_note]);
                TIM_SetCounter(TIM3, 0);
                TIM_Cmd(TIM3, ENABLE);
                music_duration_ms = music_curr_time * 100;
                music_tick_count  = 0;
                music_state = MUSIC_NOTE_PLAYING;
            }
            break;
        }

        case MUSIC_NOTE_PLAYING:
        {
            if (music_tick_count >= music_duration_ms)
            {
                TIM_Cmd(TIM3, DISABLE);
                GPIO_ResetBits(GPIOB, GPIO_Pin_12);
                music_duration_ms = 10;
                music_tick_count  = 0;
                music_state = MUSIC_NOTE_GAP;
            }
            break;
        }

        case MUSIC_NOTE_GAP:
        {
            if (music_tick_count >= music_duration_ms)
            {
                music_note_index++;
                music_tick_count = 0;
                music_state = MUSIC_NOTE_START;
            }
            break;
        }

        case MUSIC_REST:
        {
            if (music_tick_count >= music_duration_ms)
            {
                music_note_index++;
                music_tick_count = 0;
                music_state = MUSIC_NOTE_START;
            }
            break;
        }

        case MUSIC_END_DELAY:
        {
            if (music_tick_count >= music_duration_ms)
            {
                music_tick_count = 0;
                music_state = MUSIC_FINISHED;
            }
            break;
        }

        default:
            break;
    }
}

/**
  * @brief  查询是否正在播放
  */
uint8_t Music_IsPlaying(void)
{
    return (music_state != MUSIC_IDLE && music_state != MUSIC_FINISHED);
}

/* ======================== TIM3 中断服务函数 ======================== */
void TIM3_IRQHandler(void)
{
    if (TIM_GetITStatus(TIM3, TIM_IT_Update) == SET)
    {
        GPIOB->ODR ^= GPIO_Pin_12;
        TIM_ClearITPendingBit(TIM3, TIM_IT_Update);
    }
}
