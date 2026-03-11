"""Strategy V2 - 基于 RecoverableUnit 抽象"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from deva import NB
from deva.core.namespace import NS

from ..common.recoverable import (
    RecoverableUnit,
    UnitMetadata,
    UnitState,
    UnitStatus,
)


STRATEGY_TABLE = "naja_strategies"
STRATEGY_RESULTS_TABLE = "naja_strategy_results"
STRATEGY_EXPERIMENT_TABLE = "naja_strategy_experiment"
STRATEGY_EXPERIMENT_ACTIVE_KEY = "active_session"


@dataclass
class StrategyMetadata(UnitMetadata):
    """策略元数据"""
    bound_datasource_id: str = ""
    bound_datasource_ids: List[str] = field(default_factory=list)  # 多数据源支持
    compute_mode: str = "record"
    window_size: int = 5
    window_type: str = "sliding"
    window_interval: str = "10s"
    window_return_partial: bool = False
    dictionary_profile_ids: List[str] = field(default_factory=list)
    max_history_count: int = 100
    diagram_info: Dict[str, Any] = field(default_factory=dict)
    category: str = "默认"  # 策略类别


@dataclass
class StrategyState(UnitState):
    """策略状态"""
    processed_count: int = 0
    last_process_ts: float = 0
    output_count: int = 0


class StrategyEntry(RecoverableUnit):
    """策略条目"""
    
    def __init__(
        self,
        metadata: StrategyMetadata = None,
        state: StrategyState = None,
    ):
        super().__init__(
            metadata=metadata or StrategyMetadata(),
            state=state or StrategyState(),
        )
        
        self._input_stream: Optional[Any] = None
        self._input_streams: Dict[str, Any] = {}  # 多数据源支持：数据源ID -> 流
        self._datasource_names: Dict[str, str] = {}  # 数据源ID -> 名称
        self._output_stream: Optional[Any] = None
        self._processing_lock = threading.Lock()
        self._window_buffer: List[Any] = []
        self._last_window_trigger: float = 0  # 上次窗口触发时间
    
    def _get_func_name(self) -> str:
        return "process"
    
    def _do_compile(self, code: str) -> Callable:
        env = self._build_execution_env()
        exec(code, env)
        
        func = env.get(self._get_func_name())
        if not func or not callable(func):
            raise ValueError(f"函数 '{self._get_func_name()}' 未在代码中定义")
        
        return func
    
    def _do_start(self, func: Callable) -> dict:
        try:
            # 获取多数据源ID列表
            datasource_ids = getattr(self._metadata, "bound_datasource_ids", [])
            if not datasource_ids:
                # 兼容旧版本单数据源
                datasource_id = getattr(self._metadata, "bound_datasource_id", "")
                if datasource_id:
                    datasource_ids = [datasource_id]
            
            if not datasource_ids:
                return {"success": True, "message": "No datasource bound"}
            
            from ..datasource import get_datasource_manager
            ds_mgr = get_datasource_manager()
            
            bound_count = 0
            failed_datasources = []
            
            for ds_id in datasource_ids:
                ds = ds_mgr.get(ds_id)
                if ds is None:
                    failed_datasources.append(ds_id)
                    continue
                
                try:
                    self._bind_datasource(ds)
                    bound_count += 1
                except Exception as e:
                    self._log("ERROR", f"Bind datasource failed", datasource_id=ds_id, error=str(e))
                    failed_datasources.append(ds_id)
            
            if bound_count == 0:
                return {"success": True, "message": f"No datasources could be bound. Failed: {failed_datasources}"}
            
            return {
                "success": True, 
                "message": f"Bound {bound_count} datasources, failed: {len(failed_datasources)}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _do_stop(self) -> dict:
        try:
            self._input_stream = None
            self._output_stream = None
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _bind_datasource(self, datasource: Any):
        """绑定数据源"""
        try:
            ds_id = datasource.id
            ds_name = datasource.name
            stream = datasource.get_stream()
            
            if stream is None:
                self._log("ERROR", "Bind datasource failed: stream is None", datasource_id=ds_id)
                return
            
            # 保存流和名称（多数据源支持）
            self._input_streams[ds_id] = stream
            self._datasource_names[ds_id] = ds_name
            
            # 兼容单数据源模式
            if self._input_stream is None:
                self._input_stream = stream
            
            output_stream_name = f"strategy_output_{self.id}"
            self._output_stream = NS(
                output_stream_name,
                cache_max_len=10,
                cache_max_age_seconds=3600,
                description=f"Strategy {self.name} output",
            )
            
            # 创建数据源特定的数据处理函数
            def create_on_data(datasource_id: str, datasource_name: str):
                def on_data(data: Any):
                    # 添加数据源信息到数据
                    enriched_data = {
                        "_datasource_id": datasource_id,
                        "_datasource_name": datasource_name,
                        "_receive_time": time.time(),
                        "data": data,
                    }
                    self._process_data(enriched_data)
                return on_data
            
            on_data = create_on_data(ds_id, ds_name)
            
            if hasattr(stream, "sink"):
                stream.sink(on_data)
            elif hasattr(stream, "map"):
                mapped_stream = stream.map(on_data)
                mapped_stream.sink(lambda x: None)
            elif hasattr(stream, "subscribe"):
                stream.subscribe(on_data)
            else:
                self._log("ERROR", "No valid subscription method found on stream", datasource_id=ds_id)
            
            self._log("INFO", f"Datasource bound successfully", datasource_id=ds_id, name=ds_name)
                
        except Exception as e:
            self._log("ERROR", "Bind datasource failed", error=str(e))
    
    def _process_data(self, data: Any):
        """处理数据"""
        if not self.is_running:
            return
        
        if self._compiled_func is None:
            return
        
        with self._processing_lock:
            start_time = time.time()
            success = False
            result = None
            error = ""
            skipped = False  # 是否跳过（如 timed 窗口未触发）
            duplicate = False  # 是否与上次结果相同
            
            try:
                data = self._enrich_data(data)
                
                compute_mode = getattr(self._metadata, "compute_mode", "record")
                
                if compute_mode == "window":
                    result = self._process_window(data)
                    # timed 窗口未触发时返回 None，标记为跳过
                    if result is None and getattr(self._metadata, "window_type", "sliding") == "timed":
                        skipped = True
                else:
                    result = self._process_record(data)
                
                if not skipped:
                    success = True
                    self._state.processed_count += 1
                    self._state.last_process_ts = time.time()
                    
                    if result is not None:
                        # 检查是否与上次结果相同
                        if self._is_duplicate_result(result):
                            duplicate = True
                        else:
                            self._emit_result(result)
                            self._state.output_count += 1
                
            except Exception as e:
                error = str(e)
                self._state.record_error(error)
                self._log("ERROR", "Process data failed", error=str(e))
            
            # 保存结果（包括未命中的情况）
            if not skipped and not duplicate:
                process_time_ms = (time.time() - start_time) * 1000
                # 只有命中策略（result 不为 None）才保存到结果存储
                if result is not None:
                    self._save_result_to_store(data, result, process_time_ms, success, error)
    
    def _is_duplicate_result(self, result: Any) -> bool:
        """检查结果是否与上次相同"""
        import json
        
        try:
            # 获取上次结果
            from .result_store import get_result_store
            store = get_result_store()
            recent = store.get_recent(self.id, limit=1)
            
            if not recent:
                return False
            
            last_result = recent[0].output_full
            
            # 比较结果
            if last_result is None and result is None:
                return True
            
            if last_result is None or result is None:
                return False
            
            # 排除时间戳等动态字段后比较
            exclude_keys = {'timestamp', 'ts', 'datetime', 'time', 'created_at', 'updated_at'}
            
            def filter_result(r):
                if isinstance(r, dict):
                    return {k: v for k, v in r.items() if k not in exclude_keys}
                return r
            
            last_filtered = filter_result(last_result)
            current_filtered = filter_result(result)
            
            # 序列化比较
            last_json = json.dumps(last_filtered, sort_keys=True, default=str)
            current_json = json.dumps(current_filtered, sort_keys=True, default=str)
            
            return last_json == current_json
            
        except Exception:
            return False
    
    def _process_record(self, data: Any) -> Any:
        # Create context object
        context = {
            'strategy_id': self.id,
            'strategy_name': self.name,
            'metadata': self._metadata.to_dict(),
            'state': self._state.to_dict()
        }
        
        # Try calling with context first, then fallback to data only
        try:
            result = self._compiled_func(data, context)
        except TypeError:
            # Fallback to data only for backward compatibility
            result = self._compiled_func(data)
            
        if asyncio.iscoroutine(result):
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(result)
            finally:
                loop.close()
        return result
    
    def _process_window(self, data: Any) -> Any:
        window_type = getattr(self._metadata, "window_type", "sliding") or "sliding"
        window_size = max(1, int(getattr(self._metadata, "window_size", 5) or 5))
        return_partial = bool(getattr(self._metadata, "window_return_partial", False))
        
        self._window_buffer.append(data)
        
        if window_type == "sliding":
            if len(self._window_buffer) > window_size:
                self._window_buffer = self._window_buffer[-window_size:]
            
            if not return_partial and len(self._window_buffer) < window_size:
                return None
            
            # Create context object
            context = {
                'strategy_id': self.id,
                'strategy_name': self.name,
                'metadata': self._metadata.to_dict(),
                'state': self._state.to_dict()
            }
            
            # Try calling with context first, then fallback to data only
            try:
                result = self._compiled_func(list(self._window_buffer), context)
            except TypeError:
                # Fallback to data only for backward compatibility
                result = self._compiled_func(list(self._window_buffer))
                
            if asyncio.iscoroutine(result):
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(result)
                finally:
                    loop.close()
            return result
        
        elif window_type == "timed":
            # 定时窗口：按时间间隔触发
            window_interval_str = getattr(self._metadata, "window_interval", "10s") or "10s"
            interval_seconds = self._parse_interval(window_interval_str)
            
            now = time.time()
            
            # 首次调用时，初始化触发时间，等待下一个周期
            if self._last_window_trigger == 0:
                self._last_window_trigger = now
                return None
            
            should_trigger = (now - self._last_window_trigger) >= interval_seconds
            
            if not should_trigger:
                return None
            
            # 触发窗口处理
            self._last_window_trigger = now
            
            if len(self._window_buffer) < 1:
                return None
            
            # Create context object
            context = {
                'strategy_id': self.id,
                'strategy_name': self.name,
                'metadata': self._metadata.to_dict(),
                'state': self._state.to_dict()
            }
            
            # Try calling with context first, then fallback to data only
            try:
                result = self._compiled_func(list(self._window_buffer), context)
            except TypeError:
                # Fallback to data only for backward compatibility
                result = self._compiled_func(list(self._window_buffer))
                
            # 清空窗口缓冲区，开始新的窗口周期
            self._window_buffer = []
            
            if asyncio.iscoroutine(result):
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(result)
                finally:
                    loop.close()
            return result
        
        else:
            if len(self._window_buffer) > window_size:
                self._window_buffer = self._window_buffer[-window_size:]
            
            if len(self._window_buffer) < window_size:
                return None
            
            # Create context object
            context = {
                'strategy_id': self.id,
                'strategy_name': self.name,
                'metadata': self._metadata.to_dict(),
                'state': self._state.to_dict()
            }
            
            # Try calling with context first, then fallback to data only
            try:
                result = self._compiled_func(list(self._window_buffer), context)
            except TypeError:
                # Fallback to data only for backward compatibility
                result = self._compiled_func(list(self._window_buffer))
                
            if asyncio.iscoroutine(result):
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(result)
                finally:
                    loop.close()
            return result
    
    def _parse_interval(self, interval_str: str) -> float:
        """解析时间间隔字符串，返回秒数"""
        if not interval_str:
            return 10.0
        
        interval_str = str(interval_str).strip().lower()
        
        # 支持的格式: 10s, 5min, 1h, 30m, 2hour 等
        import re
        match = re.match(r'^(\d+(?:\.\d+)?)\s*(s|sec|second|seconds|m|min|minute|minutes|h|hour|hours)?$', interval_str)
        
        if not match:
            try:
                return float(interval_str)
            except ValueError:
                return 10.0
        
        value = float(match.group(1))
        unit = match.group(2) or 's'
        
        if unit in ('s', 'sec', 'second', 'seconds'):
            return value
        elif unit in ('m', 'min', 'minute', 'minutes'):
            return value * 60
        elif unit in ('h', 'hour', 'hours'):
            return value * 3600
        
        return value
    
    def _enrich_data(self, data: Any) -> Any:
        """数据补齐"""
        import pandas as pd
        
        profile_ids = getattr(self._metadata, "dictionary_profile_ids", [])
        if not profile_ids:
            return data
        
        if not isinstance(data, pd.DataFrame):
            return data
        
        result = data
        for profile_id in profile_ids:
            result = self._enrich_dataframe(result, profile_id)
        
        return result
    
    def _enrich_dataframe(self, df: Any, profile_id: str) -> Any:
        """使用字典数据补齐 DataFrame"""
        try:
            from ..dictionary import get_dictionary_manager
            dict_mgr = get_dictionary_manager()
            entry = dict_mgr.get(profile_id)
            
            if entry is None:
                return df
            
            dim_data = entry.get_payload()
            if dim_data is None:
                return df
            
            import pandas as pd
            if not isinstance(dim_data, pd.DataFrame):
                dim_df = pd.DataFrame(dim_data) if isinstance(dim_data, (list, dict)) else None
            else:
                dim_df = dim_data
            
            if dim_df is None or dim_df.empty:
                return df
            
            join_key = self._infer_join_key(df, dim_df)
            if not join_key:
                return df
            
            left_df = df.copy()
            right_df = dim_df.copy()
            
            if join_key == "code":
                left_df[join_key] = left_df[join_key].astype(str)
                right_df[join_key] = right_df[join_key].astype(str)
            
            enrich_cols = [c for c in right_df.columns if c != join_key]
            if not enrich_cols:
                return left_df
            
            merged = left_df.merge(
                right_df[[join_key] + enrich_cols],
                on=join_key,
                how="left",
                suffixes=("", "__dict"),
            )
            
            for col in enrich_cols:
                dict_col = f"{col}__dict"
                if dict_col not in merged.columns:
                    continue
                if col in left_df.columns:
                    merged[col] = merged[col].where(merged[col].notna(), merged[dict_col])
                    merged.drop(columns=[dict_col], inplace=True)
                else:
                    merged.rename(columns={dict_col: col}, inplace=True)
            
            return merged
            
        except Exception:
            return df
    
    def _infer_join_key(self, left_df: Any, right_df: Any) -> Optional[str]:
        common_cols = set(left_df.columns).intersection(set(right_df.columns))
        for key in ("code", "ts_code", "symbol", "name"):
            if key in common_cols:
                return key
        return None
    
    def _emit_result(self, result: Any):
        if self._output_stream is None:
            return
        
        try:
            if hasattr(self._output_stream, "emit"):
                self._output_stream.emit(result)
            
            self._save_result(result)
            
        except Exception as e:
            self._log("ERROR", "Emit result failed", error=str(e))
    
    def _save_result(self, result: Any):
        try:
            db = NB(STRATEGY_RESULTS_TABLE)
            result_key = f"{self.id}_{int(time.time() * 1000)}"
            db[result_key] = {
                "strategy_id": self.id,
                "strategy_name": self.name,
                "result": result,
                "timestamp": time.time(),
            }
        except Exception:
            pass
    
    def _save_result_to_store(self, input_data: Any, output_data: Any, process_time_ms: float, success: bool, error: str = ""):
        """保存执行结果到 ResultStore"""
        from .result_store import get_result_store
        from ..config import get_strategy_total_history_count
        
        store = get_result_store()
        store.save(
            strategy_id=self.id,
            strategy_name=self.name,
            success=success,
            input_data=input_data,
            output_data=output_data,
            process_time_ms=process_time_ms,
            error=error,
            persist=True,
        )
        
        # 清理单个策略的历史记录
        max_count = getattr(self._metadata, "max_history_count", 100)
        if max_count > 0:
            store.cleanup(strategy_id=self.id, max_count=max_count)
        
        # 清理总历史记录
        total_max_count = get_strategy_total_history_count()
        if total_max_count > 0:
            store.cleanup_total(max_count=total_max_count)
    
    def get_recent_results(self, limit: int = 10) -> List[dict]:
        """获取最近执行结果"""
        from .result_store import get_result_store
        store = get_result_store()
        results = store.get_recent(self.id, limit=limit)
        return [r.to_dict() for r in results]
    
    def get_result_stats(self) -> dict:
        """获取执行统计"""
        from .result_store import get_result_store
        store = get_result_store()
        return store.get_stats(self.id)
    
    def get_result_trend(self, interval_minutes: int = 5, limit: int = 20) -> dict:
        """获取执行趋势"""
        from .result_store import get_result_store
        store = get_result_store()
        return store.get_trend_data(self.id, interval_minutes=interval_minutes, limit=limit)
    
    def bind_datasource(self, datasource_id: str):
        self._metadata.bound_datasource_id = datasource_id
        self.save()
        
        from ..datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        ds = ds_mgr.get(datasource_id)
        
        if ds is not None:
            self._bind_datasource(ds)
    
    def update_config(
        self,
        name: str = None,
        description: str = None,
        func_code: str = None,
        bound_datasource_id: str = None,
        bound_datasource_ids: List[str] = None,
        compute_mode: str = None,
        window_size: int = None,
        window_type: str = None,
        window_interval: str = None,
        window_return_partial: bool = None,
        max_history_count: int = None,
        dictionary_profile_ids: List[str] = None,
        category: str = None,
    ) -> dict:
        # 记录是否正在运行
        was_running = self.is_running

        if name is not None:
            self._metadata.name = name
        if description is not None:
            self._metadata.description = description
        if compute_mode is not None:
            self._metadata.compute_mode = compute_mode
        if window_size is not None:
            self._metadata.window_size = max(1, int(window_size))
        if window_type is not None:
            self._metadata.window_type = window_type
        if window_interval is not None:
            self._metadata.window_interval = window_interval
        if window_return_partial is not None:
            self._metadata.window_return_partial = window_return_partial
        if max_history_count is not None:
            self._metadata.max_history_count = max(1, int(max_history_count))
        if dictionary_profile_ids is not None:
            self._metadata.dictionary_profile_ids = dictionary_profile_ids
        if category is not None:
            self._metadata.category = category

        # 处理多数据源绑定
        if bound_datasource_ids is not None:
            self._metadata.bound_datasource_ids = bound_datasource_ids
            # 同步更新单数据源字段（取第一个）
            self._metadata.bound_datasource_id = bound_datasource_ids[0] if bound_datasource_ids else ""
        elif bound_datasource_id is not None:
            self._metadata.bound_datasource_id = bound_datasource_id
            # 同步更新多数据源列表
            if bound_datasource_id:
                if bound_datasource_id not in self._metadata.bound_datasource_ids:
                    self._metadata.bound_datasource_ids = [bound_datasource_id]
            else:
                self._metadata.bound_datasource_ids = []
        
        if func_code is not None:
            if self._get_func_name() not in func_code:
                return {"success": False, "error": f"代码必须包含 {self._get_func_name()} 函数"}
            
            self._func_code = func_code
            self._compiled_func = None
            
            result = self.compile_code()
            if not result["success"]:
                return result
        
        # 重置窗口状态（配置变更后需要重新开始）
        self._window_buffer = []
        self._last_window_trigger = 0
        
        self.save()
        
        # 如果之前在运行，重启以应用新配置
        if was_running:
            self.stop()
            start_result = self.start()
            if not start_result.get("success"):
                return {"success": False, "error": f"重启失败: {start_result.get('error')}"}
        
        return {"success": True, "was_running": was_running, "restarted": was_running}
    
    def save(self) -> dict:
        try:
            db = NB(STRATEGY_TABLE)
            db[self.id] = self.to_dict()
            return {"success": True, "id": self.id}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def to_dict(self) -> dict:
        # 优化：直接访问属性，避免使用getattr
        metadata = self._metadata
        return {
            "metadata": {
                "id": metadata.id,
                "name": metadata.name,
                "description": metadata.description,
                "tags": metadata.tags,
                "bound_datasource_id": getattr(metadata, "bound_datasource_id", ""),
                "bound_datasource_ids": getattr(metadata, "bound_datasource_ids", []),  # 多数据源支持
                "compute_mode": getattr(metadata, "compute_mode", "record"),
                "window_size": getattr(metadata, "window_size", 5),
                "window_type": getattr(metadata, "window_type", "sliding"),
                "window_interval": getattr(metadata, "window_interval", "10s"),
                "window_return_partial": getattr(metadata, "window_return_partial", False),
                "dictionary_profile_ids": getattr(metadata, "dictionary_profile_ids", []),
                "max_history_count": getattr(metadata, "max_history_count", 100),
                "diagram_info": getattr(metadata, "diagram_info", {}),
                "category": getattr(metadata, "category", "默认"),
                "created_at": metadata.created_at,
                "updated_at": metadata.updated_at,
            },
            "state": self._state.to_dict(),
            "func_code": self._func_code,
            "was_running": self._was_running,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "StrategyEntry":
        metadata_data = data.get("metadata", {})
        metadata = StrategyMetadata(
            id=metadata_data.get("id", ""),
            name=metadata_data.get("name", "unnamed"),
            description=metadata_data.get("description", ""),
            tags=metadata_data.get("tags", []),
            bound_datasource_id=metadata_data.get("bound_datasource_id", ""),
            bound_datasource_ids=metadata_data.get("bound_datasource_ids", []),  # 多数据源支持
            compute_mode=metadata_data.get("compute_mode", "record"),
            window_size=metadata_data.get("window_size", 5),
            window_type=metadata_data.get("window_type", "sliding"),
            window_interval=metadata_data.get("window_interval", "10s"),
            window_return_partial=metadata_data.get("window_return_partial", False),
            dictionary_profile_ids=metadata_data.get("dictionary_profile_ids", []),
            max_history_count=metadata_data.get("max_history_count", 100),
            diagram_info=metadata_data.get("diagram_info", {}),
            category=metadata_data.get("category", "默认"),
            created_at=metadata_data.get("created_at", time.time()),
            updated_at=metadata_data.get("updated_at", time.time()),
        )
        
        state_data = data.get("state", {})
        state = StrategyState.from_dict(state_data)
        
        entry = cls(metadata=metadata, state=state)
        
        func_code = data.get("func_code", "")
        if func_code:
            entry._func_code = func_code
            try:
                entry.compile_code()
            except Exception:
                pass
        
        entry._was_running = data.get("was_running", False)
        entry._state.status = UnitStatus.STOPPED.value
        
        return entry


class StrategyManager:
    """策略管理器"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._items: Dict[str, StrategyEntry] = {}
        self._items_lock = threading.Lock()
        self._experiment_lock = threading.Lock()
        self._experiment_session: Optional[Dict[str, Any]] = None
        self._initialized = True

    def _normalize_categories(self, categories: List[str]) -> List[str]:
        normalized: List[str] = []
        for cat in categories or []:
            cat_name = str(cat or "").strip()
            if not cat_name:
                continue
            if cat_name not in normalized:
                normalized.append(cat_name)
        return normalized

    def _list_by_categories(self, categories: List[str]) -> List[StrategyEntry]:
        category_set = set(self._normalize_categories(categories))
        if not category_set:
            return []
        return [
            entry for entry in self.list_all()
            if str(getattr(entry._metadata, "category", "默认") or "默认") in category_set
        ]

    def _save_experiment_session(self):
        try:
            db = NB(STRATEGY_EXPERIMENT_TABLE)
            if self._experiment_session is None:
                if STRATEGY_EXPERIMENT_ACTIVE_KEY in db:
                    del db[STRATEGY_EXPERIMENT_ACTIVE_KEY]
                return
            db[STRATEGY_EXPERIMENT_ACTIVE_KEY] = self._experiment_session
        except Exception as e:
            self._log("ERROR", "Save experiment session failed", error=str(e))

    def _load_experiment_session(self):
        try:
            db = NB(STRATEGY_EXPERIMENT_TABLE)
            data = db.get(STRATEGY_EXPERIMENT_ACTIVE_KEY)
            if not isinstance(data, dict):
                self._experiment_session = None
                return

            snapshot = data.get("snapshot", {}) or {}
            normalized_snapshot = {}
            for entry_id, snap in snapshot.items():
                if entry_id not in self._items:
                    continue
                if not isinstance(snap, dict):
                    continue
                normalized_snapshot[entry_id] = {
                    "entry_id": entry_id,
                    "name": snap.get("name", self._items[entry_id].name),
                    "category": snap.get("category", getattr(self._items[entry_id]._metadata, "category", "默认")),
                    "pre_experiment_bound_datasource_id": snap.get(
                        "pre_experiment_bound_datasource_id",
                        snap.get("bound_datasource_id", ""),
                    ) or "",
                    "pre_experiment_was_running": bool(
                        snap.get("pre_experiment_was_running", snap.get("was_running", False))
                    ),
                    # 兼容旧字段
                    "bound_datasource_id": snap.get("bound_datasource_id", "") or "",
                    "was_running": bool(snap.get("was_running", False)),
                }

            if not normalized_snapshot:
                self._experiment_session = None
                if STRATEGY_EXPERIMENT_ACTIVE_KEY in db:
                    del db[STRATEGY_EXPERIMENT_ACTIVE_KEY]
                return

            self._experiment_session = {
                "active": bool(data.get("active", True)),
                "started_at": float(data.get("started_at", time.time())),
                "datasource_id": str(data.get("datasource_id", "") or ""),
                "datasource_name": str(data.get("datasource_name", "") or ""),
                "categories": self._normalize_categories(data.get("categories", [])),
                "target_count": int(data.get("target_count", len(normalized_snapshot))),
                "snapshot": normalized_snapshot,
            }
            self._save_experiment_session()
        except Exception as e:
            self._experiment_session = None
            self._log("ERROR", "Load experiment session failed", error=str(e))
    
    def create(
        self,
        name: str,
        func_code: str,
        bound_datasource_id: str = "",
        bound_datasource_ids: List[str] = None,
        description: str = "",
        compute_mode: str = "record",
        window_size: int = None,
        window_type: str = "sliding",
        window_interval: str = None,
        window_return_partial: bool = False,
        max_history_count: int = None,
        dictionary_profile_ids: List[str] = None,
        tags: List[str] = None,
        category: str = "默认",
    ) -> dict:
        from ..config import get_strategy_config

        import hashlib
        entry_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]

        # 使用配置默认值
        strategy_config = get_strategy_config()
        if window_size is None:
            window_size = strategy_config.get("default_window_size", 5)
        if max_history_count is None:
            max_history_count = strategy_config.get("single_history_count", 30)
        if window_interval is None:
            window_interval = strategy_config.get("default_window_interval", "10s")

        if "process" not in func_code:
            return {"success": False, "error": "代码必须包含 process 函数"}

        # 处理多数据源绑定
        if bound_datasource_ids is None:
            bound_datasource_ids = [bound_datasource_id] if bound_datasource_id else []
        elif bound_datasource_id and bound_datasource_id not in bound_datasource_ids:
            # 如果提供了单数据源但不在列表中，添加到列表
            bound_datasource_ids = [bound_datasource_id] + list(bound_datasource_ids)

        metadata = StrategyMetadata(
            id=entry_id,
            name=name,
            description=description,
            tags=tags or [],
            bound_datasource_id=bound_datasource_ids[0] if bound_datasource_ids else "",  # 兼容单数据源
            bound_datasource_ids=bound_datasource_ids,
            compute_mode=compute_mode,
            window_size=window_size,
            window_type=window_type,
            window_interval=window_interval,
            window_return_partial=window_return_partial,
            dictionary_profile_ids=dictionary_profile_ids or [],
            max_history_count=max_history_count,
            category=category or "默认",
        )
        
        entry = StrategyEntry(metadata=metadata)
        entry._func_code = func_code
        
        result = entry.compile_code()
        if not result["success"]:
            return {"success": False, "error": f"编译失败: {result['error']}"}
        
        with self._items_lock:
            if any(e.name == name for e in self._items.values()):
                return {"success": False, "error": f"策略名称已存在: {name}"}
            self._items[entry_id] = entry
        
        entry.save()
        
        self._log("INFO", "Strategy created", id=entry_id, name=name)
        return {"success": True, "id": entry_id, "entry": entry.to_dict()}
    
    def get(self, entry_id: str) -> Optional[StrategyEntry]:
        return self._items.get(entry_id)
    
    def get_by_name(self, name: str) -> Optional[StrategyEntry]:
        for entry in self._items.values():
            if entry.name == name:
                return entry
        return None
    
    def list_all(self) -> List[StrategyEntry]:
        return list(self._items.values())
    
    def list_all_dict(self) -> List[dict]:
        return [entry.to_dict() for entry in self._items.values()]
    
    def delete(self, entry_id: str) -> dict:
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}
        
        entry.stop()
        
        with self._items_lock:
            self._items.pop(entry_id, None)
        
        db = NB(STRATEGY_TABLE)
        if entry_id in db:
            del db[entry_id]
        
        self._log("INFO", "Strategy deleted", id=entry_id, name=entry.name)
        return {"success": True}
    
    def start(self, entry_id: str) -> dict:
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}
        return entry.start()
    
    def stop(self, entry_id: str) -> dict:
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}
        return entry.stop()

    def get_experiment_info(self) -> dict:
        with self._experiment_lock:
            session = self._experiment_session
            if not session:
                return {"active": False}
            info = dict(session)
            info.pop("snapshot", None)
            return info

    def start_experiment(self, categories: List[str], datasource_id: str) -> dict:
        normalized_categories = self._normalize_categories(categories)
        datasource_id = str(datasource_id or "").strip()

        if not normalized_categories:
            return {"success": False, "error": "请至少选择一个策略类别"}
        if not datasource_id:
            return {"success": False, "error": "请先选择实验数据源"}

        with self._experiment_lock:
            if self._experiment_session is not None:
                return {"success": False, "error": "实验模式已开启，请先关闭"}

            from ..datasource import get_datasource_manager
            ds_mgr = get_datasource_manager()
            ds_entry = ds_mgr.get(datasource_id)
            if ds_entry is None:
                return {"success": False, "error": "实验数据源不存在"}

            # 开启实验时确保实验数据源处于运行中（如“回放行情”）
            datasource_started = False
            datasource_start_error = ""
            if not ds_entry.is_running:
                ds_start_result = ds_entry.start()
                if not ds_start_result.get("success"):
                    datasource_start_error = ds_start_result.get("error", "unknown error")
                    return {"success": False, "error": f"实验数据源启动失败: {datasource_start_error}"}
                datasource_started = True

            target_entries = self._list_by_categories(normalized_categories)
            if not target_entries:
                return {"success": False, "error": "所选类别下没有策略"}

            snapshot: Dict[str, Dict[str, Any]] = {}
            failed_switch = []
            started = 0
            failed_start = []

            for entry in target_entries:
                snapshot[entry.id] = {
                    "entry_id": entry.id,
                    "name": entry.name,
                    "category": getattr(entry._metadata, "category", "默认") or "默认",
                    # 实验前快照（关闭实验时用于恢复）
                    "pre_experiment_bound_datasource_id": getattr(entry._metadata, "bound_datasource_id", "") or "",
                    "pre_experiment_was_running": bool(entry.is_running),
                    # 兼容旧字段
                    "bound_datasource_id": getattr(entry._metadata, "bound_datasource_id", "") or "",
                    "was_running": bool(entry.is_running),
                }

                switch_result = entry.update_config(bound_datasource_id=datasource_id)
                if not switch_result.get("success"):
                    failed_switch.append({
                        "entry_id": entry.id,
                        "name": entry.name,
                        "error": switch_result.get("error", "unknown error"),
                    })
                    continue

                if not entry.is_running:
                    start_result = entry.start()
                    if start_result.get("success"):
                        started += 1
                    else:
                        failed_start.append({
                            "entry_id": entry.id,
                            "name": entry.name,
                            "error": start_result.get("error", "unknown error"),
                        })

            switched_ok = len(target_entries) - len(failed_switch)
            if switched_ok <= 0:
                return {
                    "success": False,
                    "error": "未能切换任何策略到实验数据源",
                    "categories": normalized_categories,
                    "target_count": len(target_entries),
                    "failed_switch": failed_switch,
                    "failed_start": failed_start,
                }

            self._experiment_session = {
                "active": True,
                "started_at": time.time(),
                "datasource_id": datasource_id,
                "datasource_name": ds_entry.name,
                "categories": normalized_categories,
                "target_count": len(target_entries),
                "snapshot": snapshot,
            }
            self._save_experiment_session()

            return {
                "success": True,
                "active": True,
                "datasource_id": datasource_id,
                "datasource_name": ds_entry.name,
                "categories": normalized_categories,
                "target_count": len(target_entries),
                "switched_count": switched_ok,
                "started_count": started,
                "datasource_started": datasource_started,
                "failed_switch": failed_switch,
                "failed_start": failed_start,
            }

    def stop_experiment(self) -> dict:
        with self._experiment_lock:
            session = self._experiment_session
            if not session:
                return {"success": False, "error": "实验模式未开启"}

            snapshot = session.get("snapshot", {}) or {}
            restored_bind = 0
            restored_run = 0
            failed = []

            for entry_id, snap in snapshot.items():
                entry = self.get(entry_id)
                if entry is None:
                    failed.append({
                        "entry_id": entry_id,
                        "name": snap.get("name", ""),
                        "error": "策略不存在",
                    })
                    continue

                prev_ds_id = snap.get(
                    "pre_experiment_bound_datasource_id",
                    snap.get("bound_datasource_id", ""),
                ) or ""
                prev_running = bool(
                    snap.get("pre_experiment_was_running", snap.get("was_running", False))
                )

                bind_result = entry.update_config(bound_datasource_id=prev_ds_id)
                if not bind_result.get("success"):
                    failed.append({
                        "entry_id": entry.id,
                        "name": entry.name,
                        "error": f"恢复数据源失败: {bind_result.get('error', 'unknown error')}",
                    })
                    continue
                restored_bind += 1

                state_result = {"success": True}
                if prev_running and not entry.is_running:
                    state_result = entry.start()
                elif not prev_running and entry.is_running:
                    state_result = entry.stop()

                if state_result.get("success"):
                    restored_run += 1
                else:
                    failed.append({
                        "entry_id": entry.id,
                        "name": entry.name,
                        "error": f"恢复运行状态失败: {state_result.get('error', 'unknown error')}",
                    })

            if not failed:
                self._experiment_session = None
                self._save_experiment_session()
                return {
                    "success": True,
                    "active": False,
                    "restored_bind_count": restored_bind,
                    "restored_state_count": restored_run,
                    "failed": failed,
                }

            return {
                "success": False,
                "active": True,
                "error": "部分策略恢复失败，请修复后重试关闭实验模式",
                "restored_bind_count": restored_bind,
                "restored_state_count": restored_run,
                "failed": failed,
            }
    
    def load_from_db(self) -> int:
        db = NB(STRATEGY_TABLE)
        count = 0
        
        with self._items_lock:
            self._items.clear()
            
            for entry_id, data in list(db.items()):
                if not isinstance(data, dict):
                    continue
                
                try:
                    entry = StrategyEntry.from_dict(data)
                    if not entry.id:
                        continue
                    
                    self._items[entry.id] = entry
                    count += 1
                    
                except Exception as e:
                    self._log("ERROR", "Load entry failed", id=entry_id, error=str(e))

        with self._experiment_lock:
            self._load_experiment_session()
        
        self._log("INFO", "Load from db finished", count=count)
        return count
    
    def reload_entry(self, entry_id: str) -> dict:
        """热重载单个策略（从数据库重新加载配置和代码）
        
        Args:
            entry_id: 策略ID
            
        Returns:
            重载结果
        """
        db = NB(STRATEGY_TABLE)
        data = db.get(entry_id)
        
        if not data or not isinstance(data, dict):
            return {"success": False, "error": "策略不存在"}
        
        try:
            # 获取当前运行状态
            current_entry = self._items.get(entry_id)
            was_running = current_entry and current_entry.is_running
            
            # 先停止旧的策略
            if current_entry and current_entry.is_running:
                current_entry.stop()
                self._log("INFO", "Stopped old strategy before reload", id=entry_id)
            
            # 从数据库加载新数据
            new_entry = StrategyEntry.from_dict(data)
            
            with self._items_lock:
                self._items[entry_id] = new_entry
            
            # 如果之前在运行，重新启动
            if was_running:
                new_entry.start()
            
            self._log("INFO", "Strategy reloaded", id=entry_id, name=new_entry.name, was_running=was_running)
            return {
                "success": True, 
                "entry": new_entry.to_dict(),
                "was_running": was_running,
                "restarted": was_running,
            }
            
        except Exception as e:
            self._log("ERROR", "Reload entry failed", id=entry_id, error=str(e))
            return {"success": False, "error": str(e)}
    
    def reload_all(self) -> dict:
        """热重载所有策略（从数据库重新加载）
        
        Returns:
            重载结果统计
        """
        db = NB(STRATEGY_TABLE)
        reloaded = 0
        failed = 0
        results = []
        
        for entry_id, data in list(db.items()):
            if not isinstance(data, dict):
                continue
            
            result = self.reload_entry(entry_id)
            if result.get("success"):
                reloaded += 1
            else:
                failed += 1
            results.append({"id": entry_id, "result": result})
        
        self._log("INFO", "Reload all finished", reloaded=reloaded, failed=failed)
        return {
            "success": True,
            "reloaded": reloaded,
            "failed": failed,
            "results": results,
        }
    
    def restore_running_states(self) -> dict:
        restored_count = 0
        failed_count = 0
        results = []
        
        with self._items_lock:
            entries_to_check = list(self._items.values())
        
        for entry in entries_to_check:
            try:
                prep = entry.prepare_for_recovery()
                
                if not prep.get("can_recover"):
                    results.append({
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": False,
                        "reason": prep.get("reason"),
                    })
                    continue
                
                result = entry.start()
                
                if result.get("success"):
                    restored_count += 1
                    results.append({
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": True,
                    })
                else:
                    failed_count += 1
                    results.append({
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": False,
                        "error": result.get("error"),
                    })
                    
            except Exception as e:
                failed_count += 1
                results.append({
                    "entry_id": entry.id,
                    "entry_name": entry.name,
                    "success": False,
                    "error": str(e),
                })
        
        self._log("INFO", "Restore finished", restored=restored_count, failed=failed_count)
        
        return {
            "success": True,
            "restored_count": restored_count,
            "failed_count": failed_count,
            "results": results,
        }
    
    def get_all_recovery_info(self) -> List[dict]:
        info = []
        for entry in self._items.values():
            prep = entry.prepare_for_recovery()
            info.append({
                "id": entry.id,
                "name": entry.name,
                "was_running": entry.was_running,
                "can_recover": prep.get("can_recover"),
                "reason": prep.get("reason"),
            })
        return info
    
    def get_stats(self) -> dict:
        entries = self.list_all()
        running = sum(1 for e in entries if e.is_running)
        
        total_processed = sum(e._state.processed_count for e in entries)
        total_output = sum(e._state.output_count for e in entries)
        
        return {
            "total": len(entries),
            "running": running,
            "stopped": len(entries) - running,
            "total_processed": total_processed,
            "total_output": total_output,
        }
    
    def _log(self, level: str, message: str, **extra):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
        print(f"[{ts}][StrategyManager][{level}] {message} | {extra_str}")


_strategy_manager: Optional[StrategyManager] = None
_strategy_manager_lock = threading.Lock()


def get_strategy_manager() -> StrategyManager:
    global _strategy_manager
    if _strategy_manager is None:
        with _strategy_manager_lock:
            if _strategy_manager is None:
                _strategy_manager = StrategyManager()
    return _strategy_manager
