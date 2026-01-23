# 🐕 四轮足森林守护机器犬 | Forest-Guard DoggyCar

**智能视觉与实时定位的森林生态监控系统**  
*AI Eyes, Faithful Guardian - Protecting Every Tree's Breath*

---

## 📋 项目概述

### 核心使命
本项目是一个集 **AI视觉识别**、**GPS实时定位**、**远程监控**于一体的智能化森林监控系统。系统通过部署在森林中的ESP32智能节点，实现对人、动物、异常事件的自动识别与位置追踪，为森林保护提供全天候、智能化的守护方案。

### 系统特点
- 🎯 **双重AI识别**：同时检测人脸与动物（支持猫/狗等扩展）
- 📍 **精准定位**：GPS实时定位，坐标转换，轨迹记录
- 🌲 **远程监控**：WiFi无线传输，支持多节点组网
- 🗺️ **智能可视化**：实时地图显示，轨迹分析，热力图生成
- 🔄 **自适应路径**：牛耕式智能巡逻，支持自定义区域覆盖

---

## 🏗️ 系统架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   摄像头模块     │    │   ESP32主控     │    │   GPS模块       │
│  - OV2640传感器  │◄──►│  - AI推理引擎   │◄──►│  - UART1通信    │
│  - RGB565 QVGA   │    │  - WiFi AP      │    │  - NMEA解析     │
│  - 图像采集      │    │  - HTTP服务器   │    │  - 坐标转换     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────┐
│                PC端监控平台 (map.py)                  │
│  - PyQt5 GUI界面     - Folium地图可视化              │
│  - 实时视频流显示    - 轨迹分析与存储                │
│  - 智能路径规划      - 异常事件告警                  │
└─────────────────────────────────────────────────────┘
```

---

## ✨ 核心功能

### 1. AI智能识别
- **人脸检测**：实时识别并标记（红色边框）
- **动物检测**：猫脸识别（绿色边框），可扩展至其他动物
- **事件记录**：自动记录检测时间戳和地理位置

### 2. 实时定位与追踪
- **GPS数据采集**：每秒更新定位信息
- **坐标转换**：WGS-84 → GCJ-02（高德地图坐标系）
- **轨迹记录**：自动保存至本地文件，支持历史回放


### 3. 可视化监控平台
- **实时视频流**：带AI识别框的MJPEG流
- **交互式地图**：Folium地图，支持缩放、测量、标记
- **数据管理**：GPS数据导入/导出，截图保存
- **状态监控**：系统状态实时显示，异常告警

---

## 🛠️ 技术栈

### 硬件平台
- **主控制器**：ESP32-S3（双核240MHz，8MB PSRAM）
- **摄像头**：OV2640（200万像素，RGB565输出）
- **GPS模块**：支持NMEA协议的GPS/北斗双模模块
- **供电**：锂电池+太阳能板（可选）

### 软件框架
| 模块 | 技术栈 | 说明 |
|------|--------|------|
| **固件层** | ESP-IDF v5.1.2, FreeRTOS | 乐鑫官方物联网开发框架 |
| **AI推理** | TensorFlow Lite Micro | 轻量级AI推理框架 |
| **通信协议** | HTTP/MJPEG, WebSocket | 网络数据传输 |
| **PC端应用** | Python 3.9+, PyQt5, Folium | 跨平台桌面应用 |
| **地图服务** | 高德地图瓦片 | GCJ-02坐标系支持 |
| **开发工具** | VS Code, Git, ESP-IDF插件 | 一体化开发环境 |

---




### 4. 系统连接
1. 手机/电脑连接ESP32热点：`Yahboom_AP`
2. 浏览器访问：http://192.168.4.1 或使用PC端软件
3. 在PC软件中配置ESP32 IP地址，开始监控

---

## 📊 系统配置

### 网络配置
```yaml
# config/default.yaml
esp32:
  ap_ssid: "Forest_Guardian_AP"
  ap_password: "secure_password"
  ip_address: "192.168.4.1"
  http_port: 80
  stream_port: 81

gps:
  update_interval: 1.0  # 秒
  coordinate_system: "gcj02"  # wgs84/gcj02/bd09
  
map:
  tile_provider: "amap"  # 高德地图
  default_zoom: 16
  max_zoom: 20
```

### AI模型配置
```python
# 检测阈值调整
human_detector = HumanFaceDetectMSR01(
    score_threshold=0.3,
    nms_threshold=0.3
)

cat_detector = CatFaceDetectMN03(
    score_threshold=0.4,
    nms_threshold=0.3
)
```

---

---

## 🎯 应用场景

### 1. 森林防火监控
- 早期火源识别
- 非法进入人员检测
- 火势蔓延轨迹预测

### 2. 野生动物研究
- 动物活动轨迹追踪
- 种群数量统计
- 行为模式分析

### 3. 生态保护区管理
- 游客活动监控
- 非法砍伐检测
- 生态环境评估

### 4. 智慧农业
- 农作物生长监测
- 病虫害早期预警
- 灌溉区域规划

---


## 🙏 致谢

### 技术支持
- [乐鑫科技](https://www.espressif.com/) - ESP32芯片与开发框架
- [高德地图](https://lbs.amap.com/) - 地图瓦片服务

### 开源项目
- [esp32-camera](https://github.com/espressif/esp32-camera) - 摄像头驱动
- [Folium](https://python-visualization.github.io/folium/) - Python地图可视化
- [PyQt5](https://www.riverbankcomputing.com/software/pyqt/) - GUI框架

---


**四轮足森林守护机器狗** - 用科技守护每一片绿色，让AI成为森林最忠诚的卫士 🐕🌲👁️
