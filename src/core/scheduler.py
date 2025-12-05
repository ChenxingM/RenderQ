"""
RenderQ - 任务调度器
负责Job到Task的转换、Task分配、依赖管理
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .models import Job, Task, Worker, JobStatus, TaskStatus, WorkerStatus
from .database import Database
from .events import event_bus, Event, EventType

if TYPE_CHECKING:
    from src.plugins.base import RenderPlugin

logger = logging.getLogger(__name__)


class Scheduler:
    """任务调度器"""
    
    def __init__(self, db: Database, plugins: dict[str, "RenderPlugin"] = None):
        self.db = db
        self.plugins = plugins or {}
        self.running = False
        
        # 配置
        self.poll_interval = 1.0          # 轮询间隔(秒)
        self.worker_timeout = 60          # Worker心跳超时(秒)
        self.max_task_retries = 3         # Task最大重试次数
    
    def register_plugin(self, plugin: "RenderPlugin"):
        """注册渲染插件"""
        self.plugins[plugin.name] = plugin
        logger.info(f"Registered plugin: {plugin.name}")
    
    async def start(self):
        """启动调度器"""
        self.running = True
        logger.info("Scheduler started")

        while self.running:
            try:
                # NOTE: _schedule_pending_jobs() 和 _assign_tasks() 已禁用
                # 因为 submit_job 已经创建 Tasks，Worker 的 request-task 处理分配
                # 这两个函数与 Worker 的拉取机制冲突，导致任务卡在 "assigned" 状态
                # await self._schedule_pending_jobs()
                # await self._assign_tasks()
                await self._check_worker_timeouts()
                await self._update_job_progress()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")

            await asyncio.sleep(self.poll_interval)
    
    def stop(self):
        """停止调度器"""
        self.running = False
        logger.info("Scheduler stopped")
    
    async def _schedule_pending_jobs(self):
        """处理PENDING状态的Jobs，生成Tasks"""
        pending_jobs = self.db.get_jobs_by_status(JobStatus.PENDING)
        
        for job in pending_jobs:
            # 检查依赖是否满足
            if not self._check_dependencies(job):
                continue
            
            # 获取插件
            plugin = self.plugins.get(job.plugin)
            if not plugin:
                logger.error(f"Plugin not found: {job.plugin}")
                self.db.update_job_status(job.id, JobStatus.FAILED, f"Plugin not found: {job.plugin}")
                continue
            
            # 验证参数
            valid, error = plugin.validate(job.plugin_data)
            if not valid:
                logger.error(f"Job validation failed: {error}")
                self.db.update_job_status(job.id, JobStatus.FAILED, error)
                continue
            
            # 创建Tasks
            try:
                tasks = plugin.create_tasks(job)
                for task in tasks:
                    task.command = plugin.build_command(task, job)
                    self.db.add_task(task)
                
                # 更新Job状态
                job.status = JobStatus.QUEUED
                job.task_total = len(tasks)
                self.db.update_job(job)
                
                logger.info(f"Job {job.id} queued with {len(tasks)} tasks")
                await event_bus.emit_async(Event(EventType.JOB_STARTED, {"job_id": job.id}))
                
            except Exception as e:
                logger.error(f"Failed to create tasks for job {job.id}: {e}")
                self.db.update_job_status(job.id, JobStatus.FAILED, str(e))
    
    async def _assign_tasks(self):
        """将Tasks分配给空闲Worker"""
        idle_workers = self.db.get_workers_by_status(WorkerStatus.IDLE)
        
        for worker in idle_workers:
            # 检查Worker能力是否匹配
            task = self._find_task_for_worker(worker)
            if not task:
                continue
            
            # 分配Task
            task.status = TaskStatus.ASSIGNED
            task.assigned_worker = worker.id
            self.db.update_task(task)
            
            # 更新Worker状态
            worker.status = WorkerStatus.BUSY
            worker.current_task = task.id
            self.db.update_worker(worker)
            
            # 更新Job状态为ACTIVE
            job = self.db.get_job(task.job_id)
            if job and job.status == JobStatus.QUEUED:
                job.status = JobStatus.ACTIVE
                job.started_at = datetime.now()
                self.db.update_job(job)
            
            logger.info(f"Task {task.id} assigned to worker {worker.name}")
            await event_bus.emit_async(Event(EventType.TASK_ASSIGNED, {
                "task_id": task.id,
                "worker_id": worker.id,
                "job_id": task.job_id
            }))
    
    def _find_task_for_worker(self, worker: Worker) -> Task | None:
        """找到适合Worker的Task"""
        # 获取Worker能处理的插件类型
        capabilities = set(worker.capabilities) if worker.capabilities else set()
        
        # 查找符合条件的Task
        # 优先级: 高优先级Job > 提交时间早
        queued_jobs = self.db.get_jobs_by_status(JobStatus.QUEUED)
        active_jobs = self.db.get_jobs_by_status(JobStatus.ACTIVE)
        
        all_jobs = sorted(
            queued_jobs + active_jobs,
            key=lambda j: (-j.priority, j.submitted_at)
        )
        
        for job in all_jobs:
            # 检查pool
            if job.pool not in worker.pools:
                continue
            
            # 检查能力
            if capabilities and job.plugin not in capabilities:
                continue
            
            # 查找该Job下的pending task
            tasks = self.db.get_tasks_by_job(job.id)
            for task in tasks:
                if task.status == TaskStatus.PENDING:
                    return task
        
        return None
    
    def _check_dependencies(self, job: Job) -> bool:
        """检查Job依赖是否满足"""
        for dep_id in job.dependent_on:
            dep_job = self.db.get_job(dep_id)
            if not dep_job or dep_job.status != JobStatus.COMPLETED:
                return False
        return True
    
    async def _check_worker_timeouts(self):
        """检查Worker心跳超时"""
        workers = self.db.get_workers()
        now = datetime.now()
        timeout = timedelta(seconds=self.worker_timeout)
        
        for worker in workers:
            if worker.status == WorkerStatus.OFFLINE:
                continue
            
            if not worker.last_heartbeat:
                continue
            
            if now - worker.last_heartbeat > timeout:
                logger.warning(f"Worker {worker.name} timed out")
                
                # 如果有正在执行的Task，标记为失败并重新排队
                if worker.current_task:
                    task = self.db.get_task(worker.current_task)
                    if task and task.status == TaskStatus.RUNNING:
                        task.status = TaskStatus.PENDING
                        task.assigned_worker = None
                        self.db.update_task(task)
                        logger.info(f"Task {task.id} re-queued due to worker timeout")
                
                # 标记Worker离线
                self.db.mark_worker_offline(worker.id)
                await event_bus.emit_async(Event(EventType.WORKER_DISCONNECTED, {
                    "worker_id": worker.id
                }))
    
    async def _update_job_progress(self):
        """更新Job进度"""
        active_jobs = self.db.get_jobs_by_status(JobStatus.ACTIVE)
        
        for job in active_jobs:
            tasks = self.db.get_tasks_by_job(job.id)
            if not tasks:
                continue
            
            completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
            failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
            total = len(tasks)
            
            # 计算总进度 (包含正在执行的Task的部分进度)
            progress = 0.0
            for task in tasks:
                if task.status == TaskStatus.COMPLETED:
                    progress += 100.0
                elif task.status == TaskStatus.RUNNING:
                    progress += task.progress
            
            if total > 0:
                progress = progress / total
            
            # 更新Job
            job.progress = progress
            job.task_completed = completed
            job.task_failed = failed
            
            # 检查是否完成
            if completed + failed >= total:
                if failed == 0:
                    job.status = JobStatus.COMPLETED
                    job.finished_at = datetime.now()
                    logger.info(f"Job {job.id} completed")

                    # 创建后续编码任务
                    await self._create_follow_up_jobs(job)

                    await event_bus.emit_async(Event(EventType.JOB_COMPLETED, {"job_id": job.id}))
                elif failed >= total or failed > self.max_task_retries:
                    job.status = JobStatus.FAILED
                    job.finished_at = datetime.now()
                    job.error_message = f"{failed} tasks failed"
                    logger.error(f"Job {job.id} failed")
                    await event_bus.emit_async(Event(EventType.JOB_FAILED, {
                        "job_id": job.id,
                        "error": job.error_message
                    }))
            
            self.db.update_job(job)

    async def _create_follow_up_jobs(self, job: Job):
        """创建后续任务 (如编码任务)"""
        plugin = self.plugins.get(job.plugin)
        if not plugin:
            return

        # 检查插件是否有 get_encoding_jobs 方法
        if not hasattr(plugin, 'get_encoding_jobs'):
            return

        try:
            encoding_jobs = plugin.get_encoding_jobs(job)
            for job_data in encoding_jobs:
                from datetime import datetime
                import uuid

                new_job = Job(
                    id=str(uuid.uuid4()),
                    name=job_data.get("name", f"{job.name} - Encode"),
                    plugin=job_data.get("plugin", "ffmpeg"),
                    priority=job_data.get("priority", job.priority),
                    pool=job_data.get("pool", job.pool),
                    plugin_data=job_data.get("plugin_data", {}),
                    dependent_on=job_data.get("dependent_on", []),
                    metadata=job_data.get("metadata", {}),
                    submitted_at=datetime.now(),
                )

                self.db.add_job(new_job)
                logger.info(f"Created follow-up job: {new_job.name} (depends on {job.id})")

        except Exception as e:
            logger.error(f"Failed to create follow-up jobs for {job.id}: {e}")

    # ============ 手动操作 ============
    
    async def suspend_job(self, job_id: str):
        """暂停Job"""
        job = self.db.get_job(job_id)
        if not job:
            return False
        
        if job.status in (JobStatus.PENDING, JobStatus.QUEUED, JobStatus.ACTIVE):
            self.db.update_job_status(job_id, JobStatus.SUSPENDED)
            await event_bus.emit_async(Event(EventType.JOB_SUSPENDED, {"job_id": job_id}))
            return True
        return False
    
    async def resume_job(self, job_id: str):
        """恢复Job"""
        job = self.db.get_job(job_id)
        if not job:
            return False
        
        if job.status == JobStatus.SUSPENDED:
            # 根据Tasks状态决定恢复到哪个状态
            tasks = self.db.get_tasks_by_job(job_id)
            has_pending = any(t.status == TaskStatus.PENDING for t in tasks)
            
            if has_pending:
                self.db.update_job_status(job_id, JobStatus.QUEUED)
            else:
                self.db.update_job_status(job_id, JobStatus.ACTIVE)
            
            await event_bus.emit_async(Event(EventType.JOB_RESUMED, {"job_id": job_id}))
            return True
        return False
    
    async def cancel_job(self, job_id: str):
        """取消Job"""
        job = self.db.get_job(job_id)
        if not job:
            return False
        
        self.db.update_job_status(job_id, JobStatus.CANCELLED)
        
        # TODO: 通知Worker停止相关Task
        
        await event_bus.emit_async(Event(EventType.JOB_CANCELLED, {"job_id": job_id}))
        return True
    
    async def retry_job(self, job_id: str):
        """重试失败的Job"""
        job = self.db.get_job(job_id)
        if not job or job.status != JobStatus.FAILED:
            return False
        
        # 重置失败的Tasks
        tasks = self.db.get_tasks_by_job(job_id)
        for task in tasks:
            if task.status == TaskStatus.FAILED:
                task.status = TaskStatus.PENDING
                task.assigned_worker = None
                task.error_message = None
                task.exit_code = None
                self.db.update_task(task)
        
        # 重置Job状态
        job.status = JobStatus.QUEUED
        job.task_failed = 0
        job.error_message = None
        job.finished_at = None
        self.db.update_job(job)
        
        return True
