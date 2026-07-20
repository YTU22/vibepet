import time
import datetime
import logging
from PyQt6.QtCore import QThread, pyqtSignal

import win32gui
import win32process
import win32api
import psutil

from utils.helpers import normalize_process_name, is_screenshot_tool

logger = logging.getLogger("vibe_pet")

class MonitorThread(QThread):
    # Signals for communicating with PyQt UI
    # 末位 bool 为截图工具是否在前台（权威状态，供 UI 轮询兜底对齐）
    status_updated = pyqtSignal(str, str, bool, int, int, bool)
    animation_changed = pyqtSignal(str)
    show_bubble = pyqtSignal(str)
    show_warning_dialog = pyqtSignal()
    config_reloaded = pyqtSignal()
    # 截图工具（Snipaste/微信截图等）进入或退出前台时触发，用于即时隐藏/恢复桌宠
    screenshot_mode_changed = pyqtSignal(bool)

    def __init__(self, db_manager, config_manager, reminder_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.config = config_manager
        self.reminder = reminder_manager
        
        self._running = True
        self._hook = None
        
        # Memory cache for active usage accumulation
        # Key: (process_name, category), Value: duration in seconds
        self.memory_cache = {}
        
        # Track active time since last 5-min idle period
        self.active_time_since_idle = 0
        
        # Today's daily statistics (cached in memory, synced after db flush)
        self.today_total = 0
        self.today_game = 0
        self.today_work = 0
        
        # Current status
        self.current_app = "unknown"
        self.current_category = "idle"
        self.is_idle = False
        self.current_animation = "idle"
        self._screenshot_active = False
        
        # Set up callbacks in the reminder manager to emit Qt signals
        self.reminder.set_callbacks(
            bubble_cb=self._on_reminder_bubble,
            warning_dialog_cb=self._on_reminder_warning
        )
        
        # Load initial values from DB
        self.sync_today_totals_from_db()

        # 初始化前台窗口检测与事件钩子
        self._active_process_name = self._lookup_foreground_process()
        self.current_app = normalize_process_name(self._active_process_name)
        self.current_category = self.config.get_category_for_app(self.current_app)
        
        # 注册事件钩子
        self._register_event_hook()
        # 初始化截图工具状态（桌宠启动时截图工具可能已在前台，此处仅置位不发信号）
        try:
            hwnd = win32gui.GetForegroundWindow()
            class_name = win32gui.GetClassName(hwnd) if hwnd else ""
            self._screenshot_active = is_screenshot_tool(
                process_name=self._active_process_name, window_class=class_name)
        except Exception:
            pass

    def __del__(self):
        self._unregister_event_hook()

    def _register_event_hook(self):
        """ 注册全局前台窗口切换事件钩子 """
        import ctypes
        import ctypes.wintypes
        
        EVENT_SYSTEM_FOREGROUND = 0x0003
        WINEVENT_OUTOFCONTEXT = 0x0000
        
        user32 = ctypes.windll.user32
        
        # 定义回调函数类型
        self._cb_type = ctypes.WINFUNCTYPE(
            None,
            ctypes.wintypes.HANDLE,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.HWND,
            ctypes.wintypes.LONG,
            ctypes.wintypes.LONG,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD
        )
        
        # 实例化回调函数并保持引用防止垃圾回收
        self._cb_func = self._cb_type(self._win_event_proc)
        
        self._hook = user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            0,
            self._cb_func,
            0,
            0,
            WINEVENT_OUTOFCONTEXT
        )
        if self._hook:
            logger.info("SetWinEventHook registered successfully for EVENT_SYSTEM_FOREGROUND.")
        else:
            logger.error("Failed to register SetWinEventHook.")

    def _unregister_event_hook(self):
        """ 注销全局前台窗口切换事件钩子 """
        if hasattr(self, '_hook') and self._hook:
            import ctypes
            user32 = ctypes.windll.user32
            user32.UnhookWinEvent(self._hook)
            self._hook = None
            logger.info("SetWinEventHook unregistered successfully.")

    def _win_event_proc(self, hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime):
        """ Windows 前台窗口变更回调 """
        EVENT_SYSTEM_FOREGROUND = 0x0003
        if event == EVENT_SYSTEM_FOREGROUND:
            name = self._lookup_foreground_process_by_hwnd(hwnd)
            self._active_process_name = name
            self._update_screenshot_state(hwnd, name)

    def _update_screenshot_state(self, hwnd, process_name):
        """ 根据前台窗口的类名与进程名检测截图工具，状态变化时即时发出信号 """
        try:
            class_name = win32gui.GetClassName(hwnd) if hwnd else ""
        except Exception:
            class_name = ""
        active = is_screenshot_tool(process_name=process_name, window_class=class_name)
        if active != self._screenshot_active:
            self._screenshot_active = active
            self.screenshot_mode_changed.emit(active)
            logger.info(f"截图模式{'开启' if active else '关闭'}（进程={process_name}, 类名={class_name}）")

    def _lookup_foreground_process_by_hwnd(self, hwnd):
        """ 根据窗口句柄查找进程名 """
        if not hwnd:
            return "unknown"
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == 0:
                return "unknown"
            try:
                proc = psutil.Process(pid)
                return proc.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return "unknown"
        except Exception:
            return "unknown"

    def _lookup_foreground_process(self):
        """ 查找当前的前台窗口进程名 """
        try:
            hwnd = win32gui.GetForegroundWindow()
            return self._lookup_foreground_process_by_hwnd(hwnd)
        except Exception:
            return "unknown"

    def sync_today_totals_from_db(self):
        """ Reload today's usage statistics from database """
        try:
            self.today_total = self.db.get_today_total()
            self.today_game = self.db.get_today_by_category("game")
            self.today_work = self.db.get_today_by_category("work")
            logger.info(f"Synced today's totals from DB: total={self.today_total}s, game={self.today_game}s, work={self.today_work}s")
        except Exception as e:
            logger.error(f"Failed to sync today's totals: {e}")

    def stop(self):
        self._running = False
        # 注销全局事件钩子
        self._unregister_event_hook()
        # Save remaining cache before exit
        self.flush_cache_to_db()

    def _on_reminder_bubble(self, text):
        """ Callback from reminder engine to emit signal """
        self.show_bubble.emit(text)

    def _on_reminder_warning(self):
        """ Callback from reminder engine to emit signal """
        self.show_warning_dialog.emit()

    def get_idle_time(self):
        """ Get system idle time in seconds using GetLastInputInfo """
        try:
            last_input = win32api.GetLastInputInfo()
            current_tick = win32api.GetTickCount()
            # Tick counts wrap around every 49.7 days, but for idle calculation
            # a simple subtraction works fine as long as there is no overflow boundary event.
            idle_ms = current_tick - last_input
            return idle_ms / 1000.0
        except Exception as e:
            logger.error(f"Error getting system idle time: {e}")
            return 0.0

    def get_foreground_process_name(self):
        """ Directly retrieve the cached foreground process name """
        if not hasattr(self, '_active_process_name'):
            self._active_process_name = self._lookup_foreground_process()
        return self._active_process_name

    def flush_cache_to_db(self):
        """ Flush accumulated memory usage to SQLite """
        if not self.memory_cache:
            return
            
        today = datetime.date.today().isoformat()
        batch = []
        for (proc_name, category), seconds in self.memory_cache.items():
            batch.append((today, proc_name, category, seconds))
            
        success = self.db.save_batch(batch)
        if success:
            self.memory_cache.clear()
            self.sync_today_totals_from_db()
        else:
            logger.warning("Failed to flush memory cache to DB, will retry next minute.")

    def run(self):
        logger.info("Monitor background thread started.")
        
        poll_interval = max(1, self.config.get("sys_monitor_interval", 5))  # 读取配置的采样间隔（秒）
        flush_interval = 60 # Flush every 60 seconds
        
        last_flush_time = time.time()
        
        prev_idle_state = None  # 用于检测 idle 状态变化
        while self._running:
            # 检查是否有任何监控项被启用；若全部关闭，则直接休眠并跳过本轮采集
            enabled_items = [name for name, flag in self.config.get("sys_monitor_items", {}).items() if flag]
            if not enabled_items:
                logger.info("所有系统监控项已关闭，暂时休眠 %ds" % poll_interval)
                self.msleep(poll_interval * 1000)
                continue
            # Check for config modifications on disk and reload if necessary
            if self.config.check_and_reload():
                self.config_reloaded.emit()
                
            start_time = time.time()

            # 0. 前台窗口自愈式复核：事件钩子之外每轮兜底一次（含窗口类名检测），
            #    即使钩子事件丢失也能在一个轮询周期内恢复正确状态
            try:
                fg_hwnd = win32gui.GetForegroundWindow()
                fg_name = self._lookup_foreground_process_by_hwnd(fg_hwnd)
                if fg_name != "unknown":
                    self._active_process_name = fg_name
                self._update_screenshot_state(fg_hwnd, self._active_process_name)
            except Exception:
                pass

            # 1. Check if user is idle (no input for >= 5 minutes)
            idle_seconds = self.get_idle_time()
            is_currently_idle = idle_seconds >= 300.0
            # 检测 idle 状态变化并动态调节轮询间隔
            if prev_idle_state is None:
                # 第一次检测，仅记录状态
                prev_idle_state = is_currently_idle
            elif prev_idle_state != is_currently_idle:
                if is_currently_idle:
                    logger.info(f"系统进入空闲，轮询间隔加倍至 {poll_interval * 2}s")
                else:
                    logger.info(f"系统恢复活跃，轮询间隔恢复为 {poll_interval}s")
                prev_idle_state = is_currently_idle
            # 根据当前 idle 状态决定本轮使用的实际轮询间隔
            effective_poll = poll_interval * 2 if is_currently_idle else poll_interval
            self.is_idle = is_currently_idle
            
            if is_currently_idle:
                # Reset continuous active time since last 5-min idle period
                self.active_time_since_idle = 0
                self.current_app = "idle (no input)"
                self.current_category = "idle"
            else:
                # User is active, increment active time
                self.active_time_since_idle += effective_poll
                
                # 2. Get foreground process name and classify
                raw_name = self.get_foreground_process_name()
                normalized_name = normalize_process_name(raw_name)
                self.current_app = normalized_name
                
                # Determine category
                self.current_category = self.config.get_category_for_app(normalized_name)
                
                    
                # 3. Accumulate time in memory cache
                cache_key = (normalized_name, self.current_category)
                self.memory_cache[cache_key] = self.memory_cache.get(cache_key, 0) + effective_poll
                
                # Add to temporary today counts (for real-time feedback before flush)
                self.today_total += effective_poll
                if self.current_category == "game":
                    self.today_game += effective_poll
                elif self.current_category == "work":
                    self.today_work += effective_poll

            # 4. Check reminder rules and update animation state
            target_animation = self.reminder.check_rules(
                current_category=self.current_category,
                is_idle=self.is_idle,
                today_total=self.today_total,
                today_game=self.today_game,
                today_work=self.today_work,
                active_time_since_idle=self.active_time_since_idle
            )
            
            if target_animation != self.current_animation:
                self.current_animation = target_animation
                self.animation_changed.emit(target_animation)
                logger.info(f"Pet animation changed to: {target_animation}")

            # 5. Emit status update signal for UI (e.g. tray icon tooltips, stats dialog)
            self.status_updated.emit(
                self.current_app,
                self.current_category,
                self.is_idle,
                self.today_total,
                self.today_game,
                self._screenshot_active
            )

            # 6. Periodic flush to DB (every 60s)
            now = time.time()
            if now - last_flush_time >= flush_interval:
                self.flush_cache_to_db()
                last_flush_time = now

            # Sleep to match poll interval, accounting for execution time
            elapsed = time.time() - start_time
            sleep_time = max(0.1, effective_poll - elapsed)
            self.msleep(int(sleep_time * 1000))
            
        logger.info("Monitor background thread stopping. Final flush...")
        self.flush_cache_to_db()
