"""
RenderQ GUI - Worker表格组件
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QAbstractItemView, QMenu
)
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QColor, QAction, QCursor


STATUS_COLORS = {
    "idle": QColor(50, 205, 50),           # 绿色 - 空闲
    "busy": QColor(255, 165, 0),           # 橙色 - 忙碌
    "offline": QColor(128, 128, 128),      # 灰色 - 离线
    "disabled": QColor(220, 20, 60),       # 红色 - 禁用
}

STATUS_TEXT = {
    "idle": "空闲",
    "busy": "忙碌",
    "offline": "离线",
    "disabled": "禁用",
}


def format_bytes(size: int) -> str:
    """格式化字节大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


class WorkerTableWidget(QWidget):
    """Worker表格"""

    worker_selected = Signal(dict)
    worker_action = Signal(str, dict)  # action_name, worker

    def __init__(self, parent=None):
        super().__init__(parent)

        self.workers = []
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "名称", "状态", "当前任务", "CPU", "内存", "核心数", "IP", "最后心跳"
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
        
        self.table.setColumnWidth(1, 60)    # 状态
        self.table.setColumnWidth(2, 120)   # 当前任务
        self.table.setColumnWidth(3, 80)    # CPU
        self.table.setColumnWidth(4, 120)   # 内存
        self.table.setColumnWidth(5, 60)    # 核心数
        self.table.setColumnWidth(6, 120)   # IP
        self.table.setColumnWidth(7, 140)   # 最后心跳
        
        # 选择行为
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        # Context menu
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

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
                return True
        return super().eventFilter(obj, event)

    def _show_context_menu(self, pos):
        """Show context menu for worker"""
        index = self.table.indexAt(pos)
        if not index.isValid():
            return

        worker = self.workers[index.row()]
        status = worker.get("status", "offline")

        menu = QMenu(self)

        # Connect to Worker Log
        connect_log_action = QAction("Connect to Log", self)
        connect_log_action.triggered.connect(lambda: self.worker_action.emit("connect_log", worker))
        menu.addAction(connect_log_action)

        menu.addSeparator()

        # Enable/Disable
        if status == "disabled":
            enable_action = QAction("Enable Worker", self)
            enable_action.triggered.connect(lambda: self.worker_action.emit("enable", worker))
            menu.addAction(enable_action)
        elif status in ("idle", "busy"):
            disable_action = QAction("Disable Worker", self)
            disable_action.triggered.connect(lambda: self.worker_action.emit("disable", worker))
            menu.addAction(disable_action)

        # Delete offline worker
        if status == "offline":
            delete_action = QAction("Delete Worker", self)
            delete_action.triggered.connect(lambda: self.worker_action.emit("delete", worker))
            menu.addAction(delete_action)

        menu.exec_(QCursor.pos())
    
    def set_workers(self, workers: list):
        """设置Worker列表"""
        self.workers = workers
        
        self.table.setRowCount(len(workers))
        
        for row, worker in enumerate(workers):
            # 名称
            name_item = QTableWidgetItem(worker.get("name", ""))
            self.table.setItem(row, 0, name_item)
            
            # 状态
            status = worker.get("status", "offline")
            status_item = QTableWidgetItem(STATUS_TEXT.get(status, status))
            status_item.setForeground(STATUS_COLORS.get(status, QColor(0, 0, 0)))
            self.table.setItem(row, 1, status_item)
            
            # 当前任务
            current_task = worker.get("current_task", "")
            if current_task:
                current_task = current_task[:8] + "..."
            self.table.setItem(row, 2, QTableWidgetItem(current_task or "-"))
            
            # CPU
            cpu_usage = worker.get("cpu_usage", 0)
            cpu_bar = QProgressBar()
            cpu_bar.setRange(0, 100)
            cpu_bar.setValue(int(cpu_usage))
            cpu_bar.setFormat(f"{cpu_usage:.0f}%")
            self.table.setCellWidget(row, 3, cpu_bar)
            
            # 内存
            mem_used = worker.get("memory_used", 0)
            mem_total = worker.get("memory_total", 0)
            if mem_total > 0:
                mem_text = f"{format_bytes(mem_used)} / {format_bytes(mem_total)}"
            else:
                mem_text = "-"
            self.table.setItem(row, 4, QTableWidgetItem(mem_text))
            
            # 核心数
            cores = worker.get("cpu_cores", 0)
            self.table.setItem(row, 5, QTableWidgetItem(str(cores) if cores else "-"))
            
            # IP
            ip = worker.get("ip_address", "")
            self.table.setItem(row, 6, QTableWidgetItem(ip or "-"))
            
            # 最后心跳
            heartbeat = worker.get("last_heartbeat", "")
            if heartbeat:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))
                    heartbeat = dt.strftime("%m-%d %H:%M:%S")
                except Exception:
                    pass
            self.table.setItem(row, 7, QTableWidgetItem(heartbeat or "-"))
    
    def get_selected_worker(self) -> dict | None:
        """获取选中的Worker"""
        row = self.table.currentRow()
        if 0 <= row < len(self.workers):
            return self.workers[row]
        return None
    
    def _on_selection_changed(self):
        """选择改变"""
        worker = self.get_selected_worker()
        self.worker_selected.emit(worker or {})
