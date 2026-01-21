#include <stdio.h>
#include <SoftwareSerial.h>
#include <string.h>
#include "esp32_wifi.hpp"

#define AI_set_mode REFACE_AI  // 设置AI模式为人脸识别

// GPS相关定义
#define GPS_RX_PIN 10  // GPS模块TX连接Arduino的RX (Pin10)
#define GPS_TX_PIN 11  // GPS模块RX连接Arduino的TX (Pin11)
SoftwareSerial gpsSerial(GPS_RX_PIN, GPS_TX_PIN);  // 软件串口连接GPS

// GPS数据结构
struct GPSData {
  char utcTime[12];    // UTC时间（增大1位）
  char latitude[12];   // 纬度（增大1位）
  char longitude[13];  // 经度（增大1位）
  char nsIndicator[2]; // N/S指示
  char ewIndicator[2]; // E/W指示
  bool isValid;        // 数据是否有效
  float speed;         // 速度(节)
  float course;        // 航向
};

GPSData currentGPS;
unsigned long lastGPSTime = 0;
const unsigned long GPS_INTERVAL = 1000;  // 1秒发送一次GPS数据
unsigned long gpsLastUpdate = 0;

void mode_change()
{
  if(runmode == Nornal_AI) 
  {
    cmd_flag = 2; // 进入透传模式
  }
  else if(runmode == REFACE_AI)
  {
    cmd_flag = 3; // 解析人脸识别数据
  }
  else if(runmode == QR_AI)
  {
    cmd_flag = 4; // 解析二维码数据
  }
  else
  {
    cmd_flag = 5; // 其它AI模式数据
  }
}

void detect_face()
{
  if (esp32_ai_msg.cx != 160) // 过滤默认值
  {
    char faceData[50];
    sprintf(faceData, "$FACE,%d,%d,%d#", esp32_ai_msg.cx, esp32_ai_msg.cy, esp32_ai_msg.id);
    IRMODELSerial.print(faceData);
    ESPWIFISerial.print("发送人脸数据: ");
    ESPWIFISerial.println(faceData);
  }
}

// GPS初始化
void gps_init() {
  gpsSerial.begin(9600);
  // 初始化GPS数据结构
  strcpy(currentGPS.utcTime, "000000.00");
  strcpy(currentGPS.latitude, "0000.0000");
  strcpy(currentGPS.longitude, "00000.0000");
  strcpy(currentGPS.nsIndicator, "N");
  strcpy(currentGPS.ewIndicator, "E");
  currentGPS.isValid = false;
  currentGPS.speed = 0.0;
  currentGPS.course = 0.0;
  
  ESPWIFISerial.println("GPS模块初始化完成");
  delay(100);
}

// GPS数据处理函数
void processGPS() {
  static char gpsBuffer[256];
  static int bufferIndex = 0;
  
  while (gpsSerial.available()) {
    char c = gpsSerial.read();
    
    // 查找句子开始
    if (c == '$') {
      bufferIndex = 0;
      gpsBuffer[bufferIndex++] = c;
    }
    // 存储数据直到换行符
    else if (c == '\n') {
      gpsBuffer[bufferIndex] = '\0';
      
      // 解析GPRMC语句（推荐位置速度时间数据）
      if (strstr(gpsBuffer, "$GPRMC") || strstr(gpsBuffer, "$GNRMC")) {
        parseGPRMC(gpsBuffer);
      }
      
      bufferIndex = 0;
    }
    // 存储数据
    else if (bufferIndex < 255) {
      gpsBuffer[bufferIndex++] = c;
    }
  }
}

// 解析GPRMC语句
void parseGPRMC(char* buffer) {
  char* tokens[13];
  char tempBuffer[256];
  strcpy(tempBuffer, buffer);
  
  char* ptr = strtok(tempBuffer, ",");
  int i = 0;
  
  // 分割字符串
  while (ptr != NULL && i < 13) {
    tokens[i++] = ptr;
    ptr = strtok(NULL, ",");
  }
  
  if (i >= 12) {  // GPRMC至少有12个字段
    // UTC时间 (HHMMSS.SS)
    if (strlen(tokens[1]) > 0) {
      strncpy(currentGPS.utcTime, tokens[1], min(11, (int)strlen(tokens[1])));
      currentGPS.utcTime[11] = '\0';
    }
    
    // 状态 A=有效, V=无效
    currentGPS.isValid = (tokens[2][0] == 'A');
    
    // 纬度 (DDMM.MMMM)
    if (strlen(tokens[3]) > 0) {
      strncpy(currentGPS.latitude, tokens[3], min(11, (int)strlen(tokens[3])));
      currentGPS.latitude[11] = '\0';
      strncpy(currentGPS.nsIndicator, tokens[4], 1);
      currentGPS.nsIndicator[1] = '\0';
    }
    
    // 经度 (DDDMM.MMMM)
    if (strlen(tokens[5]) > 0) {
      strncpy(currentGPS.longitude, tokens[5], min(12, (int)strlen(tokens[5])));
      currentGPS.longitude[12] = '\0';
      strncpy(currentGPS.ewIndicator, tokens[6], 1);
      currentGPS.ewIndicator[1] = '\0';
    }
    
    // 速度 (节)
    if (strlen(tokens[7]) > 0) {
      currentGPS.speed = atof(tokens[7]);
    }
    
    // 航向 (度)
    if (i > 8 && strlen(tokens[8]) > 0) {
      currentGPS.course = atof(tokens[8]);
    }
    
    // 更新标志
    gpsLastUpdate = millis();
    
    // 调试输出
    if (currentGPS.isValid) {
      ESPWIFISerial.print("GPS有效数据: ");
      ESPWIFISerial.print(currentGPS.utcTime);
      ESPWIFISerial.print(", Lat: ");
      ESPWIFISerial.print(currentGPS.latitude);
      ESPWIFISerial.print(currentGPS.nsIndicator);
      ESPWIFISerial.print(", Lon: ");
      ESPWIFISerial.print(currentGPS.longitude);
      ESPWIFISerial.print(currentGPS.ewIndicator);
      ESPWIFISerial.print(", Speed: ");
      ESPWIFISerial.print(currentGPS.speed);
      ESPWIFISerial.print(", Course: ");
      ESPWIFISerial.println(currentGPS.course);
    }
  }
}

// 发送GPS数据到WiFi模块
void sendGPSData() {
  if (millis() - lastGPSTime > GPS_INTERVAL) {
    lastGPSTime = millis();
    
    // 构建GPS数据包
    char gpsPacket[120];
    
    if (currentGPS.isValid && (millis() - gpsLastUpdate < 5000)) {
      // 构建标准GPS数据格式：$GPS,时间,纬度,N/S,经度,E/W,速度,航向#
      snprintf(gpsPacket, sizeof(gpsPacket), "$GPS,%s,%s,%s,%s,%s,%.1f,%.1f#",
              currentGPS.utcTime,
              currentGPS.latitude,
              currentGPS.nsIndicator,
              currentGPS.longitude,
              currentGPS.ewIndicator,
              currentGPS.speed,
              currentGPS.course);
    } else {
      // 无有效GPS信号
      snprintf(gpsPacket, sizeof(gpsPacket), "$GPS,NO_SIGNAL#");
    }
    
    // 通过IRMODELSerial发送GPS数据（与摄像头共用通道）
    IRMODELSerial.print(gpsPacket);
    ESPWIFISerial.print("发送GPS: ");
    ESPWIFISerial.println(gpsPacket);
  }
}

void setup()
{
  serial_init();             // 串口初始化
  
  // GPS初始化
  gps_init();
  
  SET_ESP_WIFI_MODE();       // 设置wifi模式
  SET_STA_WIFI();
  SET_AP_WIFI();
  SET_ESP_AI_MODE(AI_set_mode); // 设置AI模式
  delay(20);
  Get_STAIP();
  delay(20);
  Get_APIP();
  delay(20);
  
  mode_change();              // 根据模式选择解析数据办法
  
  // 通知电脑系统已就绪
  ESPWIFISerial.println("系统已启动 - GPS和摄像头已集成");
  ESPWIFISerial.println("等待连接...");
}

void loop() 
{
  // 1. 接收来自WiFi模块的数据
  recv_data();
  
  // 2. 数据处理
  if(newlines == 1) // 接收到新数据
  {
    newlines = 0;
    if(runmode == REFACE_AI && esp32_ai_msg.cx != 160)
    {
      // 识别人脸
      detect_face();
    }
  }
  
  // 3. 处理GPS数据
  processGPS();
  
  // 4. 发送GPS数据
  sendGPSData();
  
  // 小延迟，避免占用太多CPU
  delay(10);
}