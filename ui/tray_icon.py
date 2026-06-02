import logging
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QAction, QPixmap
from PyQt6.QtCore import Qt
from utils.helpers import resource_path, set_auto_start, is_auto_start_enabled

APP_VERSION = "1.1.7"

logger = logging.getLogger("vibe_pet")


class TrayIcon(QSystemTrayIcon):
    def __init__(self, main_window, parent=None):
        # Resolve assets/icon.png path
        self.icon_path = resource_path("assets/icon.png")

        # Smoothly scale the icon to 32x32 or 64x64 based on screen DPI
        pixmap = QPixmap(self.icon_path)
        if not pixmap.isNull():
            # Standard scale is 32x32, High DPI is 64x64
            dpr = QApplication.primaryScreen().devicePixelRatio()
            target_size = 64 if dpr > 1.0 else 32
            scaled_pixmap = pixmap.scaled(
                target_size, target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            icon = QIcon(scaled_pixmap)
            logger.info(f"Tray icon scaled to {target_size}x{target_size} (DPR: {dpr})")
        else:
            icon = QIcon(self.icon_path)
            logger.warning("Tray icon image not loaded, using fallback icon.")

        super().__init__(icon, parent)

        self.main_win = main_window
        self.setup_menu()

        # Connect activation event (e.g. double click tray to show/hide pet)
        self.activated.connect(self.on_tray_activated)

        self.setToolTip("VibePet - 守护您的健康")
        self.show()
        logger.info("System Tray Icon initialized.")

    def setup_menu(self):
        self.menu = QMenu()

        # 1. Show/Hide Pet Window
        self.act_toggle = QAction("隐藏桌宠" if self.main_win.isVisible() else "显示桌宠", self)
        self.act_toggle.triggered.connect(self.toggle_pet_visibility)
        self.menu.addAction(self.act_toggle)

        self.menu.addSeparator()

        # 2. Stats Board
        self.act_stats = QAction("统计看板", self)
        self.act_stats.triggered.connect(self.main_win.open_stats_dialog)
        self.menu.addAction(self.act_stats)

        # 3. Settings Dialog
        self.act_settings = QAction("系统设置", self)
        self.act_settings.triggered.connect(self.main_win.open_settings_dialog)
        self.menu.addAction(self.act_settings)

        self.menu.addSeparator()

        # 4. 窗口锁定/解锁
        self.act_lock = QAction("锁定窗口位置", self)
        self.act_lock.setCheckable(True)
        self.act_lock.setChecked(self.main_win.window_locked)
        self.act_lock.triggered.connect(self.toggle_window_lock)
        self.menu.addAction(self.act_lock)

        # 5. 鼠标穿透
        self.act_passthrough = QAction("鼠标穿透", self)
        self.act_passthrough.setCheckable(True)
        self.act_passthrough.setChecked(self.main_win.mouse_passthrough)
        self.act_passthrough.triggered.connect(self.toggle_mouse_passthrough)
        self.menu.addAction(self.act_passthrough)

        # 5.5 便签待办
        self.act_todo = QAction("便签待办", self)
        self.act_todo.setCheckable(True)
        self.act_todo.setChecked(self.main_win.config.get("todo_visible", False))
        self.act_todo.triggered.connect(self.toggle_todo)
        self.menu.addAction(self.act_todo)

        self.menu.addSeparator()

        # 6. 开机自启动
        self.act_auto_start = QAction("开机自启动", self)
        self.act_auto_start.setCheckable(True)
        self.act_auto_start.setChecked(is_auto_start_enabled())
        self.act_auto_start.triggered.connect(self.toggle_auto_start)
        self.menu.addAction(self.act_auto_start)

        self.menu.addSeparator()

        # 7. 版本号（不可点击）
        self.act_version = QAction(f"v{APP_VERSION}", self)
        self.act_version.setEnabled(False)
        self.menu.addAction(self.act_version)

        # 8. Exit App
        self.act_exit = QAction("完全退出", self)
        self.act_exit.triggered.connect(self.main_win.quit_application)
        self.menu.addAction(self.act_exit)

        self.setContextMenu(self.menu)

    def toggle_pet_visibility(self):
        """ Toggle visibility of the desktop pet """
        if self.main_win.isVisible():
            self.main_win.hide()
            self.act_toggle.setText("显示桌宠")
            logger.info("Pet window hidden by user.")
        else:
            self.main_win.show()
            self.main_win.raise_()
            self.main_win.activateWindow()
            self.act_toggle.setText("隐藏桌宠")
            logger.info(f"[托盘] 用户手动显示宠物，可见性: {self.main_win.isVisible()}")

    def toggle_window_lock(self):
        """ 从托盘菜单切换窗口锁定状态 """
        new_state = not self.main_win.window_locked
        self.main_win.set_window_locked(new_state)
        self.act_lock.setChecked(new_state)

    def toggle_mouse_passthrough(self):
        """ 从托盘菜单切换鼠标穿透状态 """
        new_state = not self.main_win.mouse_passthrough
        self.main_win.set_mouse_passthrough(new_state)
        self.act_passthrough.setChecked(new_state)

    def update_tooltip(self, today_total_s, today_game_s):
        """ Dynamically update the hover tooltip text on the tray icon """
        total_h = today_total_s // 3600
        total_m = (today_total_s % 3600) // 60

        # Compute game duration
        game_h = today_game_s // 3600
        game_m = (today_game_s % 3600) // 60

        tooltip_text = (
            f"VibePet\n"
            f"今日已运行: {total_h}小时{total_m}分\n"
            f"游戏时间: {game_h}小时{game_m}分"
        )
        self.setToolTip(tooltip_text)

    def on_tray_activated(self, reason):
        """ Handle double click or single click on tray icon """
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # Single click
            pass
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:  # Double click
            self.toggle_pet_visibility()

    def toggle_auto_start(self):
        """ 切换开机自启动状态 """
        new_state = self.act_auto_start.isChecked()
        success = set_auto_start(new_state)
        if success:
            self.main_win.config.set("auto_start", new_state)
            logger.info(f"Auto-start set to: {new_state}")
        else:
            self.act_auto_start.setChecked(not new_state)

    def toggle_todo(self):
        """ 从托盘菜单切换便签窗口显示状态 """
        self.main_win.toggle_todo_window()

    def update_menu_text(self):
        """ Sync menu toggle text with current window visibility """
        if self.main_win.isVisible():
            self.act_toggle.setText("隐藏桌宠")
        else:
            self.act_toggle.setText("显示桌宠")
        # 同步锁定和穿透状态显示
        self.act_lock.setChecked(self.main_win.window_locked)
        self.act_passthrough.setChecked(self.main_win.mouse_passthrough)
        self.act_todo.setChecked(self.main_win.config.get("todo_visible", False))
        self.act_auto_start.setChecked(is_auto_start_enabled())
