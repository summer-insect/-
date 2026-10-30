/**
  * @file    Buzzer.c
  * @brief   蜂鸣器音乐播放模块（起风了 + 晴天 + 落泪）
  *
  * 硬件连接: PB12 → 蜂鸣器
  * 定时器:   TIM3用于音调生成（中断中翻转蜂鸣器引脚）
  *
  * 移植自8051版本:
  * - 原8051版本使用Timer0 + 11.0592MHz晶振生成音调
  * - STM32版本使用TIM3 (PSC=71, 定时器时钟=1MHz) 生成音调
  * - 乐谱数据格式: {音符编号, 时长基数}
  *
  * 转换公式:
  * 8051 定时器时钟 = 11.0592MHz / 12 = 921.6kHz
  * STM32 定时器时钟 = 72MHz / (PSC+1) = 72MHz / 72 = 1MHz
  * ARR = 1000000 × (65536 - TH0_TL0) / 921600 - 1
  */

#include "stm32f10x.h"                  // Device header
#include "Buzzer.h"
#include "Delay.h"

/* ======================== 歌曲名称 ======================== */
const char *SONG_NAMES[SONG_COUNT] = {
    "起风了",
    "晴天",
    "落泪"
};

/* ======================== 全局变量 ======================== */
uint16_t g_noteIndex = 0;               // 当前音符索引
uint8_t  g_currentSong = 0;             // 当前播放的歌曲编号

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

/* ======================== 乐谱数据 ======================== */
static const uint8_t MUSIC_QIFENGLE[][2] = {
    {P,4},
    {M4,2},{M4_,2},{M5_,2},{M6_,2},{L6_,4},{H1_,2},{M6_,6},{P,2},{M4,2},{M4_,2},{M5_,2},{M6_,2},{L5_,4},{H1_,2},{M6_,2},{M5_,2},{M6_,2},{M4_,2},{M5_,2},{M4,2},{M4_,2},
    {M1_,2},{P,4},{M4,2},{M4_,2},{M5_,2},{M6_,2},{L6_,4},{H1_,2},{M6_,6},{P,2},{M4,2},{M4_,2},{M5_,2},{M6_,2},{L5_,4},{H1_,2},{M6_,2},{M5_,2},{M6_,2},{M4_,2},{M5_,2},
    {M4,2},{M4_,2},{M1_,2},{P,4},{L5_,6},{L4_,2},{L5_,6},{L4_,2},{L5_,4},{L6_,4},{M1_,4},{L6_,4},{L5_,6},{L4_,2},{L5_,6},{L4_,2},{L5_,2},{L6_,2},{L5_,2},{L4_,2},{L1,4},{P,4},{L5_,6},
    {L4_,2},{L5_,6},{L4_,2},{L5_,4},{L6_,4},{M1_,4},{L6_,4},{L5_,6},{L6_,2},{L5_,4},{L4_,4},{L5_,8},{P,8},{L5_,6},{L4_,2},{L5_,6},{L4_,2},{L5_,4},{L6_,4},{M1_,4},{L6_,4},{L5_,6},{L6_,2},
    {L5_,4},{L4_,4},{L2,4},{P,4},{L6_,2},{L5_,2},{L4_,2},{L5_,2},{L4_,4},{P,4},{L6_,2},{L5_,2},{L4_,2},{L5_,2},{L4_,4},{P,4},{L6_,2},{L5_,2},{L4_,2},{L5_,2},{L4_,8},{P,8},{P,4},{L4_,4},
    {L5_,4},{L6_,4},{L4_,4},{M2_,4},{M1_,2},{M2_,6},{P,2},{L4_,2},{M4,4},{M2_,2},{M4,6},{P,4},{M4,4},{M2_,2},{M4,6},{L6_,4},{M4_,2},{M5_,2},{M4_,2},{M4,2},{M2_,4},{M1_,4},
    {M2_,4},{M1_,2},{M2_,4},{M1_,2},{M2_,2},{M1_,2},{M2_,4},{M1_,2},{L5_,4},{M1_,4},{L6_,8},{P,8},{L4_,4},{L5_,4},{L6_,4},{L4_,4},{M2_,4},{M1_,2},{M2_,6},{P,2},{L4_,2},{M4,4},
    {M2_,2},{M4,6},{P,4},{M4,4},{M2_,2},{M4,6},{L6_,4},{M4_,2},{M5_,2},{M4_,2},{M4,2},{M2_,4},{M1_,4},{M2_,4},{M6_,2},{M6_,6},{M1_,4},{M2_,4},{M6_,2},{M6_,4},{M1_,4},
    {M2_,2},{M2_,12},{P,4},{M4_,4},{M5_,4},{M6_,4},{H2_,2},{H1_,6},{H2_,2},{H1_,6},{H2_,2},{H1_,6},{M5_,4},{M6_,6},{H2_,2},{H1_,6},{H2_,2},{H1_,6},{H2_,2},{H1_,4},{M6_,8},
    {M5_,4},{M4_,2},{M2_,4},{M4_,4},{M4_,2},{M5_,4},{M4_,2},{M2_,4},{M4_,4},{M6_,8},{M6_,4},{M5_,6},{P,4},{M4_,4},{M5_,4},{M6_,4},{H2_,2},{H1_,6},{H2_,2},{H1_,6},{H2_,2},
    {H1_,6},{P,2},{M5_,2},{M6_,4},{H2_,2},{H1_,6},{H2_,2},{H1_,6},{H2_,2},{H1_,6},{M6_,6},{M5_,4},{M4_,2},{M2_,4},{M6_,4},{M5_,4},{M4_,2},{M2_,4},{M2_,2},{M4_,2},{M4_,8},
    {P,4},{M2_,2},{M6_,6},{M5_,4},{M4_,2},{M2_,4},{M6_,4},{M5_,4},{M4_,2},{M2_,4},{M2_,2},{M4_,6},{M4_,8},{0xFF,0xFF}
};

static const uint8_t MUSIC_QINGTIAN[][2] = {
    {L6_,4},{M1_,4},{M5_,4},{M1_,4},{L4_,4},{L5_,2},{L6_,2},{M5_,4},{M1_,4},{M1_,4},{L5_,4},
    {M5_,4},{M1_,4},{M1_,4},{M5_,4},{M1,4},{M5_,4},{L6_,4},{M1_,4},{M5_,4},{M1_,4},{L4_,4},
    {L5_,2},{L6_,2},{M5_,4},{M1_,4},{M1_,4},{L5_,4},{M5_,4},{M1_,4},{M1_,4},{M5_,4},{L5_,2},
    {M1_,2},{M5_,4},{P,4},{M5_,4},{M5_,4},{M1_,4},{M1_,7},{M2_,4},{M4,4},{P,4},{M5_,4},
    {M5_,4},{M1_,4},{M1_,4},{M2_,2},{M4,2},{M2_,2},{M1_,2},{L5_,4},{P,4},{M5_,4},{M5_,4},
    {M1_,4},{M1_,7},{M2_,4},{M4,4},{P,4},{M4,7},{M2_,2},{M4,2},{M4_,2},{M4,2},{M2_,2},
    {M4_,2},{M4,2},{M2_,2},{M1_,4},{L5_,4},{M1_,4},{M1_,4},{M4,4},{M4_,4},{M4,4},{M2_,4},
    {M1_,2},{M2_,2},{M4,4},{M4,4},{M4,4},{M4,4},{M2_,2},{M4,2},{M2_,4},{M1_,7},{L5_,4},
    {M1_,4},{M2_,4},{M4,4},{M4_,4},{M4,4},{M2_,4},{M1_,2},{M2_,2},{M4,4},{M4,4},{M4,4},
    {M4,4},{M2_,2},{M4,2},{M2_,4},{M1_,5},{P,29},{M1_,2},{M1_,2},{M1_,2},{M1_,2},{L6_,4},
    {M1,4},{M1_,4},{M5_,4},{M4_,4},{M4,4},{M1_,4},{M2,9},{P,4},{M1_,2},{M1_,2},{M1_,2},
    {M1_,2},{M4,4},{M1_,4},{L6_,4},{M1,4},{M1_,4},{M5_,4},{M4_,4},{M4,4},{M1_,4},{M2_,9},
    {M4,4},{M2_,4},{M4_,4},{M4,7},{M1_,4},{M5_,4},{H1,4},{H1_,4},{H1,4},{M5_,4},{M1_,4},
    {P,4},{M1_,4},{M6_,4},{M6_,4},{P,4},{M6_,4},{M5_,4},{M5_,4},{P,4},{M5_,4},{M4_,4},
    {M4,4},{M2_,4},{M4,4},{M4_,4},{M4,9},{P,5},{M4,4},{M4_,4},{M5_,4},{M4,4},{P,4},{M4_,4},
    {M5_,4},{H1,4},{H2_,4},{H1,4},{H1_,4},{H1_,9},{P,4},{H1_,4},{H1_,4},{M5_,4},{M5_,4},
    {M6_,4},{M5_,4},{M4_,4},{M2_,4},{M4,4},{M4_,4},{M5_,4},{M6_,4},{M1_,4},{M6_,5},{H1,2},
    {H1,7},{M4,4},{M2_,4},{M4_,4},{M4,4},{P,4},{M1_,4},{M5_,4},{H1,4},{H1_,4},{H1,4},
    {M5_,4},{M1_,4},{P,4},{M1_,4},{M6_,4},{M6_,4},{P,4},{M6_,4},{M5_,4},{M5_,4},{P,4},
    {M5_,4},{M4_,4},{M4,4},{M2_,4},{M4,4},{M4_,4},{M4,11},{P,4},{M4,4},{M4_,4},{M5_,4},
    {M4,4},{P,4},{M4_,4},{M5_,4},{H1,4},{H2_,4},{H1,4},{H1_,4},{H1_,9},{P,4},{M1_,4},
    {H1_,4},{M5_,4},{M5_,4},{M6_,4},{M5_,4},{M4_,4},{L6_,4},{M1,4},{M1_,4},{M2_,4},{M4,4},
    {M2_,7},{P,1},{M4,4},{M1_,14},
    {0xFF,0xFF}
};

/** 落泪 简谱乐谱（优化版：增加时长+合理停顿）
  * 原问题：速度过快、无停顿感
  * 优化点：
  * 1. 基础时长从2→4（单音400ms，舒缓节奏）
  * 2. 每句结尾加200ms休止符(P,2)
  * 3. 段落间加400ms长休止符(P,4)
  * 4. 保留原旋律走向，仅调整节奏
  */
/** 落泪 简谱乐谱（全部音符时长4改为3，舒缓节奏）
  * 基础音符时长300ms，句尾200ms停顿，段落400ms长停顿
  */
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


/* ======================== 歌曲数据指针数组 ======================== */
static const uint8_t (*MUSIC_SONGS[SONG_COUNT])[2] = {
    MUSIC_QIFENGLE,
    MUSIC_QINGTIAN,
    MUSIC_LUOLUO
};


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

void Buzzer_On(void)
{
    TIM_Cmd(TIM3, DISABLE);
    GPIO_SetBits(GPIOB, GPIO_Pin_12);
}

void Buzzer_Off(void)
{
    TIM_Cmd(TIM3, DISABLE);
    GPIO_ResetBits(GPIOB, GPIO_Pin_12);
}

void Music_Play(uint8_t songIndex)
{
    uint8_t currNote;
    uint8_t currTime;
    const uint8_t (*pMusic)[2];

    if (songIndex >= SONG_COUNT) return;
    pMusic = MUSIC_SONGS[songIndex];
    g_noteIndex = 0;

    while (1)
    {
        currNote = pMusic[g_noteIndex][0];
        currTime = pMusic[g_noteIndex][1];

        if (currNote == 0x00)  // 休止符处理
        {
            TIM_Cmd(TIM3, DISABLE);
            GPIO_ResetBits(GPIOB, GPIO_Pin_12);
            Delay_ms(currTime * 100);
        }
        else if (currNote == 0xFF)  // 结束标记
        {
            TIM_Cmd(TIM3, DISABLE);
            GPIO_ResetBits(GPIOB, GPIO_Pin_12);
            Delay_ms(1500);
            return;
        }
        else  // 有效音符播放
        {
            TIM_SetAutoreload(TIM3, TONE_ARR[currNote]);
            TIM_SetCounter(TIM3, 0);
            TIM_Cmd(TIM3, ENABLE);
            Delay_ms(currTime * 100);
            TIM_Cmd(TIM3, DISABLE);
            GPIO_ResetBits(GPIOB, GPIO_Pin_12);
            Delay_ms(10);  
        }
        g_noteIndex++;
    }
}

void TIM3_IRQHandler(void)
{
    if (TIM_GetITStatus(TIM3, TIM_IT_Update) == SET)
    {
        GPIOB->ODR ^= GPIO_Pin_12;
        TIM_ClearITPendingBit(TIM3, TIM_IT_Update);
    }
}
