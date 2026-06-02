import os
import sqlite3
import datetime
import logging

logger = logging.getLogger("vibe_pet")

from utils.helpers import get_app_dir

class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            # Place usage.db in application directory
            base_dir = get_app_dir()
            self.db_path = os.path.join(base_dir, "usage.db")
        else:
            self.db_path = db_path
            
        self.init_db()
        self.auto_cleanup_data(30)

    def _get_conn(self):
        """ Get database connection with custom timeouts and parameters """
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        # Enable WAL mode for better concurrency if needed, but standard is fine
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """ Initialize tables if they don't exist """
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS usage (
                        date TEXT,
                        process_name TEXT,
                        category TEXT,
                        duration_seconds INTEGER,
                        PRIMARY KEY (date, process_name)
                    )
                """)
                # Create an index for faster queries on date
                conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_date ON usage(date)")
                
                # 新增待办事项表
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS todo (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        content TEXT NOT NULL,
                        completed INTEGER DEFAULT 0,
                        created_at TEXT NOT NULL,
                        archived INTEGER DEFAULT 0,
                        completed_at TEXT
                    )
                """)
                # 检查并新增 archived 与 completed_at 字段（针对旧表迁移）
                cursor = conn.execute("PRAGMA table_info(todo)")
                columns = [row[1] for row in cursor.fetchall()]
                if columns:
                    if "archived" not in columns:
                        conn.execute("ALTER TABLE todo ADD COLUMN archived INTEGER DEFAULT 0")
                        logger.info("Migrated todo table to include 'archived' column.")
                    if "completed_at" not in columns:
                        conn.execute("ALTER TABLE todo ADD COLUMN completed_at TEXT")
                        logger.info("Migrated todo table to include 'completed_at' column.")
            logger.info("Database initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")

    def save_batch(self, batch_data):
        """
        Save a batch of app usage.
        batch_data: list of dicts/tuples: (date, process_name, category, duration_seconds)
        Uses ON CONFLICT to increment duration_seconds if key exists.
        """
        if not batch_data:
            return True
            
        try:
            # Open transaction
            with self._get_conn() as conn:
                conn.executemany("""
                    INSERT INTO usage (date, process_name, category, duration_seconds)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(date, process_name) DO UPDATE SET
                        duration_seconds = duration_seconds + excluded.duration_seconds,
                        category = excluded.category
                """, batch_data)
            logger.info(f"Successfully saved batch of {len(batch_data)} records to database.")
            return True
        except Exception as e:
            logger.error(f"Failed to save batch to database: {e}")
            return False

    def get_today_total(self):
        """ Get total usage duration (in seconds) for today """
        today = datetime.date.today().isoformat()
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    "SELECT SUM(duration_seconds) FROM usage WHERE date = ?", (today,)
                )
                row = cursor.fetchone()
                return row[0] if row and row[0] is not None else 0
        except Exception as e:
            logger.error(f"Error getting today's total: {e}")
            return 0

    def get_today_by_category(self, category):
        """ Get total usage duration (in seconds) for a category today """
        today = datetime.date.today().isoformat()
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    "SELECT SUM(duration_seconds) FROM usage WHERE date = ? AND category = ?", 
                    (today, category)
                )
                row = cursor.fetchone()
                return row[0] if row and row[0] is not None else 0
        except Exception as e:
            logger.error(f"Error getting today's category total: {e}")
            return 0

    def get_today_top_apps(self, limit=10):
        """ Get top apps used today, sorted by duration_seconds descending """
        today = datetime.date.today().isoformat()
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    """
                    SELECT process_name, category, duration_seconds 
                    FROM usage 
                    WHERE date = ? 
                    ORDER BY duration_seconds DESC 
                    LIMIT ?
                    """, (today, limit)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting today's top apps: {e}")
            return []

    def get_weekly_data(self):
        """
        Get usage data for the last 7 days (including today).
        Returns a list of dicts containing date, category, and total duration.
        """
        today = datetime.date.today()
        seven_days_ago = (today - datetime.timedelta(days=6)).isoformat()
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    """
                    SELECT date, category, SUM(duration_seconds) as total_duration
                    FROM usage 
                    WHERE date >= ? 
                    GROUP BY date, category
                    ORDER BY date ASC
                    """, (seven_days_ago,)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting weekly data: {e}")
            return []
            
    def export_all_to_csv(self, file_path, category_mapping=None):
        """ Export all usage data from database to a CSV file """
        import csv
        
        def format_friendly_duration(seconds):
            # 格式化时长为友好显示：
            # 1小时内精确到秒，如「46 分钟 58 秒」，省略为0的单位
            # 1小时以上精确到分，如「1 小时 23 分钟」，省略秒，且省略为0的单位
            if seconds < 3600:
                minutes = seconds // 60
                secs = seconds % 60
                parts = []
                if minutes > 0:
                    parts.append(f"{minutes} 分钟")
                if secs > 0 or not parts:
                    parts.append(f"{secs} 秒")
                return " ".join(parts)
            else:
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                parts = []
                if hours > 0:
                    parts.append(f"{hours} 小时")
                if minutes > 0:
                    parts.append(f"{minutes} 分钟")
                return " ".join(parts)

        try:
            with self._get_conn() as conn:
                cursor = conn.execute("SELECT date, process_name, category, duration_seconds FROM usage ORDER BY date DESC, duration_seconds DESC")
                with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    # 中文化表头：日期, 进程名称, 分类, 使用时长(秒), 使用时长(友好格式)
                    writer.writerow(["日期", "进程名称", "分类", "使用时长(秒)", "使用时长(友好格式)"])
                    
                    for row in cursor.fetchall():
                        seconds = row["duration_seconds"]
                        cat_id = row["category"]
                        # 分类列显示中文：支持自定义分类名称
                        if category_mapping and cat_id in category_mapping:
                            category_cn = category_mapping[cat_id]
                        else:
                            category_cn = {"work": "工作", "game": "游戏", "leisure": "休闲"}.get(cat_id, "其他")
                        formatted = format_friendly_duration(seconds)
                        writer.writerow([
                            row["date"],
                            row["process_name"],
                            category_cn,
                            seconds,
                            formatted
                        ])
            logger.info(f"Database exported successfully to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting data to CSV: {e}")
            return False

    def auto_cleanup_data(self, retention_days=30):
        """
        将 retention_days 天前的历史详细进程数据进行降维聚合：
        每个日期和分类的所有进程明细合并为一条记录，进程名为 '<aggregated>'。
        这可以大幅缩减数据库体积，同时保留历史分类统计趋势。
        """
        try:
            today = datetime.date.today()
            cutoff_date = (today - datetime.timedelta(days=retention_days)).isoformat()
            
            with self._get_conn() as conn:
                # 1. 查找 cutoff_date 之前，且含有非聚合进程数据的日期
                cursor = conn.execute("""
                    SELECT DISTINCT date 
                    FROM usage 
                    WHERE date < ? AND process_name NOT LIKE '<aggregated_%>'
                """, (cutoff_date,))
                dates_to_aggregate = [row[0] for row in cursor.fetchall()]
                
                if not dates_to_aggregate:
                    logger.info("No old detailed records need to be aggregated.")
                    return
                
                logger.info(f"Database cleanup: Found {len(dates_to_aggregate)} days to aggregate.")
                
                for d in dates_to_aggregate:
                    # 2. 计算该日期按 category 汇总的总时长
                    cursor = conn.execute("""
                        SELECT category, SUM(duration_seconds) as total 
                        FROM usage 
                        WHERE date = ? 
                        GROUP BY category
                    """, (d,))
                    summary = cursor.fetchall()
                    
                    # 3. 删除该日期的所有旧记录
                    conn.execute("DELETE FROM usage WHERE date = ?", (d,))
                    
                    # 4. 插入聚合后的记录
                    for row in summary:
                        conn.execute("""
                            INSERT INTO usage (date, process_name, category, duration_seconds)
                            VALUES (?, ?, ?, ?)
                        """, (d, f"<aggregated_{row['category']}>", row["category"], row["total"]))
                        
            # 5. 执行 VACUUM 整理数据库文件以释放空间（不能在 transaction 内执行，故建立新连接）
            try:
                conn_vac = self._get_conn()
                conn_vac.isolation_level = None
                conn_vac.execute("VACUUM")
                conn_vac.close()
                logger.info("Database auto-cleanup and VACUUM compression completed.")
            except Exception as ev:
                logger.warning(f"Failed to run database VACUUM: {ev}")
                
        except Exception as e:
            logger.error(f"Error during database auto-cleanup: {e}")

    def get_all_todos(self):
        """ 获取所有未归档的待办事项，未完成的在前，已完成的在后，按ID倒序 """
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("SELECT id, content, completed, created_at FROM todo WHERE archived = 0 ORDER BY completed ASC, id DESC")
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting all todos: {e}")
            return []

    def add_todo(self, content):
        """ 添加一条新的待办事项 """
        if not content:
            return None
        created_at = datetime.datetime.now().isoformat()
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    "INSERT INTO todo (content, completed, created_at, archived) VALUES (?, 0, ?, 0)",
                    (content, created_at)
                )
                todo_id = cursor.lastrowid
                return todo_id
        except Exception as e:
            logger.error(f"Error adding todo: {e}")
            return None

    def update_todo_status(self, todo_id, completed):
        """ 更新待办事项的完成状态 (1: 已完成, 0: 未完成) """
        try:
            completed_at = datetime.datetime.now().isoformat() if completed else None
            with self._get_conn() as conn:
                conn.execute(
                    "UPDATE todo SET completed = ?, completed_at = ? WHERE id = ?",
                    (1 if completed else 0, completed_at, todo_id)
                )
            return True
        except Exception as e:
            logger.error(f"Error updating todo status: {e}")
            return False

    def delete_todo(self, todo_id):
        """ 物理删除指定的待办事项 """
        try:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM todo WHERE id = ?", (todo_id,))
            return True
        except Exception as e:
            logger.error(f"Error deleting todo: {e}")
            return False

    def archive_todo(self, todo_id):
        """ 归档指定的已完成待办事项 """
        try:
            with self._get_conn() as conn:
                conn.execute("UPDATE todo SET archived = 1 WHERE id = ?", (todo_id,))
            return True
        except Exception as e:
            logger.error(f"Error archiving todo: {e}")
            return False

    def get_completed_todos(self, date_str=None):
        """ 获取已完成的待办事项（包括已归档的和未归档的），按完成时间倒序
        Args:
            date_str: 可选，筛选指定日期的待办 (YYYY-MM-DD 格式)
        """
        try:
            with self._get_conn() as conn:
                # 检查 completed_at 字段是否存在，做防错处理
                cursor = conn.execute("PRAGMA table_info(todo)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if date_str and "completed_at" in columns:
                    # 按日期筛选：completed_at 的前10位匹配日期
                    sql = "SELECT id, content, created_at, completed_at, archived FROM todo WHERE completed = 1 AND SUBSTR(COALESCE(completed_at, created_at), 1, 10) = ? ORDER BY COALESCE(completed_at, created_at) DESC, id DESC"
                    cursor = conn.execute(sql, (date_str,))
                elif "completed_at" in columns:
                    sql = "SELECT id, content, created_at, completed_at, archived FROM todo WHERE completed = 1 ORDER BY COALESCE(completed_at, created_at) DESC, id DESC"
                    cursor = conn.execute(sql)
                else:
                    sql = "SELECT id, content, created_at, NULL as completed_at, archived FROM todo WHERE completed = 1 ORDER BY id DESC"
                    cursor = conn.execute(sql)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting completed todos: {e}")
            return []

    def get_usage_by_date(self, date_str):
        """ 获取指定日期的软件使用数据 """
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    """
                    SELECT process_name, category, duration_seconds 
                    FROM usage 
                    WHERE date = ? 
                    ORDER BY duration_seconds DESC
                    """, (date_str,)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting usage by date: {e}")
            return []

    def get_total_by_date(self, date_str):
        """ 获取指定日期的总使用时长 """
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    "SELECT SUM(duration_seconds) FROM usage WHERE date = ?", (date_str,)
                )
                row = cursor.fetchone()
                return row[0] if row and row[0] is not None else 0
        except Exception as e:
            logger.error(f"Error getting total by date: {e}")
            return 0

    def get_category_by_date(self, date_str, category):
        """ 获取指定日期某分类的使用时长 """
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    "SELECT SUM(duration_seconds) FROM usage WHERE date = ? AND category = ?", 
                    (date_str, category)
                )
                row = cursor.fetchone()
                return row[0] if row and row[0] is not None else 0
        except Exception as e:
            logger.error(f"Error getting category by date: {e}")
            return 0
