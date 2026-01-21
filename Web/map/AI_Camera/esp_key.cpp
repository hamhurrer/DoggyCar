#include "esp_key.hpp"

// 全局变量定义
uint8_t Virtual_key = 1;
uint8_t Key_send = 0;

void init_key(void)
{
  // 不需要按键功能，留空
}

int key_state()
{
  return 0; // 总是返回0，表示无按键
}

void key_goto_state(void)
{
  // 不需要按键功能，留空
}

void send_key(void)
{
  // 不需要按键功能，留空
}