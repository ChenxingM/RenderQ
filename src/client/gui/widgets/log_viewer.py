"""
RenderQ GUI - Log Viewer Dialog
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QCheckBox, QComboBox, QLineEdit
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QTextCursor, QColor, QTextCharFormat

import httpx


class LogViewer(QDialog):
    """Task Log Viewer"""

    def __init__(self, server_url: str, task_id: str, task_info: dict = None, parent=None):
        super().__init__(parent)
        self.server_url = server_url
        self.task_id = task_id
        self.task_info = task_info or {}
        self.auto_scroll = True
        self.auto_refresh = True
        self.last_line_count = 0
        self.current_progress = 0.0
        self.current_frame = 0

        self._setup_ui()
        self._setup_timer()
        self._fetch_log()

    def _setup_ui(self):
        self.setWindowTitle(f"Task Log - {self.task_id[:8]}...")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)

        layout = QVBoxLayout(self)

        # Header info
        header = QHBoxLayout()

        frame_info = ""
        frame_start = self.task_info.get("frame_start")
        frame_end = self.task_info.get("frame_end")
        if frame_start is not None and frame_end is not None:
            total_frames = frame_end - frame_start + 1
            frame_info = f" | Frames: {frame_start}-{frame_end} ({total_frames}f)"

        worker = self.task_info.get("assigned_worker", "N/A")
        if len(worker) > 20:
            worker = worker[:20] + "..."

        info_label = QLabel(f"Task: {self.task_id[:16]}...{frame_info} | Worker: {worker}")
        info_label.setStyleSheet("color: #888; padding: 4px;")
        header.addWidget(info_label)

        header.addStretch()

        # Auto refresh checkbox
        self.auto_refresh_cb = QCheckBox("Auto Refresh")
        self.auto_refresh_cb.setChecked(True)
        self.auto_refresh_cb.toggled.connect(self._on_auto_refresh_toggled)
        header.addWidget(self.auto_refresh_cb)

        # Auto scroll checkbox
        self.auto_scroll_cb = QCheckBox("Auto Scroll")
        self.auto_scroll_cb.setChecked(True)
        self.auto_scroll_cb.toggled.connect(lambda checked: setattr(self, 'auto_scroll', checked))
        header.addWidget(self.auto_scroll_cb)

        layout.addLayout(header)

        # Progress panel (for aerender)
        from PySide6.QtWidgets import QProgressBar, QFrame
        progress_frame = QFrame()
        progress_frame.setStyleSheet("QFrame { background: #2a2a2a; border-radius: 4px; padding: 8px; }")
        progress_layout = QHBoxLayout(progress_frame)
        progress_layout.setContentsMargins(10, 5, 10, 5)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background-color: #333; border: none; border-radius: 4px; height: 20px; }
            QProgressBar::chunk { background-color: #FF9800; border-radius: 4px; }
        """)
        progress_layout.addWidget(self.progress_bar, 1)

        self.progress_label = QLabel("Progress: 0% | Frame: - | ETA: -")
        self.progress_label.setStyleSheet("color: #ccc; padding-left: 10px; min-width: 200px;")
        progress_layout.addWidget(self.progress_label)

        layout.addWidget(progress_frame)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.log_text)

        # Search bar
        search_layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search...")
        self.search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self.search_input)

        self.search_btn = QPushButton("Find")
        self.search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(self.search_btn)

        self.clear_btn = QPushButton("Clear Highlight")
        self.clear_btn.clicked.connect(self._clear_highlight)
        search_layout.addWidget(self.clear_btn)

        layout.addLayout(search_layout)

        # Buttons
        btn_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._fetch_log)
        btn_layout.addWidget(self.refresh_btn)

        btn_layout.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

    def _setup_timer(self):
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._fetch_log)
        self.refresh_timer.start(2000)  # 2 seconds

    def _on_auto_refresh_toggled(self, checked):
        self.auto_refresh = checked
        if checked:
            self.refresh_timer.start(2000)
        else:
            self.refresh_timer.stop()

    def _fetch_log(self):
        try:
            with httpx.Client(base_url=self.server_url, timeout=5) as client:
                response = client.get(f"/api/tasks/{self.task_id}/log")
                if response.status_code == 200:
                    data = response.json()
                    log_content = data.get("log", "")
                    self._update_log(log_content)
                elif response.status_code == 404:
                    self.log_text.setPlainText("Log not found")
        except Exception as e:
            pass  # Silently fail for auto-refresh

    def _update_log(self, content: str):
        lines = content.split('\n')
        new_line_count = len(lines)

        if new_line_count != self.last_line_count:
            self.last_line_count = new_line_count

            # Save scroll position
            scrollbar = self.log_text.verticalScrollBar()
            was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10

            self.log_text.setPlainText(content)

            # Restore or auto-scroll
            if self.auto_scroll or was_at_bottom:
                scrollbar.setValue(scrollbar.maximum())

        # Parse aerender progress from log
        self._parse_aerender_progress(content)

    def _parse_aerender_progress(self, content: str):
        """Parse aerender output for progress information"""
        import re

        # Get frame range
        frame_start = self.task_info.get("frame_start", 0)
        frame_end = self.task_info.get("frame_end")

        if frame_end is None:
            # Try to parse from log
            match = re.search(r'Start Frame:\s*(\d+)', content)
            if match:
                frame_start = int(match.group(1))
            match = re.search(r'End Frame:\s*(\d+)', content)
            if match:
                frame_end = int(match.group(1))

        if frame_end is None:
            self.progress_label.setText("Progress: - | Waiting for frame info...")
            return

        total_frames = frame_end - frame_start + 1

        # Parse current frame from PROGRESS lines
        # Format: "PROGRESS:  0:00:01:15 (101): 0 Seconds"
        progress_matches = re.findall(r'PROGRESS:.*\((\d+)\)', content)
        if progress_matches:
            current_frame = int(progress_matches[-1])  # Get the last progress
            self.current_frame = current_frame

            if total_frames > 0:
                progress = min(100.0, (current_frame - frame_start + 1) / total_frames * 100)
                self.current_progress = progress
                self.progress_bar.setValue(int(progress))

                remaining_frames = frame_end - current_frame
                self.progress_label.setText(
                    f"Progress: {progress:.1f}% | Frame: {current_frame}/{frame_end} | Remaining: {remaining_frames}f"
                )

        # Check for completion
        if "PROGRESS: Total Time Elapsed" in content:
            self.progress_bar.setValue(100)
            self.progress_bar.setStyleSheet("""
                QProgressBar { background-color: #333; border: none; border-radius: 4px; height: 20px; }
                QProgressBar::chunk { background-color: #4CAF50; border-radius: 4px; }
            """)

            # Parse elapsed time
            time_match = re.search(r'Total Time Elapsed:\s*(\d+:\d+:\d+)', content)
            if time_match:
                self.progress_label.setText(f"Completed | Total time: {time_match.group(1)}")
            else:
                self.progress_label.setText("Completed")

        # Check for errors
        if "ERROR:" in content or "RENDER ERROR" in content:
            self.progress_bar.setStyleSheet("""
                QProgressBar { background-color: #333; border: none; border-radius: 4px; height: 20px; }
                QProgressBar::chunk { background-color: #F44336; border-radius: 4px; }
            """)

    def _on_search(self):
        search_text = self.search_input.text()
        if not search_text:
            return

        self._clear_highlight()

        # Highlight all occurrences
        cursor = self.log_text.textCursor()
        format = QTextCharFormat()
        format.setBackground(QColor("#5a5a00"))

        cursor.beginEditBlock()

        doc = self.log_text.document()
        cursor = doc.find(search_text)

        while not cursor.isNull():
            cursor.mergeCharFormat(format)
            cursor = doc.find(search_text, cursor)

        cursor.endEditBlock()

    def _clear_highlight(self):
        cursor = self.log_text.textCursor()
        cursor.select(QTextCursor.Document)
        format = QTextCharFormat()
        format.setBackground(QColor("transparent"))
        cursor.mergeCharFormat(format)

    def closeEvent(self, event):
        self.refresh_timer.stop()
        super().closeEvent(event)


class WorkerLogViewer(QDialog):
    """Worker Real-time Log Viewer (WebSocket connection)"""

    def __init__(self, server_url: str, worker_id: str, worker_info: dict = None, parent=None):
        super().__init__(parent)
        self.server_url = server_url
        self.worker_id = worker_id
        self.worker_info = worker_info or {}
        self.auto_scroll = True

        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self):
        worker_name = self.worker_info.get("name", self.worker_id[:8])
        self.setWindowTitle(f"Worker Log - {worker_name}")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)

        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()

        info_label = QLabel(
            f"Worker: {worker_name} | "
            f"IP: {self.worker_info.get('ip_address', 'N/A')} | "
            f"Status: {self.worker_info.get('status', 'N/A')}"
        )
        info_label.setStyleSheet("color: #888; padding: 4px;")
        header.addWidget(info_label)

        header.addStretch()

        self.auto_scroll_cb = QCheckBox("Auto Scroll")
        self.auto_scroll_cb.setChecked(True)
        self.auto_scroll_cb.toggled.connect(lambda checked: setattr(self, 'auto_scroll', checked))
        header.addWidget(self.auto_scroll_cb)

        layout.addLayout(header)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.log_text)

        # Status
        status_layout = QHBoxLayout()

        self.status_label = QLabel("Connecting...")
        self.status_label.setStyleSheet("color: #888;")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(lambda: self.log_text.clear())
        status_layout.addWidget(self.clear_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        status_layout.addWidget(self.close_btn)

        layout.addLayout(status_layout)

    def _setup_timer(self):
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._fetch_worker_log)
        self.refresh_timer.start(1000)
        self._fetch_worker_log()

    def _fetch_worker_log(self):
        try:
            with httpx.Client(base_url=self.server_url, timeout=5) as client:
                response = client.get(f"/api/workers/{self.worker_id}/log")
                if response.status_code == 200:
                    data = response.json()
                    self._append_log(data.get("log", ""))
                    self.status_label.setText(f"Connected - Task: {data.get('current_task', 'None')}")
                else:
                    self.status_label.setText("Worker not available")
        except Exception as e:
            self.status_label.setText(f"Connection error: {str(e)[:30]}")

    def _append_log(self, content: str):
        if not content:
            return

        scrollbar = self.log_text.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10

        current = self.log_text.toPlainText()
        if content != current:
            self.log_text.setPlainText(content)

            if self.auto_scroll or was_at_bottom:
                scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event):
        self.refresh_timer.stop()
        super().closeEvent(event)
