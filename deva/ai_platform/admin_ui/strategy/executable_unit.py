"""可执行单元基类(Executable Unit Base Class)

为策略和数据源提供统一的代码执行、生命周期管理和流处理集成能力。

================================================================================
架构设计
================================================================================

【继承体系】
┌─────────────────────────────────────────────────────────────────────────────┐
│  ExecutableUnit (可执行单元基类)                                              │
│  ├── 代码执行: 统一的Python代码沙箱环境                                        │
│  ├── 生命周期: 标准化的start/stop/delete流程                                   │
│  ├── 错误处理: 统一的错误记录和上报机制                                        │
│  ├── 流集成: 标准化的流创建和管理                                             │
│  └── AI集成: 统一的代码生成和验证接口                                          │
│                                                                             │
│  具体实现:                                                                  │
│  ├── StrategyUnit → 策略执行单元 (数据消费者)                                  │
│  └── DataSource → 数据源单元 (数据生产者)                                     │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import hashlib
import threading
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

from deva import Stream, NS, log

from ..common.base import (
    BaseMetadata,
    BaseState,
    BaseManager,
    StatusMixin,
    CallbackMixin,
)
from .logging_context import logging_context_manager


class ExecutableUnitStatus(str):
    """可执行单元状态"""
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"
    INITIALIZING = "initializing"


@dataclass
class ExecutableUnitMetadata(BaseMetadata):
    """可执行单元元数据基类"""
    func_code: str = ""  # 可执行代码
    version: int = 1     # 代码版本
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data["func_code"] = self.func_code
        data["version"] = self.version
        return data


@dataclass
class ExecutableUnitState(BaseState):
    """可执行单元状态基类"""
    status: str = ExecutableUnitStatus.STOPPED
    start_time: float = 0
    processed_count: int = 0  # 处理/生成数据的数量
    last_activity_ts: float = 0  # 最后活动时间
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data["status"] = self.status
        data["start_time"] = self.start_time
        data["processed_count"] = self.processed_count
        data["last_activity_ts"] = self.last_activity_ts
        return data


class ExecutableUnit(ABC, StatusMixin, CallbackMixin):
    """可执行单元基类
    
    为策略和数据源提供统一的：
    - 代码执行环境
    - 生命周期管理
    - 错误处理
    - 流处理集成
    - AI代码生成支持
    """
    
    def __init__(
        self,
        metadata: ExecutableUnitMetadata,
        state: ExecutableUnitState,
        func_name: str = "process",
        stream_cache_size: int = 50,
    ):
        """
        Args:
            metadata: 元数据
            state: 状态
            func_name: 函数名称 (策略用"process", 数据源用"fetch_data")
            stream_cache_size: 流缓存大小
        """
        CallbackMixin.__init__(self)
        
        self.metadata = metadata
        self.state = state
        self._func_name = func_name
        self._stream_cache_size = stream_cache_size
        
        # 执行相关
        self._func: Optional[Callable] = None  # 编译后的函数
        self._execution_lock = threading.Lock()
        
        # 流相关
        self._stream: Optional[Stream] = None
        self._stream_lock = threading.Lock()
        
        # 运行控制
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        
        # 统计相关
        self._stats_lock = threading.Lock()
        
    # ==========================================================================
    # 代码执行相关方法
    # ==========================================================================
    
    def compile_code(self, code: str, func_name: str = None) -> Dict[str, Any]:
        """编译代码
        
        Args:
            code: Python代码
            func_name: 函数名称，如果为None则使用默认函数名
            
        Returns:
            编译结果 {"success": bool, "func": Callable, "error": str}
        """
        if func_name is None:
            func_name = self._func_name
            
        try:
            # 构建安全的执行环境
            global_env = self._build_execution_env()
            local_vars = {}
            
            # 执行代码
            exec(code, global_env, local_vars)
            
            # 获取目标函数
            func = local_vars.get(func_name)
            if func is None:
                return {
                    "success": False,
                    "error": f"函数 '{func_name}' 未在代码中定义"
                }
            
            # 验证函数签名
            validation_result = self._validate_function(func)
            if not validation_result["success"]:
                return validation_result
            
            return {
                "success": True,
                "func": func,
                "func_name": func_name
            }
            
        except Exception as e:
            error_msg = f"代码编译失败: {str(e)}"
            log.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "traceback": traceback.format_exc()
            }
    
    def _build_execution_env(self) -> Dict[str, Any]:
        """构建代码执行环境
        
        提供统一的Python执行环境，包含常用的数据分析库
        """
        import pandas as pd
        import numpy as np
        import json
        import datetime
        import time
        import random
        import math
        import re
        import urllib.request
        import urllib.parse
        
        return {
            # 数据分析库
            "pd": pd,
            "pandas": pd,
            "np": np,
            "numpy": np,
            
            # Python标准库
            "json": json,
            "datetime": datetime,
            "time": time,
            "random": random,
            "math": math,
            "re": re,
            "urllib": urllib,
            
            # 常用函数
            "len": len,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sum": sum,
            "max": max,
            "min": min,
            "abs": abs,
            "round": round,
            
            # 安全限制
            "__builtins__": {
                "len": len,
                "range": range,
                "enumerate": enumerate,
                "zip": zip,
                "map": map,
                "filter": filter,
                "sum": sum,
                "max": max,
                "min": min,
                "abs": abs,
                "round": round,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
            }
        }
    
    @abstractmethod
    def _validate_function(self, func: Callable) -> Dict[str, Any]:
        """验证函数签名
        
        子类需要实现具体的验证逻辑
        
        Returns:
            {"success": bool, "error": str}
        """
        pass
    
    def set_function(self, func: Callable, code: str = None, version: int = None):
        """设置执行函数
        
        Args:
            func: 编译后的函数
            code: 源代码，如果提供则更新元数据
            version: 版本号，如果提供则更新元数据
        """
        with self._execution_lock:
            self._func = func
            
            if code is not None:
                self.metadata.func_code = code
                
            if version is not None:
                self.metadata.version = version
            elif code is not None:
                # 代码变更时自动增加版本
                self.metadata.version += 1
                
            self.metadata.touch()  # 更新时间戳
    
    # ==========================================================================
    # 生命周期管理方法
    # ==========================================================================
    
    def start(self) -> Dict[str, Any]:
        """启动可执行单元"""
        with self._execution_lock:
            if self.is_running:
                return {"success": False, "error": "单元已在运行中"}
            
            try:
                # 编译代码（如果还没编译）
                if self._func is None and self.metadata.func_code:
                    compile_result = self.compile_code(self.metadata.func_code)
                    if not compile_result["success"]:
                        return compile_result
                    self._func = compile_result["func"]
                
                # 检查函数
                if self._func is None:
                    return {"success": False, "error": "没有可执行的函数"}
                
                # 初始化状态
                self.state.status = ExecutableUnitStatus.INITIALIZING
                self.state.start_time = time.time()
                self.state.last_activity_ts = time.time()
                self.state.error_count = 0
                self.state.last_error = ""
                self.state.last_error_ts = 0
                
                # 清除停止标志
                self._stop_event.clear()
                
                # 执行具体的启动逻辑
                start_result = self._do_start()
                if not start_result["success"]:
                    self.state.status = ExecutableUnitStatus.ERROR
                    return start_result
                
                # 更新状态
                self.state.status = ExecutableUnitStatus.RUNNING
                
                # 触发回调
                self._trigger_start_callbacks(self)
                
                log.info(f"可执行单元已启动: {self.metadata.name} ({self.metadata.id})")
                
                return {"success": True, "message": "启动成功"}
                
            except Exception as e:
                error_msg = f"启动失败: {str(e)}"
                log.error(error_msg)
                self.state.status = ExecutableUnitStatus.ERROR
                self.state.record_error(error_msg)
                return {"success": False, "error": error_msg, "traceback": traceback.format_exc()}
    
    def stop(self) -> Dict[str, Any]:
        """停止可执行单元"""
        with self._execution_lock:
            if not self.is_running:
                return {"success": False, "error": "单元未在运行"}
            
            try:
                # 设置停止标志
                self._stop_event.set()
                
                # 执行具体的停止逻辑
                stop_result = self._do_stop()
                
                # 等待线程结束
                if self._thread and self._thread.is_alive():
                    self._thread.join(timeout=5.0)
                
                # 更新状态
                self.state.status = ExecutableUnitStatus.STOPPED
                self.state.start_time = 0
                
                # 触发回调
                self._trigger_stop_callbacks(self)
                
                log.info(f"可执行单元已停止: {self.metadata.name} ({self.metadata.id})")
                
                return {"success": True, "message": "停止成功"}
                
            except Exception as e:
                error_msg = f"停止失败: {str(e)}"
                log.error(error_msg)
                return {"success": False, "error": error_msg, "traceback": traceback.format_exc()}
    
    def delete(self) -> Dict[str, Any]:
        """删除可执行单元"""
        try:
            # 先停止（如果在运行）
            if self.is_running:
                stop_result = self.stop()
                if not stop_result["success"]:
                    return stop_result
            
            # 执行具体的删除逻辑
            delete_result = self._do_delete()
            if not delete_result["success"]:
                return delete_result
            
            # 清理资源
            with self._stream_lock:
                if self._stream:
                    # 清理流资源
                    self._stream = None
            
            log.info(f"可执行单元已删除: {self.metadata.name} ({self.metadata.id})")
            
            return {"success": True, "message": "删除成功"}
            
        except Exception as e:
            error_msg = f"删除失败: {str(e)}"
            log.error(error_msg)
            return {"success": False, "error": error_msg, "traceback": traceback.format_exc()}
    
    @abstractmethod
    def _do_start(self) -> Dict[str, Any]:
        """执行具体的启动逻辑
        
        Returns:
            {"success": bool, "error": str}
        """
        pass
    
    @abstractmethod
    def _do_stop(self) -> Dict[str, Any]:
        """执行具体的停止逻辑
        
        Returns:
            {"success": bool, "error": str}
        """
        pass
    
    def _do_delete(self) -> Dict[str, Any]:
        """执行具体的删除逻辑
        
        默认实现，子类可以重写
        
        Returns:
            {"success": bool, "error": str}
        """
        return {"success": True}
    
    # ==========================================================================
    # 流处理相关方法
    # ==========================================================================
    
    def get_stream(self) -> Optional[Stream]:
        """获取输出流"""
        with self._stream_lock:
            if self._stream is None:
                self._stream = NS(self.metadata.name, cache_max_len=self._stream_cache_size)
            return self._stream
    
    def set_stream(self, stream: Stream):
        """设置输出流"""
        with self._stream_lock:
            self._stream = stream
    
    def emit_data(self, data: Any):
        """发送数据到流
        
        线程安全的流数据发射
        """
        with self._stats_lock:
            self.state.processed_count += 1
            self.state.last_activity_ts = time.time()
        
        # 触发数据回调
        self._trigger_data_callbacks(data)
        
        # 发送到流
        stream = self.get_stream()
        if stream and hasattr(stream, 'emit'):
            try:
                stream.emit(data)
            except Exception as e:
                log.error(f"流数据发射失败: {e}")
                self.state.record_error(f"流数据发射失败: {e}")
    
    # ==========================================================================
    # 错误处理方法
    # ==========================================================================
    
    def handle_error(self, error: Exception, context: str = None):
        """统一错误处理
        
        Args:
            error: 异常对象
            context: 错误上下文信息
        """
        error_msg = str(error)
        if context:
            error_msg = f"{context}: {error_msg}"
        
        log.error(f"可执行单元错误 [{self.metadata.name}]: {error_msg}")
        
        # 记录错误到状态
        self.state.record_error(error_msg)
        
        # 更新状态
        self.state.status = ExecutableUnitStatus.ERROR
        
        # 触发错误回调
        # TODO: 可以添加专门的错误回调机制
        
        # 保存状态（如果支持）
        try:
            if hasattr(self, 'save'):
                self.save()
        except Exception as e:
            log.error(f"错误状态保存失败: {e}")
    
    # ==========================================================================
    # 工具方法
    # ==========================================================================
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "metadata": self.metadata.to_dict(),
            "state": self.state.to_dict(),
            "is_running": self.is_running,
            "func_name": self._func_name,
        }
    
    def save(self):
        """保存到持久化存储
        
        子类可以重写此方法提供具体的持久化逻辑
        """
        # 默认实现，子类可以重写
        pass
    
    @property
    def id(self) -> str:
        """获取ID"""
        return self.metadata.id
    
    @property
    def name(self) -> str:
        """获取名称"""
        return self.metadata.name
    
    @property
    def status(self) -> str:
        """获取状态"""
        return self.state.status