"""策略生命周期管理器(Strategy Manager)

提供策略的统一管理、监控和协调功能。

================================================================================
架构设计
================================================================================

【管理器职责】
┌─────────────────────────────────────────────────────────────────────────────┐
│  StrategyManager                                                            │
│  ├── 策略注册表: 管理所有策略实例                                             │
│  ├── 生命周期控制: start/pause/resume/archive/delete                        │
│  ├── 热更新支持: 动态替换处理器函数                                           │
│  ├── 影响分析: 删除前分析下游影响                                             │
│  ├── 错误聚合: 收集所有策略的错误信息                                         │
│  └── 监控统计: 提供运行状态和性能指标                                         │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional
import traceback

from deva import Stream, NS, NB, log

from .base import BaseManager
from .strategy_unit import (
    StrategyUnit,
    StrategyStatus,
    OutputType,
    DownstreamSink,
    UpstreamSource,
)
from .result_store import get_result_store


@dataclass
class ManagerStats:
    total_units: int = 0
    running_count: int = 0
    paused_count: int = 0
    draft_count: int = 0
    archived_count: int = 0
    total_processed: int = 0
    total_errors: int = 0
    
    def to_dict(self) -> dict:
        return {
            "total_units": self.total_units,
            "running_count": self.running_count,
            "paused_count": self.paused_count,
            "draft_count": self.draft_count,
            "archived_count": self.archived_count,
            "total_processed": self.total_processed,
            "total_errors": self.total_errors,
        }


@dataclass
class ErrorRecord:
    strategy_id: str
    strategy_name: str
    error: str
    traceback: str
    data_preview: str
    ts: float
    
    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "error": self.error,
            "traceback": self.traceback,
            "data_preview": self.data_preview,
            "ts": self.ts,
            "ts_readable": datetime.fromtimestamp(self.ts).isoformat(),
        }


class StrategyManager(BaseManager[StrategyUnit]):
    """策略生命周期管理器
    
    提供策略的统一管理、监控和协调功能。
    """
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        super().__init__()
        
        self._error_stream: Optional[Stream] = None
        self._errors: List[ErrorRecord] = []
        self._errors_lock = threading.Lock()
        self._max_errors = 100
        
        self._stats = ManagerStats()
        
        self._initialized = True
    
    def _get_item_id(self, item: StrategyUnit) -> str:
        return item.id
    
    def _get_item_name(self, item: StrategyUnit) -> str:
        return item.name
    
    def _is_running(self, item: StrategyUnit) -> bool:
        return item.state.status == StrategyStatus.RUNNING.value
    
    def _has_error(self, item: StrategyUnit) -> bool:
        return item.state.error_count > 0
    
    def _on_registered(self, item: StrategyUnit):
        item.set_error_stream(self._get_or_create_error_stream())
        self._update_stats()
    
    def _on_unregistered(self, item: StrategyUnit):
        self._update_stats()
    
    def set_error_stream(self, stream: Stream):
        self._error_stream = stream
    
    def get_unit(self, unit_id: str) -> Optional[StrategyUnit]:
        return self.get(unit_id)
    
    def get_unit_by_name(self, name: str) -> Optional[StrategyUnit]:
        return self.get_by_name(name)
    
    def list_units(self, status: StrategyStatus = None) -> List[StrategyUnit]:
        units = list(self._items.values())
        if status:
            units = [u for u in units if u.status == status]
        return units
    
    def list_all(self) -> List[dict]:
        return [unit.to_dict() for unit in self._items.values()]
    
    def start(self, unit_id: str) -> dict:
        unit = self.get_unit(unit_id)
        if not unit:
            return {"success": False, "error": "Strategy not found"}
        
        result = unit.start()
        if result.get("success"):
            self._update_stats()
        
        return result
    
    def pause(self, unit_id: str) -> dict:
        unit = self.get_unit(unit_id)
        if not unit:
            return {"success": False, "error": "Strategy not found"}
        
        result = unit.pause()
        if result.get("success"):
            self._update_stats()
        
        return result
    
    def resume(self, unit_id: str) -> dict:
        unit = self.get_unit(unit_id)
        if not unit:
            return {"success": False, "error": "Strategy not found"}
        
        result = unit.resume()
        if result.get("success"):
            self._update_stats()
        
        return result
    
    def archive(self, unit_id: str) -> dict:
        unit = self.get_unit(unit_id)
        if not unit:
            return {"success": False, "error": "Strategy not found"}
        
        result = unit.archive()
        if result.get("success"):
            self._update_stats()
        
        return result
    
    def delete(self, unit_id: str, force: bool = False) -> dict:
        unit = self.get_unit(unit_id)
        if not unit:
            return {"success": False, "error": "Strategy not found"}
        
        impact = unit._analyze_downstream_impact()
        
        if impact.get("exclusive_sinks") and not force:
            return {
                "success": False,
                "error": "Strategy has exclusive downstream sinks",
                "impact": impact,
                "hint": "Use force=True to delete anyway",
            }
        
        result = unit.delete()
        if result.get("success"):
            with self._items_lock:
                self._items.pop(unit_id, None)
            self._update_stats()
        
        return result
    
    def hot_update(
        self,
        unit_id: str,
        func: Callable = None,
        code: str = None,
        ai_doc: str = None,
        validate: bool = True,
    ) -> dict:
        unit = self.get_unit(unit_id)
        if not unit:
            return {"success": False, "error": "Strategy not found"}
        
        if validate:
            validation_result = self._validate_code(func, code)
            if not validation_result.get("valid"):
                return {
                    "success": False,
                    "error": "Code validation failed",
                    "details": validation_result,
                }
        
        try:
            unit.update_logic(func=func, code=code, ai_doc=ai_doc)
            return {
                "success": True,
                "unit_id": unit_id,
                "code_version": unit._code_version,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
    
    def _validate_code(self, func: Callable = None, code: str = None) -> dict:
        if func is not None:
            if not callable(func):
                return {"valid": False, "error": "func must be callable"}
            return {"valid": True}
        
        if code:
            try:
                local_ns = {"__builtins__": __builtins__}
                exec(code, local_ns, local_ns)
                
                if "process" not in local_ns:
                    return {"valid": False, "error": "No 'process' function found in code"}
                
                if not callable(local_ns["process"]):
                    return {"valid": False, "error": "'process' must be a callable function"}
                
                return {"valid": True}
            except Exception as e:
                return {
                    "valid": False,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
        
        return {"valid": False, "error": "Either func or code must be provided"}
    
    def analyze_deletion_impact(self, unit_id: str) -> dict:
        unit = self.get_unit(unit_id)
        if not unit:
            return {"success": False, "error": "Strategy not found"}
        
        impact = unit._analyze_downstream_impact()
        
        for sink in unit.lineage.downstream:
            other_upstreams = self._find_other_upstreams(sink.name, unit_id)
            sink_info = {
                "name": sink.name,
                "type": sink.sink_type.value,
                "exclusive": sink.exclusive,
                "has_other_inputs": len(other_upstreams) > 0,
                "other_upstreams": other_upstreams,
            }
            impact["downstreams"] = [
                s if s["name"] != sink.name else sink_info
                for s in impact["downstreams"]
            ]
        
        return {
            "success": True,
            "unit_id": unit_id,
            "unit_name": unit.name,
            "impact": impact,
        }
    
    def _find_other_upstreams(self, sink_name: str, exclude_unit_id: str) -> List[str]:
        other_upstreams = []
        for unit in self._items.values():
            if unit.id == exclude_unit_id:
                continue
            for sink in unit.lineage.downstream:
                if sink.name == sink_name:
                    other_upstreams.append(unit.name)
        return other_upstreams
    
    def _get_or_create_error_stream(self) -> Stream:
        if self._error_stream is None:
            self._error_stream = NS("strategy_errors", description='策略错误流，用于收集策略执行过程中的错误信息')
            self._error_stream.sink(self._collect_error)
        return self._error_stream
    
    def _collect_error(self, error_info: dict):
        record = ErrorRecord(
            strategy_id=error_info.get("strategy_id", ""),
            strategy_name=error_info.get("strategy_name", ""),
            error=error_info.get("error", ""),
            traceback=error_info.get("traceback", ""),
            data_preview=error_info.get("data_preview", ""),
            ts=time.time(),
        )
        
        with self._errors_lock:
            self._errors.append(record)
            if len(self._errors) > self._max_errors:
                self._errors = self._errors[-self._max_errors:]
        
        self._stats.total_errors += 1
    
    def get_errors(self, limit: int = 20, unit_id: str = None) -> List[dict]:
        with self._errors_lock:
            errors = list(self._errors)
        
        if unit_id:
            errors = [e for e in errors if e.strategy_id == unit_id]
        
        errors = sorted(errors, key=lambda x: x.ts, reverse=True)
        return [e.to_dict() for e in errors[:limit]]
    
    def clear_errors(self):
        with self._errors_lock:
            self._errors.clear()
        self._stats.total_errors = 0
    
    def _update_stats(self):
        self._stats.total_units = len(self._items)
        self._stats.running_count = sum(
            1 for u in self._items.values() if u.status == StrategyStatus.RUNNING
        )
        self._stats.paused_count = sum(
            1 for u in self._items.values() if u.status == StrategyStatus.PAUSED
        )
        self._stats.draft_count = sum(
            1 for u in self._items.values() if u.status == StrategyStatus.DRAFT
        )
        self._stats.archived_count = sum(
            1 for u in self._items.values() if u.status == StrategyStatus.ARCHIVED
        )
        self._stats.total_processed = sum(
            u.state.processed_count for u in self._items.values()
        )
    
    def get_stats(self) -> dict:
        self._update_stats()
        return self._stats.to_dict()
    
    def get_topology(self) -> dict:
        nodes = []
        edges = []
        
        for unit in self._items.values():
            nodes.append({
                "id": unit.id,
                "name": unit.name,
                "type": "strategy",
                "status": unit.status.value,
            })
            
            for upstream in unit.lineage.upstream:
                source_id = f"source_{upstream.name}"
                if not any(n["id"] == source_id for n in nodes):
                    nodes.append({
                        "id": source_id,
                        "name": upstream.name,
                        "type": "source",
                        "source_type": upstream.source_type,
                    })
                edges.append({
                    "source": source_id,
                    "target": unit.id,
                })
            
            for downstream in unit.lineage.downstream:
                sink_id = f"sink_{downstream.name}"
                if not any(n["id"] == sink_id for n in nodes):
                    nodes.append({
                        "id": sink_id,
                        "name": downstream.name,
                        "type": "sink",
                        "sink_type": downstream.sink_type.value,
                    })
                edges.append({
                    "source": unit.id,
                    "target": sink_id,
                })
        
        return {
            "nodes": nodes,
            "edges": edges,
        }
    
    def create_strategy(
        self,
        name: str,
        processor_func: Callable = None,
        processor_code: str = None,
        description: str = "",
        tags: List[str] = None,
        upstream_source: str = None,
        downstream_sink: str = None,
        auto_start: bool = False,
        datasource_id: str = None,
        datasource_name: str = None,
    ) -> dict:
        try:
            unit = StrategyUnit(
                name=name,
                description=description,
                tags=tags,
                auto_start=False,
                strategy_func_code=processor_code or "",
                bound_datasource_id=datasource_id or "",
                bound_datasource_name=datasource_name or "",
            )
            
            if processor_func:
                unit.set_processor(processor_func)
            elif processor_code:
                unit.set_processor_from_code(processor_code)
            
            if upstream_source:
                unit.connect_upstream(upstream_source)
            
            if downstream_sink:
                unit.connect_downstream(downstream_sink)
            
            self.register(unit)
            unit.save()
            
            if auto_start and unit._processor_func:
                unit.start()
            
            return {
                "success": True,
                "unit_id": unit.id,
                "unit": unit.to_dict(),
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
    
    def load_from_db(self) -> int:
        db = NB("strategy_units")
        count = 0
        all_items = list(db.items())
        with self._items_lock:
            existing_names = {unit.name for unit in self._items.values()}
            for unit_id, data in all_items:
                if isinstance(data, dict):
                    try:
                        unit = StrategyUnit.from_dict(data)
                        if unit.id not in self._items and unit.name not in existing_names:
                            self._items[unit.id] = unit
                            unit.set_error_stream(self._get_or_create_error_stream())
                            existing_names.add(unit.name)
                            count += 1
                    except Exception:
                        pass
        if count > 0:
            self._update_stats()
        return count
    
    def save_all(self) -> int:
        count = 0
        for unit in self._items.values():
            try:
                unit.save()
                count += 1
            except Exception:
                pass
        return count
    
    def start_all(self) -> dict:
        results = {"success": 0, "failed": 0, "skipped": 0}
        for unit in self._items.values():
            if unit.status == StrategyStatus.DRAFT or unit.status == StrategyStatus.PAUSED:
                result = unit.start()
                if result.get("success"):
                    results["success"] += 1
                else:
                    results["failed"] += 1
            else:
                results["skipped"] += 1
        self._update_stats()
        return results
    
    def pause_all(self) -> dict:
        results = {"success": 0, "failed": 0, "skipped": 0}
        for unit in self._items.values():
            if unit.status == StrategyStatus.RUNNING:
                result = unit.pause()
                if result.get("success"):
                    results["success"] += 1
                else:
                    results["failed"] += 1
            else:
                results["skipped"] += 1
        self._update_stats()
        return results
    
    def restore_running_states(self) -> dict:
        restored_count = 0
        failed_count = 0
        results = []
        
        with self._items_lock:
            units_to_start = []
            for unit in self._items.values():
                if not getattr(unit, '_was_running', False):
                    continue
                    
                has_processor = unit._processor_func is not None
                has_code = bool(unit._processor_code or unit.metadata.strategy_func_code)
                
                if has_processor:
                    units_to_start.append(unit)
                elif has_code:
                    try:
                        code = unit._processor_code or unit.metadata.strategy_func_code
                        if code:
                            # 尝试不同的函数名
                            func_names = ["process", "processor", "test_strategy_processor"]
                            success = False
                            for func_name in func_names:
                                try:
                                    unit.set_processor_from_code(code, func_name=func_name)
                                    success = True
                                    break
                                except Exception:
                                    continue
                            if not success:
                                # 尝试动态查找函数
                                import re
                                match = re.search(r'def\s+(\w+)\s*\(', code)
                                if match:
                                    func_name = match.group(1)
                                    unit.set_processor_from_code(code, func_name=func_name)
                                    success = True
                            if success:
                                units_to_start.append(unit)
                    except Exception as e:
                        results.append({
                            "unit_id": unit.id,
                            "unit_name": unit.name,
                            "success": False,
                            "error": f"Failed to restore processor: {str(e)}",
                        })
        
        for unit in units_to_start:
            try:
                result = unit.start()
                if result.get("success"):
                    restored_count += 1
                    results.append({
                        "unit_id": unit.id,
                        "unit_name": unit.name,
                        "success": True,
                    })
                else:
                    failed_count += 1
                    results.append({
                        "unit_id": unit.id,
                        "unit_name": unit.name,
                        "success": False,
                        "error": result.get("error", "Unknown error"),
                    })
            except Exception as e:
                failed_count += 1
                results.append({
                    "unit_id": unit.id,
                    "unit_name": unit.name,
                    "success": False,
                    "error": str(e),
                })
        
        if restored_count > 0 or failed_count > 0:
            self._update_stats()
        
        return {
            "success": True,
            "restored_count": restored_count,
            "failed_count": failed_count,
            "results": results,
        }
    
    def get_recent_results(self, unit_id: str, limit: int = 10) -> List[dict]:
        unit = self.get_unit(unit_id)
        if not unit:
            return []
        return unit.get_recent_results(limit=limit)
    
    def get_result_by_id(self, result_id: str) -> Optional[dict]:
        store = get_result_store()
        result = store.get_by_id(result_id)
        return result.to_dict() if result else None
    
    def query_results(
        self,
        unit_id: str = None,
        start_ts: float = None,
        end_ts: float = None,
        success_only: bool = False,
        limit: int = 100,
    ) -> List[dict]:
        store = get_result_store()
        results = store.query(
            strategy_id=unit_id,
            start_ts=start_ts,
            end_ts=end_ts,
            success_only=success_only,
            limit=limit,
        )
        return [r.to_dict() for r in results]
    
    def get_result_stats(self, unit_id: str = None) -> dict:
        store = get_result_store()
        return store.get_stats(strategy_id=unit_id)
    
    def export_results(
        self,
        unit_id: str = None,
        format: str = "json",
        limit: int = 1000,
    ) -> str:
        store = get_result_store()
        return store.export_results(strategy_id=unit_id, format=format, limit=limit)
    
    def get_result_trend(self, unit_id: str, interval_minutes: int = 5) -> dict:
        store = get_result_store()
        return store.get_trend_data(
            strategy_id=unit_id,
            interval_minutes=interval_minutes,
        )
    
    def clear_result_cache(self, unit_id: str = None):
        store = get_result_store()
        store.clear_cache(strategy_id=unit_id)
    
    def clear_result_db(self, unit_id: str = None):
        store = get_result_store()
        store.clear_db(strategy_id=unit_id)


manager = StrategyManager.get_instance()


def get_manager() -> StrategyManager:
    return manager
