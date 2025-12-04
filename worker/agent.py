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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class WorkerAgent:
    """Worker代理 - 负责执行渲染任务"""
    
    def __init__(self, config: dict):
        self.server_url = config.get("server_url", "http://localhost:8000")
        self.worker_id = config.get("worker_id") or str(uuid.uuid4())
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
        task = assignment["task"]
        job = assignment.get("job", {})
        
        task_id = task["id"]
        self.current_task = task_id
        
        logger.info(f"Executing task: {task_id}")
        logger.info(f"Command: {' '.join(task['command'])}")
        
        # 报告开始
        try:
            await self.client.post(f"/api/tasks/{task_id}/start")
        except Exception as e:
            logger.error(f"Failed to report task start: {e}")
        
        # 准备日志文件
        log_path = self.log_dir / f"{task_id}.log"
        
        try:
            # 执行命令
            self.current_process = subprocess.Popen(
                task["command"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=task.get("working_dir"),
                env={**os.environ, **(task.get("environment") or {})},
            )
            
            # 读取输出并解析进度
            with open(log_path, "w", encoding="utf-8") as log_file:
                last_progress_time = datetime.now()
                
                for line in iter(self.current_process.stdout.readline, ''):
                    if not line:
                        break
                    
                    # 写入日志
                    log_file.write(line)
                    log_file.flush()
                    
                    # 解析进度 (简单实现，可扩展)
                    progress = self._parse_progress(line, task, job)
                    if progress is not None:
                        # 限制进度报告频率
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
            
            # 等待进程结束
            self.current_process.wait()
            exit_code = self.current_process.returncode
            
            # 报告结果
            if exit_code == 0:
                await self.client.post(
                    f"/api/tasks/{task_id}/complete",
                    params={"exit_code": exit_code}
                )
                logger.info(f"Task {task_id} completed")
            else:
                await self.client.post(
                    f"/api/tasks/{task_id}/fail",
                    params={
                        "exit_code": exit_code,
                        "error_message": f"Process exited with code {exit_code}"
                    }
                )
                logger.error(f"Task {task_id} failed with exit code {exit_code}")
                
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
    
    def _parse_progress(self, line: str, task: dict, job: dict) -> float | None:
        """解析进度 - 根据插件类型选择解析方式"""
        import re
        
        plugin = job.get("plugin", "")
        
        if plugin == "aftereffects":
            # aerender: "PROGRESS:  0:00:01:15 (101): 0 Seconds"
            match = re.search(r'PROGRESS:.*\((\d+)\)', line)
            if match:
                current_frame = int(match.group(1))
                frame_start = task.get("frame_start")
                frame_end = task.get("frame_end")
                
                if frame_start is not None and frame_end is not None:
                    total = frame_end - frame_start + 1
                    if total > 0:
                        return min(100.0, (current_frame - frame_start + 1) / total * 100)
        
        elif plugin == "blender":
            # Blender: "Fra:125 Mem:123.45M"
            match = re.search(r'Fra:(\d+)', line)
            if match:
                current_frame = int(match.group(1))
                frame_start = task.get("frame_start")
                frame_end = task.get("frame_end")
                
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
    
    # 运行
    asyncio.run(run_worker(config))


if __name__ == "__main__":
    main()
