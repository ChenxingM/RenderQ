"""
RenderQ GUI - 提交作业对话框
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QComboBox, QPushButton,
    QFileDialog, QGroupBox, QMessageBox, QCheckBox,
    QDialogButtonBox, QWidget
)
from PySide6.QtCore import Qt

import httpx


class SubmitDialog(QDialog):
    """提交作业对话框"""
    
    def __init__(self, server_url: str, parent=None):
        super().__init__(parent)
        
        self.server_url = server_url
        self.plugins = []
        
        self._setup_ui()
        self._load_plugins()
    
    def _setup_ui(self):
        self.setWindowTitle("提交渲染作业")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        # 基本信息
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("作业名称")
        basic_layout.addRow("名称:", self.name_edit)
        
        self.plugin_combo = QComboBox()
        self.plugin_combo.currentIndexChanged.connect(self._on_plugin_changed)
        basic_layout.addRow("插件:", self.plugin_combo)
        
        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(0, 100)
        self.priority_spin.setValue(50)
        basic_layout.addRow("优先级:", self.priority_spin)
        
        self.pool_edit = QLineEdit()
        self.pool_edit.setText("default")
        basic_layout.addRow("Worker池:", self.pool_edit)
        
        layout.addWidget(basic_group)
        
        # 插件参数 (动态生成)
        self.params_group = QGroupBox("渲染参数")
        self.params_layout = QFormLayout(self.params_group)
        layout.addWidget(self.params_group)
        
        # 参数控件字典
        self.param_widgets = {}
        
        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _load_plugins(self):
        """加载可用插件"""
        try:
            with httpx.Client(base_url=self.server_url, timeout=5) as client:
                response = client.get("/api/plugins")
                response.raise_for_status()
                self.plugins = response.json()
                
                self.plugin_combo.clear()
                for plugin in self.plugins:
                    self.plugin_combo.addItem(
                        plugin.get("display_name", plugin.get("name")),
                        plugin.get("name")
                    )
        except Exception as e:
            QMessageBox.warning(self, "警告", f"无法加载插件列表: {e}")
    
    def _on_plugin_changed(self, index: int):
        """插件选择改变"""
        if index < 0 or index >= len(self.plugins):
            return
        
        plugin = self.plugins[index]
        self._build_param_form(plugin.get("parameters", {}))
    
    def _build_param_form(self, parameters: dict):
        """根据插件参数构建表单"""
        # 清除旧的控件
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.param_widgets.clear()
        
        # 创建新控件
        for name, param in parameters.items():
            param_type = param.get("type", "string")
            label = param.get("label", name)
            required = param.get("required", False)
            default = param.get("default")
            description = param.get("description", "")
            
            if required:
                label = f"{label} *"
            
            widget = None
            
            if param_type == "string":
                widget = QLineEdit()
                if default:
                    widget.setText(str(default))
                if description:
                    widget.setPlaceholderText(description)
            
            elif param_type == "int":
                widget = QSpinBox()
                widget.setRange(-999999, 999999)
                if default is not None:
                    widget.setValue(int(default))
            
            elif param_type == "float":
                from PySide6.QtWidgets import QDoubleSpinBox
                widget = QDoubleSpinBox()
                widget.setRange(-999999, 999999)
                widget.setDecimals(2)
                if default is not None:
                    widget.setValue(float(default))
            
            elif param_type == "bool":
                widget = QCheckBox()
                if default:
                    widget.setChecked(bool(default))
            
            elif param_type == "path":
                container = QWidget()
                h_layout = QHBoxLayout(container)
                h_layout.setContentsMargins(0, 0, 0, 0)
                
                path_edit = QLineEdit()
                if default:
                    path_edit.setText(str(default))
                if description:
                    path_edit.setPlaceholderText(description)
                h_layout.addWidget(path_edit)
                
                browse_btn = QPushButton("...")
                browse_btn.setFixedWidth(30)
                
                # 判断是保存还是打开
                is_save = param.get("save", False)
                file_filter = param.get("filter", "All Files (*.*)")
                
                def make_browse_handler(edit, save, flt):
                    def handler():
                        if save:
                            path, _ = QFileDialog.getSaveFileName(self, "选择保存路径", "", flt)
                        else:
                            path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", flt)
                        if path:
                            edit.setText(path)
                    return handler
                
                browse_btn.clicked.connect(make_browse_handler(path_edit, is_save, file_filter))
                h_layout.addWidget(browse_btn)
                
                widget = container
                # 保存对path_edit的引用
                widget._path_edit = path_edit
            
            elif param_type == "choice":
                widget = QComboBox()
                choices = param.get("choices", [])
                for choice in choices:
                    widget.addItem(str(choice), choice)
                if default is not None:
                    idx = widget.findData(default)
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
            
            if widget:
                self.params_layout.addRow(f"{label}:", widget)
                self.param_widgets[name] = {
                    "widget": widget,
                    "type": param_type,
                    "required": required,
                }
    
    def _get_plugin_data(self) -> dict:
        """获取插件参数"""
        data = {}
        
        for name, info in self.param_widgets.items():
            widget = info["widget"]
            param_type = info["type"]
            
            value = None
            
            if param_type == "string":
                value = widget.text().strip() or None
            elif param_type == "int":
                value = widget.value()
            elif param_type == "float":
                value = widget.value()
            elif param_type == "bool":
                value = widget.isChecked()
            elif param_type == "path":
                value = widget._path_edit.text().strip() or None
            elif param_type == "choice":
                value = widget.currentData()
            
            if value is not None:
                data[name] = value
        
        return data
    
    def _validate(self) -> tuple[bool, str]:
        """验证输入"""
        if not self.name_edit.text().strip():
            return False, "请输入作业名称"
        
        if self.plugin_combo.currentIndex() < 0:
            return False, "请选择渲染插件"
        
        # 验证必需参数
        for name, info in self.param_widgets.items():
            if info["required"]:
                widget = info["widget"]
                param_type = info["type"]
                
                empty = False
                if param_type == "string":
                    empty = not widget.text().strip()
                elif param_type == "path":
                    empty = not widget._path_edit.text().strip()
                
                if empty:
                    return False, f"请填写必需参数: {name}"
        
        return True, ""
    
    def _on_submit(self):
        """提交作业"""
        valid, error = self._validate()
        if not valid:
            QMessageBox.warning(self, "验证失败", error)
            return
        
        job_data = {
            "name": self.name_edit.text().strip(),
            "plugin": self.plugin_combo.currentData(),
            "priority": self.priority_spin.value(),
            "pool": self.pool_edit.text().strip() or "default",
            "plugin_data": self._get_plugin_data(),
        }
        
        try:
            with httpx.Client(base_url=self.server_url, timeout=10) as client:
                response = client.post("/api/jobs", json=job_data)
                response.raise_for_status()
                
                result = response.json()
                QMessageBox.information(
                    self, "成功",
                    f"作业已提交\nID: {result.get('id', 'N/A')}"
                )
                self.accept()
                
        except httpx.HTTPStatusError as e:
            QMessageBox.critical(
                self, "提交失败",
                f"服务器返回错误: {e.response.status_code}\n{e.response.text}"
            )
        except Exception as e:
            QMessageBox.critical(self, "提交失败", str(e))
