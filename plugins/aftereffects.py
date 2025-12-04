"""
RenderQ - Adobe After Effects 渲染插件
"""
import re
import os
from typing import Any
import uuid

from plugins.base import CommandLinePlugin
from core.models import Job, Task


class AfterEffectsPlugin(CommandLinePlugin):
    """Adobe After Effects 渲染插件"""
    
    name = "aftereffects"
    display_name = "Adobe After Effects"
    version = "1.0.0"
    description = "使用aerender渲染After Effects工程"
    
    # 默认aerender路径
    default_executable_paths = [
        r"C:\Program Files\Adobe\Adobe After Effects 2025\Support Files\aerender.exe",
        r"C:\Program Files\Adobe\Adobe After Effects 2024\Support Files\aerender.exe",
        r"C:\Program Files\Adobe\Adobe After Effects 2023\Support Files\aerender.exe",
        r"C:\Program Files\Adobe\Adobe After Effects CC 2022\Support Files\aerender.exe",
        # macOS
        "/Applications/Adobe After Effects 2025/aerender",
        "/Applications/Adobe After Effects 2024/aerender",
        "/Applications/Adobe After Effects 2023/aerender",
    ]
    
    parameters = {
        "project_path": {
            "type": "path",
            "label": "工程文件",
            "required": True,
            "description": "AE工程文件路径 (.aep)",
            "filter": "After Effects Project (*.aep)",
        },
        "comp_name": {
            "type": "string",
            "label": "合成名称",
            "required": True,
            "description": "要渲染的合成名称",
        },
        "output_path": {
            "type": "path",
            "label": "输出路径",
            "required": True,
            "description": "渲染输出路径，支持[#####]帧号占位符",
            "save": True,
        },
        "output_module": {
            "type": "string",
            "label": "输出模块",
            "required": False,
            "default": "Lossless",
            "description": "AE输出模块模板名称",
        },
        "render_settings": {
            "type": "string",
            "label": "渲染设置",
            "required": False,
            "default": "Best Settings",
            "description": "AE渲染设置模板名称",
        },
        "frame_start": {
            "type": "int",
            "label": "起始帧",
            "required": False,
            "description": "渲染起始帧 (留空使用工程设置)",
        },
        "frame_end": {
            "type": "int",
            "label": "结束帧",
            "required": False,
            "description": "渲染结束帧 (留空使用工程设置)",
        },
        "chunk_size": {
            "type": "int",
            "label": "分块大小",
            "required": False,
            "default": 0,
            "description": "帧分块大小 (0=不分块，单Task渲染全部)",
        },
        "multi_machine": {
            "type": "bool",
            "label": "多机渲染模式",
            "required": False,
            "default": False,
            "description": "启用-mp标志，允许多机同时渲染同一工程",
        },
        "memory_limit": {
            "type": "int",
            "label": "内存限制(%)",
            "required": False,
            "default": 100,
            "description": "AE内存使用限制百分比",
        },
        "aerender_path": {
            "type": "path",
            "label": "aerender路径",
            "required": False,
            "description": "自定义aerender.exe路径",
        },
    }
    
    def validate(self, plugin_data: dict) -> tuple[bool, str | None]:
        """验证参数"""
        # 检查必需参数
        valid, error = self._validate_required(
            plugin_data, "project_path", "comp_name", "output_path"
        )
        if not valid:
            return valid, error
        
        # 检查工程文件存在
        project_path = plugin_data.get("project_path", "")
        if not os.path.exists(project_path):
            return False, f"工程文件不存在: {project_path}"
        
        # 检查帧范围
        frame_start = plugin_data.get("frame_start")
        frame_end = plugin_data.get("frame_end")
        if frame_start is not None and frame_end is not None:
            if frame_start > frame_end:
                return False, "起始帧不能大于结束帧"
        
        # 如果要分块，必须指定帧范围
        chunk_size = plugin_data.get("chunk_size", 0)
        if chunk_size > 0:
            if frame_start is None or frame_end is None:
                return False, "分块渲染需要指定帧范围"
        
        return True, None
    
    def create_tasks(self, job: Job) -> list[Task]:
        """创建渲染任务"""
        data = job.plugin_data
        chunk_size = data.get("chunk_size", 0)
        frame_start = data.get("frame_start")
        frame_end = data.get("frame_end")
        
        # 不分块，单任务
        if chunk_size <= 0 or frame_start is None or frame_end is None:
            return [Task(
                id=str(uuid.uuid4()),
                job_id=job.id,
                index=0,
                frame_start=frame_start,
                frame_end=frame_end,
            )]
        
        # 分块创建多个任务
        tasks = []
        idx = 0
        for start in range(frame_start, frame_end + 1, chunk_size):
            end = min(start + chunk_size - 1, frame_end)
            tasks.append(Task(
                id=str(uuid.uuid4()),
                job_id=job.id,
                index=idx,
                frame_start=start,
                frame_end=end,
            ))
            idx += 1
        
        return tasks
    
    def build_command(self, task: Task, job: Job) -> list[str]:
        """构建aerender命令"""
        data = job.plugin_data
        
        # 查找aerender
        aerender = self.find_executable(data.get("aerender_path"))
        
        cmd = [
            aerender,
            "-project", data["project_path"],
            "-comp", data["comp_name"],
            "-output", self._resolve_output_path(data["output_path"], task),
            "-v", "ERRORS_AND_PROGRESS",  # 输出进度信息
        ]
        
        # 输出模块
        if data.get("output_module"):
            cmd.extend(["-OMtemplate", data["output_module"]])
        
        # 渲染设置
        if data.get("render_settings"):
            cmd.extend(["-RStemplate", data["render_settings"]])
        
        # 帧范围
        if task.frame_start is not None:
            cmd.extend(["-s", str(task.frame_start)])
        if task.frame_end is not None:
            cmd.extend(["-e", str(task.frame_end)])
        
        # 多机渲染
        if data.get("multi_machine"):
            cmd.append("-mp")
        
        # 内存限制
        memory_limit = data.get("memory_limit")
        if memory_limit and memory_limit != 100:
            cmd.extend(["-mem_usage", str(memory_limit), str(memory_limit)])
        
        # 关闭声音
        cmd.append("-sound")
        cmd.append("OFF")
        
        return cmd
    
    def parse_progress(self, output_line: str, task: Task) -> float | None:
        """解析aerender输出的进度信息"""
        # aerender输出格式:
        # "PROGRESS:  0:00:01:15 (101): 0 Seconds"
        # 括号中的数字是当前帧号
        
        match = re.search(r'PROGRESS:.*\((\d+)\)', output_line)
        if match:
            current_frame = int(match.group(1))
            
            if task.frame_start is not None and task.frame_end is not None:
                total_frames = task.frame_end - task.frame_start + 1
                if total_frames > 0:
                    progress = (current_frame - task.frame_start + 1) / total_frames * 100
                    return min(100.0, max(0.0, progress))
            
            # 没有帧范围信息时，只返回当前帧
            return None
        
        # 检查完成标志
        if "PROGRESS: Total Time Elapsed" in output_line:
            return 100.0
        
        return None
    
    def _resolve_output_path(self, output_path: str, task: Task) -> str:
        """处理输出路径"""
        # 分块渲染时，在文件名中添加chunk标识
        if task.index > 0 or (task.frame_start is not None and task.frame_end is not None):
            # 检查是否已有帧号占位符
            if "[#" in output_path:
                # 已有占位符，不需要修改
                pass
            else:
                # 在扩展名前添加chunk标识
                base, ext = os.path.splitext(output_path)
                if task.frame_start is not None:
                    output_path = f"{base}_{task.frame_start:05d}-{task.frame_end:05d}{ext}"
        
        return output_path
    
    def on_job_complete(self, job: Job):
        """Job完成后的处理"""
        # TODO: 如果是分块渲染，可以在这里合并输出文件
        pass


# 插件实例 (用于注册)
plugin = AfterEffectsPlugin()
