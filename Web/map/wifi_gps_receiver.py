# wifi_gps_receiver_enhanced.py
import socket
import json
import time
from datetime import datetime
import threading
import sys
import os
import subprocess

class EnhancedGPSReceiver:
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.clients = {}
        self.debug_mode = True  # 开启调试模式
        
    def display_network_info(self):
        """显示网络信息"""
        print("\n" + "=" * 60)
        print("           WiFi GPS 数据接收服务器 - 增强版")
        print("=" * 60)
        
        # 获取本机IP
        local_ip = self.get_local_ip()
        print(f"📱 本机IP地址: {local_ip}")
        print(f"📡 监听端口: {self.port}")
        print(f"🌐 网络接口: {socket.gethostname()}")
        
        # 检查端口占用
        if self.is_port_in_use(self.port):
            print(f"⚠️  警告: 端口 {self.port} 可能已被占用")
        else:
            print(f"✅ 端口 {self.port} 可用")
        
        print("-" * 60)
    
    def get_local_ip(self):
        """获取本机IP地址（多方法尝试）"""
        try:
            # 方法1: 通过UDP连接获取
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            try:
                # 方法2: 获取主机名
                return socket.gethostbyname(socket.gethostname())
            except:
                return "0.0.0.0"
    
    def is_port_in_use(self, port):
        """检查端口是否被占用"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex((self.host, port)) == 0
    
    def start_server(self):
        """启动TCP服务器"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)  # 设置超时以便检查运行状态
            
            self.running = True
            print(f"\n✅ 服务器启动成功！")
            print(f"📡 监听地址: {self.host}:{self.port}")
            print(f"🔧 调试模式: {'开启' if self.debug_mode else '关闭'}")
            print("\n等待设备连接...")
            print("按 Ctrl+C 停止服务器\n")
            
            self.accept_clients()
            
        except PermissionError:
            print(f"❌ 权限错误: 请尝试使用管理员权限运行")
            return False
        except OSError as e:
            print(f"❌ 启动服务器失败: {e}")
            print(f"💡 尝试: 1. 更换端口 2. 检查防火墙 3. 使用管理员权限")
            return False
        except Exception as e:
            print(f"❌ 未知错误: {e}")
            return False
    
    def accept_clients(self):
        """接受客户端连接"""
        try:
            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    client_socket.settimeout(10.0)  # 设置客户端超时
                    
                    client_id = f"{client_address[0]}:{client_address[1]}"
                    print(f"\n📱 新设备连接: {client_id}")
                    print(f"   🕐 时间: {datetime.now().strftime('%H:%M:%S')}")
                    
                    # 创建客户端线程
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address),
                        daemon=True
                    )
                    client_thread.start()
                    
                    # 保存客户端信息
                    self.clients[client_id] = {
                        'socket': client_socket,
                        'address': client_address,
                        'thread': client_thread,
                        'connected_time': datetime.now(),
                        'last_active': datetime.now()
                    }
                    
                except socket.timeout:
                    # 超时检查，保持服务器响应
                    continue
                except Exception as e:
                    if self.debug_mode:
                        print(f"接受连接错误: {e}")
                    continue
                    
        except KeyboardInterrupt:
            print("\n\n🛑 收到停止信号，正在关闭服务器...")
        finally:
            self.cleanup()
    
    def handle_client(self, client_socket, client_address):
        """处理客户端通信"""
        buffer = ""
        client_id = f"{client_address[0]}:{client_address[1]}"
        
        try:
            while self.running:
                try:
                    # 接收数据
                    data = client_socket.recv(2048)  # 增加缓冲区大小
                    if not data:
                        print(f"\n🔌 设备断开连接: {client_id}")
                        break
                    
                    # 更新最后活动时间
                    if client_id in self.clients:
                        self.clients[client_id]['last_active'] = datetime.now()
                    
                    # 解码数据
                    try:
                        data_str = data.decode('utf-8', errors='ignore')
                    except:
                        data_str = data.decode('latin-1', errors='ignore')
                    
                    if self.debug_mode and len(data_str.strip()) > 0:
                        print(f"[DEBUG {client_id}] 收到原始数据: {data_str[:100]}")
                    
                    buffer += data_str
                    
                    # 处理完整的数据行
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        
                        if line:
                            self.process_client_data(line, client_address, client_id)
                            
                except socket.timeout:
                    # 发送心跳或保持连接
                    try:
                        client_socket.send(b'')  # 空数据包保持连接
                    except:
                        break
                    continue
                except ConnectionResetError:
                    print(f"\n❌ 连接重置: {client_id}")
                    break
                except Exception as e:
                    if self.debug_mode:
                        print(f"处理数据错误 [{client_id}]: {e}")
                    break
        
        finally:
            # 清理客户端连接
            try:
                client_socket.close()
            except:
                pass
            
            if client_id in self.clients:
                del self.clients[client_id]
                print(f"🗑️  清理客户端: {client_id}")
    
    def process_client_data(self, data_str, client_address, client_id):
        """处理客户端发送的数据"""
        # 过滤AT指令响应
        if any(at_cmd in data_str for at_cmd in ["AT", "OK", "ERROR", "SEND", "CONNECT", "CLOSED"]):
            if self.debug_mode:
                print(f"[AT {client_id}] {data_str[:50]}")
            return
        
        # 尝试解析JSON
        try:
            # 清理数据
            data_str = data_str.strip()
            if data_str.startswith('"') and data_str.endswith('"'):
                data_str = data_str[1:-1]
            
            # 尝试解析JSON
            gps_data = json.loads(data_str)
            self.display_gps_info(gps_data, client_address, client_id)
            self.save_gps_data(gps_data, client_address)
            
        except json.JSONDecodeError as e:
            # 如果不是JSON，可能是其他格式
            if len(data_str) > 5:  # 忽略短消息
                print(f"[RAW {client_id}] {data_str[:80]}")
                
                # 尝试手动解析GPRMC或GPGGA格式
                if data_str.startswith('$'):
                    self.parse_nmea_data(data_str, client_address, client_id)
        except Exception as e:
            if self.debug_mode:
                print(f"解析错误 [{client_id}]: {e}")
    
    def parse_nmea_data(self, nmea_str, client_address, client_id):
        """解析NMEA格式数据"""
        try:
            parts = nmea_str.split(',')
            
            if len(parts) > 12:
                data_type = parts[0]
                
                if data_type in ['$GPRMC', '$GNRMC']:
                    # GPRMC格式
                    if len(parts) >= 10:
                        utc_time = parts[1][:6] if len(parts[1]) >= 6 else ""
                        status = parts[2]
                        lat = parts[3] if len(parts[3]) > 0 else ""
                        lat_dir = parts[4]
                        lon = parts[5] if len(parts[5]) > 0 else ""
                        lon_dir = parts[6]
                        
                        gps_data = {
                            'time': utc_time,
                            'status': status,
                            'lat': lat,
                            'lat_dir': lat_dir,
                            'lon': lon,
                            'lon_dir': lon_dir,
                            'source': 'NMEA_RMC'
                        }
                        
                        self.display_gps_info(gps_data, client_address, client_id)
                        self.save_gps_data(gps_data, client_address)
                
                elif data_type in ['$GPGGA', '$GNGGA']:
                    # GPGGA格式
                    if len(parts) >= 10:
                        utc_time = parts[1][:6] if len(parts[1]) >= 6 else ""
                        lat = parts[2] if len(parts[2]) > 0 else ""
                        lat_dir = parts[3]
                        lon = parts[4] if len(parts[4]) > 0 else ""
                        lon_dir = parts[5]
                        status = 'A' if int(parts[6]) > 0 else 'V'
                        
                        gps_data = {
                            'time': utc_time,
                            'status': status,
                            'lat': lat,
                            'lat_dir': lat_dir,
                            'lon': lon,
                            'lon_dir': lon_dir,
                            'source': 'NMEA_GGA'
                        }
                        
                        self.display_gps_info(gps_data, client_address, client_id)
                        self.save_gps_data(gps_data, client_address)
                        
        except Exception as e:
            if self.debug_mode:
                print(f"NMEA解析错误: {e}")
    
    def display_gps_info(self, gps_data, client_address, client_id):
        """显示GPS信息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n📍 GPS数据 [{timestamp}] - {client_id}")
        print("-" * 50)
        
        status = gps_data.get('status', 'V')
        
        if status == 'A':
            print("✅ 状态: 有效定位")
            
            lat = gps_data.get('lat', 'N/A')
            lat_dir = gps_data.get('lat_dir', '')
            lon = gps_data.get('lon', 'N/A')
            lon_dir = gps_data.get('lon_dir', '')
            utc_time = gps_data.get('time', 'N/A')
            
            print(f"🕐 UTC时间: {utc_time}")
            
            if lat != 'N/A' and lon != 'N/A':
                print(f"📍 纬度: {lat} {lat_dir}")
                print(f"📍 经度: {lon} {lon_dir}")
                
                # 转换坐标
                lat_dec = self.nmea_to_decimal(lat, lat_dir)
                lon_dec = self.nmea_to_decimal(lon, lon_dir)
                
                if lat_dec != 0.0 and lon_dec != 0.0:
                    print(f"🔢 纬度(度): {lat_dec:.6f}°")
                    print(f"🔢 经度(度): {lon_dec:.6f}°")
                    
                    # 显示地图链接
                    print(f"🗺️  地图: https://www.google.com/maps?q={lat_dec},{lon_dec}")
        
        else:
            print("❌ 状态: 无效定位")
            print("💡 提示: 确保GPS模块在室外开阔处")
    
    def nmea_to_decimal(self, nmea_coord, direction):
        """NMEA坐标转十进制"""
        try:
            if not nmea_coord or len(nmea_coord) < 7:
                return 0.0
            
            # 找到小数点
            dot_index = nmea_coord.find('.')
            if dot_index < 2:
                return 0.0
            
            # 解析
            if direction in ['N', 'S']:  # 纬度 ddmm.mmmm
                degrees = float(nmea_coord[:dot_index-2])
                minutes = float(nmea_coord[dot_index-2:])
            else:  # 经度 dddmm.mmmm
                degrees = float(nmea_coord[:dot_index-3])
                minutes = float(nmea_coord[dot_index-3:])
            
            decimal = degrees + (minutes / 60.0)
            
            if direction in ['S', 'W']:
                decimal = -decimal
            
            return decimal
            
        except Exception as e:
            if self.debug_mode:
                print(f"坐标转换错误: {e}")
            return 0.0
    
    def save_gps_data(self, gps_data, client_address):
        """保存GPS数据"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            csv_file = "gps_data.csv"
            
            # 准备数据
            lat = gps_data.get('lat', '')
            lat_dir = gps_data.get('lat_dir', '')
            lon = gps_data.get('lon', '')
            lon_dir = gps_data.get('lon_dir', '')
            status = gps_data.get('status', 'V')
            utc_time = gps_data.get('time', '')
            
            lat_dec = self.nmea_to_decimal(lat, lat_dir)
            lon_dec = self.nmea_to_decimal(lon, lon_dir)
            
            # 检查文件是否存在
            file_exists = os.path.isfile(csv_file)
            
            with open(csv_file, 'a', encoding='utf-8') as f:
                if not file_exists:
                    f.write("local_time,client_ip,utc_time,latitude,lat_dir,longitude,lon_dir,status,lat_decimal,lon_decimal\n")
                
                f.write(f"{timestamp},{client_address[0]},{utc_time},{lat},{lat_dir},{lon},{lon_dir},{status},{lat_dec:.6f},{lon_dec:.6f}\n")
            
            # 同时保存到日志
            log_file = "gps_log.txt"
            with open(log_file, 'a', encoding='utf-8') as f:
                log_entry = f"[{timestamp}] {client_address[0]} - "
                if status == 'A':
                    log_entry += f"定位: {lat}{lat_dir}, {lon}{lon_dir} ({lat_dec:.6f}, {lon_dec:.6f})\n"
                else:
                    log_entry += "无效定位\n"
                f.write(log_entry)
                
        except Exception as e:
            if self.debug_mode:
                print(f"保存数据错误: {e}")
    
    def cleanup(self):
        """清理资源"""
        self.running = False
        
        print("\n🛑 正在关闭服务器...")
        
        # 关闭所有客户端连接
        for client_id, client_info in list(self.clients.items()):
            try:
                client_info['socket'].close()
                print(f"  关闭连接: {client_id}")
            except:
                pass
        
        # 关闭服务器套接字
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        print(f"\n📊 服务器统计:")
        print(f"   总连接数: {len(self.clients)}")
        print(f"   运行时间: {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 60)
        print("✅ 服务器已安全关闭")
    
    def check_firewall(self):
        """检查防火墙设置"""
        print("\n🔒 防火墙检查指南:")
        print("=" * 50)
        print("如果无法连接，请按以下步骤操作:")
        print("1. 暂时关闭防火墙测试连接")
        print("2. 或添加防火墙规则允许端口8080")
        print("3. 对于Windows:")
        print("   - 控制面板 -> 防火墙 -> 高级设置")
        print("   - 入站规则 -> 新建规则 -> 端口")
        print("   - 端口: 8080, 允许连接")
        print("=" * 50)
    
    def run(self):
        """运行服务器"""
        os.system('cls' if os.name == 'nt' else 'clear')
        
        self.display_network_info()
        self.check_firewall()
        
        # 用户确认
        print("\n🚀 准备启动服务器...")
        try:
            input("按 Enter 键开始，或按 Ctrl+C 取消: ")
        except KeyboardInterrupt:
            print("\n👋 用户取消")
            sys.exit(0)
        
        # 启动服务器
        if self.start_server():
            print("\n🎉 服务器运行中...")
        else:
            print("\n❌ 服务器启动失败")

def main():
    """主函数"""
    try:
        # 创建并运行服务器
        server = EnhancedGPSReceiver(host='0.0.0.0', port=8080)
        server.run()
        
    except KeyboardInterrupt:
        print("\n\n👋 程序结束")
    except Exception as e:
        print(f"❌ 程序错误: {e}")
        input("\n按 Enter 键退出...")

if __name__ == "__main__":
    main()