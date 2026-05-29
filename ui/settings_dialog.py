import logging
import datetime
import webbrowser
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QSpinBox, QTextEdit, QPushButton, QGroupBox, QFormLayout, QMessageBox,
    QSlider, QTabWidget, QWidget as QWidgetBase
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QDesktopServices

from utils.helpers import resource_path, set_auto_start, is_auto_start_enabled

APP_VERSION = "1.0.2"

logger = logging.getLogger("vibe_pet")


class SettingsDialog(QDialog):
    # 设置变更信号，通知主窗口应用新配置
    settings_changed = pyqtSignal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager

        self.setWindowTitle("VibePet - 系统设置")
        # 不再固定大小，允许用户自由调节
        self.setMinimumSize(600, 720)
        self.resize(680, 800)
        # Prevent closing child widgets closing parent
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        
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
        reminders_layout = QVBoxLayout(tab_reminders)
        reminders_layout.setContentsMargins(15, 15, 15, 15)
        reminders_layout.setSpacing(12)

        # 1. Reminder Switches Group
        switches_group = QGroupBox("提醒功能开关")
        switches_layout = QVBoxLayout()
        switches_layout.setSpacing(10)

        self.cb_game = QCheckBox("游戏沉迷提醒（提醒适当放松）")
        self.cb_sedentary = QCheckBox("久坐提醒（建议起身活动）")
        self.cb_late_night = QCheckBox("深夜防熬夜提醒（关怀作息健康）")
        self.cb_positive = QCheckBox("正向激励（专注工作时给予正面反馈）")
        self.cb_fatigue = QCheckBox("疲劳状态强制提醒（每日电脑总使用警示）")

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
        self.tabs.addTab(tab_reminders, "提醒设置")

        # === Tab 2: 宠物外观 ===
        tab_appearance = QWidgetBase()
        appearance_layout = QVBoxLayout(tab_appearance)
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

        pet_group.setLayout(pet_form)
        appearance_layout.addWidget(pet_group)
        # Tab 2 恢复默认按钮
        btn_reset_appearance = QPushButton("恢复外观默认")
        btn_reset_appearance.setObjectName("TabResetButton")
        btn_reset_appearance.clicked.connect(self.reset_appearance_tab)
        appearance_layout.addWidget(btn_reset_appearance, alignment=Qt.AlignmentFlag.AlignRight)
        self.tabs.addTab(tab_appearance, "宠物外观")

        # === Tab 3: 随机情绪 ===
        tab_emotions = QWidgetBase()
        emotions_layout = QVBoxLayout(tab_emotions)
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
        self.tabs.addTab(tab_emotions, "随机情绪")

        # === Tab 4: 进程名单 ===
        tab_apps = QWidgetBase()
        apps_layout = QVBoxLayout(tab_apps)
        apps_layout.setContentsMargins(15, 15, 15, 15)
        apps_layout.setSpacing(10)

        apps_group = QGroupBox("进程名单（换行或逗号分隔）")
        apps_inner = QVBoxLayout()
        apps_inner.setSpacing(8)

        apps_inner.addWidget(QLabel("工作类进程名 (Work Apps):"))
        self.te_work = QTextEdit()
        self.te_work.setPlaceholderText("例如: code, pycharm, word, excel（换行或逗号分隔）")
        self.te_work.setMinimumHeight(60)
        apps_inner.addWidget(self.te_work)

        apps_inner.addWidget(QLabel("游戏类进程名 (Game Apps):"))
        self.te_game = QTextEdit()
        self.te_game.setPlaceholderText("例如: steam, genshinimpact, valorant, lol（换行或逗号分隔）")
        self.te_game.setMinimumHeight(60)
        apps_inner.addWidget(self.te_game)

        apps_inner.addWidget(QLabel("休闲类进程名 (Leisure Apps):"))
        self.te_leisure = QTextEdit()
        self.te_leisure.setPlaceholderText("例如: chrome, netflix, bilibili, qq, wechat（追剧、社交等，换行或逗号分隔）")
        self.te_leisure.setMinimumHeight(60)
        apps_inner.addWidget(self.te_leisure)

        apps_group.setLayout(apps_inner)
        apps_layout.addWidget(apps_group)
        # Tab 4 恢复默认按钮
        btn_reset_apps = QPushButton("恢复名单默认")
        btn_reset_apps.setObjectName("TabResetButton")
        btn_reset_apps.clicked.connect(self.reset_apps_tab)
        apps_layout.addWidget(btn_reset_apps, alignment=Qt.AlignmentFlag.AlignRight)
        self.tabs.addTab(tab_apps, "进程名单")

        # === Tab 5: 系统监控 ===
        tab_sysmon = QWidgetBase()
        sysmon_layout = QVBoxLayout(tab_sysmon)
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
        
        # Tab 5 恢复默认按钮
        btn_reset_sysmon = QPushButton("恢复监控默认")
        btn_reset_sysmon.setObjectName("TabResetButton")
        btn_reset_sysmon.clicked.connect(self.reset_sysmon_tab)
        sysmon_layout.addWidget(btn_reset_sysmon, alignment=Qt.AlignmentFlag.AlignRight)
        sysmon_layout.addStretch()
        self.tabs.addTab(tab_sysmon, "系统监控")

        # === Tab 6: 关于 ===
        tab_about = QWidgetBase()
        about_layout = QVBoxLayout(tab_about)
        about_layout.setContentsMargins(15, 15, 15, 15)
        about_layout.setSpacing(12)

        about_group = QGroupBox("关于 VibePet")
        about_inner = QVBoxLayout()
        about_inner.setSpacing(10)

        about_inner.addWidget(QLabel("<h2 style='color:#81c784;'>VibePet 桌面宠物</h2>"))
        about_inner.addWidget(QLabel(f"<b>版本号:</b> {APP_VERSION}"))
        about_inner.addWidget(QLabel("<b>作者:</b> 丞客Show"))
        
        # 官网链接标签（支持点击打开浏览器）
        lbl_website = QLabel("<b>官网:</b> <a href='https://vibeharbor.art' style='color:#81c784;'>vibeharbor.art</a>")
        lbl_website.setOpenExternalLinks(True)
        about_inner.addWidget(lbl_website)
        
        about_inner.addWidget(QLabel("实时监测软件时长，守护您的作息与健康！"))
        
        # 开机自启动选项
        about_inner.addSpacing(20)
        self.cb_auto_start = QCheckBox("开机自动启动 VibePet")
        self.cb_auto_start.setChecked(is_auto_start_enabled())
        self.cb_auto_start.stateChanged.connect(self._on_auto_start_changed)
        about_inner.addWidget(self.cb_auto_start)
        
        about_group.setLayout(about_inner)
        about_layout.addWidget(about_group)
        about_layout.addStretch()
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

        work_list = self.config.get("work_apps", [])
        self.te_work.setPlainText(", ".join(work_list))

        game_list = self.config.get("game_apps", [])
        self.te_game.setPlainText(", ".join(game_list))

        leisure_list = self.config.get("leisure_apps", [])
        self.te_leisure.setPlainText(", ".join(leisure_list))

        # 宠物外观设置
        self.slider_size.setValue(self.config.get("pet_size", 200))
        self.lbl_size_value.setText(f"{self.slider_size.value()} px")
        self.cb_window_locked.setChecked(self.config.get("window_locked", False))
        self.cb_mouse_passthrough.setChecked(self.config.get("mouse_passthrough", False))
        self.cb_show_bubble.setChecked(self.config.get("show_app_bubble", True))

        # 气泡透明度
        opacity = int(self.config.get("bubble_opacity", 1.0) * 100)
        self.slider_bubble_opacity.setValue(opacity)
        self.lbl_opacity_value.setText(f"{opacity}%")

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
        # Process and clean input lists (supports commas and newlines mix)
        work_text = self.te_work.toPlainText().replace('\n', ',').replace('\r', ',')
        game_text = self.te_game.toPlainText().replace('\n', ',').replace('\r', ',')
        leisure_text = self.te_leisure.toPlainText().replace('\n', ',').replace('\r', ',')

        work_apps = [name.strip().lower() for name in work_text.split(",") if name.strip()]
        game_apps = [name.strip().lower() for name in game_text.split(",") if name.strip()]
        leisure_apps = [name.strip().lower() for name in leisure_text.split(",") if name.strip()]

        # Check overlaps
        overlap = set(work_apps).intersection(set(game_apps))
        overlap = overlap.union(set(work_apps).intersection(set(leisure_apps)))
        overlap = overlap.union(set(game_apps).intersection(set(leisure_apps)))
        if overlap:
            # Styled warning message box to prevent dark text on dark background
            msg = QMessageBox(None)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("名单冲突")
            msg.setText(f"进程 {list(overlap)} 同时存在于多个名单中，请移除重复项。")
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

        self.config.set("work_apps", work_apps)
        self.config.set("game_apps", game_apps)
        self.config.set("leisure_apps", leisure_apps)

        # 宠物外观设置
        self.config.set("pet_size", self.slider_size.value())
        self.config.set("window_locked", self.cb_window_locked.isChecked())
        self.config.set("mouse_passthrough", self.cb_mouse_passthrough.isChecked())
        self.config.set("show_app_bubble", self.cb_show_bubble.isChecked())
        self.config.set("bubble_opacity", self.slider_bubble_opacity.value() / 100.0)

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

        self.config.save_config()
        # 发射信号通知主窗口应用新配置
        self.settings_changed.emit()
        # 保存后不关闭对话框，仅显示成功提示
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("保存成功")
        msg.setText("设置已保存并生效！")
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #1e1e24;
                color: #ffffff;
                font-family: "Microsoft YaHei", sans-serif;
            }
            QLabel {
                color: #81c784;
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
        return msg.exec() == QMessageBox.StandardButton.Yes

    def _show_ok(self, text):
        """ 通用成功提示 """
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("恢复成功")
        msg.setText(text)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #1e1e24;
                color: #ffffff;
                font-family: "Microsoft YaHei", sans-serif;
            }
            QLabel {
                color: #81c784;
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
        self.config.set("bubble_opacity", DEFAULT_CONFIG["bubble_opacity"])
        self.config.save_config()
        self.slider_size.setValue(DEFAULT_CONFIG["pet_size"])
        self.lbl_size_value.setText(f"{DEFAULT_CONFIG['pet_size']} px")
        self.cb_window_locked.setChecked(DEFAULT_CONFIG["window_locked"])
        self.cb_mouse_passthrough.setChecked(DEFAULT_CONFIG["mouse_passthrough"])
        self.cb_show_bubble.setChecked(DEFAULT_CONFIG["show_app_bubble"])
        opacity = int(DEFAULT_CONFIG["bubble_opacity"] * 100)
        self.slider_bubble_opacity.setValue(opacity)
        self.lbl_opacity_value.setText(f"{opacity}%")
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
        self.config.set("work_apps", DEFAULT_CONFIG["work_apps"].copy())
        self.config.set("game_apps", DEFAULT_CONFIG["game_apps"].copy())
        self.config.set("leisure_apps", DEFAULT_CONFIG["leisure_apps"].copy())
        self.config.save_config()
        self.te_work.setPlainText(", ".join(DEFAULT_CONFIG["work_apps"]))
        self.te_game.setPlainText(", ".join(DEFAULT_CONFIG["game_apps"]))
        self.te_leisure.setPlainText(", ".join(DEFAULT_CONFIG["leisure_apps"]))
        self.settings_changed.emit()
        self._show_ok("进程名单已恢复为默认值！")

    def reset_sysmon_tab(self):
        """ 恢复系统监控Tab为默认 """
        if not self._confirm_reset("系统监控"):
            return
        from core.config import DEFAULT_CONFIG
        self.config.set("sys_monitor_enabled", DEFAULT_CONFIG["sys_monitor_enabled"])
        self.config.set("sys_monitor_items", DEFAULT_CONFIG["sys_monitor_items"].copy())
        self.config.set("sys_monitor_interval", DEFAULT_CONFIG["sys_monitor_interval"])
        self.config.save_config()
        self.cb_sysmon_enabled.setChecked(DEFAULT_CONFIG["sys_monitor_enabled"])
        items = DEFAULT_CONFIG["sys_monitor_items"]
        self.cb_show_cpu.setChecked(items["cpu"])
        self.cb_show_memory.setChecked(items["memory"])
        self.cb_show_disk.setChecked(items["disk"])
        self.cb_show_network.setChecked(items["network"])
        self.cb_show_gpu.setChecked(items["gpu"])
        self.sb_sysmon_interval.setValue(DEFAULT_CONFIG["sys_monitor_interval"])
        self.settings_changed.emit()
        self._show_ok("系统监控已恢复为默认值！")

    def apply_styles(self):
        """ Apply modern dark stylesheet """
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
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #455a64;
            }
            QPushButton:pressed {
                background-color: #263238;
            }
            QPushButton[text="保存设置"] {
                background-color: #2e7d32;
            }
            QPushButton[text="保存设置"]:hover {
                background-color: #388e3c;
            }
            QPushButton[text="保存设置"]:pressed {
                background-color: #1b5e20;
            }
            #TimeLabel {
                color: #90a4ae;
                font-size: 12px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
            }
            QPushButton#TabResetButton {
                background-color: #455a64;
                color: #cfd8dc;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 4px;
            }
            QPushButton#TabResetButton:hover {
                background-color: #c62828;
                color: #ffffff;
            }
        """)
