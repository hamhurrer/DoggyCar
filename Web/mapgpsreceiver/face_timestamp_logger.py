import serial
import re
import datetime
import requests
from pathlib import Path
from PIL import Image
from io import BytesIO

# ============ 配置区 ============
SERIAL_PORT = 'COM6'  # 修改为你的串口号
BAUD_RATE = 115200
TIMEOUT = 1

# ESP32 相机配置
ESP32_IP = '192.168.4.1'  # 修改为你的 ESP32 IP地址
CAPTURE_URL = f'http://{ESP32_IP}/capture'  # 截图接口
CAPTURE_TIMEOUT = 2  # 截图超时时间（秒）

# 输出文件配置
OUTPUT_DIR = Path('detection_logs')
HUMAN_DIR = OUTPUT_DIR / 'human_face'  # 人脸记录目录
CAT_DIR = OUTPUT_DIR / 'cat_face'      # 猫脸记录目录

# 人脸相关文件
HUMAN_TIMESTAMP_FILE = HUMAN_DIR / 'timestamps.txt'
HUMAN_SCREENSHOT_DIR = HUMAN_DIR / 'screenshots'

# 猫脸相关文件
CAT_TIMESTAMP_FILE = CAT_DIR / 'timestamps.txt'
CAT_SCREENSHOT_DIR = CAT_DIR / 'screenshots'

# 通用文件
DEBUG_LOG_FILE = OUTPUT_DIR / 'debug_log.txt'
STATISTICS_FILE = OUTPUT_DIR / 'statistics.txt'

# 功能开关
SAVE_DEBUG_LOG = True
SAVE_SCREENSHOTS = True  # 是否保存截图
# ===============================


class DualDetectionLogger:
    def __init__(self, port, baudrate):
        """初始化串口连接和文件"""
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        
        # 分别统计人脸和猫脸
        self.human_count = 0
        self.cat_count = 0
        self.human_screenshot_success = 0
        self.human_screenshot_fail = 0
        self.cat_screenshot_success = 0
        self.cat_screenshot_fail = 0
        
        # 创建目录结构
        self._create_directories()
        
        # 正则表达式匹配时间戳
        self.human_pattern = re.compile(r'HUMAN_FACE,TIME:(\d+\.\d+),COUNT:(\d+)')
        self.cat_pattern = re.compile(r'CAT_FACE,TIME:(\d+\.\d+),COUNT:(\d+)')
        
        # 初始化统计信息
        self.start_time = datetime.datetime.now()
        
        self._print_header()
        self._init_statistics_file()
    
    def _create_directories(self):
        """创建所有需要的目录"""
        OUTPUT_DIR.mkdir(exist_ok=True)
        HUMAN_DIR.mkdir(exist_ok=True)
        CAT_DIR.mkdir(exist_ok=True)
        
        if SAVE_SCREENSHOTS:
            HUMAN_SCREENSHOT_DIR.mkdir(exist_ok=True)
            CAT_SCREENSHOT_DIR.mkdir(exist_ok=True)
    
    def _print_header(self):
        """打印启动信息"""
        print("=" * 70)
        print("  ESP32 双AI检测时间戳记录器 v2.0")
        print("  人脸检测 + 猫脸检测 + 自动截图")
        print("=" * 70)
        print(f"串口: {self.port} @ {self.baudrate}")
        print(f"ESP32 IP: {ESP32_IP}")
        print(f"截图接口: {CAPTURE_URL}")
        print()
        print("输出目录:")
        print(f"  人脸时间戳: {HUMAN_TIMESTAMP_FILE}")
        print(f"  人脸截图:   {HUMAN_SCREENSHOT_DIR if SAVE_SCREENSHOTS else '不保存'}")
        print(f"  猫脸时间戳: {CAT_TIMESTAMP_FILE}")
        print(f"  猫脸截图:   {CAT_SCREENSHOT_DIR if SAVE_SCREENSHOTS else '不保存'}")
        print(f"  调试日志:   {DEBUG_LOG_FILE if SAVE_DEBUG_LOG else '不保存'}")
        print(f"  统计信息:   {STATISTICS_FILE}")
        print("-" * 70)
    
    def _init_statistics_file(self):
        """初始化统计文件"""
        with open(STATISTICS_FILE, 'w', encoding='utf-8') as f:
            f.write(f"ESP32 双AI检测统计报告\n")
            f.write(f"{'=' * 70}\n")
            f.write(f"开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"ESP32 IP: {ESP32_IP}\n")
            f.write(f"截图功能: {'启用' if SAVE_SCREENSHOTS else '禁用'}\n")
            f.write(f"{'=' * 70}\n\n")
        
        # 初始化人脸时间戳文件
        with open(HUMAN_TIMESTAMP_FILE, 'w', encoding='utf-8') as f:
            f.write(f"人脸检测时间戳记录\n")
            f.write(f"{'=' * 70}\n")
            f.write(f"开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'=' * 70}\n\n")
        
        # 初始化猫脸时间戳文件
        with open(CAT_TIMESTAMP_FILE, 'w', encoding='utf-8') as f:
            f.write(f"猫脸检测时间戳记录\n")
            f.write(f"{'=' * 70}\n")
            f.write(f"开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'=' * 70}\n\n")
    
    def connect(self):
        """连接串口"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=TIMEOUT
            )
            print(f"✓ 成功连接到 {self.port}")
            
            # 测试 ESP32 相机连接
            if SAVE_SCREENSHOTS:
                self._test_camera_connection()
            
            print("\n开始监听...")
            print("=" * 70)
            print(f"{'时间':<20} {'类型':<8} {'检测时间戳':<15} {'截图':<8} {'序号':<8}")
            print("-" * 70)
            return True
        except serial.SerialException as e:
            print(f"✗ 串口连接失败: {e}")
            return False
    
    def _test_camera_connection(self):
        """测试 ESP32 相机连接"""
        try:
            print(f"正在测试相机连接: {CAPTURE_URL}")
            response = requests.get(CAPTURE_URL, timeout=CAPTURE_TIMEOUT)
            if response.status_code == 200:
                print("✓ 相机连接成功")
            else:
                print(f"⚠ 相机响应异常: HTTP {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"⚠ 相机连接失败: {e}")
            print("提示: 请检查 ESP32_IP 配置是否正确")
    
    def capture_screenshot(self, detection_type, timestamp_str, count):
        """从 ESP32 获取截图
        
        Args:
            detection_type: 'human' 或 'cat'
            timestamp_str: 时间戳字符串
            count: 当前检测序号
        """
        if not SAVE_SCREENSHOTS:
            return False
        
        try:
            # 请求截图
            response = requests.get(CAPTURE_URL, timeout=CAPTURE_TIMEOUT)
            
            if response.status_code == 200:
                # 根据类型选择目录
                screenshot_dir = HUMAN_SCREENSHOT_DIR if detection_type == 'human' else CAT_SCREENSHOT_DIR
                prefix = 'human' if detection_type == 'human' else 'cat'
                
                # 生成文件名: human_0001_12.345678.jpg 或 cat_0001_12.345678.jpg
                filename = f"{prefix}_{count:04d}_{timestamp_str}.jpg"
                filepath = screenshot_dir / filename
                
                # 保存图片
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                # 可选：使用 PIL 验证图片
                try:
                    img = Image.open(BytesIO(response.content))
                    img.save(filepath, 'JPEG', quality=95)
                except Exception:
                    pass  # 如果 PIL 处理失败，至少保存了原始图片
                
                # 更新成功计数
                if detection_type == 'human':
                    self.human_screenshot_success += 1
                else:
                    self.cat_screenshot_success += 1
                
                return True
            else:
                # 更新失败计数
                if detection_type == 'human':
                    self.human_screenshot_fail += 1
                else:
                    self.cat_screenshot_fail += 1
                return False
                
        except requests.exceptions.RequestException:
            # 更新失败计数
            if detection_type == 'human':
                self.human_screenshot_fail += 1
            else:
                self.cat_screenshot_fail += 1
            return False
    
    def process_human_detection(self, timestamp_str, esp_count):
        """处理人脸检测"""
        self.human_count += 1
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 截图
        screenshot_status = ""
        if SAVE_SCREENSHOTS:
            if self.capture_screenshot('human', timestamp_str, self.human_count):
                screenshot_status = "✓"
            else:
                screenshot_status = "✗"
        else:
            screenshot_status = "-"
        
        # 保存到人脸时间戳文件
        with open(HUMAN_TIMESTAMP_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{self.human_count:04d}] {current_time} | {timestamp_str} | "
                   f"ESP计数:{esp_count} | 截图:{screenshot_status}\n")
        
        # 控制台输出
        print(f"{current_time:<20} {'👤人脸':<8} {timestamp_str:<15} {screenshot_status:<8} #{self.human_count:04d}")
    
    def process_cat_detection(self, timestamp_str, esp_count):
        """处理猫脸检测"""
        self.cat_count += 1
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 截图
        screenshot_status = ""
        if SAVE_SCREENSHOTS:
            if self.capture_screenshot('cat', timestamp_str, self.cat_count):
                screenshot_status = "✓"
            else:
                screenshot_status = "✗"
        else:
            screenshot_status = "-"
        
        # 保存到猫脸时间戳文件
        with open(CAT_TIMESTAMP_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{self.cat_count:04d}] {current_time} | {timestamp_str} | "
                   f"ESP计数:{esp_count} | 截图:{screenshot_status}\n")
        
        # 控制台输出
        print(f"{current_time:<20} {'🐱猫脸':<8} {timestamp_str:<15} {screenshot_status:<8} #{self.cat_count:04d}")
    
    def save_debug_log(self, line):
        """保存所有串口数据到调试日志"""
        if SAVE_DEBUG_LOG:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            with open(DEBUG_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"[{current_time}] {line}\n")
    
    def update_statistics(self):
        """更新统计信息"""
        end_time = datetime.datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        with open(STATISTICS_FILE, 'a', encoding='utf-8') as f:
            f.write(f"\n{'=' * 70}\n")
            f.write(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"运行时长: {duration:.1f} 秒 ({duration/60:.1f} 分钟)\n")
            
            f.write(f"\n人脸检测统计:\n")
            f.write(f"  检测次数: {self.human_count}\n")
            if duration > 0:
                f.write(f"  检测频率: {self.human_count/duration:.2f} 次/秒\n")
            if SAVE_SCREENSHOTS:
                f.write(f"  截图成功: {self.human_screenshot_success}\n")
                f.write(f"  截图失败: {self.human_screenshot_fail}\n")
                if self.human_count > 0:
                    rate = (self.human_screenshot_success / self.human_count) * 100
                    f.write(f"  截图成功率: {rate:.1f}%\n")
            
            f.write(f"\n猫脸检测统计:\n")
            f.write(f"  检测次数: {self.cat_count}\n")
            if duration > 0:
                f.write(f"  检测频率: {self.cat_count/duration:.2f} 次/秒\n")
            if SAVE_SCREENSHOTS:
                f.write(f"  截图成功: {self.cat_screenshot_success}\n")
                f.write(f"  截图失败: {self.cat_screenshot_fail}\n")
                if self.cat_count > 0:
                    rate = (self.cat_screenshot_success / self.cat_count) * 100
                    f.write(f"  截图成功率: {rate:.1f}%\n")
            
            f.write(f"\n总计:\n")
            f.write(f"  总检测次数: {self.human_count + self.cat_count}\n")
            if SAVE_SCREENSHOTS:
                total_success = self.human_screenshot_success + self.cat_screenshot_success
                total_fail = self.human_screenshot_fail + self.cat_screenshot_fail
                total = self.human_count + self.cat_count
                f.write(f"  总截图成功: {total_success}\n")
                f.write(f"  总截图失败: {total_fail}\n")
                if total > 0:
                    rate = (total_success / total) * 100
                    f.write(f"  总成功率: {rate:.1f}%\n")
            
            f.write(f"{'=' * 70}\n")
    
    def run(self):
        """主循环 - 持续监听串口"""
        if not self.connect():
            return
        
        try:
            while True:
                if self.serial_conn.in_waiting > 0:
                    # 读取一行数据
                    raw_data = self.serial_conn.readline()
                    
                    try:
                        line = raw_data.decode('utf-8', errors='ignore').strip()
                    except:
                        continue
                    
                    if not line:
                        continue
                    
                    # 保存所有数据到调试日志
                    self.save_debug_log(line)
                    
                    # 检查是否是人脸时间戳
                    human_match = self.human_pattern.search(line)
                    if human_match:
                        timestamp = human_match.group(1)
                        esp_count = human_match.group(2)
                        self.process_human_detection(timestamp, esp_count)
                        continue
                    
                    # 检查是否是猫脸时间戳
                    cat_match = self.cat_pattern.search(line)
                    if cat_match:
                        timestamp = cat_match.group(1)
                        esp_count = cat_match.group(2)
                        self.process_cat_detection(timestamp, esp_count)
                        continue
        
        except KeyboardInterrupt:
            print("\n" + "=" * 70)
            print("停止记录")
            print("=" * 70)
            
            # 打印统计信息
            print(f"\n检测统计:")
            print(f"  人脸检测: {self.human_count} 次")
            if SAVE_SCREENSHOTS:
                print(f"    截图成功: {self.human_screenshot_success}")
                print(f"    截图失败: {self.human_screenshot_fail}")
                if self.human_count > 0:
                    rate = (self.human_screenshot_success / self.human_count) * 100
                    print(f"    成功率: {rate:.1f}%")
            
            print(f"\n  猫脸检测: {self.cat_count} 次")
            if SAVE_SCREENSHOTS:
                print(f"    截图成功: {self.cat_screenshot_success}")
                print(f"    截图失败: {self.cat_screenshot_fail}")
                if self.cat_count > 0:
                    rate = (self.cat_screenshot_success / self.cat_count) * 100
                    print(f"    成功率: {rate:.1f}%")
            
            print(f"\n  总计: {self.human_count + self.cat_count} 次")
            
            # 更新统计信息
            self.update_statistics()
            
            # 打印文件位置
            print(f"\n输出文件:")
            print(f"  人脸时间戳: {HUMAN_TIMESTAMP_FILE.absolute()}")
            if SAVE_SCREENSHOTS:
                print(f"  人脸截图:   {HUMAN_SCREENSHOT_DIR.absolute()} ({self.human_screenshot_success}张)")
            print(f"  猫脸时间戳: {CAT_TIMESTAMP_FILE.absolute()}")
            if SAVE_SCREENSHOTS:
                print(f"  猫脸截图:   {CAT_SCREENSHOT_DIR.absolute()} ({self.cat_screenshot_success}张)")
            print(f"  调试日志:   {DEBUG_LOG_FILE.absolute()}")
            print(f"  统计信息:   {STATISTICS_FILE.absolute()}")
        
        finally:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
                print("\n串口已关闭")


def main():
    """主函数"""
    logger = DualDetectionLogger(SERIAL_PORT, BAUD_RATE)
    logger.run()


if __name__ == "__main__":
    main()