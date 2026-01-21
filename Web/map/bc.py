# [file name]: bc.py
import cv2
import socket
import threading
import time
import os
import queue
import numpy as np
from datetime import datetime
import json
import subprocess
import platform

# ========== 配置参数 ==========
ESP32_IP = "192.168.4.1"  # ESP32热点IP
ESP32_PORT = 8888  # ESP32数据端口
VIDEO_URL = f"http://{ESP32_IP}:81/stream"  # 视频流URL

# 保存目录
SAVE_DIR = "./captured_data"
GPS_DATA_FILE = f"{SAVE_DIR}/gps_log.txt"
FACE_DATA_FILE = f"{SAVE_DIR}/face_log.txt"
SYNC_DATA_FILE = f"{SAVE_DIR}/sync_data.json"

# 创建保存目录
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

print(f"数据保存目录: {os.path.abspath(SAVE_DIR)}")

# ========== 数据队列 ==========
gps_data_queue = queue.Queue()
face_data_queue = queue.Queue()
frame_queue = queue.Queue(maxsize=10)  # 限制队列大小避免内存溢出
raw_data_queue = queue.Queue()

# ========== 全局状态变量 ==========
running = True
socket_connected = False
video_stream_available = False
last_gps_time = None
last_face_time = None

# ========== 网络测试函数 ==========
def test_network_connection():
    """测试网络连接"""
    print("\n=== 网络连接测试 ===")
    
    # 测试是否能ping通ESP32
    print("1. 测试Ping ESP32...")
    try:
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        result = subprocess.run(['ping', param, '1', ESP32_IP], 
                               capture_output=True, text=True, timeout=5)
        if "TTL" in result.stdout or "time" in result.stdout:
            print(f"✅ Ping {ESP32_IP} 成功")
            return True
        else:
            print(f"❌ Ping {ESP32_IP} 失败")
            return False
    except:
        print(f"❌ Ping {ESP32_IP} 超时")
        return False

def test_port_connection():
    """测试端口连接"""
    print("2. 测试TCP端口...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((ESP32_IP, ESP32_PORT))
        sock.close()
        print(f"✅ 端口 {ESP32_PORT} 连接成功")
        return True
    except Exception as e:
        print(f"❌ 端口 {ESP32_PORT} 连接失败: {e}")
        return False

def test_http_stream():
    """测试HTTP视频流"""
    print("3. 测试HTTP视频流...")
    try:
        import urllib.request
        req = urllib.request.Request(f"{VIDEO_URL}", headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=5)
        if response.getcode() == 200:
            print(f"✅ 视频流连接成功")
            return True
        else:
            print(f"❌ 视频流返回状态码: {response.getcode()}")
            return False
    except Exception as e:
        print(f"❌ 视频流连接失败: {e}")
        return False

def check_wifi_connection():
    """检查WiFi连接状态"""
    print("\n=== WiFi连接检查 ===")
    try:
        import netifaces
        interfaces = netifaces.interfaces()
        for iface in interfaces:
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr.get('addr', '')
                    if ip.startswith('192.168.4.'):
                        print(f"✅ 已连接到ESP32网络，IP: {ip}")
                        return True
        print("❌ 未检测到ESP32网络连接")
        print("请执行以下步骤：")
        print("1. 确保ESP32已启动")
        print("2. 电脑连接到WiFi热点: ESP32_WIFI_TEST")
        print("3. 密码: (空)")
        return False
    except ImportError:
        print("⚠ 无法自动检测网络，请手动检查")
        return True  # 跳过网络检测

# ========== WiFi连接函数 ==========
def connect_to_esp32():
    """连接到ESP32 WiFi模块"""
    global socket_connected
    
    # 先检查WiFi连接
    if not check_wifi_connection():
        return None
    
    # 测试网络连接
    if not test_network_connection():
        print("⚠ 网络测试失败，但仍尝试连接...")
    
    max_retries = 10  # 增加重试次数
    for i in range(max_retries):
        try:
            print(f"尝试连接ESP32 ({i+1}/{max_retries})...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((ESP32_IP, ESP32_PORT))
            sock.settimeout(2)  # 设置较小的超时时间
            
            # 发送连接测试命令
            test_commands = [
                b"AT\r\n",
                b"AT+GMR\r\n",
                b"AT+CWMODE?\r\n"
            ]
            
            for cmd in test_commands:
                try:
                    sock.send(cmd)
                    time.sleep(0.1)
                    response = sock.recv(1024)
                    if response:
                        print(f"收到响应: {response[:50]}...")
                except:
                    pass
            
            print(f"✅ 成功连接到ESP32: {ESP32_IP}:{ESP32_PORT}")
            socket_connected = True
            return sock
                
        except socket.timeout:
            print(f"连接超时 ({i+1}/{max_retries})")
            time.sleep(2)
        except ConnectionRefusedError:
            print(f"连接被拒绝 ({i+1}/{max_retries})，检查ESP32是否启动")
            time.sleep(2)
        except Exception as e:
            print(f"连接失败 ({i+1}/{max_retries}): {e}")
            time.sleep(2)
    
    print("❌ 无法连接到ESP32")
    print("建议：")
    print("1. 重启ESP32")
    print("2. 检查Arduino代码是否正确上传")
    print("3. 确保ESP32热点已开启")
    print("4. 尝试关闭防火墙或杀毒软件")
    socket_connected = False
    return None

# ========== 视频流连接函数 ==========
def connect_video_stream():
    """连接视频流"""
    global video_stream_available
    
    max_retries = 5
    for i in range(max_retries):
        try:
            print(f"尝试连接视频流 ({i+1}/{max_retries})...")
            cap = cv2.VideoCapture(VIDEO_URL)
            
            # 设置超时
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # 尝试读取一帧
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    print("✅ 视频流连接成功")
                    print(f"  帧大小: {frame.shape}")
                    video_stream_available = True
                    return cap
                else:
                    print("⚠ 视频流打开但无法读取帧")
                    cap.release()
            else:
                print("❌ 无法打开视频流")
                    
        except Exception as e:
            print(f"视频流连接失败 ({i+1}/{max_retries}): {e}")
    
    print("⚠ 视频流连接失败，将继续尝试接收GPS和人脸数据")
    video_stream_available = False
    return None

# ========== WiFi数据接收线程 ==========
def wifi_receiver_thread(sock):
    """接收WiFi数据的线程"""
    global running, socket_connected
    
    buffer = ""
    empty_counter = 0  # 空数据计数器
    
    # 发送启动命令
    try:
        startup_commands = [
            b"AT\r\n",
            b"AT+CIPMUX=1\r\n",
            b"AT+CIPSERVER=1,8888\r\n"
        ]
        
        for cmd in startup_commands:
            sock.send(cmd)
            time.sleep(0.5)
            response = sock.recv(1024)
            if response:
                print(f"启动命令响应: {response[:100]}")
    except:
        pass
    
    while running and socket_connected:
        try:
            # 接收数据
            data = sock.recv(1024)
            if not data:
                empty_counter += 1
                if empty_counter > 10:  # 连续10次空数据
                    print("WiFi连接无数据，可能已断开")
                    socket_connected = False
                    break
                time.sleep(0.1)
                continue
            
            empty_counter = 0  # 重置计数器
            
            # 解码数据
            decoded_data = data.decode('utf-8', errors='ignore')
            buffer += decoded_data
            
            # 输出原始数据（调试用）
            if len(decoded_data.strip()) > 0:
                print(f"收到原始数据: {decoded_data[:100]}...")
            
            # 处理完整的数据包（以换行符或#结束）
            while buffer and ('\n' in buffer or '#' in buffer):
                # 先查找换行符
                if '\n' in buffer:
                    line_end = buffer.find('\n')
                    packet = buffer[:line_end].strip()
                    buffer = buffer[line_end + 1:]
                # 再查找#作为分隔符
                elif '#' in buffer:
                    hash_end = buffer.find('#')
                    packet = buffer[:hash_end].strip()
                    buffer = buffer[hash_end + 1:]
                    packet += '#'
                else:
                    break
                
                if packet:
                    print(f"处理数据包: {packet[:80]}...")
                    
                    # 保存原始数据
                    timestamp = datetime.now()
                    raw_data_queue.put({
                        'data': packet,
                        'timestamp': timestamp
                    })
                    
                    # 解析数据类型
                    parse_data_packet(packet, timestamp)
                    
        except socket.timeout:
            # 正常超时，继续循环
            continue
        except Exception as e:
            print(f"WiFi接收错误: {e}")
            socket_connected = False
            break
    
    # 清理连接
    if sock:
        try:
            sock.close()
        except:
            pass
    print("WiFi接收线程结束")

# ========== 数据包解析函数 ==========
def parse_data_packet(packet, timestamp):
    """解析接收到的数据包"""
    
    # 保存原始数据到文件
    try:
        with open(f"{SAVE_DIR}/raw_data.log", "a", encoding='utf-8') as f:
            f.write(f"[{timestamp.strftime('%H:%M:%S.%f')[:-3]}] {packet}\n")
    except:
        pass
    
    # 解析GPS数据
    if packet.startswith("$GPS,"):
        parse_gps_data(packet, timestamp)
    
    # 解析人脸数据
    elif packet.startswith("$FACE,"):
        parse_face_data(packet, timestamp)
    
    # 解析串口调试信息
    elif packet.startswith("GPS:") or packet.startswith("检测到人脸") or packet.startswith("发送"):
        print(f"📢 {packet}")
    
    # 其他数据
    elif packet.startswith("$"):
        print(f"📦 收到未知数据包: {packet[:50]}...")

# ========== GPS数据解析函数 ==========
def parse_gps_data(packet, timestamp):
    """解析GPS数据"""
    try:
        # 移除$和#，分割字段
        clean_packet = packet.strip('$#')
        parts = clean_packet.split(',')
        
        if len(parts) < 8:
            print(f"GPS数据字段不足: {parts}")
            return
        
        gps_info = {
            'type': 'gps',
            'timestamp': timestamp,
            'raw': packet,
            'utc_time': parts[1] if len(parts) > 1 else '',
            'latitude': parts[2] if len(parts) > 2 else '',
            'ns_indicator': parts[3] if len(parts) > 3 else '',
            'longitude': parts[4] if len(parts) > 4 else '',
            'ew_indicator': parts[5] if len(parts) > 5 else '',
            'speed': float(parts[6]) if len(parts) > 6 and parts[6] else 0.0,
            'course': float(parts[7]) if len(parts) > 7 and parts[7] else 0.0,
            'is_valid': parts[1] != 'NO_SIGNAL'
        }
        
        # 添加到队列
        gps_data_queue.put(gps_info)
        
        # 输出到控制台
        if gps_info['is_valid']:
            print(f"📍 GPS数据: 时间={gps_info['utc_time']}, "
                  f"纬度={gps_info['latitude']}{gps_info['ns_indicator']}, "
                  f"经度={gps_info['longitude']}{gps_info['ew_indicator']}, "
                  f"速度={gps_info['speed']}节, "
                  f"航向={gps_info['course']}度")
        else:
            print(f"📍 GPS: 无信号")
            
        # 保存到文件
        save_gps_to_file(gps_info)
        
    except Exception as e:
        print(f"GPS解析错误: {e}, 数据包: {packet}")

# ========== 人脸数据解析函数 ==========
def parse_face_data(packet, timestamp):
    """解析人脸数据"""
    try:
        # 移除$和#，分割字段
        clean_packet = packet.strip('$#')
        parts = clean_packet.split(',')
        
        if len(parts) < 4:
            print(f"人脸数据字段不足: {parts}")
            return
        
        face_info = {
            'type': 'face',
            'timestamp': timestamp,
            'raw': packet,
            'center_x': int(parts[1]) if len(parts) > 1 and parts[1] else 0,
            'center_y': int(parts[2]) if len(parts) > 2 and parts[2] else 0,
            'face_id': int(parts[3]) if len(parts) > 3 and parts[3] else 0
        }
        
        # 添加到队列
        face_data_queue.put(face_info)
        
        # 输出到控制台
        print(f"👤 人脸检测: 位置({face_info['center_x']}, {face_info['center_y']}), "
              f"ID: {face_info['face_id']}")
        
        # 保存到文件
        save_face_to_file(face_info)
        
    except Exception as e:
        print(f"人脸数据解析错误: {e}, 数据包: {packet}")

# ========== 视频流读取线程 ==========
def video_stream_thread(cap):
    """读取视频流的线程"""
    global running, video_stream_available
    
    frame_counter = 0
    error_counter = 0
    
    while running and video_stream_available:
        try:
            ret, frame = cap.read()
            if ret and frame is not None:
                error_counter = 0  # 重置错误计数器
                
                # 限制帧率，避免队列溢出
                frame_counter += 1
                if frame_counter % 3 == 0:  # 大约10fps
                    try:
                        frame_queue.put_nowait({
                            'frame': frame.copy(),
                            'timestamp': datetime.now(),
                            'frame_id': frame_counter
                        })
                    except queue.Full:
                        # 队列已满，丢弃最旧的帧
                        try:
                            frame_queue.get_nowait()
                            frame_queue.put_nowait({
                                'frame': frame.copy(),
                                'timestamp': datetime.now(),
                                'frame_id': frame_counter
                            })
                        except:
                            pass
            else:
                error_counter += 1
                if error_counter > 5:  # 连续5次读取失败
                    print("视频流读取失败多次，停止视频流")
                    video_stream_available = False
                    break
                    
        except Exception as e:
            print(f"视频流错误: {e}")
            video_stream_available = False
            break
    
    # 清理
    if cap:
        cap.release()
    print("视频流线程结束")

# ========== 数据保存函数 ==========
def save_gps_to_file(gps_info):
    """保存GPS数据到文件"""
    try:
        with open(GPS_DATA_FILE, "a", encoding='utf-8') as f:
            timestamp = gps_info['timestamp'].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            f.write(f"时间: {timestamp}\n")
            f.write(f"原始数据: {gps_info['raw']}\n")
            
            if gps_info['is_valid']:
                f.write(f"UTC时间: {gps_info['utc_time']}\n")
                f.write(f"纬度: {gps_info['latitude']} {gps_info['ns_indicator']}\n")
                f.write(f"经度: {gps_info['longitude']} {gps_info['ew_indicator']}\n")
                f.write(f"速度: {gps_info['speed']:.1f} 节\n")
                f.write(f"航向: {gps_info['course']:.1f} 度\n")
            else:
                f.write("状态: 无GPS信号\n")
            
            f.write("-" * 50 + "\n")
            
    except Exception as e:
        print(f"保存GPS数据失败: {e}")

def save_face_to_file(face_info):
    """保存人脸数据到文件"""
    try:
        with open(FACE_DATA_FILE, "a", encoding='utf-8') as f:
            timestamp = face_info['timestamp'].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            f.write(f"时间: {timestamp}\n")
            f.write(f"原始数据: {face_info['raw']}\n")
            f.write(f"中心X: {face_info['center_x']}\n")
            f.write(f"中心Y: {face_info['center_y']}\n")
            f.write(f"人脸ID: {face_info['face_id']}\n")
            f.write("-" * 50 + "\n")
            
    except Exception as e:
        print(f"保存人脸数据失败: {e}")

def save_sync_data(gps_info, face_info, frame_info):
    """保存同步数据（GPS+人脸+帧）"""
    try:
        sync_data = {
            'timestamp': datetime.now().isoformat(),
            'gps': gps_info if gps_info else None,
            'face': face_info if face_info else None,
            'frame_id': frame_info['frame_id'] if frame_info else None,
            'image_file': None
        }
        
        # 如果有关联的帧，保存图片
        if frame_info:
            frame = frame_info['frame']
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            image_file = f"{SAVE_DIR}/frame_{timestamp_str}.jpg"
            
            # 在图片上添加标注
            annotated_frame = frame.copy()
            
            # 添加时间戳
            cv2.putText(annotated_frame, timestamp_str, 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            
            # 添加GPS信息
            if gps_info and gps_info['is_valid']:
                gps_text = f"GPS: {gps_info['latitude']}{gps_info['ns_indicator']}, {gps_info['longitude']}{gps_info['ew_indicator']}"
                cv2.putText(annotated_frame, gps_text, 
                           (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            
            # 添加人脸信息
            if face_info:
                face_text = f"Face: ({face_info['center_x']}, {face_info['center_y']}) ID:{face_info['face_id']}"
                cv2.putText(annotated_frame, face_text, 
                           (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 100, 255), 1)
            
            # 保存图片
            cv2.imwrite(image_file, annotated_frame)
            sync_data['image_file'] = image_file
        
        # 保存到JSON文件
        with open(SYNC_DATA_FILE, "a", encoding='utf-8') as f:
            f.write(json.dumps(sync_data, default=str) + "\n")
            
    except Exception as e:
        print(f"保存同步数据失败: {e}")

# ========== 主显示循环 ==========
def main_display_loop():
    """主显示循环"""
    global running, socket_connected, video_stream_available
    
    print("启动主显示循环...")
    frame_counter = 0
    last_sync_time = time.time()
    connection_check_time = time.time()
    
    # 最新数据缓存
    latest_gps = None
    latest_face = None
    latest_frame = None
    
    while running:
        current_time = time.time()
        
        # 定期检查连接状态（每5秒）
        if current_time - connection_check_time > 5:
            if not socket_connected:
                print("尝试重新连接...")
                # 这里可以添加重新连接逻辑
            connection_check_time = current_time
        
        # 获取最新GPS数据
        try:
            while not gps_data_queue.empty():
                latest_gps = gps_data_queue.get_nowait()
        except queue.Empty:
            pass
        
        # 获取最新人脸数据
        try:
            while not face_data_queue.empty():
                latest_face = face_data_queue.get_nowait()
        except queue.Empty:
            pass
        
        # 获取最新帧
        try:
            latest_frame = frame_queue.get_nowait()
            frame_counter += 1
        except queue.Empty:
            latest_frame = None
        
        # 显示帧
        display_frame = None
        if latest_frame:
            display_frame = latest_frame['frame'].copy()
        else:
            # 创建空白帧用于显示
            display_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            display_frame[:] = (30, 30, 30)  # 深灰色背景
        
        # 添加状态信息
        status_y = 30
        line_height = 25
        
        # 系统状态
        cv2.putText(display_frame, f"WiFi状态: {'已连接' if socket_connected else '断开'}", 
                   (10, status_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 
                   (0, 255, 0) if socket_connected else (0, 0, 255), 1)
        
        # 视频状态
        video_status = "已连接" if video_stream_available else "断开"
        cv2.putText(display_frame, f"视频状态: {video_status}", 
                   (10, status_y + line_height), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                   (0, 255, 0) if video_stream_available else (0, 0, 255), 1)
        
        # GPS信息
        if latest_gps and latest_gps['is_valid']:
            gps_text = f"GPS: {latest_gps['latitude']}{latest_gps['ns_indicator']}, {latest_gps['longitude']}{latest_gps['ew_indicator']}"
            cv2.putText(display_frame, gps_text, 
                       (10, status_y + line_height * 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 
                       (255, 255, 0), 1)
        else:
            cv2.putText(display_frame, "GPS: 等待信号...", 
                       (10, status_y + line_height * 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 
                       (100, 100, 255), 1)
        
        # 人脸信息
        if latest_face:
            face_text = f"人脸: ({latest_face['center_x']}, {latest_face['center_y']}) ID:{latest_face['face_id']}"
            cv2.putText(display_frame, face_text, 
                       (10, status_y + line_height * 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 
                       (255, 100, 255), 1)
        else:
            cv2.putText(display_frame, "人脸: 未检测到", 
                       (10, status_y + line_height * 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 
                       (200, 200, 200), 1)
        
        # 帧计数
        cv2.putText(display_frame, f"帧数: {frame_counter}", 
                   (10, status_y + line_height * 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 
                   (255, 255, 255), 1)
        
        # 时间
        time_text = f"时间: {datetime.now().strftime('%H:%M:%S')}"
        cv2.putText(display_frame, time_text, 
                   (10, status_y + line_height * 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 
                   (200, 200, 0), 1)
        
        # 连接提示
        if not socket_connected:
            cv2.putText(display_frame, "⚠ 请检查ESP32连接和Arduino代码", 
                       (10, status_y + line_height * 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 
                       (0, 255, 255), 1)
        
        # 显示窗口
        cv2.imshow('ESP32摄像头+GPS监控系统 (按q退出)', display_frame)
        
        # 每2秒保存一次同步数据
        if current_time - last_sync_time > 2.0:
            if latest_frame:
                save_sync_data(latest_gps, latest_face, latest_frame)
                last_sync_time = current_time
        
        # 按键处理
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("用户请求退出")
            running = False
            break
        elif key == ord('s'):
            # 手动保存当前状态
            print("手动保存当前状态...")
            if latest_frame:
                save_sync_data(latest_gps, latest_face, latest_frame)
        elif key == ord('r'):
            # 重新连接
            print("重新连接...")
            # 这里可以添加重新连接逻辑
        elif key == ord('t'):
            # 测试连接
            print("执行网络测试...")
            test_network_connection()
            test_port_connection()
            test_http_stream()
        
        # 控制循环频率
        time.sleep(0.01)

# ========== 主函数 ==========
def main():
    global running, socket_connected, video_stream_available
    
    print("=" * 60)
    print("ESP32摄像头+GPS监控系统")
    print(f"目标设备: {ESP32_IP}:{ESP32_PORT}")
    print(f"视频流: {VIDEO_URL}")
    print(f"数据保存到: {SAVE_DIR}")
    print("=" * 60)
    
    # 执行网络测试
    test_network_connection()
    test_port_connection()
    test_http_stream()
    
    print("\n=== 开始连接ESP32 ===")
    
    # 连接WiFi
    sock = connect_to_esp32()
    if not sock:
        print("WiFi连接失败，是否继续？")
        response = input("继续使用仅显示模式？(y/n): ")
        if response.lower() != 'y':
            print("退出程序")
            return
        else:
            socket_connected = False
    
    # 连接视频流
    cap = connect_video_stream()
    
    # 启动WiFi接收线程
    if socket_connected:
        wifi_thread = threading.Thread(target=wifi_receiver_thread, args=(sock,), daemon=True)
        wifi_thread.start()
    else:
        print("⚠ WiFi连接失败，仅显示模式")
    
    # 启动视频流线程
    if cap:
        video_thread = threading.Thread(target=video_stream_thread, args=(cap,), daemon=True)
        video_thread.start()
    else:
        print("⚠ 视频流连接失败，仅数据模式")
    
    # 主显示循环
    try:
        main_display_loop()
    except KeyboardInterrupt:
        print("\n程序被中断")
    except Exception as e:
        print(f"程序错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理
        running = False
        
        if sock:
            try:
                sock.close()
            except:
                pass
        
        if cap:
            cap.release()
        
        cv2.destroyAllWindows()
        
        # 保存总结
        save_summary()
        
        print("\n程序已退出")

def save_summary():
    """保存运行总结"""
    try:
        summary_file = f"{SAVE_DIR}/session_summary.txt"
        with open(summary_file, "w", encoding='utf-8') as f:
            f.write("=== 监控会话总结 ===\n")
            f.write(f"开始时间: 未知\n")
            f.write(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"WiFi连接: {'成功' if socket_connected else '失败'}\n")
            f.write(f"视频连接: {'成功' if video_stream_available else '失败'}\n")
            f.write(f"数据目录: {os.path.abspath(SAVE_DIR)}\n")
            f.write(f"GPS数据文件: {GPS_DATA_FILE}\n")
            f.write(f"人脸数据文件: {FACE_DATA_FILE}\n")
            f.write(f"同步数据文件: {SYNC_DATA_FILE}\n")
            f.write("=" * 40 + "\n")
        print(f"会话总结已保存到: {summary_file}")
    except Exception as e:
        print(f"保存总结失败: {e}")

if __name__ == "__main__":
    main()