"""
RenderQ Worker Agent - 渲染执行代理
运行在渲染机上，从Server获取任务并执行
"""
import asyncio
import logging
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import httpx
import psutil

from src.plugins import registry
from src.core.models import Task, Job

# 加载内置插件
registry.load_builtin_plugins()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class WorkerAgent:
    """Worker代理 - 负责执行渲染任务"""

    def __init__(self, config: dict):
        self.server_url = config.get("server_url", "http://localhost:8000")
        self.worker_id = config.get("worker_id") or self._generate_stable_id()
        self.name = config.get("name") or platform.node()
        self.pools = config.get("pools", ["default"])
        self.capabilities = config.get("capabilities", ["aftereffects"])

        self.running = False
        self.current_task = None
        self.current_process: subprocess.Popen | None = None

        # HTTP客户端
        self.client: httpx.AsyncClient | None = None

        # 日志目录
        self.log_dir = Path(config.get("log_dir", "logs"))
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 配置
        self.heartbeat_interval = config.get("heartbeat_interval", 10)
        self.poll_interval = config.get("poll_interval", 2)

        # 是否显示渲染窗口 (Windows)
        self.show_render_window = config.get("show_render_window", True)
    
    async def start(self):
        """启动Worker"""
        self.running = True
        self.client = httpx.AsyncClient(base_url=self.server_url, timeout=30)
        
        # 注册到Server
        await self._register()
        
        # 启动心跳任务
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        logger.info(f"Worker started: {self.name} ({self.worker_id})")
        
        # 主循环 - 请求并执行任务
        try:
            while self.running:
                if self.current_task is None:
                    assignment = await self._request_task()
                    if assignment:
                        await self._execute_task(assignment)
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            pass
        finally:
            heartbeat_task.cancel()
            await self.client.aclose()
            logger.info("Worker stopped")
    
    def stop(self):
        """停止Worker"""
        self.running = False
        if self.current_process:
            self.current_process.terminate()
    
    async def _register(self):
        """向Server注册"""
        try:
            response = await self.client.post("/api/workers/register", json={
                "id": self.worker_id,
                "name": self.name,
                "hostname": platform.node(),
                "ip_address": self._get_local_ip(),
                "pools": self.pools,
                "capabilities": self.capabilities,
                "cpu_cores": psutil.cpu_count(logical=True),
                "memory_total": psutil.virtual_memory().total,
                "version": "1.0.0",
            })
            response.raise_for_status()
            logger.info("Registered with server")
        except Exception as e:
            logger.error(f"Failed to register: {e}")
            raise
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        while self.running:
            try:
                await self.client.post(f"/api/workers/{self.worker_id}/heartbeat", json={
                    "status": "busy" if self.current_task else "idle",
                    "current_task": self.current_task,
                    "cpu_usage": psutil.cpu_percent(),
                    "memory_used": psutil.virtual_memory().used,
                })
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
            
            await asyncio.sleep(self.heartbeat_interval)
    
    async def _request_task(self) -> dict | None:
        """请求任务"""
        try:
            response = await self.client.post(f"/api/workers/{self.worker_id}/request-task")
            if response.status_code == 200:
                data = response.json()
                if data:
                    return data
        except Exception as e:
            logger.warning(f"Failed to request task: {e}")
        return None
    
    async def _execute_task(self, assignment: dict):
        """执行任务"""
        task_data = assignment.get("task")
        job_data = assignment.get("job")

        if not task_data:
            logger.error(f"No task data in assignment: {assignment}")
            return

        task_id = task_data.get("id", "unknown")
        self.current_task = task_id

        logger.info(f"Executing task: {task_id}")
        logger.info(f"Task data: {task_data}")
        logger.info(f"Job data: {job_data}")

        if not job_data:
            logger.error(f"No job data for task {task_id}")
            try:
                await self.client.post(
                    f"/api/tasks/{task_id}/fail",
                    params={"exit_code": -1, "error_message": "No job data"}
                )
            except Exception:
                pass
            self.current_task = None
            return

        # 获取插件并在本地构建命令
        plugin_name = job_data.get("plugin", "")
        plugin = registry.get(plugin_name)

        if not plugin:
            logger.error(f"Unknown plugin: {plugin_name}")
            try:
                await self.client.post(
                    f"/api/tasks/{task_id}/fail",
                    params={"exit_code": -1, "error_message": f"Unknown plugin: {plugin_name}"}
                )
            except Exception:
                pass
            self.current_task = None
            return

        # 在 Worker 本地构建命令 (使用本地的 aerender 路径)
        # 创建简单的 Task 和 Job 对象用于构建命令
        try:
            # 只提取必要的字段，避免 datetime 解析问题
            task = Task(
                id=task_data["id"],
                job_id=task_data["job_id"],
                index=task_data.get("index", 0),
                frame_start=task_data.get("frame_start"),
                frame_end=task_data.get("frame_end"),
                metadata=task_data.get("metadata", {}),
            )
            job = Job(
                id=job_data["id"],
                name=job_data["name"],
                plugin=job_data["plugin"],
                plugin_data=job_data.get("plugin_data", {}),
            )
            command = plugin.build_command(task, job)
            logger.info(f"Built command: {' '.join(command)}")
        except Exception as e:
            import traceback
            logger.error(f"Failed to build command: {e}")
            traceback.print_exc()
            try:
                await self.client.post(
                    f"/api/tasks/{task_id}/fail",
                    params={"exit_code": -1, "error_message": f"Failed to build command: {e}"}
                )
            except Exception:
                pass
            self.current_task = None
            return

        if not command:
            logger.error(f"Task {task_id} has empty command!")
            try:
                await self.client.post(
                    f"/api/tasks/{task_id}/fail",
                    params={"exit_code": -1, "error_message": "Empty command"}
                )
            except Exception:
                pass
            self.current_task = None
            return

        logger.info(f"Command: {' '.join(command)}")
        
        # 报告开始
        try:
            await self.client.post(f"/api/tasks/{task_id}/start")
            # 初始化日志 (清除旧日志)
            await self.client.post(
                f"/api/tasks/{task_id}/log",
                json={"log": f"=== Task started at {datetime.now().isoformat()} ===\n", "append": False}
            )
        except Exception as e:
            logger.error(f"Failed to report task start: {e}")
        
        # 准备日志文件和批处理文件 (使用绝对路径)
        log_path = (self.log_dir / f"{task_id}.log").resolve()
        bat_path = (self.log_dir / f"{task_id}.bat").resolve()

        try:
            # 执行命令 (复制一份以便修改)
            command = list(command)
            show_window = self.show_render_window and sys.platform == "win32"

            if show_window:
                # Windows: 创建批处理文件并在新窗口中执行
                # 添加 aerender 的 -log 参数
                if "aerender" in command[0].lower():
                    command.extend(["-log", str(log_path)])

                # 构建批处理内容
                # 使用引号包裹路径以处理空格
                cmd_str = " ".join(f'"{arg}"' if " " in arg else arg for arg in command)
                bat_content = f'''@echo off
chcp 65001 >nul
echo ========================================
echo RenderQ Task: {task_id}
echo Started: %date% %time%
echo ========================================
echo.
echo Command: {cmd_str}
echo.
echo Log file: {log_path}
echo ========================================
echo.

{cmd_str}

set EXIT_CODE=%errorlevel%
echo.
echo ========================================
echo Exit Code: %EXIT_CODE%
echo Finished: %date% %time%
echo ========================================
echo.
echo Window will close in 5 seconds...
timeout /t 5 /nobreak >nul
exit /b %EXIT_CODE%
'''
                bat_path.write_text(bat_content, encoding="utf-8")
                logger.info(f"Created batch file: {bat_path}")
                logger.info(f"Command: {cmd_str}")

                # 执行批处理文件
                self.current_process = subprocess.Popen(
                    ["cmd", "/c", str(bat_path)],
                    cwd=task.working_dir,
                    env={**os.environ, **(task.environment or {})},
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )

                # 通过读取日志文件来获取进度
                await self._monitor_log_file(task_id, log_path, task, job)

            else:
                # 后台运行，捕获 stdout
                self.current_process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    cwd=task.working_dir,
                    env={**os.environ, **(task.environment or {})},
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )

                # 读取 stdout 获取进度
                await self._monitor_stdout(task_id, log_path, task, job)
            
            # 等待进程结束
            self.current_process.wait()
            exit_code = self.current_process.returncode
            logger.info(f"Process finished with exit code: {exit_code}")

            # 报告结果
            if exit_code == 0:
                try:
                    response = await self.client.post(
                        f"/api/tasks/{task_id}/complete",
                        params={"exit_code": exit_code}
                    )
                    logger.info(f"Task {task_id} completed, server response: {response.status_code}")
                except Exception as e:
                    logger.error(f"Failed to report task completion: {e}")
            else:
                try:
                    response = await self.client.post(
                        f"/api/tasks/{task_id}/fail",
                        params={
                            "exit_code": exit_code,
                            "error_message": f"Process exited with code {exit_code}"
                        }
                    )
                    logger.error(f"Task {task_id} failed with exit code {exit_code}")
                except Exception as e:
                    logger.error(f"Failed to report task failure: {e}")

        except Exception as e:
            logger.exception(f"Task execution error: {e}")
            try:
                await self.client.post(
                    f"/api/tasks/{task_id}/fail",
                    params={"exit_code": -1, "error_message": str(e)}
                )
            except Exception:
                pass
        
        finally:
            self.current_task = None
            self.current_process = None
    
    async def _monitor_stdout(self, task_id: str, log_path: Path, task: Task, job: Job):
        """从 stdout 监控进度 (后台模式)"""
        log_buffer = []
        last_progress_time = datetime.now()
        last_log_upload_time = datetime.now()

        with open(log_path, "w", encoding="utf-8") as log_file:
            for line in iter(self.current_process.stdout.readline, ''):
                if not line:
                    break

                # 写入本地日志
                log_file.write(line)
                log_file.flush()

                # 收集日志用于上传
                log_buffer.append(line)

                # 解析进度
                progress = self._parse_progress(line, task, job)
                now = datetime.now()

                # 限制进度报告频率 (每秒一次)
                if progress is not None and (now - last_progress_time).total_seconds() >= 1:
                    try:
                        await self.client.post(
                            f"/api/tasks/{task_id}/progress",
                            params={"progress": progress}
                        )
                        last_progress_time = now
                    except Exception:
                        pass

                # 定期上传日志到Server (每2秒或缓冲区超过50行)
                if len(log_buffer) >= 50 or (now - last_log_upload_time).total_seconds() >= 2:
                    try:
                        await self.client.post(
                            f"/api/tasks/{task_id}/log",
                            json={"log": "".join(log_buffer), "append": True}
                        )
                        log_buffer = []
                        last_log_upload_time = now
                    except Exception:
                        pass

        # 上传剩余日志
        if log_buffer:
            try:
                await self.client.post(
                    f"/api/tasks/{task_id}/log",
                    json={"log": "".join(log_buffer), "append": True}
                )
            except Exception:
                pass

    def _read_log_file(self, log_path: Path) -> str:
        """读取日志文件，自动检测编码 (支持 UTF-8, Shift-JIS, GBK)"""
        encodings = ["utf-8", "shift_jis", "gbk", "cp936", "latin-1"]
        for encoding in encodings:
            try:
                with open(log_path, "r", encoding=encoding) as f:
                    return f.read()
            except (UnicodeDecodeError, LookupError):
                continue
        # 最后用 latin-1 强制读取
        with open(log_path, "r", encoding="latin-1") as f:
            return f.read()

    async def _monitor_log_file(self, task_id: str, log_path: Path, task: Task, job: Job):
        """从日志文件监控进度 (窗口模式，aerender -log)"""
        last_size = 0
        last_progress_time = datetime.now()
        last_log_upload_time = datetime.now()
        last_content = ""

        while self.current_process.poll() is None:
            await asyncio.sleep(0.5)  # 每0.5秒检查一次

            if not log_path.exists():
                continue

            try:
                current_size = log_path.stat().st_size
                if current_size > last_size:
                    content = self._read_log_file(log_path)

                    # 获取新增内容
                    new_content = content[len(last_content):]
                    last_content = content
                    last_size = current_size

                    if new_content:
                        # 解析进度
                        for line in new_content.split('\n'):
                            progress = self._parse_progress(line, task, job)
                            if progress is not None:
                                now = datetime.now()
                                if (now - last_progress_time).total_seconds() >= 1:
                                    try:
                                        await self.client.post(
                                            f"/api/tasks/{task_id}/progress",
                                            params={"progress": progress}
                                        )
                                        last_progress_time = now
                                    except Exception:
                                        pass

                        # 上传日志
                        now = datetime.now()
                        if (now - last_log_upload_time).total_seconds() >= 2:
                            try:
                                await self.client.post(
                                    f"/api/tasks/{task_id}/log",
                                    json={"log": new_content, "append": True}
                                )
                                last_log_upload_time = now
                            except Exception:
                                pass

            except Exception as e:
                logger.warning(f"Error reading log file: {e}")

        # 进程结束后，上传完整日志
        if log_path.exists():
            try:
                content = self._read_log_file(log_path)
                await self.client.post(
                    f"/api/tasks/{task_id}/log",
                    json={"log": content, "append": False}
                )
            except Exception as e:
                logger.warning(f"Failed to upload final log: {e}")
                pass

    def _parse_progress(self, line: str, task: Task, job: Job) -> float | None:
        """解析进度 - 根据插件类型选择解析方式"""
        import re

        plugin = job.plugin

        if plugin == "aftereffects":
            # aerender: "PROGRESS:  0:00:01:15 (101): 0 Seconds"
            match = re.search(r'PROGRESS:.*\((\d+)\)', line)
            if match:
                current_frame = int(match.group(1))
                frame_start = task.frame_start
                frame_end = task.frame_end

                if frame_start is not None and frame_end is not None:
                    total = frame_end - frame_start + 1
                    if total > 0:
                        return min(100.0, (current_frame - frame_start + 1) / total * 100)

        elif plugin == "blender":
            # Blender: "Fra:125 Mem:123.45M"
            match = re.search(r'Fra:(\d+)', line)
            if match:
                current_frame = int(match.group(1))
                frame_start = task.frame_start
                frame_end = task.frame_end

                if frame_start is not None and frame_end is not None:
                    total = frame_end - frame_start + 1
                    if total > 0:
                        return min(100.0, (current_frame - frame_start + 1) / total * 100)

        return None
    
    def _get_local_ip(self) -> str:
        """获取本机IP"""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _generate_stable_id(self) -> str:
        """生成基于机器标识的稳定ID"""
        import hashlib

        # 获取机器标识信息
        hostname = platform.node()

        # 尝试获取MAC地址
        mac = ""
        try:
            import uuid as uuid_lib
            mac = hex(uuid_lib.getnode())
        except Exception:
            pass

        # 组合生成稳定的ID
        identity = f"{hostname}-{mac}"
        hash_bytes = hashlib.sha256(identity.encode()).digest()[:16]

        # 转换为UUID格式
        stable_uuid = uuid.UUID(bytes=hash_bytes)
        return str(stable_uuid)


async def run_worker(config: dict):
    """运行Worker"""
    agent = WorkerAgent(config)
    
    # 处理信号
    import signal
    
    def signal_handler(sig, frame):
        logger.info("Shutting down...")
        agent.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    await agent.start()


def main():
    """入口函数"""
    import argparse
    import yaml

    parser = argparse.ArgumentParser(description="RenderQ Worker")
    parser.add_argument("-c", "--config", help="Config file path")
    parser.add_argument("-s", "--server", default="http://localhost:8000", help="Server URL")
    parser.add_argument("-n", "--name", help="Worker name")
    parser.add_argument("--pools", nargs="+", default=["default"], help="Worker pools")
    parser.add_argument("--capabilities", nargs="+", default=["aftereffects"], help="Supported plugins")
    parser.add_argument("--show-window", action="store_true", default=True,
                        help="Show render window (default: True)")
    parser.add_argument("--hide-window", action="store_true",
                        help="Hide render window")
    args = parser.parse_args()

    # 加载配置
    config = {}
    if args.config:
        with open(args.config, "r") as f:
            config = yaml.safe_load(f)

    # 命令行参数覆盖
    if args.server:
        config["server_url"] = args.server
    if args.name:
        config["name"] = args.name
    if args.pools:
        config["pools"] = args.pools
    if args.capabilities:
        config["capabilities"] = args.capabilities

    # 窗口显示设置
    config["show_render_window"] = not args.hide_window

    # 运行
    asyncio.run(run_worker(config))


if __name__ == "__main__":
    main()
