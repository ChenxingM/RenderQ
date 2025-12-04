"""
RenderQ - 核心数据模型
"""
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any
import uuid


class JobStatus(str, Enum):
    """作业状态"""
    PENDING = "pending"          # 等待调度
    QUEUED = "queued"            # 已入队，等待Worker
    ACTIVE = "active"            # 正在渲染
    COMPLETED = "completed"      # 完成
    FAILED = "failed"            # 失败
    SUSPENDED = "suspended"      # 暂停
    CANCELLED = "cancelled"      # 取消


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"          # 等待分配
    ASSIGNED = "assigned"        # 已分配给Worker
    RUNNING = "running"          # 正在执行
    COMPLETED = "completed"      # 完成
    FAILED = "failed"            # 失败


class WorkerStatus(str, Enum):
    """Worker状态"""
    IDLE = "idle"                # 空闲
    BUSY = "busy"                # 忙碌
    OFFLINE = "offline"          # 离线
    DISABLED = "disabled"        # 禁用


# ============ Job 相关 ============

class JobSubmission(BaseModel):
    """提交Job时的输入数据"""
    name: str = Field(..., description="作业名称")
    plugin: str = Field(..., description="插件类型: aftereffects, max, blender等")
    priority: int = Field(default=50, ge=0, le=100, description="优先级0-100")
    pool: str = Field(default="default", description="Worker池")
    
    # 插件特定参数
    plugin_data: dict[str, Any] = Field(default_factory=dict)
    
    # 可选参数
    dependent_on: list[str] = Field(default_factory=list, description="依赖的Job ID列表")
    metadata: dict[str, Any] = Field(default_factory=dict, description="用户自定义元数据")


class Job(BaseModel):
    """完整的Job对象"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    plugin: str
    priority: int = 50
    pool: str = "default"
    
    plugin_data: dict[str, Any] = Field(default_factory=dict)
    
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    
    task_total: int = 0
    task_completed: int = 0
    task_failed: int = 0
    
    dependent_on: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    submitted_by: str | None = None
    submitted_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    
    error_message: str | None = None

    class Config:
        use_enum_values = True


# ============ Task 相关 ============

class Task(BaseModel):
    """Job的子任务"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    index: int = 0                           # 任务序号
    
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    
    # 由插件生成的执行命令
    command: list[str] = Field(default_factory=list)
    working_dir: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    
    # 帧范围 (可选)
    frame_start: int | None = None
    frame_end: int | None = None
    
    assigned_worker: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    
    exit_code: int | None = None
    error_message: str | None = None
    log_path: str | None = None

    class Config:
        use_enum_values = True


# ============ Worker 相关 ============

class WorkerRegistration(BaseModel):
    """Worker注册信息"""
    id: str
    name: str
    hostname: str
    ip_address: str
    pools: list[str] = Field(default_factory=lambda: ["default"])
    capabilities: list[str] = Field(default_factory=list)
    cpu_cores: int = 0
    memory_total: int = 0
    version: str = ""


class WorkerHeartbeat(BaseModel):
    """Worker心跳数据"""
    status: WorkerStatus
    current_task: str | None = None
    cpu_usage: float = 0.0
    memory_used: int = 0
    gpu_usage: float | None = None


class Worker(BaseModel):
    """工作节点"""
    id: str
    name: str
    hostname: str
    ip_address: str
    
    status: WorkerStatus = WorkerStatus.OFFLINE
    current_task: str | None = None
    
    pools: list[str] = Field(default_factory=lambda: ["default"])
    capabilities: list[str] = Field(default_factory=list)
    
    cpu_cores: int = 0
    cpu_usage: float = 0.0
    memory_total: int = 0
    memory_used: int = 0
    
    last_heartbeat: datetime | None = None
    version: str = ""

    class Config:
        use_enum_values = True


# ============ API 响应 ============

class TaskAssignment(BaseModel):
    """分配给Worker的任务"""
    task: Task
    job: Job


class ProgressUpdate(BaseModel):
    """进度更新"""
    progress: float
    current_frame: int | None = None
    message: str | None = None


class TaskResult(BaseModel):
    """任务执行结果"""
    exit_code: int = 0
    error_message: str | None = None
