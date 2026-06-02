import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QCheckBox, QGraphicsDropShadowEffect, QApplication
)
from PyQt6.QtCore import Qt, QPoint, pyqtSlot
from PyQt6.QtGui import QFont, QColor

logger = logging.getLogger("vibe_pet")


class TodoItemWidget(QWidget):
    """ 自定义待办条目组件 """
    def __init__(self, todo_id, content, completed, on_status_changed, on_deleted, parent=None):
        super().__init__(parent)
        self.todo_id = todo_id
        self.content = content
        self.completed = bool(completed)
        self.on_status_changed = on_status_changed
        self.on_deleted = on_deleted

        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        # 1. 复选框
        self.cb = QCheckBox(self)
        self.cb.setChecked(self.completed)
        self.cb.stateChanged.connect(self._on_state_changed)
        layout.addWidget(self.cb)

        # 2. 文本 Label
        self.lbl = QLabel(self.content, self)
        self.lbl.setWordWrap(True)
        self.lbl.setFont(QFont("Microsoft YaHei", 9))
        layout.addWidget(self.lbl, stretch=1)

        # 3. 删除按钮
        self.btn_del = QPushButton("×", self)
        self.btn_del.setFixedSize(18, 18)
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del.clicked.connect(self._on_delete_clicked)
        layout.addWidget(self.btn_del)

        self.update_style()

    def _on_state_changed(self, state):
        self.completed = (state == 2)  # Qt.CheckState.Checked
        self.update_style()
        self.on_status_changed(self.todo_id, self.completed)

    def _on_delete_clicked(self):
        self.on_deleted(self.todo_id, self)

    def update_style(self):
        """ 根据完成状态更新文本样式 """
        if self.completed:
            # 已完成：置灰且带删除线
            self.lbl.setStyleSheet("""
                color: #888888;
                text-decoration: line-through;
            """)
        else:
            # 未完成
            self.lbl.setStyleSheet("color: inherit; text-decoration: none;")


class TodoWindow(QWidget):
    """ 便签待办清单窗口 """
    def __init__(self, db_manager, config_manager, main_win=None, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.config = config_manager
        self.main_win = main_win

        # 设置窗口标志：无边框、工具悬浮窗（不在任务栏显示）、置顶
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setFixedSize(260, 320)
        self.drag_position = QPoint()
        self._is_dragging = False

        self.setup_ui()
        self.load_position()
        self.apply_theme()
        self.reload_todos()

    def setup_ui(self):
        # 1. 窗口主卡片容器（用于实现圆角与投影效果）
        self.card = QFrame(self)
        self.card.setObjectName("TodoCard")
        self.card.setGeometry(10, 10, 240, 300)

        # 添加阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.card.setGraphicsEffect(shadow)

        # 2. 卡片内部主布局
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        # 3. 头部标题栏
        header = QHBoxLayout()
        header.setSpacing(4)

        self.lbl_pin = QLabel("📌", self)
        self.lbl_pin.setFont(QFont("Microsoft YaHei", 10))
        header.addWidget(self.lbl_pin)

        self.lbl_title = QLabel("待办清单", self)
        self.lbl_title.setObjectName("TodoTitle")
        self.lbl_title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        header.addWidget(self.lbl_title)

        header.addStretch()

        self.btn_close = QPushButton("×", self)
        self.btn_close.setObjectName("TodoCloseBtn")
        self.btn_close.setFixedSize(20, 20)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.hide_window)
        header.addWidget(self.btn_close)

        card_layout.addLayout(header)

        # 4. 滚动区域用于展示待办条目
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("TodoScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.FrameShape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 滚动区域内部容器
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("TodoScrollContent")
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(2)
        self.list_layout.addStretch()  # 靠上对齐

        self.scroll.setWidget(self.scroll_content)
        card_layout.addWidget(self.scroll, stretch=1)

        # 5. 底部输入栏
        input_layout = QHBoxLayout()
        input_layout.setSpacing(4)

        self.txt_input = QLineEdit(self)
        self.txt_input.setObjectName("TodoInput")
        self.txt_input.setPlaceholderText("添加新待办...")
        self.txt_input.setFont(QFont("Microsoft YaHei", 9))
        self.txt_input.returnPressed.connect(self.add_todo)
        input_layout.addWidget(self.txt_input, stretch=1)

        self.btn_add = QPushButton("+", self)
        self.btn_add.setObjectName("TodoAddBtn")
        self.btn_add.setFixedSize(22, 22)
        self.btn_add.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self.add_todo)
        input_layout.addWidget(self.btn_add)

        card_layout.addLayout(input_layout)

    def load_position(self):
        """ 恢复上次保存的窗口位置 """
        screen = QApplication.primaryScreen().availableGeometry()
        saved_x = self.config.get("todo_x")
        saved_y = self.config.get("todo_y")

        if saved_x is not None and saved_y is not None:
            # 确保位置在当前屏幕范围内
            x = max(0, min(saved_x, screen.width() - self.width()))
            y = max(0, min(saved_y, screen.height() - self.height()))
            self.move(x, y)
        else:
            # 默认放置在桌宠上方或屏幕中间偏右
            x = screen.width() - self.width() - 40
            y = screen.height() - self.height() - 360
            self.move(x, y)

    def apply_theme(self):
        """ 根据明亮/暗黑模式应用样式 """
        theme = self.config.get("theme_mode", "light")
        if theme == "light":
            # 拟物化浅黄 post-it 便签风格
            self.card.setStyleSheet("""
                #TodoCard {
                    background-color: #fef9c3; /* 浅黄色 */
                    border: 1px solid #fde047;
                    border-radius: 8px;
                }
                #TodoTitle {
                    color: #713f12; /* 深褐色手写感 */
                }
                #TodoCloseBtn {
                    border: none;
                    background: transparent;
                    color: #ca8a04;
                    font-size: 14px;
                    font-weight: bold;
                }
                #TodoCloseBtn:hover {
                    color: #854d0e;
                }
                #TodoScroll, #TodoScrollContent {
                    background: transparent;
                }
                #TodoInput {
                    background-color: rgba(255, 255, 255, 0.8);
                    border: 1px solid #fde047;
                    border-radius: 4px;
                    padding: 2px 6px;
                    color: #451a03;
                }
                #TodoInput:focus {
                    border: 1px solid #ca8a04;
                    background-color: #ffffff;
                }
                #TodoAddBtn {
                    background-color: #fde047;
                    border: 1px solid #eab308;
                    border-radius: 4px;
                    color: #713f12;
                }
                #TodoAddBtn:hover {
                    background-color: #facc15;
                }
                #TodoAddBtn:pressed {
                    background-color: #eab308;
                }
                QCheckBox {
                    color: #451a03;
                }
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
                    image: url(assets/check.png); /* 如果没有贴图，Qt会使用默认或者没有 */
                }
                QLabel {
                    color: #451a03;
                }
                QPushButton {
                    border: none;
                    background: transparent;
                    color: #ca8a04;
                    font-size: 12px;
                }
                QPushButton:hover {
                    color: #b91c1c;
                }
            """)
        else:
            # 拟物化暗紫灰 post-it 便签风格
            self.card.setStyleSheet("""
                #TodoCard {
                    background-color: #262130; /* 深紫灰色 */
                    border: 1px solid #493d59;
                    border-radius: 8px;
                }
                #TodoTitle {
                    color: #d8b4fe; /* 淡紫色 */
                }
                #TodoCloseBtn {
                    border: none;
                    background: transparent;
                    color: #8b5cf6;
                    font-size: 14px;
                    font-weight: bold;
                }
                #TodoCloseBtn:hover {
                    color: #a78bfa;
                }
                #TodoScroll, #TodoScrollContent {
                    background: transparent;
                }
                #TodoInput {
                    background-color: #1a1622;
                    border: 1px solid #493d59;
                    border-radius: 4px;
                    padding: 2px 6px;
                    color: #e2e8f0;
                }
                #TodoInput:focus {
                    border: 1px solid #8b5cf6;
                }
                #TodoAddBtn {
                    background-color: #6d28d9;
                    border: 1px solid #5b21b6;
                    border-radius: 4px;
                    color: #ffffff;
                }
                #TodoAddBtn:hover {
                    background-color: #7c3aed;
                }
                #TodoAddBtn:pressed {
                    background-color: #5b21b6;
                }
                QCheckBox {
                    color: #e2e8f0;
                }
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
                QLabel {
                    color: #e2e8f0;
                }
                QPushButton {
                    border: none;
                    background: transparent;
                    color: #8b5cf6;
                    font-size: 12px;
                }
                QPushButton:hover {
                    color: #ef4444;
                }
            """)

    def reload_todos(self):
        """ 从数据库重载待办事项并显示 """
        # 清理原有的待办小部件
        # 移除 list_layout 中除了底部的 stretch 之外的所有 widget
        for i in reversed(range(self.list_layout.count())):
            item = self.list_layout.itemAt(i)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        todos = self.db.get_all_todos()
        
        # 依次添加到布局中（在 stretch 之前）
        for todo in todos:
            item_widget = TodoItemWidget(
                todo_id=todo["id"],
                content=todo["content"],
                completed=todo["completed"],
                on_status_changed=self.on_todo_status_changed,
                on_deleted=self.on_todo_deleted,
                parent=self
            )
            # 在布局的顶部或相应位置插入
            self.list_layout.insertWidget(self.list_layout.count() - 1, item_widget)

    def add_todo(self):
        """ 添加一条待办 """
        text = self.txt_input.text().strip()
        if not text:
            return
        
        todo_id = self.db.add_todo(text)
        if todo_id:
            self.txt_input.clear()
            self.reload_todos()
            logger.info(f"Added todo item id={todo_id}")

    def on_todo_status_changed(self, todo_id, completed):
        """ 待办勾选状态改变回调 """
        self.db.update_todo_status(todo_id, completed)
        # 为了配合完成的事项沉底逻辑，重新加载列表
        self.reload_todos()
        logger.info(f"Updated todo item id={todo_id} status={completed}")

    def on_todo_deleted(self, todo_id, item_widget):
        """ 待办删除回调 """
        self.db.delete_todo(todo_id)
        self.list_layout.removeWidget(item_widget)
        item_widget.deleteLater()
        # 重新加载保持布局一致
        self.reload_todos()
        logger.info(f"Deleted todo item id={todo_id}")

    def hide_window(self):
        """ 隐藏便签窗口并保存配置状态 """
        self.hide()
        self.config.set("todo_visible", False)
        # 发送设置变更通知，以便桌宠菜单更新同步
        main_win = self.main_win
        if main_win and hasattr(main_win, 'on_todo_window_toggled'):
            main_win.on_todo_window_toggled(False)

    # --- 鼠标拖拽功能 ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 仅允许在标题栏或图钉区域进行拖动
            # 便签窗口卡片高度300，最上方30px为标题区域
            local_pos = event.position().toPoint()
            if local_pos.y() >= 10 and local_pos.y() <= 45:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self._is_dragging = True
                event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._is_dragging:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            # 保存坐标到配置中
            self.config.set("todo_x", self.x())
            self.config.set("todo_y", self.y())
            event.accept()
            logger.info(f"[便签] 拖拽完成，位置保存到 ({self.x()}, {self.y()})")
