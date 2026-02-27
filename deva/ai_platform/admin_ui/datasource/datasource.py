"""数据源管理模块(DataSource Management Module)

提供数据源的生命周期管理、依赖追踪和可视化功能。

================================================================================
架构设计
================================================================================

【数据源单元结构】
┌─────────────────────────────────────────────────────────────────────────────┐
│  DataSource                                                                 │
│  ├── 元数据 (DataSourceMetadata)                                            │
│  │   ├── id: 唯一标识                                                        │
│  │   ├── name: 名称                                                          │
│  │   ├── source_type: 数据源类型(stream/timer/http/kafka/redis等)            │
│  │   ├── description: 描述                                                   │
│  │   └── config: 配置参数                                                    │
│  │                                                                          │
│  ├── 状态 (DataSourceState)                                                  │
│  │   ├── status: running | stopped | error | initializing                   │
│  │   ├── last_data_ts: 最后数据时间戳                                        │
│  │   └── error_count: 错误计数                                               │
│  │                                                                          │
│  ├── 统计 (DataSourceStats)                                                  │
│  │   ├── total_emitted: 总发送数据量                                         │
│  │   └── emit_rate: 发送速率(条/秒)                                          │
│  │                                                                          │
│  └── 依赖关系                                                                │
│      └── dependent_strategies: 依赖此数据源的策略列表                         │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import threading
import time
import traceback
import weakref
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from deva import Stream, NS, NB, log
from deva.utils.ioloop import get_io_loop

from ..common.base import (
    BaseMetadata,
    BaseState,
    BaseStats,
    BaseManager,
    StatusMixin,
    CallbackMixin,
)
from ..strategy.utils import format_duration
from ..strategy.logging_context import (
    log_datasource_event,
    logging_context_manager,
    with_datasource_logging
)


class DataSourceStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    INITIALIZING = "initializing"


class DataSourceType(str, Enum):
    TIMER = "timer"
    STREAM = "stream"
    HTTP = "http"
    KAFKA = "kafka"
    REDIS = "redis"
    TCP = "tcp"
    FILE = "file"
    CUSTOM = "custom"
    REPLAY = "replay"


@dataclass
class DataSourceMetadata(BaseMetadata):
    """数据源元数据"""
    source_type: DataSourceType = DataSourceType.CUSTOM
    config: dict = field(default_factory=dict)
    data_func_code: str = ""
    interval: float = 5.0
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data["source_type"] = self.source_type.value
        return data


@dataclass
class DataSourceState(BaseState):
    """数据源状态"""
    status: str = "initializing"
    last_data_ts: float = 0
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data["last_data_ts_readable"] = datetime.fromtimestamp(self.last_data_ts).isoformat() if self.last_data_ts > 0 else "-"
        return data


@dataclass
class DataSourceStats(BaseStats):
    """数据源统计"""
    total_emitted: int = 0
    emit_rate: float = 0.0
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data["total_emitted"] = self.total_emitted
        data["emit_rate"] = self.emit_rate
        return data


class DataSource(StatusMixin, CallbackMixin):
    """数据源单元
    
    封装数据源的元数据、状态、统计和依赖关系。
    """
    
    _instances: Dict[str, weakref.ref] = {}
    _instances_lock = threading.Lock()
    
    def __init__(
        self,
        name: str,
        source_type: DataSourceType = DataSourceType.CUSTOM,
        description: str = "",
        config: dict = None,
        stream: Stream = None,
        auto_start: bool = False,
        data_func_code: str = "",
        interval: float = 5.0,
    ):
        CallbackMixin.__init__(self)
        
        self._id = self._generate_id(name)
        self.metadata = DataSourceMetadata(
            id=self._id,
            name=name,
            source_type=source_type,
            description=description,
            config=config or {},
            data_func_code=data_func_code,
            interval=interval,
        )
        
        self.state = DataSourceState()
        self.stats = DataSourceStats()
        
        self._stream: Optional[Stream] = stream
        self._dependent_strategies: Set[str] = set()
        self._dependent_strategies_lock = threading.Lock()
        
        self._timer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._was_running: bool = False
        
        self._register_instance()
        
        if auto_start:
            self.start()
    
    @classmethod
    def _generate_id(cls, name: str) -> str:
        ts = time.time()
        hash_input = f"{name}_{ts}".encode()
        return hashlib.md5(hash_input).hexdigest()[:12]
    
    def _register_instance(self):
        with self._instances_lock:
            self._instances[self._id] = weakref.ref(self)
    
    @classmethod
    def get_instance(cls, source_id: str) -> Optional["DataSource"]:
        with cls._instances_lock:
            ref = cls._instances.get(source_id)
            return ref() if ref else None
    
    @classmethod
    def get_all_instances(cls) -> List["DataSource"]:
        with cls._instances_lock:
            instances = []
            dead_refs = []
            for source_id, ref in cls._instances.items():
                source = ref()
                if source:
                    instances.append(source)
                else:
                    dead_refs.append(source_id)
            for source_id in dead_refs:
                del cls._instances[source_id]
            return instances
    
    @property
    def id(self) -> str:
        return self._id
    
    @property
    def name(self) -> str:
        return self.metadata.name
    
    @property
    def status(self) -> DataSourceStatus:
        return DataSourceStatus(self.state.status)
    
    def set_stream(self, stream: Stream):
        self._stream = stream
        self.metadata.config["stream_name"] = getattr(stream, 'name', str(stream))
    
    def get_stream(self) -> Optional[Stream]:
        return self._stream
    
    def add_dependent_strategy(self, strategy_id: str):
        with self._dependent_strategies_lock:
            self._dependent_strategies.add(strategy_id)
    
    def remove_dependent_strategy(self, strategy_id: str):
        with self._dependent_strategies_lock:
            self._dependent_strategies.discard(strategy_id)
    
    def get_dependent_strategies(self) -> List[str]:
        with self._dependent_strategies_lock:
            return list(self._dependent_strategies)
    
    def _compile_data_func(self) -> Optional[Callable]:
        if not self.metadata.data_func_code:
            return None
        
        try:
            # 创建包含常用库的环境
            import pandas as pd
            import numpy as np
            import datetime
            import time
            import json
            import random
            import math
            import re
            import os
            import sys
            from typing import Any, Dict, List, Optional
            
            # 构建全局命名空间，包含常用库和内置函数
            global_env = {
                "__builtins__": __builtins__,
                "pd": pd,
                "pandas": pd,
                "numpy": np,
                "np": np,
                "datetime": datetime,
                "time": time,
                "json": json,
                "random": random,
                "math": math,
                "re": re,
                "os": os,
                "sys": sys,
                "Any": Any,
                "Dict": Dict,
                "List": List,
                "Optional": Optional,
            }
            
            # 执行代码，所有函数和变量都会保存在 local_vars 中
            local_vars = {}
            exec(self.metadata.data_func_code, global_env, local_vars)
            
            if "fetch_data" in local_vars and callable(local_vars["fetch_data"]):
                original_func = local_vars["fetch_data"]
                is_async = asyncio.iscoroutinefunction(original_func)
                
                if is_async:
                    async def wrapped_fetch_data():
                        exec_env = global_env.copy()
                        exec_env.update(local_vars)
                        
                        for name, obj in local_vars.items():
                            if callable(obj) and hasattr(obj, '__globals__'):
                                obj.__globals__.update(exec_env)
                        
                        return await local_vars["fetch_data"]()
                    
                    return wrapped_fetch_data
                else:
                    def wrapped_fetch_data():
                        exec_env = global_env.copy()
                        exec_env.update(local_vars)
                        
                        for name, obj in local_vars.items():
                            if callable(obj) and hasattr(obj, '__globals__'):
                                obj.__globals__.update(exec_env)
                        
                        return local_vars["fetch_data"]()
                    
                    return wrapped_fetch_data
            return None
        except Exception as e:
            self.state.record_error(f"代码编译错误: {str(e)}")
            return None
    
    def update_data_func_code(self, code: str) -> dict:
        """更新数据获取代码并保存到数据库"""
        try:
            # 先验证代码是否可编译
            import pandas as pd
            import numpy as np
            import datetime
            import time
            import json
            import random
            import math
            import re
            import os
            import sys
            from typing import Any, Dict, List, Optional
            
            # 构建验证环境
            test_globals = {
                "__builtins__": __builtins__,
                "pd": pd,
                "pandas": pd,
                "numpy": np,
                "np": np,
                "datetime": datetime,
                "time": time,
                "json": json,
                "random": random,
                "math": math,
                "re": re,
                "os": os,
                "sys": sys,
                "Any": Any,
                "Dict": Dict,
                "List": List,
                "Optional": Optional,
            }
            
            test_locals = {}
            exec(code, test_globals, test_locals)
            if "fetch_data" not in test_locals or not callable(test_locals["fetch_data"]):
                return {"success": False, "error": "代码必须包含可调用的fetch_data函数"}
            
            # 保存旧代码用于回滚
            old_code = self.metadata.data_func_code
            
            # 更新代码
            self.metadata.data_func_code = code
            self.metadata.touch()
            
            # 保存到数据库
            self.save()
            
            # 保存代码历史版本
            self._save_code_version(code, old_code)
            
            self._log_event("INFO", "Data function code updated")
            return {"success": True, "message": "代码更新成功"}
            
        except Exception as e:
            return {"success": False, "error": f"代码更新失败: {str(e)}"}
    
    def _save_code_version(self, new_code: str, old_code: str):
        """保存代码版本历史"""
        try:
            version_db = NB("data_source_code_versions")
            version_info = {
                "id": self._id,
                "name": self.name,
                "new_code": new_code,
                "old_code": old_code,
                "timestamp": time.time(),
                "version": self.metadata.updated_at,
            }
            version_db[f"{self._id}_code_{int(time.time() * 1000)}"] = version_info
        except Exception as e:
            self._log_event("ERROR", f"Failed to save code version: {str(e)}")
    
    def get_code_versions(self, limit: int = 10) -> List[dict]:
        """获取代码版本历史"""
        try:
            version_db = NB("data_source_code_versions")
            versions = []
            prefix = f"{self._id}_code_"
            
            # 获取所有版本并按时间排序
            for key, value in version_db.items():
                if key.startswith(prefix):
                    versions.append(value)
            
            # 按时间戳倒序排序
            versions.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return versions[:limit]
            
        except Exception as e:
            self._log_event("ERROR", f"Failed to get code versions: {str(e)}")
            return []
    
    def get_full_state_summary(self) -> dict:
        """获取完整的状态摘要，用于监控和调试"""
        try:
            running_state = self.get_saved_running_state()
            latest_data = self.get_saved_latest_data()
            code_versions = self.get_code_versions(3)
            
            return {
                "id": self._id,
                "name": self.name,
                "current_status": self.state.status,
                "current_stats": self.stats.to_dict(),
                "saved_running_state": running_state,
                "saved_latest_data": {
                    "has_data": bool(latest_data),
                    "data_type": latest_data.get("data_type") if latest_data else None,
                    "timestamp": latest_data.get("timestamp") if latest_data else None,
                    "size": latest_data.get("size") if latest_data else 0,
                },
                "code_versions_count": len(code_versions),
                "latest_code_update": code_versions[0].get("timestamp") if code_versions else None,
                "dependent_strategies": self.get_dependent_strategies(),
                "metadata": self.metadata.to_dict(),
            }
        except Exception as e:
            self._log_event("ERROR", f"Failed to get full state summary: {str(e)}")
            return {"error": str(e)}
    
    def export_state(self, include_data: bool = False, include_code: bool = True) -> dict:
        """导出完整状态，用于备份和迁移"""
        try:
            state_data = self.to_dict()
            
            # 添加额外的状态信息
            state_data["saved_running_state"] = self.get_saved_running_state()
            state_data["saved_latest_data"] = self.get_saved_latest_data() if include_data else None
            
            if include_code:
                state_data["code_versions"] = self.get_code_versions(10)
            
            # 添加运行时信息
            state_data["export_info"] = {
                "export_time": time.time(),
                "export_timestamp": datetime.now().isoformat(),
                "pid": os.getpid(),
                "include_data": include_data,
                "include_code": include_code,
            }
            
            return state_data
            
        except Exception as e:
            self._log_event("ERROR", f"Failed to export state: {str(e)}")
            return {"error": str(e)}
    
    def import_state(self, state_data: dict, merge: bool = False) -> dict:
        """导入状态，用于恢复和迁移"""
        try:
            if not merge:
                # 完全替换模式
                if "metadata" in state_data:
                    metadata_data = state_data["metadata"]
                    self.metadata.description = metadata_data.get("description", self.metadata.description)
                    self.metadata.config = metadata_data.get("config", self.metadata.config)
                    self.metadata.data_func_code = metadata_data.get("data_func_code", self.metadata.data_func_code)
                    self.metadata.interval = metadata_data.get("interval", self.metadata.interval)
                    self.metadata.tags = metadata_data.get("tags", self.metadata.tags)
                
                if "state" in state_data:
                    state_info = state_data["state"]
                    self.state.error_count = state_info.get("error_count", self.state.error_count)
                    self.state.last_error = state_info.get("last_error", self.state.last_error)
                
                if "stats" in state_data:
                    stats_info = state_data["stats"]
                    self.stats.total_emitted = stats_info.get("total_emitted", self.stats.total_emitted)
            
            # 保存导入的状态
            self.metadata.touch()
            self.save()
            
            self._log_event("INFO", "State imported successfully", merge=merge)
            return {"success": True, "message": "状态导入成功"}
            
        except Exception as e:
            self._log_event("ERROR", f"Failed to import state: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _timer_loop(self, func: Callable):
        import asyncio
        
        # 使用数据源上下文包装整个定时器循环
        with logging_context_manager.datasource_context(
            self.id, 
            self.name, 
            self.metadata.source_type.value if hasattr(self.metadata, 'source_type') else None
        ):
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            except Exception:
                loop = None
            
            is_async = asyncio.iscoroutinefunction(func) if func else False
            
            while not self._stop_event.is_set():
                try:
                    if is_async:
                        if loop:
                            result = loop.run_until_complete(func())
                        else:
                            result = asyncio.run(func())
                        
                        if asyncio.iscoroutine(result):
                            if loop:
                                result = loop.run_until_complete(result)
                            else:
                                result = asyncio.run(result)
                        data = result
                    else:
                        data = func()
                    
                    if data is not None and not asyncio.iscoroutine(data):
                        self.record_data(data)
                except Exception as e:
                    self.state.record_error(str(e))
                    self._log_event("ERROR", f"数据获取错误: {str(e)}")
                
                self._stop_event.wait(self.metadata.interval)
            
            if loop:
                loop.close()
    
    def start(self) -> dict:
        if self.state.status == DataSourceStatus.RUNNING.value:
            return {"success": True, "message": "Already running"}
        
        try:
            if self._stream:
                try:
                    self._stream.start()
                except Exception:
                    pass
            
            if self.metadata.source_type == DataSourceType.TIMER and self.metadata.data_func_code:
                data_func = self._compile_data_func()
                if data_func is None:
                    return {"success": False, "error": "无法编译数据生成代码"}
                
                self._stop_event.clear()
                self._timer_thread = threading.Thread(
                    target=self._timer_loop,
                    args=(data_func,),
                    daemon=True,
                    name=f"ds_timer_{self.name}"
                )
                self._timer_thread.start()
            
            elif self.metadata.source_type == DataSourceType.REPLAY:
                # 处理回放数据源
                config = self.metadata.config
                table_name = config.get("table_name")
                if not table_name:
                    return {"success": False, "error": "缺少表名配置"}
                
                # 创建 DBStream 对象用于读取数据
                from deva import NB, NS
                db_stream = NB(table_name, key_mode='time')
                # 创建普通 Stream 对象作为数据源的输出流
                output_stream = NS(self.name, cache_max_len=50, cache_max_age_seconds=3600, description=f'{self.name}回放数据源的数据流')
                self.set_stream(output_stream)
                
                # 获取回放配置
                start_time = config.get("start_time")
                end_time = config.get("end_time")
                interval = config.get("interval", 1.0)
                
                # 启动回放线程
                def replay_loop():
                    try:
                        self._log_event("INFO", f"开始回放表 {table_name}")
                        # 执行回放
                        # 处理 start_time 和 end_time 为 None 的情况
                        if start_time is None and end_time is None:
                            # 回放所有数据
                            self._log_event("INFO", "回放所有数据")
                            keys = list(db_stream.keys())
                            self._log_event("INFO", f"找到 {len(keys)} 条数据")
                            for key in keys:
                                if self._stop_event.is_set():
                                    self._log_event("INFO", "回放被手动停止")
                                    break
                                try:
                                    data = db_stream[key]
                                    if data is not None:
                                        self._log_event("INFO", f"回放数据: {data}")
                                        self.record_data(data)
                                    if interval > 0:
                                        if self._stop_event.wait(timeout=interval):
                                            self._log_event("INFO", "回放被手动停止")
                                            break
                                except Exception as e:
                                    self._log_event("ERROR", f"处理数据 {key} 时出错: {str(e)}")
                        else:
                            # 按时间范围回放
                            self._log_event("INFO", f"按时间范围回放: {start_time} 到 {end_time}")
                            keys = list(db_stream[start_time:end_time])
                            self._log_event("INFO", f"找到 {len(keys)} 条数据")
                            for key in keys:
                                if self._stop_event.is_set():
                                    self._log_event("INFO", "回放被手动停止")
                                    break
                                try:
                                    data = db_stream[key]
                                    if data is not None:
                                        self._log_event("INFO", f"回放数据: {data}")
                                        self.record_data(data)
                                    if interval > 0:
                                        if self._stop_event.wait(timeout=interval):
                                            self._log_event("INFO", "回放被手动停止")
                                            break
                                except Exception as e:
                                    self._log_event("ERROR", f"处理数据 {key} 时出错: {str(e)}")
                    except Exception as e:
                        import traceback
                        self.state.record_error(str(e))
                        self._log_event("ERROR", f"回放错误: {str(e)}")
                        self._log_event("ERROR", f"错误堆栈: {traceback.format_exc()}")
                    finally:
                        # 回放完成后自动停止数据源
                        self._log_event("INFO", "回放完成，自动停止数据源")
                        # 直接更新状态为停止，避免调用 stop 方法可能引起的错误
                        try:
                            self._stop_event.set()
                            # 不要在当前线程中调用 join()
                            # if self._timer_thread and self._timer_thread.is_alive():
                            #     self._timer_thread.join(timeout=2)
                            
                            if self._stream:
                                try:
                                    # 检查 stream 是否有 stop 方法
                                    if hasattr(self._stream, 'stop'):
                                        self._stream.stop()
                                except Exception as e:
                                    self._log_event("WARNING", f"停止流时出错: {str(e)}")
                                    pass
                            
                            self.state.status = DataSourceStatus.STOPPED.value
                            self.metadata.touch()
                            
                            # 保存停止状态
                            self._save_running_state(False)
                            self.save()
                            
                            self._trigger_stop_callbacks(self)
                            
                            self._log_event("INFO", "Data source stopped")
                        except Exception as e:
                            self.state.status = DataSourceStatus.ERROR.value
                            self.state.record_error(str(e))
                            # 保存错误状态
                            self._save_running_state(False)
                            self.save()
                            self._log_event("ERROR", f"停止数据源时出错: {str(e)}")
                
                self._stop_event.clear()
                self._timer_thread = threading.Thread(
                    target=replay_loop,
                    daemon=True,
                    name=f"ds_replay_{self.name}"
                )
                self._timer_thread.start()
            
            self.state.status = DataSourceStatus.RUNNING.value
            self.stats.start_time = time.time()
            self.metadata.touch()
            
            # 保存运行状态到数据库
            self._save_running_state(True)
            self.save()
            
            self._trigger_start_callbacks(self)
            
            self._log_event("INFO", "Data source started")
            return {"success": True, "status": self.state.status}
            
        except Exception as e:
            self.state.status = DataSourceStatus.ERROR.value
            self.state.record_error(str(e))
            # 保存错误状态
            self._save_running_state(False)
            self.save()
            return {"success": False, "error": str(e)}
    
    def stop(self) -> dict:
        if self.state.status != DataSourceStatus.RUNNING.value:
            return {"success": True, "message": "Not running"}
        
        impact = self._analyze_impact()
        
        try:
            self._stop_event.set()
            if self._timer_thread and self._timer_thread.is_alive():
                self._timer_thread.join(timeout=2)
            
            if self._stream:
                try:
                    # 检查 stream 是否有 stop 方法
                    if hasattr(self._stream, 'stop'):
                        self._stream.stop()
                except Exception as e:
                    self._log_event("WARNING", f"停止流时出错: {str(e)}")
                    pass
            
            self.state.status = DataSourceStatus.STOPPED.value
            self.metadata.touch()
            
            # 保存停止状态
            self._save_running_state(False)
            self.save()
            
            self._trigger_stop_callbacks(self)
            
            self._log_event("INFO", "Data source stopped", impact=impact)
            return {"success": True, "status": self.state.status, "impact": impact}
            
        except Exception as e:
            self.state.status = DataSourceStatus.ERROR.value
            self.state.record_error(str(e))
            # 保存错误状态
            self._save_running_state(False)
            self.save()
            return {"success": False, "error": str(e)}
    
    def _analyze_impact(self) -> dict:
        dependent = self.get_dependent_strategies()
        return {
            "dependent_strategies": dependent,
            "count": len(dependent),
            "warning": f"{len(dependent)} strategies depend on this data source" if dependent else None,
        }
    
    def record_emit(self, count: int = 1):
        self.stats.total_emitted += count
        self.state.last_data_ts = time.time()
        
        self._trigger_data_callbacks(self, count)
    
    def record_data(self, data: Any):
        import asyncio
        
        if asyncio.iscoroutine(data):
            return
        
        if self._stream is None:
            self._stream = NS(self.name, cache_max_len=50, cache_max_age_seconds=3600, description=f'{self.name}数据源的数据流')
        
        if hasattr(self._stream, 'emit'):
            try:
                current_thread = threading.current_thread()
                main_thread = threading.main_thread()
                
                if current_thread is main_thread:
                    self._stream.emit(data)
                else:
                    try:
                        loop = get_io_loop()
                        if loop is not None and not loop._closing:
                            loop.add_callback(lambda d=data: self._stream.emit(d))
                        else:
                            self._stream.emit(data)
                    except Exception:
                        self._stream.emit(data)
            except Exception:
                self._stream.emit(data)
        self.record_emit()
        
        # 保存最新数据状态
        self._save_latest_data(data)
    
    def get_data_stream(self) -> Optional[Stream]:
        return self._stream
    
    def get_recent_data(self, n: int = 10) -> List[Any]:
        if self._stream is None:
            return []
        
        try:
            if hasattr(self._stream, 'recent'):
                cached = self._stream.recent(n)
                return list(cached) if cached else []
        except Exception:
            pass
        return []
    
    def map(self, func: Callable) -> Stream:
        if self._stream:
            return self._stream.map(func)
        return None
    
    def filter(self, func: Callable) -> Stream:
        if self._stream:
            return self._stream.filter(func)
        return None
    
    def sink(self, func: Callable):
        if self._stream:
            return self._stream.sink(func)
        return None
    
    def recent(self, n: int = 10):
        return self.get_recent_data(n)
    
    def __rshift__(self, other):
        if self._stream:
            return self._stream >> other
        return None
    
    def get_output_stream(self) -> Stream:
        return self._stream
    
    def record_error(self, error: str):
        self.state.record_error(error)
        self._log_event("ERROR", error)
        # 保存错误状态
        self.save()
    
    def _save_running_state(self, is_running: bool):
        """保存运行状态到独立的数据库键，确保状态可靠性"""
        try:
            state_db = NB("data_source_states")
            state_info = {
                "id": self._id,
                "name": self.name,
                "is_running": is_running,
                "status": self.state.status,
                "last_update": time.time(),
                "last_data_ts": self.state.last_data_ts,
                "error_count": self.state.error_count,
                "last_error": self.state.last_error,
                "pid": os.getpid(),  # 记录进程ID
            }
            state_db[f"{self._id}_running_state"] = state_info
        except Exception as e:
            self._log_event("ERROR", f"Failed to save running state: {str(e)}")
    
    def _save_latest_data(self, data: Any):
        """保存最新数据状态，用于故障恢复"""
        try:
            data_db = NB("data_source_latest_data")
            data_info = {
                "id": self._id,
                "name": self.name,
                "data": data,
                "data_type": type(data).__name__,
                "timestamp": time.time(),
                "size": len(data) if hasattr(data, '__len__') else 0,
            }
            data_db[f"{self._id}_latest_data"] = data_info
        except Exception as e:
            self._log_event("ERROR", f"Failed to save latest data: {str(e)}")
    
    def get_saved_running_state(self) -> Optional[dict]:
        """获取保存的运行状态"""
        try:
            state_db = NB("data_source_states")
            return state_db.get(f"{self._id}_running_state")
        except Exception as e:
            self._log_event("ERROR", f"Failed to get running state: {str(e)}")
            return None
    
    def get_saved_latest_data(self) -> Optional[dict]:
        """获取保存的最新数据"""
        try:
            data_db = NB("data_source_latest_data")
            return data_db.get(f"{self._id}_latest_data")
        except Exception as e:
            self._log_event("ERROR", f"Failed to get latest data: {str(e)}")
            return None
    
    def _log_event(self, level: str, message: str, **extra):
        """记录数据源事件 - 使用增强的日志系统"""
        log_datasource_event(level, message, datasource=self, **extra)
    
    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "state": self.state.to_dict(),
            "stats": self.stats.to_dict(),
            "dependent_strategies": self.get_dependent_strategies(),
        }
    
    def save(self) -> dict:
        db = NB("data_sources")
        db[self._id] = self.to_dict()
        return {"success": True, "id": self._id}
    
    @classmethod
    def load(cls, source_id: str) -> Optional["DataSource"]:
        db = NB("data_sources")
        data = db.get(source_id)
        if data:
            return cls.from_dict(data)
        return None
    
    @classmethod
    def from_dict(cls, data: dict) -> "DataSource":
        metadata = data.get("metadata", {})
        source = cls(
            name=metadata.get("name", "unnamed"),
            source_type=DataSourceType(metadata.get("source_type", "custom")),
            description=metadata.get("description", ""),
            config=metadata.get("config", {}),
            data_func_code=metadata.get("data_func_code", ""),
            interval=metadata.get("interval", 5.0),
        )
        
        source._id = metadata.get("id", source._id)
        source.metadata.id = source._id
        source.metadata.created_at = metadata.get("created_at", time.time())
        source.metadata.updated_at = metadata.get("updated_at", time.time())
        source.metadata.tags = metadata.get("tags", [])
        
        state_data = data.get("state", {})
        saved_status = state_data.get("status", "stopped")
        source._was_running = (saved_status == DataSourceStatus.RUNNING.value)
        source.state.status = DataSourceStatus.STOPPED.value
        source.state.error_count = state_data.get("error_count", 0)
        source.state.last_error = state_data.get("last_error", "")
        
        for strategy_id in data.get("dependent_strategies", []):
            source.add_dependent_strategy(strategy_id)
        
        return source
    
    def delete(self) -> dict:
        impact = self._analyze_impact()
        
        if self.state.status == DataSourceStatus.RUNNING.value:
            stop_result = self.stop()
            if not stop_result.get("success", False):
                self._log_event("WARNING", f"Failed to stop data source during delete: {stop_result.get('error', 'Unknown error')}")
        
        if self._stream:
            try:
                if hasattr(self._stream, 'destroy'):
                    self._stream.destroy()
            except Exception:
                pass
            self._stream = None
        
        from . import get_ds_manager
        get_ds_manager().unregister(self._id)
        
        with self._instances_lock:
            self._instances.pop(self._id, None)
        
        db = NB("data_sources")
        if self._id in db:
            del db[self._id]
        
        self._log_event("INFO", "Data source deleted", impact=impact)
        return {"success": True, "impact": impact}
    
    def __repr__(self) -> str:
        return f"<DataSource: {self.name} [{self.state.status}]>"


class DataSourceManager(BaseManager[DataSource]):
    """数据源管理器
    
    提供数据源的统一管理、监控和协调功能。
    """
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        super().__init__()
        
        self._strategy_source_map: Dict[str, Set[str]] = {}
        self._map_lock = threading.Lock()
        
        self._initialized = True
    
    def _get_item_id(self, item: DataSource) -> str:
        return item.id
    
    def _get_item_name(self, item: DataSource) -> str:
        return item.name
    
    def _on_registered(self, item: DataSource):
        item.save()
    
    def get_source(self, source_id: str) -> Optional[DataSource]:
        return self.get(source_id)
    
    def get_source_by_name(self, name: str) -> Optional[DataSource]:
        return self.get_by_name(name)
    
    def list_sources(self, status: DataSourceStatus = None) -> List[DataSource]:
        sources = self.list_all()
        if status:
            sources = [s for s in sources if s.status == status]
        return sources
    
    def list_source_objects(self) -> List["DataSource"]:
        with self._items_lock:
            return list(self._items.values())
    
    def list_all(self) -> List[dict]:
        with self._items_lock:
            return [source.to_dict() for source in list(self._items.values())]
    
    def link_strategy(self, source_id: str, strategy_id: str):
        source = self.get_source(source_id)
        if source:
            source.add_dependent_strategy(strategy_id)
        
        with self._map_lock:
            if strategy_id not in self._strategy_source_map:
                self._strategy_source_map[strategy_id] = set()
            self._strategy_source_map[strategy_id].add(source_id)
    
    def unlink_strategy(self, source_id: str, strategy_id: str):
        source = self.get_source(source_id)
        if source:
            source.remove_dependent_strategy(strategy_id)
        
        with self._map_lock:
            if strategy_id in self._strategy_source_map:
                self._strategy_source_map[strategy_id].discard(source_id)
    
    def get_strategies_for_source(self, source_id: str) -> List[str]:
        source = self.get_source(source_id)
        return source.get_dependent_strategies() if source else []
    
    def get_sources_for_strategy(self, strategy_id: str) -> List[str]:
        with self._map_lock:
            return list(self._strategy_source_map.get(strategy_id, set()))
    
    def get_stats(self) -> dict:
        with self._items_lock:
            total = len(self._items)
            running = sum(1 for s in self._items.values() if s.status == DataSourceStatus.RUNNING)
            stopped = sum(1 for s in self._items.values() if s.status == DataSourceStatus.STOPPED)
            error = sum(1 for s in self._items.values() if s.status == DataSourceStatus.ERROR)
        
        return {
            "total_sources": total,
            "running_count": running,
            "stopped_count": stopped,
            "error_count": error,
        }
    
    def create_source(
        self,
        name: str,
        source_type: DataSourceType = DataSourceType.CUSTOM,
        description: str = "",
        config: dict = None,
        stream: Stream = None,
        auto_start: bool = False,
        data_func_code: str = "",
        interval: float = 5.0,
    ) -> dict:
        try:
            source = DataSource(
                name=name,
                source_type=source_type,
                description=description,
                config=config,
                stream=stream,
                auto_start=False,
                data_func_code=data_func_code,
                interval=interval,
            )
            
            if stream:
                source.set_stream(stream)
            
            self.register(source)
            
            if auto_start:
                source.start()
            
            return {
                "success": True,
                "source_id": source.id,
                "source": source.to_dict(),
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
    
    def load_from_db(self) -> int:
        """从数据库加载数据源配置"""
        db = NB("data_sources")
        count = 0
        all_items = list(db.items())
        
        print(f"[DataSourceManager] 从数据库加载数据源，共 {len(all_items)} 条记录")
        
        with self._items_lock:
            existing_names = {s.name for s in self._items.values()}
            for source_id, data in all_items:
                if isinstance(data, dict):
                    try:
                        source = DataSource.from_dict(data)
                        saved_status = data.get("state", {}).get("status", "stopped")
                        was_running = saved_status == "running"
                        
                        if source.id not in self._items and source.name not in existing_names:
                            self._items[source.id] = source
                            existing_names.add(source.name)
                            count += 1
                            print(f"[DataSourceManager] 加载数据源：{source.name} (was_running={was_running})")
                    except Exception as e:
                        print(f"[DataSourceManager] 加载数据源失败：{source_id}, 错误：{e}")
                        pass
        return count
    
    def restore_running_states(self) -> dict:
        """恢复数据源的运行状态"""
        print(f"[DataSourceManager] 开始恢复数据源状态，共{len(list(self._items.values()))}个数据源")
        restored_count = 0
        failed_count = 0
        results = []
        
        with self._items_lock:
            # 扩展恢复逻辑：不仅恢复之前运行的，还要检查保存的状态
            sources_to_check = list(self._items.values())
        
        for source in sources_to_check:
            try:
                # 获取保存的运行状态
                saved_state = source.get_saved_running_state()
                
                # 确定是否应该恢复运行
                should_restore = False
                restore_reason = ""
                
                # 情况1：之前标记为运行状态
                if getattr(source, '_was_running', False):
                    should_restore = True
                    restore_reason = "was_running_flag"
                
                # 情况2：保存的运行状态显示应该运行
                elif saved_state and saved_state.get("is_running", False):
                    should_restore = True
                    restore_reason = "saved_state_running"
                
                # 情况3：当前状态为运行但定时器未启动（修复状态不一致）
                elif source.status == DataSourceStatus.RUNNING.value:
                    should_restore = True
                    restore_reason = "current_status_running"
                
                print(f"[DataSourceManager] 检查数据源：{source.name} (should_restore={should_restore}, reason={restore_reason})")
                if not should_restore:
                    continue
                
                # 检查是否需要跳过恢复
                if saved_state and not saved_state.get("is_running", False) and restore_reason != "current_status_running":
                    results.append({
                        "source_id": source.id,
                        "source_name": source.name,
                        "success": False,
                        "error": "Saved state indicates source should not be running",
                        "skipped": True,
                        "reason": restore_reason,
                    })
                    continue
                
                # 如果已经在运行，检查定时器状态
                if source.status == DataSourceStatus.RUNNING.value:
                    # 检查定时器线程是否活跃
                    if hasattr(source, '_timer_thread') and source._timer_thread and source._timer_thread.is_alive():
                        results.append({
                            "source_id": source.id,
                            "source_name": source.name,
                            "success": True,
                            "message": "Already running with active timer",
                            "reason": restore_reason,
                            "timer_active": True,
                        })
                        continue
                    else:
                        # 状态为运行但定时器不活跃，需要重新启动
                        source._log_event("WARNING", "Status is running but timer inactive, restarting")
                
                # 恢复最新数据状态
                saved_data = source.get_saved_latest_data()
                if saved_data:
                    source._log_event("INFO", "Restoring latest data", 
                                    data_type=saved_data.get("data_type"),
                                    timestamp=saved_data.get("timestamp"))
                
                # 启动数据源
                result = source.start()
                if result.get("success"):
                    restored_count += 1
                    results.append({
                        "source_id": source.id,
                        "source_name": source.name,
                        "success": True,
                        "restored_from_state": bool(saved_state),
                        "restored_with_data": bool(saved_data),
                        "reason": restore_reason,
                        "timer_restarted": source.status == DataSourceStatus.RUNNING.value,
                    })
                else:
                    failed_count += 1
                    results.append({
                        "source_id": source.id,
                        "source_name": source.name,
                        "success": False,
                        "error": result.get("error", "Unknown error"),
                        "restored_from_state": bool(saved_state),
                        "reason": restore_reason,
                    })
            except Exception as e:
                failed_count += 1
                results.append({
                    "source_id": source.id,
                    "source_name": source.name,
                    "success": False,
                    "error": str(e),
                    "reason": restore_reason if 'restore_reason' in locals() else "unknown",
                })
        
        return {
            "success": True,
            "restored_count": restored_count,
            "failed_count": failed_count,
            "results": results,
            "total_attempted": len(sources_to_check),
        }


ds_manager = DataSourceManager.get_instance()


def get_ds_manager() -> DataSourceManager:
    return ds_manager


def create_timer_source(
    name: str,
    interval: float = 5.0,
    func: Callable = None,
    description: str = "",
    auto_start: bool = False,
) -> DataSource:
    from deva import Stream
    
    stream = Stream.timer(func=func, interval=interval, start=False, name=name)
    
    source = DataSource(
        name=name,
        source_type=DataSourceType.TIMER,
        description=description or f"Timer source with {interval}s interval",
        config={"interval": interval},
        stream=stream,
        auto_start=auto_start,
    )
    
    ds_manager.register(source)
    return source


def create_stream_source(
    name: str,
    description: str = "",
    cache_max_len: int = None,
    auto_start: bool = False,
) -> DataSource:
    stream = NS(name, cache_max_len=cache_max_len, description=description or f'命名流数据源: {name}')
    
    source = DataSource(
        name=name,
        source_type=DataSourceType.STREAM,
        description=description or f"Named stream: {name}",
        stream=stream,
        auto_start=auto_start,
    )
    
    ds_manager.register(source)
    return source


def get_replay_tables() -> List[dict]:
    """获取支持回放的数据库表
    
    返回所有使用 key_mode='time' 创建的表，这些表支持按时间顺序回放数据
    """
    from deva import NB
    
    try:
        # 获取默认数据库的所有表
        db = NB('default')
        tables = db.tables
        
        # 过滤出支持回放的表
        replay_tables = []
        for table in tables:
            # 尝试创建 DBStream 对象并检查 key_mode
            try:
                # 这里我们不能直接检查 key_mode，因为它是在初始化时设置的
                # 但我们可以通过尝试按时间范围查询来判断是否支持回放
                test_stream = NB(table, key_mode='time')
                # 尝试获取一个时间范围的键，如果成功，说明表支持时间索引
                keys = list(test_stream['2000-01-01 00:00:00':'2000-01-01 00:01:00'])
                replay_tables.append({
                    'name': table,
                    'description': f'支持时间回放的表: {table}'
                })
            except Exception:
                # 如果创建失败或查询失败，说明表不支持回放
                pass
        
        return replay_tables
    except Exception as e:
        print(f"获取回放表失败: {e}")
        return []


def create_replay_source(
    name: str,
    table_name: str,
    start_time: str = None,
    end_time: str = None,
    interval: float = 1.0,
    description: str = "",
    auto_start: bool = False,
) -> DataSource:
    """创建回放数据源
    
    Args:
        name: 数据源名称
        table_name: 要回放的表名
        start_time: 开始时间，格式为 'YYYY-MM-DD HH:MM:SS'
        end_time: 结束时间，格式为 'YYYY-MM-DD HH:MM:SS'
        interval: 回放间隔（秒）
        description: 数据源描述
        auto_start: 是否自动启动
    """
    config = {
        'table_name': table_name,
        'start_time': start_time,
        'end_time': end_time,
        'interval': interval,
    }
    
    source = DataSource(
        name=name,
        source_type=DataSourceType.REPLAY,
        description=description or f"回放数据源: {table_name}",
        config=config,
        auto_start=auto_start,
    )
    
    ds_manager.register(source)
    return source
