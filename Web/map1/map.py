# map.py - GPS轨迹可视化系统
import sys
import os
import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QTextEdit, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QFont
import dijkstra_run as d

class GPSProcessingThread(QThread):
    """GPS处理线程"""
    processing_started = pyqtSignal()
    processing_finished = pyqtSignal(object, object)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
    
    def run(self):
        try:
            self.processing_started.emit()
            img, result_p = d.gps_track_planning(self.file_path)
            self.processing_finished.emit(img, result_p)
        except Exception as e:
            self.error_occurred.emit(str(e))

class GPSTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.processing_thread = None
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle('GPS轨迹可视化系统')
        self.setGeometry(100, 100, 900, 950)
        
        # 设置窗口图标和样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QLabel {
                font-size: 14px;
            }
            QTextEdit {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 5px;
                font-size: 12px;
            }
        """)
        
        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title_label = QLabel('🚀 GPS轨迹可视化系统')
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(22)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 20px;")
        main_layout.addWidget(title_label)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        
        self.load_btn = QPushButton('📁 导入GPS数据文件')
        self.load_btn.setFixedSize(180, 50)
        self.load_btn.clicked.connect(self.load_gps_file)
        
        self.demo_btn = QPushButton('📊 查看示例轨迹')
        self.demo_btn.setFixedSize(180, 50)
        self.demo_btn.clicked.connect(self.show_demo)
        
        self.quit_btn = QPushButton('❌ 退出系统')
        self.quit_btn.setFixedSize(180, 50)
        self.quit_btn.clicked.connect(self.close)
        
        button_layout.addWidget(self.load_btn)
        button_layout.addWidget(self.demo_btn)
        button_layout.addWidget(self.quit_btn)
        button_layout.addStretch()
        
        main_layout.addLayout(button_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)  # 不确定进度模式
        self.progress_bar.setFixedHeight(20)
        main_layout.addWidget(self.progress_bar)
        
        # 图像显示区域
        image_container = QWidget()
        image_layout = QVBoxLayout()
        image_layout.setContentsMargins(0, 0, 0, 0)
        
        self.image_label = QLabel()
        self.image_label.setFixedSize(800, 800)
        self.image_label.setStyleSheet('''
            QLabel {
                background-color: white;
                border: 2px solid #3498db;
                border-radius: 5px;
            }
        ''')
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setText('等待导入GPS数据...\n\n点击"导入GPS数据文件"按钮开始')
        
        image_layout.addWidget(self.image_label, alignment=Qt.AlignCenter)
        image_container.setLayout(image_layout)
        
        main_layout.addWidget(image_container, alignment=Qt.AlignCenter)
        
        # 信息显示区域
        info_container = QWidget()
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 10, 0, 0)
        
        info_title = QLabel('📋 处理信息')
        info_title.setStyleSheet('font-size: 16px; font-weight: bold; color: #2c3e50;')
        info_layout.addWidget(info_title)
        
        self.info_text = QTextEdit()
        self.info_text.setFixedHeight(120)
        self.info_text.setReadOnly(True)
        self.info_text.setStyleSheet('''
            QTextEdit {
                font-size: 12px;
                padding: 5px;
            }
        ''')
        info_layout.addWidget(self.info_text)
        
        info_container.setLayout(info_layout)
        main_layout.addWidget(info_container)
        
        central_widget.setLayout(main_layout)
        
        # 状态栏
        self.statusBar().showMessage('就绪')
        
    def load_gps_file(self):
        """加载GPS数据文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            '选择GPS数据文件', 
            '', 
            '文本文件 (*.txt *.nmea);;所有文件 (*.*)'
        )
        
        if file_path:
            if not os.path.exists(file_path):
                QMessageBox.warning(self, '错误', '文件不存在！')
                return
            
            # 清空之前的信息
            self.info_text.clear()
            self.info_text.append(f'📂 选择文件: {os.path.basename(file_path)}')
            self.info_text.append('🔄 开始处理GPS数据...')
            
            # 禁用按钮
            self.set_buttons_enabled(False)
            
            # 显示进度条
            self.progress_bar.setVisible(True)
            self.statusBar().showMessage('正在处理GPS数据...')
            
            # 启动处理线程
            self.processing_thread = GPSProcessingThread(file_path)
            self.processing_thread.processing_started.connect(self.on_processing_started)
            self.processing_thread.processing_finished.connect(self.on_processing_finished)
            self.processing_thread.error_occurred.connect(self.on_processing_error)
            self.processing_thread.start()
    
    def show_demo(self):
        """显示示例轨迹"""
        self.info_text.clear()
        self.info_text.append('📊 显示示例轨迹')
        self.info_text.append('这是一个示例功能，实际使用时请导入GPS数据文件')
        
        # 创建一个示例图像
        demo_image = np.zeros((800, 800, 3), dtype=np.uint8)
        demo_image[:] = (240, 240, 240)
        
        # 绘制示例轨迹
        cv2.putText(demo_image, "GPS轨迹示例", (300, 150), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
        cv2.putText(demo_image, "导入GPS数据文件查看实际轨迹", (200, 250), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        
        # 绘制示例路径
        points = [(200, 400), (300, 350), (400, 380), (500, 320), 
                 (600, 360), (700, 400), (600, 500), (500, 450),
                 (400, 500), (300, 450), (200, 500)]
        
        for i in range(len(points)-1):
            cv2.line(demo_image, points[i], points[i+1], (0, 0, 255), 3)
        
        for point in points:
            cv2.circle(demo_image, point, 8, (255, 0, 0), -1)
        
        # 显示示例图像
        self.display_image(demo_image)
    
    def on_processing_started(self):
        """处理开始"""
        self.info_text.append('✅ GPS数据解析中...')
        QApplication.processEvents()
    
    def on_processing_finished(self, img, result_p):
        """处理完成"""
        self.progress_bar.setVisible(False)
        self.set_buttons_enabled(True)
        
        if img is not None:
            self.info_text.append('✅ 地图生成成功！')
            
            # 显示结果图像
            self.display_image(img)
            
            # 显示结果信息
            if result_p:
                self.info_text.append(f'📊 {result_p[0]}')
            
            # 保存图像
            save_path = os.path.join(os.path.dirname(__file__), "gps_track_result.jpg")
            cv2.imwrite(save_path, img)
            self.info_text.append(f'💾 图像已保存至: {save_path}')
            
            self.statusBar().showMessage('处理完成')
        else:
            self.info_text.append('❌ 地图生成失败')
            self.statusBar().showMessage('处理失败')
    
    def on_processing_error(self, error_msg):
        """处理错误"""
        self.progress_bar.setVisible(False)
        self.set_buttons_enabled(True)
        
        self.info_text.append(f'❌ 处理过程中发生错误: {error_msg}')
        QMessageBox.critical(self, '处理错误', f'处理过程中发生错误:\n{error_msg}')
        self.statusBar().showMessage('处理错误')
    
    def display_image(self, img):
        """显示图像"""
        try:
            # 转换图像格式
            rgb_image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            height, width, channel = rgb_image.shape
            bytes_per_line = 3 * width
            
            q_image = QImage(rgb_image.data, width, height, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_image)
            
            # 缩放以适应显示区域
            scaled_pixmap = pixmap.scaled(
                self.image_label.size(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
            self.image_label.setPixmap(scaled_pixmap)
            
        except Exception as e:
            print(f"显示图像失败: {e}")
    
    def set_buttons_enabled(self, enabled):
        """设置按钮状态"""
        self.load_btn.setEnabled(enabled)
        self.demo_btn.setEnabled(enabled)
        self.quit_btn.setEnabled(enabled)
    
    def closeEvent(self, event):
        """关闭事件"""
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.terminate()
            self.processing_thread.wait()
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    # 设置应用程序样式
    app.setStyle('Fusion')
    
    window = GPSTracker()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()