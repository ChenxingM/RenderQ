"""
RenderQ GUI - 主窗口
"""
import json
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QStatusBar, QLabel,
    QMessageBox, QInputDialog, QSplitter, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QAction

import httpx

from .widgets.job_table import JobTableWidget
from .widgets.worker_table import WorkerTableWidget
from .widgets.task_table import TaskTableWidget
from .widgets.submit_dialog import SubmitDialog
from .widgets.settings_dialog import SettingsDialog
from .widgets.log_viewer import LogViewer, WorkerLogViewer


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
        self._current_job = None
        self._log_dialogs = []  # Keep log dialogs alive

        self._setup_ui()
        self._setup_toolbar()
        self._setup_statusbar()
        self._setup_timer()

        # 初始加载
        self.refresh_all()

    def _setup_ui(self):
        """设置UI"""
        self.setWindowTitle("RenderQ - 渲染队列管理")
        self.setMinimumSize(1200, 800)

        # 中心widget
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 主分割器 (上下)
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(main_splitter)

        # ===== 上部分: 作业队列 (Job + Task) =====
        job_section = QWidget()
        job_layout = QVBoxLayout(job_section)
        job_layout.setContentsMargins(0, 0, 0, 0)
        job_layout.setSpacing(4)

        # 作业队列标题
        job_header = QLabel("作业队列")
        job_header.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px;")
        job_layout.addWidget(job_header)

        # Job和Task的水平分割器
        job_splitter = QSplitter(Qt.Orientation.Horizontal)
        job_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        job_layout.addWidget(job_splitter, 1)  # stretch factor 1

        # 左侧: Job列表
        self.job_table = JobTableWidget()
        self.job_table.job_selected.connect(self._on_job_selected)
        job_splitter.addWidget(self.job_table)

        # 右侧: Task列表
        self.task_table = TaskTableWidget()
        self.task_table.task_action.connect(self._on_task_action)
        job_splitter.addWidget(self.task_table)

        # 设置分割比例
        job_splitter.setSizes([500, 500])

        main_splitter.addWidget(job_section)

        # ===== 下部分: 渲染节点 =====
        worker_section = QWidget()
        worker_layout = QVBoxLayout(worker_section)
        worker_layout.setContentsMargins(0, 0, 0, 0)
        worker_layout.setSpacing(4)

        # 渲染节点标题
        worker_header = QLabel("渲染节点")
        worker_header.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px;")
        worker_layout.addWidget(worker_header)

        # Worker表格
        self.worker_table = WorkerTableWidget()
        self.worker_table.worker_action.connect(self._on_worker_action)
        worker_layout.addWidget(self.worker_table, 1)  # stretch factor 1

        main_splitter.addWidget(worker_section)

        # 设置上下分割比例 (作业队列占更多空间)
        main_splitter.setSizes([550, 250])

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
        # 如果有选中的Job，刷新其Tasks
        if self._current_job:
            self._fetch_tasks(self._current_job.get("id"))

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

    def _fetch_tasks(self, job_id: str):
        """获取Job的Task列表"""
        worker = ApiWorker("GET", f"/api/jobs/{job_id}/tasks")
        worker.base_url = self.server_url
        worker.finished.connect(self._on_tasks_loaded)
        worker.error.connect(self._on_tasks_error)
        worker.start()
        self.api_workers.append(worker)

    def _on_jobs_loaded(self, data):
        """作业列表加载完成"""
        if data:
            self.job_table.set_jobs(data)

            # 更新当前选中的Job数据
            if self._current_job:
                for job in data:
                    if job.get("id") == self._current_job.get("id"):
                        self._current_job = job
                        break

    def _on_workers_loaded(self, data):
        """Worker列表加载完成"""
        if data:
            self.worker_table.set_workers(data)

    def _on_tasks_loaded(self, data):
        """Task列表加载完成"""
        if data is not None:
            self.task_table.set_tasks(data)

    def _on_tasks_error(self, error: str):
        """Task加载错误 (Job可能已删除)"""
        self.task_table.clear()
        # 如果是404错误，清除当前选中的Job
        if "404" in error:
            self._current_job = None

    def _on_api_error(self, error: str):
        """API错误"""
        self.status_label.setText(f"错误: {error}")

    def _on_job_selected(self, job: dict):
        """选中作业"""
        self._current_job = job if job else None
        if job:
            # 设置Task表格标题并获取Tasks
            self.task_table.set_job(job.get("id"), job.get("name"))
            self._fetch_tasks(job.get("id"))

            # 更新状态栏
            status = job.get("status", "unknown")
            progress = job.get("progress", 0)
            self.status_label.setText(
                f"已选择: {job.get('name')} | 状态: {status} | 进度: {progress:.1f}%"
            )
        else:
            self.task_table.clear()
            self.status_label.setText("就绪")

    def _on_task_action(self, action: str, task: dict):
        """Handle task context menu actions"""
        task_id = task.get("id")
        if not task_id:
            return

        if action == "view_log":
            dialog = LogViewer(self.server_url, task_id, task, self)
            dialog.show()
            self._log_dialogs.append(dialog)

        elif action == "worker_log":
            worker_id = task.get("assigned_worker")
            if worker_id:
                dialog = WorkerLogViewer(self.server_url, worker_id, {"id": worker_id}, self)
                dialog.show()
                self._log_dialogs.append(dialog)

        elif action == "retry":
            worker = ApiWorker("POST", f"/api/tasks/{task_id}/retry")
            worker.base_url = self.server_url
            worker.finished.connect(lambda _: self.refresh_all())
            worker.error.connect(self._on_api_error)
            worker.start()
            self.api_workers.append(worker)

        elif action == "cancel":
            worker = ApiWorker("POST", f"/api/tasks/{task_id}/cancel")
            worker.base_url = self.server_url
            worker.finished.connect(lambda _: self.refresh_all())
            worker.error.connect(self._on_api_error)
            worker.start()
            self.api_workers.append(worker)

        elif action == "suspend":
            worker = ApiWorker("POST", f"/api/tasks/{task_id}/suspend")
            worker.base_url = self.server_url
            worker.finished.connect(lambda _: self.refresh_all())
            worker.error.connect(self._on_api_error)
            worker.start()
            self.api_workers.append(worker)

    def _on_worker_action(self, action: str, worker_data: dict):
        """Handle worker context menu actions"""
        worker_id = worker_data.get("id")
        if not worker_id:
            return

        if action == "connect_log":
            dialog = WorkerLogViewer(self.server_url, worker_id, worker_data, self)
            dialog.show()
            self._log_dialogs.append(dialog)

        elif action == "enable":
            worker = ApiWorker("POST", f"/api/workers/{worker_id}/enable")
            worker.base_url = self.server_url
            worker.finished.connect(lambda _: self.refresh_all())
            worker.error.connect(self._on_api_error)
            worker.start()
            self.api_workers.append(worker)

        elif action == "disable":
            worker = ApiWorker("POST", f"/api/workers/{worker_id}/disable")
            worker.base_url = self.server_url
            worker.finished.connect(lambda _: self.refresh_all())
            worker.error.connect(self._on_api_error)
            worker.start()
            self.api_workers.append(worker)

        elif action == "delete":
            reply = QMessageBox.question(
                self, "确认", f"确定要删除Worker '{worker_data.get('name', worker_id)}'吗?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                worker = ApiWorker("DELETE", f"/api/workers/{worker_id}")
                worker.base_url = self.server_url
                worker.finished.connect(lambda _: self.refresh_all())
                worker.error.connect(self._on_api_error)
                worker.start()
                self.api_workers.append(worker)

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
        # Close all log dialogs
        for dialog in self._log_dialogs:
            try:
                dialog.close()
            except:
                pass
        super().closeEvent(event)
