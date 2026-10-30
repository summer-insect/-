#ifndef __Key_H__
#define __Key_H__

#include "stm32f10x.h"

/* 按键返回值定义 */
#define KEY_NONE     0    // 无按键按下
#define KEY_SELECT   1    // PA5 选择键（切换歌曲）
#define KEY_CONFIRM  2    // PA3 确认键（播放歌曲）

void Key_Init(void);
uint8_t Key_GetNum(void);        // 获取键值（带消抖，松开后返回）
uint8_t Key_GetState(void);      // 获取键值（实时状态，不等待松开）

#endif
