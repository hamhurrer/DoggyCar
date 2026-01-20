# -*- coding: utf-8 -*-
import os
import time
import golbal_define as gd
import sys
import cv2
import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import (QApplication, QLineEdit, QLabel, QTabWidget, 
                            QWidget, QTextEdit, QFormLayout, QPushButton, 
                            QTableWidget, QTableWidgetItem, QAbstractItemView,
                            QFileDialog, QDialog)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, Qt, QDate, QTime, QDateTime
from PyQt5.QtGui import QPixmap, QImage
import dijkstra_run as d

today_date = QDate.currentDate()
today_date = today_date.toString(Qt.DefaultLocaleLongDate)
print(today_date)

main_location = '北京'
zoom_ = 12  # 地图放大 1-17

class Ui_TabWidget(object):
    def setupUi(self, TabWidget):
        # 主窗口设置
        TabWidget.setObjectName("基于dijkstra算法的路径规划")
        TabWidget.setGeometry(gd.big_x, gd.big_y, gd.big_w, gd.big_h + 50)
        
        self.pushButton = QtWidgets.QPushButton(TabWidget)
        self.pushButton.setGeometry(QtCore.QRect(5, 80, 90, 46))
        self.pushButton.setObjectName("pushButton")

        self.pushButton1 = QtWidgets.QPushButton(TabWidget)
        self.pushButton1.setGeometry(QtCore.QRect(5, 500, 90, 46))
        self.pushButton1.setObjectName("pushButton")

        self.pushButton3 = QtWidgets.QPushButton(TabWidget)
        self.pushButton3.setGeometry(QtCore.QRect(5, 300, 90, 46))
        self.pushButton3.setObjectName("按A打卡")

        self.pushButton2 = QtWidgets.QPushButton(TabWidget)
        self.pushButton2.setGeometry(QtCore.QRect(5, 700, 90, 46))
        self.pushButton2.setObjectName("pushButton")

        # 日期显示设置
        self.labeldate = QtWidgets.QLabel(TabWidget)
        self.labeldate.setGeometry(QtCore.QRect(300, gd.show_y-30, gd.show_w-30, 30))

        # 结果显示设置
        self.labelresult = QtWidgets.QLabel(TabWidget)
        self.labelresult.setGeometry(QtCore.QRect(100, gd.show_y + gd.show_h+30, gd.show_w, 60))    
        self.labelresult.setAlignment(QtCore.Qt.AlignVCenter)

        # 显示设置
        self.label = QtWidgets.QLabel(TabWidget)
        self.label.setGeometry(QtCore.QRect(gd.show_x, gd.show_y, gd.show_w, gd.show_h))
        self.label.setText("")
        self.label.setObjectName("label")

        self.retranslateUi(TabWidget)
        TabWidget.setCurrentIndex(0)
        self.pushButton.clicked.connect(TabWidget.tsp_show)
        self.pushButton1.clicked.connect(TabWidget.showdialog)
        self.pushButton2.clicked.connect(TabWidget.quit_system)
        self.pushButton3.clicked.connect(TabWidget.changeMain_location)

        QtCore.QMetaObject.connectSlotsByName(TabWidget)

    def retranslateUi(self, TabWidget):
        _translate = QtCore.QCoreApplication.translate
        TabWidget.setWindowTitle(_translate("TabWidget", "基于dijkstra算法的路径规划"))
        self.pushButton.setText(_translate("TabWidget", "TSP问题"))
        self.pushButton1.setText(_translate("TabWidget", "输入地点"))
        self.pushButton2.setText(_translate("TabWidget", "退出系统"))
        self.pushButton3.setText(_translate("TabWidget", f"当前：{main_location}"))

    def changeMain_location(self):
        self.change_dialog = QtWidgets.QDialog()
        self.change_dialog.setGeometry(QtCore.QRect(300, 300, 260, 160))
        
        btn1 = QPushButton("确定", self.change_dialog)
        btn1.move(20, 100)
        btn2 = QPushButton("退出", self.change_dialog)
        btn2.move(140, 100)
        
        flo = QFormLayout()
        self.change_line = QLineEdit()
        flo.addRow("城市", self.change_line)
        self.change_line.setMaxLength(10)
        self.change_dialog.setLayout(flo)

        btn1.clicked.connect(self.new_city)
        btn2.clicked.connect(self.change_dialog.close)
        self.change_dialog.exec_()

    def new_city(self):
        global main_location
        new_city_changed = self.change_line.text()
        if new_city_changed:
            main_location = new_city_changed
            self.pushButton3.setText(f"当前：{main_location}")
        self.change_dialog.close()

    def showdialog(self):
        self.dialog = QtWidgets.QDialog()
        self.dialog.setGeometry(QtCore.QRect(300, 300, 300, 260))
        
        btn1 = QPushButton("确定", self.dialog)
        btn1.move(20, 200)
        btn2 = QPushButton("退出", self.dialog)
        btn2.move(200, 200)

        self.label_ = QLabel("输入地点,空格隔开\n例子：天安门 清华大学 颐和园\n", self.dialog)
        self.label_.move(20, 10)

        self.pNormalLineEdit = QTextEdit(self.dialog)
        self.pNormalLineEdit.setPlaceholderText("天安门;清华大学;颐和园")
        self.pNormalLineEdit.move(20, 70)
        self.pNormalLineEdit.resize(260, 100)

        btn1.clicked.connect(self.input_detect)
        btn2.clicked.connect(self.dialog.close)
        self.dialog.exec_()

    def input_detect(self):
        global main_location
        name = self.pNormalLineEdit.toPlainText()
        places = [p.strip() for p in name.split() if p.strip()]
        
        if places:
            img, result_p = d.path_planning(places, main_location, zoom_)
            self.dialog.close()

            rgbImage = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            convertToQtFormat = QtGui.QImage(
                rgbImage.data, rgbImage.shape[1], rgbImage.shape[0],
                QImage.Format_RGB888
            )  
            p = convertToQtFormat.scaled(gd.show_w, gd.show_h, Qt.KeepAspectRatio)
            self.setImage(p)

            re_text = '自驾游玩顺序：\n' + ' 到 '.join(result_p)
            self.labelresult.setText(re_text)

    def setImage(self, image):
        self.label.setPixmap(QPixmap.fromImage(image))

class MyWindow(QTabWidget, Ui_TabWidget):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        
        self.th = QTimer()
        self.th.timeout.connect(self.setDataLabel)
        self.th.start(1000)

    def quit_system(self):
        sender = self.sender()         
        print(sender.text(), '被按下了', '退出系统！')  
        self.th.stop()
        QApplication.instance().quit()

    def tsp_show(self):
        try:
            tsp_re = cv2.imread('Figure_1.png')
            if tsp_re is not None:
                rgbImage = cv2.cvtColor(tsp_re, cv2.COLOR_BGR2RGB)
                show = cv2.resize(rgbImage, (800, 800))
                show.fill(255)
                show[130:800-130, :] = cv2.resize(rgbImage, (800, 540), cv2.INTER_CUBIC)
                
                convertToQtFormat = QtGui.QImage(
                    show.data, show.shape[1], show.shape[0], 
                    show.shape[1] * 3, QImage.Format_RGB888
                )  
                p = convertToQtFormat.scaled(gd.show_w, gd.show_h, Qt.KeepAspectRatio)
                self.setImage(p)
                self.labelresult.setText("")
        except Exception as e:
            print(f"加载图片出错: {e}")

    def setDataLabel(self):
        time = QTime.currentTime()
        now_time = time.toString(Qt.DefaultLocaleLongDate)
        # 安全处理时间字符串
        time_parts = now_time.split(' ')
        if len(time_parts) > 1:
            display_time = f"{today_date}  {time_parts[1]}"
        else:
            display_time = f"{today_date}  {now_time}"
        self.labeldate.setText(display_time)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MyWindow()
    window.show()
    sys.exit(app.exec_())

#火车东站 武侯祠 春熙路 金沙博物馆 天府广场 大熊猫繁育研究基地 宽窄巷子
#清华大学 颐和园 圆明园 天安门广场 海淀黄庄
# 清华大学 北京大学 圆明园 颐和园 北京动物园 天安门广场
# 双流国际机场 成都大熊猫繁育研究基地 金沙博物馆 武侯祠 宽窄巷子 春熙路 天府广场
