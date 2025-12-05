"""
RenderQ - 事件系统
用于组件间通信和WebSocket推送
"""
from typing import Callable, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import asyncio
import logging

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """事件类型"""
    # Job 事件
    JOB_SUBMITTED = "job.submitted"
    JOB_STARTED = "job.started"
    JOB_PROGRESS = "job.progress"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_CANCELLED = "job.cancelled"
    JOB_SUSPENDED = "job.suspended"
    JOB_RESUMED = "job.resumed"
    
    # Task 事件
    TASK_ASSIGNED = "task.assigned"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    
    # Worker 事件
    WORKER_CONNECTED = "worker.connected"
    WORKER_DISCONNECTED = "worker.disconnected"
    WORKER_HEARTBEAT = "worker.heartbeat"


@dataclass
class Event:
    """事件对象"""
    type: EventType
    data: dict[str, Any]
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


class EventBus:
    """事件总线 - 发布/订阅模式"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._handlers: dict[EventType, list[Callable]] = {}
        self._async_handlers: dict[EventType, list[Callable]] = {}
        self._global_handlers: list[Callable] = []
        self._async_global_handlers: list[Callable] = []
        self._initialized = True
    
    def subscribe(self, event_type: EventType, handler: Callable):
        """订阅特定事件"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def subscribe_async(self, event_type: EventType, handler: Callable):
        """订阅特定事件 (异步)"""
        if event_type not in self._async_handlers:
            self._async_handlers[event_type] = []
        self._async_handlers[event_type].append(handler)
    
    def subscribe_all(self, handler: Callable):
        """订阅所有事件"""
        self._global_handlers.append(handler)
    
    def subscribe_all_async(self, handler: Callable):
        """订阅所有事件 (异步)"""
        self._async_global_handlers.append(handler)
    
    def unsubscribe(self, event_type: EventType, handler: Callable):
        """取消订阅"""
        if event_type in self._handlers:
            self._handlers[event_type].remove(handler)
        if event_type in self._async_handlers:
            self._async_handlers[event_type].remove(handler)
    
    def emit(self, event: Event):
        """发送事件 (同步)"""
        # 特定类型的处理器
        for handler in self._handlers.get(event.type, []):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")
        
        # 全局处理器
        for handler in self._global_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Global event handler error: {e}")
    
    async def emit_async(self, event: Event):
        """发送事件 (异步)"""
        # 同步处理器
        self.emit(event)
        
        # 异步特定类型处理器
        for handler in self._async_handlers.get(event.type, []):
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Async event handler error: {e}")
        
        # 异步全局处理器
        for handler in self._async_global_handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Async global event handler error: {e}")
    
    def clear(self):
        """清除所有订阅"""
        self._handlers.clear()
        self._async_handlers.clear()
        self._global_handlers.clear()
        self._async_global_handlers.clear()


# 全局事件总线实例
event_bus = EventBus()


# 便捷函数
def emit_job_submitted(job_id: str, job_name: str):
    event_bus.emit(Event(EventType.JOB_SUBMITTED, {"job_id": job_id, "name": job_name}))

def emit_job_progress(job_id: str, progress: float):
    event_bus.emit(Event(EventType.JOB_PROGRESS, {"job_id": job_id, "progress": progress}))

def emit_job_completed(job_id: str):
    event_bus.emit(Event(EventType.JOB_COMPLETED, {"job_id": job_id}))

def emit_job_failed(job_id: str, error: str):
    event_bus.emit(Event(EventType.JOB_FAILED, {"job_id": job_id, "error": error}))

def emit_task_progress(task_id: str, job_id: str, progress: float):
    event_bus.emit(Event(EventType.TASK_PROGRESS, {
        "task_id": task_id, "job_id": job_id, "progress": progress
    }))

def emit_worker_connected(worker_id: str, worker_name: str):
    event_bus.emit(Event(EventType.WORKER_CONNECTED, {
        "worker_id": worker_id, "name": worker_name
    }))

def emit_worker_disconnected(worker_id: str):
    event_bus.emit(Event(EventType.WORKER_DISCONNECTED, {"worker_id": worker_id}))
