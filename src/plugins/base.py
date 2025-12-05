"""
RenderQ - 渲染插件基类
"""
from abc import ABC, abstractmethod
from typing import Any
import re

from src.core.models import Job, Task


class RenderPlugin(ABC):
    """渲染插件基类 - 所有渲染器插件必须继承此类"""
    
    # 插件标识符 (唯一)
    name: str = ""
    
    # 显示名称
    display_name: str = ""
    
    # 版本
    version: str = "1.0.0"
    
    # 描述
    description: str = ""
    
    # 插件参数定义 (用于UI生成表单)
    # 格式: {
    #     "param_name": {
    #         "type": "string" | "int" | "float" | "bool" | "path" | "choice",
    #         "label": "显示名称",
    #         "required": True | False,
    #         "default": 默认值,
    #         "choices": ["a", "b"],  # 仅type=choice时
    #         "description": "参数描述",
    #     }
    # }
    parameters: dict[str, dict[str, Any]] = {}
    
    @abstractmethod
    def validate(self, plugin_data: dict) -> tuple[bool, str | None]:
        """
        验证plugin_data是否合法
        
        Returns:
            (True, None) 如果验证通过
            (False, "错误信息") 如果验证失败
        """
        pass
    
    @abstractmethod
    def create_tasks(self, job: Job) -> list[Task]:
        """
        根据Job创建Task列表
        
        - 如果不需要分块，返回单个Task的列表
        - 如果需要分块(如按帧范围)，返回多个Task
        
        Returns:
            Task列表 (command字段可以为空，build_command会填充)
        """
        pass
    
    @abstractmethod
    def build_command(self, task: Task, job: Job) -> list[str]:
        """
        构建Task的执行命令
        
        Returns:
            命令行参数列表，如 ["aerender.exe", "-project", "xxx.aep", ...]
        """
        pass
    
    def parse_progress(self, output_line: str, task: Task) -> float | None:
        """
        解析渲染器输出，提取进度
        
        Args:
            output_line: 渲染器stdout的一行输出
            task: 当前执行的Task
        
        Returns:
            进度值(0-100)，或None表示该行不包含进度信息
        """
        return None
    
    def on_task_start(self, task: Task, job: Job):
        """Task开始执行时的回调 (可选覆写)"""
        pass
    
    def on_task_complete(self, task: Task, job: Job):
        """Task完成时的回调 (可选覆写)"""
        pass
    
    def on_task_fail(self, task: Task, job: Job, error: str):
        """Task失败时的回调 (可选覆写)"""
        pass
    
    def on_job_complete(self, job: Job):
        """Job完成时的回调 (可选覆写) - 用于合并分块等后处理"""
        pass
    
    def get_info(self) -> dict:
        """获取插件信息"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "version": self.version,
            "description": self.description,
            "parameters": self.parameters,
        }


class CommandLinePlugin(RenderPlugin):
    """命令行渲染器插件基类 - 简化常见模式"""
    
    # 默认可执行文件路径列表 (按优先级)
    default_executable_paths: list[str] = []
    
    def find_executable(self, custom_path: str = None) -> str:
        """查找可执行文件"""
        import os
        
        # 优先使用自定义路径
        if custom_path and os.path.exists(custom_path):
            return custom_path
        
        # 搜索默认路径
        for path in self.default_executable_paths:
            if os.path.exists(path):
                return path
        
        raise FileNotFoundError(f"Cannot find executable for {self.name}")
    
    def create_tasks(self, job: Job) -> list[Task]:
        """默认实现：创建单个Task"""
        return [Task(job_id=job.id, index=0)]
    
    def _validate_required(self, plugin_data: dict, *keys) -> tuple[bool, str | None]:
        """验证必需参数"""
        for key in keys:
            if not plugin_data.get(key):
                label = self.parameters.get(key, {}).get("label", key)
                return False, f"缺少必需参数: {label}"
        return True, None
