"""
RenderQ Server - FastAPI 服务器
"""
import asyncio
import logging
import shutil
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.core import Database, Scheduler, Job, Task, JobSubmission, JobStatus, TaskStatus, WorkerStatus
from src.core.events import event_bus, Event
from src.plugins import registry

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 全局实例
db: Database = None
scheduler: Scheduler = None

# WebSocket 连接管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected, total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected, total: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn)

ws_manager = ConnectionManager()


# 事件处理 - 广播到WebSocket
async def broadcast_event(event: Event):
    await ws_manager.broadcast(event.to_dict())

event_bus.subscribe_all_async(broadcast_event)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    global db, scheduler
    
    # 初始化数据库
    db = Database("data/renderq.db")
    
    # 加载插件
    registry.load_builtin_plugins()
    
    # 初始化调度器
    scheduler = Scheduler(db, registry.get_all())
    
    # 启动调度器
    scheduler_task = asyncio.create_task(scheduler.start())
    
    logger.info("RenderQ Server started")
    
    yield
    
    # 停止调度器
    scheduler.stop()
    scheduler_task.cancel()
    
    logger.info("RenderQ Server stopped")


# 创建应用
app = FastAPI(
    title="RenderQ",
    description="轻量级渲染队列管理系统",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Jobs API ============

@app.post("/api/jobs", response_model=Job, tags=["Jobs"])
async def submit_job(submission: JobSubmission):
    """提交渲染作业"""
    # 验证插件存在
    plugin = registry.get(submission.plugin)
    if not plugin:
        raise HTTPException(400, f"Unknown plugin: {submission.plugin}")

    # 验证插件参数
    valid, error = plugin.validate(submission.plugin_data)
    if not valid:
        raise HTTPException(400, f"Plugin validation failed: {error}")

    # 创建Job
    job = Job(
        name=submission.name,
        plugin=submission.plugin,
        priority=submission.priority,
        pool=submission.pool,
        plugin_data=submission.plugin_data,
        dependent_on=submission.dependent_on,
        metadata=submission.metadata,
        submitted_at=datetime.now(),
    )

    db.add_job(job)

    # 使用插件创建Tasks (不构建命令，命令由Worker构建)
    try:
        tasks = plugin.create_tasks(job)
        logger.info(f"Created {len(tasks)} tasks for job {job.id}")

        for task in tasks:
            # 不在Server构建命令，由Worker根据本地环境构建
            db.add_task(task)

        job.task_total = len(tasks)
        job.status = JobStatus.QUEUED  # 设置为已排队状态，等待Worker执行
        db.update_job(job)

        logger.info(f"Job submitted: {job.id} ({job.name}) with {len(tasks)} tasks")
    except Exception as e:
        # 如果创建任务失败，删除Job
        db.delete_job(job.id)
        logger.error(f"Failed to create tasks: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to create tasks: {e}")

    return job


@app.get("/api/jobs", tags=["Jobs"])
async def list_jobs(status: JobStatus = None, limit: int = 100, offset: int = 0):
    """获取作业列表"""
    return db.get_jobs(status=status, limit=limit, offset=offset)


@app.get("/api/jobs/{job_id}", response_model=Job, tags=["Jobs"])
async def get_job(job_id: str):
    """获取作业详情"""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/jobs/{job_id}/tasks", tags=["Jobs"])
async def get_job_tasks(job_id: str):
    """获取作业的所有任务"""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return db.get_tasks_by_job(job_id)


@app.post("/api/jobs/{job_id}/suspend", tags=["Jobs"])
async def suspend_job(job_id: str):
    """暂停作业"""
    success = await scheduler.suspend_job(job_id)
    if not success:
        raise HTTPException(400, "Cannot suspend job")
    return {"status": "suspended"}


@app.post("/api/jobs/{job_id}/resume", tags=["Jobs"])
async def resume_job(job_id: str):
    """恢复作业"""
    success = await scheduler.resume_job(job_id)
    if not success:
        raise HTTPException(400, "Cannot resume job")
    return {"status": "resumed"}


@app.post("/api/jobs/{job_id}/cancel", tags=["Jobs"])
async def cancel_job(job_id: str):
    """取消作业"""
    success = await scheduler.cancel_job(job_id)
    if not success:
        raise HTTPException(400, "Cannot cancel job")
    return {"status": "cancelled"}


@app.post("/api/jobs/{job_id}/retry", tags=["Jobs"])
async def retry_job(job_id: str):
    """重试失败的作业"""
    success = await scheduler.retry_job(job_id)
    if not success:
        raise HTTPException(400, "Cannot retry job")
    return {"status": "retrying"}


@app.delete("/api/jobs/{job_id}", tags=["Jobs"])
async def delete_job(job_id: str):
    """删除作业"""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    
    # 只能删除已完成/已取消/已失败的作业
    if job.status not in (JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED):
        raise HTTPException(400, "Cannot delete active job")
    
    db.delete_job(job_id)
    return {"status": "deleted"}


@app.put("/api/jobs/{job_id}/priority", tags=["Jobs"])
async def update_job_priority(job_id: str, priority: int):
    """更新作业优先级"""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    
    if not 0 <= priority <= 100:
        raise HTTPException(400, "Priority must be 0-100")
    
    job.priority = priority
    db.update_job(job)
    return {"status": "updated", "priority": priority}


# ============ Tasks API ============

@app.post("/api/tasks/{task_id}/start", tags=["Tasks"])
async def task_started(task_id: str):
    """Worker报告Task开始"""
    db.update_task_status(task_id, TaskStatus.RUNNING, started_at=datetime.now())
    return {"ok": True}


@app.post("/api/tasks/{task_id}/progress", tags=["Tasks"])
async def task_progress(task_id: str, progress: float):
    """Worker报告Task进度"""
    db.update_task_progress(task_id, progress)
    return {"ok": True}


@app.post("/api/tasks/{task_id}/log", tags=["Tasks"])
async def upload_task_log(task_id: str, data: dict):
    """Worker上传Task日志"""
    from pathlib import Path

    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / f"{task_id}.log"
    log_content = data.get("log", "")

    # 追加或覆盖日志
    mode = "a" if data.get("append", False) else "w"
    with open(log_path, mode, encoding="utf-8") as f:
        f.write(log_content)

    return {"ok": True}


@app.post("/api/tasks/{task_id}/complete", tags=["Tasks"])
async def task_completed(task_id: str, exit_code: int = 0):
    """Worker报告Task完成"""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    db.update_task_status(
        task_id, TaskStatus.COMPLETED,
        finished_at=datetime.now(),
        exit_code=exit_code
    )

    # 释放Worker
    if task.assigned_worker:
        worker = db.get_worker(task.assigned_worker)
        if worker:
            worker.status = WorkerStatus.IDLE
            worker.current_task = None
            db.update_worker(worker)

    # 更新Job状态
    job = db.get_job(task.job_id)
    if job:
        all_tasks = db.get_tasks_by_job(task.job_id)
        completed_count = sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED)
        failed_count = sum(1 for t in all_tasks if t.status == TaskStatus.FAILED)

        job.task_completed = completed_count
        job.task_failed = failed_count
        job.progress = (completed_count / job.task_total * 100) if job.task_total > 0 else 0

        # 检查是否所有任务都完成
        if completed_count + failed_count >= job.task_total:
            if failed_count > 0:
                job.status = JobStatus.FAILED
            else:
                job.status = JobStatus.COMPLETED
            job.finished_at = datetime.now()

            # Job 完成后清理 PNG (如果需要)
            await _cleanup_png_if_needed(job)

        db.update_job(job)
        logger.info(f"Job {job.id} progress: {completed_count}/{job.task_total} tasks completed")

    return {"ok": True}


async def _cleanup_png_if_needed(job: Job):
    """Job完成后清理PNG序列 (如果不需要保留)"""
    plugin_data = job.plugin_data
    mode = plugin_data.get("mode", "")

    # 只有 custom 模式需要清理
    if mode != "custom":
        return

    # 检查输出格式 - 如果包含 png 则保留
    output_formats = plugin_data.get("output_formats", [])
    if isinstance(output_formats, str):
        output_formats = [f.strip() for f in output_formats.split(",")]

    # 如果用户选择了 PNG 输出，不删除
    if "png" in [f.lower() for f in output_formats]:
        logger.info(f"Job {job.id}: PNG output requested, keeping PNG files")
        return

    # 如果只有 PNG (没有其他编码格式)，也不删除
    non_png_formats = [f for f in output_formats if f.lower() != "png"]
    if not non_png_formats:
        logger.info(f"Job {job.id}: Only PNG format, keeping PNG files")
        return

    # 删除 PNG 目录
    output_path = plugin_data.get("output_path", "")
    if output_path:
        png_dir = Path(output_path) / "png"
        if png_dir.exists() and png_dir.is_dir():
            try:
                shutil.rmtree(png_dir)
                logger.info(f"Job {job.id}: Cleaned up PNG directory: {png_dir}")
            except Exception as e:
                logger.error(f"Job {job.id}: Failed to cleanup PNG: {e}")


@app.post("/api/tasks/{task_id}/fail", tags=["Tasks"])
async def task_failed(task_id: str, exit_code: int = -1, error_message: str = None):
    """Worker报告Task失败"""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    db.update_task_status(
        task_id, TaskStatus.FAILED,
        finished_at=datetime.now(),
        exit_code=exit_code,
        error_message=error_message
    )

    # 释放Worker
    if task.assigned_worker:
        worker = db.get_worker(task.assigned_worker)
        if worker:
            worker.status = WorkerStatus.IDLE
            worker.current_task = None
            db.update_worker(worker)

    # 更新Job状态
    job = db.get_job(task.job_id)
    if job:
        all_tasks = db.get_tasks_by_job(task.job_id)
        completed_count = sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED)
        failed_count = sum(1 for t in all_tasks if t.status == TaskStatus.FAILED)

        job.task_completed = completed_count
        job.task_failed = failed_count
        job.progress = (completed_count / job.task_total * 100) if job.task_total > 0 else 0

        # 检查是否所有任务都完成
        if completed_count + failed_count >= job.task_total:
            job.status = JobStatus.FAILED
            job.finished_at = datetime.now()
            job.error_message = error_message

        db.update_job(job)
        logger.info(f"Job {job.id} task failed: {completed_count}/{job.task_total} completed, {failed_count} failed")

    return {"ok": True}


@app.get("/api/tasks/{task_id}/log", tags=["Tasks"])
async def get_task_log(task_id: str):
    """获取Task日志"""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    from pathlib import Path

    # 首先尝试从data/logs目录读取 (Worker上传的日志)
    log_path = Path("data/logs") / f"{task_id}.log"

    # 如果不存在，尝试旧路径
    if not log_path.exists():
        log_path = Path("logs") / f"{task_id}.log"

    if log_path.exists():
        try:
            content = log_path.read_text(encoding="utf-8")
            return {"log": content, "task_id": task_id}
        except Exception as e:
            return {"log": f"Error reading log: {e}", "task_id": task_id}

    return {"log": "Log not available yet. Waiting for worker to upload...", "task_id": task_id}


@app.post("/api/tasks/{task_id}/retry", tags=["Tasks"])
async def retry_task(task_id: str):
    """重试失败的Task"""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status != TaskStatus.FAILED:
        raise HTTPException(400, "Can only retry failed tasks")

    # 重置Task状态
    db.update_task_status(task_id, TaskStatus.PENDING)
    task.assigned_worker = None
    task.started_at = None
    task.finished_at = None
    task.progress = 0
    task.exit_code = None
    task.error_message = None
    db.update_task(task)

    return {"ok": True}


@app.post("/api/tasks/{task_id}/cancel", tags=["Tasks"])
async def cancel_task(task_id: str):
    """取消Task"""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status not in (TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.RUNNING):
        raise HTTPException(400, "Cannot cancel task in current state")

    # 释放Worker
    if task.assigned_worker:
        worker = db.get_worker(task.assigned_worker)
        if worker:
            worker.status = WorkerStatus.IDLE
            worker.current_task = None
            db.update_worker(worker)

    db.update_task_status(task_id, TaskStatus.FAILED, error_message="Cancelled by user")

    return {"ok": True}


@app.post("/api/tasks/{task_id}/suspend", tags=["Tasks"])
async def suspend_task(task_id: str):
    """暂停Task (标记为失败，可重试)"""
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status != TaskStatus.RUNNING:
        raise HTTPException(400, "Can only suspend running tasks")

    # 释放Worker
    if task.assigned_worker:
        worker = db.get_worker(task.assigned_worker)
        if worker:
            worker.status = WorkerStatus.IDLE
            worker.current_task = None
            db.update_worker(worker)

    db.update_task_status(task_id, TaskStatus.FAILED, error_message="Suspended by user")

    return {"ok": True}


# ============ Workers API ============

@app.post("/api/workers/register", tags=["Workers"])
async def register_worker(data: dict):
    """Worker注册"""
    from src.core.models import Worker
    
    worker = Worker(
        id=data["id"],
        name=data["name"],
        hostname=data["hostname"],
        ip_address=data["ip_address"],
        pools=data.get("pools", ["default"]),
        capabilities=data.get("capabilities", []),
        cpu_cores=data.get("cpu_cores", 0),
        memory_total=data.get("memory_total", 0),
        version=data.get("version", ""),
        status=WorkerStatus.IDLE,
        last_heartbeat=datetime.now(),
    )
    
    db.upsert_worker(worker)
    logger.info(f"Worker registered: {worker.name} ({worker.id})")
    
    return {"ok": True, "worker_id": worker.id}


@app.post("/api/workers/{worker_id}/heartbeat", tags=["Workers"])
async def worker_heartbeat(worker_id: str, data: dict):
    """Worker心跳"""
    worker = db.get_worker(worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found, please re-register")
    
    db.update_worker_heartbeat(worker_id, data)
    return {"ok": True}


@app.post("/api/workers/{worker_id}/request-task", tags=["Workers"])
async def request_task(worker_id: str):
    """Worker请求任务"""
    worker = db.get_worker(worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")
    
    # 确保Worker状态为IDLE
    if worker.status != WorkerStatus.IDLE:
        return None
    
    # 查找任务
    task = db.get_next_task_for_worker(worker)
    if not task:
        return None
    
    # 分配任务
    task.status = TaskStatus.ASSIGNED
    task.assigned_worker = worker_id
    db.update_task(task)
    
    # 更新Worker状态
    worker.status = WorkerStatus.BUSY
    worker.current_task = task.id
    db.update_worker(worker)
    
    # 获取Job信息
    job = db.get_job(task.job_id)
    
    # 更新Job状态
    if job and job.status == JobStatus.QUEUED:
        job.status = JobStatus.ACTIVE
        job.started_at = datetime.now()
        db.update_job(job)
    
    logger.info(f"Task {task.id} assigned to {worker.name}")
    
    return {
        "task": task.model_dump(),
        "job": job.model_dump() if job else None,
    }


@app.get("/api/workers", tags=["Workers"])
async def list_workers():
    """获取所有Worker"""
    return db.get_workers()


@app.get("/api/workers/{worker_id}", tags=["Workers"])
async def get_worker(worker_id: str):
    """获取Worker详情"""
    worker = db.get_worker(worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")
    return worker


@app.post("/api/workers/{worker_id}/disable", tags=["Workers"])
async def disable_worker(worker_id: str):
    """禁用Worker"""
    worker = db.get_worker(worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")
    
    worker.status = WorkerStatus.DISABLED
    db.update_worker(worker)
    return {"status": "disabled"}


@app.post("/api/workers/{worker_id}/enable", tags=["Workers"])
async def enable_worker(worker_id: str):
    """启用Worker"""
    worker = db.get_worker(worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")

    worker.status = WorkerStatus.IDLE
    db.update_worker(worker)
    return {"status": "enabled"}


@app.delete("/api/workers/{worker_id}", tags=["Workers"])
async def delete_worker(worker_id: str):
    """删除Worker"""
    worker = db.get_worker(worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")

    # 只能删除离线的Worker
    if worker.status not in (WorkerStatus.OFFLINE, WorkerStatus.DISABLED):
        raise HTTPException(400, "Can only delete offline or disabled workers")

    db.delete_worker(worker_id)
    return {"status": "deleted"}


@app.get("/api/workers/{worker_id}/log", tags=["Workers"])
async def get_worker_log(worker_id: str):
    """获取Worker当前任务的日志"""
    worker = db.get_worker(worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")

    current_task = worker.current_task
    log_content = ""

    if current_task:
        from pathlib import Path

        # 首先尝试data/logs (Worker上传的日志)
        log_path = Path("data/logs") / f"{current_task}.log"
        if not log_path.exists():
            log_path = Path("logs") / f"{current_task}.log"

        if log_path.exists():
            try:
                log_content = log_path.read_text(encoding="utf-8")
            except Exception as e:
                log_content = f"Error reading log: {e}"
        else:
            log_content = "Waiting for log data..."

    return {
        "log": log_content,
        "worker_id": worker_id,
        "current_task": current_task,
        "status": worker.status
    }


# ============ Plugins API ============

@app.get("/api/plugins", tags=["Plugins"])
async def list_plugins():
    """获取可用插件列表"""
    return registry.list_plugins()


@app.get("/api/plugins/{plugin_name}", tags=["Plugins"])
async def get_plugin_info(plugin_name: str):
    """获取插件详情"""
    plugin = registry.get(plugin_name)
    if not plugin:
        raise HTTPException(404, "Plugin not found")
    return plugin.get_info()


# ============ Stats API ============

@app.get("/api/stats", tags=["Stats"])
async def get_stats():
    """获取系统统计"""
    return db.get_stats()


# ============ WebSocket ============

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket实时更新"""
    await ws_manager.connect(websocket)
    try:
        while True:
            # 保持连接，接收心跳
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ============ 入口 ============

def main():
    """运行服务器"""
    import uvicorn
    uvicorn.run(
        "src.server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
