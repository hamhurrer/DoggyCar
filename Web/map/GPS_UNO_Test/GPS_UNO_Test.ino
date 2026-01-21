#include <SoftwareSerial.h>
#include <string.h>

// 串口定义
SoftwareSerial gpsSerial(10, 11);  // GPS: RX=10, TX=11

// 引脚定义
int LED_PIN = 13;           // 板载LED

// WiFi配置 - 修改这里！
const char WIFI_SSID[] PROGMEM = "NET";          // 你的WiFi名称
const char WIFI_PASS[] PROGMEM = "12345678";     // 你的WiFi密码
const char SERVER_IP[] PROGMEM = "192.168.207.34"; // 电脑IP地址
const int SERVER_PORT = 8080;                    // 电脑端口

// GPS数据结构
struct GPSData
{
  char GPS_Buffer[128];  // 增加缓冲区
  bool isGetData;
  bool isParseData;
  char UTCTime[12];
  char latitude[12];
  char N_S;
  char longitude[13];
  char E_W;
  char status;
  bool isUsefull;
  char jsonData[150];
} Save_Data;

// 缓冲区
const unsigned int gpsRxBufferLength = 256;
char gpsRxBuffer[gpsRxBufferLength];
unsigned int ii = 0;

// WiFi状态
#define WIFI_DISCONNECTED 0
#define WIFI_CONNECTING   1
#define WIFI_CONNECTED    2
#define WIFI_ERROR        3
byte wifiState = WIFI_DISCONNECTED;

// 时间控制
unsigned long lastWiFiCheck = 0;
unsigned long lastDataSend = 0;
unsigned long lastGpsTime = 0;
unsigned long lastATCommand = 0;
bool sendInProgress = false;
bool gpsHasFix = false;  // GPS是否有定位

// 辅助函数声明
void readFromPROGMEM(char* dest, const char* src, size_t len);
bool checkATResponse(const char* expected, unsigned int timeout);
void clearSerialBuffer();

void setup() {
  // 初始化串口
  Serial.begin(115200);
  
  Serial.println(F("\nGPS+WiFi数据发射器 - 改进版"));
  Serial.println(F("======================"));
  
  // 初始化GPS串口
  gpsSerial.begin(9600);
  Serial.println(F("GPS串口已初始化"));
  
  // 初始化LED引脚
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  
  // 初始化结构体
  memset(&Save_Data, 0, sizeof(Save_Data));
  Save_Data.isGetData = false;
  Save_Data.isParseData = false;
  Save_Data.isUsefull = false;
  
  // 显示配置信息
  printConfigInfo();
  
  // 先等待GPS获取数据（至少30秒）
  Serial.println(F("等待GPS获取定位数据..."));
  Serial.println(F("将GPS模块放在室外开阔处"));
  
  unsigned long gpsStartTime = millis();
  bool gpsInitialized = false;
  
  while (millis() - gpsStartTime < 30000) {
    gpsRead();
    
    if (Save_Data.isGetData) {
      parseGpsBuffer();
      Save_Data.isGetData = false;
      
      if (Save_Data.isUsefull) {
        Serial.println(F("GPS已获取有效定位！"));
        gpsHasFix = true;
        gpsInitialized = true;
        break;
      }
    }
    
    // 显示等待进度
    static unsigned long lastProgress = 0;
    if (millis() - lastProgress > 2000) {
      Serial.print(F("."));
      lastProgress = millis();
    }
  }
  
  if (!gpsInitialized) {
    Serial.println(F("\nGPS未能在30秒内获取定位，继续等待..."));
  }
  
  // 等待ESP-01S启动
  delay(2000);
  
  // 测试ESP-01S
  Serial.println(F("\n测试ESP-01S..."));
  clearSerialBuffer();
  delay(1000);
  
  if (testESP01()) {
    Serial.println(F("ESP测试成功，连接WiFi..."));
    wifiState = WIFI_CONNECTING;
    
    if (setupESP01()) {
      wifiState = WIFI_CONNECTED;
      Serial.println(F("WiFi连接成功!"));
      digitalWrite(LED_PIN, HIGH);
      delay(500);
      digitalWrite(LED_PIN, LOW);
    } else {
      Serial.println(F("WiFi连接失败"));
      wifiState = WIFI_ERROR;
      errorBlink(5);
    }
  } else {
    Serial.println(F("ESP无响应"));
    wifiState = WIFI_ERROR;
    errorBlink(3);
  }
  
  // 启动完成
  for (int i = 0; i < 2; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(300);
    digitalWrite(LED_PIN, LOW);
    delay(300);
  }
  
  lastGpsTime = millis();
}

void loop() {
  // 第一步：总是优先读取GPS数据
  gpsRead();
  
  if (Save_Data.isGetData) {
    parseGpsBuffer();
    Save_Data.isGetData = false;
  }
  
  // 第二步：只在非AT指令发送期间处理WiFi
  if (!sendInProgress && millis() - lastATCommand > 100) {
    handleWiFi();
  }
  
  // 第三步：处理数据发送
  if (Save_Data.isParseData && Save_Data.isUsefull && wifiState == WIFI_CONNECTED) {
    if (!sendInProgress && (millis() - lastDataSend > 5000)) {
      sendInProgress = true;
      lastATCommand = millis();
      handleDataSend();
      Save_Data.isParseData = false;
      Save_Data.isUsefull = false;
      sendInProgress = false;
      lastDataSend = millis();
    }
  }
  
  // 状态显示
  static unsigned long lastStatus = 0;
  if (millis() - lastStatus > 10000) {
    printSystemStatus();
    lastStatus = millis();
  }
  
  // GPS超时检查
  if (millis() - lastGpsTime > 10000) {
    static unsigned long lastTimeoutMsg = 0;
    if (millis() - lastTimeoutMsg > 5000) {
      Serial.println(F("GPS无数据"));
      lastTimeoutMsg = millis();
    }
  }
  
  // 处理WiFi响应（非阻塞方式）
  if (Serial.available()) {
    String response = Serial.readStringUntil('\n');
    response.trim();
    
    if (response.length() > 0) {
      if (response.indexOf("WIFI DISCONNECT") >= 0) {
        Serial.println(F("WiFi断开"));
        wifiState = WIFI_DISCONNECTED;
      } else if (response.indexOf("WIFI CONNECTED") >= 0) {
        Serial.println(F("WiFi连接"));
        wifiState = WIFI_CONNECTED;
      } else if (response.indexOf("WIFI GOT IP") >= 0) {
        Serial.println(F("WiFi已获取IP"));
        wifiState = WIFI_CONNECTED;
      }
    }
  }
  
  // 短延迟以避免CPU过载
  delay(1);
}

// ============================ WiFi处理函数 ============================
bool testESP01() {
  Serial.println(F("发送AT指令测试ESP..."));
  
  clearSerialBuffer();
  
  for (int i = 0; i < 3; i++) {
    Serial.println("AT");
    delay(500);
    
    if (checkATResponse("OK", 2000)) {
      Serial.println(F("ESP响应正常"));
      return true;
    }
    delay(500);
  }
  
  Serial.println(F("ESP无响应"));
  return false;
}

bool setupESP01() {
  Serial.println(F("配置ESP-01S连接WiFi..."));
  
  char ssid[32];
  char pass[32];
  readFromPROGMEM(ssid, WIFI_SSID, 31);
  readFromPROGMEM(pass, WIFI_PASS, 31);
  
  // 设置WiFi模式
  Serial.println("AT+CWMODE=1");
  if (!checkATResponse("OK", 3000)) {
    Serial.println(F("设置WiFi模式失败"));
    return false;
  }
  delay(200);
  
  // 连接WiFi
  Serial.print("AT+CWJAP=\"");
  Serial.print(ssid);
  Serial.print("\",\"");
  Serial.print(pass);
  Serial.println("\"");
  
  Serial.println(F("连接WiFi..."));
  
  unsigned long startTime = millis();
  bool connected = false;
  
  while (millis() - startTime < 30000) {
    if (Serial.available()) {
      String response = Serial.readStringUntil('\n');
      response.trim();
      
      if (response.indexOf("WIFI CONNECTED") >= 0) {
        Serial.println(F("WiFi连接成功"));
        connected = true;
      }
      if (response.indexOf("WIFI GOT IP") >= 0) {
        Serial.println(F("已获取IP"));
        connected = true;
      }
      if (response.indexOf("OK") >= 0 && connected) {
        break;
      }
      if (response.indexOf("FAIL") >= 0) {
        Serial.println(F("WiFi连接失败"));
        return false;
      }
    }
    
    // 在等待WiFi连接时，仍然处理GPS数据
    gpsRead();
    if (Save_Data.isGetData) {
      parseGpsBuffer();
      Save_Data.isGetData = false;
    }
    
    delay(50);
  }
  
  if (!connected) {
    Serial.println(F("WiFi连接超时"));
    return false;
  }
  
  delay(1000);
  
  // 设置单连接模式
  Serial.println("AT+CIPMUX=0");
  if (!checkATResponse("OK", 3000)) {
    Serial.println(F("设置连接模式失败"));
    return false;
  }
  
  Serial.println(F("ESP配置完成"));
  return true;
}

void handleWiFi() {
  if (wifiState != WIFI_CONNECTED && millis() - lastWiFiCheck > 30000) {
    Serial.println(F("尝试重新连接WiFi..."));
    
    if (setupESP01()) {
      wifiState = WIFI_CONNECTED;
      digitalWrite(LED_PIN, HIGH);
      delay(200);
      digitalWrite(LED_PIN, LOW);
      Serial.println(F("WiFi重连成功"));
    } else {
      wifiState = WIFI_ERROR;
      Serial.println(F("WiFi重连失败"));
    }
    
    lastWiFiCheck = millis();
  }
  
  // LED指示
  if (wifiState == WIFI_CONNECTED) {
    static unsigned long lastBlink = 0;
    static bool ledState = false;
    
    if (millis() - lastBlink > 1000) {
      ledState = !ledState;
      digitalWrite(LED_PIN, ledState ? HIGH : LOW);
      lastBlink = millis();
    }
  } else if (wifiState == WIFI_ERROR) {
    static unsigned long lastErrorBlink = 0;
    static bool errorLedState = false;
    
    if (millis() - lastErrorBlink > 200) {
      errorLedState = !errorLedState;
      digitalWrite(LED_PIN, errorLedState ? HIGH : LOW);
      lastErrorBlink = millis();
    }
  }
}

void handleDataSend() {
  if (wifiState != WIFI_CONNECTED) {
    Serial.println(F("WiFi未连接"));
    return;
  }
  
  formatGPSData();
  
  Serial.println(F("发送GPS数据..."));
  
  if (sendDataToServer()) {
    Serial.println(F("数据发送成功"));
    digitalWrite(LED_PIN, HIGH);
    delay(100);
    digitalWrite(LED_PIN, LOW);
  } else {
    Serial.println(F("数据发送失败"));
  }
}

void formatGPSData() {
  char latDir[2] = {Save_Data.N_S, '\0'};
  char lonDir[2] = {Save_Data.E_W, '\0'};
  char statusChar[2] = {Save_Data.status, '\0'};
  
  strcpy(Save_Data.jsonData, "{\"time\":\"");
  strcat(Save_Data.jsonData, Save_Data.UTCTime);
  strcat(Save_Data.jsonData, "\",\"lat\":\"");
  strcat(Save_Data.jsonData, Save_Data.latitude);
  strcat(Save_Data.jsonData, "\",\"lat_dir\":\"");
  strcat(Save_Data.jsonData, latDir);
  strcat(Save_Data.jsonData, "\",\"lon\":\"");
  strcat(Save_Data.jsonData, Save_Data.longitude);
  strcat(Save_Data.jsonData, "\",\"lon_dir\":\"");
  strcat(Save_Data.jsonData, lonDir);
  strcat(Save_Data.jsonData, "\",\"status\":\"");
  strcat(Save_Data.jsonData, statusChar);
  strcat(Save_Data.jsonData, "\"}");
  
  Serial.print(F("JSON: "));
  Serial.println(Save_Data.jsonData);
}

bool sendDataToServer() {
  char server[16];
  readFromPROGMEM(server, SERVER_IP, 15);
  
  Serial.print(F("连接服务器: "));
  Serial.print(server);
  Serial.print(F(":"));
  Serial.println(SERVER_PORT);
  
  // 建立TCP连接
  Serial.print("AT+CIPSTART=\"TCP\",\"");
  Serial.print(server);
  Serial.print("\",");
  Serial.println(SERVER_PORT);
  
  if (!checkATResponse("OK", 5000)) {
    if (!checkATResponse("ALREADY CONNECTED", 1000)) {
      Serial.println(F("服务器连接失败"));
      Serial.println("AT+CIPCLOSE");
      delay(100);
      return false;
    }
  }
  
  Serial.println(F("服务器连接成功"));
  delay(100);
  
  // 发送数据
  int dataLength = strlen(Save_Data.jsonData);
  Serial.print("AT+CIPSEND=");
  Serial.println(dataLength);
  
  if (!checkATResponse(">", 3000)) {
    Serial.println(F("发送准备失败"));
    Serial.println("AT+CIPCLOSE");
    delay(100);
    return false;
  }
  
  Serial.println(Save_Data.jsonData);
  
  if (checkATResponse("SEND OK", 5000)) {
    Serial.println(F("数据发送完成"));
    delay(100);
    return true;
  }
  
  Serial.println(F("数据发送超时"));
  Serial.println("AT+CIPCLOSE");
  delay(100);
  return false;
}

bool checkATResponse(const char* expected, unsigned int timeout) {
  unsigned long startTime = millis();
  String response = "";
  
  while (millis() - startTime < timeout) {
    // 在等待AT响应时，仍然处理GPS数据
    gpsRead();
    
    if (Serial.available()) {
      char c = Serial.read();
      response += c;
      
      if (response.indexOf(expected) >= 0) {
        delay(10);
        while (Serial.available()) {
          Serial.read();
        }
        return true;
      }
      
      if (response.indexOf("ERROR") >= 0 || response.indexOf("FAIL") >= 0) {
        Serial.print(F("AT错误: "));
        Serial.println(response);
        return false;
      }
    }
  }
  
  if (response.length() > 0) {
    Serial.print(F("AT响应超时: "));
    Serial.println(response);
  } else {
    Serial.println(F("AT无响应"));
  }
  
  return false;
}

void clearSerialBuffer() {
  while (Serial.available()) {
    Serial.read();
  }
}

// ============================ 系统辅助函数 ============================
void printConfigInfo() {
  Serial.println(F("\n配置信息:"));
  
  Serial.print(F("WiFi SSID: "));
  char ssid[32];
  readFromPROGMEM(ssid, WIFI_SSID, 31);
  Serial.println(ssid);
  
  Serial.print(F("服务器IP: "));
  char server[16];
  readFromPROGMEM(server, SERVER_IP, 15);
  Serial.println(server);
  
  Serial.print(F("服务器端口: "));
  Serial.println(SERVER_PORT);
  
  Serial.println(F("====================\n"));
}

void printSystemStatus() {
  Serial.println(F("\n系统状态:"));
  
  Serial.print(F("WiFi状态: "));
  switch(wifiState) {
    case WIFI_DISCONNECTED: Serial.println(F("未连接")); break;
    case WIFI_CONNECTING:   Serial.println(F("连接中")); break;
    case WIFI_CONNECTED:    Serial.println(F("已连接")); break;
    case WIFI_ERROR:        Serial.println(F("错误")); break;
  }
  
  Serial.print(F("GPS定位: "));
  if (gpsHasFix) {
    Serial.println(F("已获取"));
  } else {
    Serial.println(F("等待中"));
  }
  
  if (Save_Data.status == 'A') {
    Serial.print(F("位置: "));
    Serial.print(Save_Data.latitude);
    Serial.print(Save_Data.N_S);
    Serial.print(F(", "));
    Serial.print(Save_Data.longitude);
    Serial.println(Save_Data.E_W);
  } else {
    Serial.println(F("位置: 无效"));
  }
  
  Serial.print(F("上次发送: "));
  Serial.print((millis() - lastDataSend) / 1000);
  Serial.println(F("秒前"));
}

void errorBlink(int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(200);
    digitalWrite(LED_PIN, LOW);
    delay(200);
  }
}

void readFromPROGMEM(char* dest, const char* src, size_t len) {
  size_t i;
  for (i = 0; i < len; i++) {
    dest[i] = pgm_read_byte(src + i);
    if (dest[i] == '\0') break;
  }
  if (i == len) dest[len] = '\0';
}

// ============================ GPS处理函数 ============================
void parseGpsBuffer() {
  char tempBuffer[128];
  strcpy(tempBuffer, Save_Data.GPS_Buffer);
  
  char* tokens[20];
  int tokenCount = 0;
  
  char* token = strtok(tempBuffer, ",");
  while (token != NULL && tokenCount < 20) {
    tokens[tokenCount++] = token;
    token = strtok(NULL, ",");
  }
  
  if (tokenCount >= 7) {
    // UTC时间
    if (strlen(tokens[1]) > 0) {
      strncpy(Save_Data.UTCTime, tokens[1], 11);
      Save_Data.UTCTime[11] = '\0';
    }
    
    // 状态
    Save_Data.status = tokens[2][0];
    Save_Data.isUsefull = (Save_Data.status == 'A');
    if (Save_Data.isUsefull) {
      gpsHasFix = true;
    }
    
    // 纬度
    if (strlen(tokens[3]) > 0) {
      strncpy(Save_Data.latitude, tokens[3], 11);
      Save_Data.latitude[11] = '\0';
    }
    
    // 纬度方向
    if (strlen(tokens[4]) > 0) {
      Save_Data.N_S = tokens[4][0];
    }
    
    // 经度
    if (strlen(tokens[5]) > 0) {
      strncpy(Save_Data.longitude, tokens[5], 12);
      Save_Data.longitude[12] = '\0';
    }
    
    // 经度方向
    if (strlen(tokens[6]) > 0) {
      Save_Data.E_W = tokens[6][0];
    }
    
    Save_Data.isParseData = true;
    lastGpsTime = millis();
    
    Serial.print(F("GPS: "));
    Serial.print(Save_Data.UTCTime);
    Serial.print(F(" "));
    Serial.print(Save_Data.status);
    
    if (Save_Data.isUsefull) {
      Serial.print(F(" 有效 "));
      Serial.print(Save_Data.latitude);
      Serial.print(Save_Data.N_S);
      Serial.print(F(" "));
      Serial.print(Save_Data.longitude);
      Serial.println(Save_Data.E_W);
    } else {
      Serial.println(F(" 无效"));
    }
  }
}

void gpsRead() {
  while (gpsSerial.available()) {
    char c = gpsSerial.read();
    
    if (ii < gpsRxBufferLength - 1) {
      gpsRxBuffer[ii++] = c;
      gpsRxBuffer[ii] = '\0';
    }
    
    if (c == '\n') {
      lastGpsTime = millis();
      
      char* gprmc = strstr(gpsRxBuffer, "$GPRMC");
      if (gprmc == NULL) {
        gprmc = strstr(gpsRxBuffer, "$GNRMC");
      }
      if (gprmc == NULL) {
        gprmc = strstr(gpsRxBuffer, "$GPGGA");
      }
      if (gprmc == NULL) {
        gprmc = strstr(gpsRxBuffer, "$GNGGA");
      }
      
      if (gprmc != NULL) {
        char* lineEnd = strchr(gprmc, '\n');
        if (lineEnd == NULL) lineEnd = strchr(gprmc, '\r');
        if (lineEnd == NULL) lineEnd = gprmc + strlen(gprmc);
        
        int len = lineEnd - gprmc;
        if (len > 0 && len < 128) {
          strncpy(Save_Data.GPS_Buffer, gprmc, len);
          Save_Data.GPS_Buffer[len] = '\0';
          Save_Data.isGetData = true;
        }
      }
      
      ii = 0;
      memset(gpsRxBuffer, 0, gpsRxBufferLength);
      break;
    }
  }
}