# dijkstra_run.py
# coding=utf-8
import re
import cv2
import numpy as np
import urllib.request
import math
import os
import json
from urllib.parse import urlencode
from PIL import Image, ImageDraw, ImageFont
import traceback

def url_to_image(url):
    """从URL下载图片"""
    try:
        print(f"请求地图URL...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'image/webp,image/*,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=15)
        
        image_data = resp.read()
        
        # 检查返回的数据是否是图片
        if len(image_data) < 500:  # 增加最小长度检查
            try:
                error_text = image_data.decode('utf-8', errors='ignore')
                print(f"API可能返回错误: {error_text[:100]}")
                # 如果是JSON格式的错误信息，解析它
                if 'status' in error_text:
                    error_json = json.loads(error_text)
                    if error_json.get('status') == '0':
                        print(f"高德地图API错误: {error_json.get('info')}")
                        return None
            except:
                pass
        
        image = np.asarray(bytearray(image_data), dtype="uint8")
        image = cv2.imdecode(image, cv2.IMREAD_COLOR)
        
        if image is None:
            print("无法解码图像数据")
            return None
            
        print(f"地图下载成功，尺寸: {image.shape}")
        return image
        
    except Exception as e:
        print(f"下载地图失败: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None

def parse_nmea_data(file_path):
    """
    解析NMEA格式的GPS数据文件
    修正解析逻辑，确保正确解析DDMM.MMMM格式
    """
    positions = []
    
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line.startswith('$'):
                continue
            
            # 解析GNRMC数据（推荐的最小数据）
            if 'GNRMC' in line or 'GPRMC' in line:
                parts = line.split(',')
                if len(parts) < 7:
                    continue
                
                try:
                    time_str = parts[1]
                    status = parts[2]
                    
                    if status != 'A':  # 只处理有效数据
                        continue
                    
                    # 解析纬度
                    lat_str = parts[3]
                    lat_dir = parts[4]
                    
                    # 解析经度
                    lon_str = parts[5]
                    lon_dir = parts[6]
                    
                    # 转换DDMM.MMMM格式为十进制度
                    if lat_str and len(lat_str) >= 4:
                        lat_deg = float(lat_str[:2])
                        lat_min = float(lat_str[2:])
                        latitude = lat_deg + lat_min / 60.0
                        if lat_dir == 'S':
                            latitude = -latitude
                    else:
                        continue
                    
                    if lon_str and len(lon_str) >= 5:
                        lon_deg = float(lon_str[:3])
                        lon_min = float(lon_str[3:])
                        longitude = lon_deg + lon_min / 60.0
                        if lon_dir == 'W':
                            longitude = -longitude
                    else:
                        continue
                    
                    positions.append({
                        'timestamp': time_str,
                        'latitude': latitude,
                        'longitude': longitude,
                        'status': status
                    })
                    
                except (ValueError, IndexError) as e:
                    print(f"解析GNRMC数据错误: {e}, 行: {line}")
                    continue
            
            # 解析GNGGA数据（全球定位系统定位数据）
            elif 'GNGGA' in line or 'GPGGA' in line:
                parts = line.split(',')
                if len(parts) < 10:
                    continue
                
                try:
                    time_str = parts[1]
                    
                    # 解析纬度
                    lat_str = parts[2]
                    lat_dir = parts[3]
                    
                    # 解析经度
                    lon_str = parts[4]
                    lon_dir = parts[5]
                    
                    # 定位质量指示器
                    quality = parts[6]
                    if quality == '0':  # 无效定位
                        continue
                    
                    # 转换DDMM.MMMM格式为十进制度
                    if lat_str and len(lat_str) >= 4:
                        lat_deg = float(lat_str[:2])
                        lat_min = float(lat_str[2:])
                        latitude = lat_deg + lat_min / 60.0
                        if lat_dir == 'S':
                            latitude = -latitude
                    else:
                        continue
                    
                    if lon_str and len(lon_str) >= 5:
                        lon_deg = float(lon_str[:3])
                        lon_min = float(lon_str[3:])
                        longitude = lon_deg + lon_min / 60.0
                        if lon_dir == 'W':
                            longitude = -longitude
                    else:
                        continue
                    
                    positions.append({
                        'timestamp': time_str,
                        'latitude': latitude,
                        'longitude': longitude,
                        'quality': quality
                    })
                    
                except (ValueError, IndexError) as e:
                    print(f"解析GNGGA数据错误: {e}, 行: {line}")
                    continue
    
    return positions

def validate_gps_coordinates(locations):
    """
    验证GPS坐标是否在合理范围内
    返回有效的坐标列表
    """
    valid_locations = []
    
    # 中国大致范围
    CHINA_LAT_MIN, CHINA_LAT_MAX = 18.0, 54.0
    CHINA_LON_MIN, CHINA_LON_MAX = 73.0, 136.0
    
    for lon, lat in locations:
        # 检查坐标是否在合理范围内
        if (CHINA_LAT_MIN <= lat <= CHINA_LAT_MAX and 
            CHINA_LON_MIN <= lon <= CHINA_LON_MAX):
            valid_locations.append((lon, lat))
        else:
            print(f"警告: 坐标超出中国范围: {lat:.6f}, {lon:.6f}")
    
    return valid_locations

def create_gaode_map_with_track(locations, center_lat, center_lon):
    """创建带轨迹的高德地图 - 修复版本"""
    try:
        key = "157dd028dc0ff60dc9517c5783dab4a6"
        
        # 检查是否有足够的点
        if len(locations) < 2:
            print("位置点太少，无法生成轨迹")
            return None
        
        # 验证坐标范围
        valid_locations = validate_gps_coordinates(locations)
        if len(valid_locations) < 2:
            print("有效坐标点不足")
            return None
        
        # 重新计算中心点
        lats = [loc[1] for loc in valid_locations]
        lons = [loc[0] for loc in valid_locations]
        center_lat = sum(lats) / len(lats)
        center_lon = sum(lons) / len(lons)
        
        print(f"有效坐标点: {len(valid_locations)}个")
        print(f"调整后的中心点: {center_lon:.6f}, {center_lat:.6f}")
        
        # 构建标记点（起点和终点）- 使用高德地图API推荐格式
        markers = []
        if len(valid_locations) >= 1:
            start_lon, start_lat = valid_locations[0]
            # 格式: mid,0xFF0000,S:经度,纬度
            markers.append(f"mid,0xFF0000,S:{start_lon:.6f},{start_lat:.6f}")
        
        if len(valid_locations) >= 2:
            end_lon, end_lat = valid_locations[-1]
            markers.append(f"mid,0x00FF00,E:{end_lon:.6f},{end_lat:.6f}")
        
        # 构建轨迹线 - 对点进行适当采样
        path_points = []
        max_points = 30  # 进一步减少点数
        
        # 计算点之间的距离，如果点太密集则采样
        if len(valid_locations) > max_points:
            step = max(1, len(valid_locations) // max_points)
            for i in range(0, len(valid_locations), step):
                lon, lat = valid_locations[i]
                path_points.append(f"{lon:.6f},{lat:.6f}")
            
            # 确保包含终点
            if (len(valid_locations) - 1) % step != 0:
                lon, lat = valid_locations[-1]
                path_points.append(f"{lon:.6f},{lat:.6f}")
        else:
            for lon, lat in valid_locations:
                path_points.append(f"{lon:.6f},{lat:.6f}")
        
        # 确保至少有2个点
        if len(path_points) >= 2:
            # 格式: 线宽,颜色,透明度,是否虚线:坐标点1;坐标点2;...
            paths_str = f"3,0x0000FF,0.8,0:{';'.join(path_points)}"
        
        # 构建URL参数 - 简化版本
        markers_str = "|".join(markers) if markers else ""
        
        params = {
            'key': key,
            'location': f"{center_lon:.6f},{center_lat:.6f}",
            'zoom': 16,  # 调整缩放级别
            'size': '800*600',  # 调整大小
            'scale': 1,
        }
        
        # 添加标记点
        if markers_str:
            params['markers'] = markers_str
            print(f"标记点参数: {markers_str[:50]}...")
        
        # 添加轨迹线
        if 'paths_str' in locals():
            params['paths'] = paths_str
            print(f"轨迹线点数: {len(path_points)}")
        
        # 构建URL
        query_string = urlencode(params)
        map_url = f"https://restapi.amap.com/v3/staticmap?{query_string}"
        
        print(f"地图URL长度: {len(map_url)}")
        print(f"地图URL前200字符: {map_url[:200]}...")
        
        # 下载地图
        response = url_to_image(map_url)
        
        if response is None:
            print("标准URL失败，尝试更简单的版本...")
            # 尝试更简单的版本：只显示中心点和标记
            simple_params = {
                'key': key,
                'location': f"{center_lon:.6f},{center_lat:.6f}",
                'zoom': 15,
                'size': '800*600',
                'scale': 1,
                'markers': f"large,0xFF0000,A:{center_lon:.6f},{center_lat:.6f}"
            }
            simple_query = urlencode(simple_params)
            simple_url = f"https://restapi.amap.com/v3/staticmap?{simple_query}"
            print(f"简化URL: {simple_url[:150]}...")
            return url_to_image(simple_url)
        
        return response
        
    except Exception as e:
        print(f"创建轨迹地图失败: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None

def create_osm_map_with_track(locations, center_lat, center_lon):
    """使用OpenStreetMap创建地图"""
    try:
        # OpenStreetMap的静态地图URL（使用静态图API）
        zoom = 15
        
        # 使用StaticMapAPI
        # 构建边界框
        lats = [loc[1] for loc in locations]
        lons = [loc[0] for loc in locations]
        
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)
        
        # 构建路径
        path_points = []
        for lon, lat in locations:
            path_points.append(f"{lat},{lon}")
        
        # 构建URL
        bbox = f"{lon_min},{lat_min},{lon_max},{lat_max}"
        path = f"color:red|weight:3|{'|'.join(path_points[:50])}"  # 限制点数
        
        osm_url = f"https://staticmap.openstreetmap.de/staticmap.php?bbox={bbox}&size=800x600&maptype=mapnik&path={path}"
        
        print(f"尝试OpenStreetMap: {osm_url[:150]}...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        req = urllib.request.Request(osm_url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=10)
        image_data = resp.read()
        
        image = np.asarray(bytearray(image_data), dtype="uint8")
        image = cv2.imdecode(image, cv2.IMREAD_COLOR)
        
        if image is not None:
            # 调整大小
            image = cv2.resize(image, (800, 600))
            print(f"OpenStreetMap获取成功，尺寸: {image.shape}")
            return image
        else:
            print("OpenStreetMap解码失败")
            return None
            
    except Exception as e:
        print(f"OpenStreetMap获取失败: {e}")
        # 尝试备用方案
        return create_simple_map(locations, center_lat, center_lon)

def create_simple_map(locations, center_lat, center_lon):
    """创建简单的地图作为最后备用"""
    try:
        # 创建一个简单的地图背景
        map_img = np.zeros((600, 800, 3), dtype=np.uint8)
        map_img[:] = (230, 240, 250)  # 浅蓝色背景
        
        # 添加网格线
        for i in range(0, 800, 50):
            cv2.line(map_img, (i, 0), (i, 600), (200, 210, 220), 1)
        for i in range(0, 600, 50):
            cv2.line(map_img, (0, i), (800, i), (200, 210, 220), 1)
        
        # 绘制坐标轴
        cv2.line(map_img, (50, 550), (750, 550), (0, 0, 0), 2)  # X轴
        cv2.line(map_img, (50, 50), (50, 550), (0, 0, 0), 2)    # Y轴
        
        # 绘制轨迹
        if len(locations) > 1:
            # 计算边界
            lats = [loc[1] for loc in locations]
            lons = [loc[0] for loc in locations]
            
            lat_min, lat_max = min(lats), max(lats)
            lon_min, lon_max = min(lons), max(lons)
            
            # 添加边距
            lat_range = max(lat_max - lat_min, 0.0001)  # 避免除零
            lon_range = max(lon_max - lon_min, 0.0001)
            
            lat_min -= lat_range * 0.1
            lat_max += lat_range * 0.1
            lon_min -= lon_range * 0.1
            lon_max += lon_range * 0.1
            
            # 绘制轨迹线
            for i in range(1, len(locations)):
                lon1, lat1 = locations[i-1]
                lon2, lat2 = locations[i]
                
                # 映射到图像坐标
                x1 = int((lon1 - lon_min) / (lon_max - lon_min) * 650 + 75)
                y1 = int((lat1 - lat_min) / (lat_max - lat_min) * 450 + 75)
                x2 = int((lon2 - lon_min) / (lon_max - lon_min) * 650 + 75)
                y2 = int((lat2 - lat_min) / (lat_max - lat_min) * 450 + 75)
                
                # 确保坐标在范围内
                x1 = max(75, min(725, x1))
                y1 = max(75, min(525, y1))
                x2 = max(75, min(725, x2))
                y2 = max(75, min(525, y2))
                
                # 绘制线
                cv2.line(map_img, (x1, y1), (x2, y2), (0, 0, 255), 2)
                
                # 绘制点
                cv2.circle(map_img, (x1, y1), 4, (255, 0, 0), -1)
                cv2.circle(map_img, (x2, y2), 4, (255, 0, 0), -1)
        
        # 添加标题
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(map_img, "GPS轨迹图", (300, 30), font, 0.8, (0, 0, 255), 2)
        cv2.putText(map_img, f"中心点: {center_lat:.6f}, {center_lon:.6f}", (50, 570), font, 0.5, (0, 0, 0), 1)
        
        return map_img
        
    except Exception as e:
        print(f"创建简单地图失败: {e}")
        return None

def draw_track_on_actual_map(base_map, positions):
    """在实际地图上绘制轨迹"""
    if base_map is None or len(positions) < 2:
        return base_map
    
    try:
        # 复制地图
        track_map = base_map.copy()
        height, width = track_map.shape[:2]
        
        # 提取坐标
        lats = [p['latitude'] for p in positions]
        lons = [p['longitude'] for p in positions]
        
        # 计算边界
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)
        
        # 添加边距
        lat_range = max(lat_max - lat_min, 0.0001)
        lon_range = max(lon_max - lon_min, 0.0001)
        
        lat_min -= lat_range * 0.2
        lat_max += lat_range * 0.2
        lon_min -= lon_range * 0.2
        lon_max += lon_range * 0.2
        
        # 绘制轨迹线
        for i in range(1, len(positions)):
            lat1, lon1 = positions[i-1]['latitude'], positions[i-1]['longitude']
            lat2, lon2 = positions[i]['latitude'], positions[i]['longitude']
            
            # 映射到图像坐标
            x1 = int((lon1 - lon_min) / (lon_max - lon_min) * (width - 100) + 50)
            y1 = int((lat1 - lat_min) / (lat_max - lat_min) * (height - 100) + 50)
            x2 = int((lon2 - lon_min) / (lon_max - lon_min) * (width - 100) + 50)
            y2 = int((lat2 - lat_min) / (lat_max - lat_min) * (height - 100) + 50)
            
            # 确保坐标在图像范围内
            x1 = max(50, min(width-50, x1))
            y1 = max(50, min(height-50, y1))
            x2 = max(50, min(width-50, x2))
            y2 = max(50, min(height-50, y2))
            
            # 绘制轨迹线
            cv2.line(track_map, (x1, y1), (x2, y2), (0, 0, 255), 3)
            
            # 绘制轨迹点
            if i == 1:  # 起点
                cv2.circle(track_map, (x1, y1), 8, (0, 255, 0), -1)
                cv2.putText(track_map, "S", (x1+5, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            if i == len(positions) - 1:  # 终点
                cv2.circle(track_map, (x2, y2), 8, (0, 165, 255), -1)
                cv2.putText(track_map, "E", (x2+5, y2-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
            else:
                cv2.circle(track_map, (x1, y1), 5, (255, 0, 0), -1)
        
        return track_map
        
    except Exception as e:
        print(f"在地图上绘制轨迹失败: {e}")
        return base_map

def add_info_to_map(image, title, point_info, distance, center_lat, center_lon):
    """在地图上添加信息（支持中文）"""
    if image is None:
        return create_blank_map()
    
    try:
        # 调整图像大小
        if image.shape[0] != 800 or image.shape[1] != 800:
            image = cv2.resize(image, (800, 800))
        
        # 转换为PIL图像用于绘制中文
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(image_rgb)
        
        draw = ImageDraw.Draw(pil_image)
        
        try:
            # 尝试加载中文字体
            font_paths = [
                "simsun.ttc",
                "msyh.ttc",
                "C:/Windows/Fonts/simsun.ttc",
                "C:/Windows/Fonts/msyh.ttc"
            ]
            
            title_font = None
            info_font = None
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        title_font = ImageFont.truetype(font_path, 28, encoding="utf-8")
                        info_font = ImageFont.truetype(font_path, 18, encoding="utf-8")
                        print(f"使用字体: {font_path}")
                        break
                    except:
                        continue
            
            if title_font is None:
                print("未找到中文字体，使用默认字体")
                title_font = ImageFont.load_default()
                info_font = ImageFont.load_default()
                
        except Exception as e:
            print(f"字体加载失败: {e}")
            title_font = ImageFont.load_default()
            info_font = ImageFont.load_default()
        
        # 绘制标题
        draw.text((20, 20), title, fill=(255, 0, 0), font=title_font)
        
        # 绘制GPS点信息
        info_y = 60
        draw.text((20, info_y), f"GPS点数: {point_info}", fill=(0, 0, 0), font=info_font)
        
        # 绘制轨迹长度
        if distance > 0:
            info_y += 35
            if distance < 1000:
                draw.text((20, info_y), f"轨迹长度: {distance:.2f}米", fill=(0, 0, 0), font=info_font)
            else:
                draw.text((20, info_y), f"轨迹长度: {distance/1000:.2f}公里", fill=(0, 0, 0), font=info_font)
        
        # 绘制中心点坐标
        info_y += 35
        draw.text((20, info_y), f"中心点: {center_lat:.6f}, {center_lon:.6f}", fill=(0, 0, 0), font=info_font)
        
        # 添加边框
        draw.rectangle([(10, 10), (790, 790)], outline=(0, 0, 0), width=2)
        
        # 转换回OpenCV格式
        result_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        
        return result_image
        
    except Exception as e:
        print(f"添加信息失败，使用英文显示: {e}")
        # 如果PIL失败，使用原来的英文版本
        return add_info_to_map_english(image, title, point_info, distance, center_lat, center_lon)

def add_info_to_map_english(image, title, point_info, distance, center_lat, center_lon):
    """英文版本的信息添加"""
    if image is None:
        return create_blank_map()
    
    try:
        if image.shape[0] != 800 or image.shape[1] != 800:
            image = cv2.resize(image, (800, 800))
        
        # 添加统计信息到图片
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        # 标题
        cv2.putText(image, title, (20, 40), font, 0.8, (0, 0, 255), 2)
        
        # GPS点信息
        cv2.putText(image, f"GPS Points: {point_info}", (20, 80), font, 0.6, (0, 0, 0), 2)
        
        # 轨迹长度
        if distance > 0:
            if distance < 1000:
                cv2.putText(image, f"Distance: {distance:.2f}m", (20, 110), font, 0.6, (0, 0, 0), 2)
            else:
                cv2.putText(image, f"Distance: {distance/1000:.2f}km", (20, 110), font, 0.6, (0, 0, 0), 2)
        
        # 中心点坐标
        cv2.putText(image, f"Center: {center_lat:.6f}, {center_lon:.6f}", (20, 140), font, 0.6, (0, 0, 0), 2)
        
        # 添加边框
        cv2.rectangle(image, (10, 10), (790, 790), (0, 0, 0), 2)
        
        return image
        
    except Exception as e:
        print(f"添加英文信息失败: {e}")
        return image

def create_blank_map():
    """创建空白地图"""
    blank_map = np.zeros((800, 800, 3), dtype=np.uint8)
    blank_map[:] = (240, 240, 240)  # 浅灰色背景
    
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(blank_map, "GPS轨迹地图", (250, 200), font, 1, (0, 0, 255), 2)
    cv2.putText(blank_map, "地图生成失败", (200, 250), font, 0.7, (255, 0, 0), 2)
    cv2.putText(blank_map, "请检查网络连接和API密钥", (150, 300), font, 0.7, (255, 0, 0), 2)
    
    return blank_map

def check_and_download_font():
    """检查字体文件是否存在"""
    font_paths = [
        "simsun.ttc",
        "msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/msyh.ttc"
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            print(f"找到字体文件: {font_path}")
            return True
    
    print("未找到中文字体文件")
    print("请将simsun.ttc或msyh.ttc字体文件放在当前目录")
    print("或程序将使用英文显示")
    return False

def create_gps_track_map(gps_file_path, output_size=(800, 800)):
    """
    创建GPS轨迹地图 - 增强版本
    """
    print("=" * 50)
    print("开始处理GPS数据...")
    print("=" * 50)
    
    # 1. 解析GPS数据
    print("\n1. 正在解析GPS数据...")
    positions = parse_nmea_data(gps_file_path)
    
    if not positions:
        print("没有找到有效的GPS位置数据")
        blank_map = np.zeros((800, 800, 3), dtype=np.uint8)
        blank_map[:] = (240, 240, 240)
        info_map = add_info_to_map(blank_map, "GPS数据解析", "未找到有效数据", 0, 0, 0)
        return info_map, []
    
    print(f"成功解析 {len(positions)} 个GPS位置点")
    
    # 显示前几个点的数据用于调试
    print("\n前5个GPS点数据:")
    for i, pos in enumerate(positions[:5]):
        print(f"点{i+1}: 时间={pos['timestamp']}, 纬度={pos['latitude']:.8f}, 经度={pos['longitude']:.8f}")
    
    # 2. 提取经纬度坐标
    locations = [(pos['longitude'], pos['latitude']) for pos in positions]
    
    # 3. 计算中心点和轨迹长度
    lats = [pos['latitude'] for pos in positions]
    lons = [pos['longitude'] for pos in positions]
    
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)
    
    print(f"\n轨迹中心点: {center_lat:.8f}, {center_lon:.8f}")
    
    # 计算轨迹总长度（使用Haversine公式）
    total_distance = 0
    for i in range(1, len(positions)):
        lat1, lon1 = positions[i-1]['latitude'], positions[i-1]['longitude']
        lat2, lon2 = positions[i]['latitude'], positions[i]['longitude']
        
        # 使用更精确的距离计算
        R = 6371000  # 地球半径（米）
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = R * c
        
        total_distance += distance
    
    print(f"轨迹总长度: {total_distance:.2f}米")
    
    # 4. 尝试使用高德地图API
    print("\n2. 正在尝试从高德地图获取地图...")
    track_map = create_gaode_map_with_track(locations, center_lat, center_lon)
    
    if track_map is not None:
        print("高德地图获取成功")
        # 在高德地图上绘制轨迹
        final_map = draw_track_on_actual_map(track_map, positions)
    else:
        print("高德地图获取失败，尝试OpenStreetMap...")
        # 使用OpenStreetMap作为备选
        track_map = create_osm_map_with_track(locations, center_lat, center_lon)
        
        if track_map is not None:
            print("OpenStreetMap获取成功")
            final_map = draw_track_on_actual_map(track_map, positions)
        else:
            print("所有在线地图获取失败，使用本地绘图...")
            # 使用本地绘图
            final_map = create_simple_map(locations, center_lat, center_lon)
    
    # 5. 添加信息
    if final_map is not None:
        final_map = add_info_to_map(final_map, "GPS轨迹地图", 
                                  f"{len(positions)}个点", 
                                  total_distance, center_lat, center_lon)
    else:
        print("地图生成完全失败")
        final_map = create_blank_map()
    
    return final_map, positions

def gps_track_planning(gps_file_path):
    """
    GPS轨迹规划主函数
    """
    if not os.path.exists(gps_file_path):
        print(f"错误: 文件不存在: {gps_file_path}")
        return None, []
    
    # 检查字体文件
    check_and_download_font()
    
    print(f"\n正在处理GPS数据文件: {os.path.basename(gps_file_path)}")
    img, positions = create_gps_track_map(gps_file_path)
    
    if img is not None:
        # 计算实际轨迹长度
        if len(positions) >= 2:
            total_dist = 0
            for i in range(1, len(positions)):
                lat1, lon1 = positions[i-1]['latitude'], positions[i-1]['longitude']
                lat2, lon2 = positions[i]['latitude'], positions[i]['longitude']
                
                R = 6371000
                lat1_rad = math.radians(lat1)
                lat2_rad = math.radians(lat2)
                delta_lat = math.radians(lat2 - lat1)
                delta_lon = math.radians(lon2 - lon1)
                
                a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                distance = R * c
                total_dist += distance
            
            result_text = f"GPS轨迹已生成，共{len(positions)}个GPS点，总长度{total_dist:.2f}米"
        else:
            result_text = f"GPS轨迹已生成，共{len(positions)}个GPS点"
        
        return img, [result_text]
    
    return None, []

if __name__ == "__main__":
    # 测试代码
    gps_file = "COM9_20260119_0926278.txt"
    
    if os.path.exists(gps_file):
        print("开始测试GPS轨迹生成...")
        img, result = gps_track_planning(gps_file)
        if img is not None:
            cv2.imshow("GPS轨迹地图", img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
            
            save_path = "gps_track_result.jpg"
            cv2.imwrite(save_path, img)
            print(f"结果已保存到: {save_path}")
            
            if result:
                print(f"处理结果: {result[0]}")
    else:
        print(f"请将GPS数据文件 {gps_file} 放在当前目录下")