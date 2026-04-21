"""可恢复单元基类(Recoverable Unit Base Class)

统一状态保存恢复与执行函数恢复的抽象模型。
"""

from __future__ import annotations

import os
import threading
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class UnitStatus(str, Enum):
    """单元状态枚举"""
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"
    INITIALIZING = "initializing"


@dataclass
class UnitState:
    """单元状态数据类"""
    status: str = UnitStatus.STOPPED.value
    start_time: float = 0
    last_activity_ts: float = 0
    error_count: int = 0
    last_error: str = ""
    last_error_ts: float = 0
    run_count: int = 0
    
    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "start_time": self.start_time,
            "last_activity_ts": self.last_activity_ts,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "last_error_ts": self.last_error_ts,
            "run_count": self.run_count,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "UnitState":
        if isinstance(data, cls):
            return data
        return cls(
            status=data.get("status", UnitStatus.STOPPED.value),
            start_time=data.get("start_time", 0),
            last_activity_ts=data.get("last_activity_ts", 0),
            error_count=data.get("error_count", 0),
            last_error=data.get("last_error", ""),
            last_error_ts=data.get("last_error_ts", 0),
            run_count=data.get("run_count", 0),
        )
    
    def record_error(self, error: str):
        self.error_count += 1
        self.last_error = error
        self.last_error_ts = time.time()
    
    def record_success(self):
        self.run_count += 1
        self.last_activity_ts = time.time()


@dataclass
class UnitMetadata:
    """单元元数据基类"""
    id: str = ""
    name: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "UnitMetadata":
        if isinstance(data, cls):
            return data
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )
    
    def touch(self):
        self.updated_at = time.time()


class RecoverableUnit(ABC):
    """可恢复单元基类
    
    统一状态保存恢复与执行函数恢复的抽象模型。
    """
    
    def __init__(
        self,
        metadata: UnitMetadata = None,
        state: UnitState = None,
    ):
        self._metadata = metadata or UnitMetadata()
        self._state = state or UnitState()
        
        self._func_code: str = ""
        self._compiled_func: Optional[Callable] = None
        self._compile_error: str = ""
        
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._execution_lock = threading.Lock()
        
        self._was_running: bool = False
    
    @property
    def id(self) -> str:
        return self._metadata.id
    
    @id.setter
    def id(self, value: str):
        self._metadata.id = value
    
    @property
    def name(self) -> str:
        return self._metadata.name
    
    @name.setter
    def name(self, value: str):
        self._metadata.name = value
    
    @property
    def status(self) -> str:
        return self._state.status
    
    @property
    def is_running(self) -> bool:
        return self._state.status == UnitStatus.RUNNING.value
    
    @property
    def enabled(self) -> bool:
        return self._state.status == UnitStatus.RUNNING.value
    
    @enabled.setter
    def enabled(self, value: bool):
        if value and not self.is_running:
            self.start()
        elif not value and self.is_running:
            self.stop()
    
    @property
    def state(self) -> UnitState:
        return self._state
    
    @property
    def metadata(self) -> UnitMetadata:
        return self._metadata
    
    @property
    def func_code(self) -> str:
        return self._func_code
    
    @func_code.setter
    def func_code(self, value: str):
        self._func_code = value
        self._compiled_func = None
        self._compile_error = ""
    
    @property
    def compiled_func(self) -> Optional[Callable]:
        return self._compiled_func
    
    @property
    def compile_error(self) -> str:
        return self._compile_error
    
    @property
    def was_running(self) -> bool:
        return self._was_running
    
    @was_running.setter
    def was_running(self, value: bool):
        self._was_running = value
    
    def _log(self, level: str, message: str, **extra):
        extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
        print_msg = f"[{self.__class__.__name__}][{level}] {message} | {extra_str}"
        print(print_msg)
        try:
            from deva.naja.infra.log.log_stream import get_log_stream
            source_type = "datasource" if "DataSource" in self.__class__.__name__ else "task" if "Task" in self.__class__.__name__ else "strategy"
            source_id = getattr(self, 'id', 'unknown')
            source_name = getattr(self, 'name', 'unknown')
            log_stream = get_log_stream()
            if source_type == "datasource":
                log_stream.log_datasource(level, source_id, source_name, message, **extra)
            elif source_type == "task":
                log_stream.log_task(level, source_id, source_name, message, **extra)
            else:
                log_stream.log_strategy(level, source_id, source_name, message, **extra)
        except Exception:
            pass
    
    def _build_execution_env(self) -> Dict[str, Any]:
        import sys
        import pandas as pd
        import numpy as np
        import json
        import datetime as datetime_module
        from datetime import datetime, timedelta, date
        import time as time_module
        import random
        import math
        import re
        from collections import defaultdict
        
        # 注入 deva/naja 核心工具
        try:
            from deva.naja.register import SR
        except Exception:
            SR = None
        
        try:
            from deva import NB
        except Exception:
            NB = None
        
        return {
            "pd": pd,
            "pandas": pd,
            "np": np,
            "numpy": np,
            "json": json,
            "datetime": datetime,
            "datetime_module": datetime_module,
            "timedelta": timedelta,
            "date": date,
            "time": time_module,
            "random": random,
            "math": math,
            "re": re,
            "defaultdict": defaultdict,
            "sys": sys,
            "SR": SR,
            "NB": NB,
            "__builtins__": __builtins__,
        }
    
    def compile_code(self) -> dict:
        if self._compiled_func is not None:
            return {"success": True, "func": self._compiled_func, "cached": True}
        
        if not self._func_code:
            return {"success": False, "error": "No code to compile"}
        
        try:
            self._compiled_func = self._do_compile(self._func_code)
            self._compile_error = ""
            return {"success": True, "func": self._compiled_func}
        except Exception as e:
            self._compile_error = str(e)
            self._log("ERROR", "Code compilation failed", id=self.id, error=str(e))
            return {"success": False, "error": str(e), "traceback": traceback.format_exc()}
    
    @abstractmethod
    def _do_compile(self, code: str) -> Callable:
        pass
    
    @abstractmethod
    def _get_func_name(self) -> str:
        pass
    
    def ensure_compiled(self) -> dict:
        if self._compiled_func is not None:
            return {"success": True, "func": self._compiled_func, "cached": True}
        return self.compile_code()
    
    @abstractmethod
    def save(self) -> dict:
        pass
    
    @abstractmethod
    def to_dict(self) -> dict:
        pass
    
    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict) -> "RecoverableUnit":
        pass

    def save_running_state(self, is_running: bool):
        old_status = self._state.status
        new_status = UnitStatus.RUNNING.value if is_running else UnitStatus.STOPPED.value

        self._state.status = new_status
        try:
            self.save()
        except Exception as e:
            self._state.status = old_status
            self._log("ERROR", "Save running state failed, rolled back", error=str(e))
            raise
    
    def get_saved_running_state(self) -> dict:
        return {
            "is_running": self.is_running,
            "status": self._state.status,
            "pid": os.getpid(),
            "timestamp": time.time(),
        }
    
    def should_restore(self) -> tuple:
        if self.is_running:
            return False, "already_running"
        
        if self._was_running:
            return True, "was_running_flag"
        
        return False, ""
    
    def prepare_for_recovery(self) -> dict:
        should, reason = self.should_restore()
        if not should:
            return {"can_recover": False, "reason": reason}
        
        result = self.ensure_compiled()
        if not result["success"]:
            return {
                "can_recover": False,
                "reason": "compile_failed",
                "error": result.get("error"),
            }
        
        return {
            "can_recover": True,
            "func": self._compiled_func,
            "reason": reason,
        }
    
    def start(self) -> dict:
        with self._execution_lock:
            if self.is_running:
                return {"success": True, "message": "Already running"}
            
            result = self.ensure_compiled()
            if not result["success"]:
                return {"success": False, "error": f"编译失败: {result['error']}"}
            
            try:
                self._state.status = UnitStatus.INITIALIZING.value
                self._stop_event.clear()
                
                start_result = self._do_start(self._compiled_func)
                if not start_result["success"]:
                    self._state.status = UnitStatus.ERROR.value
                    self._state.record_error(start_result.get("error", "Unknown error"))
                    self.save()
                    return start_result
                
                self._state.status = UnitStatus.RUNNING.value
                self._state.start_time = time.time()
                self._was_running = True
                self.save()
                
                self._log("INFO", "Unit started", id=self.id, name=self.name)
                return {"success": True, "status": self._state.status}
                
            except Exception as e:
                self._state.status = UnitStatus.ERROR.value
                self._state.record_error(str(e))
                self.save()
                self._log("ERROR", "Start failed", id=self.id, error=str(e))
                return {"success": False, "error": str(e), "traceback": traceback.format_exc()}
    
    def stop(self) -> dict:
        with self._execution_lock:
            if not self.is_running:
                return {"success": True, "message": "Not running"}
            
            try:
                self._stop_event.set()
                
                stop_result = self._do_stop()
                
                if self._thread and self._thread.is_alive():
                    self._thread.join(timeout=1.0)
                
                self._state.status = UnitStatus.STOPPED.value
                self._was_running = False
                self.save()
                
                self._log("INFO", "Unit stopped", id=self.id, name=self.name)
                return {"success": True, "status": self._state.status}
                
            except Exception as e:
                self._state.status = UnitStatus.ERROR.value
                self._state.record_error(str(e))
                self.save()
                self._log("ERROR", "Stop failed", id=self.id, error=str(e))
                return {"success": False, "error": str(e)}
    
    def recover(self) -> dict:
        prep = self.prepare_for_recovery()
        if not prep.get("can_recover"):
            return {
                "success": False,
                "reason": prep.get("reason"),
                "error": prep.get("error"),
            }

        result = self.start()

        if result.get("success") and not self.is_running:
            return {
                "success": False,
                "error": "Recovery started but not running",
                "reason": "start_returned_success_but_status_not_running",
            }

        return result
    
    @abstractmethod
    def _do_start(self, func: Callable) -> dict:
        pass
    
    @abstractmethod
    def _do_stop(self) -> dict:
        pass
    
    def delete(self) -> dict:
        if self.is_running:
            stop_result = self.stop()
            if not stop_result.get("success"):
                return stop_result
        
        self._log("INFO", "Unit deleted", id=self.id, name=self.name)
        return {"success": True}


class RecoveryManager:
    """恢复管理器

    统一管理所有可恢复单元的恢复流程。

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局恢复决策：RecoveryManager 是全局恢复决策器，所有可恢复单元的
       故障恢复都通过这个实例。如果存在多个实例，可能导致恢复冲突。

    2. 状态一致性：恢复状态、单元状态等需要在全系统保持一致。

    3. 生命周期：Manager 的生命周期与系统一致，随系统启动和关闭。

    4. 这是系统故障恢复的设计选择，不是过度工程。
    ================================================================================
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
        self._managers: Dict[str, Any] = {}
        self._initialized = True
    
    def register(self, unit_type: str, manager: Any):
        self._managers[unit_type] = manager
    
    def unregister(self, unit_type: str):
        self._managers.pop(unit_type, None)
    
    def restore_all(self, order: List[str] = None) -> dict:
        results = {}
        unit_types = order or ["datasource", "dictionary", "strategy", "task"]
        
        for unit_type in unit_types:
            manager = self._managers.get(unit_type)
            if not manager:
                results[unit_type] = {"success": False, "error": "Manager not registered"}
                continue
            
            try:
                if hasattr(manager, 'load_from_db'):
                    manager.load_from_db()
                
                if hasattr(manager, 'restore_running_states'):
                    result = manager.restore_running_states()
                else:
                    result = {"success": True, "message": "No restore method"}
                
                results[unit_type] = result
            except Exception as e:
                results[unit_type] = {"success": False, "error": str(e)}
        
        return results
    
    def get_recovery_info(self) -> dict:
        info = {}
        for unit_type, manager in self._managers.items():
            if hasattr(manager, 'get_all_recovery_info'):
                info[unit_type] = manager.get_all_recovery_info()
        return info


recovery_manager = RecoveryManager()
