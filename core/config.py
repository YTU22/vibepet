import os
import json
import logging

logger = logging.getLogger("vibe_pet")

# Default Config Structure
DEFAULT_CONFIG = {
    "reminder_switches": {
        "game_sedentary": True,     # 游戏沉迷提醒
        "sedentary": True,          # 久坐提醒
        "late_night": True,         # 深夜提醒
        "positive": True,           # 正向工作激励
        "fatigue": True             # 每日总时长疲劳提醒
    },
    "thresholds": {
        "game_limit_minutes": 120,    # 游戏限制时长（分），默认2小时
        "sedentary_minutes": 60,      # 久坐时长（分），默认1小时
        "late_night_minutes": 30,     # 深夜持续使用时长（分），默认30分钟
        "positive_minutes": 5,        # 切换到工作持续时长（分），默认5分钟
        "fatigue_minutes": 480        # 每日总运行警示时长（分），默认8小时
    },
    "work_apps": ["code", "pycharm", "word", "excel", "obsidian", "notion", "vscode", "intellij idea", "clion"],
    "game_apps": ["steam", "yihuan", "genshinimpact", "league of legends", "valorant", "lol", "genshin impact"],
    "leisure_apps": ["chrome", "msedge", "firefox", "netflix", "bilibili", "youtube", "qq", "wechat", "dingtalk"],  # 休闲应用（追剧、社交等）
    "custom_categories": {
        "work": "工作",
        "game": "游戏",
        "leisure": "休闲"
    },
    "show_app_bubble": True,
    "show_pet_on_startup": True,      # 启动时是否显示宠物窗口
    "auto_start": False,              # 是否开机自启动
    "first_run": True,                # 是否首次运行（用于创建桌面快捷方式）
    "theme_mode": "light",            # 默认主题模式：light/dark
    "word_count_enabled": False,      # 是否启用全局划词统计
    "word_count_mode": "bubble",      # 划词统计显示模式：bubble/card
    "update_mirror": "直连 GitHub",
    # 宠物窗口外观与行为设置
    "pet_size": 200,                  # 宠物窗口大小（像素），默认200
    "window_x": None,                 # 窗口上次X坐标
    "window_y": None,                 # 窗口上次Y坐标
    "window_locked": False,           # 窗口位置是否锁定（禁止拖拽）
    "mouse_passthrough": False,       # 鼠标穿透模式（点击穿透到下层窗口）
    "screen_snapping": True,          # 边缘隐藏（躲猫猫）模式
    "todo_visible": False,            # 便签待办窗口可见状态
    "todo_x": None,                   # 便签待办窗口上次X坐标
    "todo_y": None,                   # 便签待办窗口上次Y坐标
    "bubble_opacity": 1.0,            # 气泡背景不透明度 (0.3-1.0)
    "app_bubble_font_size": 9,        # 监控气泡字号，默认9
    "random_emotions": True,          # 是否启用随机情绪
    # 系统监控配置
    "sys_monitor_enabled": True,      # 是否启用系统监控
    "sys_monitor_items": {            # 显示哪些监控项
        "cpu": True,
        "memory": True,
        "disk": False,
        "network": False,
        "gpu": False
    },
    "sys_monitor_interval": 1,        # 监控刷新间隔（秒）
    # 随机情绪概率配置（百分比 0-100）
    "emotion_probabilities": {
        # 白天时段 (06:00-18:00)
        "day": {
            "sleep": 2,      # 白天睡眠概率较低
            "happy": 15,     # 白天开心概率较高
            "tired": 3       # 白天疲惫概率较低
        },
        # 傍晚时段 (18:00-22:00)
        "evening": {
            "sleep": 5,      # 傍晚睡眠概率稍增
            "happy": 10,     # 傍晚开心概率中等
            "tired": 8       # 傍晚疲惫概率增加
        },
        # 夜晚时段 (22:00-06:00)
        "night": {
            "sleep": 20,     # 夜晚睡眠概率高
            "happy": 5,      # 夜晚开心概率低
            "tired": 15      # 夜晚疲惫概率高
        }
    },
    "rules": [
        {
            "id": "fatigue",
            "name": "每日总时间疲劳提醒",
            "threshold_key": "fatigue_minutes",
            "condition": "today_total >= threshold",
            "bubble_text": "今日累计工作/使用时间过长，强制建议休息！",
            "toast_text": "您今天已经使用电脑超过 {threshold} 分钟，请立即休息！",
            "is_toast": True,
            "animation": "angry",
            "priority": 60,
            "cooldown": 1800
        },
        {
            "id": "late_night",
            "name": "深夜防熬夜提醒",
            "threshold_key": "late_night_minutes",
            "condition": "is_late_night and late_night_active >= threshold",
            "bubble_text": "很晚了，保持良好作息该睡觉啦~",
            "toast_text": "夜深了，连续使用电脑已超 {threshold} 分钟，请尽快休息睡觉！",
            "is_toast": True,
            "animation": "sleep",
            "priority": 50,
            "cooldown": 1800
        },
        {
            "id": "game_sedentary",
            "name": "游戏沉迷提醒",
            "threshold_key": "game_limit_minutes",
            "condition": "current_category == 'game' and today_game >= threshold",
            "bubble_text": "游戏玩太久啦，让眼睛休息一下~",
            "toast_text": "今日游戏时间已累计超过 {threshold} 分钟，请注意休息！",
            "is_toast": True,
            "animation": "tired",
            "priority": 40,
            "cooldown": 1800
        },
        {
            "id": "sedentary",
            "name": "久坐提醒",
            "threshold_key": "sedentary_minutes",
            "condition": "active_time_since_idle >= threshold",
            "bubble_text": "坐太久啦，站起来活动活动！",
            "toast_text": "您已连续使用电脑超过 {threshold} 分钟，请站起来活动一下身体！",
            "is_toast": True,
            "animation": "tired",
            "priority": 30,
            "cooldown": 1800
        },
        {
            "id": "positive",
            "name": "正向激励（工作）",
            "threshold_key": "positive_minutes",
            "condition": "current_category == 'work'",
            "bubble_text": "加油，高效产出！",
            "toast_text": "看到你开始专心工作了，加油！",
            "is_toast": False,
            "animation": "happy",
            "priority": 20,
            "cooldown": 1800
        }
    ]
}

from utils.helpers import get_app_dir


class ConfigManager:
    def __init__(self, config_path=None):
        if config_path is None:
            # Place config.json in the application directory
            base_dir = get_app_dir()
            self.config_path = os.path.join(base_dir, "config.json")
        else:
            self.config_path = config_path
            
        self.config = {}
        self._last_mtime = 0
        self.load_config()

    def load_config(self):
        """ Load config.json, or create it with default values if not exists """
        if not os.path.exists(self.config_path):
            logger.info("config.json not found, creating default configuration.")
            self.config = DEFAULT_CONFIG.copy()
            self.save_config()
            return
            
        try:
            mtime = os.path.getmtime(self.config_path)
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
            self._last_mtime = mtime
            # Ensure all default keys exist (in case the config format was updated)
            self._fill_missing_keys(self.config, DEFAULT_CONFIG)
        except Exception as e:
            logger.error(f"Failed to read config.json: {e}. Resetting to defaults.")
            self.config = DEFAULT_CONFIG.copy()
            self.save_config()

    def check_and_reload(self):
        """ 检查磁盘上的配置文件是否被修改，若被修改则在内存中重新加载它 """
        if os.path.exists(self.config_path):
            try:
                mtime = os.path.getmtime(self.config_path)
                if self._last_mtime != mtime:
                    logger.info("Config file modification detected on disk. Reloading...")
                    self.load_config()
                    return True
            except Exception as e:
                logger.error(f"Failed to check config file modification time: {e}")
        return False

    def _fill_missing_keys(self, target, source):
        """ Recursively fill missing keys in target dict from source dict """
        for k, v in source.items():
            if k not in target:
                target[k] = v
            elif isinstance(v, dict) and isinstance(target[k], dict):
                self._fill_missing_keys(target[k], v)
            elif isinstance(v, list) and k == "rules":
                if not isinstance(target[k], list) or len(target[k]) != len(v):
                    target[k] = v

    def save_config(self):
        """ Save current config to config.json """
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            self._last_mtime = os.path.getmtime(self.config_path)
            logger.info("Configuration saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save config.json: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()
        
    def get_reminder_switch(self, rule_name):
        return self.config.get("reminder_switches", {}).get(rule_name, True)
        
    def get_threshold(self, threshold_name):
        return self.config.get("thresholds", {}).get(threshold_name, 0)
        
    def is_work_app(self, app_name):
        return app_name in self.config.get("work_apps", [])
        
    def is_game_app(self, app_name):
        return app_name in self.config.get("game_apps", [])
    
    def is_leisure_app(self, app_name):
        return app_name in self.config.get("leisure_apps", [])
    
    def get_emotion_probabilities(self, time_period):
        """ 获取指定时间段的随机情绪概率配置 """
        probs = self.config.get("emotion_probabilities", {})
        return probs.get(time_period, DEFAULT_CONFIG["emotion_probabilities"][time_period])
    
    def get_bubble_opacity(self):
        """ 获取气泡不透明度 """
        return self.config.get("bubble_opacity", 1.0)

    def get_categories(self):
        """ 获取所有分类（包含默认与自定义分类），返回 {id: display_name} """
        return self.config.get("custom_categories", {
            "work": "工作",
            "game": "游戏",
            "leisure": "休闲"
        })

    def get_category_for_app(self, app_name):
        """ 获取进程对应的分类 ID """
        categories = self.get_categories()
        for cat_id in categories.keys():
            if app_name in self.config.get(f"{cat_id}_apps", []):
                return cat_id
        return "other"

