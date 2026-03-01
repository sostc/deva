"""Strategy V2 - 基于 RecoverableUnit 抽象

统一状态保存恢复与执行函数恢复的策略实现。
"""

from __future__ import annotations

import threading
import time
import traceback
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


STRATEGY_TABLE = "strategies_v2"
STRATEGY_RESULTS_TABLE = "strategy_v2_results"


@dataclass
class StrategyMetadata(UnitMetadata):
    """策略元数据"""
    bound_datasource_id: str = ""
    compute_mode: str = "record"
    window_size: int = 5
    window_type: str = "sliding"
    window_interval: str = "10s"
    dictionary_profile_ids: List[str] = field(default_factory=list)


@dataclass
class StrategyState(UnitState):
    """策略状态"""
    processed_count: int = 0
    last_process_ts: float = 0
    output_count: int = 0


class StrategyEntry(RecoverableUnit):
    """策略条目
    
    基于 RecoverableUnit 抽象的策略实现。
    支持：
    - 绑定数据源，处理数据流
    - 数据补齐（字典数据）
    - 状态持久化与恢复
    """
    
    _instances: Dict[str, "StrategyEntry"] = {}
    _instances_lock = threading.Lock()
    
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
        self._output_stream: Optional[Any] = None
        self._processing_lock = threading.Lock()
        self._window_buffer: List[Any] = []
    
    def _get_func_name(self) -> str:
        return "process"
    
    def _do_compile(self, code: str) -> Callable:
        env = self._build_execution_env()
        local_vars: Dict[str, Any] = {}
        exec(code, env, local_vars)
        
        func = local_vars.get(self._get_func_name())
        if not func or not callable(func):
            raise ValueError(f"函数 '{self._get_func_name()}' 未在代码中定义")
        
        return func
    
    def _do_start(self, func: Callable) -> dict:
        try:
            datasource_id = getattr(self._metadata, "bound_datasource_id", "")
            if not datasource_id:
                return {"success": True, "message": "No datasource bound"}
            
            from ..datasource.datasource_v2 import get_datasource_manager
            ds_mgr = get_datasource_manager()
            ds = ds_mgr.get(datasource_id)
            
            if ds is None:
                return {"success": True, "message": "Datasource not found, will bind later"}
            
            self._bind_datasource(ds)
            
            return {"success": True}
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
            self._input_stream = datasource.get_stream()
            
            if self._input_stream is None:
                return
            
            output_stream_name = f"strategy_output_{self.id}"
            self._output_stream = NS(
                output_stream_name,
                cache_max_len=10,
                cache_max_age_seconds=3600,
                description=f"Strategy {self.name} output",
            )
            
            def on_data(data: Any):
                self._process_data(data)
            
            if hasattr(self._input_stream, "subscribe"):
                self._input_stream.subscribe(on_data)
            elif hasattr(self._input_stream, "map"):
                self._input_stream.map(on_data)
                
        except Exception as e:
            self._log("ERROR", "Bind datasource failed", error=str(e))
    
    def _process_data(self, data: Any):
        """处理数据"""
        if not self.is_running:
            return
        
        if self._compiled_func is None:
            return
        
        with self._processing_lock:
            try:
                data = self._enrich_data(data)
                
                compute_mode = getattr(self._metadata, "compute_mode", "record")
                
                if compute_mode == "window":
                    result = self._process_window(data)
                else:
                    result = self._process_record(data)
                
                if result is not None:
                    self._emit_result(result)
                    self._state.output_count += 1
                
                self._state.processed_count += 1
                self._state.last_process_ts = time.time()
                
            except Exception as e:
                self._state.record_error(str(e))
                self._log("ERROR", "Process data failed", error=str(e))
    
    def _process_record(self, data: Any) -> Any:
        """单条处理"""
        return self._compiled_func(data)
    
    def _process_window(self, data: Any) -> Any:
        """窗口处理"""
        window_size = getattr(self._metadata, "window_size", 5)
        
        self._window_buffer.append(data)
        
        if len(self._window_buffer) > window_size:
            self._window_buffer = self._window_buffer[-window_size:]
        
        if len(self._window_buffer) < window_size:
            return None
        
        return self._compiled_func(list(self._window_buffer))
    
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
            from ..dictionary.dictionary_v2 import get_dictionary_manager
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
        """推断 join 键"""
        common_cols = set(left_df.columns).intersection(set(right_df.columns))
        for key in ("code", "ts_code", "symbol", "name"):
            if key in common_cols:
                return key
        return None
    
    def _emit_result(self, result: Any):
        """发送结果"""
        if self._output_stream is None:
            return
        
        try:
            if hasattr(self._output_stream, "emit"):
                self._output_stream.emit(result)
            
            self._save_result(result)
            
        except Exception as e:
            self._log("ERROR", "Emit result failed", error=str(e))
    
    def _save_result(self, result: Any):
        """保存结果"""
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
    
    def bind_datasource(self, datasource_id: str, datasource_name: str = ""):
        """绑定数据源"""
        self._metadata.bound_datasource_id = datasource_id
        self.save()
        
        from ..datasource.datasource_v2 import get_datasource_manager
        ds_mgr = get_datasource_manager()
        ds = ds_mgr.get(datasource_id)
        
        if ds is not None:
            self._bind_datasource(ds)
    
    def unbind_datasource(self):
        """解绑数据源"""
        self._metadata.bound_datasource_id = ""
        self._input_stream = None
        self.save()
    
    def update_config(
        self,
        name: str = None,
        description: str = None,
        func_code: str = None,
        bound_datasource_id: str = None,
        compute_mode: str = None,
        window_size: int = None,
        dictionary_profile_ids: List[str] = None,
    ) -> dict:
        """更新配置"""
        if name is not None:
            self._metadata.name = name
        if description is not None:
            self._metadata.description = description
        if compute_mode is not None:
            self._metadata.compute_mode = compute_mode
        if window_size is not None:
            self._metadata.window_size = max(1, int(window_size))
        if dictionary_profile_ids is not None:
            self._metadata.dictionary_profile_ids = dictionary_profile_ids
        
        if bound_datasource_id is not None:
            self._metadata.bound_datasource_id = bound_datasource_id
        
        if func_code is not None:
            if self._get_func_name() not in func_code:
                return {"success": False, "error": f"代码必须包含 {self._get_func_name()} 函数"}
            
            self._func_code = func_code
            self._compiled_func = None
            
            result = self.compile_code()
            if not result["success"]:
                return result
        
        self.save()
        return {"success": True}
    
    def save(self) -> dict:
        try:
            db = NB(STRATEGY_TABLE)
            db[self.id] = self.to_dict()
            return {"success": True, "id": self.id}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def to_dict(self) -> dict:
        return {
            "metadata": {
                "id": self._metadata.id,
                "name": self._metadata.name,
                "description": self._metadata.description,
                "tags": self._metadata.tags,
                "bound_datasource_id": getattr(self._metadata, "bound_datasource_id", ""),
                "compute_mode": getattr(self._metadata, "compute_mode", "record"),
                "window_size": getattr(self._metadata, "window_size", 5),
                "window_type": getattr(self._metadata, "window_type", "sliding"),
                "window_interval": getattr(self._metadata, "window_interval", "10s"),
                "dictionary_profile_ids": getattr(self._metadata, "dictionary_profile_ids", []),
                "created_at": self._metadata.created_at,
                "updated_at": self._metadata.updated_at,
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
            compute_mode=metadata_data.get("compute_mode", "record"),
            window_size=metadata_data.get("window_size", 5),
            window_type=metadata_data.get("window_type", "sliding"),
            window_interval=metadata_data.get("window_interval", "10s"),
            dictionary_profile_ids=metadata_data.get("dictionary_profile_ids", []),
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
        
        saved_status = state_data.get("status", UnitStatus.STOPPED.value)
        entry._was_running = (saved_status == UnitStatus.RUNNING.value)
        entry._state.status = UnitStatus.STOPPED.value
        
        return entry


class StrategyManager:
    """策略管理器 V2
    
    继承统一管理器设计模式。
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
        if hasattr(self, "_initialized"):
            return
        self._items: Dict[str, StrategyEntry] = {}
        self._items_lock = threading.Lock()
        self._initialized = True
    
    def create(
        self,
        name: str,
        func_code: str,
        bound_datasource_id: str = "",
        description: str = "",
        compute_mode: str = "record",
        window_size: int = 5,
        dictionary_profile_ids: List[str] = None,
        tags: List[str] = None,
    ) -> dict:
        import hashlib
        entry_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]
        
        if "process" not in func_code:
            return {"success": False, "error": "代码必须包含 process 函数"}
        
        metadata = StrategyMetadata(
            id=entry_id,
            name=name,
            description=description,
            tags=tags or [],
            bound_datasource_id=bound_datasource_id,
            compute_mode=compute_mode,
            window_size=window_size,
            dictionary_profile_ids=dictionary_profile_ids or [],
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
        
        self._log("INFO", "Load from db finished", count=count)
        return count
    
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
                        "error": prep.get("error"),
                    })
                    continue
                
                result = entry.start()
                
                if result.get("success"):
                    restored_count += 1
                    results.append({
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": True,
                        "reason": prep.get("reason"),
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
        
        self._log(
            "INFO",
            "Restore running states finished",
            restored=restored_count,
            failed=failed_count,
        )
        
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
                "compile_error": entry.compile_error,
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
