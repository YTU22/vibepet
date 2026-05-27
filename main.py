import os
import sys

# Dummy stream to prevent crash when writing warnings/prints in headless GUI mode (Bug 4)
class DummyStream:
    def write(self, *args, **kwargs):
        pass
    def flush(self, *args, **kwargs):
        pass

if sys.stdout is None:
    sys.stdout = DummyStream()
else:
    try:
        sys.stdout.write("")
        sys.stdout.flush()
    except Exception:
        sys.stdout = DummyStream()

if sys.stderr is None:
    sys.stderr = DummyStream()
else:
    try:
        sys.stderr.write("")
        sys.stderr.flush()
    except Exception:
        sys.stderr = DummyStream()

import logging
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QLockFile

from utils.helpers import get_app_dir, create_desktop_shortcut, set_auto_start

# Setup Logging first so other modules can use it
log_path = os.path.join(get_app_dir(), "vibe_pet.log")
handlers = [logging.FileHandler(log_path, encoding="utf-8")]
if sys.stdout is not None and not isinstance(sys.stdout, DummyStream):
    handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(module)s] %(levelname)s: %(message)s",
    handlers=handlers
)
logger = logging.getLogger("vibe_pet")

# Global Exception Hook to capture and log any unhandled exceptions
def global_exception_hook(exctype, value, traceback):
    logger.critical("Unhandled exception captured:", exc_info=(exctype, value, traceback))
    # Suppress default window crash reports for clean user experience

sys.excepthook = global_exception_hook

# Core & UI Imports
from core.config import ConfigManager
from core.database import DatabaseManager
from core.reminder import ReminderManager
from core.monitor import MonitorThread
from ui.pet_window import PetWindow

def main():
    logger.info("Initializing VibePet desktop application...")
    
    # 1. Single Instance Lock using QLockFile
    lock_path = os.path.join(get_app_dir(), "vibe_pet.lock")
    lock_file = QLockFile(lock_path)
    if not lock_file.tryLock(100):
        # Notify the user that it's already running
        # We need a temporary QApplication to show a warning box
        temp_app = QApplication(sys.argv)
        QMessageBox.warning(
            None,
            "重复启动",
            "VibePet 已经在后台运行中！\n请检查右下角系统托盘区域。"
        )
        logger.warning("Another instance is already running. Exiting.")
        sys.exit(1)
        
    # 2. Main Application Initialization
    app = QApplication(sys.argv)
    # Ensure application does not quit when stats/settings dialog is closed
    app.setQuitOnLastWindowClosed(False)
    
    # 3. Component Instantiation
    try:
        config_mgr = ConfigManager()
        db_mgr = DatabaseManager()
        reminder_mgr = ReminderManager(config_mgr)
        
        # 首次运行：创建桌面快捷方式
        if config_mgr.get("first_run", True):
            try:
                exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
                icon_path = os.path.join(get_app_dir(), "assets", "icon.png")
                if create_desktop_shortcut(exe_path, "VibePet", icon_path):
                    config_mgr.set("first_run", False)
                    logger.info("Desktop shortcut created successfully.")
                else:
                    logger.warning("Failed to create desktop shortcut.")
            except Exception as e:
                logger.error(f"Error creating desktop shortcut: {e}")
        
        # 同步开机自启动注册表状态（防止用户手动修改注册表后不一致）
        auto_start_config = config_mgr.get("auto_start", False)
        if auto_start_config:
            set_auto_start(True)
        
        # Main desktop pet window
        pet_win = PetWindow(db_mgr, config_mgr, reminder_mgr)
        
        # ===== 关键修复：根据配置强制显示窗口 =====
        if config_mgr.get("show_pet_on_startup", True):
            pet_win.show()
            pet_win.raise_()
            pet_win.activateWindow()
            logger.info(f"[启动] 宠物窗口已显示，可见性: {pet_win.isVisible()}, 位置: {pet_win.pos()}")
            
            # 修复5：启动后延迟1秒再执行一次move/raise_，确保窗口真正显示在最上层
            from PyQt6.QtCore import QTimer
            def _ensure_visible():
                pet_win.raise_()
                pet_win.activateWindow()
                logger.info(f"[启动延迟确认] 窗口可见性: {pet_win.isVisible()}, 位置: {pet_win.pos()}, 尺寸: {pet_win.size()}")
            QTimer.singleShot(1000, _ensure_visible)
        else:
            pet_win.hide()
            logger.info("[启动] 宠物窗口初始化为隐藏状态")
        
        # 启动诊断日志
        from PyQt6.QtCore import QT_VERSION_STR
        screen = app.primaryScreen()
        logger.info("=== VibePet 启动诊断 ===")
        logger.info(f"Qt版本: {QT_VERSION_STR}")
        logger.info(f"屏幕分辨率: {screen.size()}")
        logger.info(f"可用屏幕区域: {screen.availableGeometry()}")
        logger.info(f"宠物窗口标志: {pet_win.windowFlags()}")
        logger.info(f"宠物窗口尺寸: {pet_win.size()}")
        logger.info(f"宠物窗口位置: {pet_win.pos()}")
        
        # 4. Background Monitor Thread
        monitor_thread = MonitorThread(db_mgr, config_mgr, reminder_mgr)
        
        # Connect monitor signals to pet window slots
        monitor_thread.status_updated.connect(pet_win.on_status_updated)
        monitor_thread.animation_changed.connect(pet_win.load_animation)
        monitor_thread.show_bubble.connect(pet_win.show_bubble_message)
        monitor_thread.show_warning_dialog.connect(pet_win.trigger_fatigue_warning)
        
        # Start background loop
        monitor_thread.start()
        logger.info("Background monitor thread launched.")
        
    except Exception as e:
        logger.critical(f"Critical failure during initialization: {e}", exc_info=True)
        lock_file.unlock()
        sys.exit(1)
        
    # 5. Cleanup upon Exit
    def shutdown_cleanup():
        logger.info("Shutting down VibePet application...")
        # Stop background thread and flush data
        monitor_thread.stop()
        monitor_thread.wait()
        # Release the lock file
        lock_file.unlock()
        logger.info("VibePet shutdown complete.")
        
    app.aboutToQuit.connect(shutdown_cleanup)
    
    # Run event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
