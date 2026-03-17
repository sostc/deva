"""临时的可执行单元模块，替代已删除的 strategy.executable_unit"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import time


@dataclass
class ExecutableUnitMetadata:
    """可执行单元元数据"""
    id: str = ""
    name: str = ""
    description: str = ""
    func_code: str = ""
    tags: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def touch(self):
        """更新时间戳"""
        self.updated_at = time.time()
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "func_code": self.func_code,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


@dataclass
class ExecutableUnitState:
    """可执行单元状态"""
    status: str = "stopped"
    start_time: float = 0
    last_activity_ts: float = 0
    error_count: int = 0
    last_error: str = ""
    last_error_ts: float = 0
    run_count: int = 0
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "status": self.status,
            "start_time": self.start_time,
            "last_activity_ts": self.last_activity_ts,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "last_error_ts": self.last_error_ts,
            "run_count": self.run_count
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ExecutableUnitState":
        """从字典创建"""
        return cls(
            status=data.get("status", "stopped"),
            start_time=data.get("start_time", 0),
            last_activity_ts=data.get("last_activity_ts", 0),
            error_count=data.get("error_count", 0),
            last_error=data.get("last_error", ""),
            last_error_ts=data.get("last_error_ts", 0),
            run_count=data.get("run_count", 0)
        )
    
    def record_error(self, error: str):
        """记录错误"""
        self.error_count += 1
        self.last_error = error
        self.last_error_ts = time.time()
    
    def record_success(self):
        """记录成功"""
        self.run_count += 1
        self.last_activity_ts = time.time()


class ExecutableUnit:
    """可执行单元基类"""
    
    def __init__(self, metadata: ExecutableUnitMetadata = None, state: ExecutableUnitState = None, func_name: str = "execute", stream_cache_size: int = 50):
        self._metadata = metadata or ExecutableUnitMetadata()
        self._state = state or ExecutableUnitState()
        self._func_code = ""
        self._compiled_func = None
        self._stop_event = None
        self._thread = None
        self._was_running = False
        self._func = None
    
    @property
    def id(self) -> str:
        return self._metadata.id
    
    @property
    def name(self) -> str:
        return self._metadata.name
    
    @property
    def is_running(self) -> bool:
        return self._state.status == "running"
    
    def start(self) -> dict:
        """启动"""
        return {"success": True}
    
    def stop(self) -> dict:
        """停止"""
        return {"success": True}
    
    def compile_code(self) -> dict:
        """编译代码"""
        return {"success": True}
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "metadata": {
                "id": self._metadata.id,
                "name": self._metadata.name,
                "description": self._metadata.description,
                "tags": self._metadata.tags,
                "created_at": self._metadata.created_at,
                "updated_at": self._metadata.updated_at
            },
            "state": self._state.to_dict(),
            "func_code": self._func_code
        }
