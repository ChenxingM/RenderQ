"""
RenderQ GUI - 设置对话框
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout,
    QLineEdit, QDialogButtonBox, QGroupBox,
    QSpinBox, QCheckBox
)


class SettingsDialog(QDialog):
    """设置对话框"""
    
    def __init__(self, current_server_url: str, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("设置")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # 服务器设置
        server_group = QGroupBox("服务器")
        server_layout = QFormLayout(server_group)
        
        self.server_url_edit = QLineEdit()
        self.server_url_edit.setText(current_server_url)
        self.server_url_edit.setPlaceholderText("http://localhost:8000")
        server_layout.addRow("服务器地址:", self.server_url_edit)
        
        layout.addWidget(server_group)
        
        # 界面设置
        ui_group = QGroupBox("界面")
        ui_layout = QFormLayout(ui_group)
        
        self.refresh_interval_spin = QSpinBox()
        self.refresh_interval_spin.setRange(1, 60)
        self.refresh_interval_spin.setValue(3)
        self.refresh_interval_spin.setSuffix(" 秒")
        ui_layout.addRow("刷新间隔:", self.refresh_interval_spin)
        
        self.auto_scroll_check = QCheckBox("自动滚动到新作业")
        self.auto_scroll_check.setChecked(True)
        ui_layout.addRow("", self.auto_scroll_check)
        
        layout.addWidget(ui_group)
        
        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_server_url(self) -> str:
        """获取服务器URL"""
        return self.server_url_edit.text().strip() or "http://localhost:8000"
    
    def get_refresh_interval(self) -> int:
        """获取刷新间隔(秒)"""
        return self.refresh_interval_spin.value()
