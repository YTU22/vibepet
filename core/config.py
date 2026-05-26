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
    "show_app_bubble": True,
    "show_pet_on_startup": True,      # 启动时是否显示宠物窗口
    # 宠物窗口外观与行为设置
    "pet_size": 200,                  # 宠物窗口大小（像素），默认200
    "window_locked": False,           # 窗口位置是否锁定（禁止拖拽）
    "mouse_passthrough": False,       # 鼠标穿透模式（点击穿透到下层窗口）
    "bubble_opacity": 1.0,            # 气泡背景不透明度 (0.3-1.0)
    "random_emotions": True,          # 是否启用随机情绪
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
    }
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
        self.load_config()

    def load_config(self):
        """ Load config.json, or create it with default values if not exists """
        if not os.path.exists(self.config_path):
            logger.info("config.json not found, creating default configuration.")
            self.config = DEFAULT_CONFIG.copy()
            self.save_config()
            return
            
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
            # Ensure all default keys exist (in case the config format was updated)
            self._fill_missing_keys(self.config, DEFAULT_CONFIG)
        except Exception as e:
            logger.error(f"Failed to read config.json: {e}. Resetting to defaults.")
            self.config = DEFAULT_CONFIG.copy()
            self.save_config()

    def _fill_missing_keys(self, target, source):
        """ Recursively fill missing keys in target dict from source dict """
        for k, v in source.items():
            if k not in target:
                target[k] = v
            elif isinstance(v, dict) and isinstance(target[k], dict):
                self._fill_missing_keys(target[k], v)

    def save_config(self):
        """ Save current config to config.json """
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
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
