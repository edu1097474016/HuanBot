"""HuanBot控制台应用"""
import sys
import os
import json
import threading
import time
from datetime import datetime
from typing import Dict, List, Any

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QTextEdit, QPushButton, QLineEdit, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QGroupBox, QFormLayout, QMessageBox, QProgressBar, QStatusBar,
    QTreeWidget, QTreeWidgetItem, QAction, QMenuBar, QToolBar,
    QFileDialog, QComboBox, QSpinBox, QCheckBox, QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QFont, QIcon, QColor, QPalette

from core.logger import logger
from core.config import config
from core.api_manager import get_api_manager
from modules.memory.vector_memory import VectorMemory
from modules.tools.emoji_manager import get_emoji_manager
from modules.tools.user_manager import get_user_id_by_name


class LogViewer(QTextEdit):
    """日志查看器"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 9))
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)


class MemoryManager(QWidget):
    """记忆管理模块"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.memory = None
        self.init_ui()
        self.load_memory()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 搜索区域
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索记忆...")
        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self.search_memory)
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_btn)
        
        # 记忆列表
        self.memory_table = QTableWidget()
        self.memory_table.setColumnCount(2)
        self.memory_table.setHorizontalHeaderLabels(["时间", "内容"])
        self.memory_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新")
        self.clear_btn = QPushButton("清空记忆")
        
        self.refresh_btn.clicked.connect(self.load_memory)
        self.clear_btn.clicked.connect(self.clear_memory)
        
        button_layout.addWidget(self.refresh_btn)
        button_layout.addWidget(self.clear_btn)
        
        layout.addLayout(search_layout)
        layout.addWidget(self.memory_table)
        layout.addLayout(button_layout)
    
    def load_memory(self):
        """加载记忆"""
        try:
            self.memory = VectorMemory()
            # 获取最近的记忆
            memories = self.memory.get_recent_memories(100)
            
            self.memory_table.setRowCount(0)
            for i, memory in enumerate(memories):
                self.memory_table.insertRow(i)
                self.memory_table.setItem(i, 0, QTableWidgetItem(memory[:19]))  # 时间部分
                self.memory_table.setItem(i, 1, QTableWidgetItem(memory[20:]))  # 内容部分
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载记忆失败: {str(e)}")
    
    def search_memory(self):
        """搜索记忆"""
        query = self.search_input.text().strip()
        if not query:
            self.load_memory()
            return
        
        try:
            results = self.memory.search_similar(query, top_k=50)
            self.memory_table.setRowCount(0)
            for i, memory in enumerate(results):
                self.memory_table.insertRow(i)
                self.memory_table.setItem(i, 0, QTableWidgetItem(memory[:19]))
                self.memory_table.setItem(i, 1, QTableWidgetItem(memory[20:]))
        except Exception as e:
            QMessageBox.warning(self, "错误", f"搜索记忆失败: {str(e)}")
    
    def clear_memory(self):
        """清空记忆"""
        reply = QMessageBox.question(self, "确认", "确定要清空所有记忆吗？", 
                                   QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                # 清空ChromaDB数据
                import shutil
                chroma_path = os.path.join(os.getcwd(), "chroma_db")
                if os.path.exists(chroma_path):
                    shutil.rmtree(chroma_path)
                    os.makedirs(chroma_path, exist_ok=True)
                QMessageBox.information(self, "成功", "记忆已清空")
                self.load_memory()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"清空记忆失败: {str(e)}")


class MemoryVisualization(QWidget):
    """记忆可视化模块"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 可视化区域（简单实现，显示统计信息）
        stats_group = QGroupBox("记忆统计")
        stats_layout = QFormLayout(stats_group)
        
        # 统计信息
        self.total_memories = QLabel("0")
        self.memory_size = QLabel("0 KB")
        self.model_info = QLabel("加载中...")
        
        stats_layout.addRow("总记忆数:", self.total_memories)
        stats_layout.addRow("记忆库大小:", self.memory_size)
        stats_layout.addRow("嵌入模型:", self.model_info)
        
        # 最近记忆
        recent_group = QGroupBox("最近记忆")
        recent_layout = QVBoxLayout(recent_group)
        self.recent_memories = QTextEdit()
        self.recent_memories.setReadOnly(True)
        recent_layout.addWidget(self.recent_memories)
        
        layout.addWidget(stats_group)
        layout.addWidget(recent_group)
        
        # 更新统计信息
        self.update_stats()
    
    def update_stats(self):
        """更新统计信息"""
        try:
            memory = VectorMemory()
            
            # 获取记忆数量（通过搜索获取近似值）
            recent = memory.get_recent_memories(500)
            self.total_memories.setText(str(len(recent)))
            
            # 计算记忆库大小
            chroma_path = os.path.join(os.getcwd(), "chroma_db")
            if os.path.exists(chroma_path):
                total_size = 0
                for root, dirs, files in os.walk(chroma_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        total_size += os.path.getsize(file_path)
                self.memory_size.setText(f"{total_size / 1024:.2f} KB")
            
            # 显示模型信息
            self.model_info.setText("all-MiniLM-L6-v2")
            
            # 显示最近记忆
            self.recent_memories.clear()
            for mem in recent[:10]:
                self.recent_memories.append(mem)
                
        except Exception as e:
            logger.error("记忆可视化", f"更新统计失败: {e}")


class SystemStatus(QWidget):
    """系统状态模块"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(5000)
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 连接状态
        conn_group = QGroupBox("连接状态")
        conn_layout = QFormLayout(conn_group)
        self.ws_status = QLabel("未连接")
        self.ws_status.setStyleSheet("color: red")
        conn_layout.addRow("WebSocket:", self.ws_status)
        
        # API状态
        api_group = QGroupBox("API状态")
        api_layout = QFormLayout(api_group)
        self.api_status = QLabel("未知")
        api_layout.addRow("NapCat API:", self.api_status)
        
        # 内存状态
        mem_group = QGroupBox("内存状态")
        mem_layout = QFormLayout(mem_group)
        self.mem_usage = QLabel("加载中...")
        mem_layout.addRow("系统内存:", self.mem_usage)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        self.connect_btn = QPushButton("连接NapCat")
        self.disconnect_btn = QPushButton("断开连接")
        self.restart_btn = QPushButton("重启服务")
        
        button_layout.addWidget(self.connect_btn)
        button_layout.addWidget(self.disconnect_btn)
        button_layout.addWidget(self.restart_btn)
        
        layout.addWidget(conn_group)
        layout.addWidget(api_group)
        layout.addWidget(mem_group)
        layout.addLayout(button_layout)
    
    def update_status(self):
        """更新系统状态"""
        try:
            # 更新WebSocket状态
            api_manager = get_api_manager()
            if api_manager and hasattr(api_manager, 'ws') and api_manager.ws:
                self.ws_status.setText("已连接")
                self.ws_status.setStyleSheet("color: green")
            else:
                self.ws_status.setText("未连接")
                self.ws_status.setStyleSheet("color: red")
            
            # 更新API状态
            self.api_status.setText("正常" if self.ws_status.text() == "已连接" else "异常")
            
            # 更新内存使用
            import psutil
            mem = psutil.virtual_memory()
            self.mem_usage.setText(f"{mem.used / 1024 / 1024:.1f} MB / {mem.total / 1024 / 1024:.1f} MB")
            
        except Exception as e:
            logger.error("系统状态", f"更新状态失败: {e}")


class ConfigManager(QWidget):
    """配置管理模块"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 配置文件路径
        path_layout = QHBoxLayout()
        path_label = QLabel("配置文件:")
        self.config_path = QLineEdit(config.config_file)
        path_layout.addWidget(path_label)
        path_layout.addWidget(self.config_path)
        
        # 配置编辑器
        self.config_editor = QTextEdit()
        self.config_editor.setFont(QFont("Consolas", 10))
        
        # 操作按钮
        button_layout = QHBoxLayout()
        self.load_btn = QPushButton("加载")
        self.save_btn = QPushButton("保存")
        self.reset_btn = QPushButton("重置")
        
        button_layout.addWidget(self.load_btn)
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.reset_btn)
        
        layout.addLayout(path_layout)
        layout.addWidget(self.config_editor)
        layout.addLayout(button_layout)
        
        # 连接信号
        self.load_btn.clicked.connect(self.load_config)
        self.save_btn.clicked.connect(self.save_config)
        self.reset_btn.clicked.connect(self.reset_config)
        
        # 初始加载
        self.load_config()
    
    def load_config(self):
        """加载配置"""
        try:
            with open(self.config_path.text(), 'r', encoding='utf-8') as f:
                content = f.read()
            self.config_editor.setText(content)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载配置失败: {str(e)}")
    
    def save_config(self):
        """保存配置"""
        try:
            content = self.config_editor.toPlainText()
            # 验证JSON格式
            json.loads(content)
            
            with open(self.config_path.text(), 'w', encoding='utf-8') as f:
                f.write(content)
            
            QMessageBox.information(self, "成功", "配置已保存")
            # 重新加载配置
            config.load_config()
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "错误", f"JSON格式错误: {str(e)}")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存配置失败: {str(e)}")
    
    def reset_config(self):
        """重置配置"""
        reply = QMessageBox.question(self, "确认", "确定要重置为默认配置吗？",
                                   QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            default_config = {
                "napcat": {
                    "host": "127.0.0.1",
                    "port": 3001,
                    "token": "your_token_here",
                    "group_id": 1087824597
                },
                "llm": {
                    "model": "Qwen/Qwen3.5-27B",
                    "api_key": "your_api_key",
                    "base_url": "https://api.openai.com/v1"
                },
                "emergency": {
                    "phone_number": "110",
                    "adb_path": "adb"
                },
                "tts": {
                    "api_key": "",
                    "region": "",
                    "voice": "zh-CN-XiaoxiaoNeural"
                }
            }
            self.config_editor.setText(json.dumps(default_config, indent=2, ensure_ascii=False))


class MainWindow(QMainWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HuanBot 控制台")
        self.setGeometry(100, 100, 1200, 800)
        
        # 设置GitHub风格样式
        self.set_github_style()
        
        self.init_ui()
    
    def set_github_style(self):
        """设置GitHub风格样式"""
        palette = QPalette()
        # GitHub深色主题配色
        palette.setColor(QPalette.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
        palette.setColor(QPalette.Base, QColor(40, 40, 40))
        palette.setColor(QPalette.AlternateBase, QColor(45, 45, 45))
        palette.setColor(QPalette.ToolTipBase, QColor(0, 0, 0))
        palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
        palette.setColor(QPalette.Text, QColor(255, 255, 255))
        palette.setColor(QPalette.Button, QColor(55, 55, 55))
        palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
        palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.Link, QColor(88, 166, 255))
        palette.setColor(QPalette.Highlight, QColor(88, 166, 255))
        palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
        
        self.setPalette(palette)
        
        # 设置全局样式
        style = """
        QWidget {
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px;
        }
        
        QTabWidget::pane {
            border: 1px solid #555;
        }
        
        QTabBar::tab {
            background: #444;
            color: #fff;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
        
        QTabBar::tab:selected {
            background: #333;
            border-bottom: 2px solid #88a;
        }
        
        QPushButton {
            background: #555;
            color: #fff;
            border: 1px solid #666;
            padding: 6px 12px;
            border-radius: 4px;
        }
        
        QPushButton:hover {
            background: #666;
        }
        
        QPushButton:pressed {
            background: #777;
        }
        
        QLineEdit, QTextEdit {
            background: #444;
            color: #fff;
            border: 1px solid #666;
            padding: 4px;
            border-radius: 4px;
        }
        
        QTableWidget {
            background: #444;
            color: #fff;
            border: 1px solid #666;
        }
        
        QTableWidget::item {
            border: 1px solid #555;
        }
        
        QTableWidget::item:selected {
            background: #88a;
            color: #000;
        }
        
        QHeaderView::section {
            background: #555;
            color: #fff;
            padding: 4px;
            border: 1px solid #666;
        }
        
        QGroupBox {
            border: 1px solid #666;
            border-radius: 4px;
            margin-top: 10px;
        }
        
        QGroupBox::title {
            color: #fff;
            subcontrol-origin: margin;
            left: 10px;
        }
        """
        
        self.setStyleSheet(style)
    
    def init_ui(self):
        """初始化UI"""
        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 标签页
        self.tab_widget = QTabWidget()
        
        # 创建各个标签页
        self.log_viewer = LogViewer()
        self.memory_manager = MemoryManager()
        self.memory_visualization = MemoryVisualization()
        self.system_status = SystemStatus()
        self.config_manager = ConfigManager()
        
        # 添加标签页
        self.tab_widget.addTab(self.log_viewer, "日志")
        self.tab_widget.addTab(self.memory_manager, "记忆管理")
        self.tab_widget.addTab(self.memory_visualization, "记忆可视化")
        self.tab_widget.addTab(self.system_status, "系统状态")
        self.tab_widget.addTab(self.config_manager, "配置管理")
        
        main_layout.addWidget(self.tab_widget)
        
        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("HuanBot 控制台已启动")
    
    def append_log(self, message):
        """添加日志消息"""
        self.log_viewer.append(message)
        # 自动滚动到底部
        cursor = self.log_viewer.textCursor()
        cursor.movePosition(cursor.End)
        self.log_viewer.setTextCursor(cursor)


class LogRedirector:
    """日志重定向器"""
    def __init__(self, window):
        self.window = window
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
    
    def write(self, message):
        """重写write方法"""
        self.original_stdout.write(message)
        if message.strip():
            self.window.append_log(message.strip())
    
    def flush(self):
        """重写flush方法"""
        self.original_stdout.flush()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 创建主窗口
    window = MainWindow()
    
    # 重定向日志
    sys.stdout = LogRedirector(window)
    sys.stderr = LogRedirector(window)
    
    window.show()
    
    # 启动应用
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
