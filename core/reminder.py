import datetime
import time
import random
import logging
from win10toast import ToastNotifier

logger = logging.getLogger("vibe_pet")


class ReminderManager:
    def __init__(self, config_manager):
        self.config = config_manager
        self.toaster = ToastNotifier()

        # Keep track of when reminders last fired to enforce the 30-minute cooldown
        # Cooldown = 1800 seconds
        self.cooldown_seconds = 1800
        self.last_triggered = {
            "game_sedentary": 0,
            "sedentary": 0,
            "late_night": 0,
            "positive": 0,
            "fatigue": 0
        }

        # State tracking for positive incentive (game -> work transition)
        self.last_category = "idle"
        self.work_start_time = 0
        self.happy_until = 0  # Timestamp until which "happy" animation remains active

        # State tracking for late night continuous active time
        self.late_night_active_seconds = 0

        # --- 随机情绪状态机 ---
        # 随机情绪优先级低于规则触发的情绪，但高于基础idle/work
        self.random_emotion_active = False
        self.random_emotion_state = "idle"   # "sleep", "happy", "tired"
        self.random_emotion_until = 0        # 随机情绪持续到该时间戳
        self.last_emotion_check = 0          # 上次检查随机情绪的时间
        self.emotion_check_interval = 10     # 每10秒检查一次概率

        # Callback for showing a bubble on the pet window: fn(text)
        self.bubble_callback = None
        # Callback for showing an angry warning dialog: fn()
        self.warning_dialog_cb = None

    def set_callbacks(self, bubble_cb, warning_dialog_cb):
        self.bubble_callback = bubble_cb
        self.warning_dialog_cb = warning_dialog_cb

    def _evaluate_condition(self, condition, context):
        try:
            # 安全地进行 eval：屏蔽 __builtins__
            return eval(condition, {"__builtins__": None}, context)
        except Exception as e:
            logger.error(f"Error evaluating rule condition '{condition}': {e}")
            return False

    def show_toast(self, title, message):
        """ Show Windows Toast notification in a background thread """
        try:
            # win10toast's show_toast with threaded=True runs asynchronously
            self.toaster.show_toast(
                title,
                message,
                icon_path=None,
                duration=5,
                threaded=True
            )
            logger.info(f"Toast sent: {title} - {message}")
        except Exception as e:
            logger.error(f"Failed to show toast notification: {e}")

    def trigger_reminder(self, rule_key, bubble_text, toast_text, is_toast=True):
        """ Helper to trigger a reminder if it is enabled and outside cooldown """
        now = time.time()
        # Check if enabled in config
        if not self.config.get_reminder_switch(rule_key):
            return False

        # Check cooldown
        if now - self.last_triggered[rule_key] < self.cooldown_seconds:
            return False

        self.last_triggered[rule_key] = now

        # Trigger bubble
        if self.bubble_callback and bubble_text:
            self.bubble_callback(bubble_text)

        # Trigger toast
        if is_toast and toast_text:
            self.show_toast("VibePet 健康助手", toast_text)

        return True

    def _get_time_period(self):
        """ 根据当前时间返回时间段：day/evening/night """
        hour = datetime.datetime.now().hour
        if 6 <= hour < 18:
            return "day"
        elif 18 <= hour < 22:
            return "evening"
        else:
            return "night"

    def _check_random_emotions(self, current_category, is_idle):
        """
        检查并更新随机情绪状态。
        按时间段概率触发：夜晚更容易疲惫和睡觉，白天更容易开心。
        每10秒检查一次概率。
        """
        now = time.time()

        # 检查是否启用了随机情绪
        if not self.config.get("random_emotions", True):
            return

        # 获取当前时间段的概率配置
        time_period = self._get_time_period()
        probs = self.config.get_emotion_probabilities(time_period)

        # 计算各情绪的总概率
        tired_prob = probs.get("tired", 5)
        sleep_prob = probs.get("sleep", 5)
        happy_prob = probs.get("happy", 10)

        # 判断当前应触发的情绪（100%概率时持续保持）
        target_emotion = None

        # 检查 tired（疲惫）- 所有状态都可能触发
        if tired_prob >= 100:
            target_emotion = "tired"
        # 检查 sleep（睡眠）- 主要在 idle 状态触发
        elif (is_idle or current_category == "idle") and sleep_prob >= 100:
            target_emotion = "sleep"
        # 检查 happy（开心）- 主要在活跃状态触发
        elif not is_idle and current_category in ("work", "other", "leisure") and happy_prob >= 100:
            target_emotion = "happy"

        # 如果某个情绪概率为100%，持续保持该状态（不设置过期时间）
        if target_emotion:
            if not self.random_emotion_active or self.random_emotion_state != target_emotion:
                self.random_emotion_active = True
                self.random_emotion_state = target_emotion
                self.random_emotion_until = float('inf')  # 永不过期
                logger.info(f"Random {target_emotion} set to permanent (prob=100%)")
                if self.bubble_callback:
                    texts = {"tired": "有点累了呢... 😔", "sleep": "zzz... 小憩一下~", "happy": "今天状态不错呢~ 😊"}
                    self.bubble_callback(texts.get(target_emotion, ""))
            return

        # 如果随机情绪已过期，重置状态
        if self.random_emotion_active and now >= self.random_emotion_until:
            self.random_emotion_active = False
            self.random_emotion_state = "idle"
            logger.info("Random emotion expired, returning to normal state.")

        # 如果当前已有随机情绪活跃，不再触发新的
        if self.random_emotion_active:
            return

        # 每10秒检查一次概率
        if now - self.last_emotion_check < self.emotion_check_interval:
            return
        self.last_emotion_check = now

        # 使用 0-99 的随机整数，确保 100% 概率一定触发
        roll = random.randint(0, 99)

        # 检查 tired（疲惫）- 所有状态都可能触发
        if roll < tired_prob:
            duration = random.randint(15, 45)
            self.random_emotion_active = True
            self.random_emotion_state = "tired"
            self.random_emotion_until = now + duration
            logger.info(f"Random tired triggered for {duration}s (period={time_period}, prob={tired_prob}%)")
            if self.bubble_callback:
                self.bubble_callback("有点累了呢... 😔")
            return

        # 检查 sleep（睡眠）- 主要在 idle 状态触发
        if is_idle or current_category == "idle":
            # 累加概率区间：tired 已检查过，现在检查 tired+sleep 区间
            if roll < tired_prob + sleep_prob:
                duration = random.randint(20, 60)
                self.random_emotion_active = True
                self.random_emotion_state = "sleep"
                self.random_emotion_until = now + duration
                logger.info(f"Random sleep triggered for {duration}s (period={time_period}, prob={sleep_prob}%)")
                if self.bubble_callback:
                    self.bubble_callback("zzz... 小憩一下~")
                return

        # 检查 happy（开心）- 主要在活跃状态触发
        if not is_idle and current_category in ("work", "other", "leisure"):
            # 累加概率区间：tired 已检查过，现在检查 tired+happy 区间
            if roll < tired_prob + happy_prob:
                duration = random.randint(15, 40)
                self.random_emotion_active = True
                self.random_emotion_state = "happy"
                self.random_emotion_until = now + duration
                logger.info(f"Random happy triggered for {duration}s (period={time_period}, prob={happy_prob}%)")
                if self.bubble_callback:
                    self.bubble_callback("今天状态不错呢~ 😊")
                return

    def check_rules(self, current_category, is_idle, today_total, today_game, today_work, active_time_since_idle):
        """
        Check health/work rules and determine the target pet animation state.
        Should be called every 2 seconds by the monitor.

        Returns:
            str: Target animation state ('angry', 'sleep', 'tired', 'happy', 'work', 'idle')
        """
        now = time.time()
        rules = self.config.get("rules", [])

        # 1. Evaluate late night activity (23:00 - 06:30)
        current_time = datetime.datetime.now().time()
        is_late_night_window = (current_time >= datetime.time(23, 0)) or (current_time <= datetime.time(6, 30))

        if is_late_night_window and not is_idle:
            self.late_night_active_seconds += 2
        elif is_idle or not is_late_night_window:
            if is_idle:
                self.late_night_active_seconds = 0

        # 2. Evaluate positive incentive state machine (game -> work transition)
        positive_rule = next((r for r in rules if r["id"] == "positive"), None)
        if positive_rule and self.config.get_reminder_switch("positive"):
            if current_category == "work" and not is_idle:
                if self.last_category == "game" and self.work_start_time == 0:
                    self.work_start_time = now
                    logger.info("Category switched from game to work. Positive timer started.")
                elif self.work_start_time > 0:
                    work_duration = now - self.work_start_time
                    threshold_val = self.config.get_threshold(positive_rule["threshold_key"])
                    threshold_seconds = threshold_val * 60
                    if work_duration >= threshold_seconds:
                        bubble_text = positive_rule.get("bubble_text", "加油，高效产出！").format(threshold=int(threshold_val))
                        toast_text = positive_rule.get("toast_text", "看到你开始专心工作了，加油！").format(threshold=int(threshold_val))
                        triggered = self.trigger_reminder(
                            "positive",
                            bubble_text,
                            toast_text,
                            is_toast=positive_rule.get("is_toast", False)
                        )
                        if triggered:
                            self.happy_until = now + 60
                        self.work_start_time = 0
            else:
                self.work_start_time = 0

        if current_category != "idle":
            self.last_category = current_category

        # 3. Check random emotions
        self._check_random_emotions(current_category, is_idle)

        # 4. Check other rules via dynamic rules engine
        active_rules = []
        for rule in rules:
            if rule["id"] == "positive":
                continue
                
            rule_id = rule["id"]
            if not self.config.get_reminder_switch(rule_id):
                continue
                
            threshold_val = self.config.get_threshold(rule["threshold_key"])
            
            # Setup evaluation context (values in minutes for user convenience)
            context = {
                "today_total": today_total / 60.0,
                "today_game": today_game / 60.0,
                "today_work": today_work / 60.0,
                "active_time_since_idle": active_time_since_idle / 60.0,
                "late_night_active": self.late_night_active_seconds / 60.0,
                "is_late_night": is_late_night_window,
                "current_category": current_category,
                "is_idle": is_idle,
                "threshold": threshold_val
            }
            
            # Evaluate condition
            if self._evaluate_condition(rule["condition"], context):
                active_rules.append(rule)
                
                # Format texts
                bubble_text = rule.get("bubble_text", "").format(threshold=int(threshold_val))
                toast_text = rule.get("toast_text", "").format(threshold=int(threshold_val))
                
                # Enforce notification trigger
                triggered = self.trigger_reminder(rule_id, bubble_text, toast_text, rule.get("is_toast", True))
                if triggered and rule_id == "fatigue" and self.warning_dialog_cb:
                    self.warning_dialog_cb()

        # Sort rules that are currently met/active by priority descending
        active_rules.sort(key=lambda r: r.get("priority", 0), reverse=True)
        
        # Priority mapping: active rules -> happy -> work -> random_emotions -> idle
        if active_rules:
            return active_rules[0]["animation"]
        elif now < self.happy_until:
            return "happy"
        elif current_category == "work" and not is_idle:
            return "work"
        else:
            if self.random_emotion_active:
                return self.random_emotion_state
            return "idle"
