import requests
import cv2
import numpy as np
import time
import os
from datetime import datetime
import json
from threading import Thread, Lock
from pathlib import Path

class ESP32FaceCatMonitor:
    def __init__(self, esp32_ip="192.168.4.1"):
        """
        初始化监控器
        
        Args:
            esp32_ip: ESP32的IP地址，默认为192.168.4.1
        """
        self.esp32_ip = esp32_ip
        self.stream_url = f"http://{esp32_ip}/stream"
        self.gps_json_url = f"http://{esp32_ip}/gps/json"
        self.status_url = f"http://{esp32_ip}/status"
        self.base_save_dir = "detections"
        
        # 创建保存目录
        self.create_directories()
        
        # 初始化人脸检测器
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        
        # 尝试加载猫脸检测器
        self.cat_detector_available = False
        self.setup_cat_detector()
        
        # 检测状态管理
        self.last_detection_time = 0
        self.detection_cooldown = 3  # 3秒冷却时间
        self.detection_lock = Lock()
        
        # 帧处理参数
        self.frame_skip = 3  # 每3帧处理1帧
        self.frame_count = 0
        
        # 监控状态
        self.is_monitoring = False
        self.current_gps = {"valid": False}
        
    def create_directories(self):
        """创建保存目录结构"""
        directories = [
            self.base_save_dir,
            f"{self.base_save_dir}/faces",
            f"{self.base_save_dir}/cats",
            f"{self.base_save_dir}/both",
            f"{self.base_save_dir}/logs"
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
            
    def setup_cat_detector(self):
        """
        设置猫脸检测器
        这里使用一个简化的方法检测较小的物体
        """
        try:
            # 尝试加载haarcascade_frontalface_default.xml作为基础检测器
            # 通过调整参数来检测较小的物体
            self.cat_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            self.cat_detector_available = True
            print("✅ 猫脸检测器初始化完成（简化版）")
        except Exception as e:
            print(f"⚠️  猫脸检测器初始化失败: {e}")
            print("将仅使用人脸检测功能")
            self.cat_detector_available = False
    
    def update_gps_data(self):
        """持续更新GPS数据"""
        while self.is_monitoring:
            try:
                response = requests.get(self.gps_json_url, timeout=2)
                if response.status_code == 200:
                    gps_data = response.json()
                    if gps_data.get("valid", False):
                        self.current_gps = gps_data
                    else:
                        self.current_gps = {"valid": False, "error": "No GPS fix"}
                else:
                    self.current_gps = {"valid": False, "error": f"HTTP {response.status_code}"}
            except Exception as e:
                self.current_gps = {"valid": False, "error": str(e)}
            
            time.sleep(1)
    
    def detect_faces(self, frame):
        """检测人脸"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        return faces
    
    def detect_cats(self, frame):
        """检测猫脸（简化版）"""
        if not self.cat_detector_available:
            return []
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # 使用不同的参数检测可能更小的物体
        cats = self.cat_cascade.detectMultiScale(
            gray,
            scaleFactor=1.05,  # 更小的缩放因子
            minNeighbors=3,    # 更少的邻居数
            minSize=(15, 15),  # 更小的最小尺寸
            maxSize=(80, 80),  # 限制最大尺寸
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        
        # 过滤掉太大的检测框（可能是人脸）
        filtered_cats = []
        for (x, y, w, h) in cats:
            if w < 80 and h < 80:  # 猫脸通常比人脸小
                filtered_cats.append((x, y, w, h))
        
        return filtered_cats
    
    def save_detection(self, frame, detection_type, faces=None, cats=None):
        """
        保存检测结果
        
        Args:
            frame: 图像帧
            detection_type: 检测类型 ('face', 'cat', 'both')
            faces: 人脸位置列表
            cats: 猫脸位置列表
        """
        with self.detection_lock:
            current_time = time.time()
            
            # 检查冷却时间
            if current_time - self.last_detection_time < self.detection_cooldown:
                return False
            
            # 获取当前时间戳
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            date_str = datetime.now().strftime("%Y-%m-%d")
            time_str = datetime.now().strftime("%H:%M:%S")
            
            # 确定保存目录和文件名
            if detection_type == "face":
                save_dir = f"{self.base_save_dir}/faces/{date_str}"
            elif detection_type == "cat":
                save_dir = f"{self.base_save_dir}/cats/{date_str}"
            else:  # both
                save_dir = f"{self.base_save_dir}/both/{date_str}"
            
            Path(save_dir).mkdir(parents=True, exist_ok=True)
            
            # 绘制检测框
            marked_frame = frame.copy()
            
            if faces is not None and len(faces) > 0:
                for (x, y, w, h) in faces:
                    cv2.rectangle(marked_frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    cv2.putText(marked_frame, 'Face', (x, y-10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            if cats is not None and len(cats) > 0:
                for (x, y, w, h) in cats:
                    cv2.rectangle(marked_frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                    cv2.putText(marked_frame, 'Cat', (x, y-10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            
            # 添加时间戳
            cv2.putText(marked_frame, time_str, (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # 添加GPS信息
            if self.current_gps.get("valid", False):
                gps_text = f"Lat:{self.current_gps.get('lat', 'N/A')} Lon:{self.current_gps.get('lon', 'N/A')}"
                cv2.putText(marked_frame, gps_text, (10, 60), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # 保存图像
            image_path = f"{save_dir}/{timestamp}.jpg"
            cv2.imwrite(image_path, marked_frame)
            
            # 准备数据用于JSON保存
            faces_list = faces.tolist() if hasattr(faces, 'tolist') else faces
            cats_list = cats.tolist() if hasattr(cats, 'tolist') else cats
            
            # 保存JSON元数据
            metadata = {
                "timestamp": timestamp,
                "date": date_str,
                "time": time_str,
                "detection_type": detection_type,
                "faces_count": len(faces) if faces else 0,
                "cats_count": len(cats) if cats else 0,
                "image_path": image_path,
                "gps_data": self.current_gps,
                "faces_positions": faces_list if faces_list is not None else [],
                "cats_positions": cats_list if cats_list is not None else []
            }
            
            metadata_path = f"{save_dir}/{timestamp}.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            # 更新日志文件
            log_entry = {
                "timestamp": timestamp,
                "date": date_str,
                "time": time_str,
                "type": detection_type,
                "faces": len(faces) if faces else 0,
                "cats": len(cats) if cats else 0,
                "gps_valid": self.current_gps.get("valid", False),
                "latitude": self.current_gps.get("lat", None),
                "longitude": self.current_gps.get("lon", None),
                "image": image_path,
                "metadata": metadata_path
            }
            
            log_file = f"{self.base_save_dir}/logs/detections_{date_str}.json"
            log_data = []
            
            if os.path.exists(log_file):
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        log_data = json.load(f)
                except:
                    log_data = []
            
            log_data.append(log_entry)
            
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
            
            # 打印信息
            print(f"[{time_str}] 检测到 {detection_type}!")
            print(f"  人脸: {len(faces) if faces else 0}个, 猫脸: {len(cats) if cats else 0}个")
            print(f"  保存到: {image_path}")
            
            if self.current_gps.get("valid", False):
                lat = self.current_gps.get('lat', 'N/A')
                lon = self.current_gps.get('lon', 'N/A')
                sats = self.current_gps.get('satellites', 0)
                print(f"  位置: 纬度 {lat}°, 经度 {lon}°, 卫星: {sats}颗")
            
            print("-" * 40)
            
            self.last_detection_time = current_time
            return True
    
    def process_frame(self, frame):
        """处理单帧图像"""
        self.frame_count += 1
        
        # 跳过一些帧以提高性能
        if self.frame_count % self.frame_skip != 0:
            return
        
        try:
            # 检测人脸
            faces = self.detect_faces(frame)
            
            # 检测猫脸
            cats = self.detect_cats(frame)
            
            # 根据检测结果进行处理
            has_faces = len(faces) > 0
            has_cats = len(cats) > 0
            
            if has_faces and has_cats:
                # 同时检测到人脸和猫脸
                self.save_detection(frame, "both", faces, cats)
            elif has_faces:
                # 只检测到人脸
                self.save_detection(frame, "face", faces, None)
            elif has_cats:
                # 只检测到猫脸
                self.save_detection(frame, "cat", None, cats)
                
        except Exception as e:
            print(f"处理帧时出错: {e}")
    
    def monitor_stream(self):
        """尝试使用OpenCV直接读取视频流"""
        print("正在尝试使用OpenCV连接视频流...")
        
        self.is_monitoring = True
        gps_thread = Thread(target=self.update_gps_data, daemon=True)
        gps_thread.start()
        
        try:
            # 设置OpenCV参数以提高连接稳定性
            stream = cv2.VideoCapture(self.stream_url)
            stream.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 减少缓冲区
            
            if not stream.isOpened():
                print("无法打开视频流")
                return False
            
            print("✅ OpenCV连接成功，开始监控...")
            print("按 'q' 键退出监控")
            
            while self.is_monitoring:
                ret, frame = stream.read()
                
                if not ret:
                    print("无法获取帧，尝试重新连接...")
                    time.sleep(1)
                    stream.release()
                    stream = cv2.VideoCapture(self.stream_url)
                    if not stream.isOpened():
                        print("重新连接失败")
                        break
                    continue
                
                # 处理帧
                self.process_frame(frame)
                
                # 显示实时画面
                cv2.imshow('ESP32 Camera Monitor', frame)
                
                # 检查按键
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                
            return True
            
        except Exception as e:
            print(f"OpenCV监控出错: {e}")
            return False
        finally:
            self.is_monitoring = False
            if 'stream' in locals():
                stream.release()
            cv2.destroyAllWindows()
    
    def monitor_with_requests(self):
        """
        使用requests库监控视频流（更稳定的方法）
        适用于OpenCV无法直接读取MJPEG流的情况
        """
        print("正在使用requests方法连接视频流...")
        
        self.is_monitoring = True
        gps_thread = Thread(target=self.update_gps_data, daemon=True)
        gps_thread.start()
        
        try:
            print("正在建立视频流连接...")
            response = requests.get(self.stream_url, stream=True, timeout=10)
            
            if response.status_code != 200:
                print(f"连接失败，状态码: {response.status_code}")
                return False
            
            print("✅ requests连接成功，开始监控...")
            print("按 'q' 键退出监控")
            
            bytes_data = b""
            frame_count = 0
            
            for chunk in response.iter_content(chunk_size=1024):
                if not self.is_monitoring:
                    break
                
                bytes_data += chunk
                a = bytes_data.find(b'\xff\xd8')  # JPEG开始标记
                b = bytes_data.find(b'\xff\xd9')  # JPEG结束标记
                
                while a != -1 and b != -1:
                    jpg_data = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]
                    
                    # 解码JPEG图像
                    frame = cv2.imdecode(
                        np.frombuffer(jpg_data, dtype=np.uint8), 
                        cv2.IMREAD_COLOR
                    )
                    
                    if frame is not None:
                        # 处理帧
                        self.process_frame(frame)
                        frame_count += 1
                        
                        # 显示实时画面
                        cv2.imshow('ESP32 Camera Monitor', frame)
                        
                        # 检查按键
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            self.is_monitoring = False
                            break
                    
                    # 查找下一个JPEG帧
                    a = bytes_data.find(b'\xff\xd8')
                    b = bytes_data.find(b'\xff\xd9')
            
            return True
            
        except KeyboardInterrupt:
            print("\n监控被用户中断")
            return True
        except Exception as e:
            print(f"requests监控出错: {e}")
            return False
        finally:
            self.is_monitoring = False
            cv2.destroyAllWindows()
    
    def test_connection(self):
        """测试所有连接"""
        print("=" * 50)
        print("ESP32 人脸/猫脸检测监控系统")
        print("=" * 50)
        
        # 测试基础连接
        try:
            response = requests.get(f"http://{self.esp32_ip}", timeout=3)
            print(f"✅ 成功连接到ESP32 (IP: {self.esp32_ip})")
        except Exception as e:
            print(f"❌ 无法连接到 {self.esp32_ip}: {e}")
            print("请确保:")
            print(f"1. ESP32已启动并连接到WiFi")
            print(f"2. 电脑和ESP32在同一网络")
            print(f"3. ESP32 IP地址正确")
            return False
        
        # 测试状态接口
        try:
            response = requests.get(self.status_url, timeout=3)
            if response.status_code == 200:
                print("✅ 摄像头状态正常")
            else:
                print(f"⚠️  摄像头状态异常: HTTP {response.status_code}")
        except:
            print("⚠️  无法获取摄像头状态")
        
        # 测试视频流
        try:
            response = requests.get(self.stream_url, stream=True, timeout=5)
            if response.status_code == 200:
                print("✅ 视频流可访问")
                response.close()  # 关闭连接
            else:
                print(f"⚠️  视频流不可用: HTTP {response.status_code}")
        except Exception as e:
            print(f"⚠️  视频流测试失败: {e}")
        
        # 测试GPS
        try:
            gps_response = requests.get(self.gps_json_url, timeout=3)
            gps_data = gps_response.json()
            if gps_data.get("valid", False):
                sats = gps_data.get('satellites', 0)
                print(f"✅ GPS信号正常: {sats}颗卫星")
            else:
                print("⚠️  GPS无有效信号")
        except Exception as e:
            print(f"⚠️  无法获取GPS数据: {e}")
        
        print("-" * 50)
        return True
    
    def run(self, method='requests'):
        """
        运行监控
        
        Args:
            method: 监控方法 ('auto', 'opencv', 或 'requests')
        """
        # 首先测试连接
        if not self.test_connection():
            print("连接测试失败，请检查设置后重试")
            return
        
        print("开始监控...")
        print(f"检测结果保存到: {os.path.abspath(self.base_save_dir)}/")
        print("冷却时间: 3秒 (防止重复保存)")
        print("-" * 50)
        
        success = False
        
        if method == 'auto':
            # 先尝试OpenCV，失败则使用requests
            print("尝试使用OpenCV方法...")
            success = self.monitor_stream()
            if not success:
                print("OpenCV方法失败，切换到requests方法...")
                success = self.monitor_with_requests()
        elif method == 'opencv':
            success = self.monitor_stream()
        else:  # requests
            success = self.monitor_with_requests()
        
        if success:
            print("监控正常结束")
        else:
            print("监控失败")


def main():
    """主函数"""
    # 配置参数
    ESP32_IP = "192.168.4.1"  # 根据实际情况修改
    MONITOR_METHOD = "requests"   # 'auto', 'opencv', 或 'requests'
    
    # 创建监控器
    monitor = ESP32FaceCatMonitor(esp32_ip=ESP32_IP)
    
    # 运行监控
    try:
        monitor.run(method=MONITOR_METHOD)
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"程序运行出错: {e}")


if __name__ == "__main__":
    main()