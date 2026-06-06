import logging
import datetime
import json
import os
import sys
import urllib.request
import urllib.error
import webbrowser
import subprocess
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QSpinBox, QTextEdit, QPushButton, QGroupBox, QFormLayout, QMessageBox,
    QSlider, QTabWidget, QWidget as QWidgetBase, QListWidget, QListWidgetItem,
    QScrollArea, QFrame, QLineEdit, QComboBox, QAbstractButton, QProgressBar,
    QListView
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, pyqtProperty, QPropertyAnimation, QEasingCurve, QThread
from PyQt6.QtGui import QDesktopServices, QKeySequence, QPainter, QBrush, QPen, QColor, QFont

from utils.helpers import resource_path, set_auto_start, is_auto_start_enabled, get_app_dir

APP_VERSION = "1.2.10"

logger = logging.getLogger("vibe_pet")


class UpdateCheckThread(QThread):
    # Emit: success, latest_version, download_url, error_msg
    finished = pyqtSignal(bool, str, str, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
    def run(self):
        try:
            import urllib.request
            import json
            req = urllib.request.Request(
                "https://vibeharbor.art/api/github/vibepet/latest",
                headers={"User-Agent": "VibePet-UpdateChecker"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = data.get("tag_name", "").lstrip("v")
            download_url = ""
            assets = data.get("assets", [])
            if assets and isinstance(assets, list):
                download_url = assets[0].get("browser_download_url", "")
            
            if not latest:
                self.finished.emit(False, "", "", "无法获取最新版本信息")
            else:
                self.finished.emit(True, latest, download_url, "")
        except Exception as e:
            self.finished.emit(False, "", "", str(e))

class AnimatedSwitch(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(50, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self._knob_position = 0.0
        self.animation = QPropertyAnimation(self, b"knob_position", self)
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
    @pyqtProperty(float)
    def knob_position(self):
        return self._knob_position
        
    @knob_position.setter
    def knob_position(self, pos):
        self._knob_position = pos
        self.update()
        
    def nextCheckState(self):
        super().nextCheckState()
        self.animate(self.isChecked())
        
    def setChecked(self, checked):
        super().setChecked(checked)
        self._knob_position = 1.0 if checked else 0.0
        self.update()
        
    def animate(self, checked):
        self.animation.stop()
        self.animation.setStartValue(self._knob_position)
        self.animation.setEndValue(1.0 if checked else 0.0)
        self.animation.start()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        is_dark = True
        try:
            win = self.window()
            if hasattr(win, "config") and win.config:
                is_dark = (win.config.get("theme_mode", "light") == "dark")
        except Exception:
            pass
            
        # Draw track
        if self.isChecked():
            track_color = QColor("#81c784" if is_dark else "#2e7d32")
        else:
            track_color = QColor("#3e3e4a" if is_dark else "#dcdcdc")
            
        painter.setBrush(QBrush(track_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 13, 13)
        
        # Draw knob
        knob_color = QColor("#ffffff")
        painter.setBrush(QBrush(knob_color))
        
        knob_size = 20
        margin = 3
        start_x = margin
        end_x = self.width() - knob_size - margin
        knob_x = start_x + (end_x - start_x) * self._knob_position
        
        if is_dark:
            shadow_color = QColor(0, 0, 0, 60)
            painter.setBrush(QBrush(shadow_color))
            painter.drawEllipse(int(knob_x), margin + 1, knob_size, knob_size)
            painter.setBrush(QBrush(knob_color))
            
        painter.drawEllipse(int(knob_x), margin, knob_size, knob_size)
        painter.end()


class SettingCard(QFrame):
    def __init__(self, icon, title, description, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingCard")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(12)
        
        # Left icon
        self.lbl_icon = QLabel(icon)
        self.lbl_icon.setObjectName("CardIcon")
        self.lbl_icon.setFont(QFont("Segoe UI Emoji", 14))
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_icon.setFixedSize(36, 36)
        layout.addWidget(self.lbl_icon)
        
        # Text block
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("CardTitle")
        self.lbl_title.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
        text_layout.addWidget(self.lbl_title)
        
        self.lbl_desc = QLabel(description)
        self.lbl_desc.setObjectName("CardDesc")
        self.lbl_desc.setFont(QFont("Microsoft YaHei", 8))
        self.lbl_desc.setWordWrap(True)
        text_layout.addWidget(self.lbl_desc)
        
        layout.addLayout(text_layout, stretch=1)
        
        # Switch button
        self.switch_btn = AnimatedSwitch(self)
        layout.addWidget(self.switch_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

    def isChecked(self):
        return self.switch_btn.isChecked()
        
    def setChecked(self, checked):
        self.switch_btn.setChecked(checked)


class SettingsDialog(QDialog):
    # 设置变更信号，通知主窗口应用新配置
    settings_changed = pyqtSignal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self._download_url = ""
        
        # 安装事件过滤器，阻止滚轮事件改变 SpinBox 值（防止滑动时误触）
        self.installEventFilter(self)

        self.setWindowTitle("VibePet - 系统设置")
        # Prevent closing child widgets closing parent
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        
        # 动态自适应屏幕分辨率与DPI缩放比例，防止低分辨率或高DPI缩放下设置界面超出屏幕而无法拖动
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            available_geo = screen.availableGeometry()
            screen_width = available_geo.width()
            screen_height = available_geo.height()
            
            # 计算适合当前屏幕的高度与宽度
            width = min(680, int(screen_width * 0.95))
            height = min(800, int(screen_height * 0.85))
            
            # 自适应调整最小尺寸
            min_width = min(600, int(screen_width * 0.85))
            min_height = min(720, int(screen_height * 0.8))
            
            self.setMinimumSize(min_width, min_height)
            self.resize(width, height)
            
            # 居中移动到可用的桌面区域（排除任务栏）
            x = available_geo.x() + (screen_width - width) // 2
            y = available_geo.y() + (screen_height - height) // 2
            self.move(x, y)
        else:
            self.setMinimumSize(600, 720)
            self.resize(680, 800)
        
        # 设置窗口图标
        from PyQt6.QtGui import QIcon, QPixmap
        icon_path = resource_path("assets/icon.png")
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            self.setWindowIcon(QIcon(pixmap))

        self.setup_ui()
        self.load_values()
        self.apply_styles()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title + Time
        title_layout = QHBoxLayout()
        title_label = QLabel("VibePet 偏好设置")
        title_label.setObjectName("DialogTitle")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        self.lbl_time = QLabel()
        self.lbl_time.setObjectName("TimeLabel")
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title_layout.addWidget(self.lbl_time)
        layout.addLayout(title_layout)
        
        # 启动时间更新定时器
        self._time_timer = QTimer(self)
        self._time_timer.timeout.connect(self._update_time)
        self._time_timer.start(1000)
        self._update_time()

        # 使用 Tab 分组组织设置
        self.tabs = QTabWidget()
        self.tabs.setObjectName("SettingsTabs")

        # === Tab 1: 提醒设置 ===
        tab_reminders = QWidgetBase()
        tab_reminders_layout = QVBoxLayout(tab_reminders)
        tab_reminders_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll_reminders = QScrollArea()
        scroll_reminders.setWidgetResizable(True)
        scroll_reminders.setFrameShape(QFrame.Shape.NoFrame)
        scroll_reminders.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_reminders_content = QWidgetBase()
        scroll_reminders_content.setStyleSheet("background-color: transparent;")
        reminders_layout = QVBoxLayout(scroll_reminders_content)
        reminders_layout.setContentsMargins(15, 15, 15, 15)
        reminders_layout.setSpacing(12)

        # 1. Reminder Switches Group
        switches_group = QGroupBox("提醒功能开关")
        switches_layout = QVBoxLayout()
        switches_layout.setContentsMargins(15, 15, 15, 15)
        switches_layout.setSpacing(10)

        self.cb_game = SettingCard("🎮", "游戏沉迷提醒", "检测到游戏运行时间过长时提醒适当放松", self)
        self.cb_sedentary = SettingCard("🚶‍♂️", "连续久坐提醒", "连续使用电脑时间过长时发出活动建议", self)
        self.cb_late_night = SettingCard("🌙", "深夜防熬夜提醒", "深夜时段连续活跃时间较长时提醒合理作息", self)
        self.cb_positive = SettingCard("🌟", "工作正向激励", "专注工作或学习一段时间后桌宠给出正向反馈与鼓励", self)
        self.cb_fatigue = SettingCard("⚠️", "疲劳强制提醒", "每日电脑累计总使用时长达到限制后进行全屏强制警示", self)

        switches_layout.addWidget(self.cb_game)
        switches_layout.addWidget(self.cb_sedentary)
        switches_layout.addWidget(self.cb_late_night)
        switches_layout.addWidget(self.cb_positive)
        switches_layout.addWidget(self.cb_fatigue)
        switches_group.setLayout(switches_layout)
        reminders_layout.addWidget(switches_group)

        # 2. Thresholds Group
        thresholds_group = QGroupBox("提醒阈值设置（单位：分钟）")
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.sb_game = QSpinBox()
        self.sb_game.setRange(1, 1440)
        self.sb_game.setSingleStep(5)
        self.sb_game.setSuffix(" 分钟")
        self.sb_game.setMinimumWidth(140)
        form_layout.addRow("游戏沉迷阈值:", self.sb_game)

        self.sb_sedentary = QSpinBox()
        self.sb_sedentary.setRange(1, 1440)
        self.sb_sedentary.setSingleStep(5)
        self.sb_sedentary.setSuffix(" 分钟")
        self.sb_sedentary.setMinimumWidth(140)
        form_layout.addRow("连续久坐阈值:", self.sb_sedentary)

        self.sb_late_night = QSpinBox()
        self.sb_late_night.setRange(1, 1440)
        self.sb_late_night.setSingleStep(5)
        self.sb_late_night.setSuffix(" 分钟")
        self.sb_late_night.setMinimumWidth(140)
        form_layout.addRow("深夜连续活跃限制:", self.sb_late_night)

        self.sb_positive = QSpinBox()
        self.sb_positive.setRange(1, 1440)
        self.sb_positive.setSingleStep(5)
        self.sb_positive.setSuffix(" 分钟")
        self.sb_positive.setMinimumWidth(140)
        form_layout.addRow("工作专注激励触发:", self.sb_positive)

        self.sb_fatigue = QSpinBox()
        self.sb_fatigue.setRange(1, 1440)
        self.sb_fatigue.setSingleStep(5)
        self.sb_fatigue.setSuffix(" 分钟")
        self.sb_fatigue.setMinimumWidth(140)
        form_layout.addRow("每日使用时间上限:", self.sb_fatigue)

        thresholds_group.setLayout(form_layout)
        reminders_layout.addWidget(thresholds_group)
        # Tab 1 恢复默认按钮
        btn_reset_reminders = QPushButton("恢复提醒默认")
        btn_reset_reminders.setObjectName("TabResetButton")
        btn_reset_reminders.clicked.connect(self.reset_reminders_tab)
        reminders_layout.addWidget(btn_reset_reminders, alignment=Qt.AlignmentFlag.AlignRight)
        scroll_reminders.setWidget(scroll_reminders_content)
        tab_reminders_layout.addWidget(scroll_reminders)
        self.tabs.addTab(tab_reminders, "提醒设置")

        # === Tab 2: 宠物外观 ===
        tab_appearance = QWidgetBase()
        tab_appearance_layout = QVBoxLayout(tab_appearance)
        tab_appearance_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll_appearance = QScrollArea()
        scroll_appearance.setWidgetResizable(True)
        scroll_appearance.setFrameShape(QFrame.Shape.NoFrame)
        scroll_appearance.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_appearance_content = QWidgetBase()
        scroll_appearance_content.setStyleSheet("background-color: transparent;")
        appearance_layout = QVBoxLayout(scroll_appearance_content)
        appearance_layout.setContentsMargins(15, 15, 15, 15)
        appearance_layout.setSpacing(12)

        pet_group = QGroupBox("宠物窗口设置")
        pet_form = QFormLayout()
        pet_form.setSpacing(14)
        pet_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 宠物大小滑块
        self.slider_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(80, 400)
        self.slider_size.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider_size.setTickInterval(40)
        self.slider_size.valueChanged.connect(self._on_size_slider_changed)

        size_row = QHBoxLayout()
        size_row.addWidget(self.slider_size, stretch=1)
        self.lbl_size_value = QLabel("200 px")
        self.lbl_size_value.setMinimumWidth(60)
        size_row.addWidget(self.lbl_size_value)
        pet_form.addRow("宠物大小:", size_row)

        # 窗口锁定
        self.cb_window_locked = QCheckBox("锁定窗口位置（禁止拖拽移动）")
        pet_form.addRow("", self.cb_window_locked)

        # 鼠标穿透
        self.cb_mouse_passthrough = QCheckBox("启用鼠标穿透（点击穿透到下层窗口）")
        pet_form.addRow("", self.cb_mouse_passthrough)

        # 监控气泡
        self.cb_show_bubble = QCheckBox("显示当前应用监控气泡")
        pet_form.addRow("", self.cb_show_bubble)

        # 贴边自动隐藏（躲猫猫）
        self.cb_screen_snapping = QCheckBox("启用贴边自动隐藏（躲猫猫模式）")
        pet_form.addRow("", self.cb_screen_snapping)

        # 便签待办清单
        self.cb_todo_visible = QCheckBox("显示桌面便签待办清单")
        pet_form.addRow("", self.cb_todo_visible)

        # 气泡透明度
        self.slider_bubble_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_bubble_opacity.setRange(30, 100)
        self.slider_bubble_opacity.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider_bubble_opacity.setTickInterval(10)
        self.slider_bubble_opacity.valueChanged.connect(self._on_opacity_slider_changed)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.slider_bubble_opacity, stretch=1)
        self.lbl_opacity_value = QLabel("100%")
        self.lbl_opacity_value.setMinimumWidth(50)
        opacity_row.addWidget(self.lbl_opacity_value)
        pet_form.addRow("气泡透明度:", opacity_row)

        # 监控气泡字号
        self.sb_bubble_font_size = QSpinBox()
        self.sb_bubble_font_size.setRange(8, 20)
        self.sb_bubble_font_size.setSuffix(" pt")
        self.sb_bubble_font_size.setMinimumWidth(140)
        pet_form.addRow("气泡大小 (字号):", self.sb_bubble_font_size)

        # 主题风格设置
        self.combo_theme = QComboBox()
        self.combo_theme.setView(QListView())
        self.combo_theme.addItems(["暗黑模式", "明亮模式"])
        self.combo_theme.setMinimumWidth(140)
        pet_form.addRow("界面主题风格:", self.combo_theme)

        pet_group.setLayout(pet_form)
        appearance_layout.addWidget(pet_group)
        # Tab 2 恢复默认按钮
        btn_reset_appearance = QPushButton("恢复外观默认")
        btn_reset_appearance.setObjectName("TabResetButton")
        btn_reset_appearance.clicked.connect(self.reset_appearance_tab)
        appearance_layout.addWidget(btn_reset_appearance, alignment=Qt.AlignmentFlag.AlignRight)
        scroll_appearance.setWidget(scroll_appearance_content)
        tab_appearance_layout.addWidget(scroll_appearance)
        self.tabs.addTab(tab_appearance, "宠物外观")

        # === Tab 3: 随机情绪 ===
        tab_emotions = QWidgetBase()
        tab_emotions_layout = QVBoxLayout(tab_emotions)
        tab_emotions_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll_emotions = QScrollArea()
        scroll_emotions.setWidgetResizable(True)
        scroll_emotions.setFrameShape(QFrame.Shape.NoFrame)
        scroll_emotions.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_emotions_content = QWidgetBase()
        scroll_emotions_content.setStyleSheet("background-color: transparent;")
        emotions_layout = QVBoxLayout(scroll_emotions_content)
        emotions_layout.setContentsMargins(15, 15, 15, 15)
        emotions_layout.setSpacing(12)

        emotion_group = QGroupBox("随机情绪行为")
        emotion_form = QFormLayout()
        emotion_form.setSpacing(14)
        emotion_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.cb_random_emotions = QCheckBox("启用随机情绪（宠物会随机进入睡眠、开心或疲惫状态）")
        emotion_form.addRow("", self.cb_random_emotions)

        emotion_group.setLayout(emotion_form)
        emotions_layout.addWidget(emotion_group)

        # 白天时段概率
        day_group = QGroupBox("白天时段 (06:00-18:00)")
        day_form = QFormLayout()
        day_form.setSpacing(10)
        day_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.sb_day_sleep = QSpinBox()
        self.sb_day_sleep.setRange(0, 100)
        self.sb_day_sleep.setSuffix(" %")
        self.sb_day_sleep.setMinimumWidth(100)
        day_form.addRow("睡眠概率:", self.sb_day_sleep)

        self.sb_day_happy = QSpinBox()
        self.sb_day_happy.setRange(0, 100)
        self.sb_day_happy.setSuffix(" %")
        self.sb_day_happy.setMinimumWidth(100)
        day_form.addRow("开心概率:", self.sb_day_happy)

        self.sb_day_tired = QSpinBox()
        self.sb_day_tired.setRange(0, 100)
        self.sb_day_tired.setSuffix(" %")
        self.sb_day_tired.setMinimumWidth(100)
        day_form.addRow("疲惫概率:", self.sb_day_tired)

        day_group.setLayout(day_form)
        emotions_layout.addWidget(day_group)

        # 傍晚时段概率
        evening_group = QGroupBox("傍晚时段 (18:00-22:00)")
        evening_form = QFormLayout()
        evening_form.setSpacing(10)
        evening_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.sb_evening_sleep = QSpinBox()
        self.sb_evening_sleep.setRange(0, 100)
        self.sb_evening_sleep.setSuffix(" %")
        self.sb_evening_sleep.setMinimumWidth(100)
        evening_form.addRow("睡眠概率:", self.sb_evening_sleep)

        self.sb_evening_happy = QSpinBox()
        self.sb_evening_happy.setRange(0, 100)
        self.sb_evening_happy.setSuffix(" %")
        self.sb_evening_happy.setMinimumWidth(100)
        evening_form.addRow("开心概率:", self.sb_evening_happy)

        self.sb_evening_tired = QSpinBox()
        self.sb_evening_tired.setRange(0, 100)
        self.sb_evening_tired.setSuffix(" %")
        self.sb_evening_tired.setMinimumWidth(100)
        evening_form.addRow("疲惫概率:", self.sb_evening_tired)

        evening_group.setLayout(evening_form)
        emotions_layout.addWidget(evening_group)

        # 夜晚时段概率
        night_group = QGroupBox("夜晚时段 (22:00-06:00)")
        night_form = QFormLayout()
        night_form.setSpacing(10)
        night_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.sb_night_sleep = QSpinBox()
        self.sb_night_sleep.setRange(0, 100)
        self.sb_night_sleep.setSuffix(" %")
        self.sb_night_sleep.setMinimumWidth(100)
        night_form.addRow("睡眠概率:", self.sb_night_sleep)

        self.sb_night_happy = QSpinBox()
        self.sb_night_happy.setRange(0, 100)
        self.sb_night_happy.setSuffix(" %")
        self.sb_night_happy.setMinimumWidth(100)
        night_form.addRow("开心概率:", self.sb_night_happy)

        self.sb_night_tired = QSpinBox()
        self.sb_night_tired.setRange(0, 100)
        self.sb_night_tired.setSuffix(" %")
        self.sb_night_tired.setMinimumWidth(100)
        night_form.addRow("疲惫概率:", self.sb_night_tired)

        night_group.setLayout(night_form)
        emotions_layout.addWidget(night_group)

        # 说明文本
        info_label = QLabel(
            "💡 说明：启用随机情绪后，宠物会根据当前时间段以不同概率进入各种情绪状态。"
            "白天更容易开心，夜晚更容易疲惫和睡觉。概率值越高，触发越频繁。"
        )
        info_label.setWordWrap(True)
        info_label.setObjectName("InfoLabel")
        emotions_layout.addWidget(info_label)
        # Tab 3 恢复默认按钮
        btn_reset_emotions = QPushButton("恢复情绪默认")
        btn_reset_emotions.setObjectName("TabResetButton")
        btn_reset_emotions.clicked.connect(self.reset_emotions_tab)
        emotions_layout.addWidget(btn_reset_emotions, alignment=Qt.AlignmentFlag.AlignRight)
        scroll_emotions.setWidget(scroll_emotions_content)
        tab_emotions_layout.addWidget(scroll_emotions)
        self.tabs.addTab(tab_emotions, "随机情绪")

        # === Tab 4: 进程名单 ===
        tab_apps = QWidgetBase()
        tab_apps_layout = QVBoxLayout(tab_apps)
        tab_apps_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setObjectName("AppsScrollArea")
        scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        scroll_area.viewport().setStyleSheet("background-color: transparent;")
        
        self.scroll_content = QWidgetBase()
        self.scroll_content.setObjectName("AppsScrollContent")
        self.scroll_content.setStyleSheet("QWidget#AppsScrollContent { background-color: transparent; }")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(15, 15, 15, 15)
        self.scroll_layout.setSpacing(10)
        
        scroll_area.setWidget(self.scroll_content)
        tab_apps_layout.addWidget(scroll_area)
        self.tabs.addTab(tab_apps, "进程名单")
        
        # 动态构建进程名单选项卡内容
        self.rebuild_apps_tab_content(initial=True)

        # === Tab 5: 系统监控 ===
        tab_sysmon = QWidgetBase()
        tab_sysmon_layout = QVBoxLayout(tab_sysmon)
        tab_sysmon_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll_sysmon = QScrollArea()
        scroll_sysmon.setWidgetResizable(True)
        scroll_sysmon.setFrameShape(QFrame.Shape.NoFrame)
        scroll_sysmon.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_sysmon_content = QWidgetBase()
        scroll_sysmon_content.setStyleSheet("background-color: transparent;")
        sysmon_layout = QVBoxLayout(scroll_sysmon_content)
        sysmon_layout.setContentsMargins(15, 15, 15, 15)
        sysmon_layout.setSpacing(12)

        sysmon_group = QGroupBox("系统资源监控")
        sysmon_inner = QVBoxLayout()
        sysmon_inner.setSpacing(10)

        self.cb_sysmon_enabled = QCheckBox("启用系统监控面板")
        sysmon_inner.addWidget(self.cb_sysmon_enabled)

        sysmon_inner.addWidget(QLabel("选择要显示的项目（可多选）："))
        
        self.cb_show_cpu = QCheckBox("▲ CPU 使用率")
        self.cb_show_memory = QCheckBox("◆ 内存使用率")
        self.cb_show_disk = QCheckBox("■ 磁盘使用率")
        self.cb_show_network = QCheckBox("▼▲ 网络速度 (KB/s)")
        self.cb_show_gpu = QCheckBox("● GPU 使用率（零依赖，支持 NVIDIA/AMD/Intel）")
        
        sysmon_inner.addWidget(self.cb_show_cpu)
        sysmon_inner.addWidget(self.cb_show_memory)
        sysmon_inner.addWidget(self.cb_show_disk)
        sysmon_inner.addWidget(self.cb_show_network)
        sysmon_inner.addWidget(self.cb_show_gpu)
        
        # 刷新间隔
        sysmon_form = QFormLayout()
        sysmon_form.setSpacing(10)
        sysmon_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.sb_sysmon_interval = QSpinBox()
        self.sb_sysmon_interval.setRange(1, 10)
        self.sb_sysmon_interval.setSuffix(" 秒")
        sysmon_form.addRow("刷新间隔:", self.sb_sysmon_interval)
        sysmon_inner.addLayout(sysmon_form)
        sysmon_group.setLayout(sysmon_inner)
        sysmon_layout.addWidget(sysmon_group)
        
        # 新增：划词字数统计设置分组
        word_count_group = QGroupBox("划词字数统计 (选区文本统计)")
        word_count_inner = QVBoxLayout()
        word_count_inner.setSpacing(10)
        
        self.cb_word_count_enabled = QCheckBox("启用全局划词字数统计")
        word_count_inner.addWidget(self.cb_word_count_enabled)
        
        word_count_group.setLayout(word_count_inner)
        sysmon_layout.addWidget(word_count_group)
        
        # Tab 5 恢复默认按钮
        btn_reset_sysmon = QPushButton("恢复监控默认")
        btn_reset_sysmon.setObjectName("TabResetButton")
        btn_reset_sysmon.clicked.connect(self.reset_sysmon_tab)
        sysmon_layout.addWidget(btn_reset_sysmon, alignment=Qt.AlignmentFlag.AlignRight)
        sysmon_layout.addStretch()
        scroll_sysmon.setWidget(scroll_sysmon_content)
        tab_sysmon_layout.addWidget(scroll_sysmon)
        self.tabs.addTab(tab_sysmon, "系统监控")

        # === Tab 6: 关于 ===
        tab_about = QWidgetBase()
        tab_about_layout = QVBoxLayout(tab_about)
        tab_about_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll_about = QScrollArea()
        scroll_about.setWidgetResizable(True)
        scroll_about.setFrameShape(QFrame.Shape.NoFrame)
        scroll_about.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_about_content = QWidgetBase()
        scroll_about_content.setStyleSheet("background-color: transparent;")
        about_layout = QVBoxLayout(scroll_about_content)
        about_layout.setContentsMargins(15, 15, 15, 15)
        about_layout.setSpacing(12)

        about_group = QGroupBox("关于 VibePet")
        about_inner = QVBoxLayout()
        about_inner.setSpacing(10)

        self.lbl_about_title = QLabel()
        about_inner.addWidget(self.lbl_about_title)
        about_inner.addWidget(QLabel(f"<b>版本号:</b> {APP_VERSION}"))
        about_inner.addWidget(QLabel("<b>作者:</b> YTU22"))
        
        self.lbl_github = QLabel()
        self.lbl_github.setOpenExternalLinks(True)
        about_inner.addWidget(self.lbl_github)
        
        self.lbl_website = QLabel()
        self.lbl_website.setOpenExternalLinks(True)
        about_inner.addWidget(self.lbl_website)
        
        about_inner.addWidget(QLabel("实时监测软件时长，守护您的作息与健康！"))
        
        # 下载源选择
        mirror_layout = QHBoxLayout()
        lbl_mirror = QLabel("下载加速通道:")
        mirror_layout.addWidget(lbl_mirror)
        self.combo_mirror = QComboBox()
        self.combo_mirror.setView(QListView())
        self.combo_mirror.addItems([
            "自动选择 (多镜像测速)",
            "加速通道 A (Moeyy - 推荐)",
            "加速通道 B (GHProxy)",
            "加速通道 C (GHProxy Net)",
            "直连 GitHub",
            "官方备用通道"
        ])
        self.combo_mirror.setMinimumWidth(180)
        mirror_layout.addWidget(self.combo_mirror)
        mirror_layout.addStretch()
        about_inner.addLayout(mirror_layout)

        # 检测更新区域
        about_inner.addSpacing(10)
        self.btn_check_update = QPushButton("🔍 检测更新")
        self.btn_check_update.clicked.connect(self._check_for_update)
        about_inner.addWidget(self.btn_check_update)
        
        # 下载进度条（默认隐藏）
        self.progress_update = QProgressBar()
        self.progress_update.setRange(0, 100)
        self.progress_update.setValue(0)
        self.progress_update.setTextVisible(True)
        self.progress_update.setStyleSheet("""
            QProgressBar {
                border: 1px solid #42424a;
                border-radius: 4px;
                background-color: #2b2b35;
                color: #e0e0e6;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #81c784;
                border-radius: 4px;
            }
        """)
        self.progress_update.hide()
        about_inner.addWidget(self.progress_update)
        
        self.lbl_update_status = QLabel("")
        self.lbl_update_status.setWordWrap(True)
        about_inner.addWidget(self.lbl_update_status)
        
        # 一键更新按钮（检测到新版本后才显示）
        self.btn_onekey_update = QPushButton("⬇️ 一键下载更新")
        self.btn_onekey_update.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #388e3c;
            }
            QPushButton:pressed {
                background-color: #1b5e20;
            }
        """)
        self.btn_onekey_update.clicked.connect(self._onekey_update)
        self.btn_onekey_update.hide()
        about_inner.addWidget(self.btn_onekey_update)
        
        # 开机自启动选项
        about_inner.addSpacing(10)
        self.cb_auto_start = QCheckBox("开机自动启动 VibePet")
        self.cb_auto_start.setChecked(is_auto_start_enabled())
        self.cb_auto_start.stateChanged.connect(self._on_auto_start_changed)
        about_inner.addWidget(self.cb_auto_start)
        
        about_group.setLayout(about_inner)
        about_layout.addWidget(about_group)
        about_layout.addStretch()
        scroll_about.setWidget(scroll_about_content)
        tab_about_layout.addWidget(scroll_about)
        self.tabs.addTab(tab_about, "关于")

        layout.addWidget(self.tabs, stretch=1)

        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_save = QPushButton("保存设置")
        self.btn_save.clicked.connect(self.save_values)

        self.btn_cancel = QPushButton("关闭")
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _on_size_slider_changed(self, value):
        self.lbl_size_value.setText(f"{value} px")

    def _on_opacity_slider_changed(self, value):
        self.lbl_opacity_value.setText(f"{value}%")

    def _on_auto_start_changed(self, state):
        """ 处理开机自启动选项变更 """
        enabled = state == Qt.CheckState.Checked.value
        success = set_auto_start(enabled)
        if success:
            self.config.set("auto_start", enabled)
            logger.info(f"Auto-start changed to: {enabled}")

    def eventFilter(self, obj, event):
        """ 拦截滚轮事件，防止滚动页面时误触 SpinBox/Slider 值 """
        if event.type() == event.Type.Wheel:
            # 如果滚轮事件目标不是滚动区域本身，则忽略（阻止 SpinBox/Slider 响应）
            if obj is not self and not isinstance(obj, QScrollArea):
                event.ignore()
                return True
        return super().eventFilter(obj, event)

    def _check_for_update(self):
        """ 检测网站 API 是否有新版本 """
        self.lbl_update_status.setText("正在检测更新...")
        self.btn_check_update.setEnabled(False)
        self.btn_onekey_update.hide()
        
        self._update_check_thread = UpdateCheckThread(self)
        self._update_check_thread.finished.connect(self._on_update_check_finished)
        self._update_check_thread.start()

    def _on_update_check_finished(self, success, latest, download_url, error_msg):
        self._download_url = download_url
        if success:
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
                self.lbl_update_status.setText(
                    f"<span style='color:#81c784;'>发现新版本 v{latest}！</span><br>"
                    f"点击下方按钮一键下载更新。"
                )
                self.btn_onekey_update.show()
            else:
                self.lbl_update_status.setText("<span style='color:#81c784;'>✓ 当前已是最新版本</span>")
        else:
            if "HTTP Error" in error_msg or "URLError" in error_msg or "timeout" in error_msg.lower():
                self.lbl_update_status.setText(f"<span style='color:#ff9800;'>网络连接失败，请稍后重试</span>")
            else:
                self.lbl_update_status.setText(f"<span style='color:#ff9800;'>检测失败: {error_msg}</span>")
            logger.warning(f"Update check failed: {error_msg}")
        
        self.btn_check_update.setEnabled(True)

    def _onekey_update(self):
        """ 一键下载更新：下载新 exe → 提示用户关闭 → 启动更新器替换 """
        self.btn_onekey_update.setEnabled(False)
        self.btn_onekey_update.setText("正在下载...")
        self.progress_update.show()
        
        # 在后台线程下载，避免阻塞 UI
        from PyQt6.QtCore import QThread, pyqtSignal
        
        class DownloadThread(QThread):
            progress = pyqtSignal(int)
            finished = pyqtSignal(bool, str)
            
            def __init__(self, download_url="", mirror_pref="自动选择 (多镜像测速)", parent=None):
                super().__init__(parent)
                self.download_url = download_url
                self.mirror_pref = mirror_pref
                
            def run(self):
                try:
                    app_dir = get_app_dir()
                    temp_zip = os.path.join(app_dir, "VibePet_update.zip")
                    
                    # 各个加速源的地址映射
                    mirrors = {
                        "加速通道 A (Moeyy - 推荐)": ("Moeyy 镜像", f"https://github.moeyy.xyz/{self.download_url}"),
                        "加速通道 B (GHProxy)": ("GHProxy 镜像", f"https://mirror.ghproxy.com/{self.download_url}"),
                        "加速通道 C (GHProxy Net)": ("GHProxy Net 镜像", f"https://ghproxy.net/{self.download_url}"),
                        "直连 GitHub": ("直连 GitHub", self.download_url),
                        "官方备用通道": ("官方备用服务器", "https://vibeharbor.art/api/github/vibepet/download-latest")
                    }
                    
                    # 按照优先级排序的下载源列表
                    urls_to_try = []
                    if self.download_url:
                        pref = self.mirror_pref
                        if pref in mirrors:
                            urls_to_try.append(mirrors[pref])
                            logger.info(f"User preferred mirror: {pref}")
                            
                        order = [
                            "加速通道 A (Moeyy - 推荐)",
                            "加速通道 B (GHProxy)",
                            "加速通道 C (GHProxy Net)",
                            "直连 GitHub",
                            "官方备用通道"
                        ]
                        
                        if pref == "自动选择 (多镜像测速)":
                            logger.info("Auto mirror select: testing latencies...")
                            import concurrent.futures
                            import time
                            
                            candidates = [
                                ("加速通道 A (Moeyy - 推荐)", mirrors["加速通道 A (Moeyy - 推荐)"][1]),
                                ("加速通道 B (GHProxy)", mirrors["加速通道 B (GHProxy)"][1]),
                                ("加速通道 C (GHProxy Net)", mirrors["加速通道 C (GHProxy Net)"][1]),
                                ("直连 GitHub", mirrors["直连 GitHub"][1])
                            ]
                            
                            def test_mirror(item):
                                m_name, m_url = item
                                try:
                                    # 测速请求 HEAD，超时限制为 1.5 秒
                                    req = urllib.request.Request(m_url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
                                    start = time.time()
                                    with urllib.request.urlopen(req, timeout=1.5) as resp:
                                        return time.time() - start, m_name
                                except Exception:
                                    return float('inf'), m_name
                                    
                            with concurrent.futures.ThreadPoolExecutor(max_workers=len(candidates)) as executor:
                                results = list(executor.map(test_mirror, candidates))
                                
                            results.sort(key=lambda x: x[0])
                            
                            for latency, m_name in results:
                                if latency < float('inf'):
                                    logger.info(f"Speedtest: {m_name} latency={latency:.3f}s")
                                    urls_to_try.append(mirrors[m_name])
                                    
                            for m_name in order:
                                if mirrors[m_name] not in urls_to_try:
                                    urls_to_try.append(mirrors[m_name])
                        else:
                            for m_name in order:
                                if mirrors[m_name] not in urls_to_try:
                                    urls_to_try.append(mirrors[m_name])
                    else:
                        urls_to_try.append(mirrors["官方备用通道"])
                    
                    last_error = ""
                    success = False
                    
                    for name, url in urls_to_try:
                        logger.info(f"Trying to download update from {name}: {url}")
                        try:
                            # 必须使用主流浏览器 User-Agent 绕过某些防护墙与 Cloudflare 拦截
                            req = urllib.request.Request(
                                url,
                                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                            )
                            with urllib.request.urlopen(req, timeout=45) as resp:
                                total_size = int(resp.headers.get('content-length', 0))
                                downloaded = 0
                                chunk_size = 8192
                                
                                with open(temp_zip, 'wb') as f:
                                    while True:
                                        chunk = resp.read(chunk_size)
                                        if not chunk:
                                            break
                                        f.write(chunk)
                                        downloaded += len(chunk)
                                        if total_size > 0:
                                            self.progress.emit(int(downloaded * 100 / total_size))
                            
                            success = True
                            logger.info(f"Successfully downloaded update from {name}")
                            break
                        except Exception as e:
                            logger.warning(f"Failed to download update from {name}: {e}")
                            last_error = str(e)
                            # 清理下载失败的临时残留文件
                            if os.path.exists(temp_zip):
                                try:
                                    os.remove(temp_zip)
                                except Exception:
                                    pass
                    
                    if success:
                        self.finished.emit(True, temp_zip)
                    else:
                        self.finished.emit(False, last_error)
                except Exception as e:
                    self.finished.emit(False, str(e))
        
        mirror_pref = self.combo_mirror.currentText()
        self._dl_thread = DownloadThread(self._download_url, mirror_pref, self)
        self._dl_thread.progress.connect(self.progress_update.setValue)
        self._dl_thread.finished.connect(self._on_download_finished)
        self._dl_thread.start()
    
    def _on_download_finished(self, success, result):
        """ 下载完成后处理 """
        self.progress_update.hide()
        self.btn_onekey_update.setEnabled(True)
        self.btn_onekey_update.setText("⬇️ 一键下载更新")
        
        if not success:
            self.lbl_update_status.setText(f"<span style='color:#ff9800;'>下载失败: {result}</span>")
            return
        
        temp_zip = result
        
        # 提示用户关闭程序后开始更新
        msg = QMessageBox(self)
        msg.setWindowTitle("下载完成")
        msg.setText(
            f"新版本已下载完成！\n\n"
            f"点击【确定】将关闭当前程序并开始全自动安装更新。\n"
            f"更新完成后，软件将自动重新启动为最新版本。"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Ok)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #1e1e24;
                color: #ffffff;
                font-family: "Microsoft YaHei", sans-serif;
            }
            QLabel {
                color: #e0e0e6;
                font-size: 13px;
            }
            QPushButton {
                background-color: #37474f;
                color: #ffffff;
                border-radius: 4px;
                padding: 6px 16px;
            }
        """)
        
        if msg.exec() == QMessageBox.StandardButton.Ok:
            self._run_updater_and_exit(temp_zip)
    
    def _run_updater_and_exit(self, temp_zip):
        """ 启动后台 PowerShell 执行静默解压替换，并退出当前程序 """
        import subprocess
        import sys
        import os
        
        current_exe = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
        exe_dir = os.path.dirname(current_exe)
        
        if getattr(sys, 'frozen', False):
            exe_name = os.path.basename(current_exe)
            
            # PowerShell 命令：
            # 1. 寻找正在运行的 VibePet 进程并强制结束它（防止用户未完全关闭或多开）
            # 2. 将正在运行的旧 exe 文件重命名为 .bak 以即时释放文件锁（防止由于多线程退出延迟导致的解压覆盖权限错误）
            # 3. 将新下载的 zip 包解压并覆盖到可执行文件所在目录 (exe_dir)
            # 4. 启动更新后的新版本 VibePet.exe
            # 5. 清理 zip 临时文件，并在新进程启动后安全移除旧 .bak 文件
            # 采用 -WindowStyle Hidden 隐藏 PowerShell 黑窗
            ps_command = (
                f'Start-Sleep -Seconds 1; '
                f'$exePath = Join-Path "{exe_dir}" "{exe_name}"; '
                f'$bakPath = "$exePath.bak"; '
                f'$proc = Get-Process -Name "{exe_name.replace(".exe", "")}" -ErrorAction SilentlyContinue; '
                f'if ($proc) {{ $proc | Stop-Process -Force; Start-Sleep -Seconds 1 }}; '
                f'if (Test-Path $bakPath) {{ Remove-Item $bakPath -Force -ErrorAction SilentlyContinue }}; '
                f'if (Test-Path $exePath) {{ Rename-Item $exePath -NewName "{exe_name}.bak" -Force -ErrorAction SilentlyContinue }}; '
                f'Expand-Archive -Path "{temp_zip}" -DestinationPath "{exe_dir}" -Force; '
                f'Start-Process -FilePath "$exePath" -WorkingDirectory "{exe_dir}"; '
                f'Remove-Item -Path "{temp_zip}" -Force -ErrorAction SilentlyContinue; '
                f'Start-Sleep -Seconds 1; '
                f'if (Test-Path $bakPath) {{ Remove-Item $bakPath -Force -ErrorAction SilentlyContinue }}'
            )
            
            try:
                subprocess.Popen(
                    ["powershell", "-WindowStyle", "Hidden", "-Command", ps_command],
                    shell=True,
                    creationflags=0x08000000  # CREATE_NO_WINDOW
                )
                logger.info("Automatic updater script launched via PowerShell background task.")
                self._quit_for_update()
            except Exception as e:
                logger.error(f"Failed to start automatic updater: {e}")
                self.lbl_update_status.setText(f"<span style='color:#ff9800;'>更新失败: {e}</span>")
        else:
            # 开发环境下仅解压并提示
            try:
                import zipfile
                with zipfile.ZipFile(temp_zip, 'r') as zf:
                    zf.extractall(exe_dir)
                os.remove(temp_zip)
                
                msg = QMessageBox(self)
                msg.setWindowTitle("更新成功 (开发环境)")
                msg.setText("开发环境：更新包已成功解压并覆盖当前工作目录。请手动重启以应用更新。")
                msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg.exec()
            except Exception as e:
                self.lbl_update_status.setText(f"<span style='color:#ff9800;'>解压失败: {e}</span>")
    
    def _quit_for_update(self):
        """ 退出程序以便更新器替换 exe """
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    def load_values(self):
        """ Read config manager and populate form elements """
        switches = self.config.get("reminder_switches", {})
        self.cb_game.setChecked(switches.get("game_sedentary", True))
        self.cb_sedentary.setChecked(switches.get("sedentary", True))
        self.cb_late_night.setChecked(switches.get("late_night", True))
        self.cb_positive.setChecked(switches.get("positive", True))
        self.cb_fatigue.setChecked(switches.get("fatigue", True))

        thresholds = self.config.get("thresholds", {})
        self.sb_game.setValue(thresholds.get("game_limit_minutes", 120))
        self.sb_sedentary.setValue(thresholds.get("sedentary_minutes", 60))
        self.sb_late_night.setValue(thresholds.get("late_night_minutes", 30))
        self.sb_positive.setValue(thresholds.get("positive_minutes", 5))
        self.sb_fatigue.setValue(thresholds.get("fatigue_minutes", 480))

        # 动态填充各分类文本框内容
        categories = self.config.get_categories()
        for cat_id, te in self.category_textedits.items():
            if cat_id in categories:
                app_list = self.config.get(f"{cat_id}_apps", [])
                te.setPlainText(", ".join(app_list))

        # 宠物外观设置
        self.slider_size.setValue(self.config.get("pet_size", 200))
        self.lbl_size_value.setText(f"{self.slider_size.value()} px")
        self.cb_window_locked.setChecked(self.config.get("window_locked", False))
        self.cb_mouse_passthrough.setChecked(self.config.get("mouse_passthrough", False))
        self.cb_show_bubble.setChecked(self.config.get("show_app_bubble", True))
        self.cb_screen_snapping.setChecked(self.config.get("screen_snapping", True))
        self.cb_todo_visible.setChecked(self.config.get("todo_visible", False))
        theme_val = self.config.get("theme_mode", "light")
        self.combo_theme.setCurrentIndex(1 if theme_val == "light" else 0)

        # 气泡透明度
        opacity = int(self.config.get("bubble_opacity", 1.0) * 100)
        self.slider_bubble_opacity.setValue(opacity)
        self.lbl_opacity_value.setText(f"{opacity}%")
        self.sb_bubble_font_size.setValue(self.config.get("app_bubble_font_size", 9))

        # 随机情绪设置
        self.cb_random_emotions.setChecked(self.config.get("random_emotions", True))

        # 系统监控设置
        self.cb_sysmon_enabled.setChecked(self.config.get("sys_monitor_enabled", True))
        sys_items = self.config.get("sys_monitor_items", {})
        self.cb_show_cpu.setChecked(sys_items.get("cpu", True))
        self.cb_show_memory.setChecked(sys_items.get("memory", True))
        self.cb_show_disk.setChecked(sys_items.get("disk", False))
        self.cb_show_network.setChecked(sys_items.get("network", False))
        self.cb_show_gpu.setChecked(sys_items.get("gpu", False))
        self.sb_sysmon_interval.setValue(self.config.get("sys_monitor_interval", 2))
        
        # 划词统计设置
        self.cb_word_count_enabled.setChecked(self.config.get("word_count_enabled", False))

        # 加载下载加速镜像源设置
        mirror_val = self.config.get("update_mirror", "自动选择 (多镜像测速)")
        idx = self.combo_mirror.findText(mirror_val)
        if idx >= 0:
            self.combo_mirror.setCurrentIndex(idx)
        else:
            self.combo_mirror.setCurrentIndex(0)

        # 加载各时段概率
        probs = self.config.get("emotion_probabilities", {})
        day = probs.get("day", {})
        self.sb_day_sleep.setValue(day.get("sleep", 2))
        self.sb_day_happy.setValue(day.get("happy", 15))
        self.sb_day_tired.setValue(day.get("tired", 3))

        evening = probs.get("evening", {})
        self.sb_evening_sleep.setValue(evening.get("sleep", 5))
        self.sb_evening_happy.setValue(evening.get("happy", 10))
        self.sb_evening_tired.setValue(evening.get("tired", 8))

        night = probs.get("night", {})
        self.sb_night_sleep.setValue(night.get("sleep", 20))
        self.sb_night_happy.setValue(night.get("happy", 5))
        self.sb_night_tired.setValue(night.get("tired", 15))

    def save_values(self):
        """ Validate and save settings back to config manager """
        # 首先将当前所有 textedit 缓存回 config 内存
        self.cache_current_apps_inputs()

        # 校验各分类的冲突
        categories = self.config.get_categories()
        all_apps = {}
        has_overlap = False
        overlapping_apps = set()
        
        for cat_id in categories.keys():
            apps = self.config.get(f"{cat_id}_apps", [])
            for app in apps:
                if app in all_apps:
                    overlapping_apps.add(app)
                    has_overlap = True
                else:
                    all_apps[app] = cat_id
                    
        if has_overlap:
            # Styled warning message box to prevent dark text on dark background
            msg = QMessageBox(None)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("名单冲突")
            msg.setText(f"进程 {list(overlapping_apps)} 同时存在于多个名单中，请移除重复项。")
            msg.setStyleSheet("""
                QMessageBox {
                    background-color: #1e1e24;
                    color: #ffffff;
                    font-family: "Microsoft YaHei", sans-serif;
                }
                QLabel {
                    color: #ff8a80;
                    font-size: 13px;
                }
                QPushButton {
                    background-color: #37474f;
                    color: #ffffff;
                    border-radius: 4px;
                    padding: 6px 16px;
                }
            """)
            msg.exec()
            return

        # Update config dictionary
        self.config.set("reminder_switches", {
            "game_sedentary": self.cb_game.isChecked(),
            "sedentary": self.cb_sedentary.isChecked(),
            "late_night": self.cb_late_night.isChecked(),
            "positive": self.cb_positive.isChecked(),
            "fatigue": self.cb_fatigue.isChecked()
        })

        self.config.set("thresholds", {
            "game_limit_minutes": self.sb_game.value(),
            "sedentary_minutes": self.sb_sedentary.value(),
            "late_night_minutes": self.sb_late_night.value(),
            "positive_minutes": self.sb_positive.value(),
            "fatigue_minutes": self.sb_fatigue.value()
        })

        # 各分类 apps 在 cache_current_apps_inputs 里已保存到 self.config

        # 宠物外观设置
        self.config.set("pet_size", self.slider_size.value())
        self.config.set("window_locked", self.cb_window_locked.isChecked())
        self.config.set("mouse_passthrough", self.cb_mouse_passthrough.isChecked())
        self.config.set("show_app_bubble", self.cb_show_bubble.isChecked())
        self.config.set("screen_snapping", self.cb_screen_snapping.isChecked())
        self.config.set("todo_visible", self.cb_todo_visible.isChecked())
        self.config.set("bubble_opacity", self.slider_bubble_opacity.value() / 100.0)
        self.config.set("app_bubble_font_size", self.sb_bubble_font_size.value())
        theme_val = "light" if self.combo_theme.currentIndex() == 1 else "dark"
        self.config.set("theme_mode", theme_val)

        # 系统监控设置
        self.config.set("sys_monitor_enabled", self.cb_sysmon_enabled.isChecked())
        self.config.set("sys_monitor_items", {
            "cpu": self.cb_show_cpu.isChecked(),
            "memory": self.cb_show_memory.isChecked(),
            "disk": self.cb_show_disk.isChecked(),
            "network": self.cb_show_network.isChecked(),
            "gpu": self.cb_show_gpu.isChecked()
        })
        self.config.set("sys_monitor_interval", self.sb_sysmon_interval.value())

        # 划词统计设置
        self.config.set("word_count_enabled", self.cb_word_count_enabled.isChecked())
        self.config.set("word_count_mode", "bubble")

        # 随机情绪设置
        self.config.set("random_emotions", self.cb_random_emotions.isChecked())
        self.config.set("emotion_probabilities", {
            "day": {
                "sleep": self.sb_day_sleep.value(),
                "happy": self.sb_day_happy.value(),
                "tired": self.sb_day_tired.value()
            },
            "evening": {
                "sleep": self.sb_evening_sleep.value(),
                "happy": self.sb_evening_happy.value(),
                "tired": self.sb_evening_tired.value()
            },
            "night": {
                "sleep": self.sb_night_sleep.value(),
                "happy": self.sb_night_happy.value(),
                "tired": self.sb_night_tired.value()
            }
        })

        # 保存下载加速镜像源设置
        self.config.set("update_mirror", self.combo_mirror.currentText())

        self.config.save_config()
        # 发射信号通知主窗口应用新配置
        self.settings_changed.emit()
        # 保存后不关闭对话框，仅显示成功提示
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("保存成功")
        msg.setText("设置已保存并生效！")
        self._apply_msg_style(msg, is_warning=False)
        msg.exec()

    def _update_time(self):
        """ 更新时间显示 """
        now = datetime.datetime.now()
        self.lbl_time.setText(now.strftime("%Y-%m-%d %H:%M:%S"))

    def _confirm_reset(self, tab_name):
        """ 通用确认对话框 """
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("确认恢复")
        msg.setText(f"确定要将【{tab_name}】恢复为默认值吗？")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        self._apply_msg_style(msg, is_warning=True)
        return msg.exec() == QMessageBox.StandardButton.Yes

    def _show_ok(self, text):
        """ 通用成功提示 """
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("恢复成功")
        msg.setText(text)
        self._apply_msg_style(msg, is_warning=False)
        msg.exec()

    def reset_reminders_tab(self):
        """ 恢复提醒设置Tab为默认 """
        if not self._confirm_reset("提醒设置"):
            return
        from core.config import DEFAULT_CONFIG
        self.config.set("reminder_switches", DEFAULT_CONFIG["reminder_switches"].copy())
        self.config.set("thresholds", DEFAULT_CONFIG["thresholds"].copy())
        self.config.save_config()
        # 重新加载当前Tab的值
        switches = DEFAULT_CONFIG["reminder_switches"]
        self.cb_game.setChecked(switches["game_sedentary"])
        self.cb_sedentary.setChecked(switches["sedentary"])
        self.cb_late_night.setChecked(switches["late_night"])
        self.cb_positive.setChecked(switches["positive"])
        self.cb_fatigue.setChecked(switches["fatigue"])
        thresholds = DEFAULT_CONFIG["thresholds"]
        self.sb_game.setValue(thresholds["game_limit_minutes"])
        self.sb_sedentary.setValue(thresholds["sedentary_minutes"])
        self.sb_late_night.setValue(thresholds["late_night_minutes"])
        self.sb_positive.setValue(thresholds["positive_minutes"])
        self.sb_fatigue.setValue(thresholds["fatigue_minutes"])
        self.settings_changed.emit()
        self._show_ok("提醒设置已恢复为默认值！")

    def reset_appearance_tab(self):
        """ 恢复宠物外观Tab为默认 """
        if not self._confirm_reset("宠物外观"):
            return
        from core.config import DEFAULT_CONFIG
        self.config.set("pet_size", DEFAULT_CONFIG["pet_size"])
        self.config.set("window_locked", DEFAULT_CONFIG["window_locked"])
        self.config.set("mouse_passthrough", DEFAULT_CONFIG["mouse_passthrough"])
        self.config.set("show_app_bubble", DEFAULT_CONFIG["show_app_bubble"])
        self.config.set("screen_snapping", DEFAULT_CONFIG["screen_snapping"])
        self.config.set("todo_visible", DEFAULT_CONFIG["todo_visible"])
        self.config.set("bubble_opacity", DEFAULT_CONFIG["bubble_opacity"])
        self.config.set("app_bubble_font_size", DEFAULT_CONFIG.get("app_bubble_font_size", 9))
        self.config.set("theme_mode", DEFAULT_CONFIG["theme_mode"])
        self.config.save_config()
        self.slider_size.setValue(DEFAULT_CONFIG["pet_size"])
        self.lbl_size_value.setText(f"{DEFAULT_CONFIG['pet_size']} px")
        self.cb_window_locked.setChecked(DEFAULT_CONFIG["window_locked"])
        self.cb_mouse_passthrough.setChecked(DEFAULT_CONFIG["mouse_passthrough"])
        self.cb_show_bubble.setChecked(DEFAULT_CONFIG["show_app_bubble"])
        self.cb_screen_snapping.setChecked(DEFAULT_CONFIG["screen_snapping"])
        self.cb_todo_visible.setChecked(DEFAULT_CONFIG["todo_visible"])
        opacity = int(DEFAULT_CONFIG["bubble_opacity"] * 100)
        self.slider_bubble_opacity.setValue(opacity)
        self.lbl_opacity_value.setText(f"{opacity}%")
        self.sb_bubble_font_size.setValue(DEFAULT_CONFIG.get("app_bubble_font_size", 9))
        theme_val = DEFAULT_CONFIG["theme_mode"]
        self.combo_theme.setCurrentIndex(1 if theme_val == "light" else 0)
        self.settings_changed.emit()
        self._show_ok("宠物外观已恢复为默认值！")

    def reset_emotions_tab(self):
        """ 恢复随机情绪Tab为默认 """
        if not self._confirm_reset("随机情绪"):
            return
        from core.config import DEFAULT_CONFIG
        self.config.set("random_emotions", DEFAULT_CONFIG["random_emotions"])
        self.config.set("emotion_probabilities", {
            k: v.copy() for k, v in DEFAULT_CONFIG["emotion_probabilities"].items()
        })
        self.config.save_config()
        self.cb_random_emotions.setChecked(DEFAULT_CONFIG["random_emotions"])
        day = DEFAULT_CONFIG["emotion_probabilities"]["day"]
        self.sb_day_sleep.setValue(day["sleep"])
        self.sb_day_happy.setValue(day["happy"])
        self.sb_day_tired.setValue(day["tired"])
        evening = DEFAULT_CONFIG["emotion_probabilities"]["evening"]
        self.sb_evening_sleep.setValue(evening["sleep"])
        self.sb_evening_happy.setValue(evening["happy"])
        self.sb_evening_tired.setValue(evening["tired"])
        night = DEFAULT_CONFIG["emotion_probabilities"]["night"]
        self.sb_night_sleep.setValue(night["sleep"])
        self.sb_night_happy.setValue(night["happy"])
        self.sb_night_tired.setValue(night["tired"])
        self.settings_changed.emit()
        self._show_ok("随机情绪已恢复为默认值！")

    def reset_apps_tab(self):
        """ 恢复进程名单Tab为默认 """
        if not self._confirm_reset("进程名单"):
            return
        from core.config import DEFAULT_CONFIG
        
        # 恢复默认的 custom_categories，清除所有自定义分类及其 app 名单
        self.config.set("custom_categories", DEFAULT_CONFIG["custom_categories"].copy())
        
        # 只保留 work, game, leisure，并把其他的配置项删掉/重置
        self.config.set("work_apps", DEFAULT_CONFIG["work_apps"].copy())
        self.config.set("game_apps", DEFAULT_CONFIG["game_apps"].copy())
        self.config.set("leisure_apps", DEFAULT_CONFIG["leisure_apps"].copy())
        
        # 移除任何其他自定义分类的 app 配置项
        default_cats = ["work", "game", "leisure"]
        keys_to_delete = []
        for k in list(self.config.config.keys()):
            if k.endswith("_apps") and k[:-5] not in default_cats:
                keys_to_delete.append(k)
        for k in keys_to_delete:
            if k in self.config.config:
                del self.config.config[k]
                
        self.config.save_config()
        self.settings_changed.emit()
        
        # 动态重建 UI 并恢复默认值
        self.rebuild_apps_tab_content(initial=True)
        self._show_ok("进程名单已恢复为默认值！")

    def reset_sysmon_tab(self):
        """ 恢复系统监控Tab为默认 """
        if not self._confirm_reset("系统监控"):
            return
        from core.config import DEFAULT_CONFIG
        self.config.set("sys_monitor_enabled", DEFAULT_CONFIG["sys_monitor_enabled"])
        self.config.set("sys_monitor_items", DEFAULT_CONFIG["sys_monitor_items"].copy())
        self.config.set("sys_monitor_interval", DEFAULT_CONFIG["sys_monitor_interval"])
        self.config.set("word_count_enabled", DEFAULT_CONFIG["word_count_enabled"])
        self.config.set("word_count_mode", DEFAULT_CONFIG["word_count_mode"])
        self.config.save_config()
        self.cb_sysmon_enabled.setChecked(DEFAULT_CONFIG["sys_monitor_enabled"])
        items = DEFAULT_CONFIG["sys_monitor_items"]
        self.cb_show_cpu.setChecked(items["cpu"])
        self.cb_show_memory.setChecked(items["memory"])
        self.cb_show_disk.setChecked(items["disk"])
        self.cb_show_network.setChecked(items["network"])
        self.cb_show_gpu.setChecked(items["gpu"])
        self.sb_sysmon_interval.setValue(DEFAULT_CONFIG["sys_monitor_interval"])
        self.cb_word_count_enabled.setChecked(DEFAULT_CONFIG["word_count_enabled"])
        self.settings_changed.emit()
        self._show_ok("系统监控已恢复为默认值！")

    # === 自定义分类/名单动态渲染辅助函数 ===
    def cache_current_apps_inputs(self):
        """ 将当前界面上所有分类输入框的内容临时更新至 config (仅在内存中，不保存到硬盘)，防止刷新 UI 时丢失输入 """
        if not hasattr(self, 'category_textedits'):
            return
        categories = self.config.get_categories()
        for cat_id, te in self.category_textedits.items():
            if cat_id not in categories:
                continue
            try:
                # 过滤并提取文本，换行或逗号分隔
                text = te.toPlainText().replace('\n', ',').replace('\r', ',')
                apps = [name.strip().lower() for name in text.split(",") if name.strip()]
                self.config.set(f"{cat_id}_apps", apps)
            except Exception as e:
                logger.error(f"Error caching apps inputs for {cat_id}: {e}")

    def rebuild_apps_tab_content(self, initial=False):
        """ 动态重建进程名单 Tab 中的所有分类表单和检测列表 """
        is_dark = (self.config.get("theme_mode", "light") == "dark")
        # 1. 缓存当前输入的文本值，防止刷新界面丢失
        if not initial:
            self.cache_current_apps_inputs()

        # 2. 清空 scroll_layout 中已有的控件
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        # 3. 添加“新增自定义分类”区块
        add_cat_group = QGroupBox("新增自定义分类")
        add_cat_layout = QHBoxLayout()
        add_cat_layout.setSpacing(8)
        
        self.txt_new_cat_name = QLineEdit()
        self.txt_new_cat_name.setPlaceholderText("输入新分类名称（如：学习、社交、办公）")
        bg_color = "#2b2b35" if is_dark else "#ffffff"
        text_color = "#ffffff" if is_dark else "#333333"
        border_color = "#455a64" if is_dark else "#cccccc"
        focus_color = "#81c784" if is_dark else "#2e7d32"
        self.txt_new_cat_name.setStyleSheet(f"""
            QLineEdit {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 6px;
            }}
            QLineEdit:focus {{
                border: 1px solid {focus_color};
            }}
        """)
        
        btn_add_cat = QPushButton("添加分类")
        btn_add_cat.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32;
                color: #ffffff;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #388e3c;
            }
        """)
        btn_add_cat.clicked.connect(self.add_custom_category)
        
        add_cat_layout.addWidget(self.txt_new_cat_name, stretch=1)
        add_cat_layout.addWidget(btn_add_cat)
        add_cat_group.setLayout(add_cat_layout)
        self.scroll_layout.addWidget(add_cat_group)

        # 4. 添加进程分类配置区块
        apps_group = QGroupBox("进程配置（换行或逗号分隔）")
        apps_inner = QVBoxLayout()
        apps_inner.setSpacing(10)

        self.category_textedits = {}
        categories = self.config.get_categories()

        for cat_id, cat_name in categories.items():
            # 为每个分类分配一个水平标题行，以便在右侧放“删除”按钮
            header_layout = QHBoxLayout()
            lbl_title = QLabel(f"<b>{cat_name}类进程名</b>:")
            title_color = "#81c784" if is_dark else "#2e7d32"
            lbl_title.setStyleSheet(f"font-size: 13px; color: {title_color};")
            header_layout.addWidget(lbl_title)
            header_layout.addStretch()

            # 自定义分类允许删除
            if cat_id not in ["work", "game", "leisure"]:
                btn_delete = QPushButton("删除该分类")
                btn_delete.setStyleSheet("""
                    QPushButton {
                        background-color: #c62828;
                        color: #ffffff;
                        padding: 2px 8px;
                        font-size: 11px;
                        font-weight: normal;
                        border-radius: 3px;
                    }
                    QPushButton:hover {
                        background-color: #d32f2f;
                    }
                """)
                btn_delete.clicked.connect(lambda checked=False, cid=cat_id: self.delete_custom_category(cid))
                header_layout.addWidget(btn_delete)

            apps_inner.addLayout(header_layout)

            te = QTextEdit()
            te.setPlaceholderText("换行或逗号分隔。例如: app1, app2")
            te.setMinimumHeight(60)
            
            # 从内存/配置中获取当前应用名列表
            app_list = self.config.get(f"{cat_id}_apps", [])
            te.setPlainText(", ".join(app_list))
            
            apps_inner.addWidget(te)
            self.category_textedits[cat_id] = te

        apps_group.setLayout(apps_inner)
        self.scroll_layout.addWidget(apps_group)

        # 5. 添加“未分类进程检测列表”区块
        detected_group = QGroupBox("检测到但未分类的进程")
        detected_layout = QVBoxLayout()
        detected_layout.setSpacing(8)

        detected_info = QLabel("💡 下方列出桌宠检测到但尚未分类的进程。选中后按快捷键或点击分类按钮快速归类：")
        detected_info.setWordWrap(True)
        detected_info.setObjectName("InfoLabel")
        detected_layout.addWidget(detected_info)

        shortcut_info = QLabel("<b>快捷键：</b> W-办公 | G-游戏 | L-休闲 | O-其他 | Delete-移除")
        shortcut_info.setWordWrap(True)
        shortcut_info.setObjectName("InfoLabel")
        detected_layout.addWidget(shortcut_info)

        self.lw_detected = QListWidget()
        self.lw_detected.setMinimumHeight(150)
        self.lw_detected.setMaximumHeight(250)
        self.lw_detected.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        lw_bg = "#2b2b35" if is_dark else "#ffffff"
        lw_fg = "#e0e0e6" if is_dark else "#333333"
        lw_border = "#42424a" if is_dark else "#cccccc"
        lw_sel_bg = "#37474f" if is_dark else "#e0e0e0"
        lw_sel_fg = "#81c784" if is_dark else "#2e7d32"
        lw_hov_bg = "#353545" if is_dark else "#f0f0f0"
        self.lw_detected.setStyleSheet(f"""
            QListWidget {{
                background-color: {lw_bg};
                color: {lw_fg};
                border: 1px solid {lw_border};
                border-radius: 6px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 4px 8px;
                border-radius: 3px;
            }}
            QListWidget::item:selected {{
                background-color: {lw_sel_bg};
                color: {lw_sel_fg};
            }}
            QListWidget::item:hover {{
                background-color: {lw_hov_bg};
            }}
        """)
        self.lw_detected.keyPressEvent = self._on_detected_list_keypress
        detected_layout.addWidget(self.lw_detected)

        # 分类动作按钮行
        btn_classify_layout = QHBoxLayout()
        btn_classify_layout.setSpacing(8)

        # 动态创建分类按钮（带颜色区分）
        shortcuts = {"work": "W", "game": "G", "leisure": "L"}
        btn_colors = {
            "work": ("#2e7d32", "#388e3c", "#1b5e20"),
            "game": ("#c62828", "#d32f2f", "#b71c1c"),
            "leisure": ("#1565c0", "#1976d2", "#0d47a1"),
        }
        custom_colors_list = [
            ("#7c4dff", "#8c5eff", "#6236df"), # 深紫色
            ("#ab47bc", "#ba68c8", "#8e24aa"), # 紫红色
            ("#00bfa5", "#1de9b6", "#00897b"), # 蓝绿色
            ("#ff6f00", "#ff8f00", "#e65100"), # 橙色
            ("#ec407a", "#f48fb1", "#d81b60"), # 玫瑰粉
            ("#26a69a", "#4db6ac", "#00796b"), # 哑致绿
            ("#78909c", "#90a4ae", "#546e7a"), # 蓝灰色
        ]
        for cat_id, cat_name in categories.items():
            btn_label = cat_name
            if cat_id in shortcuts:
                btn_label += f" ({shortcuts[cat_id]})"
            btn = QPushButton(btn_label)
            btn.setToolTip(f"将选中进程添加到{cat_name}类")
            
            # 确定按钮颜色：标准分类或从调色板中按哈希选取
            if cat_id in btn_colors:
                normal, hover, pressed = btn_colors[cat_id]
            else:
                color_index = abs(hash(cat_id)) % len(custom_colors_list)
                normal, hover, pressed = custom_colors_list[color_index]
                
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {normal};
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 6px 14px;
                    font-weight: bold;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {hover};
                }}
                QPushButton:pressed {{
                    background-color: {pressed};
                }}
                QToolTip {{
                    background-color: #ffffff;
                    color: #1a1a24;
                    border: 2px solid {normal};
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-family: "Microsoft YaHei", sans-serif;
                    font-size: 13px;
                    font-weight: bold;
                }}
            """)
            btn.clicked.connect(lambda checked=False, cid=cat_id: self._classify_selected(cid))
            btn_classify_layout.addWidget(btn)

        # "其他"按钮 - 灰色
        btn_to_other = QPushButton("其他 (O)")
        btn_to_other.setToolTip("将选中进程添加到其他类")
        btn_to_other.setStyleSheet("""
            QPushButton {
                background-color: #616161;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #757575;
            }
            QPushButton:pressed {
                background-color: #424242;
            }
            QToolTip {
                background-color: #ffffff;
                color: #1a1a24;
                border: 2px solid #616161;
                border-radius: 6px;
                padding: 6px 12px;
                font-family: "Microsoft YaHei", sans-serif;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        btn_to_other.clicked.connect(lambda: self._classify_selected("other"))
        btn_classify_layout.addWidget(btn_to_other)

        btn_classify_layout.addStretch()

        # "移除"按钮 - 棕色
        btn_remove_detected = QPushButton("移除 (Del)")
        btn_remove_detected.setToolTip("从列表中移除选中进程")
        btn_remove_detected.setStyleSheet("""
            QPushButton {
                background-color: #8d6e63;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #a1887f;
            }
            QPushButton:pressed {
                background-color: #6d4c41;
            }
            QToolTip {
                background-color: #ffffff;
                color: #1a1a24;
                border: 2px solid #8d6e63;
                border-radius: 6px;
                padding: 6px 12px;
                font-family: "Microsoft YaHei", sans-serif;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        btn_remove_detected.clicked.connect(self._remove_selected_detected)
        btn_classify_layout.addWidget(btn_remove_detected)

        detected_layout.addLayout(btn_classify_layout)

        # 刷新列表按钮
        btn_refresh_detected = QPushButton("🔄 刷新检测列表")
        btn_refresh_detected.clicked.connect(self._refresh_detected_apps)
        detected_layout.addWidget(btn_refresh_detected, alignment=Qt.AlignmentFlag.AlignRight)

        detected_group.setLayout(detected_layout)
        self.scroll_layout.addWidget(detected_group)

        # 6. 恢复默认按钮
        btn_reset_apps = QPushButton("恢复名单默认")
        btn_reset_apps.setObjectName("TabResetButton")
        btn_reset_apps.clicked.connect(self.reset_apps_tab)
        self.scroll_layout.addWidget(btn_reset_apps, alignment=Qt.AlignmentFlag.AlignRight)

        # 7. 动态刷新未分类列表
        self._refresh_detected_apps()

    def add_custom_category(self):
        """ 新增自定义分类 """
        cat_name = self.txt_new_cat_name.text().strip()
        if not cat_name:
            QMessageBox.warning(self, "错误", "分类名称不能为空！")
            return
            
        categories = self.config.get_categories()
        
        # 检查重名
        if cat_name in categories.values():
            QMessageBox.warning(self, "错误", f"分类【{cat_name}】已存在！")
            return
            
        # 生成唯一 ID
        import time
        cat_id = f"custom_{int(time.time())}"
        
        # 缓存当前输入，更新 custom_categories 并在内存中初始化新分类
        self.cache_current_apps_inputs()
        
        new_categories = categories.copy()
        new_categories[cat_id] = cat_name
        self.config.set("custom_categories", new_categories)
        self.config.set(f"{cat_id}_apps", [])
        
        # 保存设置
        self.config.save_config()
        
        # 重建 UI
        self.rebuild_apps_tab_content()

    def delete_custom_category(self, cat_id):
        """ 删除指定的自定义分类 """
        categories = self.config.get_categories()
        cat_name = categories.get(cat_id, cat_id)
        
        # 确认弹窗
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("确认删除")
        msg.setText(f"确定要删除自定义分类【{cat_name}】吗？\n删除后该分类下的所有配置进程将被清除。")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #1e1e24;
                color: #ffffff;
                font-family: "Microsoft YaHei", sans-serif;
            }
            QLabel {
                color: #ff8a80;
                font-size: 13px;
            }
            QPushButton {
                background-color: #37474f;
                color: #ffffff;
                border-radius: 4px;
                padding: 6px 16px;
            }
        """)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return
            
        # 缓存当前输入（排除要删除的这一个）
        self.cache_current_apps_inputs()
        
        # 更新分类
        new_categories = categories.copy()
        if cat_id in new_categories:
            del new_categories[cat_id]
        self.config.set("custom_categories", new_categories)
        
        # 删除对应的 apps 列表
        app_key = f"{cat_id}_apps"
        if app_key in self.config.config:
            del self.config.config[app_key]
            
        # 保存设置
        self.config.save_config()
        
        # 重建 UI
        self.rebuild_apps_tab_content()

    # === 未分类进程检测列表功能 ===
    def _refresh_detected_apps(self):
        """ 刷新检测到的未分类进程列表 """
        if not hasattr(self, 'lw_detected') or self.lw_detected is None:
            return
        self.lw_detected.clear()
        
        # 从数据库获取今日检测到的所有进程
        try:
            from core.database import DatabaseManager
            db = DatabaseManager()
            top_apps = db.get_today_top_apps(50)
        except Exception:
            top_apps = []
        
        # 获取当前配置中的所有分类名单
        categories = self.config.get_categories()
        all_categorized_apps = set()
        for cat_id in categories.keys():
            all_categorized_apps.update(self.config.get(f"{cat_id}_apps", []))
        
        # 过滤出未分类的进程
        detected = set()
        for app in top_apps:
            name = app.get("process_name", "").strip().lower()
            if name and name not in all_categorized_apps:
                detected.add(name)
        
        # 如果没有数据库数据，显示提示
        if not detected:
            item = QListWidgetItem("暂无未分类进程（使用软件后自动检测）")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.lw_detected.addItem(item)
            return
        
        # 添加到列表
        for name in sorted(detected):
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.lw_detected.addItem(item)
    
    def _on_detected_list_keypress(self, event):
        """ 处理检测列表的键盘快捷键 """
        key = event.key()
        
        if key == Qt.Key.Key_W:
            self._classify_selected("work")
        elif key == Qt.Key.Key_G:
            self._classify_selected("game")
        elif key == Qt.Key.Key_L:
            self._classify_selected("leisure")
        elif key == Qt.Key.Key_O:
            self._classify_selected("other")
        elif key == Qt.Key.Key_Delete:
            self._remove_selected_detected()
        else:
            # 其他按键交给默认处理
            QListWidget.keyPressEvent(self.lw_detected, event)
    
    def _classify_selected(self, category):
        """ 将选中的进程分类到指定类别 """
        if not hasattr(self, 'lw_detected') or self.lw_detected is None:
            return
        selected_items = self.lw_detected.selectedItems()
        if not selected_items:
            return
        
        names = []
        for item in selected_items:
            name = item.data(Qt.ItemDataRole.UserRole)
            if name:
                names.append(name)
        
        if not names:
            return
        
        if category == "other":
            # 其他类不保存到 any 列表，只是从检测列表移除
            pass
        elif category in self.category_textedits:
            # 找到对应的 QTextEdit 并追加内容
            te = self.category_textedits[category]
            current_text = te.toPlainText().strip()
            new_names = ", ".join(names)
            te.setPlainText(current_text + ", " + new_names if current_text else new_names)
            
            # 临时更新到 config 并保存
            self.cache_current_apps_inputs()
            self.config.save_config()
        
        # 从检测列表移除
        for item in selected_items:
            row = self.lw_detected.row(item)
            self.lw_detected.takeItem(row)
        
        # 自动保存并通知主窗口配置已变更
        self.save_values()
        self.settings_changed.emit()
    
    def _remove_selected_detected(self):
        """ 从检测列表中移除选中的进程 """
        if not hasattr(self, 'lw_detected') or self.lw_detected is None:
            return
        selected_items = self.lw_detected.selectedItems()
        for item in selected_items:
            row = self.lw_detected.row(item)
            self.lw_detected.takeItem(row)

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
                    background-color: #37474f;
                    color: #ffffff;
                    border-radius: 4px;
                    padding: 6px 16px;
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
                    background-color: #e0e0e0;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    padding: 6px 16px;
                }}
            """)

    def apply_styles(self):
        """ Apply modern stylesheet based on light/dark mode """
        is_dark = (self.config.get("theme_mode", "light") == "dark")
        if is_dark:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e1e24;
                    color: #e0e0e6;
                    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                }
                #DialogTitle {
                    font-size: 18px;
                    font-weight: bold;
                    color: #81c784;
                    padding-bottom: 5px;
                }
                QTabWidget::pane {
                    border: 1px solid #42424a;
                    border-radius: 6px;
                    background-color: #25252e;
                    top: -1px;
                }
                QScrollArea {
                    background-color: transparent;
                    border: none;
                }
                QScrollArea > QWidget > QWidget {
                    background-color: transparent;
                }
                #AppsScrollArea, #AppsScrollContent {
                    background-color: transparent;
                    background: transparent;
                }
                QTabBar::tab {
                    background-color: #2b2b35;
                    color: #90a4ae;
                    border: 1px solid #42424a;
                    border-bottom: none;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                    padding: 8px 18px;
                    margin-right: 2px;
                }
                QTabBar::tab:selected {
                    background-color: #25252e;
                    color: #81c784;
                    font-weight: bold;
                }
                QTabBar::tab:hover:!selected {
                    background-color: #353545;
                    color: #cfd8dc;
                }
                QGroupBox {
                    border: 1px solid #42424a;
                    border-radius: 8px;
                    margin-top: 10px;
                    padding-top: 15px;
                    font-weight: bold;
                    color: #90a4ae;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 10px;
                    padding: 0 5px;
                }
                QLabel {
                    color: #cfd8dc;
                    font-size: 12px;
                }
                #InfoLabel {
                    color: #90a4ae;
                    font-size: 11px;
                    padding: 8px;
                    background-color: #2b2b35;
                    border-radius: 6px;
                }
                QCheckBox {
                    color: #cfd8dc;
                    spacing: 8px;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    background-color: #2b2b35;
                    border: 1px solid #546e7a;
                    border-radius: 3px;
                }
                QCheckBox::indicator:checked {
                    background-color: #81c784;
                    border-color: #81c784;
                }
                QSpinBox {
                    background-color: #2b2b35;
                    color: #ffffff;
                    border: 1px solid #455a64;
                    border-radius: 4px;
                    padding: 2px 6px;
                    padding-right: 24px;
                    min-width: 100px;
                    min-height: 28px;
                }
                QSpinBox:focus {
                    border: 1px solid #81c784;
                }
                QSpinBox::up-button {
                    subcontrol-origin: border;
                    subcontrol-position: top right;
                    width: 18px;
                    border-left: 1px solid #455a64;
                    border-bottom: 1px solid #455a64;
                    background-color: #37474f;
                }
                QSpinBox::up-button:hover {
                    background-color: #455a64;
                }
                QSpinBox::down-button {
                    subcontrol-origin: border;
                    subcontrol-position: bottom right;
                    width: 18px;
                    border-left: 1px solid #455a64;
                    background-color: #37474f;
                }
                QSpinBox::down-button:hover {
                    background-color: #455a64;
                }
                QSpinBox::up-arrow {
                    border-left: 4px solid transparent;
                    border-right: 4px solid transparent;
                    border-bottom: 4px solid #cfd8dc;
                    width: 0;
                    height: 0;
                }
                QSpinBox::down-arrow {
                    border-left: 4px solid transparent;
                    border-right: 4px solid transparent;
                    border-top: 4px solid #cfd8dc;
                    width: 0;
                    height: 0;
                }
                QSlider::groove:horizontal {
                    border: 1px solid #455a64;
                    height: 6px;
                    background: #2b2b35;
                    border-radius: 3px;
                }
                QSlider::sub-page:horizontal {
                    background: #81c784;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #cfd8dc;
                    border: 1px solid #455a64;
                    width: 16px;
                    height: 16px;
                    margin: -5px 0;
                    border-radius: 8px;
                }
                QSlider::handle:horizontal:hover {
                    background: #ffffff;
                }
                QTextEdit {
                    background-color: #2b2b35;
                    color: #ffffff;
                    border: 1px solid #455a64;
                    border-radius: 6px;
                    padding: 6px;
                }
                QTextEdit:focus {
                    border: 1px solid #81c784;
                }
                 QPushButton {
                    background-color: #37474f;
                    color: #ffffff;
                    border: 1px solid #455a64;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #3d4f58;
                    color: #81c784;
                    border: 1px solid #81c784;
                }
                QPushButton:pressed {
                    background-color: #212c31;
                    color: #66bb6a;
                    border: 1px solid #66bb6a;
                }
                QPushButton[text="保存设置"] {
                    background-color: #2e7d32;
                    color: #ffffff;
                    border: 1px solid #2e7d32;
                }
                QPushButton[text="保存设置"]:hover {
                    background-color: #388e3c;
                    border: 1px solid #81c784;
                }
                QPushButton[text="保存设置"]:pressed {
                    background-color: #1b5e20;
                    border: 1px solid #66bb6a;
                }
                #TimeLabel {
                    color: #90a4ae;
                    font-size: 12px;
                    font-family: "Consolas", "Microsoft YaHei", monospace;
                }
                QPushButton#TabResetButton {
                    background-color: #455a64;
                    color: #cfd8dc;
                    border: 1px solid #455a64;
                    font-size: 11px;
                    padding: 4px 10px;
                    border-radius: 4px;
                }
                QPushButton#TabResetButton:hover {
                    background-color: #c62828;
                    color: #ffffff;
                    border: 1px solid #ef5350;
                }
                QPushButton#TabResetButton:pressed {
                    background-color: #b71c1c;
                    color: #ffffff;
                    border: 1px solid #e53935;
                }
                QComboBox {
                    background-color: #2b2b35;
                    color: #ffffff;
                    border: 1px solid #455a64;
                    border-radius: 4px;
                    padding: 2px 6px;
                    min-width: 120px;
                    min-height: 28px;
                }
                QComboBox:focus {
                    border: 1px solid #81c784;
                }
                QComboBox::drop-down {
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 20px;
                    border-left-width: 1px;
                    border-left-color: #455a64;
                    border-left-style: solid;
                }
                QComboBox QAbstractItemView {
                    background-color: #2b2b35;
                    color: #ffffff;
                    selection-background-color: #81c784;
                    selection-color: #1e1e24;
                    border: 1px solid #455a64;
                }
                #SettingCard {
                    background-color: #2b2b35;
                    border: 1px solid #42424a;
                    border-radius: 8px;
                }
                #SettingCard:hover {
                    border: 1px solid #81c784;
                    background-color: #353545;
                }
                #CardIcon {
                    background-color: #1e1e24;
                    border-radius: 18px;
                }
                #CardTitle {
                    color: #ffffff;
                    font-size: 13px;
                }
                #CardDesc {
                    color: #90a4ae;
                    font-size: 11px;
                }
                QToolTip {
                    background-color: #ffffff;
                    color: #1a1a24;
                    border: 2px solid #2e7d32;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-family: "Microsoft YaHei", sans-serif;
                    font-size: 13px;
                    font-weight: bold;
                }
                QScrollBar:vertical {
                    border: none;
                    background-color: #25252e;
                    width: 10px;
                    margin: 0px 0px 0px 0px;
                    border-radius: 5px;
                }
                QScrollBar::handle:vertical {
                    background-color: #455a64;
                    min-height: 20px;
                    border-radius: 5px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #81c784;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    border: none;
                    background: none;
                    height: 0px;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f5f5f7;
                    color: #333333;
                    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                }
                #DialogTitle {
                    font-size: 18px;
                    font-weight: bold;
                    color: #2e7d32;
                    padding-bottom: 5px;
                }
                QTabWidget::pane {
                    border: 1px solid #cccccc;
                    border-radius: 6px;
                    background-color: #ffffff;
                    top: -1px;
                }
                QScrollArea {
                    background-color: transparent;
                    border: none;
                }
                QScrollArea > QWidget > QWidget {
                    background-color: transparent;
                }
                #AppsScrollArea, #AppsScrollContent {
                    background-color: transparent;
                    background: transparent;
                }
                QTabBar::tab {
                    background-color: #e0e0e0;
                    color: #555555;
                    border: 1px solid #cccccc;
                    border-bottom: none;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                    padding: 8px 18px;
                    margin-right: 2px;
                }
                QTabBar::tab:selected {
                    background-color: #ffffff;
                    color: #2e7d32;
                    font-weight: bold;
                }
                QTabBar::tab:hover:!selected {
                    background-color: #d6d6d6;
                    color: #333333;
                }
                QGroupBox {
                    border: 1px solid #cccccc;
                    border-radius: 8px;
                    margin-top: 10px;
                    padding-top: 15px;
                    font-weight: bold;
                    color: #666666;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 10px;
                    padding: 0 5px;
                }
                QLabel {
                    color: #333333;
                    font-size: 12px;
                }
                #InfoLabel {
                    color: #555555;
                    font-size: 11px;
                    padding: 8px;
                    background-color: #e0e0e0;
                    border-radius: 6px;
                }
                QCheckBox {
                    color: #333333;
                    spacing: 8px;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    background-color: #ffffff;
                    border: 1px solid #cccccc;
                    border-radius: 3px;
                }
                QCheckBox::indicator:checked {
                    background-color: #2e7d32;
                    border-color: #2e7d32;
                }
                QSpinBox {
                    background-color: #ffffff;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    padding: 2px 6px;
                    padding-right: 24px;
                    min-width: 100px;
                    min-height: 28px;
                }
                QSpinBox:focus {
                    border: 1px solid #2e7d32;
                }
                QSpinBox::up-button {
                    subcontrol-origin: border;
                    subcontrol-position: top right;
                    width: 18px;
                    border-left: 1px solid #cccccc;
                    border-bottom: 1px solid #cccccc;
                    background-color: #e0e0e0;
                }
                QSpinBox::up-button:hover {
                    background-color: #d6d6d6;
                }
                QSpinBox::down-button {
                    subcontrol-origin: border;
                    subcontrol-position: bottom right;
                    width: 18px;
                    border-left: 1px solid #cccccc;
                    background-color: #e0e0e0;
                }
                QSpinBox::down-button:hover {
                    background-color: #d6d6d6;
                }
                QSpinBox::up-arrow {
                    border-left: 4px solid transparent;
                    border-right: 4px solid transparent;
                    border-bottom: 4px solid #555555;
                    width: 0;
                    height: 0;
                }
                QSpinBox::down-arrow {
                    border-left: 4px solid transparent;
                    border-right: 4px solid transparent;
                    border-top: 4px solid #555555;
                    width: 0;
                    height: 0;
                }
                QSlider::groove:horizontal {
                    border: 1px solid #cccccc;
                    height: 6px;
                    background: #e0e0e0;
                    border-radius: 3px;
                }
                QSlider::sub-page:horizontal {
                    background: #2e7d32;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #ffffff;
                    border: 1px solid #cccccc;
                    width: 16px;
                    height: 16px;
                    margin: -5px 0;
                    border-radius: 8px;
                }
                QSlider::handle:horizontal:hover {
                    background: #f5f5f7;
                }
                QTextEdit {
                    background-color: #ffffff;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 6px;
                    padding: 6px;
                }
                QTextEdit:focus {
                    border: 1px solid #2e7d32;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #e8f5e9;
                    color: #2e7d32;
                    border: 1px solid #2e7d32;
                }
                QPushButton:pressed {
                    background-color: #c8e6c9;
                    color: #1b5e20;
                    border: 1px solid #1b5e20;
                }
                QPushButton[text="保存设置"] {
                    background-color: #2e7d32;
                    color: #ffffff;
                    border: 1px solid #2e7d32;
                }
                QPushButton[text="保存设置"]:hover {
                    background-color: #388e3c;
                    border: 1px solid #4caf50;
                }
                QPushButton[text="保存设置"]:pressed {
                    background-color: #1b5e20;
                    border: 1px solid #388e3c;
                }
                #TimeLabel {
                    color: #555555;
                    font-size: 12px;
                    font-family: "Consolas", "Microsoft YaHei", monospace;
                }
                QPushButton#TabResetButton {
                    background-color: #e0e0e0;
                    color: #555555;
                    border: 1px solid #cccccc;
                    font-size: 11px;
                    padding: 4px 10px;
                    border-radius: 4px;
                }
                QPushButton#TabResetButton:hover {
                    background-color: #ffebee;
                    color: #c62828;
                    border: 1px solid #c62828;
                }
                QPushButton#TabResetButton:pressed {
                    background-color: #ffcdd2;
                    color: #b71c1c;
                    border: 1px solid #b71c1c;
                }
                QComboBox {
                    background-color: #ffffff;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    padding: 2px 6px;
                    min-width: 120px;
                    min-height: 28px;
                }
                QComboBox:focus {
                    border: 1px solid #2e7d32;
                }
                QComboBox::drop-down {
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 20px;
                    border-left-width: 1px;
                    border-left-color: #cccccc;
                    border-left-style: solid;
                }
                QComboBox QAbstractItemView {
                    background-color: #ffffff;
                    color: #333333;
                    selection-background-color: #a5d6a7;
                    selection-color: #1b5e20;
                    border: 1px solid #cccccc;
                }
                #SettingCard {
                    background-color: #ffffff;
                    border: 1px solid #e0e0e0;
                    border-radius: 8px;
                }
                #SettingCard:hover {
                    border: 1px solid #2e7d32;
                    background-color: #fafafa;
                }
                #CardIcon {
                    background-color: #f5f5f7;
                    border-radius: 18px;
                }
                #CardTitle {
                    color: #333333;
                    font-size: 13px;
                }
                #CardDesc {
                    color: #666666;
                    font-size: 11px;
                }
                QToolTip {
                    background-color: #ffffff;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    font-family: "Microsoft YaHei", sans-serif;
                    font-size: 11px;
                }
                QScrollBar:vertical {
                    border: none;
                    background-color: #f0f0f0;
                    width: 12px;
                    margin: 0px 0px 0px 0px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #b0bec5;
                    min-height: 20px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #2e7d32;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    border: none;
                    background: none;
                    height: 0px;
                }
            """)
        # Ensure combobox dropdown views (QListView) have the correct stylesheet applied directly to them
        # This prevents Windows Dark Mode from overriding the popup background with black while using light theme text
        combo_view_style = """
            QListView {
                background-color: #2b2b35;
                color: #ffffff;
                selection-background-color: #81c784;
                selection-color: #1e1e24;
                border: 1px solid #455a64;
            }
        """ if is_dark else """
            QListView {
                background-color: #ffffff;
                color: #333333;
                selection-background-color: #a5d6a7;
                selection-color: #1b5e20;
                border: 1px solid #cccccc;
            }
        """
        if hasattr(self, "combo_theme") and self.combo_theme.view():
            self.combo_theme.view().setStyleSheet(combo_view_style)
        if hasattr(self, "combo_mirror") and self.combo_mirror.view():
            self.combo_mirror.view().setStyleSheet(combo_view_style)
        
        # Update dynamic labels in the About tab
        link_color = "#81c784" if is_dark else "#2e7d32"
        title_color = "#81c784" if is_dark else "#2e7d32"
        if hasattr(self, "lbl_about_title"):
            self.lbl_about_title.setText(f"<h2 style='color:{title_color}; margin:0; padding:0;'>VibePet 桌面宠物</h2>")
        if hasattr(self, "lbl_github"):
            self.lbl_github.setText(f"<b>GitHub:</b> <a href='https://github.com/YTU22/vibepet' style='color:{link_color};'>github.com/YTU22/vibepet</a>")
        if hasattr(self, "lbl_website"):
            self.lbl_website.setText(f"<b>综合官网:</b> <a href='https://vibeharbor.art' style='color:{link_color};'>vibeharbor.art</a>")
