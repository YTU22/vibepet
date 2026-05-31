import os
import datetime
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget, 
    QWidget, QMessageBox, QLabel
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QBrush, QPen, QPainter, QIcon, QPixmap

from utils.helpers import resource_path
from PyQt6.QtCharts import (
    QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, 
    QValueAxis, QPieSeries, QPieSlice
)

logger = logging.getLogger("vibe_pet")

class StatsDialog(QDialog):
    def __init__(self, db_manager, config_manager=None, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.config = config_manager
        
        self.setWindowTitle("VibePet - 软体统计看板")
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

    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # 顶部标题 + 时间
        top_layout = QHBoxLayout()
        title_label = QLabel("VibePet 软体统计看板")
        title_label.setObjectName("StatsTitle")
        top_layout.addWidget(title_label)
        top_layout.addStretch()
        self.lbl_time = QLabel()
        self.lbl_time.setObjectName("TimeLabel")
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_layout.addWidget(self.lbl_time)
        main_layout.addLayout(top_layout)
        
        # Tabs for charts
        self.tab_widget = QTabWidget()
        
        # Tab 1: Bar Chart (Top 10 Apps)
        self.tab_bar = QWidget()
        bar_layout = QVBoxLayout(self.tab_bar)
        bar_layout.setContentsMargins(5, 5, 5, 5)
        
        self.bar_chart = QChart()
        self.bar_chart.setTitle("今日使用时长 Top 10 应用 (单位：分钟)")
        self.bar_chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        
        self.bar_view = QChartView(self.bar_chart)
        self.bar_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar_layout.addWidget(self.bar_view)
        
        self.tab_widget.addTab(self.tab_bar, "今日排行")
        
        # Tab 2: Pie Chart (Category ratio)
        self.tab_pie = QWidget()
        pie_layout = QVBoxLayout(self.tab_pie)
        pie_layout.setContentsMargins(5, 5, 5, 5)
        
        self.pie_chart = QChart()
        self.pie_chart.setTitle("今日软件使用分类比例")
        self.pie_chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        
        self.pie_view = QChartView(self.pie_chart)
        self.pie_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        pie_layout.addWidget(self.pie_view)
        
        self.tab_widget.addTab(self.tab_pie, "分类占比")
        
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

    def refresh_data(self):
        """ Refresh chart data from database """
        self.update_bar_chart()
        self.update_pie_chart()

    def update_bar_chart(self):
        """ Fetch top 10 apps and render bar chart """
        self.bar_chart.removeAllSeries()
        
        # Clear existing axes
        for axis in self.bar_chart.axes():
            self.bar_chart.removeAxis(axis)
            
        top_apps = self.db.get_today_top_apps(10)
        
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
            # Shorten name if too long
            name = app["process_name"]
            if len(name) > 12:
                name = name[:10] + ".."
            categories.append(name)
            
            # Value in minutes
            minutes = app["duration_seconds"] / 60.0
            cat = app["category"]
            
            target_cat = cat if cat in bar_sets else "other"
            for cat_id, bset in bar_sets.items():
                if cat_id == target_cat:
                    bset.append(minutes)
                else:
                    bset.append(0)
                    
        series = QBarSeries()
        # 只向 series 中添加包含有效数据的分类集，避免图例展示过多空白分类
        for cat_id, bset in bar_sets.items():
            has_data = False
            for val_idx in range(bset.count()):
                if bset.at(val_idx) > 0:
                    has_data = True
                    break
            if has_data:
                series.append(bset)
                
        # 如果全部没有数据，或者没有加入任何 series，至少加一个 other 保证不报错
        if series.count() == 0 and bar_sets:
            series.append(bar_sets["other"])
            
        self.bar_chart.addSeries(series)
        
        # X-Axis (Categories)
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        self.bar_chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)
        axis_x.setLabelsBrush(QBrush(QColor("#cfd8dc")))
        
        # Y-Axis (Values in minutes)
        axis_y = QValueAxis()
        axis_y.setTitleText("分钟")
        axis_y.setTitleBrush(QBrush(QColor("#cfd8dc")))
        axis_y.setLabelsBrush(QBrush(QColor("#cfd8dc")))
        # Determine maximum value to set range dynamically
        max_val = max([app["duration_seconds"] / 60.0 for app in top_apps]) if top_apps else 10.0
        axis_y.setRange(0, max(1.0, max_val * 1.15))
        self.bar_chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        
        # Styling Chart
        self.bar_chart.setBackgroundBrush(QBrush(QColor("#2b2b35")))
        self.bar_chart.setTitleBrush(QBrush(QColor("#ffffff")))
        self.bar_chart.legend().setLabelColor(QColor("#cfd8dc"))
        self.bar_chart.legend().setVisible(True)
        self.bar_chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

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
        
        for cat_id in categories_dict.keys():
            sec = self.db.get_today_by_category(cat_id)
            if sec > 0:
                cat_seconds[cat_id] = sec
                total_sec += sec
                
        # 兜底查询“其他”分类时间
        other_sec = self.db.get_today_by_category("other")
        if other_sec > 0:
            cat_seconds["other"] = other_sec
            total_sec += other_sec
            
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
        
        # Custom labels: 显示百分比 + 时长，放在切片外侧
        for s in slices:
            s.setLabelVisible(True)
            s.setLabelColor(QColor("#ffffff"))
            # 标签格式: 分类名 时长(占比%)
            pct = s.percentage() * 100
            minutes = s.value() // 60
            s.setLabel(f"{s.label()} {minutes:.0f}分 ({pct:.1f}%)")
            s.setLabelPosition(QPieSlice.LabelPosition.LabelOutside)
            
        self.pie_chart.addSeries(series)
        
        # Styling Chart
        self.pie_chart.setBackgroundBrush(QBrush(QColor("#2b2b35")))
        self.pie_chart.setTitleBrush(QBrush(QColor("#ffffff")))
        self.pie_chart.legend().setLabelColor(QColor("#cfd8dc"))
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
        """ Apply modern dark stylesheet """
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
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #455a64;
            }
            QPushButton:pressed {
                background-color: #263238;
            }
            QPushButton[text="导出 CSV"] {
                background-color: #00796b;
            }
            QPushButton[text="导出 CSV"]:hover {
                background-color: #00897b;
            }
            QPushButton[text="导出 CSV"]:pressed {
                background-color: #004d40;
            }
        """)
