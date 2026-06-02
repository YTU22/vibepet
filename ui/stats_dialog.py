import os
import datetime
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget, 
    QWidget, QMessageBox, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QStackedWidget, QDateEdit,
    QCalendarWidget, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QDate
from PyQt6.QtGui import QColor, QBrush, QPen, QPainter, QIcon, QPixmap

from utils.helpers import resource_path
from PyQt6.QtCharts import (
    QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, 
    QValueAxis, QPieSeries, QPieSlice
)

logger = logging.getLogger("vibe_pet")

class StatsDialog(QDialog):
    theme_changed = pyqtSignal()

    def __init__(self, db_manager, config_manager=None, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.config = config_manager
        self.theme_mode = self.config.get("theme_mode", "light") if self.config else "light"
        
        # 当前查看的日期，默认今天
        self.current_date = datetime.date.today()
        
        self.setWindowTitle("统计看板")
        self.resize(700, 500)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        
        # 设置窗口图标
        icon_path = resource_path("assets/icon.png")
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            self.setWindowIcon(QIcon(pixmap))
        
        self.setup_ui()
        self.refresh_data()
        self.apply_styles()
        
        # 启动时间更新定时器
        self._time_timer = QTimer(self)
        self._time_timer.timeout.connect(self._update_time)
        self._time_timer.start(1000)
        self._update_time()

    def _update_time(self):
        """ 更新时间显示 """
        now = datetime.datetime.now()
        self.lbl_time.setText(now.strftime("%Y-%m-%d %H:%M:%S"))

    def toggle_theme(self):
        """ 切换明亮模式/暗黑模式 """
        if self.theme_mode == "dark":
            self.theme_mode = "light"
            self.btn_theme.setText("暗黑模式")
        else:
            self.theme_mode = "dark"
            self.btn_theme.setText("明亮模式")
        if self.config:
            self.config.set("theme_mode", self.theme_mode)
            self.config.save_config()
        self.apply_styles()
        self.refresh_data()
        self.theme_changed.emit()

    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # 顶部标题 + 日期选择 + 时间 + 主题切换
        top_layout = QHBoxLayout()
        title_label = QLabel("统计看板")
        title_label.setObjectName("StatsTitle")
        top_layout.addWidget(title_label)
        
        # 日期选择器
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate(self.current_date.year, self.current_date.month, self.current_date.day))
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.dateChanged.connect(self.on_date_changed)
        self.date_edit.setObjectName("DateEdit")
        top_layout.addWidget(self.date_edit)
        
        self.btn_today = QPushButton("今天")
        self.btn_today.setObjectName("BtnToday")
        self.btn_today.clicked.connect(self.go_to_today)
        top_layout.addWidget(self.btn_today)
        
        top_layout.addStretch()
        
        self.lbl_time = QLabel()
        self.lbl_time.setObjectName("TimeLabel")
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_layout.addWidget(self.lbl_time)
        
        self.btn_theme = QPushButton("暗黑模式" if self.theme_mode == "light" else "明亮模式")
        self.btn_theme.setObjectName("BtnTheme")
        self.btn_theme.clicked.connect(self.toggle_theme)
        top_layout.addWidget(self.btn_theme)
        
        main_layout.addLayout(top_layout)
        
        # Tabs for charts
        self.tab_widget = QTabWidget()
        
        # Tab 1: Bar Chart / List View (Top 10 Apps / All Apps)
        self.tab_bar = QWidget()
        bar_layout = QVBoxLayout(self.tab_bar)
        bar_layout.setContentsMargins(5, 5, 5, 5)
        
        self.bar_stack = QStackedWidget()
        
        # Page 0: Chart View
        self.bar_chart = QChart()
        self.bar_chart.setTitle("今日使用时长 Top 10 应用 (单位：分钟)")
        self.bar_chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        
        self.bar_view = QChartView(self.bar_chart)
        self.bar_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.bar_stack.addWidget(self.bar_view)
        
        # Page 1: Table View for expanded view
        self.app_table = QTableWidget()
        self.app_table.setColumnCount(4)
        self.app_table.setHorizontalHeaderLabels(["排名", "应用名称", "所属分类", "今日时长"])
        self.app_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.app_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.app_table.setColumnWidth(0, 60)
        self.app_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.app_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.app_table.setAlternatingRowColors(True)
        self.app_table.verticalHeader().setVisible(False)
        self.bar_stack.addWidget(self.app_table)
        
        bar_layout.addWidget(self.bar_stack)
        
        # 展开/折叠显示非前十个的按钮
        self.btn_expand = QPushButton("展开全部应用")
        self.btn_expand.setCheckable(True)
        self.btn_expand.setObjectName("BtnExpand")
        self.btn_expand.clicked.connect(self.toggle_expand_bar_chart)
        bar_layout.addWidget(self.btn_expand)
        
        self.tab_widget.addTab(self.tab_bar, "今日排行")
        
        # Tab 2: Pie Chart (Category ratio)
        self.tab_pie = QWidget()
        pie_layout = QVBoxLayout(self.tab_pie)
        pie_layout.setContentsMargins(5, 5, 5, 5)
        
        self.lbl_pie_total = QLabel("今日已监控软件总时长: --")
        self.lbl_pie_total.setObjectName("PieTotalLabel")
        self.lbl_pie_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pie_layout.addWidget(self.lbl_pie_total)
        
        self.pie_chart = QChart()
        self.pie_chart.setTitle("今日软件使用分类比例")
        self.pie_chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        
        self.pie_view = QChartView(self.pie_chart)
        self.pie_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        pie_layout.addWidget(self.pie_view)
        
        self.tab_widget.addTab(self.tab_pie, "分类占比")
        
        # Tab 3: Pending Todos (待办清单)
        self.tab_pending_todo = QWidget()
        pending_todo_layout = QVBoxLayout(self.tab_pending_todo)
        pending_todo_layout.setContentsMargins(10, 10, 10, 10)
        
        self.todo_pending_table = QTableWidget()
        self.todo_pending_table.setColumnCount(4)
        self.todo_pending_table.setHorizontalHeaderLabels(["状态", "任务内容", "创建时间", "操作"])
        self.todo_pending_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.todo_pending_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.todo_pending_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.todo_pending_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.todo_pending_table.setColumnWidth(0, 80)
        self.todo_pending_table.setColumnWidth(2, 160)
        self.todo_pending_table.setColumnWidth(3, 80)
        self.todo_pending_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.todo_pending_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.todo_pending_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.todo_pending_table.setAlternatingRowColors(True)
        self.todo_pending_table.verticalHeader().setVisible(False)
        pending_todo_layout.addWidget(self.todo_pending_table)
        
        pending_bottom_layout = QHBoxLayout()
        self.btn_batch_delete_pending = QPushButton("批量删除所选")
        self.btn_batch_delete_pending.setObjectName("BtnBatchDeletePending")
        self.btn_batch_delete_pending.clicked.connect(self.batch_delete_pending_todos)
        pending_bottom_layout.addWidget(self.btn_batch_delete_pending)
        pending_bottom_layout.addStretch()
        pending_todo_layout.addLayout(pending_bottom_layout)
        
        self.tab_widget.addTab(self.tab_pending_todo, "待办清单")
        
        # Tab 4: Completed Todos (待办日记)
        self.tab_todo = QWidget()
        todo_layout = QVBoxLayout(self.tab_todo)
        todo_layout.setContentsMargins(10, 10, 10, 10)
        
        self.todo_table = QTableWidget()
        self.todo_table.setColumnCount(4)
        self.todo_table.setHorizontalHeaderLabels(["状态", "任务内容", "完成时间", "操作"])
        self.todo_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.todo_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.todo_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.todo_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.todo_table.setColumnWidth(0, 80)
        self.todo_table.setColumnWidth(2, 160)
        self.todo_table.setColumnWidth(3, 80)
        self.todo_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.todo_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.todo_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.todo_table.setAlternatingRowColors(True)
        self.todo_table.verticalHeader().setVisible(False)
        todo_layout.addWidget(self.todo_table)
        
        completed_bottom_layout = QHBoxLayout()
        self.btn_batch_delete_completed = QPushButton("批量删除所选")
        self.btn_batch_delete_completed.setObjectName("BtnBatchDeleteCompleted")
        self.btn_batch_delete_completed.clicked.connect(self.batch_delete_completed_todos)
        completed_bottom_layout.addWidget(self.btn_batch_delete_completed)
        completed_bottom_layout.addStretch()
        todo_layout.addLayout(completed_bottom_layout)
        
        self.tab_widget.addTab(self.tab_todo, "待办日记")
        
        main_layout.addWidget(self.tab_widget)
        
        # Bottom controls
        bottom_layout = QHBoxLayout()
        
        self.btn_refresh = QPushButton("刷新数据")
        self.btn_refresh.clicked.connect(self.refresh_data)
        
        self.btn_export = QPushButton("导出 CSV")
        self.btn_export.clicked.connect(self.export_csv)
        
        bottom_layout.addWidget(self.btn_refresh)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_export)
        
        main_layout.addLayout(bottom_layout)
        self.setLayout(main_layout)

    def on_date_changed(self, qdate):
        """ 日期选择器变更时刷新数据 """
        self.current_date = datetime.date(qdate.year(), qdate.month(), qdate.day())
        self.refresh_data()

    def go_to_today(self):
        """ 跳转到今天 """
        self.current_date = datetime.date.today()
        self.date_edit.setDate(QDate(self.current_date.year, self.current_date.month, self.current_date.day))
        self.refresh_data()

    def refresh_data(self):
        """ Refresh chart data from database """
        self.update_bar_chart()
        self.update_pie_chart()
        self.update_todo_list()
        self.update_todo_pending_list()

    def delete_todo_from_stats(self, todo_id):
        """ 从统计看板删除待办记录 """
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除这条待办记录吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.db.delete_todo(todo_id):
                self.update_todo_list()
                logger.info(f"Todo {todo_id} deleted from stats dialog")
            else:
                QMessageBox.warning(self, "删除失败", "无法删除该记录，请查看日志。")

    def update_todo_list(self):
        """ 更新待办日记表格 """
        date_str = self.current_date.isoformat()
        completed_todos = self.db.get_completed_todos(date_str)
        self.todo_table.setRowCount(len(completed_todos))
        
        for row_idx, todo in enumerate(completed_todos):
            # 1. 状态
            status_text = "📁 已归档" if todo.get("archived") else "✅ 已完成"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setData(Qt.ItemDataRole.UserRole, todo["id"]) # For batch deletion
            self.todo_table.setItem(row_idx, 0, status_item)
            
            # 2. 任务内容
            content_item = QTableWidgetItem(todo.get("content", ""))
            content_item.setToolTip(todo.get("content", ""))
            self.todo_table.setItem(row_idx, 1, content_item)
            
            # 3. 完成时间
            time_str = todo.get("completed_at") or todo.get("created_at") or ""
            # Format time if it's in ISO format (e.g. 2026-06-02T17:05:27.123)
            if time_str:
                try:
                    if 'T' in time_str:
                        # ISO format
                        dt = datetime.datetime.fromisoformat(time_str)
                        time_str = dt.strftime("%Y-%m-%d %H:%M")
                    else:
                        # Maybe already formatted or other format
                        time_str = time_str[:16]
                except Exception:
                    pass
            time_item = QTableWidgetItem(time_str)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.todo_table.setItem(row_idx, 2, time_item)
            
            # 4. 删除按钮
            btn_delete = QPushButton("🗑️ 删除")
            btn_delete.setStyleSheet("""
                QPushButton {
                    background-color: #c62828;
                    color: #ffffff;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            btn_delete.clicked.connect(lambda checked=False, tid=todo["id"]: self.delete_todo_from_stats(tid))
            self.todo_table.setCellWidget(row_idx, 3, btn_delete)

    def update_bar_chart(self):
        """ Fetch top apps and render bar/table chart """
        is_expanded = hasattr(self, 'btn_expand') and self.btn_expand.isChecked()
        limit = 100 if is_expanded else 10
        
        # 使用当前选择的日期
        date_str = self.current_date.isoformat()
        top_apps = self.db.get_usage_by_date(date_str)
        if not is_expanded:
            top_apps = top_apps[:10]
        self.current_top_apps = top_apps
        
        # Determine theme colors
        is_dark = (self.theme_mode == "dark")
        bg_color = QColor("#2b2b35") if is_dark else QColor("#ffffff")
        text_color = QColor("#ffffff") if is_dark else QColor("#333333")
        label_color = QColor("#cfd8dc") if is_dark else QColor("#555555")
        
        if is_expanded:
            self.bar_stack.setCurrentIndex(1)  # Table view
            self.btn_expand.setText("返回图表排行")
            # Populate table
            self.app_table.setRowCount(len(top_apps))
            
            categories_dict = {
                "work": "工作",
                "game": "游戏",
                "leisure": "休闲"
            }
            if hasattr(self, 'config') and self.config:
                categories_dict = self.config.get("custom_categories", categories_dict)
                
            for idx, app in enumerate(top_apps):
                rank_item = QTableWidgetItem(str(idx + 1))
                rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                name_item = QTableWidgetItem(app["process_name"])
                
                cat_id = app["category"]
                cat_name = categories_dict.get(cat_id, "其他")
                cat_item = QTableWidgetItem(cat_name)
                cat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                sec = app["duration_seconds"]
                hours = sec // 3600
                mins = (sec % 3600) // 60
                secs = sec % 60
                duration_str = ""
                if hours > 0:
                    duration_str += f"{hours}小时"
                if mins > 0 or hours > 0:
                    duration_str += f"{mins}分钟"
                duration_str += f"{secs}秒"
                if not duration_str:
                    duration_str = "0秒"
                time_item = QTableWidgetItem(duration_str)
                time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Make items read-only and look styled
                for item in (rank_item, name_item, cat_item, time_item):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if not is_dark:
                        item.setForeground(QBrush(QColor("#333333")))
                    else:
                        item.setForeground(QBrush(QColor("#e0e0e6")))
                
                self.app_table.setItem(idx, 0, rank_item)
                self.app_table.setItem(idx, 1, name_item)
                self.app_table.setItem(idx, 2, cat_item)
                self.app_table.setItem(idx, 3, time_item)
        else:
            self.bar_stack.setCurrentIndex(0)  # Chart view
            self.btn_expand.setText("展开全部应用")
            
            self.bar_chart.removeAllSeries()
            
            # Clear existing axes
            for axis in self.bar_chart.axes():
                self.bar_chart.removeAxis(axis)
                
            self.bar_chart.setTitle("今日使用时长 Top 10 应用 (单位：分钟)")
            
            # 获取系统及自定义分类映射
            categories_dict = {
                "work": "工作",
                "game": "游戏",
                "leisure": "休闲"
            }
            if hasattr(self, 'config') and self.config:
                categories_dict = self.config.get("custom_categories", categories_dict)
                
            # 动态创建 QBarSet 集合
            bar_sets = {}
            colors_map = {
                "work": QColor("#4ADE80"),   # 绿色
                "game": QColor("#F87171"),   # 红色
                "leisure": QColor("#38BDF8"),# 蓝绿色
                "other": QColor("#FBBF24")   # 黄琥珀色
            }
            nice_colors = [
                "#A78BFA", "#F472B6", "#FB7185", "#2DD4BF", "#F59E0B", "#60A5FA", "#34D399"
            ]
            
            for cat_id, cat_name in categories_dict.items():
                bar_sets[cat_id] = QBarSet(cat_name)
                if cat_id in colors_map:
                    bar_sets[cat_id].setColor(colors_map[cat_id])
                else:
                    color_index = abs(hash(cat_id)) % len(nice_colors)
                    bar_sets[cat_id].setColor(QColor(nice_colors[color_index]))
                    
            # 兜底添加“其他”分类
            if "other" not in bar_sets:
                bar_sets["other"] = QBarSet("其他")
                bar_sets["other"].setColor(colors_map["other"])
                
            categories = []
            for app in top_apps:
                name = app["process_name"]
                if len(name) > 12:
                    name = name[:10] + ".."
                categories.append(name)
                
                minutes = app["duration_seconds"] / 60.0
                cat = app["category"]
                
                target_cat = cat if cat in bar_sets else "other"
                for cat_id, bset in bar_sets.items():
                    if cat_id == target_cat:
                        bset.append(minutes)
                    else:
                        bset.append(0)
                        
            self.current_categories = categories
            series = QBarSeries()
            for cat_id, bset in bar_sets.items():
                has_data = False
                for val_idx in range(bset.count()):
                    if bset.at(val_idx) > 0:
                        has_data = True
                        break
                if has_data:
                    series.append(bset)
                    
            if series.count() == 0 and bar_sets:
                series.append(bar_sets["other"])
                
            self.bar_chart.addSeries(series)
            
            axis_x = QBarCategoryAxis()
            axis_x.append(categories)
            self.bar_chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
            series.attachAxis(axis_x)
            axis_x.setLabelsBrush(QBrush(label_color))
            
            axis_y = QValueAxis()
            axis_y.setTitleText("分钟")
            axis_y.setTitleBrush(QBrush(label_color))
            axis_y.setLabelsBrush(QBrush(label_color))
            max_val = max([app["duration_seconds"] / 60.0 for app in top_apps]) if top_apps else 10.0
            axis_y.setRange(0, max(1.0, max_val * 1.15))
            self.bar_chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
            series.attachAxis(axis_y)
            
            self.bar_chart.setBackgroundBrush(QBrush(bg_color))
            self.bar_chart.setTitleBrush(QBrush(text_color))
            self.bar_chart.legend().setLabelColor(label_color)
            self.bar_chart.legend().setVisible(True)
            self.bar_chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
            
            series.hovered.connect(self.on_bar_hovered)

    def toggle_expand_bar_chart(self):
        """ Toggle showing top 10 or all applications """
        self.update_bar_chart()

    def on_bar_hovered(self, status, index, barset):
        """ 处理柱状图悬停事件，显示提示框 """
        if status:
            val = barset.at(index)
            if val > 0:
                # 获取应用真实名称
                app_name = self.current_categories[index] if hasattr(self, 'current_categories') and index < len(self.current_categories) else ""
                if hasattr(self, 'current_top_apps') and index < len(self.current_top_apps):
                    app_name = self.current_top_apps[index]["process_name"]
                
                # 转换格式
                total_seconds = int(val * 60)
                hours = total_seconds // 3600
                mins = (total_seconds % 3600) // 60
                secs = total_seconds % 60
                
                duration_str = ""
                if hours > 0:
                    duration_str += f"{hours}小时"
                if mins > 0 or hours > 0:
                    duration_str += f"{mins}分钟"
                duration_str += f"{secs}秒"
                
                from PyQt6.QtWidgets import QToolTip
                from PyQt6.QtGui import QCursor
                
                tooltip_text = f"<b>应用:</b> {app_name}<br/><b>分类:</b> {barset.label()}<br/><b>时长:</b> {duration_str}"
                QToolTip.showText(QCursor.pos(), tooltip_text, self.bar_view)
        else:
            from PyQt6.QtWidgets import QToolTip
            QToolTip.hideText()

    def on_pie_hovered(self, slice_obj, status):
        """ 处理饼图切片悬停事件，显示提示框 """
        if status:
            pct = slice_obj.percentage() * 100
            total_seconds = int(slice_obj.value())
            hours = total_seconds // 3600
            mins = (total_seconds % 3600) // 60
            secs = total_seconds % 60
            
            duration_str = ""
            if hours > 0:
                duration_str += f"{hours}小时"
            if mins > 0 or hours > 0:
                duration_str += f"{mins}分钟"
            duration_str += f"{secs}秒"
            
            from PyQt6.QtWidgets import QToolTip
            from PyQt6.QtGui import QCursor
            
            label_title = slice_obj.label().split(' ')[0]
            tooltip_text = f"<b>分类:</b> {label_title}<br/><b>时长:</b> {duration_str}<br/><b>比例:</b> {pct:.1f}%"
            QToolTip.showText(QCursor.pos(), tooltip_text, self.pie_view)
        else:
            from PyQt6.QtWidgets import QToolTip
            QToolTip.hideText()

    def update_pie_chart(self):
        """ Fetch categories usage and render pie chart """
        self.pie_chart.removeAllSeries()
        
        # 获取系统及自定义分类映射
        categories_dict = {
            "work": "工作",
            "game": "游戏",
            "leisure": "休闲"
        }
        if hasattr(self, 'config') and self.config:
            categories_dict = self.config.get("custom_categories", categories_dict)
            
        cat_seconds = {}
        total_sec = 0
        
        colors_map = {
            "work": QColor("#4ADE80"),   # 绿色
            "game": QColor("#F87171"),   # 红色
            "leisure": QColor("#38BDF8"),# 蓝绿色
            "other": QColor("#FBBF24")   # 黄琥珀色
        }
        nice_colors = [
            "#A78BFA", "#F472B6", "#FB7185", "#2DD4BF", "#F59E0B", "#60A5FA", "#34D399"
        ]
        
        # 使用当前选择的日期
        date_str = self.current_date.isoformat()

        for cat_id in categories_dict.keys():
            sec = self.db.get_category_by_date(date_str, cat_id)
            if sec > 0:
                cat_seconds[cat_id] = sec
                total_sec += sec

        # 兜底查询其他分类时间
        other_sec = self.db.get_category_by_date(date_str, "other")
        if other_sec > 0:
            cat_seconds["other"] = other_sec
            total_sec += other_sec
            
        # 格式化并设置总时长显示
        hours = total_sec // 3600
        mins = (total_sec % 3600) // 60
        secs = total_sec % 60
        
        duration_str = ""
        if hours > 0:
            duration_str += f"{hours}小时"
        if mins > 0 or hours > 0:
            duration_str += f"{mins}分钟"
        duration_str += f"{secs}秒"
        if not duration_str:
            duration_str = "0秒"
            
        self.lbl_pie_total.setText(f"今日已监控软件总时长: {duration_str}")
            
        if total_sec == 0:
            # Empty state
            series = QPieSeries()
            empty_slice = series.append("无数据", 1)
            empty_slice.setBrush(QBrush(QColor("#455a64")))
            empty_slice.setLabelColor(QColor("#cfd8dc"))
            self.pie_chart.addSeries(series)
            return
            
        series = QPieSeries()
        slices = []
        
        for cat_id, sec in cat_seconds.items():
            name = categories_dict.get(cat_id, "其他")
            slice_obj = series.append(name, sec)
            if cat_id in colors_map:
                slice_obj.setBrush(colors_map[cat_id])
            else:
                color_index = abs(hash(cat_id)) % len(nice_colors)
                slice_obj.setBrush(QColor(nice_colors[color_index]))
            slices.append(slice_obj)
            
        # 如果只有一个分类有数据，稍微分离切片让标签更清晰
        if len(slices) == 1:
            slices[0].setExploded(True)
            slices[0].setExplodeDistanceFactor(0.05)
        
        is_dark = (self.theme_mode == "dark")
        bg_color = QColor("#2b2b35") if is_dark else QColor("#ffffff")
        text_color = QColor("#ffffff") if is_dark else QColor("#333333")
        label_color = QColor("#cfd8dc") if is_dark else QColor("#555555")

        # Custom labels: 显示百分比 + 时长，小于 3% 隐藏，防止重叠
        for s in slices:
            pct = s.percentage() * 100
            if pct < 3.0:
                s.setLabelVisible(False)
            else:
                s.setLabelVisible(True)
                s.setLabelColor(QColor("#ffffff") if is_dark else QColor("#333333"))
                # 标签格式: 分类名 时长(占比%)
                minutes = s.value() // 60
                s.setLabel(f"{s.label()} {minutes:.0f}分 ({pct:.1f}%)")
                s.setLabelPosition(QPieSlice.LabelPosition.LabelOutside)
            
        self.pie_chart.addSeries(series)
        series.hovered.connect(self.on_pie_hovered)
        
        # Styling Chart
        self.pie_chart.setBackgroundBrush(QBrush(bg_color))
        self.pie_chart.setTitleBrush(QBrush(text_color))
        self.pie_chart.legend().setLabelColor(label_color)
        self.pie_chart.legend().setVisible(True)
        self.pie_chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

    def export_csv(self):
        """ Export raw SQLite data into CSV on desktop """
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        date_str = datetime.date.today().strftime("%Y%m%d")
        filename = f"vibepet_export_{date_str}.csv"
        file_path = os.path.join(desktop_path, filename)
        
        categories_dict = {
            "work": "工作",
            "game": "游戏",
            "leisure": "休闲"
        }
        if hasattr(self, 'config') and self.config:
            categories_dict = self.config.get("custom_categories", categories_dict)
            
        success = self.db.export_all_to_csv(file_path, categories_dict)
        
        # QMessageBox manually styled to prevent text from being unreadable (Bug 1)
        msg = QMessageBox(None)
        self.style_message_box(msg)
        
        if success:
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("导出成功")
            msg.setText(f"数据已成功导出到桌面！\n文件名称：{filename}")
            logger.info(f"Exported database to {file_path}")
        else:
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("导出失败")
            msg.setText("无法将数据导出到 CSV 文件，请查看日志。")
            
        msg.exec()

    def apply_styles(self):
        """ Apply modern stylesheet based on light/dark mode """
        is_dark = (self.theme_mode == "dark")
        if is_dark:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e1e24;
                    color: #e0e0e6;
                    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                }
                #StatsTitle {
                    font-size: 18px;
                    font-weight: bold;
                    color: #81c784;
                    padding-bottom: 5px;
                }
                #TimeLabel {
                    color: #90a4ae;
                    font-size: 12px;
                    font-family: "Consolas", "Microsoft YaHei", monospace;
                    margin-right: 10px;
                }
                #BtnTheme {
                    background-color: #37474f;
                    color: #ffffff;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                }
                #BtnTheme:hover {
                    background-color: #455a64;
                }
                QTabWidget::pane {
                    border: 1px solid #42424a;
                    border-radius: 6px;
                    background-color: #2b2b35;
                }
                QTabBar::tab {
                    background-color: #37474f;
                    color: #b0bec5;
                    border: 1px solid #42424a;
                    border-bottom: none;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                }
                QTabBar::tab:selected {
                    background-color: #2b2b35;
                    color: #ffffff;
                    border-bottom: 1px solid #2b2b35;
                }
                QTabBar::tab:hover:!selected {
                    background-color: #455a64;
                    color: #ffffff;
                }
                QPushButton {
                    background-color: #37474f;
                    color: #ffffff;
                    border: 1px solid #455a64;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #3d4f58;
                    color: #81c784;
                    border: 1px solid #81c784;
                }
                QPushButton:pressed {
                    background-color: #212c31;
                    color: #66bb6a;
                    border: 1px solid #66bb6a;
                }
                QPushButton[text="导出 CSV"] {
                    background-color: #00796b;
                    color: #ffffff;
                    border: 1px solid #00796b;
                }
                QPushButton[text="导出 CSV"]:hover {
                    background-color: #00897b;
                    border: 1px solid #26a69a;
                }
                QPushButton[text="导出 CSV"]:pressed {
                    background-color: #004d40;
                    border: 1px solid #00695c;
                }
                #BtnBatchDeletePending, #BtnBatchDeleteCompleted {
                    background-color: #c62828;
                    color: #ffffff;
                    border: 1px solid #c62828;
                }
                #BtnBatchDeletePending:hover, #BtnBatchDeleteCompleted:hover {
                    background-color: #d32f2f;
                    border: 1px solid #d32f2f;
                    color: #ffffff;
                }
                #BtnExpand {
                    margin-top: 5px;
                    margin-bottom: 5px;
                }
                #BtnExpand:checked {
                    background-color: #00796b;
                }
                #BtnExpand:checked:hover {
                    background-color: #00897b;
                }
                #PieTotalLabel {
                    background-color: #37474f;
                    color: #81c784;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                    font-size: 14px;
                    margin-bottom: 5px;
                }
                QTableWidget {
                    background-color: #2b2b35;
                    alternate-background-color: #24242d;
                    color: #e0e0e6;
                    gridline-color: #42424a;
                    border: none;
                    border-radius: 4px;
                }
                QTableWidget::item {
                    padding: 5px;
                }
                QTableWidget::item:selected {
                    background-color: #00796b;
                    color: #ffffff;
                }
                QHeaderView::section {
                    background-color: #37474f;
                    color: #ffffff;
                    padding: 6px;
                    font-weight: bold;
                    border: 1px solid #42424a;
                }
                QScrollBar:vertical {
                    border: none;
                    background-color: #2b2b35;
                    width: 10px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background-color: #546e7a;
                    min-height: 20px;
                    border-radius: 5px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #78909c;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QToolTip {
                    background-color: #2b2b35;
                    color: #e0e0e6;
                    border: 1px solid #455a64;
                    border-radius: 4px;
                    font-family: "Microsoft YaHei", sans-serif;
                    font-size: 11px;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f5f5f7;
                    color: #333333;
                    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                }
                #StatsTitle {
                    font-size: 18px;
                    font-weight: bold;
                    color: #2e7d32;
                    padding-bottom: 5px;
                }
                #TimeLabel {
                    color: #555555;
                    font-size: 12px;
                    font-family: "Consolas", "Microsoft YaHei", monospace;
                    margin-right: 10px;
                }
                #BtnTheme {
                    background-color: #e0e0e0;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                }
                #BtnTheme:hover {
                    background-color: #d6d6d6;
                }
                QTabWidget::pane {
                    border: 1px solid #cccccc;
                    border-radius: 6px;
                    background-color: #ffffff;
                }
                QTabBar::tab {
                    background-color: #e0e0e0;
                    color: #555555;
                    border: 1px solid #cccccc;
                    border-bottom: none;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                }
                QTabBar::tab:selected {
                    background-color: #ffffff;
                    color: #000000;
                    border-bottom: 1px solid #ffffff;
                }
                QTabBar::tab:hover:!selected {
                    background-color: #d6d6d6;
                    color: #333333;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #e8f5e9;
                    color: #2e7d32;
                    border: 1px solid #2e7d32;
                }
                QPushButton:pressed {
                    background-color: #c8e6c9;
                    color: #1b5e20;
                    border: 1px solid #1b5e20;
                }
                QPushButton[text="导出 CSV"] {
                    background-color: #2e7d32;
                    color: #ffffff;
                    border: 1px solid #2e7d32;
                }
                QPushButton[text="导出 CSV"]:hover {
                    background-color: #388e3c;
                    border: 1px solid #4caf50;
                }
                QPushButton[text="导出 CSV"]:pressed {
                    background-color: #1b5e20;
                    border: 1px solid #388e3c;
                }
                #BtnBatchDeletePending, #BtnBatchDeleteCompleted {
                    background-color: #d32f2f;
                    color: #ffffff;
                    border: 1px solid #d32f2f;
                }
                #BtnBatchDeletePending:hover, #BtnBatchDeleteCompleted:hover {
                    background-color: #e53935;
                    border: 1px solid #e53935;
                    color: #ffffff;
                }
                #BtnExpand {
                    margin-top: 5px;
                    margin-bottom: 5px;
                }
                #BtnExpand:checked {
                    background-color: #2e7d32;
                    color: #ffffff;
                    border: none;
                }
                #BtnExpand:checked:hover {
                    background-color: #388e3c;
                }
                #PieTotalLabel {
                    background-color: #e8f5e9;
                    color: #2e7d32;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                    font-size: 14px;
                    margin-bottom: 5px;
                }
                QTableWidget {
                    background-color: #ffffff;
                    alternate-background-color: #f7f7f9;
                    color: #333333;
                    gridline-color: #e0e0e0;
                    border: none;
                    border-radius: 4px;
                }
                QTableWidget::item {
                    padding: 5px;
                }
                QTableWidget::item:selected {
                    background-color: #a5d6a7;
                    color: #1b5e20;
                }
                QHeaderView::section {
                    background-color: #f5f5f5;
                    color: #333333;
                    padding: 6px;
                    font-weight: bold;
                    border: 1px solid #e0e0e0;
                }
                QScrollBar:vertical {
                    border: none;
                    background-color: #ffffff;
                    width: 10px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background-color: #bdbdbd;
                    min-height: 20px;
                    border-radius: 5px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #9e9e9e;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QToolTip {
                    background-color: #ffffff;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    font-family: "Microsoft YaHei", sans-serif;
                    font-size: 11px;
                }
            """)

    def update_todo_pending_list(self):
        """ 更新待办清单表格（进行中） """
        pending_todos = self.db.get_uncompleted_todos()
        self.todo_pending_table.setRowCount(len(pending_todos))
        
        is_dark = (self.theme_mode == "dark")
        
        for row_idx, todo in enumerate(pending_todos):
            # 1. 状态复选框
            cb_container = QWidget()
            cb_layout = QHBoxLayout(cb_container)
            cb = QCheckBox()
            cb.setChecked(False)
            cb.setProperty("todo_id", todo["id"])
            cb.clicked.connect(self.on_stats_todo_status_changed)
            
            # Apply styling for QCheckBox in table
            if is_dark:
                cb.setStyleSheet("""
                    QCheckBox::indicator {
                        width: 14px;
                        height: 14px;
                        border: 1px solid #8b5cf6;
                        border-radius: 3px;
                        background: #1a1622;
                    }
                    QCheckBox::indicator:checked {
                        background-color: #8b5cf6;
                        border: 1px solid #a78bfa;
                    }
                """)
            else:
                cb.setStyleSheet("""
                    QCheckBox::indicator {
                        width: 14px;
                        height: 14px;
                        border: 1px solid #ca8a04;
                        border-radius: 3px;
                        background: #ffffff;
                    }
                    QCheckBox::indicator:checked {
                        background-color: #facc15;
                        border: 1px solid #ca8a04;
                    }
                """)
            cb_layout.addWidget(cb)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            self.todo_pending_table.setCellWidget(row_idx, 0, cb_container)
            
            # Storing todo ID in column 0 item for reference
            status_dummy = QTableWidgetItem("")
            status_dummy.setData(Qt.ItemDataRole.UserRole, todo["id"])
            self.todo_pending_table.setItem(row_idx, 0, status_dummy)
            
            # 2. 任务内容
            content_item = QTableWidgetItem(todo.get("content", ""))
            content_item.setToolTip(todo.get("content", ""))
            self.todo_pending_table.setItem(row_idx, 1, content_item)
            
            # 3. 创建时间
            time_str = todo.get("created_at") or ""
            if time_str:
                try:
                    if 'T' in time_str:
                        dt = datetime.datetime.fromisoformat(time_str)
                        time_str = dt.strftime("%Y-%m-%d %H:%M")
                    else:
                        time_str = time_str[:16]
                except Exception:
                    pass
            time_item = QTableWidgetItem(time_str)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.todo_pending_table.setItem(row_idx, 2, time_item)
            
            # 4. 删除按钮
            btn_delete = QPushButton("🗑️ 删除")
            btn_delete.setStyleSheet("""
                QPushButton {
                    background-color: #c62828;
                    color: #ffffff;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            btn_delete.clicked.connect(lambda checked=False, tid=todo["id"]: self.delete_pending_todo_from_stats(tid))
            self.todo_pending_table.setCellWidget(row_idx, 3, btn_delete)

    def on_stats_todo_status_changed(self):
        """ 看板中待办勾选状态改变回调 """
        cb = self.sender()
        if cb:
            todo_id = cb.property("todo_id")
            checked = cb.isChecked()
            if todo_id is not None:
                self.db.update_todo_status(todo_id, checked)
                logger.info(f"Todo {todo_id} status updated to {checked} from stats dialog")
                self.refresh_data()
                self.refresh_external_todo_window()

    def delete_pending_todo_from_stats(self, todo_id):
        """ 从统计看板删除进行中（未完成）待办记录 """
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除这条待办事项吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.db.delete_todo(todo_id):
                self.refresh_data()
                self.refresh_external_todo_window()
                logger.info(f"Pending todo {todo_id} deleted from stats dialog")
            else:
                QMessageBox.warning(self, "删除失败", "无法删除该记录，请查看日志。")

    def batch_delete_pending_todos(self):
        """ 批量删除选中的未完成待办事项 """
        selected_indexes = self.todo_pending_table.selectedIndexes()
        if not selected_indexes:
            msg = QMessageBox(None)
            self.style_message_box(msg)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("提示")
            msg.setText("请先选择需要删除的行。")
            msg.exec()
            return
            
        # Extract unique row indexes
        rows = sorted(list(set(index.row() for index in selected_indexes)), reverse=True)
        
        # Get todo IDs for selected rows
        todo_ids = []
        for row in rows:
            dummy_item = self.todo_pending_table.item(row, 0)
            if dummy_item:
                tid = dummy_item.data(Qt.ItemDataRole.UserRole)
                if tid is not None:
                    todo_ids.append(tid)
                    
        if not todo_ids:
            return
            
        msg = QMessageBox(None)
        self.style_message_box(msg)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("确认批量删除")
        msg.setText(f"确定要删除选中的 {len(todo_ids)} 条待办事项吗？\n此操作不可恢复。")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        
        if msg.exec() == QMessageBox.StandardButton.Yes:
            success_count = 0
            for tid in todo_ids:
                if self.db.delete_todo(tid):
                    success_count += 1
            
            logger.info(f"Batch deleted {success_count}/{len(todo_ids)} pending todos from stats dialog")
            self.refresh_data()
            self.refresh_external_todo_window()

    def batch_delete_completed_todos(self):
        """ 批量删除选中的已完成待办记录（待办日记） """
        selected_indexes = self.todo_table.selectedIndexes()
        if not selected_indexes:
            msg = QMessageBox(None)
            self.style_message_box(msg)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("提示")
            msg.setText("请先选择需要删除的行。")
            msg.exec()
            return
            
        rows = sorted(list(set(index.row() for index in selected_indexes)), reverse=True)
        
        todo_ids = []
        for row in rows:
            dummy_item = self.todo_table.item(row, 0)
            if dummy_item:
                tid = dummy_item.data(Qt.ItemDataRole.UserRole)
                if tid is not None:
                    todo_ids.append(tid)
                    
        if not todo_ids:
            return
            
        msg = QMessageBox(None)
        self.style_message_box(msg)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("确认批量删除")
        msg.setText(f"确定要删除选中的 {len(todo_ids)} 条已完成待办记录吗？\n此操作不可恢复。")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        
        if msg.exec() == QMessageBox.StandardButton.Yes:
            success_count = 0
            for tid in todo_ids:
                if self.db.delete_todo(tid):
                    success_count += 1
            
            logger.info(f"Batch deleted {success_count}/{len(todo_ids)} completed todos from stats dialog")
            self.refresh_data()
            self.refresh_external_todo_window()

    def style_message_box(self, msg):
        """ 样式化消息提示框 """
        # 设置窗口图标
        icon_path = resource_path("assets/icon.png")
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            msg.setWindowIcon(QIcon(pixmap))
            
        is_dark = (self.theme_mode == "dark")
        if is_dark:
            msg.setStyleSheet("""
                QMessageBox {
                    background-color: #1e1e24;
                    color: #ffffff;
                    font-family: "Microsoft YaHei", sans-serif;
                }
                QLabel {
                    color: #ffffff;
                    font-size: 13px;
                }
                QPushButton {
                    background-color: #37474f;
                    color: #ffffff;
                    border-radius: 4px;
                    padding: 6px 16px;
                    min-width: 60px;
                }
                QPushButton:hover {
                    background-color: #455a64;
                }
            """)
        else:
            msg.setStyleSheet("""
                QMessageBox {
                    background-color: #f5f5f7;
                    color: #333333;
                    font-family: "Microsoft YaHei", sans-serif;
                }
                QLabel {
                    color: #333333;
                    font-size: 13px;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    padding: 6px 16px;
                    min-width: 60px;
                }
                QPushButton:hover {
                    background-color: #d6d6d6;
                }
            """)

    def refresh_external_todo_window(self):
        """ 刷新外部的便签待办窗口 """
        from PyQt6.QtWidgets import QApplication
        from ui.todo_window import TodoWindow
        for w in QApplication.topLevelWidgets():
            if isinstance(w, TodoWindow):
                w.reload_todos()
                break
