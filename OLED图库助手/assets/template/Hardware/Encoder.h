#ifndef __ENCODER_H
#define __ENCODER_H

#include "stm32f10x.h"

void Encoder_Init(void);
int8_t Encoder_GetStep(void);
uint8_t Encoder_ButtonEvent(void);

/* 以下是接线自检用的接口，正常使用不需要调用 */
uint8_t Encoder_ReadAB(void);        /* bit1 = A 相电平，bit0 = B 相电平 */
uint32_t Encoder_GetIsrCount(void);  /* 1ms 定时中断累计次数 */
int32_t Encoder_GetEdgeCount(void);  /* 两相跳变累计数（带方向） */
void Encoder_ResetStat(void);        /* 清零上面两个计数 */

#endif
