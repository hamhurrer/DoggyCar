#ifndef __ESP32_WIFI_HPP_
#define __ESP32_WIFI_HPP_

#include <stdio.h>
#include <string.h>
#include <Arduino.h>
#include <SoftwareSerial.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ESPWIFISerial  Serial 

#define MODE_AP 			    0 
#define MODE_STA 			    0	
#define MODE_AP_STA 	    1

typedef struct ESP32_AI_Msg_t
{
  int16_t lx; // 左上角
  int16_t ly; // 左上角
  int16_t rx; // 右下角
  int16_t ry; // 右下角
  int16_t cx; // 中心点
  int16_t cy; // 中心点
  uint16_t area; // 面积
  int16_t id;  // 人脸id
} ESP32_AI_Msg;

typedef struct QR_AI_Msg_t
{
  char QR_msg[50]; // QRmsg的处理
} QR_AI_Msg;

typedef enum AI_mode_t
{
    Nornal_AI = 0, // 不检测
    Cat_Dog_AI,   // 猫狗检测
    FACE_AI,      // 人脸检测
    COLOR_AI,    // 颜色检测
    REFACE_AI,   // 人脸识别
    QR_AI = 5,   // 二维码识别
    AI_MAX      // 最大值
} AI_mode;

// 函数声明
void serial_init(void);
void SET_ESP_AI_MODE(AI_mode Mode);
void SET_ESP_WIFI_MODE(void);
void SET_STA_WIFI(void);
void SET_AP_WIFI(void);
void Get_STAIP(void);
void Get_APIP(void);
void Get_Version(void);
void recv_data(void);
void Data_Deal(char RXdata);
void recv_tcp_data(char tcpdata);
void recv_AI_data(char AIdata);
void recv_QR_data(char QRdata);
void recv_face_data(char facedata);
void Get_AI_msg(char *buf);
void Get_faceAI_msg(char *buf);
void recv_gps_data(char gpsdata);
void process_gps_packet(char* buffer);

// 全局变量声明
extern uint8_t newlines;
extern AI_mode runmode;
extern QR_AI_Msg QR_msg;
extern ESP32_AI_Msg esp32_ai_msg;
extern uint8_t cmd_flag;

// 声明SoftwareSerial对象
extern SoftwareSerial IRMODELSerial;

#ifdef __cplusplus
}
#endif

#endif