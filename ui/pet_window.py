import os
import logging
import math
import json
import urllib.request
import urllib.error
from PyQt6.QtWidgets import (
    QWidget, QLabel, QMenu, QMessageBox, QGraphicsOpacityEffect, QVBoxLayout, QApplication
)
from PyQt6.QtCore import (
    Qt, QPoint, QPropertyAnimation, QSequentialAnimationGroup, pyqtSlot,
    QEasingCurve, QTimer, QThread, pyqtSignal, QMimeData
)
from PyQt6.QtGui import QRegion, QColor, QFont, QPixmap, QPainter, QBrush, QIcon

from utils.helpers import resource_path, set_auto_start
from ui.settings_dialog import SettingsDialog
from ui.stats_dialog import StatsDialog
from ui.tray_icon import TrayIcon
from ui.todo_window import TodoWindow
from core.sys_monitor import SystemMonitorThread

APP_VERSION = "1.1.9"

logger = logging.getLogger("vibe_pet")


class WordCountMonitorThread(QThread):
    selection_detected = pyqtSignal()
    
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.running = True
        
    def stop(self):
        self.running = False
        self.wait(1000)
        
    def run(self):
        import win32api
        import win32con
        import time
        
        is_pressed = False
        press_pos = (0, 0)
        press_time = 0.0
        last_release_time = 0.0
        
        logger.info("WordCountMonitorThread background loop running.")
        while self.running:
            # 仅在启用划词统计时监控
            if not self.config.get("word_count_enabled", False):
                time.sleep(0.5)
                continue
                
            try:
                # 获取左键状态
                state = win32api.GetAsyncKeyState(win32con.VK_LBUTTON)
                is_down = (state < 0)
                
                if is_down and not is_pressed:
                    # 左键按下
                    is_pressed = True
                    press_pos = win32api.GetCursorPos()
                    press_time = time.time()
                elif not is_down and is_pressed:
                    # 左键释放
                    is_pressed = False
                    release_pos = win32api.GetCursorPos()
                    release_time = time.time()
                    
                    # 距离判定
                    dist = ((release_pos[0] - press_pos[0])**2 + (release_pos[1] - press_pos[1])**2)**0.5
                    
                    # 双击判定
                    time_since_last_release = press_time - last_release_time
                    
                    if dist > 8 or time_since_last_release < 0.4:
                        # 触发信号
                        self.selection_detected.emit()
                        
                    last_release_time = release_time
            except Exception as e:
                logger.error(f"Error checking global mouse selection: {e}")
                
            time.sleep(0.05)
        logger.info("WordCountMonitorThread background loop stopped.")


class PetWindow(QWidget):
    def __init__(self, db_manager, config_manager, reminder_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.config = config_manager
        self.reminder = reminder_manager

        # Window attributes
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        # 关键修复：使用 WA_TranslucentBackground 实现真正的透明背景
        # 之前 setMask() 导致窗口不可见，现在 setMask 已完全禁用
        # 单独使用 WA_TranslucentBackground 可以正常工作（不调用 setMask）
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 从配置读取宠物尺寸（默认200）
        self.pet_size = self.config.get("pet_size", 200)
        # 气泡区域高度：为宠物尺寸的 50%，且至少为 80px
        self.bubble_height = max(80, int(self.pet_size * 0.5))
        window_width = int(self.pet_size * 1.5)
        window_height = self.pet_size + self.bubble_height
        # 确保窗口尺寸不超过屏幕可用区域
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        window_width = min(window_width, screen.width())
        window_height = min(window_height, screen.height())
        self.resize(window_width, window_height)

        # 窗口锁定与鼠标穿透状态
        self.window_locked = self.config.get("window_locked", False)
        self.mouse_passthrough = self.config.get("mouse_passthrough", False)

        self.drag_position = QPoint()
        self.active_dialogs = []  # Keep references to avoid garbage collection

        # --- 动态效果相关 ---
        self._breath_offset = 0          # 呼吸浮动的当前偏移量
        self._base_y = 0                 # 窗口基准Y坐标（用于呼吸浮动）
        self._shake_anim = None          # 摇晃动画引用
        self._blink_anim = None          # 眨眼动画引用
        self._is_shaking = False         # 是否正在摇晃
        self._is_dragging = False        # 是否正在拖拽
        self._drag_start_pos = QPoint()  # 拖拽起始位置
        self.is_snapped = False          # 是否处于贴边隐藏状态
        self.snap_edge = None            # 贴在左侧还是右侧 ("left" / "right")

        self.setup_ui()
        self.setup_tray()
        self.setup_animations()

        # Initialize default animation state
        self.current_state = "idle"
        self.load_animation(self.current_state)

        # Positioning: Bottom right corner of screen
        self.position_on_screen()

        # 应用初始鼠标穿透状态
        self.apply_mouse_passthrough()
        
        # 初始化系统监控面板
        self._sys_monitor_data = {}  # 缓存最新监控数据
        self._sys_monitor_thread = None
        self._apply_sys_monitor_state()

        # 启动时检测更新（延迟5秒，避免影响启动速度）
        QTimer.singleShot(5000, self._check_for_updates)

        # 初始化划词监测线程
        self.word_count_thread = WordCountMonitorThread(self.config, self)
        self.word_count_thread.selection_detected.connect(self.on_selection_detected)
        self.word_count_thread.start()

        # 初始化并按配置显示便签待办窗口
        self.todo_window = None
        if self.config.get("todo_visible", False):
            self.toggle_todo_window(True)

        logger.info("Pet Window initialized.")

    def setup_ui(self):
        window_width = self.width()
        pet_x = (window_width - self.pet_size) // 2
        # 1. Pet Label（动态尺寸）
        self.pet_label = QLabel(self)
        self.pet_label.setGeometry(pet_x, self.bubble_height, self.pet_size, self.pet_size)
        self.pet_label.setScaledContents(True)
        
        # 修复：确保窗口本身有最小尺寸，防止resize为0
        self.setMinimumSize(80, 80)

        # 2. Bubble Label (Top floating speech bubble)
        self.bubble = QLabel(self)
        self.bubble.setWordWrap(True)
        self.bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bubble.setFont(QFont("Microsoft YaHei", 9))
        self.bubble.hide()  # Hidden by default

        # Bubble Style: rounded, white background, black border
        self.bubble.setStyleSheet("""
            QLabel {
                background-color: #ffffff;
                color: #2b2b35;
                border: 2px solid #2b2b35;
                border-radius: 10px;
                padding: 6px;
            }
        """)

        # Opacity effect for bubble fading
        self.bubble_opacity_effect = QGraphicsOpacityEffect(self.bubble)
        self.bubble.setGraphicsEffect(self.bubble_opacity_effect)

        # 3. Mini-Bubble for active app tracking
        # 修复：监控气泡支持动态自适应宽度，初始居中定位，右上方偏移
        self.app_bubble = QLabel(self)
        self.app_bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.app_bubble.setFont(QFont("Microsoft YaHei", 9))  # 字体改为9px
        
        self.app_bubble.setText("📊 当前: 初始化...")
        self.app_bubble.adjustSize()
        w = max(100, min(window_width - 20, self.app_bubble.width() + 12))
        app_bubble_right = min(window_width - 10, pet_x + self.pet_size + 10)
        app_bubble_x = max(10, app_bubble_right - w)
        app_bubble_y = self.bubble_height - 30
        self.app_bubble.setGeometry(app_bubble_x, app_bubble_y, w, 24)
        
        # 应用气泡透明度（初始）
        self._apply_bubble_opacity()
        # Load visibility settings from config
        self.show_app_bubble_enabled = self.config.get("show_app_bubble", True)
        self.app_bubble.setVisible(self.show_app_bubble_enabled)
        
        # 4. 系统监控面板（位于宠物左侧）
        self.sys_panel = QLabel(self)
        self.sys_panel.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.sys_panel.setFont(QFont("Consolas", 8))
        self._apply_sys_panel_style()
        self.sys_panel.hide()

    def _apply_sys_panel_style(self):
        """ Apply light/dark style to sys_panel based on configuration """
        is_dark = (self.config.get("theme_mode", "light") == "dark")
        if is_dark:
            self.sys_panel.setStyleSheet("""
                QLabel {
                    background-color: rgba(43, 43, 53, 200);
                    color: #e0e0e6;
                    border: 1px solid #42424a;
                    border-radius: 6px;
                    padding: 4px 8px;
                }
            """)
        else:
            self.sys_panel.setStyleSheet("""
                QLabel {
                    background-color: rgba(255, 255, 255, 220);
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 6px;
                    padding: 4px 8px;
                }
            """)

    def _apply_msg_style(self, msg, is_warning=False):
        """ Apply light/dark styling to QMessageBox based on theme """
        is_dark = (self.config.get("theme_mode", "light") == "dark")
        if is_dark:
            msg.setStyleSheet(f"""
                QMessageBox {{
                    background-color: #1e1e24;
                    color: #e0e0e6;
                    font-family: "Microsoft YaHei", sans-serif;
                }}
                QLabel {{
                    color: {"#ff8a80" if is_warning else "#cfd8dc"};
                    font-size: {"14px" if is_warning else "12px"};
                    font-weight: {"bold" if is_warning else "normal"};
                }}
                QPushButton {{
                    background-color: {"#c62828" if is_warning else "#37474f"};
                    color: #ffffff;
                    border-radius: 4px;
                    padding: 6px 16px;
                    font-weight: {"bold" if is_warning else "normal"};
                }}
            """)
        else:
            msg.setStyleSheet(f"""
                QMessageBox {{
                    background-color: #f5f5f7;
                    color: #333333;
                    font-family: "Microsoft YaHei", sans-serif;
                }}
                QLabel {{
                    color: {"#d32f2f" if is_warning else "#333333"};
                    font-size: {"14px" if is_warning else "12px"};
                    font-weight: {"bold" if is_warning else "normal"};
                }}
                QPushButton {{
                    background-color: {"#d32f2f" if is_warning else "#e0e0e0"};
                    color: {"#ffffff" if is_warning else "#333333"};
                    border: {"none" if is_warning else "1px solid #cccccc"};
                    border-radius: 4px;
                    padding: 6px 16px;
                    font-weight: {"bold" if is_warning else "normal"};
                }}
            """)

    def _apply_sys_monitor_state(self):
        """ 根据配置应用系统监控状态（启动/停止后台线程，显示/隐藏面板） """
        enabled = self.config.get("sys_monitor_enabled", True)
        if enabled:
            interval = self.config.get("sys_monitor_interval", 2)
            # 如果线程不存在或间隔变化，重新创建
            if (self._sys_monitor_thread is None or 
                not self._sys_monitor_thread.isRunning() or
                self._sys_monitor_thread.interval != interval):
                
                if self._sys_monitor_thread is not None:
                    self._sys_monitor_thread.stop()
                    self._sys_monitor_thread.data_ready.disconnect(self._on_sys_monitor_data)
                
                self._sys_monitor_thread = SystemMonitorThread(interval=interval)
                self._sys_monitor_thread.data_ready.connect(self._on_sys_monitor_data)
                self._sys_monitor_thread.start()
            self._update_sys_monitor()
        else:
            if self._sys_monitor_thread is not None and self._sys_monitor_thread.isRunning():
                self._sys_monitor_thread.stop()
                self._sys_monitor_thread = None
            if hasattr(self, 'sys_panel'):
                self.sys_panel.hide()
    
    def _format_speed(self, kbps):
        """ 格式化网络速度：自动切换 B/s / KB/s / MB/s """
        # kbps 已经是 KB/s 单位
        if kbps >= 1024:
            # MB/s
            return f"{kbps / 1024:.2f}M"
        elif kbps >= 1:
            # KB/s
            return f"{kbps:.1f}K"
        else:
            # B/s (< 1KB)
            return f"{kbps * 1024:.0f}B"

    @pyqtSlot(dict)
    def _on_sys_monitor_data(self, data):
        """ 接收后台线程的监控数据 """
        self._sys_monitor_data = data
        self._update_sys_monitor()
    
    def _update_sys_monitor(self):
        """ 更新系统监控显示 """
        if getattr(self, "is_snapped", False):
            self.sys_panel.hide()
            return
        if not self.config.get("sys_monitor_enabled", True):
            self.sys_panel.hide()
            return
        
        items = self.config.get("sys_monitor_items", {})
        data = self._sys_monitor_data
        
        if not data:
            return
        
        lines = []
        if items.get("cpu", False) and "cpu" in data:
            color = "#ff8a80" if data["cpu"] > 80 else "#81c784" if data["cpu"] < 30 else "#ffd54f"
            lines.append(f"<span style='color:{color}'>▲ CPU {data['cpu']:.0f}%</span>")
        
        if items.get("memory", False) and "memory" in data:
            color = "#ff8a80" if data["memory"] > 80 else "#81c784" if data["memory"] < 50 else "#ffd54f"
            lines.append(f"<span style='color:{color}'>◆ MEM {data['memory']:.0f}%</span>")
        
        if items.get("disk", False):
            # 显示磁盘读写速率（KB/s）
            read_kb = data.get("disk_read", 0)
            write_kb = data.get("disk_write", 0)
            total_kb = read_kb + write_kb
            if total_kb > 0:
                disk_str = self._format_speed(total_kb)
                lines.append(f"<span style='color:#90a4ae'>■ DISK {disk_str}</span>")
            else:
                lines.append(f"<span style='color:#90a4ae'>■ DISK 0K</span>")
        
        if items.get("network", False):
            up = data.get("net_upload", 0)
            down = data.get("net_download", 0)
            up_str = self._format_speed(up)
            down_str = self._format_speed(down)
            lines.append(f"<span style='color:#38bdf8'>▼ {down_str} ▲ {up_str}</span>")
        
        if items.get("gpu", False) and "gpu" in data:
            gpu_val = data.get("gpu", 0)
            color = "#ff8a80" if gpu_val > 80 else "#81c784" if gpu_val < 30 else "#ffd54f"
            lines.append(f"<span style='color:{color}'>● GPU {gpu_val:.0f}%</span>")
        
        if lines:
            self.sys_panel.setText("<br>".join(lines))
            self.sys_panel.adjustSize()
            # 定位：宠物左侧，垂直居中
            panel_x = 5
            panel_y = self.bubble_height + (self.pet_size - self.sys_panel.height()) // 2
            self.sys_panel.setGeometry(panel_x, panel_y, self.sys_panel.width(), self.sys_panel.height())
            self.sys_panel.show()
        else:
            self.sys_panel.hide()
    
    def setup_tray(self):
        self.tray = TrayIcon(self, self)

    def setup_animations(self):
        """ 初始化所有动态效果动画 """
        # --- 呼吸浮动：每 2 秒上下浮动 8 像素，正弦曲线循环 ---
        self._breath_timer = QTimer(self)
        self._breath_timer.timeout.connect(self._on_breath_tick)
        self._breath_timer.start(50)  # 每 50ms 更新一次，约 20fps
        self._breath_time = 0.0       # 呼吸时间累计（秒）

        # --- 眨眼效果：每 4 秒图片快速压扁至 95% 再恢复 ---
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._trigger_blink)
        self._blink_timer.start(4000)  # 每 4 秒触发一次眨眼

    def _on_breath_tick(self):
        """ 呼吸浮动定时器回调：使用正弦曲线计算偏移 """
        if self._is_shaking or self._is_dragging or self.is_snapped:
            # 摇晃、拖拽或已贴边隐藏期间暂停呼吸浮动
            return
        self._breath_time += 0.05  # 50ms = 0.05s
        # 2 秒一个周期，振幅 8 像素
        offset = int(8 * math.sin(self._breath_time * math.pi))
        if offset != self._breath_offset:
            self._breath_offset = offset
            # 移动窗口位置实现浮动效果
            self.move(self.x(), self._base_y + offset)

    def _trigger_blink(self):
        """ 触发眨眼动画：图片快速压扁至 95% 再恢复 """
        if self._is_shaking or self._is_dragging or self.is_snapped:
            return  # 摇晃、拖拽或已贴边隐藏期间不眨眼
        if self._blink_anim and self._blink_anim.state() == QPropertyAnimation.State.Running:
            return  # 已有眨眼动画在运行

        # 创建压扁动画（改变 pet_label 的高度，保持底部对齐）
        original_h = self.pet_label.height()
        blink_h = int(original_h * 0.95)
        original_y = self.pet_label.y()

        # 压扁阶段
        squeeze = QPropertyAnimation(self.pet_label, b"geometry")
        squeeze.setDuration(80)
        squeeze.setStartValue(self.pet_label.geometry())
        squeeze.setEndValue(self.pet_label.geometry().adjusted(0, original_h - blink_h, 0, 0))
        squeeze.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # 恢复阶段
        restore = QPropertyAnimation(self.pet_label, b"geometry")
        restore.setDuration(80)
        restore.setStartValue(self.pet_label.geometry().adjusted(0, original_h - blink_h, 0, 0))
        restore.setEndValue(self.pet_label.geometry())
        restore.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._blink_anim = QSequentialAnimationGroup(self)
        self._blink_anim.addAnimation(squeeze)
        self._blink_anim.addAnimation(restore)
        self._blink_anim.start()

    def _trigger_shake(self):
        """ 触发点击摇晃动画：快速左右摇摆 2 次 """
        if self._is_shaking:
            return
        self._is_shaking = True

        base_x = self.x()
        shake_amount = max(10, int(self.pet_size * 0.08))  # 摇摆幅度随尺寸变化

        # 创建左右摇摆序列
        seq = QSequentialAnimationGroup(self)

        positions = [
            base_x - shake_amount,   # 左
            base_x + shake_amount,   # 右
            base_x - shake_amount,   # 左
            base_x + shake_amount,   # 右
            base_x                   # 回中
        ]

        for i, target_x in enumerate(positions):
            anim = QPropertyAnimation(self, b"pos")
            anim.setDuration(60)
            anim.setStartValue(self.pos() if i == 0 else QPoint(positions[i-1], self.y()))
            anim.setEndValue(QPoint(target_x, self.y()))
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            seq.addAnimation(anim)

        def on_shake_finished():
            self._is_shaking = False
            # 恢复基准位置
            self._base_y = self.y()

        seq.finished.connect(on_shake_finished)
        self._shake_anim = seq
        seq.start()

    def position_on_screen(self):
        """ 放置宠物窗口：优先使用上次保存的位置，否则右下角 """
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        
        # 尝试读取上次保存的位置
        saved_x = self.config.get("window_x")
        saved_y = self.config.get("window_y")
        
        if saved_x is not None and saved_y is not None:
            # 使用上次位置，但要确保在屏幕范围内
            x = max(0, min(saved_x, screen.width() - self.width()))
            y = max(0, min(saved_y, screen.height() - self.height()))
            self.move(x, y)
            self._base_y = y
            logger.info(f"[位置] 窗口恢复到上次位置 ({x}, {y})")
        else:
            # 首次启动：右下角
            x = screen.width() - self.width() - 20
            y = screen.height() - self.height() - 20
            self.move(x, y)
            self._base_y = y
            logger.info(f"[位置] 首次启动，窗口放置到右下角 ({x}, {y})，屏幕: {screen.width()}x{screen.height()}")

    def ensure_visible_on_screen(self):
        """ 确保窗口在屏幕可视区域内，防止坐标越界导致窗口不可见 """
        if getattr(self, "is_snapped", False):
            return
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        x, y = self.x(), self.y()

        # 如果坐标为负数或超出屏幕，重置到屏幕中央
        if x < 0 or y < 0 or x > screen.width() - 50 or y > screen.height() - 50:
            center_x = (screen.width() - self.width()) // 2
            center_y = (screen.height() - self.height()) // 2
            self.move(center_x, center_y)
            self._base_y = center_y
            logger.info(f"[坐标修复] 窗口原位置越界 ({x},{y})，已重置到屏幕中央 ({center_x},{center_y})")

    def set_pet_size(self, size):
        """ 动态调整宠物窗口大小 """
        if getattr(self, "is_snapped", False):
            self.unsnap_window(animate=False)
        size = max(80, min(400, size))  # 限制范围 80~400
        self.pet_size = size
        self.bubble_height = max(80, int(size * 0.5))
        
        window_width = int(size * 1.5)
        window_height = size + self.bubble_height
        
        # 确保窗口尺寸不超过屏幕可用区域
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        window_width = min(window_width, screen.width())
        window_height = min(window_height, screen.height())
        
        self.resize(window_width, window_height)

        # 重新调整各组件几何位置
        pet_x = (window_width - size) // 2
        self.pet_label.setGeometry(pet_x, self.bubble_height, size, size)

        # 重新调整监控气泡大小和位置，防止超出窗口被裁剪
        self.app_bubble.adjustSize()
        w = max(100, min(window_width - 20, self.app_bubble.width() + 12))
        app_bubble_right = min(window_width - 10, pet_x + size + 10)
        app_bubble_x = max(10, app_bubble_right - w)
        app_bubble_y = self.bubble_height - 30
        self.app_bubble.setGeometry(app_bubble_x, app_bubble_y, w, 24)

        # 确保窗口仍在屏幕可视区域内
        self.ensure_visible_on_screen()

        # 重新加载当前动画以适配新尺寸
        self.load_animation(self.current_state)
        # 禁用setMask避免窗口不可见
        # self.update_mask_region()
        logger.info(f"Pet size changed to {size}px, window: {window_width}x{window_height}px")

    def load_animation(self, state_name):
        """ 加载 GIF 动态图，若不存在则回退至静态 PNG 宠物图片 """
        from PyQt6.QtGui import QMovie
        
        # 1. 尝试加载 GIF 动画
        gif_path = resource_path(f"assets/{state_name}.gif")
        if os.path.exists(gif_path):
            # 停止当前可能正在播放的 QMovie
            old_movie = self.pet_label.movie()
            if old_movie:
                old_movie.stop()
                
            movie = QMovie(gif_path)
            # 设置缩放以适配当前宠物大小
            movie.setScaledSize(self.pet_label.size())
            self.pet_label.setMovie(movie)
            movie.start()
            self.current_state = state_name
            # self.update_mask_region()
            logger.info(f"[动画加载] 成功加载并播放 GIF 动画: {gif_path}")
            return

        # 2. 如果 GIF 不存在，回退到静态 PNG 模式
        old_movie = self.pet_label.movie()
        if old_movie:
            old_movie.stop()
            self.pet_label.setMovie(None)

        img_path = resource_path(f"assets/pet_{state_name}.png")
        pixmap = QPixmap()
        load_ok = False

        if os.path.exists(img_path):
            if pixmap.load(img_path):
                load_ok = True
                logger.info(f"[图片加载] 成功: {img_path} ({pixmap.width()}x{pixmap.height()})")
            else:
                logger.error(f"[图片加载] 文件存在但加载失败: {img_path}")
        else:
            logger.error(f"[图片加载] 文件不存在: {img_path}")

        if not load_ok:
            logger.warning(f"[图片加载] 创建红色占位块: {img_path}")
            pixmap = QPixmap(self.pet_size, self.pet_size)
            # 亮红色背景，绝对肉眼可见
            pixmap.fill(QColor("#FF4444"))

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # 白色文字提示
            painter.setPen(QColor("#FFFFFF"))
            font_size = max(12, int(self.pet_size * 0.08))
            font = QFont("Microsoft YaHei", font_size, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "图片缺失")
            painter.end()
        else:
            # Smooth scaling to fit pet area while maintaining aspect ratio
            pixmap = pixmap.scaled(
                self.pet_size, self.pet_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

        self.pet_label.setPixmap(pixmap)
        self.pet_label.setFixedSize(self.pet_size, self.pet_size)
        self.current_state = state_name
        # 关键修复：暂时禁用setMask，它可能导致窗口完全不可见
        # self.update_mask_region()
        logger.info(f"[load_animation] 完成，pixmap尺寸: {pixmap.size()}")

    @pyqtSlot()
    def update_mask_region(self, frame_number=0):
        """ Update window mask so transparent parts of the pet image are click-through.
        
        ⚠️ 已禁用：setMask() 在 Windows + PNG透明图片 + PyInstaller打包环境下
        会导致窗口完全不可见。暂时保留函数但不做任何操作。
        透明效果由 WA_NoSystemBackground + 自绘处理。
        """
        # setMask 已禁用，参见上方注释
        pass

    def _apply_bubble_opacity(self):
        """ 应用气泡背景透明度设置 """
        # 从配置读取气泡透明度（默认1.0=不透明）
        opacity = self.config.get("bubble_opacity", 1.0)
        alpha = int(opacity * 255)
        is_dark = (self.config.get("theme_mode", "light") == "dark")
        if is_dark:
            self.bubble.setStyleSheet(f"""
                QLabel {{
                    background-color: rgba(43, 43, 53, {alpha});
                    color: #e0e0e6;
                    border: 2px solid #42424a;
                    border-radius: 10px;
                    padding: 6px;
                }}
            """)
            self.app_bubble.setStyleSheet(f"""
                QLabel {{
                    background-color: rgba(43, 43, 53, {alpha});
                    color: #e0e0e6;
                    border: 1px solid #42424a;
                    border-radius: 6px;
                    padding: 2px;
                    font-size: 9px;
                }}
            """)
        else:
            self.bubble.setStyleSheet(f"""
                QLabel {{
                    background-color: rgba(255, 255, 255, {alpha});
                    color: #2b2b35;
                    border: 2px solid #cccccc;
                    border-radius: 10px;
                    padding: 6px;
                }}
            """)
            self.app_bubble.setStyleSheet(f"""
                QLabel {{
                    background-color: rgba(255, 255, 255, {alpha});
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 6px;
                    padding: 2px;
                    font-size: 9px;
                }}
            """)

    def show_bubble_message(self, text):
        """ Trigger floating bubble animation with text """
        if getattr(self, "is_snapped", False):
            return
        # Hide app bubble to avoid layout collision
        if self.app_bubble.isVisible():
            self.app_bubble.hide()

        self.bubble.setText(text)

        # 重置气泡最大最小尺寸限制以正确重新计算大小
        self.bubble.setMinimumSize(0, 0)
        self.bubble.setMaximumSize(9999, 9999)
        self.bubble.adjustSize()

        # 限制气泡最大宽度为窗口宽度 - 20px，防止超出窗口被裁剪
        window_width = self.width()
        max_w = window_width - 20
        w = self.bubble.width()
        h = self.bubble.height()

        # 始终确保如果是折行或过宽，重新准确测算高度以防止文字截断
        if w > max_w:
            w = max_w
        
        # 针对固定宽度进行折行高度测算 (包含 padding 6px + border 2px，双侧总和 16px)
        padding_horizontal = 16
        padding_vertical = 16
        text_w = w - padding_horizontal
        
        from PyQt6.QtCore import QRect
        metrics = self.bubble.fontMetrics()
        rect = metrics.boundingRect(
            QRect(0, 0, text_w, 9999),
            Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter,
            text
        )
        h = rect.height() + padding_vertical

        # 固定几何尺寸
        self.bubble.setFixedSize(w, h)

        # 水平居中对齐，保证气泡在窗口内部且视觉上平衡对称
        bubble_x = (window_width - w) // 2
        # 垂直位置在宠物上方，间距 5px
        bubble_y = self.bubble_height - h - 5
        self.bubble.setGeometry(bubble_x, max(0, bubble_y), w, h)

        # 应用当前透明度设置
        self._apply_bubble_opacity()

        self.bubble.show()

        # Stop active animation group if running
        if hasattr(self, "_bubble_anim_group") and self._bubble_anim_group:
            self._bubble_anim_group.stop()

        # Reset opacity to 0
        self.bubble_opacity_effect.setOpacity(0.0)

        # Fade In
        fade_in = QPropertyAnimation(self.bubble_opacity_effect, b"opacity")
        fade_in.setDuration(300)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)

        # Fade Out
        fade_out = QPropertyAnimation(self.bubble_opacity_effect, b"opacity")
        fade_out.setDuration(1000)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)

        # Sequential Group: In -> wait 3s -> Out
        self._bubble_anim_group = QSequentialAnimationGroup()
        self._bubble_anim_group.addAnimation(fade_in)
        self._bubble_anim_group.addPause(3000)
        self._bubble_anim_group.addAnimation(fade_out)

        # Hide bubble and restore app bubble on completion
        def on_warning_bubble_finished():
            self.bubble.hide()
            if self.show_app_bubble_enabled:
                self.app_bubble.show()
                # self.update_mask_region(0)

        self._bubble_anim_group.finished.connect(on_warning_bubble_finished)
        self._bubble_anim_group.start()

    # --- 便签待办功能 ---
    def toggle_todo_window(self, visible=None):
        """ 切换便签待办窗口的显示与隐藏 """
        if visible is None:
            visible = not (self.todo_window is not None and self.todo_window.isVisible())

        self.config.set("todo_visible", visible)

        if visible:
            if self.todo_window is None:
                self.todo_window = TodoWindow(self.db, self.config, self, None)
            self.todo_window.apply_theme()
            self.todo_window.reload_todos()
            self.todo_window.show()
            self.todo_window.raise_()
        else:
            if self.todo_window is not None:
                self.todo_window.hide()

        # 同步托盘菜单与右键菜单勾选状态
        if hasattr(self, 'tray') and self.tray:
            self.tray.act_todo.setChecked(visible)
        
        logger.info(f"Todo window visibility toggled to: {visible}")

    def on_todo_window_toggled(self, visible):
        """ 便签窗口内部关闭回调 """
        if hasattr(self, 'tray') and self.tray:
            self.tray.act_todo.setChecked(visible)

    # --- 窗口锁定功能 ---
    def set_window_locked(self, locked):
        """ 设置窗口位置是否锁定（禁止拖拽移动） """
        self.window_locked = locked
        self.config.set("window_locked", locked)
        # 同步托盘菜单的勾选状态
        if hasattr(self, 'tray') and self.tray:
            self.tray.act_lock.setChecked(locked)
        logger.info(f"Window locked set to: {locked}")

    # --- 鼠标穿透功能 ---
    def set_mouse_passthrough(self, enabled):
        """ 设置鼠标穿透模式（点击穿透到下层窗口） """
        self.mouse_passthrough = enabled
        self.config.set("mouse_passthrough", enabled)
        self.apply_mouse_passthrough()
        # 同步托盘菜单的勾选状态
        if hasattr(self, 'tray') and self.tray:
            self.tray.act_passthrough.setChecked(enabled)
        logger.info(f"Mouse passthrough set to: {enabled}")

    def apply_mouse_passthrough(self):
        """ 应用鼠标穿透状态到窗口 """
        if self.mouse_passthrough:
            # 启用穿透：使用 Win32 API 设置窗口为点击穿透模式
            self._set_click_through(True)
        else:
            # 禁用穿透：恢复普通窗口模式
            self._set_click_through(False)
            # self.update_mask_region()

    def _set_click_through(self, enabled):
        """
        使用 Win32 API 设置/取消窗口的点击穿透属性。
        """
        try:
            import win32gui
            import win32con
            hwnd = int(self.winId())
            
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            
            if enabled:
                # 添加 WS_EX_TRANSPARENT（点击穿透）
                # 确保 WS_EX_LAYERED 也被设置（虽然后者由 Qt translucent background 自动设置）
                new_style = ex_style | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED
                if new_style != ex_style:
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, new_style)
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                logger.info("Mouse passthrough enabled via Win32 API")
            else:
                # 移除 WS_EX_TRANSPARENT
                new_style = ex_style & ~win32con.WS_EX_TRANSPARENT
                if new_style != ex_style:
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, new_style)
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
                logger.info("Mouse passthrough disabled via Win32 API")
        except Exception as e:
            logger.error(f"Failed to set click-through: {e}")
            # 回退到 Qt 方式
            if enabled:
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            else:
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    # --- Mouse Event Handlers for Dragging ---
    def mousePressEvent(self, event):
        if self.mouse_passthrough:
            event.ignore()
            return
        if getattr(self, "is_snapped", False):
            if event.button() == Qt.MouseButton.LeftButton:
                self.unsnap_window()
                event.accept()
                return
        if self.window_locked:
            event.ignore()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._drag_start_pos = event.globalPosition().toPoint()
            self._is_dragging = False  # 先标记为未拖拽，在 mouseMove 中确认
            # 触发点击摇晃效果（仅在未开始拖拽时）
            self._trigger_shake()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.mouse_passthrough:
            event.ignore()
            return
        if self.window_locked:
            event.ignore()
            return
        if event.buttons() == Qt.MouseButton.LeftButton:
            # 检测是否真正开始拖拽（移动超过 5 像素才认为是拖拽）
            if not self._is_dragging:
                dist = (event.globalPosition().toPoint() - self._drag_start_pos).manhattanLength()
                if dist > 5:
                    self._is_dragging = True
                else:
                    event.accept()
                    return
            self.move(event.globalPosition().toPoint() - self.drag_position)
            # 更新基准Y坐标（拖拽后呼吸浮动以此为准）
            self._base_y = self.y()
            # 保存位置到配置
            self.config.set("window_x", self.x())
            self.config.set("window_y", self.y())
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.mouse_passthrough:
            event.ignore()
            return
        if self.window_locked:
            event.ignore()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            was_dragging = self._is_dragging
            self._is_dragging = False
            if was_dragging:
                self.check_and_snap()
            event.accept()

    def check_and_snap(self):
        """ 检测窗口是否靠近屏幕左右边缘并触发贴边收缩 """
        if not self.config.get("screen_snapping", True):
            return

        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        
        win_x = self.x()
        win_width = self.width()
        
        dist_left = win_x - screen.x()
        dist_right = (screen.x() + screen.width()) - (win_x + win_width)
        
        # 贴边检测阈值：20 像素
        threshold = 20
        # 收缩后露出的身体大小：根据宠物大小自适应（至少60，约占大小的35%）
        sliver = max(60, int(self.pet_size * 0.35))
        
        pet_x = self.pet_label.x()
        
        if dist_left < threshold:
            # 贴左侧：露出 pet_label 右端 sliver 像素
            target_x = screen.x() + sliver - (pet_x + self.pet_size)
            self.snap_to_edge("left", target_x)
        elif dist_right < threshold:
            # 贴右侧：露出 pet_label 左端 sliver 像素
            target_x = (screen.x() + screen.width()) - sliver - pet_x
            self.snap_to_edge("right", target_x)

    def snap_to_edge(self, edge, target_x):
        """ 播放贴边收缩动画并设置状态 """
        self.is_snapped = True
        self.snap_edge = edge
        
        # 隐藏气泡与监控面板
        self.bubble.hide()
        self.app_bubble.hide()
        self.sys_panel.hide()
        
        # 如果当前启用了鼠标穿透，在贴边期间临时关闭它，以便能响应点击还原
        if self.mouse_passthrough:
            self._set_click_through(False)
        
        # 播放滑动动画
        self.snap_animation = QPropertyAnimation(self, b"pos")
        self.snap_animation.setDuration(300)
        self.snap_animation.setStartValue(self.pos())
        self.snap_animation.setEndValue(QPoint(int(target_x), self.y()))
        self.snap_animation.setEasingCurve(QEasingCurve.Type.OutQuad)
        
        def on_finished():
            self.move(int(target_x), self.y())
            logger.info(f"[贴边隐藏] 桌宠成功贴边收缩到 {edge} 侧 (x={self.x()})")
            
        self.snap_animation.finished.connect(on_finished)
        self.snap_animation.start()

    def unsnap_window(self, animate=True):
        """ 展开贴边隐藏状态，滑出还原窗口 """
        if not getattr(self, "is_snapped", False):
            return

        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        
        pet_x = self.pet_label.x()
        
        if self.snap_edge == "left":
            # 还原到左边缘对齐（pet_label 的左侧对齐屏幕左边缘）
            target_x = screen.x() - pet_x
        else:
            # 还原到右边缘对齐（pet_label 的右侧对齐屏幕右边缘）
            target_x = (screen.x() + screen.width()) - (pet_x + self.pet_size)
            
        # 限制在屏幕内，防止超出
        target_x = max(screen.x(), min(target_x, screen.x() + screen.width() - self.width()))
        
        if animate:
            self.snap_animation = QPropertyAnimation(self, b"pos")
            self.snap_animation.setDuration(300)
            self.snap_animation.setStartValue(self.pos())
            self.snap_animation.setEndValue(QPoint(int(target_x), self.y()))
            self.snap_animation.setEasingCurve(QEasingCurve.Type.OutQuad)
            
            def on_finished():
                self.move(int(target_x), self.y())
                self.is_snapped = False
                self.snap_edge = None
                # 更新坐标并保存
                self._base_y = self.y()
                self.config.set("window_x", self.x())
                self.config.set("window_y", self.y())
                
                # 恢复鼠标穿透状态（如果启用的话）
                self.apply_mouse_passthrough()
                
                # 恢复气泡
                if self.show_app_bubble_enabled:
                    self.app_bubble.show()
                self._update_sys_monitor()
                logger.info("[贴边隐藏] 桌宠还原展开")
                
            self.snap_animation.finished.connect(on_finished)
            self.snap_animation.start()
        else:
            self.move(int(target_x), self.y())
            self.is_snapped = False
            self.snap_edge = None
            self._base_y = self.y()
            self.config.set("window_x", self.x())
            self.config.set("window_y", self.y())
            self.apply_mouse_passthrough()
            if self.show_app_bubble_enabled:
                self.app_bubble.show()
            self._update_sys_monitor()
            logger.info("[贴边隐藏] 桌宠无动画直接展开")

    def mouseDoubleClickEvent(self, event):
        if self.mouse_passthrough:
            event.ignore()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            # 双击时停止拖拽状态
            self._is_dragging = False
            # Double click opens statistics
            self.open_stats_dialog()
            event.accept()

    def contextMenuEvent(self, event):
        """ Right click context menu """
        menu = QMenu(self)

        act_stats = menu.addAction("今日统计")
        act_settings = menu.addAction("设置")

        # Add checkable option to show/hide application bubble
        act_bubble = menu.addAction("显示监控气泡")
        act_bubble.setCheckable(True)
        act_bubble.setChecked(self.show_app_bubble_enabled)

        # 窗口锁定选项
        act_lock = menu.addAction("锁定窗口位置")
        act_lock.setCheckable(True)
        act_lock.setChecked(self.window_locked)

        # 鼠标穿透选项
        act_passthrough = menu.addAction("鼠标穿透")
        act_passthrough.setCheckable(True)
        act_passthrough.setChecked(self.mouse_passthrough)

        # 便签待办选项
        act_todo = menu.addAction("便签待办")
        act_todo.setCheckable(True)
        act_todo.setChecked(self.todo_window is not None and self.todo_window.isVisible())

        menu.addSeparator()
        act_about = menu.addAction("关于")
        menu.addSeparator()
        act_exit = menu.addAction("退出")

        # Apply theme-based style to menu
        is_dark = (self.config.get("theme_mode", "light") == "dark")
        if is_dark:
            menu.setStyleSheet("""
                QMenu {
                    background-color: #2b2b35;
                    color: #cfd8dc;
                    border: 1px solid #455a64;
                    border-radius: 4px;
                    font-family: "Microsoft YaHei", sans-serif;
                }
                QMenu::item {
                    padding: 6px 20px;
                }
                QMenu::item:selected {
                    background-color: #37474f;
                    color: #ffffff;
                }
            """)
        else:
            menu.setStyleSheet("""
                QMenu {
                    background-color: #ffffff;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    font-family: "Microsoft YaHei", sans-serif;
                }
                QMenu::item {
                    padding: 6px 20px;
                }
                QMenu::item:selected {
                    background-color: #e0e0e0;
                    color: #333333;
                }
            """)

        action = menu.exec(self.mapToGlobal(event.pos()))
        if action == act_stats:
            self.open_stats_dialog()
        elif action == act_settings:
            self.open_settings_dialog()
        elif action == act_bubble:
            self.show_app_bubble_enabled = not self.show_app_bubble_enabled
            self.config.set("show_app_bubble", self.show_app_bubble_enabled)
            if not self.bubble.isVisible() or self.bubble_opacity_effect.opacity() == 0.0:
                self.app_bubble.setVisible(self.show_app_bubble_enabled)
            else:
                self.app_bubble.setVisible(False)
            # self.update_mask_region(0)
            logger.info(f"Show app bubble toggled to: {self.show_app_bubble_enabled}")
        elif action == act_lock:
            self.set_window_locked(not self.window_locked)
        elif action == act_passthrough:
            self.set_mouse_passthrough(not self.mouse_passthrough)
        elif action == act_todo:
            self.toggle_todo_window()
        elif action == act_about:
            self.open_about_dialog()
        elif action == act_exit:
            self.quit_application()

    # --- Dialog Launchers ---
    def open_stats_dialog(self):
        # Prevent duplicate dialogs
        for d in self.active_dialogs:
            if isinstance(d, StatsDialog):
                d.raise_()
                d.activateWindow()
                return

        dialog = StatsDialog(self.db, self.config, None)
        dialog.theme_changed.connect(self.on_settings_changed)
        self.active_dialogs.append(dialog)
        dialog.finished.connect(lambda: self.active_dialogs.remove(dialog))
        dialog.show()

    def open_settings_dialog(self):
        # Prevent duplicate dialogs
        for d in self.active_dialogs:
            if isinstance(d, SettingsDialog):
                d.raise_()
                d.activateWindow()
                return

        dialog = SettingsDialog(self.config, None)
        # 连接设置变更信号
        dialog.settings_changed.connect(self.on_settings_changed)
        self.active_dialogs.append(dialog)
        dialog.finished.connect(lambda: self.active_dialogs.remove(dialog))
        dialog.show()

    @pyqtSlot()
    def on_settings_changed(self):
        """ 设置变更后的回调，应用新配置 """
        # 如果关闭了贴边隐藏，且当前窗口处于贴边收缩状态，则立即还原
        if not self.config.get("screen_snapping", True) and getattr(self, "is_snapped", False):
            self.unsnap_window(animate=False)

        # 重新加载尺寸
        new_size = self.config.get("pet_size", 200)
        if new_size != self.pet_size:
            self.set_pet_size(new_size)

        # 重新加载锁定状态
        self.window_locked = self.config.get("window_locked", False)

        # 重新加载鼠标穿透状态
        new_passthrough = self.config.get("mouse_passthrough", False)
        if new_passthrough != self.mouse_passthrough:
            self.set_mouse_passthrough(new_passthrough)

        # 重新加载气泡显示状态
        self.show_app_bubble_enabled = self.config.get("show_app_bubble", True)
        if not self.bubble.isVisible() or self.bubble_opacity_effect.opacity() == 0.0:
            self.app_bubble.setVisible(self.show_app_bubble_enabled)

        # 重新应用气泡透明度
        self._apply_bubble_opacity()
        
        # 重新应用系统监控设置
        self._apply_sys_monitor_state()
        
        # 重新应用系统监控面板的主题样式
        self._apply_sys_panel_style()

        # 重新应用主题与显示状态到便签窗口
        if getattr(self, "todo_window", None) is not None:
            self.todo_window.apply_theme()
        todo_visible = self.config.get("todo_visible", False)
        self.toggle_todo_window(todo_visible)

        # 重新应用主题到所有活动对话框
        theme_val = self.config.get("theme_mode", "light")
        for d in self.active_dialogs:
            if hasattr(d, "apply_styles"):
                # 如果是 StatsDialog，同步它的 self.theme_mode 并刷新
                if isinstance(d, StatsDialog):
                    d.theme_mode = theme_val
                    btn_text = "暗黑模式" if theme_val == "light" else "明亮模式"
                    if hasattr(d, "btn_theme"):
                        d.btn_theme.setText(btn_text)
                    d.apply_styles()
                    d.refresh_data()
                elif isinstance(d, SettingsDialog):
                    if hasattr(d, "combo_theme"):
                        d.combo_theme.setCurrentIndex(1 if theme_val == "light" else 0)
                    d.apply_styles()
                else:
                    d.apply_styles()
            elif isinstance(d, QMessageBox):
                is_warning = (d.icon() == QMessageBox.Icon.Warning)
                self._apply_msg_style(d, is_warning=is_warning)

        logger.info("Settings applied to pet window and all active dialogs.")

    @pyqtSlot(str, str, bool, int, int)
    def on_status_updated(self, app_name, category, is_idle, today_total_s, today_game_s):
        """ Handle status updates from the monitor thread """
        # 1. Update system tray hover tooltip
        self.tray.update_tooltip(today_total_s, today_game_s)

        # 2. Update current app bubble text
        if is_idle:
            text = "📊 当前: 挂机中"
        else:
            text = f"📊 当前: {app_name}"

        self.app_bubble.setText(text)
        
        # 动态自适应调整大小 and 位置，防止进程名过长时气泡显示不全
        self.app_bubble.adjustSize()
        window_width = self.width()
        pet_x = self.pet_label.x()
        
        w = max(100, min(window_width - 20, self.app_bubble.width() + 12))
        # 尽量让 app_bubble 右端与宠物右端对齐偏移 10px，但不能超出右窗口边界
        app_bubble_right = min(window_width - 10, pet_x + self.pet_size + 10)
        app_bubble_x = max(10, app_bubble_right - w)
        app_bubble_y = self.bubble_height - 30
        self.app_bubble.setGeometry(app_bubble_x, app_bubble_y, w, 24)

        if getattr(self, "is_snapped", False):
            self.app_bubble.hide()

    def open_about_dialog(self):
        msg = QMessageBox(None)
        self.active_dialogs.append(msg)
        msg.finished.connect(lambda: self.active_dialogs.remove(msg))
        msg.setWindowTitle("关于 VibePet")
        
        # 设置窗口图标
        icon_path = resource_path("assets/icon.png")
        msg.setWindowIcon(QIcon(icon_path))
        
        # 设置对话框主体图标
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            msg.setIconPixmap(scaled_pixmap)
        
        is_dark = (self.config.get("theme_mode", "light") == "dark")
        link_color = "#81c784" if is_dark else "#2e7d32"
        
        msg.setText(
            f"<h3>VibePet 桌面宠物软件</h3>"
            f"<p><b>版本:</b> {APP_VERSION}</p>"
            f"<p><b>作者:</b> YTU22</p>"
            f"<p><b>GitHub:</b> <a href='https://github.com/YTU22/vibepet' style='color:{link_color};'>github.com/YTU22/vibepet</a></p>"
            f"<p><b>官方网站:</b> <a href='https://vibeharbor.art' style='color:{link_color};'>vibeharbor.art</a></p>"
            f"<p>实时监测软件时长，守护您的作息与健康！</p>"
        )
        self._apply_msg_style(msg, is_warning=False)
        msg.exec()

    @pyqtSlot()
    def trigger_fatigue_warning(self):
        """ Forceful warning dialog for daily overtime """
        msg = QMessageBox(None)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("VibePet 健康警告")
        msg.setText("您今日累计使用电脑已超过 8 小时！\n建议您现在离开电脑，闭眼休息 10 分钟或起身活动活动！")
        self._apply_msg_style(msg, is_warning=True)
        msg.show()
        # Non-blocking, stays on screen
        self.active_dialogs.append(msg)
        msg.finished.connect(lambda: self.active_dialogs.remove(msg))

    @pyqtSlot()
    def on_selection_detected(self):
        """ 监测到可能存在划词选择，执行剪贴板备份、模拟复制及字数统计 """
        if not self.config.get("word_count_enabled", False):
            return
            
        clipboard = QApplication.clipboard()
        # 1. 备份原先的剪贴板内容 (MimeData 包含各种格式，能进行深度还原，避免指针实效)
        old_mime = clipboard.mimeData()
        backup_mime = QMimeData()
        if old_mime:
            for fmt in old_mime.formats():
                try:
                    backup_mime.setData(fmt, old_mime.data(fmt))
                except Exception:
                    pass
        
        # 2. 发送全局 Ctrl+C 键
        import win32api
        import win32con
        import time
        
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(0x43, 0, 0, 0) # 'C'键
        time.sleep(0.05) # 给 Windows 几十毫秒让系统处理按键与拷贝
        win32api.keybd_event(0x43, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        
        # 3. 读取复制的文字并统计
        time.sleep(0.01)
        selected_text = clipboard.text()
        
        # 4. 立即还原原先的剪贴板内容，使用户无感知
        if old_mime:
            clipboard.setMimeData(backup_mime)
            
        # 5. 进行字数计算
        if not selected_text:
            return
            
        selected_text = selected_text.strip()
        if not selected_text:
            return
            
        # 汉字数与英文单词数统计
        import re
        # 汉字
        cn_chars = re.findall(r'[\u4e00-\u9fff]', selected_text)
        cn_count = len(cn_chars)
        
        # 英文/数字单词 (中文字符替换为空格)
        text_no_cn = re.sub(r'[\u4e00-\u9fff]', ' ', selected_text)
        en_words = re.findall(r'[a-zA-Z0-9\-\']+', text_no_cn)
        en_count = len(en_words)
        
        total_count = cn_count + en_count
        if total_count <= 0:
            return
            
        # 6. 显示字数 (始终展示在对话气泡中)
        msg = f"📝 选区字数: {total_count} 字"
        if cn_count > 0 and en_count > 0:
            msg += f"\n({cn_count}汉字 + {en_count}单词)"
        self.show_bubble_message(msg)
        # 3秒后自动隐藏气泡
        QTimer.singleShot(3000, self.bubble.hide)

    def quit_application(self):
        """ Gracefully exit application """
        logger.info("Application shutdown requested via UI context menu.")
        # 停止系统监控线程
        if hasattr(self, '_sys_monitor_thread') and self._sys_monitor_thread:
            self._sys_monitor_thread.stop()
        # 停止划词监测线程
        if hasattr(self, 'word_count_thread') and self.word_count_thread:
            self.word_count_thread.stop()
            
        # Trigger application exit
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    def paintEvent(self, event):
        """ 自绘窗口背景：在透明窗口上绘制宠物图片，确保可见 """
        # 让QLabel自己绘制内容，但在贴边隐藏状态下绘制极低透明度的背景以捕获点击
        super().paintEvent(event)
        if getattr(self, "is_snapped", False):
            from PyQt6.QtGui import QPainter, QColor
            painter = QPainter(self)
            # 使用 alpha = 1 (几乎完全透明但能接收点击) 的颜色填充可见区域
            fill_color = QColor(0, 0, 0, 1)
            
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().availableGeometry()
            win_x = self.x()
            
            if self.snap_edge == "left":
                # 贴左侧，可见部分在窗口右侧：从 max(0, screen.x() - win_x) 到 self.width()
                start_x = max(0, screen.x() - win_x)
                w = self.width() - start_x
                if w > 0:
                    painter.fillRect(start_x, 0, w, self.height(), fill_color)
            elif self.snap_edge == "right":
                # 贴右侧，可见部分在窗口左侧：从 0 到 max(0, (screen.x() + screen.width()) - win_x)
                w = max(0, (screen.x() + screen.width()) - win_x)
                if w > 0:
                    painter.fillRect(0, 0, w, self.height(), fill_color)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'tray') and self.tray:
            self.tray.update_menu_text()

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, 'tray') and self.tray:
            self.tray.update_menu_text()

    def closeEvent(self, event):
        # Make sure we don't accidentally close if window close event fires
        # We handle quit explicitly through quit_application
        self.tray.hide()
        event.accept()

    def _check_for_updates(self):
        """ 启动时检测网站 API 是否有新版本 """
        try:
            req = urllib.request.Request(
                "https://vibeharbor.art/api/github/vibepet/latest",
                headers={"User-Agent": "VibePet-UpdateChecker"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = data.get("tag_name", "").lstrip("v")
            if not latest:
                return
            
            def parse_ver(v):
                try:
                    parts = [int(x) for x in v.split(".")]
                    # 补齐到4位再比较，支持 x.y.z.w 格式
                    while len(parts) < 4:
                        parts.append(0)
                    return tuple(parts[:4])
                except Exception:
                    return (0, 0, 0, 0)
            
            if parse_ver(latest) > parse_ver(APP_VERSION):
                self._latest_version = latest
                self.show_bubble_message(f"🎉 发现新版本 v{latest}！\n打开设置→关于 点击一键更新")
                logger.info(f"New version available: v{latest}")
            else:
                logger.info(f"Current version {APP_VERSION} is up to date.")
        except Exception as e:
            logger.warning(f"Auto update check failed: {e}")

    def on_todo_added(self, text):
        """ 便签新增待办的回调 """
        import random
        # 限制显示长度防止超出气泡范围
        short_text = text if len(text) <= 15 else text[:12] + "..."
        phrases = [
            f"冲呀！新增待办：【{short_text}】，加油搞定它！🔥",
            f"记在便签上了，加油干！💪",
            f"任务又多了一个，准备开始战斗吧！✨",
            f"收到新挑战！等你的好消息哦～👍"
        ]
        self.show_bubble_message(random.choice(phrases))
        
        # 播放开心/兴奋动画
        self.load_animation("happy")
        # 5秒后恢复默认状态
        QTimer.singleShot(5000, lambda: self.load_animation("idle") if self.current_state == "happy" else None)

    def on_todo_status_changed(self, todo_id, completed):
        """ 便签待办状态发生改变的回调 """
        import random
        if completed:
            # 检查是否所有待办都已经完成
            todos = self.db.get_all_todos()
            uncompleted_count = sum(1 for t in todos if not t["completed"])
            
            if uncompleted_count == 0:
                # 所有待办完成！超级庆祝！
                phrases = [
                    "哇！所有待办都完成了！太强了！🏆",
                    "任务全部扫光！今天简直效率爆表！🎉",
                    "太棒了，全部搞定！现在是休息时间！🍵"
                ]
                self.show_bubble_message(random.choice(phrases))
                self.load_animation("happy")
                QTimer.singleShot(6000, lambda: self.load_animation("idle") if self.current_state == "happy" else None)
            else:
                # 搞定其中一项
                phrases = [
                    "搞定一项！太棒了！✨",
                    "消灭了一个任务，继续保持！👍",
                    "Nice! 又少了一个待办！🎉",
                    "干得漂亮！离终点又近了一步！"
                ]
                self.show_bubble_message(random.choice(phrases))
                self.load_animation("happy")
                QTimer.singleShot(5000, lambda: self.load_animation("idle") if self.current_state == "happy" else None)
        else:
            # 取消勾选（任务重新回来）
            phrases = [
                "嗯？这个还要再做一次吗？👀",
                "任务又回来了，加油解决它！💪",
                "没关系，我们再战一轮！"
            ]
            self.show_bubble_message(random.choice(phrases))
            self.load_animation("idle")
