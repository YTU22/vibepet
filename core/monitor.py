import time
import datetime
import logging
from PyQt6.QtCore import QThread, pyqtSignal

import win32gui
import win32process
import win32api
import psutil

from utils.helpers import normalize_process_name

logger = logging.getLogger("vibe_pet")

class MonitorThread(QThread):
    # Signals for communicating with PyQt UI
    status_updated = pyqtSignal(str, str, bool, int, int)
    animation_changed = pyqtSignal(str)
    show_bubble = pyqtSignal(str)
    show_warning_dialog = pyqtSignal()
    config_reloaded = pyqtSignal()

    def __init__(self, db_manager, config_manager, reminder_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.config = config_manager
        self.reminder = reminder_manager
        
        self._running = True
        
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
        
        # Set up callbacks in the reminder manager to emit Qt signals
        self.reminder.set_callbacks(
            bubble_cb=self._on_reminder_bubble,
            warning_dialog_cb=self._on_reminder_warning
        )
        
        # Load initial values from DB
        self.sync_today_totals_from_db()

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
        """ Retrieve the process name of the active foreground window """
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return "unknown"
                
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == 0:
                return "unknown"
                
            # Use psutil to look up process name
            try:
                proc = psutil.Process(pid)
                return proc.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return "unknown"
        except Exception as e:
            # Avoid crashing, just return unknown
            return "unknown"

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
        
        poll_interval = 2 # Poll every 2 seconds
        flush_interval = 60 # Flush every 60 seconds
        
        last_flush_time = time.time()
        
        while self._running:
            # Check for config modifications on disk and reload if necessary
            if self.config.check_and_reload():
                self.config_reloaded.emit()
                
            start_time = time.time()
            
            # 1. Check if user is idle (no input for >= 5 minutes)
            idle_seconds = self.get_idle_time()
            is_currently_idle = idle_seconds >= 300.0
            self.is_idle = is_currently_idle
            
            if is_currently_idle:
                # Reset continuous active time since last 5-min idle period
                self.active_time_since_idle = 0
                self.current_app = "idle (no input)"
                self.current_category = "idle"
            else:
                # User is active, increment active time
                self.active_time_since_idle += poll_interval
                
                # 2. Get foreground process name and classify
                raw_name = self.get_foreground_process_name()
                normalized_name = normalize_process_name(raw_name)
                self.current_app = normalized_name
                
                # Determine category
                if self.config.is_work_app(normalized_name):
                    self.current_category = "work"
                elif self.config.is_game_app(normalized_name):
                    self.current_category = "game"
                elif self.config.is_leisure_app(normalized_name):
                    self.current_category = "leisure"
                else:
                    self.current_category = "other"
                    
                # 3. Accumulate time in memory cache
                cache_key = (normalized_name, self.current_category)
                self.memory_cache[cache_key] = self.memory_cache.get(cache_key, 0) + poll_interval
                
                # Add to temporary today counts (for real-time feedback before flush)
                self.today_total += poll_interval
                if self.current_category == "game":
                    self.today_game += poll_interval
                elif self.current_category == "work":
                    self.today_work += poll_interval

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
                self.today_game
            )

            # 6. Periodic flush to DB (every 60s)
            now = time.time()
            if now - last_flush_time >= flush_interval:
                self.flush_cache_to_db()
                last_flush_time = now

            # Sleep to match poll interval, accounting for execution time
            elapsed = time.time() - start_time
            sleep_time = max(0.1, poll_interval - elapsed)
            self.msleep(int(sleep_time * 1000))
            
        logger.info("Monitor background thread stopping. Final flush...")
        self.flush_cache_to_db()
