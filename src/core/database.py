"""
RenderQ - 数据库操作
使用SQLite，轻量且无需额外服务
"""
import sqlite3
import json
from datetime import datetime
from typing import Optional
from pathlib import Path
from contextlib import contextmanager
import threading

from .models import (
    Job, Task, Worker, 
    JobStatus, TaskStatus, WorkerStatus
)


class Database:
    """SQLite数据库封装"""
    
    def __init__(self, db_path: str = "renderq.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_tables()
    
    @property
    def conn(self) -> sqlite3.Connection:
        """每个线程独立的连接"""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(
                str(self.db_path), 
                check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
    
    @contextmanager
    def transaction(self):
        """事务上下文管理器"""
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
    
    def _init_tables(self):
        """初始化数据库表"""
        with self.transaction():
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    plugin TEXT NOT NULL,
                    priority INTEGER DEFAULT 50,
                    pool TEXT DEFAULT 'default',
                    plugin_data TEXT,
                    status TEXT DEFAULT 'pending',
                    progress REAL DEFAULT 0,
                    task_total INTEGER DEFAULT 0,
                    task_completed INTEGER DEFAULT 0,
                    task_failed INTEGER DEFAULT 0,
                    dependent_on TEXT,
                    metadata TEXT,
                    submitted_by TEXT,
                    submitted_at TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    error_message TEXT
                );
                
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    idx INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    progress REAL DEFAULT 0,
                    command TEXT,
                    working_dir TEXT,
                    environment TEXT,
                    frame_start INTEGER,
                    frame_end INTEGER,
                    metadata TEXT,
                    assigned_worker TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    exit_code INTEGER,
                    error_message TEXT,
                    log_path TEXT,
                    FOREIGN KEY (job_id) REFERENCES jobs(id)
                );
                
                CREATE TABLE IF NOT EXISTS workers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    hostname TEXT,
                    ip_address TEXT,
                    status TEXT DEFAULT 'offline',
                    current_task TEXT,
                    pools TEXT,
                    capabilities TEXT,
                    cpu_cores INTEGER DEFAULT 0,
                    cpu_usage REAL DEFAULT 0,
                    memory_total INTEGER DEFAULT 0,
                    memory_used INTEGER DEFAULT 0,
                    last_heartbeat TEXT,
                    version TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority DESC);
                CREATE INDEX IF NOT EXISTS idx_tasks_job_id ON tasks(job_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status);
            """)
    
    # ============ Job 操作 ============
    
    def add_job(self, job: Job) -> Job:
        """添加新Job"""
        with self.transaction():
            self.conn.execute("""
                INSERT INTO jobs (
                    id, name, plugin, priority, pool, plugin_data, status,
                    progress, task_total, task_completed, task_failed,
                    dependent_on, metadata, submitted_by, submitted_at,
                    started_at, finished_at, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.id, job.name, job.plugin, job.priority, job.pool,
                json.dumps(job.plugin_data),
                job.status,
                job.progress, job.task_total, job.task_completed, job.task_failed,
                json.dumps(job.dependent_on),
                json.dumps(job.metadata),
                job.submitted_by,
                job.submitted_at.isoformat() if job.submitted_at else None,
                job.started_at.isoformat() if job.started_at else None,
                job.finished_at.isoformat() if job.finished_at else None,
                job.error_message
            ))
        return job
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """获取单个Job"""
        row = self.conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return self._row_to_job(row) if row else None
    
    def get_jobs(
        self, 
        status: Optional[JobStatus] = None, 
        limit: int = 100,
        offset: int = 0
    ) -> list[Job]:
        """获取Job列表"""
        if status:
            rows = self.conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY priority DESC, submitted_at ASC LIMIT ? OFFSET ?",
                (status, limit, offset)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM jobs ORDER BY submitted_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
        return [self._row_to_job(row) for row in rows]
    
    def get_jobs_by_status(self, status: JobStatus) -> list[Job]:
        """按状态获取Jobs"""
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY priority DESC, submitted_at ASC",
            (status,)
        ).fetchall()
        return [self._row_to_job(row) for row in rows]
    
    def update_job(self, job: Job):
        """更新Job"""
        with self.transaction():
            self.conn.execute("""
                UPDATE jobs SET
                    name = ?, plugin = ?, priority = ?, pool = ?,
                    plugin_data = ?, status = ?, progress = ?,
                    task_total = ?, task_completed = ?, task_failed = ?,
                    dependent_on = ?, metadata = ?,
                    started_at = ?, finished_at = ?, error_message = ?
                WHERE id = ?
            """, (
                job.name, job.plugin, job.priority, job.pool,
                json.dumps(job.plugin_data),
                job.status,
                job.progress,
                job.task_total, job.task_completed, job.task_failed,
                json.dumps(job.dependent_on),
                json.dumps(job.metadata),
                job.started_at.isoformat() if job.started_at else None,
                job.finished_at.isoformat() if job.finished_at else None,
                job.error_message,
                job.id
            ))
    
    def update_job_status(self, job_id: str, status: JobStatus, error_message: str = None):
        """更新Job状态"""
        with self.transaction():
            now = datetime.now().isoformat()
            if status == JobStatus.ACTIVE:
                self.conn.execute(
                    "UPDATE jobs SET status = ?, started_at = ? WHERE id = ?",
                    (status, now, job_id)
                )
            elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                self.conn.execute(
                    "UPDATE jobs SET status = ?, finished_at = ?, error_message = ? WHERE id = ?",
                    (status, now, error_message, job_id)
                )
            else:
                self.conn.execute(
                    "UPDATE jobs SET status = ? WHERE id = ?",
                    (status, job_id)
                )
    
    def delete_job(self, job_id: str):
        """删除Job及其Tasks"""
        with self.transaction():
            self.conn.execute("DELETE FROM tasks WHERE job_id = ?", (job_id,))
            self.conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    
    def _row_to_job(self, row: sqlite3.Row) -> Job:
        """Row转Job对象"""
        return Job(
            id=row["id"],
            name=row["name"],
            plugin=row["plugin"],
            priority=row["priority"],
            pool=row["pool"],
            plugin_data=json.loads(row["plugin_data"]) if row["plugin_data"] else {},
            status=row["status"],
            progress=row["progress"],
            task_total=row["task_total"],
            task_completed=row["task_completed"],
            task_failed=row["task_failed"],
            dependent_on=json.loads(row["dependent_on"]) if row["dependent_on"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            submitted_by=row["submitted_by"],
            submitted_at=datetime.fromisoformat(row["submitted_at"]) if row["submitted_at"] else None,
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            error_message=row["error_message"],
        )
    
    # ============ Task 操作 ============
    
    def add_task(self, task: Task) -> Task:
        """添加Task"""
        with self.transaction():
            self.conn.execute("""
                INSERT INTO tasks (
                    id, job_id, idx, status, progress, command, working_dir,
                    environment, frame_start, frame_end, metadata, assigned_worker,
                    started_at, finished_at, exit_code, error_message, log_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id, task.job_id, task.index,
                task.status, task.progress,
                json.dumps(task.command),
                task.working_dir,
                json.dumps(task.environment) if task.environment else None,
                task.frame_start, task.frame_end,
                json.dumps(task.metadata) if task.metadata else None,
                task.assigned_worker,
                task.started_at.isoformat() if task.started_at else None,
                task.finished_at.isoformat() if task.finished_at else None,
                task.exit_code, task.error_message, task.log_path
            ))
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取单个Task"""
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return self._row_to_task(row) if row else None
    
    def get_tasks_by_job(self, job_id: str) -> list[Task]:
        """获取Job的所有Tasks"""
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE job_id = ? ORDER BY idx",
            (job_id,)
        ).fetchall()
        return [self._row_to_task(row) for row in rows]
    
    def get_next_task_for_worker(self, worker: Worker) -> Optional[Task]:
        """获取适合Worker的下一个待处理Task"""
        # 获取可执行的Jobs (QUEUED或ACTIVE状态，在Worker的pool中)
        rows = self.conn.execute("""
            SELECT t.* FROM tasks t
            JOIN jobs j ON t.job_id = j.id
            WHERE t.status = 'pending'
              AND j.status IN ('queued', 'active')
              AND j.pool IN ({})
            ORDER BY j.priority DESC, j.submitted_at ASC, t.idx ASC
            LIMIT 1
        """.format(','.join('?' * len(worker.pools))), worker.pools).fetchall()
        
        return self._row_to_task(rows[0]) if rows else None
    
    def update_task(self, task: Task):
        """更新Task"""
        with self.transaction():
            self.conn.execute("""
                UPDATE tasks SET
                    status = ?, progress = ?, assigned_worker = ?,
                    started_at = ?, finished_at = ?,
                    exit_code = ?, error_message = ?, log_path = ?
                WHERE id = ?
            """, (
                task.status, task.progress, task.assigned_worker,
                task.started_at.isoformat() if task.started_at else None,
                task.finished_at.isoformat() if task.finished_at else None,
                task.exit_code, task.error_message, task.log_path,
                task.id
            ))
    
    def update_task_status(
        self, 
        task_id: str, 
        status: TaskStatus,
        started_at: datetime = None,
        finished_at: datetime = None,
        exit_code: int = None,
        error_message: str = None
    ):
        """更新Task状态"""
        with self.transaction():
            self.conn.execute("""
                UPDATE tasks SET status = ?, started_at = COALESCE(?, started_at),
                    finished_at = COALESCE(?, finished_at),
                    exit_code = COALESCE(?, exit_code),
                    error_message = COALESCE(?, error_message)
                WHERE id = ?
            """, (
                status,
                started_at.isoformat() if started_at else None,
                finished_at.isoformat() if finished_at else None,
                exit_code,
                error_message,
                task_id
            ))
    
    def update_task_progress(self, task_id: str, progress: float):
        """更新Task进度"""
        with self.transaction():
            self.conn.execute(
                "UPDATE tasks SET progress = ? WHERE id = ?",
                (progress, task_id)
            )
    
    def _row_to_task(self, row: sqlite3.Row) -> Task:
        """Row转Task对象"""
        return Task(
            id=row["id"],
            job_id=row["job_id"],
            index=row["idx"],
            status=row["status"],
            progress=row["progress"],
            command=json.loads(row["command"]) if row["command"] else [],
            working_dir=row["working_dir"],
            environment=json.loads(row["environment"]) if row["environment"] else {},
            frame_start=row["frame_start"],
            frame_end=row["frame_end"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            assigned_worker=row["assigned_worker"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            exit_code=row["exit_code"],
            error_message=row["error_message"],
            log_path=row["log_path"],
        )
    
    # ============ Worker 操作 ============
    
    def upsert_worker(self, worker: Worker):
        """插入或更新Worker"""
        with self.transaction():
            self.conn.execute("""
                INSERT INTO workers (
                    id, name, hostname, ip_address, status, current_task,
                    pools, capabilities, cpu_cores, cpu_usage,
                    memory_total, memory_used, last_heartbeat, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    hostname = excluded.hostname,
                    ip_address = excluded.ip_address,
                    status = excluded.status,
                    current_task = excluded.current_task,
                    pools = excluded.pools,
                    capabilities = excluded.capabilities,
                    cpu_cores = excluded.cpu_cores,
                    cpu_usage = excluded.cpu_usage,
                    memory_total = excluded.memory_total,
                    memory_used = excluded.memory_used,
                    last_heartbeat = excluded.last_heartbeat,
                    version = excluded.version
            """, (
                worker.id, worker.name, worker.hostname, worker.ip_address,
                worker.status, worker.current_task,
                json.dumps(worker.pools),
                json.dumps(worker.capabilities),
                worker.cpu_cores, worker.cpu_usage,
                worker.memory_total, worker.memory_used,
                worker.last_heartbeat.isoformat() if worker.last_heartbeat else None,
                worker.version
            ))
    
    def get_worker(self, worker_id: str) -> Optional[Worker]:
        """获取单个Worker"""
        row = self.conn.execute(
            "SELECT * FROM workers WHERE id = ?", (worker_id,)
        ).fetchone()
        return self._row_to_worker(row) if row else None
    
    def get_workers(self) -> list[Worker]:
        """获取所有Workers"""
        rows = self.conn.execute(
            "SELECT * FROM workers ORDER BY name"
        ).fetchall()
        return [self._row_to_worker(row) for row in rows]
    
    def get_workers_by_status(self, status: WorkerStatus) -> list[Worker]:
        """按状态获取Workers"""
        rows = self.conn.execute(
            "SELECT * FROM workers WHERE status = ?", (status,)
        ).fetchall()
        return [self._row_to_worker(row) for row in rows]
    
    def update_worker(self, worker: Worker):
        """更新Worker"""
        self.upsert_worker(worker)
    
    def update_worker_heartbeat(self, worker_id: str, heartbeat: dict):
        """更新Worker心跳"""
        with self.transaction():
            self.conn.execute("""
                UPDATE workers SET
                    status = ?, current_task = ?,
                    cpu_usage = ?, memory_used = ?,
                    last_heartbeat = ?
                WHERE id = ?
            """, (
                heartbeat.get("status", "idle"),
                heartbeat.get("current_task"),
                heartbeat.get("cpu_usage", 0),
                heartbeat.get("memory_used", 0),
                datetime.now().isoformat(),
                worker_id
            ))
    
    def mark_worker_offline(self, worker_id: str):
        """标记Worker离线"""
        with self.transaction():
            self.conn.execute(
                "UPDATE workers SET status = 'offline', current_task = NULL WHERE id = ?",
                (worker_id,)
            )

    def delete_worker(self, worker_id: str):
        """删除Worker"""
        with self.transaction():
            self.conn.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
    
    def _row_to_worker(self, row: sqlite3.Row) -> Worker:
        """Row转Worker对象"""
        return Worker(
            id=row["id"],
            name=row["name"],
            hostname=row["hostname"],
            ip_address=row["ip_address"],
            status=row["status"],
            current_task=row["current_task"],
            pools=json.loads(row["pools"]) if row["pools"] else ["default"],
            capabilities=json.loads(row["capabilities"]) if row["capabilities"] else [],
            cpu_cores=row["cpu_cores"],
            cpu_usage=row["cpu_usage"],
            memory_total=row["memory_total"],
            memory_used=row["memory_used"],
            last_heartbeat=datetime.fromisoformat(row["last_heartbeat"]) if row["last_heartbeat"] else None,
            version=row["version"],
        )
    
    # ============ 统计 ============
    
    def get_stats(self) -> dict:
        """获取系统统计"""
        job_stats = self.conn.execute("""
            SELECT status, COUNT(*) as count FROM jobs GROUP BY status
        """).fetchall()
        
        worker_stats = self.conn.execute("""
            SELECT status, COUNT(*) as count FROM workers GROUP BY status
        """).fetchall()
        
        return {
            "jobs": {row["status"]: row["count"] for row in job_stats},
            "workers": {row["status"]: row["count"] for row in worker_stats},
        }
