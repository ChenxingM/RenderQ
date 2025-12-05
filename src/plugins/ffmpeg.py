"""
RenderQ - FFmpeg 编码插件
用于将图片序列编码为视频文件 (ProRes 4444, MP4等)
"""
import re
import os
from typing import Any
import uuid

from src.plugins.base import CommandLinePlugin
from src.core.models import Job, Task


class FFmpegPlugin(CommandLinePlugin):
    """FFmpeg 编码插件"""

    name = "ffmpeg"
    display_name = "FFmpeg Encoder"
    version = "1.0.0"
    description = "使用FFmpeg将图片序列编码为视频"

    # 默认ffmpeg路径
    default_executable_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        "ffmpeg",  # 使用PATH中的ffmpeg
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg",
    ]

    parameters = {
        "input_pattern": {
            "type": "path",
            "label": "输入文件模式",
            "required": True,
            "description": "输入文件路径模式，如 /path/to/frame_%05d.png",
        },
        "output_file": {
            "type": "path",
            "label": "输出文件",
            "required": True,
            "description": "输出视频文件路径",
            "save": True,
        },
        "codec": {
            "type": "choice",
            "label": "编码器",
            "required": True,
            "default": "libx264",
            "choices": ["libx264", "libx265", "prores_ks", "dnxhd", "copy"],
            "description": "视频编码器",
        },
        "profile": {
            "type": "choice",
            "label": "ProRes Profile",
            "required": False,
            "choices": ["proxy", "lt", "standard", "hq", "4444", "4444xq"],
            "description": "ProRes编码profile (仅prores_ks)",
        },
        "crf": {
            "type": "int",
            "label": "CRF质量",
            "required": False,
            "default": 18,
            "description": "CRF质量值 (0-51, 越小质量越高, 仅x264/x265)",
        },
        "preset": {
            "type": "choice",
            "label": "编码速度",
            "required": False,
            "default": "medium",
            "choices": ["ultrafast", "superfast", "veryfast", "faster", "fast",
                       "medium", "slow", "slower", "veryslow"],
            "description": "编码速度预设 (仅x264/x265)",
        },
        "frame_rate": {
            "type": "float",
            "label": "帧率",
            "required": False,
            "default": 24.0,
            "description": "输出帧率",
        },
        "start_number": {
            "type": "int",
            "label": "起始帧号",
            "required": False,
            "default": 0,
            "description": "输入序列的起始帧号",
        },
        "pix_fmt": {
            "type": "string",
            "label": "像素格式",
            "required": False,
            "default": "yuv420p",
            "description": "输出像素格式",
        },
        "audio_file": {
            "type": "path",
            "label": "音频文件",
            "required": False,
            "description": "可选的音频文件路径",
        },
        "ffmpeg_path": {
            "type": "path",
            "label": "FFmpeg路径",
            "required": False,
            "description": "自定义ffmpeg.exe路径",
        },
        "extra_args": {
            "type": "string",
            "label": "额外参数",
            "required": False,
            "description": "额外的FFmpeg命令行参数",
        },
    }

    def validate(self, plugin_data: dict) -> tuple[bool, str | None]:
        """验证参数"""
        if not plugin_data.get("input_pattern"):
            return False, "缺少输入文件模式"
        if not plugin_data.get("output_file"):
            return False, "缺少输出文件路径"

        codec = plugin_data.get("codec", "libx264")
        if codec == "prores_ks" and not plugin_data.get("profile"):
            return False, "ProRes编码需要指定profile"

        return True, None

    def create_tasks(self, job: Job) -> list[Task]:
        """创建编码任务 (单任务)"""
        return [Task(
            id=str(uuid.uuid4()),
            job_id=job.id,
            index=0,
        )]

    def build_command(self, task: Task, job: Job) -> list[str]:
        """构建FFmpeg命令"""
        data = job.plugin_data

        ffmpeg = self.find_executable(data.get("ffmpeg_path"))

        input_pattern = data["input_pattern"]
        output_file = data["output_file"]
        codec = data.get("codec", "libx264")
        frame_rate = data.get("frame_rate", 24.0)
        start_number = data.get("start_number", 0)
        pix_fmt = data.get("pix_fmt", "yuv420p")

        # 确保输出目录存在
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # 基础命令
        cmd = [
            ffmpeg,
            "-y",  # 覆盖输出文件
            "-framerate", str(frame_rate),
            "-start_number", str(start_number),
            "-i", input_pattern,
        ]

        # 音频输入
        audio_file = data.get("audio_file")
        if audio_file and os.path.exists(audio_file):
            cmd.extend(["-i", audio_file])

        # 编码器设置
        cmd.extend(["-c:v", codec])

        if codec == "prores_ks":
            # ProRes设置
            profile = data.get("profile", "hq")
            profile_map = {
                "proxy": 0,
                "lt": 1,
                "standard": 2,
                "hq": 3,
                "4444": 4,
                "4444xq": 5,
            }
            cmd.extend(["-profile:v", str(profile_map.get(profile, 3))])

            # ProRes 4444支持alpha通道
            if profile in ("4444", "4444xq"):
                cmd.extend(["-pix_fmt", data.get("pix_fmt", "yuva444p10le")])
            else:
                cmd.extend(["-pix_fmt", "yuv422p10le"])

        elif codec in ("libx264", "libx265"):
            # H.264/H.265设置
            crf = data.get("crf", 18)
            preset = data.get("preset", "medium")
            cmd.extend([
                "-crf", str(crf),
                "-preset", preset,
                "-pix_fmt", pix_fmt,
            ])

            # H.264兼容性
            if codec == "libx264":
                cmd.extend(["-movflags", "+faststart"])

        # 音频编码
        if audio_file and os.path.exists(audio_file):
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            cmd.extend(["-an"])  # 无音频

        # 额外参数
        extra_args = data.get("extra_args", "")
        if extra_args:
            cmd.extend(extra_args.split())

        # 输出文件
        cmd.append(output_file)

        return cmd

    def parse_progress(self, output_line: str, task: Task) -> float | None:
        """解析FFmpeg输出的进度信息"""
        # FFmpeg输出格式:
        # frame=  100 fps= 25 q=28.0 size=    1024kB time=00:00:04.00 ...

        # 尝试解析frame数
        frame_match = re.search(r'frame=\s*(\d+)', output_line)
        if frame_match:
            # 需要知道总帧数才能计算进度
            # 这里简单返回None，让调度器使用其他方式追踪
            return None

        # 检查是否完成
        if "video:" in output_line and "audio:" in output_line:
            return 100.0

        return None


# 插件实例 (用于注册)
plugin = FFmpegPlugin()
