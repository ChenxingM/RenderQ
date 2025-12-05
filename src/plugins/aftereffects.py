"""
RenderQ - Adobe After Effects 渲染插件
支持两种模式:
1. render_queue - 渲染AE自带的渲染队列
2. custom - 指定合成渲染PNG序列，可选编码为ProRes/MP4
"""
import re
import os
import platform
from typing import Any
import uuid

from src.plugins.base import CommandLinePlugin
from src.core.models import Job, Task


def find_ae_from_registry() -> str | None:
    """从Windows注册表查找最新版本的After Effects安装路径"""
    if platform.system() != "Windows":
        return None

    try:
        import winreg

        # Adobe After Effects 注册表路径
        ae_reg_paths = [
            r"SOFTWARE\Adobe\After Effects",
            r"SOFTWARE\Wow6432Node\Adobe\After Effects",
        ]

        versions = []

        for reg_path in ae_reg_paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                i = 0
                while True:
                    try:
                        version = winreg.EnumKey(key, i)
                        # 版本号格式如 "24.0", "25.0" 等
                        try:
                            ver_num = float(version)
                            versions.append((ver_num, reg_path, version))
                        except ValueError:
                            pass
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except OSError:
                continue

        if not versions:
            return None

        # 按版本号降序排列，取最新版本
        versions.sort(key=lambda x: x[0], reverse=True)
        latest_ver_num, reg_path, version = versions[0]

        # 获取安装路径
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                f"{reg_path}\\{version}"
            )
            install_path, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)

            # aerender.exe 在 Support Files 目录下
            aerender_path = os.path.join(install_path, "Support Files", "aerender.exe")
            if os.path.exists(aerender_path):
                return aerender_path

            # 有些版本直接在安装目录
            aerender_path = os.path.join(install_path, "aerender.exe")
            if os.path.exists(aerender_path):
                return aerender_path

        except OSError:
            pass

        return None

    except Exception as e:
        print(f"Error finding AE from registry: {e}")
        return None


class AfterEffectsPlugin(CommandLinePlugin):
    """Adobe After Effects 渲染插件"""

    name = "aftereffects"
    display_name = "Adobe After Effects"
    version = "2.0.0"
    description = "使用aerender渲染After Effects工程，支持渲染队列模式和自定义合成模式"

    # 默认aerender路径 (备用)
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

    # PNG输出模块模板名称 (需要在AE中预先创建)
    PNG_OUTPUT_MODULE = "PNG Sequence"

    def find_executable(self, custom_path: str = None) -> str:
        """查找aerender可执行文件 - 优先从注册表获取最新版本"""
        # 1. 优先使用自定义路径
        if custom_path and os.path.exists(custom_path):
            return custom_path

        # 2. 从注册表查找最新版本 (Windows)
        registry_path = find_ae_from_registry()
        if registry_path:
            print(f"Found aerender from registry: {registry_path}")
            return registry_path

        # 3. 搜索默认路径
        for path in self.default_executable_paths:
            if os.path.exists(path):
                return path

        raise FileNotFoundError(
            "Cannot find aerender.exe. Please install After Effects or specify aerender_path."
        )

    parameters = {
        # 通用参数
        "mode": {
            "type": "choice",
            "label": "渲染模式",
            "required": True,
            "default": "custom",
            "choices": ["render_queue", "custom"],
            "description": "render_queue=渲染AE队列, custom=指定合成",
        },
        "project_path": {
            "type": "path",
            "label": "工程文件",
            "required": True,
            "description": "AE工程文件路径 (.aep)",
            "filter": "After Effects Project (*.aep)",
        },
        # render_queue 模式参数
        "rq_indices": {
            "type": "string",
            "label": "渲染队列索引",
            "required": False,
            "description": "要渲染的队列项索引列表 (仅render_queue模式)",
        },
        # custom 模式参数
        "comp_name": {
            "type": "string",
            "label": "合成名称",
            "required": False,
            "description": "要渲染的合成名称 (仅custom模式)",
        },
        "output_path": {
            "type": "path",
            "label": "输出目录",
            "required": False,
            "description": "输出目录路径",
            "save": True,
        },
        "output_formats": {
            "type": "string",
            "label": "输出格式",
            "required": False,
            "default": "png",
            "description": "输出格式: png, prores4444, mp4 (逗号分隔)",
        },
        "frame_start": {
            "type": "int",
            "label": "起始帧",
            "required": False,
            "description": "渲染起始帧",
        },
        "frame_end": {
            "type": "int",
            "label": "结束帧",
            "required": False,
            "description": "渲染结束帧",
        },
        "width": {
            "type": "int",
            "label": "宽度",
            "required": False,
            "description": "输出宽度",
        },
        "height": {
            "type": "int",
            "label": "高度",
            "required": False,
            "description": "输出高度",
        },
        "frame_rate": {
            "type": "float",
            "label": "帧率",
            "required": False,
            "description": "输出帧率",
        },
        # 高级参数
        "chunk_size": {
            "type": "int",
            "label": "分块大小",
            "required": False,
            "default": 0,
            "description": "帧分块大小 (0=自动根据Worker数量分配)",
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
        mode = plugin_data.get("mode", "custom")
        project_path = plugin_data.get("project_path", "")

        # 检查工程文件
        if not project_path:
            return False, "缺少工程文件路径"
        if not os.path.exists(project_path):
            return False, f"工程文件不存在: {project_path}"

        if mode == "render_queue":
            # 渲染队列模式 - 支持新格式 rq_items 和旧格式 rq_indices
            rq_items = plugin_data.get("rq_items", [])
            rq_indices = plugin_data.get("rq_indices", [])
            if not rq_items and not rq_indices:
                return False, "请指定要渲染的队列项"

        elif mode == "custom":
            # 自定义模式
            if not plugin_data.get("comp_name"):
                return False, "请指定合成名称"
            if not plugin_data.get("output_path"):
                return False, "请指定输出目录"

            frame_start = plugin_data.get("frame_start")
            frame_end = plugin_data.get("frame_end")
            if frame_start is not None and frame_end is not None:
                if frame_start > frame_end:
                    return False, "起始帧不能大于结束帧"

        return True, None

    def create_tasks(self, job: Job) -> list[Task]:
        """创建渲染任务"""
        data = job.plugin_data
        mode = data.get("mode", "custom")

        if mode == "render_queue":
            return self._create_render_queue_tasks(job)
        else:
            return self._create_custom_tasks(job)

    def _create_render_queue_tasks(self, job: Job) -> list[Task]:
        """创建渲染队列模式的任务"""
        data = job.plugin_data

        # 支持新格式 rq_items (带帧信息) 和旧格式 rq_indices
        rq_items = data.get("rq_items", [])
        rq_indices = data.get("rq_indices", [])

        tasks = []

        if rq_items:
            # 新格式 - 带帧信息
            for idx, item in enumerate(rq_items):
                tasks.append(Task(
                    id=str(uuid.uuid4()),
                    job_id=job.id,
                    index=idx,
                    frame_start=item.get("frame_start"),
                    frame_end=item.get("frame_end"),
                    metadata={
                        "rq_index": item.get("index"),
                        "comp_name": item.get("comp_name"),
                        "total_frames": item.get("total_frames"),
                        "frame_rate": item.get("frame_rate"),
                        "output_path": item.get("output_path"),
                    }
                ))
        else:
            # 旧格式 - 仅索引
            for idx, rq_index in enumerate(rq_indices):
                tasks.append(Task(
                    id=str(uuid.uuid4()),
                    job_id=job.id,
                    index=idx,
                    metadata={"rq_index": rq_index}
                ))

        return tasks

    def _create_custom_tasks(self, job: Job) -> list[Task]:
        """创建自定义模式的任务 (PNG序列分块渲染)"""
        data = job.plugin_data
        frame_start = data.get("frame_start", 0)
        frame_end = data.get("frame_end", 100)
        chunk_size = data.get("chunk_size", 0)

        total_frames = frame_end - frame_start + 1

        # 如果chunk_size为0，自动分配 (默认每块50帧)
        if chunk_size <= 0:
            chunk_size = min(50, total_frames)

        # 创建PNG渲染任务
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
                metadata={"task_type": "render_png"}
            ))
            idx += 1

        return tasks

    def build_command(self, task: Task, job: Job) -> list[str]:
        """构建aerender命令"""
        data = job.plugin_data
        mode = data.get("mode", "custom")

        aerender = self.find_executable(data.get("aerender_path"))

        if mode == "render_queue":
            return self._build_render_queue_command(aerender, task, job)
        else:
            return self._build_custom_command(aerender, task, job)

    def _build_render_queue_command(self, aerender: str, task: Task, job: Job) -> list[str]:
        """构建渲染队列模式命令"""
        data = job.plugin_data
        rq_index = task.metadata.get("rq_index", 1)

        cmd = [
            aerender,
            "-project", data["project_path"],
            "-rqindex", str(rq_index),
            "-v", "ERRORS_AND_PROGRESS",
            "-sound", "OFF",
            "-mp",  # 多机模式
        ]

        return cmd

    def _build_custom_command(self, aerender: str, task: Task, job: Job) -> list[str]:
        """构建自定义模式命令 (渲染PNG序列)"""
        data = job.plugin_data

        # 输出路径: output_path/png/comp_name_[#####].png
        output_dir = data["output_path"]
        comp_name = data["comp_name"]
        # 清理合成名中的非法字符
        safe_comp_name = re.sub(r'[<>:"/\\|?*]', '_', comp_name)

        png_dir = os.path.join(output_dir, "png")
        output_file = os.path.join(png_dir, f"{safe_comp_name}_[#####].png")

        cmd = [
            aerender,
            "-project", data["project_path"],
            "-comp", comp_name,
            "-output", output_file,
            "-v", "ERRORS_AND_PROGRESS",
            "-sound", "OFF",
            "-mp",  # 多机模式
            "-OMtemplate", self.PNG_OUTPUT_MODULE,
            "-RStemplate", "Best Settings",
        ]

        # 帧范围
        if task.frame_start is not None:
            cmd.extend(["-s", str(task.frame_start)])
        if task.frame_end is not None:
            cmd.extend(["-e", str(task.frame_end)])

        return cmd

    def parse_progress(self, output_line: str, task: Task) -> float | None:
        """解析aerender输出的进度信息"""
        # aerender输出格式:
        # "PROGRESS:  0:00:01:15 (101): 0 Seconds"
        match = re.search(r'PROGRESS:.*\((\d+)\)', output_line)
        if match:
            current_frame = int(match.group(1))

            if task.frame_start is not None and task.frame_end is not None:
                total_frames = task.frame_end - task.frame_start + 1
                if total_frames > 0:
                    progress = (current_frame - task.frame_start + 1) / total_frames * 100
                    return min(100.0, max(0.0, progress))

            return None

        if "PROGRESS: Total Time Elapsed" in output_line:
            return 100.0

        return None

    def get_encoding_jobs(self, job: Job) -> list[dict]:
        """
        获取需要创建的编码任务
        在PNG渲染完成后调用，返回需要创建的FFmpeg编码Job
        """
        data = job.plugin_data
        mode = data.get("mode", "custom")

        if mode != "custom":
            return []

        output_formats = data.get("output_formats", ["png"])
        if isinstance(output_formats, str):
            output_formats = [f.strip() for f in output_formats.split(",")]

        encoding_jobs = []
        output_dir = data["output_path"]
        comp_name = data["comp_name"]
        safe_comp_name = re.sub(r'[<>:"/\\|?*]', '_', comp_name)

        png_dir = os.path.join(output_dir, "png")
        png_pattern = os.path.join(png_dir, f"{safe_comp_name}_%05d.png")

        frame_start = data.get("frame_start", 0)
        frame_rate = data.get("frame_rate", 24)

        for fmt in output_formats:
            fmt = fmt.lower().strip()

            if fmt == "png":
                continue  # PNG已经渲染好了

            elif fmt == "prores4444":
                prores_dir = os.path.join(output_dir, "prores")
                output_file = os.path.join(prores_dir, f"{safe_comp_name}.mov")
                encoding_jobs.append({
                    "name": f"{job.name} - ProRes 4444",
                    "plugin": "ffmpeg",
                    "priority": job.priority,
                    "dependent_on": [job.id],
                    "plugin_data": {
                        "input_pattern": png_pattern,
                        "output_file": output_file,
                        "codec": "prores_ks",
                        "profile": "4444",
                        "frame_rate": frame_rate,
                        "start_number": frame_start,
                        "pix_fmt": "yuva444p10le",
                    }
                })

            elif fmt == "mp4":
                mp4_dir = os.path.join(output_dir, "mp4")
                output_file = os.path.join(mp4_dir, f"{safe_comp_name}.mp4")
                encoding_jobs.append({
                    "name": f"{job.name} - MP4",
                    "plugin": "ffmpeg",
                    "priority": job.priority,
                    "dependent_on": [job.id],
                    "plugin_data": {
                        "input_pattern": png_pattern,
                        "output_file": output_file,
                        "codec": "libx264",
                        "crf": 18,
                        "preset": "medium",
                        "frame_rate": frame_rate,
                        "start_number": frame_start,
                        "pix_fmt": "yuv420p",
                    }
                })

        return encoding_jobs


# 插件实例 (用于注册)
plugin = AfterEffectsPlugin()
