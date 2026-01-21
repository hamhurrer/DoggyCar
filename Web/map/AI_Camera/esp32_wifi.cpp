#include "esp32_wifi.hpp"
#include <stdio.h>
#include <string.h>
#include <SoftwareSerial.h>
#include <Arduino.h>

// 定义宏
#if MODE_AP_STA
#define WIFI_MODE '2'
#elif MODE_STA
#define WIFI_MODE '1'
#elif MODE_AP 
#define WIFI_MODE '0'
#else
#define WIFI_MODE '2'
#endif

// 自发热点部分
#define APIP "ap_ip" 
#define AP_WIFI_SSID "ESP32_WIFI_TEST"      // wifi名称
#define AP_WIFI_PD   ""                     // 无密码

// 连接wifi部分
#define STAIP "sta_ip"  
#define STA_WIFI_SSID "Yahboom2"            // wifi名称
#define STA_WIFI_PD   "yahboom890729"       // wifi密码

// AI模式标志
AI_mode runmode = Nornal_AI;
ESP32_AI_Msg esp32_ai_msg;  // 二维码以外的结构体
QR_AI_Msg QR_msg;
SoftwareSerial IRMODELSerial(2, 3); // rx2 tx3 IRMODELSerial

char send_buf[35] = {0}; // 发送命令的buf
char recv_buf[100] = {0}; // 接收buf（增大到100以容纳更多数据）
char data_buff[100] = {0}; // 备份buf
uint8_t cmd_flag = 0;     // 发送命令的标志
uint8_t time_counter = 0;
uint8_t newlines = 0;     // 1:接收新的数据 0:没合适数据

// GPS相关变量
static bool g_gpsNewFlag = false;
static int g_gpsIndex = 0;
static char g_gpsBuffer[100];

void serial_init(void)
{
  ESPWIFISerial.begin(115200);
  IRMODELSerial.begin(115200);
}

// 设置sta模式的wifi
void SET_STA_WIFI(void)
{
  // 发送ssid
  sprintf(send_buf, "sta_ssid:%s", STA_WIFI_SSID);
  IRMODELSerial.print(send_buf);
  memset(send_buf, 0, sizeof(send_buf));
  delay(300);

  // 发送pd
  sprintf(send_buf, "sta_pd:%s", STA_WIFI_PD);
  IRMODELSerial.print(send_buf);
  memset(send_buf, 0, sizeof(send_buf));
  delay(2000); // 等待复位重启成功
}

// 设置ap模式的wifi
void SET_AP_WIFI(void)
{
  // 发送ssid
  sprintf(send_buf, "ap_ssid:%s", AP_WIFI_SSID);
  IRMODELSerial.print(send_buf);
  memset(send_buf, 0, sizeof(send_buf));
  delay(300);
  
  // 发送pd
  sprintf(send_buf, "ap_pd:%s", AP_WIFI_PD);
  IRMODELSerial.print(send_buf);
  memset(send_buf, 0, sizeof(send_buf));
  delay(2000); // 等待复位重启成功
}

void SET_ESP_WIFI_MODE(void) // 设置模式选择
{
  // 选择模式STA+AP模式共存
  sprintf(send_buf, "wifi_mode:%c", WIFI_MODE);
  IRMODELSerial.print(send_buf);
  memset(send_buf, 0, sizeof(send_buf));
  delay(2000); // 等待复位重启成功
}

void SET_ESP_AI_MODE(AI_mode Mode) // 设置AI模式
{
  sprintf(send_buf, "ai_mode:%d", Mode);
  IRMODELSerial.print(send_buf);
  memset(send_buf, 0, sizeof(send_buf));
  runmode = Mode;
  delay(2000); // 等待复位重启成功
}

// 查询sta模式的ip
void Get_STAIP(void)
{
  sprintf(send_buf, STAIP);
  IRMODELSerial.print(send_buf);
  memset(send_buf, 0, sizeof(send_buf));
  cmd_flag = 1;
}

// 查询ap模式的ip
void Get_APIP(void)
{
  sprintf(send_buf, APIP);
  IRMODELSerial.print(send_buf);
  memset(send_buf, 0, sizeof(send_buf));
  cmd_flag = 1;
}

void Get_Version(void)
{
  // 查询固件版本号
  sprintf(send_buf, "wifi_ver");
  IRMODELSerial.print(send_buf);
  memset(send_buf, 0, sizeof(send_buf));
  cmd_flag = 1;
}

// 接收数据处理
void recv_data(void)
{
  char strr;
  if (IRMODELSerial.available()) 
  {
    strr = char(IRMODELSerial.read());
    if (time_counter < 65)
    {
      ESPWIFISerial.print(strr);
      time_counter = time_counter + 1;
    }
    Data_Deal(strr);
  }
}

uint8_t end_falg = 0; 
uint8_t i_index = 0; // 数组索引

// 处理串口接收到的信息
void Data_Deal(char RXdata)
{
  // 查询wifi的ip地址情况
  if(cmd_flag == 1)
  {
    recv_buf[i_index] = RXdata;
    
    // 当接收到换行符,一包的数据接收完成
    if(RXdata == 0x0D)
    {
      end_falg = 1;
    }
    
    if(end_falg == 1 && RXdata == 0x0A)
    {   
      cmd_flag = 0;
      end_falg = 0;
      memcpy(data_buff, recv_buf, i_index);
      memset(recv_buf, 0, sizeof(recv_buf)); // 接收数据缓存清0
      i_index = 0; // 索引清0
    }
    else
      i_index++;
  }
  // 网络透传的数据
  else if(cmd_flag == 2)
  {
    recv_tcp_data(RXdata);
  }
  else if(cmd_flag == 3)
  {
    recv_face_data(RXdata); // 人脸识别数据解析
  }
  else if(cmd_flag == 4)
  {
    recv_QR_data(RXdata); // 二维码数据解析
  }
  else if(cmd_flag == 5)
  {
    recv_AI_data(RXdata); // AI模式解析
  }
}

uint8_t g_new_flag = 0;
uint8_t g_index = 0;

// 接收app数据透传的数据
void recv_tcp_data(char tcpdata)
{
  if (tcpdata == '$' && g_new_flag == 0)
  {
    g_new_flag = 1;
    memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    return;
  }
  if(g_new_flag == 1)
  {
    if (tcpdata == '#')
    {
      g_new_flag = 0;
      g_index = 0;
      memcpy(data_buff, recv_buf, sizeof(recv_buf));
      // 处理
      memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    }
    else if (tcpdata == '$') // 中途出现丢包
    {
      g_index = 0;
      g_new_flag = 0;
      memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    }
    else 
    {
      recv_buf[g_index++] = tcpdata;
    }
    
    if(g_index > 50) // 数组溢出
    {
      g_index = 0;
      g_new_flag = 0;
      memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    }
  }
}

// 检测和颜色识别的协议处理
void recv_AI_data(char AIdata) // 协议基本是$xxx,yyy,zzz,hhh,#
{
  if (AIdata == '$' && g_new_flag == 0)
  {
    g_new_flag = 1;
    memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    return;
  }
  
  if(g_new_flag == 1)
  {
    if (AIdata == '#')
    {
      g_new_flag = 0;
      g_index = 0;
      memcpy(data_buff, recv_buf, sizeof(recv_buf));
      // 处理
      Get_AI_msg(data_buff);
      newlines = 1; // 新数据接收完毕
      memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    }
    else if (AIdata == '$') // 中途出现丢包
    {
      g_index = 0;
      g_new_flag = 0;
      memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    }
    else 
    {
      recv_buf[g_index++] = AIdata;
    }
    
    if(g_index > 50) // 数组溢出
    { 
      g_index = 0;
      g_new_flag = 0;
      memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    }
  }
}

// 解析检测AI数据
void Get_AI_msg(char *buf)
{
  char databuf[4] = {"\0"};  // 改为4个字符，包括结束符
  uint8_t len = 0;
  
  if(strlen(buf) != 16) // 当长度不满足协议
  {
    return;  
  }
  
  if(buf[3] != ',' && buf[7] != ',' && buf[11] != ',' && buf[15] != ',') // 不是逗号
  {
    return;
  }
  
  for(uint8_t i = 0; i < 16; i++)
  {
    if(buf[i] == ',')
      len++;  
  }
  
  if(len != 4) // 逗号数量不为4
  {
    return; 
  }

  // 解析lx
  databuf[0] = buf[0];
  databuf[1] = buf[1];
  databuf[2] = buf[2];
  databuf[3] = '\0';
  esp32_ai_msg.lx = atoi(databuf);

  // 解析ly
  databuf[0] = buf[4];
  databuf[1] = buf[5];
  databuf[2] = buf[6];
  esp32_ai_msg.ly = atoi(databuf);

  // 解析rx
  databuf[0] = buf[8];
  databuf[1] = buf[9];
  databuf[2] = buf[10];
  esp32_ai_msg.rx = atoi(databuf);

  // 解析ry
  databuf[0] = buf[12];
  databuf[1] = buf[13];
  databuf[2] = buf[14];
  esp32_ai_msg.ry = atoi(databuf);

  memset(buf, 0, 16);

  if((esp32_ai_msg.lx > esp32_ai_msg.rx) || (esp32_ai_msg.ly > esp32_ai_msg.ry)) // 当坐标非法
  {
    return;
  }

  // 中心点x,y
  esp32_ai_msg.cx = (esp32_ai_msg.rx - esp32_ai_msg.lx) / 2 + esp32_ai_msg.lx;
  esp32_ai_msg.cy = (esp32_ai_msg.ry - esp32_ai_msg.ly) / 2 + esp32_ai_msg.ly;

  // 面积缩10倍
  esp32_ai_msg.area = (esp32_ai_msg.rx - esp32_ai_msg.lx) / 10 * (esp32_ai_msg.ry - esp32_ai_msg.ly);
}

// 二维码协议
void recv_QR_data(char QRdata) // 协议基本是$二维码数据#
{
  if (QRdata == '$' && g_new_flag == 0)
  {
    g_new_flag = 1;
    memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    return;
  }
  
  if(g_new_flag == 1)
  {
    if (QRdata == '#')
    {
      g_new_flag = 0;
      g_index = 0;
      newlines = 1; // 新数据接收完毕
      memcpy(data_buff, recv_buf, sizeof(recv_buf));
      ESPWIFISerial.println(data_buff); 
      memcpy(QR_msg.QR_msg, data_buff, sizeof(QR_msg.QR_msg)); // 处理赋值到有效数据

      memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
      memset(data_buff, 0, sizeof(data_buff)); // 清除旧数据
    }
    else if (QRdata == '$') // 中途出现丢包
    {
      g_index = 0;
      g_new_flag = 0;
      memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    }
    else 
    {
      recv_buf[g_index++] = QRdata;
    }

    if(g_index > 50) // 数组溢出
    { 
      g_index = 0;
      g_new_flag = 0;
      memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    }
  }
}

// 人脸识别协议
void recv_face_data(char facedata) // 协议基本是$xxx,yyy,zzz,hhh,#@ID:1!\r\n
{
  if (facedata == '$' && g_new_flag == 0)
  {
    g_new_flag = 1;
    memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    return; 
  }
  
  if(g_new_flag == 1)
  {
    if (facedata == '!')
    {
      g_new_flag = 0;
      g_index = 0;
      memcpy(data_buff, recv_buf, sizeof(recv_buf));
      
      // 处理
      Get_faceAI_msg(data_buff);
      newlines = 1; // 新数据接收完毕
      memset(data_buff, 0, sizeof(data_buff)); // 清除旧数据
      memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    }
    else if (facedata == '$') // 中途出现丢包
    {
      g_index = 0;
      g_new_flag = 0;
      memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    }
    else 
    {
      if((facedata != '#') && (facedata != '@')) // 去掉#和@号，只要有效数据
        recv_buf[g_index++] = facedata;
    }
    
    if(g_index > 50) // 数组溢出
    { 
      g_index = 0;
      g_new_flag = 0;
      memset(recv_buf, 0, sizeof(recv_buf)); // 清除旧数据
    }
  }
}

// 获取人脸数据（简化版）
void Get_faceAI_msg(char *buf)
{
  char databuf[4] = {"\0"};
  
  // 简化验证，只检查基本格式
  if(strlen(buf) < 16) return;
  
  // 解析lx
  databuf[0] = buf[0];
  databuf[1] = buf[1];
  databuf[2] = buf[2];
  esp32_ai_msg.lx = atoi(databuf);

  // 解析ly
  databuf[0] = buf[4];
  databuf[1] = buf[5];
  databuf[2] = buf[6];
  esp32_ai_msg.ly = atoi(databuf);

  // 解析rx
  databuf[0] = buf[8];
  databuf[1] = buf[9];
  databuf[2] = buf[10];
  esp32_ai_msg.rx = atoi(databuf);

  // 解析ry
  databuf[0] = buf[12];
  databuf[1] = buf[13];
  databuf[2] = buf[14];
  esp32_ai_msg.ry = atoi(databuf);

  // 中心点x,y
  esp32_ai_msg.cx = (esp32_ai_msg.rx - esp32_ai_msg.lx) / 2 + esp32_ai_msg.lx;
  esp32_ai_msg.cy = (esp32_ai_msg.ry - esp32_ai_msg.ly) / 2 + esp32_ai_msg.ly;

  // 解析id（简化版）
  esp32_ai_msg.id = 1; // 默认ID为1，可根据需要修改
  
  // 输出调试信息
  ESPWIFISerial.print("检测到人脸 - 中心点: (");
  ESPWIFISerial.print(esp32_ai_msg.cx);
  ESPWIFISerial.print(", ");
  ESPWIFISerial.print(esp32_ai_msg.cy);
  ESPWIFISerial.println(")");
}

// GPS数据接收函数（用于接收来自主程序处理的GPS数据）
void recv_gps_data(char gpsdata)
{
  // 这个函数现在不需要了，因为GPS数据在AI_Camera.ino中直接处理并发送
  // 保留函数原型避免编译错误
  (void)gpsdata; // 避免未使用参数警告
}

// 处理GPS数据包（用于调试）
void process_gps_packet(char* buffer) {
  // 直接转发到电脑串口用于调试
  ESPWIFISerial.print("GPS:");
  ESPWIFISerial.println(buffer);
}