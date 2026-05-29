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
            
    def export_all_to_csv(self, file_path):
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
                        # 分类列显示中文：工作, 游戏, 其他
                        category_cn = {"work": "工作", "game": "游戏"}.get(row["category"], "其他")
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
