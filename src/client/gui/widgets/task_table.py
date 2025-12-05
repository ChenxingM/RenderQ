"""
RenderQ GUI - Task 列表控件
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QProgressBar, QLabel, QMenu
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QAction, QCursor


class TaskTableWidget(QWidget):
    """Task列表控件"""

    task_selected = Signal(dict)
    task_action = Signal(str, dict)  # action_name, task

    # 状态颜色
    STATUS_COLORS = {
        "pending": "#888888",
        "assigned": "#2196F3",
        "running": "#FF9800",
        "completed": "#4CAF50",
        "failed": "#F44336",
    }

    STATUS_TEXT = {
        "pending": "等待中",
        "assigned": "已分配",
        "running": "渲染中",
        "completed": "已完成",
        "failed": "失败",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks = []
        self._current_job_id = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题标签
        self.title_label = QLabel("选择作业查看任务列表")
        self.title_label.setStyleSheet("color: #888; padding: 4px;")
        layout.addWidget(self.title_label)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "序号", "状态", "进度", "帧范围", "Worker", "开始时间", "耗时"
        ])

        # 表格样式
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        # 列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)  # 序号
        header.setSectionResizeMode(1, QHeaderView.Fixed)  # 状态
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # 进度
        header.setSectionResizeMode(3, QHeaderView.Fixed)  # 帧范围
        header.setSectionResizeMode(4, QHeaderView.Stretch)  # Worker
        header.setSectionResizeMode(5, QHeaderView.Fixed)  # 开始时间
        header.setSectionResizeMode(6, QHeaderView.Fixed)  # 耗时

        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 70)

        # Enable context menu
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        # Click on empty space to deselect
        self.table.viewport().installEventFilter(self)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

    def eventFilter(self, obj, event):
        """Handle clicks on empty area to deselect"""
        from PySide6.QtCore import QEvent
        if obj == self.table.viewport() and event.type() == QEvent.MouseButtonPress:
            index = self.table.indexAt(event.pos())
            if not index.isValid():
                self.table.clearSelection()
                return True
        return super().eventFilter(obj, event)

    def _show_context_menu(self, pos):
        """Show context menu for task"""
        index = self.table.indexAt(pos)
        if not index.isValid():
            return

        task = self._tasks[index.row()]
        status = task.get("status", "pending")

        menu = QMenu(self)

        # View Log
        view_log_action = QAction("View Log", self)
        view_log_action.triggered.connect(lambda: self.task_action.emit("view_log", task))
        menu.addAction(view_log_action)

        # Connect to Worker Log
        if task.get("assigned_worker"):
            worker_log_action = QAction("Connect to Worker Log", self)
            worker_log_action.triggered.connect(lambda: self.task_action.emit("worker_log", task))
            menu.addAction(worker_log_action)

        menu.addSeparator()

        # Retry - only for failed tasks
        if status == "failed":
            retry_action = QAction("Retry Task", self)
            retry_action.triggered.connect(lambda: self.task_action.emit("retry", task))
            menu.addAction(retry_action)

        # Cancel - for running/assigned tasks
        if status in ("running", "assigned"):
            cancel_action = QAction("Cancel Task", self)
            cancel_action.triggered.connect(lambda: self.task_action.emit("cancel", task))
            menu.addAction(cancel_action)

        # Suspend - for running tasks
        if status == "running":
            suspend_action = QAction("Suspend Task", self)
            suspend_action.triggered.connect(lambda: self.task_action.emit("suspend", task))
            menu.addAction(suspend_action)

        # Resume - conceptually not applicable per-task (job level)

        menu.exec_(QCursor.pos())

    def set_job(self, job_id: str, job_name: str = ""):
        """设置当前显示的Job"""
        self._current_job_id = job_id
        if job_name:
            self.title_label.setText(f"任务列表 - {job_name}")
        else:
            self.title_label.setText(f"任务列表")

    def set_tasks(self, tasks: list):
        """设置Task列表"""
        self._tasks = tasks
        self._update_table()

    def clear(self):
        """清空列表"""
        self._tasks = []
        self._current_job_id = None
        self.title_label.setText("选择作业查看任务列表")
        self.table.setRowCount(0)

    def _update_table(self):
        """更新表格"""
        self.table.setRowCount(len(self._tasks))

        for row, task in enumerate(self._tasks):
            # 序号
            idx_item = QTableWidgetItem(str(task.get("index", row)))
            idx_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, idx_item)

            # 状态
            status = task.get("status", "pending")
            status_text = self.STATUS_TEXT.get(status, status)
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            color = self.STATUS_COLORS.get(status, "#888888")
            status_item.setForeground(QColor(color))
            self.table.setItem(row, 1, status_item)

            # 进度条
            progress = task.get("progress", 0)
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setValue(int(progress))
            progress_bar.setFormat(f"{progress:.1f}%")
            progress_bar.setTextVisible(True)

            # 根据状态设置进度条颜色
            if status == "completed":
                progress_bar.setStyleSheet("""
                    QProgressBar { background-color: #262626; border: none; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #4CAF50; border-radius: 4px; }
                """)
            elif status == "failed":
                progress_bar.setStyleSheet("""
                    QProgressBar { background-color: #262626; border: none; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #F44336; border-radius: 4px; }
                """)
            elif status == "running":
                progress_bar.setStyleSheet("""
                    QProgressBar { background-color: #262626; border: none; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #FF9800; border-radius: 4px; }
                """)
            else:
                progress_bar.setStyleSheet("""
                    QProgressBar { background-color: #262626; border: none; border-radius: 4px; }
                    QProgressBar::chunk { background-color: #03A9F4; border-radius: 4px; }
                """)

            self.table.setCellWidget(row, 2, progress_bar)

            # 帧范围
            frame_start = task.get("frame_start")
            frame_end = task.get("frame_end")
            if frame_start is not None and frame_end is not None:
                frame_range = f"{frame_start}-{frame_end}"
            else:
                frame_range = "-"
            frame_item = QTableWidgetItem(frame_range)
            frame_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, frame_item)

            # Worker
            worker = task.get("assigned_worker") or ""
            worker_item = QTableWidgetItem(worker[:12] + "..." if len(worker) > 12 else worker)
            worker_item.setToolTip(worker)
            self.table.setItem(row, 4, worker_item)

            # 开始时间
            started_at = task.get("started_at", "")
            if started_at:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    started_str = dt.strftime("%H:%M:%S")
                except:
                    started_str = "-"
            else:
                started_str = "-"
            started_item = QTableWidgetItem(started_str)
            started_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 5, started_item)

            # 耗时
            started_at = task.get("started_at")
            finished_at = task.get("finished_at")
            if started_at and finished_at:
                try:
                    from datetime import datetime
                    start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                    duration = end_dt - start_dt
                    minutes = int(duration.total_seconds() // 60)
                    seconds = int(duration.total_seconds() % 60)
                    duration_str = f"{minutes}:{seconds:02d}"
                except:
                    duration_str = "-"
            elif started_at and status == "running":
                duration_str = "..."
            else:
                duration_str = "-"
            duration_item = QTableWidgetItem(duration_str)
            duration_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 6, duration_item)

            # 存储task数据
            idx_item.setData(Qt.UserRole, task)

    def _on_selection_changed(self):
        """选中变化"""
        selected = self.table.selectedItems()
        if selected:
            row = selected[0].row()
            task = self.table.item(row, 0).data(Qt.UserRole)
            self.task_selected.emit(task)

    def get_selected_task(self) -> dict | None:
        """获取选中的Task"""
        selected = self.table.selectedItems()
        if selected:
            row = selected[0].row()
            return self.table.item(row, 0).data(Qt.UserRole)
        return None
