"""公共基类模块(Base Module)

提供策略、数据源等模块的公共基类和接口定义。

================================================================================
架构设计
================================================================================

【继承体系】
┌─────────────────────────────────────────────────────────────────────────────┐
│  BaseMetadata (元数据基类)                                                   │
│       │                                                                     │
│       ├── DataSourceMetadata                                                │
│       └── StrategyMetadata                                                  │
│                                                                             │
│  BaseState (状态基类)                                                        │
│       │                                                                     │
│       ├── DataSourceState                                                   │
│       └── ExecutionState                                                    │
│                                                                             │
│  BaseManager (管理器基类)                                                    │
│       │                                                                     │
│       ├── DataSourceManager                                                 │
│       └── StrategyManager                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar, Callable

T = TypeVar('T')


class BaseStatus(str, Enum):
    """状态枚举基类"""
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class BaseMetadata:
    """元数据基类
    
    所有实体（数据源、策略等）的公共元数据字段。
    """
    id: str
    name: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def touch(self):
        """更新修改时间"""
        self.updated_at = time.time()


@dataclass
class BaseState:
    """状态基类
    
    所有实体的公共状态字段。
    """
    status: str = "stopped"
    error_count: int = 0
    last_error: str = ""
    last_error_ts: float = 0
    
    def to_dict(self) -> dict:
        data = asdict(self)
        if self.last_error_ts > 0:
            data["last_error_ts_readable"] = datetime.fromtimestamp(self.last_error_ts).isoformat()
        return data
    
    def record_error(self, error: str):
        """记录错误"""
        self.error_count += 1
        self.last_error = error
        self.last_error_ts = time.time()


@dataclass
class BaseStats:
    """统计基类"""
    start_time: float = 0
    
    def to_dict(self) -> dict:
        uptime = time.time() - self.start_time if self.start_time > 0 else 0
        return {
            "uptime_seconds": uptime,
            "uptime_readable": _format_duration(uptime),
        }


def _format_duration(seconds: float) -> str:
    """格式化时长"""
    if seconds < 60:
        return f"{int(seconds)}秒"
    elif seconds < 3600:
        return f"{int(seconds / 60)}分钟"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}小时"
    else:
        return f"{int(seconds / 86400)}天"


class BaseManager(Generic[T]):
    """管理器基类
    
    提供单例模式、注册/注销、启动/停止等通用功能。
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._items: Dict[str, T] = {}
        self._items_lock = threading.Lock()
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> "BaseManager":
        return cls()
    
    def register(self, item: T) -> dict:
        """注册实体"""
        item_id = self._get_item_id(item)
        with self._items_lock:
            if item_id in self._items:
                return {"success": False, "error": "Item already registered"}
            
            existing = self._find_by_name(self._get_item_name(item))
            if existing:
                return {
                    "success": False, 
                    "error": f"Item with name '{self._get_item_name(item)}' already exists",
                    "existing_id": self._get_item_id(existing)
                }
            
            self._items[item_id] = item
            self._on_registered(item)
        
        return {"success": True, "id": item_id}
    
    def unregister(self, item_id: str) -> dict:
        """注销实体"""
        with self._items_lock:
            item = self._items.pop(item_id, None)
            if not item:
                return {"success": False, "error": "Item not found"}
            self._on_unregistered(item)
        return {"success": True}
    
    def get(self, item_id: str) -> Optional[T]:
        """获取实体"""
        return self._items.get(item_id)
    
    def get_by_name(self, name: str) -> Optional[T]:
        """按名称获取实体"""
        return self._find_by_name(name)
    
    def list_all(self) -> List[T]:
        """列出所有实体"""
        return list(self._items.values())
    
    def start(self, item_id: str) -> dict:
        """启动实体"""
        item = self.get(item_id)
        if not item:
            return {"success": False, "error": "Item not found"}
        return self._do_start(item)
    
    def stop(self, item_id: str) -> dict:
        """停止实体"""
        item = self.get(item_id)
        if not item:
            return {"success": False, "error": "Item not found"}
        return self._do_stop(item)
    
    def start_all(self) -> dict:
        """启动所有实体"""
        results = {"success": 0, "failed": 0, "skipped": 0}
        for item in self._items.values():
            if not self._is_running(item):
                result = self._do_start(item)
                if result.get("success"):
                    results["success"] += 1
                else:
                    results["failed"] += 1
            else:
                results["skipped"] += 1
        return results
    
    def stop_all(self) -> dict:
        """停止所有实体"""
        results = {"success": 0, "failed": 0, "skipped": 0}
        for item in self._items.values():
            if self._is_running(item):
                result = self._do_stop(item)
                if result.get("success"):
                    results["success"] += 1
                else:
                    results["failed"] += 1
            else:
                results["skipped"] += 1
        return results
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._items_lock:
            total = len(self._items)
            running = sum(1 for item in self._items.values() if self._is_running(item))
            stopped = sum(1 for item in self._items.values() if not self._is_running(item))
            error = sum(1 for item in self._items.values() if self._has_error(item))
        
        return {
            "total": total,
            "running_count": running,
            "stopped_count": stopped,
            "error_count": error,
        }
    
    def _get_item_id(self, item: T) -> str:
        """获取实体ID"""
        return getattr(item, 'id', str(id(item)))
    
    def _get_item_name(self, item: T) -> str:
        """获取实体名称"""
        return getattr(item, 'name', str(id(item)))
    
    def _find_by_name(self, name: str) -> Optional[T]:
        """按名称查找实体"""
        for item in self._items.values():
            if self._get_item_name(item) == name:
                return item
        return None
    
    def _is_running(self, item: T) -> bool:
        """检查实体是否运行中"""
        status = getattr(item, 'status', None)
        if status is None:
            state = getattr(item, 'state', None)
            if state:
                status = getattr(state, 'status', None)
        if hasattr(status, 'value'):
            status = status.value
        return status == "running"
    
    def _has_error(self, item: T) -> bool:
        """检查实体是否有错误"""
        status = getattr(item, 'status', None)
        if status is None:
            state = getattr(item, 'state', None)
            if state:
                status = getattr(state, 'status', None)
        if hasattr(status, 'value'):
            status = status.value
        return status == "error"
    
    def _on_registered(self, item: T):
        """注册后回调"""
        pass
    
    def _on_unregistered(self, item: T):
        """注销后回调"""
        pass
    
    def _do_start(self, item: T) -> dict:
        """执行启动"""
        if hasattr(item, 'start'):
            return item.start()
        return {"success": False, "error": "Item has no start method"}
    
    def _do_stop(self, item: T) -> dict:
        """执行停止"""
        if hasattr(item, 'stop'):
            return item.stop()
        return {"success": False, "error": "Item has no stop method"}


class StatusMixin:
    """状态混入类
    
    为实体提供状态相关的便捷方法。
    """
    
    @property
    def is_running(self) -> bool:
        status = getattr(self, 'status', None)
        if status is None:
            state = getattr(self, 'state', None)
            if state:
                status = getattr(state, 'status', None)
        if hasattr(status, 'value'):
            status = status.value
        return status == "running"
    
    @property
    def is_stopped(self) -> bool:
        return not self.is_running


class CallbackMixin:
    """回调混入类
    
    为实体提供回调管理功能。
    """
    
    def __init__(self):
        self._on_start_callbacks: List[Callable] = []
        self._on_stop_callbacks: List[Callable] = []
        self._on_data_callbacks: List[Callable] = []
    
    def on_start(self, callback: Callable):
        """注册启动回调"""
        self._on_start_callbacks.append(callback)
    
    def on_stop(self, callback: Callable):
        """注册停止回调"""
        self._on_stop_callbacks.append(callback)
    
    def on_data(self, callback: Callable):
        """注册数据回调"""
        self._on_data_callbacks.append(callback)
    
    def _trigger_start_callbacks(self, *args, **kwargs):
        """触发启动回调"""
        for callback in self._on_start_callbacks:
            try:
                callback(*args, **kwargs)
            except Exception:
                pass
    
    def _trigger_stop_callbacks(self, *args, **kwargs):
        """触发停止回调"""
        for callback in self._on_stop_callbacks:
            try:
                callback(*args, **kwargs)
            except Exception:
                pass
    
    def _trigger_data_callbacks(self, *args, **kwargs):
        """触发数据回调"""
        for callback in self._on_data_callbacks:
            try:
                callback(*args, **kwargs)
            except Exception:
                pass
