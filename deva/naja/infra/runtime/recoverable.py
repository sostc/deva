"""可恢复单元基类(Recoverable Unit Base Class)

统一状态保存恢复与执行函数恢复的抽象模型。
"""

from __future__ import annotations

import logging
import os
import threading
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def as_epoch_seconds(value) -> float:
    """把 date / datetime / 数字 / 字符串 统一成 epoch 秒，无法解析时返回 0.0。

    ❗yaml 里写 ``updated_at: 2026-03-28`` 会被 PyYAML 解析成 ``datetime.date``，
    直接和 NB 里的 float 比较会抛 ``TypeError: '<' not supported``；而这个比较
    发生在「文件配置 vs NB 记录选哪个」的分支里，异常会被外层 ``except Exception``
    吞成「加载一条失败」，看起来像配置文件坏了。时间戳一律归一后再比。
    """
    import datetime as _dt

    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, _dt.datetime):
        return value.timestamp()
    if isinstance(value, _dt.date):
        return _dt.datetime(value.year, value.month, value.day).timestamp()
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


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
        log_msg = f"[{self.__class__.__name__}][{level}] {message} | {extra_str}"
        log_level = getattr(logging, level.upper(), logging.INFO)
        logger.log(log_level, log_msg)
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
            from deva import NB, log
        except Exception:
            NB = None
            log = None
        
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
            "log": log,
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
    
    def requires_compiled_code(self) -> bool:
        """恢复前是否必须先编译 ``func_code``。

        默认 True。``replay`` 这类按表回放的数据源根本不执行 ``func_code``
        （``DataSourceEntry.start`` 里已单独放行），若恢复路径仍强制编译，
        就会永久返回 ``compile_failed`` —— **手动能启动、重启必失败**。
        """
        return True

    def prepare_for_recovery(self) -> dict:
        should, reason = self.should_restore()
        if not should:
            return {"can_recover": False, "reason": reason}

        if self.requires_compiled_code():
            result = self.ensure_compiled()
            if not result["success"]:
                # ❗``compile_failed`` 是**真的坏了**，不是「本来就不该恢复」。
                # 带上 ``fatal`` 让调用方计入 failed_count：否则
                # 「恢复 4 个 / 跳过 1 个 / 失败 0 个」会把一个编译不过的
                # 数据源藏进「跳过」里，摘要静默撒谎。
                return {
                    "can_recover": False,
                    "reason": "compile_failed",
                    "error": result.get("error"),
                    "fatal": True,
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
    
    def stop(self, *, for_shutdown: bool = False) -> dict:
        """停止单元。

        Args:
            for_shutdown: 由**进程退出**流程调用时为 True。

        ❗``was_running`` 的语义是「进程消失前它还在跑吗」，它决定下次启动
        要不要恢复。所以两种停必须分开：

        - 用户/UI 主动停（``for_shutdown=False``，默认）→ 清掉标记，
          下次启动**不要**自己爬起来；
        - 进程退出（``for_shutdown=True``）→ **保留**标记，
          否则每次优雅重启都会把所有单元标成「用户主动停止的」，
          下次启动一个都不恢复。2026-10-20 实测：数据源的 was_running
          在一次 14:46 的优雅重启后从 5/5 掉到 1/5，首页「数据源 0/5」
          就是这么来的 —— 修好 RecoveryManager 登记之后仍然复现，
          因为第二个坑在这里。
        """
        with self._execution_lock:
            if not self.is_running:
                return {"success": True, "message": "Not running"}
            
            try:
                self._stop_event.set()
                
                stop_result = self._do_stop()
                
                if self._thread and self._thread.is_alive():
                    self._thread.join(timeout=1.0)
                
                self._state.status = UnitStatus.STOPPED.value
                if not for_shutdown:
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
                # ❗别在这里无条件 ``load_from_db()``：那一步是「只用 NB、
                #   ``_items.clear()`` 重建」。策略/数据源/任务的**真身是文件**
                #   （``load_prefer_files()``），NB 只是运行时状态。于是恢复
                #   那一刻会把「文件里 14 条策略」换成「NB 里 3 条历史残留」，
                #   另外 11 条静默消失，UI 上只剩 3 个（2026-10-20 实测）。
                #   有 ``reload_for_recovery()`` 就用它（文件基线＋NB 状态合并），
                #   没有才退回老路径。
                reload_fn = getattr(manager, 'reload_for_recovery', None)
                if callable(reload_fn):
                    reload_fn()
                elif hasattr(manager, 'load_from_db'):
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
