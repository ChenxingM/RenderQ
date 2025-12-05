"""
RenderQ GUI - 作业表格组件
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QColor


STATUS_COLORS = {
    "pending": QColor(180, 180, 180),      # 灰色
    "queued": QColor(100, 149, 237),       # 蓝色
    "active": QColor(50, 205, 50),         # 绿色
    "completed": QColor(34, 139, 34),      # 深绿
    "failed": QColor(220, 20, 60),         # 红色
    "suspended": QColor(255, 165, 0),      # 橙色
    "cancelled": QColor(128, 128, 128),    # 深灰
}

STATUS_TEXT = {
    "pending": "等待中",
    "queued": "队列中",
    "active": "渲染中",
    "completed": "已完成",
    "failed": "失败",
    "suspended": "已暂停",
    "cancelled": "已取消",
}


class JobTableWidget(QWidget):
    """作业表格"""
    
    job_selected = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.jobs = []
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "名称", "插件", "状态", "进度", "任务", "优先级", "提交时间", "ID"
        ])
        
        # 设置列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 名称
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        
        self.table.setColumnWidth(1, 100)   # 插件
        self.table.setColumnWidth(2, 80)    # 状态
        self.table.setColumnWidth(3, 120)   # 进度
        self.table.setColumnWidth(4, 80)    # 任务
        self.table.setColumnWidth(5, 60)    # 优先级
        self.table.setColumnWidth(6, 140)   # 时间
        self.table.setColumnWidth(7, 80)    # ID
        
        # 选择行为
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        # Click on empty space to deselect
        self.table.viewport().installEventFilter(self)

        # 信号
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        layout.addWidget(self.table)

    def eventFilter(self, obj, event):
        """Handle clicks on empty area to deselect"""
        if obj == self.table.viewport() and event.type() == QEvent.MouseButtonPress:
            index = self.table.indexAt(event.pos())
            if not index.isValid():
                self.table.clearSelection()
                self.job_selected.emit({})
                return True
        return super().eventFilter(obj, event)
    
    def set_jobs(self, jobs: list):
        """设置作业列表"""
        self.jobs = jobs
        
        # 保存当前选中
        selected_id = None
        current = self.table.currentRow()
        if 0 <= current < len(self.jobs):
            selected_id = self.jobs[current].get("id")
        
        self.table.setRowCount(len(jobs))
        
        for row, job in enumerate(jobs):
            # 名称
            self.table.setItem(row, 0, QTableWidgetItem(job.get("name", "")))
            
            # 插件
            self.table.setItem(row, 1, QTableWidgetItem(job.get("plugin", "")))
            
            # 状态
            status = job.get("status", "pending")
            status_item = QTableWidgetItem(STATUS_TEXT.get(status, status))
            status_item.setForeground(STATUS_COLORS.get(status, QColor(0, 0, 0)))
            self.table.setItem(row, 2, status_item)
            
            # 进度条
            progress = job.get("progress", 0)
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setValue(int(progress))
            progress_bar.setFormat(f"{progress:.1f}%")
            self.table.setCellWidget(row, 3, progress_bar)
            
            # 任务
            task_text = f"{job.get('task_completed', 0)}/{job.get('task_total', 0)}"
            self.table.setItem(row, 4, QTableWidgetItem(task_text))
            
            # 优先级
            self.table.setItem(row, 5, QTableWidgetItem(str(job.get("priority", 50))))
            
            # 提交时间
            submitted = job.get("submitted_at", "")
            if submitted:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(submitted.replace("Z", "+00:00"))
                    submitted = dt.strftime("%m-%d %H:%M:%S")
                except Exception:
                    pass
            self.table.setItem(row, 6, QTableWidgetItem(submitted))
            
            # ID (短格式)
            job_id = job.get("id", "")[:8]
            self.table.setItem(row, 7, QTableWidgetItem(job_id))
        
        # 恢复选中
        if selected_id:
            for row, job in enumerate(jobs):
                if job.get("id") == selected_id:
                    self.table.selectRow(row)
                    break
    
    def get_selected_job(self) -> dict | None:
        """获取选中的作业"""
        row = self.table.currentRow()
        if 0 <= row < len(self.jobs):
            return self.jobs[row]
        return None
    
    def _on_selection_changed(self):
        """选择改变"""
        job = self.get_selected_job()
        self.job_selected.emit(job or {})
