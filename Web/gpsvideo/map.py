# map.py - 集成视频流和实时GPS数据显示
import sys
import os
import re
import math
import folium
import numpy as np
import webbrowser
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QTextEdit, QProgressBar, QGroupBox, QCheckBox,
    QSplitter, QTabWidget, QFrame, QGridLayout, QLineEdit,
    QComboBox, QListWidget, QListWidgetItem, QDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer, QSize, QMutex, QMutexLocker
from PyQt5.QtGui import QPixmap, QFont, QIcon, QImage, QPainter, QColor
from PyQt5.QtWebEngineWidgets import QWebEngineView
from datetime import datetime
import tempfile
import json
import requests
import threading
import time
from io import BytesIO
from PIL import Image
import base64
import cv2

# 导入folium插件
from folium import plugins

# GPS坐标转换类（从GPS_MAP.py中整合）
class GPSCoordinateConverter:
    """GPS坐标转换类，处理WGS-84到GCJ-02的转换"""
    def __init__(self):
        self.PI = 3.1415926535897932384626
        self.A = 6378245.0
        self.EE = 0.00669342162296594323
    
    def str_To_Gps84(self, in_data1, in_data2):
        """
        将北斗/GPS原始字符串转换为WGS-84坐标
        参考文档中的转换方法：度分格式转换为十进制度
        """
        len_data1 = len(in_data1)
        str_data2 = "%05d" % int(in_data2)
        temp_data = int(in_data1)
        symbol = 1
        if temp_data < 0:
            symbol = -1
        degree = int(temp_data / 100.0)
        str_decimal = str(in_data1[len_data1-2]) + str(in_data1[len_data1-1]) + '.' + str(str_data2)
        f_degree = float(str_decimal)/60.0
        if symbol > 0:
            result = degree + f_degree
        else:
            result = degree - f_degree
        return result
    
    def wgs84_to_gcj02(self, lat, lon):
        """
        WGS-84坐标系转换为GCJ-02坐标系（火星坐标系）
        用于高德地图
        """
        if self.out_of_china(lat, lon):
            return [lat, lon]
        
        dLat = self.transform_lat(lon - 105.0, lat - 35.0)
        dLon = self.transform_lon(lon - 105.0, lat - 35.0)
        radLat = lat / 180.0 * self.PI
        magic = math.sin(radLat)
        magic = 1 - self.EE * magic * magic
        sqrtMagic = math.sqrt(magic)
        
        dLat = (dLat * 180.0) / ((self.A * (1 - self.EE)) / (magic * sqrtMagic) * self.PI)
        dLon = (dLon * 180.0) / (self.A / sqrtMagic * math.cos(radLat) * self.PI)
        
        mgLat = lat + dLat
        mgLon = lon + dLon
        
        return [mgLat, mgLon]
    
    def gcj02_to_bd09(self, gg_lat, gg_lon):
        """
        GCJ-02坐标系转换为BD-09坐标系
        用于百度地图
        """
        x = gg_lon
        y = gg_lat
        z = math.sqrt(x * x + y * y) + 0.00002 * math.sin(y * self.PI)
        theta = math.atan2(y, x) + 0.000003 * math.cos(x * self.PI)
        bd_lon = z * math.cos(theta) + 0.0065
        bd_lat = z * math.sin(theta) + 0.006
        return [bd_lat, bd_lon]
    
    def out_of_china(self, lat, lon):
        """判断是否在中国境内"""
        if lon < 72.004 or lon > 137.8347:
            return True
        if lat < 0.8293 or lat > 55.8271:
            return True
        return False
    
    def transform_lat(self, x, y):
        """纬度转换辅助函数"""
        ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * self.PI) + 20.0 * math.sin(2.0 * x * self.PI)) * 2.0 / 3.0
        ret += (20.0 * math.sin(y * self.PI) + 40.0 * math.sin(y / 3.0 * self.PI)) * 2.0 / 3.0
        ret += (160.0 * math.sin(y / 12.0 * self.PI) + 320 * math.sin(y * self.PI / 30.0)) * 2.0 / 3.0
        return ret
    
    def transform_lon(self, x, y):
        """经度转换辅助函数"""
        ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * self.PI) + 20.0 * math.sin(2.0 * x * self.PI)) * 2.0 / 3.0
        ret += (20.0 * math.sin(x * self.PI) + 40.0 * math.sin(x / 3.0 * self.PI)) * 2.0 / 3.0
        ret += (150.0 * math.sin(x / 12.0 * self.PI) + 300.0 * math.sin(x / 30.0 * self.PI)) * 2.0 / 3.0
        return ret
    
    def raw_to_gcj02(self, lat_str, lat_str2, lon_str, lon_str2):
        """
        北斗原始字符串直接转换为GCJ-02坐标系
        两步转换：str_To_Gps84 → wgs84_to_gcj02
        """
        # 第一步：原始字符串转WGS-84
        lat_84 = self.str_To_Gps84(lat_str, lat_str2)
        lon_84 = self.str_To_Gps84(lon_str, lon_str2)
        
        # 第二步：WGS-84转GCJ-02
        gcj_coords = self.wgs84_to_gcj02(lat_84, lon_84)
        return gcj_coords
    
    def convert_coordinates(self, positions, conversion_mode="auto_detect"):
        """
        批量转换坐标
        conversion_mode: "auto_detect", "wgs84_to_gcj02", "raw_to_gcj02", "txt_to_gcj02"
        """
        converted_positions = []
        
        if conversion_mode == "wgs84_to_gcj02":
            # 直接WGS-84转GCJ-02
            for lon, lat in positions:
                gcj_coords = self.wgs84_to_gcj02(lat, lon)
                # folium需要[lon, lat]格式
                converted_positions.append([gcj_coords[1], gcj_coords[0]])
                
        elif conversion_mode == "raw_to_gcj02":
            # 原始数据转GCJ-02
            # positions应该是包含原始字符串的字典列表
            for pos in positions:
                if isinstance(pos, dict) and 'lat_str' in pos and 'lon_str' in pos:
                    lat_str = pos['lat_str']
                    lat_str2 = pos.get('lat_str2', "0")
                    lon_str = pos['lon_str']
                    lon_str2 = pos.get('lon_str2', "0")
                    
                    gcj_coords = self.raw_to_gcj02(lat_str, lat_str2, lon_str, lon_str2)
                    converted_positions.append([gcj_coords[1], gcj_coords[0]])
                    
        elif conversion_mode == "txt_to_gcj02":
            # 已解析的经纬度数据转GCJ-02
            for lon, lat in positions:
                gcj_coords = self.wgs84_to_gcj02(lat, lon)
                converted_positions.append([gcj_coords[1], gcj_coords[0]])
        else:
            # 自动检测：假设positions已经是WGS-84格式
            for lon, lat in positions:
                gcj_coords = self.wgs84_to_gcj02(lat, lon)
                converted_positions.append([gcj_coords[1], gcj_coords[0]])
                
        return converted_positions

class GPSProcessingThread(QThread):
    """GPS处理线程"""
    processing_started = pyqtSignal()
    processing_finished = pyqtSignal(object, object, object, object)
    error_occurred = pyqtSignal(str)
    progress_updated = pyqtSignal(int)
    
    def __init__(self, file_path, conversion_mode="wgs84_to_gcj02"):
        super().__init__()
        self.file_path = file_path
        self.conversion_mode = conversion_mode
        self.converter = GPSCoordinateConverter()
    
    def run(self):
        try:
            self.processing_started.emit()
            
            # 根据转换模式选择不同的解析方法
            if self.conversion_mode == "raw_to_gcj02":
                # 处理原始字符串数据
                raw_positions, gps_data = self.parse_raw_gps_data(self.file_path)
                self.progress_updated.emit(30)
                
                if raw_positions:
                    self.progress_updated.emit(50)
                    # 批量转换原始数据到GCJ-02
                    gcj02_positions = self.converter.convert_coordinates(raw_positions, "raw_to_gcj02")
                    positions = gcj02_positions
                    coordinate_system = "GCJ-02 (从原始数据直接转换)"
                    wgs84_positions = []  # 原始数据模式没有WGS-84中间数据
                    
                    self.progress_updated.emit(70)
                    
                    # 创建Folium地图
                    map_html, info = create_folium_map_with_track(positions, gps_data, coordinate_system)
                    self.progress_updated.emit(100)
                    self.processing_finished.emit(map_html, positions, info, wgs84_positions)
                else:
                    self.error_occurred.emit("未找到有效的原始GPS数据")
                    
            elif self.conversion_mode == "txt_to_gcj02":
                # 处理已解析的.txt文件数据（时间,纬度,经度格式）
                wgs84_positions, gps_data = self.parse_txt_gps_data(self.file_path)
                self.progress_updated.emit(30)
                
                if wgs84_positions:
                    self.progress_updated.emit(50)
                    # 转换为GCJ-02坐标系
                    gcj02_positions = self.converter.convert_coordinates(wgs84_positions, "txt_to_gcj02")
                    positions = gcj02_positions
                    coordinate_system = "GCJ-02 (从已解析的.txt文件转换)"
                    
                    self.progress_updated.emit(70)
                    
                    # 创建Folium地图
                    map_html, info = create_folium_map_with_track(positions, gps_data, coordinate_system)
                    self.progress_updated.emit(100)
                    self.processing_finished.emit(map_html, positions, info, wgs84_positions)
                else:
                    self.error_occurred.emit("未找到有效的.txt格式GPS数据")
                    
            elif self.conversion_mode == "no_conversion":
                # 处理标准GPS数据，不进行转换
                wgs84_positions, gps_data = parse_gps_data_from_file(self.file_path)
                self.progress_updated.emit(30)
                
                if wgs84_positions:
                    positions = wgs84_positions
                    coordinate_system = "WGS-84 (原始坐标系)"
                    
                    self.progress_updated.emit(70)
                    
                    # 创建Folium地图
                    map_html, info = create_folium_map_with_track(positions, gps_data, coordinate_system)
                    self.progress_updated.emit(100)
                    self.processing_finished.emit(map_html, positions, info, wgs84_positions)
                else:
                    self.error_occurred.emit("未找到有效的GPS数据")
                    
            else:
                # 默认处理标准GPS数据（WGS-84转GCJ-02）
                wgs84_positions, gps_data = parse_gps_data_from_file(self.file_path)
                self.progress_updated.emit(30)
                
                if wgs84_positions:
                    self.progress_updated.emit(50)
                    # 转换为GCJ-02坐标系
                    gcj02_positions = self.converter.convert_coordinates(wgs84_positions, "wgs84_to_gcj02")
                    positions = gcj02_positions
                    coordinate_system = "GCJ-02 (从WGS-84转换)"
                    
                    self.progress_updated.emit(70)
                    
                    # 创建Folium地图
                    map_html, info = create_folium_map_with_track(positions, gps_data, coordinate_system)
                    self.progress_updated.emit(100)
                    self.processing_finished.emit(map_html, positions, info, wgs84_positions)
                else:
                    self.error_occurred.emit("未找到有效的GPS数据")
                    
        except Exception as e:
            self.error_occurred.emit(str(e))
    
    def parse_raw_gps_data(self, file_path):
        """
        解析原始GPS数据文件，提取原始字符串
        格式示例: 纬度: 2429.53531, 经度: 11810.78036
        """
        raw_positions = []
        gps_data = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            print(f"原始数据文件行数: {len(lines)}")
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                
                # 尝试匹配原始数据格式
                # 格式1: 纬度: 2429.53531, 经度: 11810.78036
                # 格式2: 2429.53531,11810.78036
                # 格式3: LAT:2429.53531 LON:11810.78036
                
                # 提取纬度字符串
                lat_match = re.search(r'(\d{4,5})\.(\d{5})', line)
                lon_match = re.search(r'(\d{5,6})\.(\d{5})', line)
                
                if lat_match and lon_match:
                    lat_str = lat_match.group(1)  # 2429
                    lat_str2 = lat_match.group(2)  # 53531
                    lon_str = lon_match.group(1)  # 11810
                    lon_str2 = lon_match.group(2)  # 78036
                    
                    try:
                        # 记录原始数据
                        raw_data = {
                            'lat_str': lat_str,
                            'lat_str2': lat_str2,
                            'lon_str': lon_str,
                            'lon_str2': lon_str2,
                            'raw_line': line[:100]
                        }
                        
                        # 转换为WGS-84用于验证
                        lat_84 = self.converter.str_To_Gps84(lat_str, lat_str2)
                        lon_84 = self.converter.str_To_Gps84(lon_str, lon_str2)
                        
                        # 基本验证（中国范围）
                        if 18 <= lat_84 <= 54 and 73 <= lon_84 <= 136:
                            raw_positions.append(raw_data)
                            
                            # 同时记录转换后的数据用于显示
                            gcj_coords = self.converter.raw_to_gcj02(lat_str, lat_str2, lon_str, lon_str2)
                            pos_data = {
                                'time': datetime.now().strftime("%H:%M:%S"),
                                'latitude': gcj_coords[0],
                                'longitude': gcj_coords[1],
                                'raw_lat_str': f"{lat_str}.{lat_str2}",
                                'raw_lon_str': f"{lon_str}.{lon_str2}",
                                'wgs84_lat': lat_84,
                                'wgs84_lon': lon_84,
                                'type': 'RAW',
                                'raw': line[:100]
                            }
                            gps_data.append(pos_data)
                            
                    except (ValueError, IndexError) as e:
                        print(f"解析原始数据错误 (第{line_num}行): {e}")
                        continue
            
            print(f"原始数据解析完成: 找到 {len(raw_positions)} 个有效点")
            
        except Exception as e:
            print(f"解析原始文件错误: {e}")
            import traceback
            traceback.print_exc()
        
        return raw_positions, gps_data
    
    def parse_txt_gps_data(self, file_path):
        """
        解析已解析的.txt文件数据
        格式: 时间, 纬度, 经度, ...
        示例: 2026-01-20 12:02:02, 39.95903950, 116.35138717, 73.3, 1.9, 290.6, 13
        """
        positions = []
        gps_data = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            print(f".txt文件行数: {len(lines)}")
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                
                # 分割数据行
                parts = line.split(',')
                if len(parts) < 3:
                    print(f"行 {line_num} 数据不足: {line}")
                    continue
                
                try:
                    # 解析时间
                    time_str = parts[0].strip()
                    
                    # 解析纬度
                    lat_str = parts[1].strip()
                    latitude = float(lat_str)
                    
                    # 解析经度
                    lon_str = parts[2].strip()
                    longitude = float(lon_str)
                    
                    # 基本验证
                    if latitude == 0 or longitude == 0:
                        print(f"行 {line_num} 无效坐标: {latitude}, {longitude}")
                        continue
                    
                    # 中国范围验证
                    if not (18 <= latitude <= 54 and 73 <= longitude <= 136):
                        print(f"行 {line_num} 坐标超出中国范围: {latitude}, {longitude}")
                        continue
                    
                    # 如果有其他数据，解析它们
                    altitude = 0.0
                    speed = 0.0
                    course = 0.0
                    satellites = 0
                    
                    if len(parts) > 3:
                        try:
                            altitude = float(parts[3].strip())
                        except:
                            pass
                    
                    if len(parts) > 4:
                        try:
                            speed = float(parts[4].strip())
                        except:
                            pass
                    
                    if len(parts) > 5:
                        try:
                            course = float(parts[5].strip())
                        except:
                            pass
                    
                    if len(parts) > 6:
                        try:
                            satellites = int(float(parts[6].strip()))
                        except:
                            pass
                    
                    # 创建位置数据
                    pos_data = {
                        'time': time_str,
                        'latitude': latitude,
                        'longitude': longitude,
                        'altitude': altitude,
                        'speed': speed,
                        'course': course,
                        'satellites': satellites,
                        'type': 'TXT',
                        'raw': line[:100]
                    }
                    
                    # folium需要[lon, lat]格式
                    positions.append([longitude, latitude])
                    gps_data.append(pos_data)
                    
                    print(f"行 {line_num} 解析成功: {latitude:.6f}, {longitude:.6f}")
                    
                except (ValueError, IndexError) as e:
                    print(f"解析.txt数据错误 (第{line_num}行): {e}")
                    continue
            
            print(f".txt数据解析完成: 找到 {len(positions)} 个有效点")
            
        except Exception as e:
            print(f"解析.txt文件错误: {e}")
            import traceback
            traceback.print_exc()
        
        return positions, gps_data

class GPSDataSaver(QThread):
    """GPS数据保存线程"""
    data_saved = pyqtSignal(str, bool)  # 文件名, 是否成功
    status_updated = pyqtSignal(str)
    
    def __init__(self, gps_json_url, save_interval=1.0):  # 修改：从5.0改为1.0秒
        super().__init__()
        self.gps_json_url = gps_json_url
        self.save_interval = save_interval
        self.is_running = False
        self.save_directory = "gps_data"
        self.current_file = None
        self._mutex = QMutex()
        
        # 创建保存目录
        if not os.path.exists(self.save_directory):
            os.makedirs(self.save_directory)
    
    def run(self):
        self.is_running = True
        self.status_updated.emit("GPS数据保存已启动")
        
        # 记录保存点数的计数器
        save_count = 0
        
        while self.is_running:
            try:
                # 获取GPS JSON数据
                response = requests.get(self.gps_json_url, timeout=1.5)  # 减少超时时间
                if response.status_code == 200:
                    gps_data = response.json()
                    
                    if gps_data.get('valid', False):
                        # 打开或创建文件
                        if self.current_file is None:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            self.current_file = os.path.join(self.save_directory, f"gps_data_{timestamp}.txt")
                            self.status_updated.emit(f"创建新数据文件: {os.path.basename(self.current_file)}")
                        
                        # 保存数据（保存为.txt格式，便于后续解析）
                        with open(self.current_file, 'a', encoding='utf-8') as f:
                            time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 增加毫秒级精度
                            data_line = f"{time_str}, {gps_data.get('lat', 0):.8f}, {gps_data.get('lon', 0):.8f}, "
                            data_line += f"{gps_data.get('altitude', 0):.1f}, {gps_data.get('speed_knots', 0):.1f}, "
                            data_line += f"{gps_data.get('course', 0):.1f}, {gps_data.get('satellites', 0)}\n"
                            f.write(data_line)
                        
                        save_count += 1
                        if save_count % 10 == 0:  # 每10个点输出一次状态
                            self.status_updated.emit(f"已保存 {save_count} 个GPS数据点")
                        
                        self.data_saved.emit(self.current_file, True)
                    else:
                        self.status_updated.emit("GPS数据无效，等待有效数据...")
                
                time.sleep(self.save_interval)
                
            except requests.exceptions.Timeout:
                # 超时时不记录为错误，继续尝试
                pass
            except Exception as e:
                if self.is_running:  # 只在运行状态下记录错误
                    self.status_updated.emit(f"保存GPS数据错误: {str(e)}")
                time.sleep(self.save_interval)
    
    def stop(self):
        with QMutexLocker(self._mutex):
            self.is_running = False
        self.status_updated.emit("GPS数据保存已停止")
    
    def get_saved_files(self):
        """获取所有保存的GPS数据文件"""
        if os.path.exists(self.save_directory):
            files = [f for f in os.listdir(self.save_directory) if f.endswith('.txt')]
            files.sort(reverse=True)  # 按时间倒序排列
            return [os.path.join(self.save_directory, f) for f in files]
        return []
    
    def read_file_content(self, file_path):
        """读取文件内容"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"读取文件错误: {str(e)}"

def parse_gps_data_from_file(file_path):
    """
    解析GPS数据文件，支持多种NMEA格式
    参考文档中的解析方法
    """
    positions = []
    gps_data = []
    converter = GPSCoordinateConverter()
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        print(f"文件行数: {len(lines)}")
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line.startswith('$'):
                continue
            
            # 解析GNRMC/GPRMC数据
            if ('GNRMC' in line or 'GPRMC' in line):
                try:
                    parts = line.split(',')
                    if len(parts) < 7:
                        continue
                    
                    if parts[2] != 'A':  # 状态无效则跳过
                        continue
                    
                    # 解析时间
                    time_str = parts[1]
                    if len(time_str) >= 6:
                        hour = time_str[:2]
                        minute = time_str[2:4]
                        second = time_str[4:6]
                        time_display = f"{hour}:{minute}:{second}"
                    else:
                        time_display = time_str
                    
                    # 解析日期
                    date_str = parts[9] if len(parts) > 9 else ""
                    if len(date_str) == 6:
                        day = date_str[:2]
                        month = date_str[2:4]
                        year = date_str[4:6]
                        date_display = f"20{year}-{month}-{day}"
                    else:
                        date_display = ""
                    
                    # 解析纬度 (DDMM.MMMM格式)
                    lat_str = parts[3]
                    lat_dir = parts[4]
                    if lat_str and len(lat_str) >= 4:
                        try:
                            # 使用转换器将度分格式转换为十进制度
                            latitude = converter.str_To_Gps84(lat_str, "0")
                            if lat_dir == 'S':
                                latitude = -latitude
                        except ValueError:
                            # 备用解析方法
                            try:
                                lat_deg = float(lat_str[:2])
                                lat_min = float(lat_str[2:])
                                latitude = lat_deg + lat_min / 60.0
                                if lat_dir == 'S':
                                    latitude = -latitude
                            except:
                                continue
                    else:
                        continue
                    
                    # 解析经度 (DDDMM.MMMM格式)
                    lon_str = parts[5]
                    lon_dir = parts[6]
                    if lon_str and len(lon_str) >= 5:
                        try:
                            # 使用转换器将度分格式转换为十进制度
                            longitude = converter.str_To_Gps84(lon_str, "0")
                            if lon_dir == 'W':
                                longitude = -longitude
                        except ValueError:
                            # 备用解析方法
                            try:
                                lon_deg = float(lon_str[:3])
                                lon_min = float(lon_str[3:])
                                longitude = lon_deg + lon_min / 60.0
                                if lon_dir == 'W':
                                    longitude = -longitude
                            except:
                                continue
                    else:
                        continue
                    
                    # 速度（节转换为米/秒）
                    try:
                        speed_knots = float(parts[7]) if parts[7] else 0.0
                        speed_mps = speed_knots * 0.51444
                    except:
                        speed_knots = 0.0
                        speed_mps = 0.0
                    
                    # 方位角
                    try:
                        course = float(parts[8]) if parts[8] else 0.0
                    except:
                        course = 0.0
                    
                    # 基本验证（中国范围）
                    if not (18 <= latitude <= 54 and 73 <= longitude <= 136):
                        print(f"坐标超出中国范围: {latitude}, {longitude}")
                        continue
                    
                    pos_data = {
                        'time': time_display,
                        'date': date_display,
                        'latitude': latitude,
                        'longitude': longitude,
                        'speed_knots': speed_knots,
                        'speed_mps': speed_mps,
                        'course': course,
                        'type': 'RMC',
                        'raw': line[:100]  # 只保存前100个字符
                    }
                    
                    positions.append([longitude, latitude])  # folium需要[lon, lat]格式
                    gps_data.append(pos_data)
                    
                except (ValueError, IndexError) as e:
                    print(f"解析RMC数据错误 (第{line_num}行): {e}")
                    continue
            
            # 解析GNGGA/GPGGA数据
            elif ('GNGGA' in line or 'GPGGA' in line):
                try:
                    parts = line.split(',')
                    if len(parts) < 10:
                        continue
                    
                    if parts[6] == '0':  # 定位质量无效
                        continue
                    
                    # 解析时间
                    time_str = parts[1]
                    if len(time_str) >= 6:
                        hour = time_str[:2]
                        minute = time_str[2:4]
                        second = time_str[4:6]
                        time_display = f"{hour}:{minute}:{second}"
                    else:
                        time_display = time_str
                    
                    # 解析纬度
                    lat_str = parts[2]
                    lat_dir = parts[3]
                    if lat_str and len(lat_str) >= 4:
                        try:
                            # 使用转换器将度分格式转换为十进制度
                            latitude = converter.str_To_Gps84(lat_str, "0")
                            if lat_dir == 'S':
                                latitude = -latitude
                        except ValueError:
                            # 备用解析方法
                            try:
                                lat_deg = float(lat_str[:2])
                                lat_min = float(lat_str[2:])
                                latitude = lat_deg + lat_min / 60.0
                                if lat_dir == 'S':
                                    latitude = -latitude
                            except:
                                continue
                    else:
                        continue
                    
                    # 解析经度
                    lon_str = parts[4]
                    lon_dir = parts[5]
                    if lon_str and len(lon_str) >= 5:
                        try:
                            # 使用转换器将度分格式转换为十进制度
                            longitude = converter.str_To_Gps84(lon_str, "0")
                            if lon_dir == 'W':
                                longitude = -longitude
                        except ValueError:
                            # 备用解析方法
                            try:
                                lon_deg = float(lon_str[:3])
                                lon_min = float(lon_str[3:])
                                longitude = lon_deg + lon_min / 60.0
                                if lon_dir == 'W':
                                    longitude = -longitude
                            except:
                                continue
                    else:
                        continue
                    
                    # 基本验证
                    if not (18 <= latitude <= 54 and 73 <= longitude <= 136):
                        print(f"坐标超出中国范围: {latitude}, {longitude}")
                        continue
                    
                    # 卫星数量和HDOP
                    try:
                        satellites = int(parts[7]) if parts[7] else 0
                    except:
                        satellites = 0
                    
                    try:
                        hdop = float(parts[8]) if parts[8] else 0.0
                    except:
                        hdop = 0.0
                    
                    # 海拔高度
                    try:
                        altitude = float(parts[9]) if parts[9] else 0.0
                    except:
                        altitude = 0.0
                    
                    pos_data = {
                        'time': time_display,
                        'latitude': latitude,
                        'longitude': longitude,
                        'satellites': satellites,
                        'hdop': hdop,
                        'altitude': altitude,
                        'type': 'GGA',
                        'raw': line[:100]
                    }
                    
                    positions.append([longitude, latitude])
                    gps_data.append(pos_data)
                    
                except (ValueError, IndexError) as e:
                    print(f"解析GGA数据错误 (第{line_num}行): {e}")
                    continue
        
        print(f"解析完成: 找到 {len(positions)} 个有效GPS点")
        
        # 如果没有解析到有效数据，尝试使用其他方法
        if not positions:
            print("尝试备用解析方法...")
            positions, gps_data = alternative_parse_method(file_path)
            
    except Exception as e:
        print(f"解析文件错误: {e}")
        import traceback
        traceback.print_exc()
    
    return positions, gps_data

def alternative_parse_method(file_path):
    """
    备用解析方法，参考文档中的方法
    """
    positions = []
    gps_data = []
    converter = GPSCoordinateConverter()
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # 查找所有GPS数据行
        gps_lines = re.findall(r'\$G[N|P][A-Z]{3},[^\r\n]*', content)
        
        print(f"备用方法找到 {len(gps_lines)} 行GPS数据")
        
        for line in gps_lines:
            line = line.strip()
            if 'GNRMC' in line or 'GPRMC' in line:
                # 使用参考资料中的简单解析方法
                parts = line.split(',')
                if len(parts) >= 7 and parts[2] == 'A':
                    try:
                        # 解析纬度 (DDMM.MMMM格式)
                        lat_str = parts[3]
                        lat_dir = parts[4]
                        if lat_str and len(lat_str) >= 4:
                            latitude = converter.str_To_Gps84(lat_str, "0")
                            if lat_dir == 'S':
                                latitude = -latitude
                        else:
                            continue
                        
                        # 解析经度 (DDDMM.MMMM格式)
                        lon_str = parts[5]
                        lon_dir = parts[6]
                        if lon_str and len(lon_str) >= 5:
                            longitude = converter.str_To_Gps84(lon_str, "0")
                            if lon_dir == 'W':
                                longitude = -longitude
                        else:
                            continue
                        
                        # 基本验证
                        if latitude == 0 or longitude == 0:
                            continue
                            
                        if 18 <= latitude <= 54 and 73 <= longitude <= 136:  # 中国大致范围
                            positions.append([longitude, latitude])
                            gps_data.append({
                                'latitude': latitude,
                                'longitude': longitude,
                                'time': parts[1][:6] if len(parts[1]) >= 6 else parts[1],
                                'type': 'RMC',
                                'raw': line[:100]
                            })
                            
                    except (ValueError, IndexError) as e:
                        continue
                        
    except Exception as e:
        print(f"备用解析方法错误: {e}")
    
    return positions, gps_data

def create_folium_map_with_track(positions, gps_data, coordinate_system="GCJ-02 (高德地图坐标系)"):
    """
    使用Folium创建带有轨迹的地图（仅使用高德地图）
    参考文档中的Folium使用方法
    """
    if not positions:
        return None, {"error": "没有有效的GPS数据"}
    
    try:
        # 计算中心点
        lats = [pos[1] for pos in positions]  # 纬度
        lons = [pos[0] for pos in positions]  # 经度
        
        center_lat = sum(lats) / len(lats)
        center_lon = sum(lons) / len(lons)
        
        print(f"中心点: {center_lat:.6f}, {center_lon:.6f}")
        print(f"使用的坐标系: {coordinate_system}")
        
        # 创建Folium地图（仅使用高德地图）
        # 高德地图瓦片URL - 使用GCJ-02坐标系
        tiles_url = 'http://webst02.is.autonavi.com/appmaptile?style=7&x={x}&y={y}&z={z}'
        attribution = '© <a href="http://ditu.amap.com/">高德地图</a>'
        
        # 创建地图，设置最大缩放级别为20（提供更详细的视图）
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=17,  # 提高初始缩放级别
            tiles=tiles_url,
            attr=attribution,
            control_scale=True,
            zoom_control=True,  # 启用缩放控件
            prefer_canvas=True,  # 使用canvas提高性能
            max_zoom=20,  # 设置最大缩放级别为20
            min_zoom=3,   # 最小缩放级别
        )
        
        # 添加缩放控件
        folium.plugins.ScrollZoomToggler().add_to(m)
        
        # 添加鼠标位置显示
        folium.plugins.MousePosition().add_to(m)
        
        # 添加轨迹线
        if len(positions) > 1:
            # 使用文档中的PolyLine方法
            folium.PolyLine(
                positions,
                weight=3,
                color='#FF6600',  # 橙色
                opacity=0.8,
                popup='GPS轨迹',
                tooltip='点击查看详细信息'
            ).add_to(m)
            
            # 添加轨迹填充效果
            folium.PolyLine(
                positions,
                weight=6,
                color='#FF6600',
                opacity=0.2,
            ).add_to(m)
        
        # 添加起点和终点标记
        if len(positions) >= 2:
            # 起点标记
            start_time = gps_data[0].get('time', 'N/A')
            start_popup = f'''
            <div style="font-family: Arial, sans-serif; max-width: 220px;">
                <h4 style="color: green; margin: 0;">🚩 起点</h4>
                <hr style="margin: 5px 0;">
                <b>时间:</b> {start_time}<br>
                <b>纬度:</b> {positions[0][1]:.6f}<br>
                <b>经度:</b> {positions[0][0]:.6f}<br>
                <b>坐标系:</b> {coordinate_system}
            </div>
            '''
            
            folium.Marker(
                [positions[0][1], positions[0][0]],  # [lat, lon]
                popup=folium.Popup(start_popup, max_width=250),
                tooltip='起点',
                icon=folium.Icon(color='green', icon='play', prefix='fa')
            ).add_to(m)
            
            # 终点标记
            end_time = gps_data[-1].get('time', 'N/A')
            end_popup = f'''
            <div style="font-family: Arial, sans-serif; max-width: 220px;">
                <h4 style="color: red; margin: 0;">🏁 终点</h4>
                <hr style="margin: 5px 0;">
                <b>时间:</b> {end_time}<br>
                <b>纬度:</b> {positions[-1][1]:.6f}<br>
                <b>经度:</b> {positions[-1][0]:.6f}<br>
                <b>坐标系:</b> {coordinate_system}
            </div>
            '''
            
            folium.Marker(
                [positions[-1][1], positions[-1][0]],
                popup=folium.Popup(end_popup, max_width=250),
                tooltip='终点',
                icon=folium.Icon(color='red', icon='stop', prefix='fa')
            ).add_to(m)
            
            # 计算轨迹长度
            total_distance = calculate_total_distance(positions)
            distance_info = f"轨迹长度: {total_distance:.2f}米"
            
            # 添加中间点标记（每隔10个点标记一个）
            for i in range(10, len(positions)-1, 10):
                if i < len(positions):
                    popup_text = f'''
                    <div style="font-family: Arial, sans-serif; max-width: 200px;">
                        <b>点 {i+1}</b><br>
                        <b>纬度:</b> {positions[i][1]:.6f}<br>
                        <b>经度:</b> {positions[i][0]:.6f}<br>
                        <b>坐标系:</b> {coordinate_system}
                    </div>
                    '''
                    
                    folium.CircleMarker(
                        [positions[i][1], positions[i][0]],
                        radius=3,
                        color='#3388ff',
                        fill=True,
                        fill_color='#3388ff',
                        fill_opacity=0.7,
                        popup=folium.Popup(popup_text, max_width=250)
                    ).add_to(m)
        else:
            # 只有一个点的情况
            point_popup = f'''
            <div style="font-family: Arial, sans-serif; max-width: 220px;">
                <h4 style="color: blue; margin: 0;">📍 GPS点</h4>
                <hr style="margin: 5px 0;">
                <b>时间:</b> {gps_data[0].get('time', 'N/A')}<br>
                <b>纬度:</b> {positions[0][1]:.6f}<br>
                <b>经度:</b> {positions[0][0]:.6f}<br>
                <b>坐标系:</b> {coordinate_system}
            </div>
            '''
            
            folium.Marker(
                [positions[0][1], positions[0][0]],
                popup=folium.Popup(point_popup, max_width=250),
                tooltip='GPS点',
                icon=folium.Icon(color='blue', icon='info-sign')
            ).add_to(m)
            distance_info = "单点位置"
            total_distance = 0
        
        # 添加全屏控件
        plugins.Fullscreen(
            position='topright',
            title='全屏',
            title_cancel='退出全屏',
            force_separate_button=True
        ).add_to(m)
        
        # 添加测量工具
        plugins.MeasureControl(
            position='topright',
            primary_length_unit='meters',
            secondary_length_unit='kilometers'
        ).add_to(m)
        
        # 添加轨迹信息控件
        info_html = f"""
        <div id="info-panel" style="
            position: fixed; 
            bottom: 50px; left: 50px; 
            width: 350px; 
            height: auto; 
            background-color: rgba(255, 255, 255, 0.95);
            border: 2px solid #4CAF50; 
            z-index: 9999; 
            padding: 15px;
            font-family: Arial, sans-serif;
            font-size: 14px; 
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            ">
            <h3 style="color: #2c3e50; margin-top: 0; margin-bottom: 10px;">📊 GPS轨迹信息</h3>
            <hr style="margin: 5px 0; border-color: #eee;">
            <div style="line-height: 1.6;">
                <b>📍 数据点数量:</b> {len(positions)}<br>
                <b>📏 轨迹长度:</b> {distance_info}<br>
                <b>🎯 中心点:</b> {center_lat:.6f}, {center_lon:.6f}<br>
                <b>🗺️ 地图类型:</b> 高德地图<br>
                <b>🔢 坐标系:</b> {coordinate_system}<br>
                <b>🔍 最大缩放级别:</b> 20级<br>
                <b>🕒 处理时间:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
            <button onclick="document.getElementById('info-panel').style.display='none'" 
                    style="margin-top: 10px; padding: 5px 10px; background-color: #f44336; color: white; border: none; border-radius: 4px; cursor: pointer;">
                关闭面板
            </button>
        </div>
        """
        
        # 将信息控件添加到地图
        m.get_root().html.add_child(folium.Element(info_html))
        
        # 添加图层控制
        folium.LayerControl().add_to(m)
        
        # 保存HTML文件到临时目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.gettempdir()
        html_file = os.path.join(temp_dir, f"gps_track_{timestamp}.html")
        
        m.save(html_file)
        print(f"地图已保存到: {html_file}")
        
        info = {
            'points_count': len(positions),
            'total_distance': total_distance if len(positions) > 1 else 0,
            'center_lat': center_lat,
            'center_lon': center_lon,
            'html_file': html_file,
            'map_type': '高德地图',
            'coordinate_system': coordinate_system,
            'max_zoom': 20
        }
        
        # 返回HTML内容
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        return html_content, info
        
    except Exception as e:
        print(f"创建地图失败: {e}")
        import traceback
        traceback.print_exc()
        return None, {"error": f"创建地图失败: {str(e)}"}

def calculate_total_distance(positions):
    """
    使用Haversine公式计算轨迹总长度
    参考文档中的距离计算方法
    """
    if len(positions) < 2:
        return 0
    
    total_distance = 0
    R = 6371000  # 地球半径（米）
    
    for i in range(1, len(positions)):
        lon1, lat1 = positions[i-1]
        lon2, lat2 = positions[i]
        
        # 转换为弧度
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        # Haversine公式
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = R * c
        
        total_distance += distance
    
    return total_distance

class SnapshotDisplayWidget(QLabel):
    """截图显示控件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setText("选择截图文件...")
        self.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                color: #666;
                font-size: 14px;
                border: 2px dashed #ccc;
                border-radius: 8px;
            }
        """)
        self.setMinimumSize(320, 180)
    
    def set_image(self, image_path):
        """设置截图图像"""
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.setPixmap(scaled_pixmap)
            else:
                self.setText("无法加载图像")
        else:
            self.setText("文件不存在")

class GPSFoliumTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.processing_thread = None
        self.gps_saver_thread = None
        self.current_html_file = None
        self.last_file_path = None
        self.wgs84_positions = None  # 保存原始WGS-84坐标
        self.conversion_mode = "wgs84_to_gcj02"  # 默认使用WGS-84转GCJ-02
        self.snapshot_files = []  # 存储截图文件列表
        
        # ESP32连接配置
        self.esp32_ip = "192.168.4.1"  # 默认AP模式IP
        self.esp32_http_port = "80"    # HTTP端口
        self.esp32_stream_port = "81"  # 视频流端口
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle('GPS轨迹可视化系统')
        self.setGeometry(100, 100, 1400, 800)  # 调整窗口尺寸
        
        # 设置样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f7fa;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QComboBox {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 4px;
                font-size: 12px;
                min-height: 28px;
            }
            QComboBox:on {
                border: 2px solid #4CAF50;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #ccc;
                background-color: white;
                selection-background-color: #e3f2fd;
            }
            QCheckBox {
                font-size: 13px;
                color: #333333;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QLabel {
                font-size: 13px;
                color: #333333;
            }
            QTextEdit {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 6px;
                font-size: 11px;
                padding: 6px;
                font-family: 'Microsoft YaHei', Arial;
            }
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 6px;
                text-align: center;
                height: 18px;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1: 0, y1: 0.5, x2: 1, y2: 0.5,
                    stop: 0 #4CAF50,
                    stop: 1 #2E7D32
                );
                border-radius: 6px;
            }
            QGroupBox {
                border: 2px solid #4CAF50;
                border-radius: 8px;
                margin-top: 8px;
                font-weight: bold;
                padding-top: 8px;
                font-size: 13px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #2c3e50;
            }
            QLineEdit {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 4px;
                font-size: 12px;
            }
            QTabWidget::pane {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
            }
            QTabBar::tab {
                padding: 8px 16px;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 2px solid #4CAF50;
                font-weight: bold;
            }
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 6px;
                background-color: white;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1565c0;
            }
        """)
        
        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局 - 使用水平分割器，从左到右排列
        main_layout = QHBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # ===== 第一列：地图模块 =====
        map_widget = QWidget()
        map_layout = QVBoxLayout()
        map_layout.setSpacing(10)
        
        # 地图标题
        map_title = QLabel('🗺️ 地图模块')
        map_title.setAlignment(Qt.AlignCenter)
        map_font = QFont()
        map_font.setPointSize(14)
        map_font.setBold(True)
        map_title.setFont(map_font)
        map_title.setStyleSheet("""
            color: white; 
            padding: 8px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #4CAF50, stop:1 #2196F3);
            border-radius: 8px;
        """)
        map_layout.addWidget(map_title)
        
        # ESP32连接配置
        esp32_group = QGroupBox("ESP32连接配置")
        esp32_layout = QGridLayout()
        
        esp32_layout.addWidget(QLabel("IP地址:"), 0, 0)
        self.ip_edit = QLineEdit(self.esp32_ip)
        esp32_layout.addWidget(self.ip_edit, 0, 1)
        
        esp32_layout.addWidget(QLabel("HTTP端口:"), 0, 2)
        self.http_port_edit = QLineEdit(self.esp32_http_port)
        esp32_layout.addWidget(self.http_port_edit, 0, 3)
        
        self.connect_btn = QPushButton('连接ESP32')
        self.connect_btn.clicked.connect(self.connect_esp32)
        esp32_layout.addWidget(self.connect_btn, 1, 0, 1, 2)
        
        self.connection_status = QLabel('未连接')
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        esp32_layout.addWidget(self.connection_status, 1, 2, 1, 2)
        
        esp32_group.setLayout(esp32_layout)
        map_layout.addWidget(esp32_group)
        
        # 控制面板
        control_group = QGroupBox("地图控制")
        control_layout = QGridLayout()
        
        self.load_btn = QPushButton('📁 导入GPS数据')
        self.load_btn.setFixedHeight(36)
        self.load_btn.clicked.connect(self.load_gps_file)
        control_layout.addWidget(self.load_btn, 0, 0, 1, 2)
        
        self.export_btn = QPushButton('💾 导出HTML')
        self.export_btn.setFixedHeight(36)
        self.export_btn.clicked.connect(self.export_html)
        self.export_btn.setEnabled(False)
        control_layout.addWidget(self.export_btn, 0, 2, 1, 2)
        
        self.view_browser_btn = QPushButton('🌐 浏览器打开')
        self.view_browser_btn.setFixedHeight(36)
        self.view_browser_btn.clicked.connect(self.view_in_browser)
        self.view_browser_btn.setEnabled(False)
        control_layout.addWidget(self.view_browser_btn, 1, 0, 1, 2)
        
        self.clear_btn = QPushButton('🗑️ 清除数据')
        self.clear_btn.setFixedHeight(36)
        self.clear_btn.clicked.connect(self.clear_data)
        control_layout.addWidget(self.clear_btn, 1, 2, 1, 2)
        
        control_group.setLayout(control_layout)
        map_layout.addWidget(control_group)
        
        # 坐标转换选项
        coord_group = QGroupBox("坐标转换设置")
        coord_layout = QGridLayout()
        
        coord_layout.addWidget(QLabel("转换模式:"), 0, 0)
        self.conversion_combo = QComboBox()
        self.conversion_combo.addItem("WGS-84 → GCJ-02 (标准转换)")
        self.conversion_combo.addItem("原始数据 → GCJ-02 (北斗原始值)")
        self.conversion_combo.addItem("TXT文件 → GCJ-02 (已解析数据)")
        self.conversion_combo.addItem("不转换 (使用原始坐标系)")
        self.conversion_combo.setCurrentIndex(0)
        self.conversion_combo.currentIndexChanged.connect(self.on_conversion_mode_changed)
        coord_layout.addWidget(self.conversion_combo, 0, 1, 1, 3)
        
        self.coordinate_info_label = QLabel('当前使用: WGS-84 → GCJ-02 转换模式')
        self.coordinate_info_label.setStyleSheet("""
            background-color: #E8F5E9; 
            padding: 8px; 
            border-radius: 4px;
            border: 1px solid #4CAF50;
            font-size: 12px;
        """)
        coord_layout.addWidget(self.coordinate_info_label, 1, 0, 1, 4)
        
        coord_group.setLayout(coord_layout)
        map_layout.addWidget(coord_group)
        
        # 地图显示区域
        map_display_group = QGroupBox("地图显示")
        map_display_layout = QVBoxLayout()
        
        # 使用QWebEngineView显示Folium地图
        self.web_view = QWebEngineView()
        self.web_view.setMinimumHeight(500)
        self.web_view.setHtml(self.get_welcome_html())
        
        map_display_layout.addWidget(self.web_view)
        map_display_group.setLayout(map_display_layout)
        map_layout.addWidget(map_display_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setValue(0)
        map_layout.addWidget(self.progress_bar)
        
        # 信息显示区域
        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setFixedHeight(100)
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
            }
        """)
        
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        map_layout.addWidget(log_group)
        
        map_widget.setLayout(map_layout)
        
        # ===== 第二列：数据管理模块 =====
        data_widget = QWidget()
        data_layout = QVBoxLayout()
        data_layout.setSpacing(10)
        
        # 数据模块标题
        data_title = QLabel('📊 数据管理模块')
        data_title.setAlignment(Qt.AlignCenter)
        data_title_font = QFont()
        data_title_font.setPointSize(14)
        data_title_font.setBold(True)
        data_title.setFont(data_title_font)
        data_title.setStyleSheet("""
            color: white; 
            padding: 8px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #2196F3, stop:1 #9C27B0);
            border-radius: 8px;
        """)
        data_layout.addWidget(data_title)
        
        # GPS数据保存设置
        gps_save_group = QGroupBox("GPS数据自动保存")
        gps_save_layout = QVBoxLayout()
        
        # 保存控制
        save_control_layout = QHBoxLayout()
        self.start_save_btn = QPushButton('💾 开始保存')
        self.start_save_btn.clicked.connect(self.start_gps_data_save)
        self.start_save_btn.setEnabled(False)
        self.start_save_btn.setMaximumWidth(120)
        
        self.stop_save_btn = QPushButton('⏹️ 停止保存')
        self.stop_save_btn.clicked.connect(self.stop_gps_data_save)
        self.stop_save_btn.setEnabled(False)
        self.stop_save_btn.setMaximumWidth(120)
        
        save_control_layout.addWidget(self.start_save_btn)
        save_control_layout.addWidget(self.stop_save_btn)
        save_control_layout.addStretch()
        
        gps_save_layout.addLayout(save_control_layout)
        
        # 保存状态
        self.save_status_label = QLabel('GPS数据保存: 未启动')
        self.save_status_label.setStyleSheet("""
            padding: 6px;
            background-color: #e8f5e9;
            border: 1px solid #c8e6c9;
            border-radius: 4px;
            font-size: 12px;
        """)
        gps_save_layout.addWidget(self.save_status_label)
        
        # 当前保存文件信息
        self.current_save_file_label = QLabel('当前保存文件: 无')
        self.current_save_file_label.setStyleSheet("""
            padding: 4px;
            font-size: 11px;
            color: #666;
        """)
        gps_save_layout.addWidget(self.current_save_file_label)
        
        gps_save_group.setLayout(gps_save_layout)
        data_layout.addWidget(gps_save_group)
        
        # 历史数据文件查看
        history_group = QGroupBox("历史GPS数据查看")
        history_layout = QVBoxLayout()
        
        # 文件列表和查看区域
        history_splitter = QSplitter(Qt.Vertical)
        
        # 上部：文件列表
        file_list_widget = QWidget()
        file_list_layout = QVBoxLayout()
        
        file_list_title = QLabel("GPS数据文件列表")
        file_list_title.setStyleSheet("font-weight: bold; color: #333;")
        file_list_layout.addWidget(file_list_title)
        
        self.gps_file_list = QListWidget()
        self.gps_file_list.itemClicked.connect(self.on_gps_file_selected)
        file_list_layout.addWidget(self.gps_file_list)
        
        # 文件管理按钮
        file_buttons = QHBoxLayout()
        self.refresh_gps_files_btn = QPushButton('🔄 刷新')
        self.refresh_gps_files_btn.clicked.connect(self.refresh_gps_files_list)
        self.refresh_gps_files_btn.setMaximumWidth(80)
        
        self.view_gps_file_btn = QPushButton('📄 查看内容')
        self.view_gps_file_btn.clicked.connect(self.view_selected_gps_file)
        self.view_gps_file_btn.setEnabled(False)
        self.view_gps_file_btn.setMaximumWidth(100)
        
        self.delete_gps_file_btn = QPushButton('🗑️ 删除')
        self.delete_gps_file_btn.clicked.connect(self.delete_selected_gps_file)
        self.delete_gps_file_btn.setEnabled(False)
        self.delete_gps_file_btn.setMaximumWidth(80)
        
        file_buttons.addWidget(self.refresh_gps_files_btn)
        file_buttons.addWidget(self.view_gps_file_btn)
        file_buttons.addWidget(self.delete_gps_file_btn)
        file_buttons.addStretch()
        
        file_list_layout.addLayout(file_buttons)
        file_list_widget.setLayout(file_list_layout)
        history_splitter.addWidget(file_list_widget)
        
        # 下部：文件内容显示
        file_content_widget = QWidget()
        file_content_layout = QVBoxLayout()
        
        file_content_title = QLabel("文件内容")
        file_content_title.setStyleSheet("font-weight: bold; color: #333;")
        file_content_layout.addWidget(file_content_title)
        
        self.gps_file_content = QTextEdit()
        self.gps_file_content.setReadOnly(True)
        self.gps_file_content.setFixedHeight(150)
        self.gps_file_content.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
                background-color: #f8f9fa;
            }
        """)
        file_content_layout.addWidget(self.gps_file_content)
        
        file_content_widget.setLayout(file_content_layout)
        history_splitter.addWidget(file_content_widget)
        
        # 设置分割器比例
        history_splitter.setSizes([250, 150])
        
        history_layout.addWidget(history_splitter)
        history_group.setLayout(history_layout)
        data_layout.addWidget(history_group)
        
        # 截图管理
        snapshot_group = QGroupBox("截图管理")
        snapshot_layout = QVBoxLayout()
        
        # 截图文件列表和显示区域
        snapshot_splitter = QSplitter(Qt.Horizontal)
        
        # 左侧：截图文件列表
        snapshot_list_widget = QWidget()
        snapshot_list_layout = QVBoxLayout()
        
        snapshot_list_title = QLabel("截图文件列表")
        snapshot_list_title.setStyleSheet("font-weight: bold; color: #333;")
        snapshot_list_layout.addWidget(snapshot_list_title)
        
        self.snapshot_list = QListWidget()
        self.snapshot_list.setMaximumWidth(150)
        self.snapshot_list.itemClicked.connect(self.on_snapshot_selected)
        snapshot_list_layout.addWidget(self.snapshot_list)
        
        # 截图文件管理按钮
        snapshot_file_buttons = QHBoxLayout()
        
        self.refresh_snapshot_btn = QPushButton('🔄 刷新')
        self.refresh_snapshot_btn.clicked.connect(self.refresh_snapshot_list)
        self.refresh_snapshot_btn.setMaximumWidth(70)
        
        self.delete_snapshot_btn = QPushButton('🗑️ 删除')
        self.delete_snapshot_btn.clicked.connect(self.delete_selected_snapshot)
        self.delete_snapshot_btn.setMaximumWidth(70)
        
        snapshot_file_buttons.addWidget(self.refresh_snapshot_btn)
        snapshot_file_buttons.addWidget(self.delete_snapshot_btn)
        snapshot_file_buttons.addStretch()
        
        snapshot_list_layout.addLayout(snapshot_file_buttons)
        snapshot_list_widget.setLayout(snapshot_list_layout)
        snapshot_splitter.addWidget(snapshot_list_widget)
        
        # 右侧：截图显示
        snapshot_display_widget = QWidget()
        snapshot_display_layout = QVBoxLayout()
        
        snapshot_display_title = QLabel("选中的截图")
        snapshot_display_title.setStyleSheet("font-weight: bold; color: #333;")
        snapshot_display_layout.addWidget(snapshot_display_title)
        
        self.snapshot_display = SnapshotDisplayWidget()
        snapshot_display_layout.addWidget(self.snapshot_display)
        
        snapshot_display_widget.setLayout(snapshot_display_layout)
        snapshot_splitter.addWidget(snapshot_display_widget)
        
        # 设置分割器比例
        snapshot_splitter.setSizes([150, 300])
        
        snapshot_layout.addWidget(snapshot_splitter)
        snapshot_group.setLayout(snapshot_layout)
        data_layout.addWidget(snapshot_group)
        
        data_widget.setLayout(data_layout)
        
        # ===== 添加到主布局 =====
        # 创建水平分割器，从左到右排列两个模块
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(map_widget)
        splitter.addWidget(data_widget)
        
        # 设置两个模块的初始比例：地图60%，数据管理40%
        splitter.setSizes([840, 560])
        
        main_layout.addWidget(splitter)
        central_widget.setLayout(main_layout)
        
        # 状态栏
        self.statusBar().showMessage('系统就绪，等待连接ESP32...')
        
        # 初始化URLs
        self.update_esp32_urls()
        
        # 刷新截图列表
        self.refresh_snapshot_list()
        
        # 刷新GPS文件列表
        self.refresh_gps_files_list()
    
    def update_esp32_urls(self):
        """更新ESP32 URLs"""
        base_http_url = f"http://{self.esp32_ip}:{self.esp32_http_port}"
        
        # HTTP服务URLs
        self.gps_json_url = f"{base_http_url}/gps/json"  # GPS JSON数据
        self.status_url = f"{base_http_url}/status"      # 状态检查
        
    def get_welcome_html(self):
        """获取欢迎页面HTML"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    font-family: 'Arial', sans-serif;
                }
                .welcome-container {
                    text-align: center;
                    background: rgba(255, 255, 255, 0.95);
                    padding: 30px;
                    border-radius: 15px;
                    box-shadow: 0 15px 40px rgba(0,0,0,0.2);
                    max-width: 600px;
                }
                .welcome-title {
                    color: #2c3e50;
                    font-size: 24px;
                    margin-bottom: 15px;
                    font-weight: bold;
                }
                .welcome-subtitle {
                    color: #666;
                    font-size: 16px;
                    margin-bottom: 20px;
                    line-height: 1.5;
                }
                .features {
                    text-align: left;
                    margin: 15px 0;
                    padding: 0 15px;
                }
                .feature-item {
                    margin: 8px 0;
                    color: #333;
                    font-size: 13px;
                }
                .feature-item:before {
                    content: "✓ ";
                    color: #4CAF50;
                    font-weight: bold;
                }
                .instruction {
                    margin-top: 20px;
                    padding: 12px;
                    background: #E3F2FD;
                    border-radius: 8px;
                    border-left: 4px solid #2196F3;
                    font-size: 12px;
                }
            </style>
        </head>
        <body>
            <div class="welcome-container">
                <div class="welcome-title">🌍 GPS轨迹可视化系统</div>
                <div class="welcome-subtitle">
                    专业GPS数据处理与轨迹可视化工具
                </div>
                
                <div class="features">
                    <div class="feature-item">GPS数据导入与轨迹可视化</div>
                    <div class="feature-item">支持四种坐标转换模式</div>
                    <div class="feature-item">模式1: WGS-84 → GCJ-02 (标准转换)</div>
                    <div class="feature-item">模式2: 原始数据 → GCJ-02 (北斗原始值)</div>
                    <div class="feature-item">模式3: TXT文件 → GCJ-02 (已解析数据)</div>
                    <div class="feature-item">模式4: 不转换 (使用原始坐标系)</div>
                    <div class="feature-item">高德地图显示，支持20级缩放</div>
                    <div class="feature-item">GPS数据自动保存到文件（每秒1个点）</div>
                    <div class="feature-item">历史数据查看与管理</div>
                    <div class="feature-item">截图文件管理功能</div>
                </div>
                
                <div class="instruction">
                    <strong>使用说明:</strong><br>
                    1. 配置ESP32连接信息并连接<br>
                    2. 选择坐标转换模式<br>
                    3. 导入GPS数据文件或使用实时GPS<br>
                    4. 可启动GPS数据自动保存（每秒1个点）<br>
                    5. 使用地图工具栏进行缩放、测量等操作<br>
                    6. 可导出HTML文件或在浏览器中查看<br>
                    7. GPS数据自动保存，可查看历史数据<br>
                    8. 管理截图文件
                </div>
            </div>
        </body>
        </html>
        """
    
    def connect_esp32(self):
        """连接ESP32"""
        self.esp32_ip = self.ip_edit.text().strip()
        self.esp32_http_port = self.http_port_edit.text().strip()
        
        if not self.esp32_ip:
            QMessageBox.warning(self, '警告', '请输入ESP32 IP地址')
            return
        
        self.update_esp32_urls()
        
        # 测试连接
        try:
            response = requests.get(self.status_url, timeout=5)
            if response.status_code == 200:
                self.connection_status.setText('已连接')
                self.connection_status.setStyleSheet("color: green; font-weight: bold;")
                
                # 启用相关按钮
                self.start_save_btn.setEnabled(True)
                
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] ✅ ESP32连接成功')
                self.statusBar().showMessage('ESP32连接成功')
            else:
                self.connection_status.setText(f'连接失败: {response.status_code}')
                self.connection_status.setStyleSheet("color: red; font-weight: bold;")
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] ❌ ESP32连接失败: {response.status_code}')
                
        except Exception as e:
            self.connection_status.setText('连接错误')
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] ❌ ESP32连接错误: {str(e)}')
    
    def refresh_snapshot_list(self):
        """刷新截图列表"""
        try:
            self.snapshot_list.clear()
            self.snapshot_files = []
            
            # 查找当前目录下所有的截图文件
            import glob
            snapshot_patterns = ["snapshot_*.png", "snapshot_*.jpg", "snapshot_*.jpeg"]
            
            for pattern in snapshot_patterns:
                for file_path in glob.glob(pattern):
                    file_name = os.path.basename(file_path)
                    file_size = os.path.getsize(file_path)
                    display_text = f"{file_name} ({file_size/1024:.1f} KB)"
                    
                    item = QListWidgetItem(display_text)
                    item.setData(Qt.UserRole, file_path)
                    self.snapshot_list.addItem(item)
                    self.snapshot_files.append(file_path)
            
            if self.snapshot_files:
                # 默认选择最后一个（最新的）
                self.snapshot_list.setCurrentRow(len(self.snapshot_files) - 1)
                self.on_snapshot_selected(self.snapshot_list.currentItem())
            
        except Exception as e:
            print(f"刷新截图列表错误: {e}")
    
    def on_snapshot_selected(self, item):
        """当截图被选中时显示"""
        if item:
            file_path = item.data(Qt.UserRole)
            if os.path.exists(file_path):
                self.show_snapshot(file_path)
    
    def show_snapshot(self, file_path):
        """显示截图"""
        try:
            self.snapshot_display.set_image(file_path)
        except Exception as e:
            print(f"显示截图错误: {e}")
    
    def delete_selected_snapshot(self):
        """删除选中的截图"""
        current_item = self.snapshot_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, '警告', '请先选择一个截图文件')
            return
        
        file_path = current_item.data(Qt.UserRole)
        
        reply = QMessageBox.question(
            self, '确认删除', 
            f'确定要删除截图文件吗？\n{os.path.basename(file_path)}',
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                os.remove(file_path)
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🗑️ 删除截图: {os.path.basename(file_path)}')
                
                # 刷新列表
                self.refresh_snapshot_list()
                
                # 清空显示
                self.snapshot_display.setText("选择截图文件...")
                
            except Exception as e:
                QMessageBox.warning(self, '删除失败', f'删除文件失败:\n{str(e)}')
    
    def start_gps_data_save(self):
        """开始保存GPS数据"""
        if self.gps_saver_thread and self.gps_saver_thread.isRunning():
            self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] ⚠️ GPS数据保存已在运行')
            return
        
        self.gps_saver_thread = GPSDataSaver(self.gps_json_url, save_interval=1.0)  # 修改为1.0秒
        self.gps_saver_thread.data_saved.connect(self.on_gps_data_saved)
        self.gps_saver_thread.status_updated.connect(self.on_gps_save_status_updated)
        self.gps_saver_thread.start()
        
        self.start_save_btn.setEnabled(False)
        self.stop_save_btn.setEnabled(True)
        
        self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 💾 启动GPS数据保存（每秒1个点）')
    
    def stop_gps_data_save(self):
        """停止保存GPS数据"""
        if self.gps_saver_thread:
            self.gps_saver_thread.stop()
            self.gps_saver_thread.wait()
        
        self.start_save_btn.setEnabled(True)
        self.stop_save_btn.setEnabled(False)
        
        self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] ⏹️ 停止GPS数据保存')
        self.save_status_label.setText('GPS数据保存: 已停止')
        self.current_save_file_label.setText('当前保存文件: 无')
    
    def on_gps_data_saved(self, file_path, success):
        """GPS数据保存回调"""
        if success:
            self.current_save_file_label.setText(f'当前保存文件: {os.path.basename(file_path)}')
    
    def on_gps_save_status_updated(self, message):
        """GPS保存状态更新"""
        self.save_status_label.setText(f'GPS数据保存: {message}')
        # 减少日志输出频率，避免日志过多
        # 只记录重要状态信息，不记录每个保存点的消息
        if any(keyword in message for keyword in ["已启动", "已停止", "错误", "创建新", "GPS数据无效"]):
            self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 💾 {message}')
    
    def refresh_gps_files_list(self):
        """刷新GPS数据文件列表"""
        try:
            self.gps_file_list.clear()
            
            # 获取保存的GPS数据文件
            if self.gps_saver_thread:
                files = self.gps_saver_thread.get_saved_files()
            else:
                # 如果没有保存线程，直接扫描目录
                save_directory = "gps_data"
                if os.path.exists(save_directory):
                    files = [f for f in os.listdir(save_directory) if f.endswith('.txt')]
                    files.sort(reverse=True)
                    files = [os.path.join(save_directory, f) for f in files]
                else:
                    files = []
            
            for file_path in files:
                if os.path.exists(file_path):
                    file_name = os.path.basename(file_path)
                    file_size = os.path.getsize(file_path)
                    display_text = f"{file_name} ({file_size/1024:.1f} KB)"
                    
                    item = QListWidgetItem(display_text)
                    item.setData(Qt.UserRole, file_path)
                    self.gps_file_list.addItem(item)
            
            if files:
                self.gps_file_list.setCurrentRow(0)
                self.on_gps_file_selected(self.gps_file_list.currentItem())
            
        except Exception as e:
            print(f"刷新GPS文件列表错误: {e}")
    
    def on_gps_file_selected(self, item):
        """当GPS文件被选中时"""
        if item:
            file_path = item.data(Qt.UserRole)
            self.view_gps_file_btn.setEnabled(True)
            self.delete_gps_file_btn.setEnabled(True)
            
            # 预览文件内容
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    preview = "".join(lines[:20])  # 预览前20行
                    if len(lines) > 20:
                        preview += f"...\n(共{len(lines)}行，显示前20行)"
                    
                    self.gps_file_content.setText(preview)
            except Exception as e:
                self.gps_file_content.setText(f"读取文件错误: {str(e)}")
        else:
            self.view_gps_file_btn.setEnabled(False)
            self.delete_gps_file_btn.setEnabled(False)
            self.gps_file_content.clear()
    
    def view_selected_gps_file(self):
        """查看选中的GPS文件完整内容"""
        current_item = self.gps_file_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, '警告', '请先选择一个GPS数据文件')
            return
        
        file_path = current_item.data(Qt.UserRole)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 创建查看对话框
            dialog = QDialog(self)
            dialog.setWindowTitle(f'查看文件: {os.path.basename(file_path)}')
            dialog.setGeometry(200, 200, 800, 600)
            
            layout = QVBoxLayout()
            
            # 添加文本显示区域
            text_edit = QTextEdit()
            text_edit.setPlainText(content)
            text_edit.setReadOnly(True)
            text_edit.setFont(QFont('Consolas', 10))
            layout.addWidget(text_edit)
            
            # 添加关闭按钮
            close_btn = QPushButton('关闭')
            close_btn.clicked.connect(dialog.close)
            layout.addWidget(close_btn)
            
            dialog.setLayout(layout)
            dialog.exec_()
            
        except Exception as e:
            QMessageBox.warning(self, '错误', f'读取文件失败:\n{str(e)}')
    
    def delete_selected_gps_file(self):
        """删除选中的GPS文件"""
        current_item = self.gps_file_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, '警告', '请先选择一个GPS数据文件')
            return
        
        file_path = current_item.data(Qt.UserRole)
        
        reply = QMessageBox.question(
            self, '确认删除', 
            f'确定要删除GPS数据文件吗？\n{os.path.basename(file_path)}',
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                os.remove(file_path)
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🗑️ 删除GPS数据文件: {os.path.basename(file_path)}')
                
                # 刷新列表
                self.refresh_gps_files_list()
                
                # 清空显示
                self.gps_file_content.clear()
                
            except Exception as e:
                QMessageBox.warning(self, '删除失败', f'删除文件失败:\n{str(e)}')
    
    def on_conversion_mode_changed(self, index):
        """坐标转换模式改变"""
        if index == 0:
            self.conversion_mode = "wgs84_to_gcj02"
            self.coordinate_info_label.setText('当前使用: WGS-84 → GCJ-02 转换模式')
            self.coordinate_info_label.setStyleSheet("""
                background-color: #E8F5E9; 
                padding: 8px; 
                border-radius: 4px;
                border: 1px solid #4CAF50;
                font-size: 12px;
            """)
        elif index == 1:
            self.conversion_mode = "raw_to_gcj02"
            self.coordinate_info_label.setText('当前使用: 原始数据 → GCJ-02 转换模式')
            self.coordinate_info_label.setStyleSheet("""
                background-color: #E3F2FD; 
                padding: 8px; 
                border-radius: 4px;
                border: 1px solid #2196F3;
                font-size: 12px;
            """)
        elif index == 2:
            self.conversion_mode = "txt_to_gcj02"
            self.coordinate_info_label.setText('当前使用: TXT文件 → GCJ-02 转换模式')
            self.coordinate_info_label.setStyleSheet("""
                background-color: #FFF3E0; 
                padding: 8px; 
                border-radius: 4px;
                border: 1px solid #FF9800;
                font-size: 12px;
            """)
        else:
            self.conversion_mode = "no_conversion"
            self.coordinate_info_label.setText('当前使用: 不进行坐标转换')
            self.coordinate_info_label.setStyleSheet("""
                background-color: #FCE4EC; 
                padding: 8px; 
                border-radius: 4px;
                border: 1px solid #E91E63;
                font-size: 12px;
            """)
        
        # 如果已经有数据，重新处理
        if self.last_file_path and os.path.exists(self.last_file_path):
            self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🔄 切换转换模式，重新处理数据')
            self.reprocess_gps_file()
    
    def reprocess_gps_file(self):
        """重新处理GPS文件"""
        if not self.last_file_path:
            return
        
        # 清空日志
        self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🔄 重新处理文件: {os.path.basename(self.last_file_path)}')
        
        # 更新界面状态
        self.set_buttons_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage('正在重新处理GPS数据...')
        
        # 如果之前有处理线程，先停止
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.terminate()
            self.processing_thread.wait()
        
        # 启动新的处理线程
        self.processing_thread = GPSProcessingThread(self.last_file_path, self.conversion_mode)
        self.processing_thread.processing_started.connect(self.on_processing_started)
        self.processing_thread.processing_finished.connect(self.on_processing_finished)
        self.processing_thread.error_occurred.connect(self.on_processing_error)
        self.processing_thread.progress_updated.connect(self.on_progress_updated)
        self.processing_thread.start()
    
    def load_gps_file(self):
        """加载GPS数据文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            '选择GPS数据文件', 
            '', 
            'GPS数据文件 (*.txt *.nmea *.log);;所有文件 (*.*)'
        )
        
        if file_path:
            self.last_file_path = file_path
            
            if not os.path.exists(file_path):
                QMessageBox.warning(self, '错误', '文件不存在！')
                return
            
            # 检查文件大小
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                QMessageBox.warning(self, '错误', '文件为空！')
                return
            
            # 清空日志
            self.log_text.clear()
            self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 📂 加载文件: {os.path.basename(file_path)}')
            self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 📏 文件大小: {file_size:,} 字节')
            self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🔄 开始解析GPS数据...')
            
            # 显示选择的转换模式
            if self.conversion_mode == "wgs84_to_gcj02":
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🔧 转换模式: WGS-84 → GCJ-02')
            elif self.conversion_mode == "raw_to_gcj02":
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🔧 转换模式: 原始数据 → GCJ-02')
            elif self.conversion_mode == "txt_to_gcj02":
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🔧 转换模式: TXT文件 → GCJ-02 (已解析数据)')
            else:
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🔧 转换模式: 不转换')
            
            # 更新界面状态
            self.set_buttons_enabled(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.statusBar().showMessage('正在处理GPS数据...')
            
            # 如果之前有处理线程，先停止
            if self.processing_thread and self.processing_thread.isRunning():
                self.processing_thread.terminate()
                self.processing_thread.wait()
            
            # 启动新的处理线程
            self.processing_thread = GPSProcessingThread(file_path, self.conversion_mode)
            self.processing_thread.processing_started.connect(self.on_processing_started)
            self.processing_thread.processing_finished.connect(self.on_processing_finished)
            self.processing_thread.error_occurred.connect(self.on_processing_error)
            self.processing_thread.progress_updated.connect(self.on_progress_updated)
            self.processing_thread.start()
    
    def on_processing_started(self):
        """处理开始"""
        self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] ✅ GPS数据解析开始...')
        QApplication.processEvents()
    
    def on_progress_updated(self, value):
        """进度更新"""
        self.progress_bar.setValue(value)
        QApplication.processEvents()
    
    def on_processing_finished(self, html_content, positions, info, wgs84_positions):
        """处理完成"""
        try:
            self.progress_bar.setVisible(False)
            
            if html_content and positions:
                # 保存原始坐标
                self.wgs84_positions = wgs84_positions
                
                # 显示HTML内容
                self.web_view.setHtml(html_content)
                self.current_html_file = info.get('html_file', None)
                
                # 更新日志
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] ✅ 地图生成成功！')
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 📍 解析到 {info["points_count"]} 个GPS点')
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🗺️ 使用坐标系: {info.get("coordinate_system", "未知")}')
                
                if info["points_count"] > 1:
                    distance_km = info["total_distance"] / 1000
                    self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 📏 轨迹长度: {info["total_distance"]:.2f} 米 ({distance_km:.3f} 公里)')
                    self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🎯 中心点: {info["center_lat"]:.6f}, {info["center_lon"]:.6f}')
                
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🗺️ 使用地图: {info.get("map_type", "高德地图")}')
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🔍 最大缩放级别: {info.get("max_zoom", 20)} 级')
                
                # 更新坐标系标签
                self.coordinate_info_label.setText(f'当前使用: {info.get("coordinate_system", "未知")}')
                
                self.statusBar().showMessage('处理完成，地图已生成')
                
                # 提示保存成功
                if self.current_html_file:
                    self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 💾 临时地图文件: {self.current_html_file}')
                
                # 启用相关按钮
                self.export_btn.setEnabled(True)
                self.view_browser_btn.setEnabled(True)
                
            else:
                error_msg = info.get("error", "未知错误")
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] ❌ 地图生成失败: {error_msg}')
                self.statusBar().showMessage('处理失败')
                
        except Exception as e:
            self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] ❌ 处理完成回调错误: {str(e)}')
        
        finally:
            # 总是启用基本按钮
            self.set_buttons_enabled(True)
            
    def on_processing_error(self, error_msg):
        """处理错误"""
        self.progress_bar.setVisible(False)
        
        self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] ❌ 处理过程中发生错误: {error_msg}')
        QMessageBox.critical(self, '处理错误', f'处理过程中发生错误:\n{error_msg}')
        self.statusBar().showMessage('处理错误')
        
        # 恢复按钮状态
        self.set_buttons_enabled(True)
    
    def export_html(self):
        """导出HTML文件"""
        if not self.current_html_file or not os.path.exists(self.current_html_file):
            QMessageBox.warning(self, '警告', '没有可导出的HTML文件')
            return
        
        default_name = f"gps_track_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            '保存HTML文件',
            default_name,
            'HTML文件 (*.html);;所有文件 (*.*)'
        )
        
        if save_path:
            try:
                # 读取当前HTML内容
                with open(self.current_html_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # 保存到指定位置
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 💾 HTML文件已保存至: {save_path}')
                QMessageBox.information(self, '导出成功', f'HTML文件已成功导出至:\n{save_path}')
                
            except Exception as e:
                self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] ❌ 导出失败: {str(e)}')
                QMessageBox.critical(self, '导出失败', f'导出HTML文件失败:\n{str(e)}')
    
    def view_in_browser(self):
        """在浏览器中打开"""
        if not self.current_html_file or not os.path.exists(self.current_html_file):
            QMessageBox.warning(self, '警告', '没有可查看的HTML文件')
            return
        
        try:
            # 转换为文件URL
            file_url = QUrl.fromLocalFile(self.current_html_file).toString()
            webbrowser.open(file_url)
            
            self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🌐 在默认浏览器中打开地图')
            
        except Exception as e:
            self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] ❌ 打开浏览器失败: {str(e)}')
            QMessageBox.critical(self, '打开失败', f'在浏览器中打开失败:\n{str(e)}')
    
    def clear_data(self):
        """清除数据"""
        reply = QMessageBox.question(
            self, 
            '确认清除', 
            '确定要清除所有数据吗？\n这将重置地图和日志。',
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 重置界面
            self.web_view.setHtml(self.get_welcome_html())
            self.log_text.clear()
            self.coordinate_info_label.setText('当前使用: WGS-84 → GCJ-02 转换模式')
            self.coordinate_info_label.setStyleSheet("""
                background-color: #E8F5E9; 
                padding: 8px; 
                border-radius: 4px;
                border: 1px solid #4CAF50;
                font-size: 12px;
            """)
            
            # 清除GPS文件内容显示
            self.gps_file_content.clear()
            
            # 清除截图显示
            self.snapshot_display.setText("选择截图文件...")
            
            # 禁用相关按钮
            self.export_btn.setEnabled(False)
            self.view_browser_btn.setEnabled(False)
            
            # 清理临时文件
            if hasattr(self, 'current_html_file') and self.current_html_file:
                try:
                    if os.path.exists(self.current_html_file):
                        os.remove(self.current_html_file)
                        self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🧹 清理临时文件: {self.current_html_file}')
                except:
                    pass
            
            self.current_html_file = None
            self.last_file_path = None
            self.wgs84_positions = None
            
            self.statusBar().showMessage('数据已清除，系统就绪')
            self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🧹 数据已清除，系统重置')
    
    def set_buttons_enabled(self, enabled):
        """设置按钮状态"""
        # 基本按钮
        self.load_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        
        # 连接相关按钮
        self.connect_btn.setEnabled(True)
        
        # 根据条件启用/禁用其他按钮
        export_enabled = enabled and (self.current_html_file is not None)
        self.export_btn.setEnabled(export_enabled)
        
        view_enabled = enabled and (self.current_html_file is not None)
        self.view_browser_btn.setEnabled(view_enabled)
        
        # 截图管理按钮
        self.refresh_snapshot_btn.setEnabled(True)
        self.delete_snapshot_btn.setEnabled(self.snapshot_list.currentItem() is not None)
        
        # GPS文件管理按钮
        self.refresh_gps_files_btn.setEnabled(True)
        self.view_gps_file_btn.setEnabled(self.gps_file_list.currentItem() is not None)
        self.delete_gps_file_btn.setEnabled(self.gps_file_list.currentItem() is not None)
    
    def closeEvent(self, event):
        """关闭事件"""
        # 清理临时文件
        if hasattr(self, 'current_html_file') and self.current_html_file:
            try:
                if os.path.exists(self.current_html_file):
                    os.remove(self.current_html_file)
                    self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] 🧹 清理临时文件: {self.current_html_file}')
            except:
                pass
        
        # 终止处理线程
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.terminate()
            self.processing_thread.wait()
        
        # 终止GPS保存线程
        if self.gps_saver_thread:
            self.gps_saver_thread.stop()
        
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('GPS轨迹可视化系统')
    app.setApplicationDisplayName('GPS轨迹可视化系统')
    
    # 设置应用程序图标（如果有）
    try:
        app.setWindowIcon(QIcon('icon.png'))
    except:
        pass
    
    # 设置应用程序样式
    app.setStyle('Fusion')
    
    # 设置全局字体
    font = QFont('Microsoft YaHei', 9)
    app.setFont(font)
    
    window = GPSFoliumTracker()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()