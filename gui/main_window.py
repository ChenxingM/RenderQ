"""
RenderQ GUI - 主窗口
"""
import json
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QToolBar, QStatusBar, QLabel,
    QMessageBox, QInputDialog, QSplitter, QTextEdit
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QAction, QIcon

import httpx

from .widgets.job_table import JobTableWidget
from .widgets.worker_table import WorkerTableWidget
from .widgets.submit_dialog import SubmitDialog
from .widgets.settings_dialog import SettingsDialog


class ApiWorker(QThread):
    """后台API请求线程"""
    finished = Signal(object)
    error = Signal(str)
    
    def __init__(self, method: str, url: str, **kwargs):
        super().__init__()
        self.method = method
        self.url = url
        self.kwargs = kwargs
        self.base_url = "http://localhost:8000"
    
    def run(self):
        try:
            with httpx.Client(base_url=self.base_url, timeout=10) as client:
                if self.method == "GET":
                    response = client.get(self.url, **self.kwargs)
                elif self.method == "POST":
                    response = client.post(self.url, **self.kwargs)
                elif self.method == "DELETE":
                    response = client.delete(self.url, **self.kwargs)
                elif self.method == "PUT":
                    response = client.put(self.url, **self.kwargs)
                else:
                    raise ValueError(f"Unknown method: {self.method}")
                
                response.raise_for_status()
                self.finished.emit(response.json() if response.content else None)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        
        self.server_url = "http://localhost:8000"
        self.api_workers = []  # 保持引用防止被GC
        
        self._setup_ui()
        self._setup_toolbar()
        self._setup_statusbar()
        self._setup_timer()
        
        # 初始加载
        self.refresh_all()
    
    def _setup_ui(self):
        """设置UI"""
        self.setWindowTitle("RenderQ - 渲染队列管理")
        self.setMinimumSize(1200, 700)
        
        # 中心widget
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # 主分割器
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)
        
        # 上部分 - Tab页
        self.tabs = QTabWidget()
        splitter.addWidget(self.tabs)
        
        # Jobs Tab
        self.job_table = JobTableWidget()
        self.job_table.job_selected.connect(self._on_job_selected)
        self.tabs.addTab(self.job_table, "作业队列")
        
        # Workers Tab
        self.worker_table = WorkerTableWidget()
        self.tabs.addTab(self.worker_table, "渲染节点")
        
        # 下部分 - 日志/详情
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setPlaceholderText("选择作业查看详情...")
        splitter.addWidget(self.log_text)
        
        splitter.setSizes([500, 150])
    
    def _setup_toolbar(self):
        """设置工具栏"""
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # 提交作业
        self.action_submit = QAction("提交作业", self)
        self.action_submit.setShortcut("Ctrl+N")
        self.action_submit.triggered.connect(self._on_submit)
        toolbar.addAction(self.action_submit)
        
        toolbar.addSeparator()
        
        # 刷新
        self.action_refresh = QAction("刷新", self)
        self.action_refresh.setShortcut("F5")
        self.action_refresh.triggered.connect(self.refresh_all)
        toolbar.addAction(self.action_refresh)
        
        toolbar.addSeparator()
        
        # 作业操作
        self.action_suspend = QAction("暂停", self)
        self.action_suspend.triggered.connect(self._on_suspend_job)
        toolbar.addAction(self.action_suspend)
        
        self.action_resume = QAction("恢复", self)
        self.action_resume.triggered.connect(self._on_resume_job)
        toolbar.addAction(self.action_resume)
        
        self.action_cancel = QAction("取消", self)
        self.action_cancel.triggered.connect(self._on_cancel_job)
        toolbar.addAction(self.action_cancel)
        
        self.action_retry = QAction("重试", self)
        self.action_retry.triggered.connect(self._on_retry_job)
        toolbar.addAction(self.action_retry)
        
        self.action_delete = QAction("删除", self)
        self.action_delete.triggered.connect(self._on_delete_job)
        toolbar.addAction(self.action_delete)
        
        toolbar.addSeparator()
        
        # 优先级
        self.action_priority = QAction("设置优先级", self)
        self.action_priority.triggered.connect(self._on_set_priority)
        toolbar.addAction(self.action_priority)
        
        # 弹性空间
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy(), 
                            spacer.sizePolicy().verticalPolicy())
        from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        
        # 设置
        self.action_settings = QAction("设置", self)
        self.action_settings.triggered.connect(self._on_settings)
        toolbar.addAction(self.action_settings)
    
    def _setup_statusbar(self):
        """设置状态栏"""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        
        self.status_label = QLabel("就绪")
        self.statusbar.addWidget(self.status_label)
        
        self.server_label = QLabel(f"服务器: {self.server_url}")
        self.statusbar.addPermanentWidget(self.server_label)
    
    def _setup_timer(self):
        """设置自动刷新定时器"""
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_all)
        self.refresh_timer.start(3000)  # 3秒刷新一次
    
    def refresh_all(self):
        """刷新所有数据"""
        self._fetch_jobs()
        self._fetch_workers()
    
    def _fetch_jobs(self):
        """获取作业列表"""
        worker = ApiWorker("GET", "/api/jobs", params={"limit": 200})
        worker.base_url = self.server_url
        worker.finished.connect(self._on_jobs_loaded)
        worker.error.connect(self._on_api_error)
        worker.start()
        self.api_workers.append(worker)
    
    def _fetch_workers(self):
        """获取Worker列表"""
        worker = ApiWorker("GET", "/api/workers")
        worker.base_url = self.server_url
        worker.finished.connect(self._on_workers_loaded)
        worker.error.connect(self._on_api_error)
        worker.start()
        self.api_workers.append(worker)
    
    def _on_jobs_loaded(self, data):
        """作业列表加载完成"""
        if data:
            self.job_table.set_jobs(data)
            
            # 更新Tab标题显示数量
            active = sum(1 for j in data if j.get("status") in ("pending", "queued", "active"))
            self.tabs.setTabText(0, f"作业队列 ({active})")
    
    def _on_workers_loaded(self, data):
        """Worker列表加载完成"""
        if data:
            self.worker_table.set_workers(data)
            
            # 更新Tab标题
            online = sum(1 for w in data if w.get("status") != "offline")
            self.tabs.setTabText(1, f"渲染节点 ({online})")
    
    def _on_api_error(self, error: str):
        """API错误"""
        self.status_label.setText(f"错误: {error}")
    
    def _on_job_selected(self, job: dict):
        """选中作业"""
        if job:
            info = [
                f"ID: {job.get('id', 'N/A')}",
                f"名称: {job.get('name', 'N/A')}",
                f"插件: {job.get('plugin', 'N/A')}",
                f"状态: {job.get('status', 'N/A')}",
                f"进度: {job.get('progress', 0):.1f}%",
                f"任务: {job.get('task_completed', 0)}/{job.get('task_total', 0)}",
                f"优先级: {job.get('priority', 50)}",
                "",
                "参数:",
                json.dumps(job.get('plugin_data', {}), indent=2, ensure_ascii=False),
            ]
            self.log_text.setText("\n".join(info))
    
    def _on_submit(self):
        """提交作业"""
        dialog = SubmitDialog(self.server_url, self)
        if dialog.exec():
            self.refresh_all()
            self.status_label.setText("作业已提交")
    
    def _on_suspend_job(self):
        """暂停作业"""
        job = self.job_table.get_selected_job()
        if not job:
            return
        
        worker = ApiWorker("POST", f"/api/jobs/{job['id']}/suspend")
        worker.base_url = self.server_url
        worker.finished.connect(lambda _: self.refresh_all())
        worker.error.connect(self._on_api_error)
        worker.start()
        self.api_workers.append(worker)
    
    def _on_resume_job(self):
        """恢复作业"""
        job = self.job_table.get_selected_job()
        if not job:
            return
        
        worker = ApiWorker("POST", f"/api/jobs/{job['id']}/resume")
        worker.base_url = self.server_url
        worker.finished.connect(lambda _: self.refresh_all())
        worker.error.connect(self._on_api_error)
        worker.start()
        self.api_workers.append(worker)
    
    def _on_cancel_job(self):
        """取消作业"""
        job = self.job_table.get_selected_job()
        if not job:
            return
        
        reply = QMessageBox.question(
            self, "确认", f"确定要取消作业 '{job['name']}' 吗?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        worker = ApiWorker("POST", f"/api/jobs/{job['id']}/cancel")
        worker.base_url = self.server_url
        worker.finished.connect(lambda _: self.refresh_all())
        worker.error.connect(self._on_api_error)
        worker.start()
        self.api_workers.append(worker)
    
    def _on_retry_job(self):
        """重试作业"""
        job = self.job_table.get_selected_job()
        if not job:
            return
        
        worker = ApiWorker("POST", f"/api/jobs/{job['id']}/retry")
        worker.base_url = self.server_url
        worker.finished.connect(lambda _: self.refresh_all())
        worker.error.connect(self._on_api_error)
        worker.start()
        self.api_workers.append(worker)
    
    def _on_delete_job(self):
        """删除作业"""
        job = self.job_table.get_selected_job()
        if not job:
            return
        
        if job.get("status") not in ("completed", "cancelled", "failed"):
            QMessageBox.warning(self, "警告", "只能删除已完成/已取消/已失败的作业")
            return
        
        reply = QMessageBox.question(
            self, "确认", f"确定要删除作业 '{job['name']}' 吗?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        worker = ApiWorker("DELETE", f"/api/jobs/{job['id']}")
        worker.base_url = self.server_url
        worker.finished.connect(lambda _: self.refresh_all())
        worker.error.connect(self._on_api_error)
        worker.start()
        self.api_workers.append(worker)
    
    def _on_set_priority(self):
        """设置优先级"""
        job = self.job_table.get_selected_job()
        if not job:
            return
        
        current = job.get("priority", 50)
        value, ok = QInputDialog.getInt(
            self, "设置优先级", "优先级 (0-100):",
            current, 0, 100
        )
        if not ok:
            return
        
        worker = ApiWorker("PUT", f"/api/jobs/{job['id']}/priority", params={"priority": value})
        worker.base_url = self.server_url
        worker.finished.connect(lambda _: self.refresh_all())
        worker.error.connect(self._on_api_error)
        worker.start()
        self.api_workers.append(worker)
    
    def _on_settings(self):
        """打开设置"""
        dialog = SettingsDialog(self.server_url, self)
        if dialog.exec():
            self.server_url = dialog.get_server_url()
            self.server_label.setText(f"服务器: {self.server_url}")
            self.refresh_all()
    
    def closeEvent(self, event):
        """窗口关闭"""
        self.refresh_timer.stop()
        super().closeEvent(event)
