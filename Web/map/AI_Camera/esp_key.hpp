#ifndef __ESP_KEY_HPP_
#define __ESP_KEY_HPP_

#include <Arduino.h>

#ifdef __cplusplus
extern "C" {
#endif

extern uint8_t Virtual_key;
extern uint8_t Key_send;

void init_key(void);
int key_state();
void key_goto_state(void);
void send_key(void);

#ifdef __cplusplus
}
#endif

#endif