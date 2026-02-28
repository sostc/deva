"""策略执行单元(Strategy Unit)核心模型

策略执行单元是一个独立的逻辑资产，非纯代码或纯数据。它封装了：
- 元数据：名称、ID、备注、属性、上下游血缘(Lineage)
- 执行体：AI生成的Python函数，负责数据转换
- 数据模版(Schema)：输入与输出的数据结构定义
- 状态机：管理生命周期（运行、暂停、归档）

================================================================================
架构设计
================================================================================

【策略执行单元结构】
┌─────────────────────────────────────────────────────────────────────────────┐
│  StrategyUnit                                                               │
│  ├── metadata: 元数据                                                        │
│  │   ├── id: 唯一标识                                                        │
│  │   ├── name: 名称                                                          │
│  │   ├── description: 备注/说明                                              │
│  │   ├── tags: 标签/属性                                                     │
│  │   ├── created_at: 创建时间                                                │
│  │   └── updated_at: 更新时间                                                │
│  │                                                                          │
│  ├── lineage: 血缘关系                                                       │
│  │   ├── upstream_sources: 上游数据源列表                                     │
│  │   └── downstream_sinks: 下游输出列表                                       │
│  │                                                                          │
│  ├── schema: 数据模版                                                        │
│  │   ├── input_schema: 输入数据结构定义                                       │
│  │   └── output_schema: 输出数据结构定义                                      │
│  │                                                                          │
│  ├── execution: 执行体                                                       │
│  │   ├── processor_func: AI生成的处理函数                                     │
│  │   ├── ai_documentation: AI生成的说明文档                                   │
│  │   └── code_version: 代码版本号                                            │
│  │                                                                          │
│  └── state: 状态机                                                           │
│       ├── status: running | paused | archived | draft                        │
│       ├── error_count: 错误计数                                              │
│       └── last_error: 最近错误信息                                           │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import hashlib
import inspect
import json
import threading
import time
import traceback
import weakref
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import pandas as pd

from deva import Stream, NS, NB, log

from ..common.base import (
    BaseMetadata,
    BaseState,
    StatusMixin,
)
from .result_store import get_result_store
from .logging_context import (
    log_strategy_event,
    logging_context_manager,
    with_strategy_logging
)


class StrategyStatus(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"


class OutputType(str, Enum):
    STREAM = "stream"
    API = "api"
    FUNCTION = "function"
    DATASOURCE = "datasource"


@dataclass
class DataSchema:
    name: str
    type: str
    required: bool = True
    description: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SchemaDefinition:
    fields: List[DataSchema] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {"fields": [f.to_dict() for f in self.fields]}
    
    def validate(self, data: Any) -> tuple[bool, str]:
        if not self.fields:
            return True, ""
        if isinstance(data, dict):
            for f in self.fields:
                if f.required and f.name not in data:
                    return False, f"Missing required field: {f.name}"
        return True, ""





@dataclass
class StrategyMetadata(BaseMetadata):
    """策略元数据"""
    owner: str = ""
    version: int = 1
    strategy_func_code: str = ""
    bound_datasource_id: str = ""
    bound_datasource_name: str = ""
    summary: str = ""
    max_history_count: int = 30


@dataclass
class ExecutionState(BaseState):
    """执行状态"""
    status: str = "draft"
    processed_count: int = 0
    last_process_ts: float = 0
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data["processed_count"] = self.processed_count
        data["last_process_ts"] = self.last_process_ts
        return data


class StrategyUnit(StatusMixin):
    """策略执行单元
    
    一个独立的逻辑资产，封装了数据处理逻辑、元数据和状态管理。
    """
    
    _instances: Dict[str, weakref.ref] = {}
    _instances_lock = threading.Lock()
    
    def __init__(
        self,
        name: str,
        processor_func: Callable = None,
        description: str = "",
        tags: List[str] = None,
        input_schema: SchemaDefinition = None,
        output_schema: SchemaDefinition = None,
        auto_start: bool = False,
        strategy_func_code: str = "",
        bound_datasource_id: str = "",
        bound_datasource_name: str = "",
        max_history_count: int = 30,
    ):
        self._id = self._generate_id(name)
        self.metadata = StrategyMetadata(
            id=self._id,
            name=name,
            description=description,
            tags=tags or [],
            strategy_func_code=strategy_func_code,
            bound_datasource_id=bound_datasource_id,
            bound_datasource_name=bound_datasource_name,
            max_history_count=max_history_count,
        )
        
        self.input_schema = input_schema or SchemaDefinition()
        self.output_schema = output_schema or SchemaDefinition()
        self.state = ExecutionState()
        self.state.status = StrategyStatus.STOPPED.value
        
        self._processor_func = None
        self._processor_code = ""
        self._ai_documentation = ""
        self._code_version = 0
        
        self._input_stream: Optional[Stream] = None
        self._output_stream: Optional[Stream] = None
        self._error_stream: Optional[Stream] = None
        self._processing_lock = threading.Lock()
        self._was_running: bool = False
        self._input_data_buffer: List[Dict] = []
        self._input_buffer_lock = threading.Lock()
        
        if processor_func:
            self.set_processor(processor_func)
        
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
    def get_instance(cls, unit_id: str) -> Optional["StrategyUnit"]:
        with cls._instances_lock:
            ref = cls._instances.get(unit_id)
            return ref() if ref else None
    
    @classmethod
    def get_all_instances(cls) -> List["StrategyUnit"]:
        with cls._instances_lock:
            instances = []
            dead_refs = []
            for unit_id, ref in cls._instances.items():
                unit = ref()
                if unit:
                    instances.append(unit)
                else:
                    dead_refs.append(unit_id)
            for unit_id in dead_refs:
                del cls._instances[unit_id]
            return instances
    
    @property
    def id(self) -> str:
        return self._id
    
    @property
    def name(self) -> str:
        return self.metadata.name
    
    @property
    def status(self) -> StrategyStatus:
        # 处理旧的状态值，映射到新的状态
        old_status = self.state.status
        if old_status in ["paused", "draft", "archived"]:
            return StrategyStatus.STOPPED
        elif old_status == "running":
            return StrategyStatus.RUNNING
        else:
            return StrategyStatus.STOPPED
    
    @property
    def is_paused(self) -> bool:
        return self.state.status == StrategyStatus.STOPPED.value
    
    @property
    def is_running(self) -> bool:
        return self.state.status == StrategyStatus.RUNNING.value
    
    def set_processor(self, func: Callable, code: str = None, ai_doc: str = None):
        if not callable(func):
            raise ValueError("processor_func must be callable")
        
        self._processor_func = func
        self._processor_code = code or inspect.getsource(func) if hasattr(func, '__code__') else ""
        self._ai_documentation = ai_doc or func.__doc__ or ""
        self._code_version += 1
        self.metadata.touch()
    
    def set_processor_from_code(self, code: str, func_name: str = "process", ai_doc: str = None):
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
        
        local_vars = {}
        exec(code, global_env, local_vars)
        
        func = local_vars.get(func_name)
        if not callable(func):
            raise ValueError(f"Function '{func_name}' not found in code")
        
        for name, obj in local_vars.items():
            if callable(obj) and hasattr(obj, '__globals__'):
                obj.__globals__.update(global_env)
                obj.__globals__.update(local_vars)
        
        self.set_processor(func, code=code, ai_doc=ai_doc)
    
    def update_strategy_func_code(self, code: str) -> dict:
        """更新策略执行代码并保存到数据库"""
        try:
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
            
            import sys
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            
            try:
                exec(code, test_globals, test_locals)
            except Exception as exec_error:
                sys.stdout = old_stdout
                error_msg = str(exec_error)
                if "indent" in error_msg.lower():
                    return {"success": False, "error": f"代码缩进错误: {error_msg}"}
                return {"success": False, "error": f"代码编译错误: {error_msg}"}
            finally:
                sys.stdout = old_stdout
            
            if "process" not in test_locals or not callable(test_locals["process"]):
                return {"success": False, "error": "代码必须包含可调用的process函数"}
            
            import inspect
            sig = inspect.signature(test_locals["process"])
            params = list(sig.parameters.keys())
            if not params or params[0] not in ("data", "df"):
                return {"success": False, "error": f"process函数的第一个参数名必须是 'data' 或 'df'，当前为 '{params[0] if params else '无参数'}'"}
            
            # 提取函数文档
            func_doc = test_locals["process"].__doc__ or ""
            
            old_code = self.metadata.strategy_func_code
            
            self.metadata.strategy_func_code = code
            self.metadata.touch()
            
            self._save_code_version(code, old_code)
            
            try:
                self.set_processor_from_code(code, ai_doc=func_doc)
            except Exception as e:
                pass
            
            self.save()
            
            self._log_event("INFO", "Strategy function code updated")
            return {"success": True, "message": "代码更新成功"}
            
        except Exception as e:
            return {"success": False, "error": f"代码更新失败: {str(e)}"}
    
    def _save_code_version(self, new_code: str, old_code: str):
        """保存代码版本历史"""
        try:
            version_db = NB("strategy_code_versions")
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
            version_db = NB("strategy_code_versions")
            versions = []
            prefix = f"{self._id}_code_"
            
            for key, value in version_db.items():
                if key.startswith(prefix):
                    versions.append(value)
            
            versions.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return versions[:limit]
            
        except Exception as e:
            self._log_event("ERROR", f"Failed to get code versions: {str(e)}")
            return []
    
    def get_processor_code(self) -> str:
        return self._processor_code
    
    def get_ai_documentation(self) -> str:
        return self._ai_documentation
    
    def set_input_stream(self, stream: Stream):
        self._input_stream = stream
        
        # Add a sink to track input data
        def track_input_data(data):
            from datetime import datetime
            input_info = {
                "data": data,
                "timestamp": datetime.now().isoformat(),
                "data_type": type(data).__name__,
                "data_size": len(data) if hasattr(data, '__len__') else 0
            }
            with self._input_buffer_lock:
                self._input_data_buffer.append(input_info)
                # Keep only the most recent 3 items
                if len(self._input_data_buffer) > 3:
                    self._input_data_buffer = self._input_data_buffer[-3:]
        
        if hasattr(stream, 'sink'):
            stream.sink(track_input_data)
    
    def get_recent_input_data(self, limit: int = 3) -> List[Dict]:
        """获取最近的输入数据概览"""
        # First try to get data from bound datasource
        if self.metadata.bound_datasource_id:
            try:
                from deva.admin_ui.datasource.datasource import get_ds_manager
                ds_mgr = get_ds_manager()
                datasource = ds_mgr.get_source(self.metadata.bound_datasource_id)
                if datasource:
                    recent_data = datasource.get_recent_data(limit)
                    if recent_data:
                        from datetime import datetime
                        formatted_data = []
                        for data in recent_data:
                            data_info = {
                                "data": data,
                                "timestamp": datetime.now().isoformat(),
                                "data_type": type(data).__name__,
                                "data_size": len(data) if hasattr(data, '__len__') else 0
                            }
                            formatted_data.append(data_info)
                        return formatted_data
            except Exception:
                pass
        
        # Fall back to input stream data
        with self._input_buffer_lock:
            return self._input_data_buffer[-limit:]
    
    def bind_datasource(self, datasource_id: str, datasource_name: str):
        """绑定到数据源"""
        self.metadata.bound_datasource_id = datasource_id
        self.metadata.bound_datasource_name = datasource_name
        self.metadata.touch()
        self.save()
        self._log_event("INFO", f"Bound to datasource: {datasource_name}")
    
    def unbind_datasource(self):
        """解除数据源绑定"""
        self.metadata.bound_datasource_id = ""
        self.metadata.bound_datasource_name = ""
        self.metadata.touch()
        self.save()
        self._log_event("INFO", "Unbound from datasource")
    

    
    def set_error_stream(self, stream: Stream):
        self._error_stream = stream
    

    
    def start(self) -> dict:
        if self.state.status == StrategyStatus.RUNNING.value:
            return {"success": True, "message": "Already running"}
        
        if not self._processor_func:
            return {"success": False, "error": "No processor function set"}
        
        # 确保函数文档已更新
        if self._processor_code:
            try:
                # 重新设置处理器以确保文档已更新
                self.set_processor_from_code(self._processor_code, ai_doc=self._ai_documentation)
            except Exception as e:
                self._log_event("ERROR", f"Failed to update processor documentation: {str(e)}")
        
        self.state.status = StrategyStatus.RUNNING.value
        self.metadata.touch()
        
        self.save()
        
        if self.metadata.bound_datasource_id:
            self._bind_to_datasource_on_start()
        else:
            self._log_event("WARNING", "Strategy started without bound datasource. Please bind a datasource for proper operation.")
        
        self._log_event("INFO", "Strategy started")
        return {"success": True, "status": self.state.status, "ai_documentation": self._ai_documentation}
    
    def _bind_to_datasource_on_start(self):
        """启动时重新绑定到数据源"""
        if not self._processor_func or not self._processor_code:
            return
            
        try:
            from deva.admin_ui.datasource import get_ds_manager
            
            ds_mgr = get_ds_manager()
            source = ds_mgr.get_source(self.metadata.bound_datasource_id)
            
            if source and self._processor_code:
                source_stream = source.get_stream()
                if source_stream:
                    from deva import NS
                    output_stream_name = f"strategy_output_{self.id}"
                    output_stream = NS(
                        output_stream_name,
                        cache_max_len=3,
                        cache_max_age_seconds=3600,
                        description=f"策略 {self.name} 的输出流"
                    )
                    
                    source_stream.map(lambda data: self.process(data)) >> output_stream
                    
                    self._input_stream = source_stream
                    self._output_stream = output_stream
        except Exception as e:
            self._log_event("ERROR", f"Failed to bind to datasource on start: {str(e)}")
    
    def stop(self) -> dict:
        if self.state.status != StrategyStatus.RUNNING.value:
            return {"success": True, "message": "Not running"}
        
        self.state.status = StrategyStatus.STOPPED.value
        self.metadata.touch()
        
        # 断开与数据源的连接，确保策略真正停止执行
        if self.metadata.bound_datasource_id:
            try:
                from deva.admin_ui.datasource import get_ds_manager
                ds_mgr = get_ds_manager()
                source = ds_mgr.get_source(self.metadata.bound_datasource_id)
                if source:
                    # 这里可以添加断开连接的逻辑
                    pass
            except Exception as e:
                self._log_event("ERROR", f"Failed to disconnect from datasource: {str(e)}")
        
        self._save_running_state(False)
        self.save()
        
        self._log_event("INFO", "Strategy stopped")
        return {"success": True, "status": self.state.status}
    
    def resume(self) -> dict:
        if self.state.status != StrategyStatus.STOPPED.value:
            return {"success": False, "error": "Not stopped"}
        
        result = self.start()
        # 确保返回函数文档
        result["ai_documentation"] = self._ai_documentation
        return result
    
    def archive(self) -> dict:
        self.state.status = StrategyStatus.STOPPED.value
        self.metadata.touch()
        
        self._save_running_state(False)
        
        self._log_event("INFO", "Strategy archived")
        return {"success": True, "status": self.state.status}
    

    
    def process(self, data: Any) -> Any:
        if not self.is_running:
            return None
        
        if not self._processor_func:
            return None
        
        # 使用策略上下文包装整个处理过程
        with logging_context_manager.strategy_context(self.id, self.name):
            with self._processing_lock:
                start_time = time.time()
                result = None
                error_msg = ""
                success = False
                
                try:
                    valid, msg = self.input_schema.validate(data)
                    if not valid:
                        error_msg = f"Schema validation failed: {msg}"
                        self._emit_error(error_msg, data)
                        self._save_result(data, None, 0, False, error_msg)
                        return None
                    
                    result = self._processor_func(data)
                    
                    if result is not None:
                        valid, msg = self.output_schema.validate(result)
                        if not valid:
                            error_msg = f"Output schema validation failed: {msg}"
                            self._emit_error(error_msg, result)
                            self._save_result(data, None, 0, False, error_msg)
                            return None
                    
                    self.state.processed_count += 1
                    self.state.last_process_ts = time.time()
                    success = True
                    
                    if self._output_stream and result is not None:
                        self._output_stream.emit(result)
                    
                    return result
                    
                except Exception as e:
                    error_msg = str(e)
                    self.state.record_error(error_msg)
                    self._emit_error(error_msg, data, traceback.format_exc())
                    return None
                
                finally:
                    process_time_ms = (time.time() - start_time) * 1000
                    self._save_result(data, result, process_time_ms, success, error_msg)
    
    def _save_result(
        self,
        input_data: Any,
        output_data: Any,
        process_time_ms: float,
        success: bool,
        error: str = "",
    ):
        try:
            store = get_result_store()
            store.save(
                strategy_id=self._id,
                strategy_name=self.name,
                success=success,
                input_data=input_data,
                output_data=output_data,
                process_time_ms=process_time_ms,
                error=error,
                persist=True,
            )
            
            # 检查并清理超过限制的历史记录
            max_count = self.metadata.max_history_count
            if max_count > 0:
                store.cleanup(strategy_id=self._id, max_count=max_count)
        except Exception:
            pass
    
    def get_recent_results(self, limit: int = 10) -> list:
        store = get_result_store()
        results = store.get_recent(self._id, limit=limit)
        return [r.to_dict() for r in results]
    
    def _emit_error(self, error_msg: str, data: Any, tb: str = ""):
        error_info = {
            "strategy_id": self._id,
            "strategy_name": self.name,
            "error": error_msg,
            "data_preview": str(data)[:500] if data else None,
            "traceback": tb,
            "ts": datetime.now().isoformat(),
        }
        
        if self._error_stream:
            self._error_stream.emit(error_info)
        
        self._log_event("ERROR", error_msg, traceback=tb[:200] if tb else None)
    
    def _log_event(self, level: str, message: str, **extra):
        """记录策略事件 - 使用增强的日志系统"""
        log_strategy_event(level, message, strategy_unit=self, **extra)
    
    def _save_running_state(self, is_running: bool):
        """保存策略运行状态到数据库"""
        try:
            state_db = NB("strategy_running_states")
            state_info = {
                "id": self._id,
                "name": self.name,
                "is_running": is_running,
                "status": self.state.status,
                "last_update": time.time(),
                "processed_count": self.state.processed_count,
                "error_count": self.state.error_count,
            }
            state_db[f"{self._id}_running_state"] = state_info
        except Exception:
            pass
    
    def update_logic(self, func: Callable = None, code: str = None, ai_doc: str = None):
        if func:
            self.set_processor(func, ai_doc=ai_doc)
        elif code:
            self.set_processor_from_code(code, ai_doc=ai_doc)
        else:
            raise ValueError("Either func or code must be provided")
        
        self._log_event("INFO", "Logic updated", version=self._code_version)
    
    def to_dict(self) -> dict:
        recent_inputs = self.get_recent_input_data()
        # Format input data for display
        formatted_inputs = []
        for input_item in recent_inputs:
            formatted_input = {
                "timestamp": input_item["timestamp"],
                "data_type": input_item["data_type"],
                "data_size": input_item["data_size"]
            }
            # Add a preview if possible
            if isinstance(input_item["data"], (list, dict, str)):
                if isinstance(input_item["data"], str):
                    preview = input_item["data"][:100] + ("..." if len(input_item["data"]) > 100 else "")
                else:
                    import json
                    try:
                        preview = json.dumps(input_item["data"], ensure_ascii=False)[:100] + ("..." if len(str(input_item["data"])) > 100 else "")
                    except:
                        preview = str(input_item["data"])[:100] + ("..." if len(str(input_item["data"])) > 100 else "")
                formatted_input["preview"] = preview
            formatted_inputs.append(formatted_input)
        
        return {
            "metadata": self.metadata.to_dict(),
            "input_schema": self.input_schema.to_dict(),
            "output_schema": self.output_schema.to_dict(),
            "state": self.state.to_dict(),
            "code_version": self._code_version,
            "has_processor": self._processor_func is not None,
            "processor_code": self._processor_code,
            "ai_documentation": self._ai_documentation,
            "recent_inputs": formatted_inputs,
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_dict(cls, data: dict) -> "StrategyUnit":
        metadata = data.get("metadata", {})
        unit = cls(
            name=metadata.get("name", "unnamed"),
            description=metadata.get("description", ""),
            tags=metadata.get("tags", []),
        )
        
        unit._id = metadata.get("id", unit._id)
        unit.metadata.id = unit._id
        unit.metadata.created_at = metadata.get("created_at", time.time())
        unit.metadata.updated_at = metadata.get("updated_at", time.time())
        unit.metadata.version = metadata.get("version", 1)
        unit.metadata.summary = metadata.get("summary", "")
        unit.metadata.max_history_count = metadata.get("max_history_count", 0)
        
        state_data = data.get("state", {})
        saved_status = state_data.get("status", "draft")
        # 处理旧的状态值，映射到新的状态
        if saved_status in ["paused", "draft", "archived"]:
            unit.state.status = StrategyStatus.STOPPED.value
        elif saved_status == "running":
            unit.state.status = StrategyStatus.RUNNING.value
        else:
            unit.state.status = StrategyStatus.STOPPED.value
        unit._was_running = (saved_status == "running")
        unit.state.error_count = state_data.get("error_count", 0)
        unit.state.last_error = state_data.get("last_error", "")
        unit.state.processed_count = state_data.get("processed_count", 0)
        unit.state.last_process_ts = state_data.get("last_process_ts", 0)
        
        processor_code = data.get("processor_code", "")
        ai_documentation = data.get("ai_documentation", "")
        if processor_code:
            try:
                # 尝试不同的函数名
                func_names = ["process", "processor", "test_strategy_processor"]
                success = False
                for func_name in func_names:
                    try:
                        unit.set_processor_from_code(processor_code, func_name=func_name, ai_doc=ai_documentation)
                        success = True
                        break
                    except Exception:
                        continue
                if not success:
                    # 尝试动态查找函数
                    import re
                    match = re.search(r'def\s+(\w+)\s*\(', processor_code)
                    if match:
                        func_name = match.group(1)
                        unit.set_processor_from_code(processor_code, func_name=func_name, ai_doc=ai_documentation)
                        success = True
                if not success:
                    unit._processor_code = processor_code
                    unit._ai_documentation = ai_documentation
            except Exception:
                unit._processor_code = processor_code
                unit._ai_documentation = ai_documentation
        
        unit.metadata.bound_datasource_id = metadata.get("bound_datasource_id", "")
        unit.metadata.bound_datasource_name = metadata.get("bound_datasource_name", "")
        
        return unit
    
    def save(self) -> dict:
        db = NB("strategy_units")
        db[self._id] = self.to_dict()
        return {"success": True, "id": self._id}
    
    @classmethod
    def load(cls, unit_id: str) -> Optional["StrategyUnit"]:
        db = NB("strategy_units")
        data = db.get(unit_id)
        if data:
            return cls.from_dict(data)
        return None
    
    def delete(self) -> dict:
        self.archive()
        
        with self._instances_lock:
            self._instances.pop(self._id, None)
        
        db = NB("strategy_units")
        if self._id in db:
            del db[self._id]
        
        self._log_event("INFO", "Strategy deleted")
        return {"success": True}
    
    def __repr__(self) -> str:
        return f"<StrategyUnit: {self.name} [{self.state.status}]>"
    
    def __str__(self) -> str:
        return self.__repr__()


def create_strategy_unit(
    name: str,
    processor_func: Callable = None,
    description: str = "",
    max_history_count: int = 30,
    **kwargs,
) -> StrategyUnit:
    unit = StrategyUnit(
        name=name,
        processor_func=processor_func,
        description=description,
        max_history_count=max_history_count,
        **kwargs,
    )
    
    return unit
