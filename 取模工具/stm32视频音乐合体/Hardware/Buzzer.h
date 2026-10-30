#ifndef __BUZZER_H
#define __BUZZER_H

#include "stm32f10x.h"

/* ======================== 音符与索引对应表 ======================== */
/* P：休止符，L：低音，M：中音，H：高音，下划线：升半音符号# */
#define P	0
#define L1	1
#define L1_	2
#define L2	3
#define L2_	4
#define L3	5
#define L4	6
#define L4_	7
#define L5	8
#define L5_	9
#define L6	10
#define L6_	11
#define L7	12
#define M1	13
#define M1_	14
#define M2	15
#define M2_	16
#define M3	17
#define M4	18
#define M4_	19
#define M5	20
#define M5_	21
#define M6	22
#define M6_	23
#define M7	24
#define H1	25
#define H1_	26
#define H2	27
#define H2_	28
#define H3	29
#define H4	30
#define H4_	31
#define H5	32
#define H5_	33
#define H6	34
#define H6_	35
#define H7	36

/* 函数声明 */
void    Buzzer_Init(void);      // 蜂鸣器初始化（GPIO PB12 + TIM3音调定时器）
void    Buzzer_Off(void);       // 蜂鸣器关闭

/* 非阻塞音乐播放 API（仅落泪） */
void    Music_Start(void);      // 启动落泪播放
void    Music_Process(void);    // 状态机处理（每1ms由TIM2中断调用）
uint8_t Music_IsPlaying(void);  // 查询是否正在播放（1=播放中, 0=空闲/已结束）

#endif
