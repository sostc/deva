"""策略执行结果存储模块(Strategy Result Store)

提供策略执行结果的存储、查询和导出功能。

================================================================================
架构设计
================================================================================

【结果存储结构】
┌─────────────────────────────────────────────────────────────────────────────┐
│  StrategyResult                                                              │
│  ├── id: 结果唯一标识                                                         │
│  ├── strategy_id: 策略ID                                                      │
│  ├── strategy_name: 策略名称                                                   │
│  ├── ts: 执行时间戳                                                           │
│  ├── success: 是否成功                                                        │
│  ├── input_preview: 输入数据预览                                               │
│  ├── output_preview: 输出数据预览                                              │
│  ├── output_full: 完整输出数据                                                 │
│  ├── process_time_ms: 处理耗时(毫秒)                                           │
│  ├── error: 错误信息(如果失败)                                                 │
│  └── metadata: 额外元数据                                                      │
└─────────────────────────────────────────────────────────────────────────────┘

【存储层次】
1. 内存缓存: 最近 N 条结果 (快速访问)
2. 数据库存储: 历史结果持久化 (NB)
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from deva import NB, log


@dataclass
class StrategyResult:
    """策略执行结果"""
    id: str
    strategy_id: str
    strategy_name: str
    ts: float
    success: bool
    input_preview: str = ""
    output_preview: str = ""
    output_full: Any = None
    process_time_ms: float = 0
    error: str = ""
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "ts": self.ts,
            "ts_readable": datetime.fromtimestamp(self.ts).strftime("%Y-%m-%d %H:%M:%S"),
            "success": self.success,
            "input_preview": self.input_preview,
            "output_preview": self.output_preview,
            "process_time_ms": self.process_time_ms,
            "error": self.error,
            "metadata": self.metadata,
        }
        if self.output_full is not None:
            try:
                if isinstance(self.output_full, (dict, list)):
                    result["output_full"] = self.output_full
                elif hasattr(self.output_full, 'to_dict'):
                    result["output_full"] = self.output_full.to_dict()
                elif hasattr(self.output_full, 'to_json'):
                    result["output_full"] = json.loads(self.output_full.to_json())
                else:
                    result["output_full"] = str(self.output_full)[:5000]
            except Exception:
                result["output_full"] = str(self.output_full)[:5000]
        return result
    
    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "ts": self.ts,
            "ts_readable": datetime.fromtimestamp(self.ts).strftime("%Y-%m-%d %H:%M:%S"),
            "success": self.success,
            "process_time_ms": self.process_time_ms,
            "error": self.error[:100] if self.error else "",
        }


class ResultStore:
    """策略执行结果存储器"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._cache: Dict[str, deque] = {}
        self._db = NB("strategy_results")
        self._stats = {
            "total_results": 0,
            "total_success": 0,
            "total_failed": 0,
            "total_process_time_ms": 0,
        }
        self._data_lock = threading.RLock()
        
        self._max_cache_size = 100
        self._initialized = True
    
    def _generate_id(self, strategy_id: str, ts: float) -> str:
        import hashlib
        hash_input = f"{strategy_id}_{ts}_{time.time()}".encode()
        return hashlib.md5(hash_input).hexdigest()[:12]
    
    def _truncate_preview(self, data: Any, max_len: int = 500) -> str:
        if data is None:
            return ""
        try:
            if isinstance(data, str):
                preview = data
            elif isinstance(data, dict):
                preview = json.dumps(data, ensure_ascii=False)
            elif hasattr(data, 'to_dict'):
                preview = json.dumps(data.to_dict(), ensure_ascii=False)
            elif hasattr(data, '__len__') and len(data) > 0:
                if hasattr(data, 'head'):
                    preview = str(data.head(3).to_dict())
                else:
                    preview = str(list(data)[:5])
            else:
                preview = str(data)
            return preview[:max_len] + "..." if len(preview) > max_len else preview
        except Exception:
            return str(type(data))
    
    def save(
        self,
        strategy_id: str,
        strategy_name: str,
        success: bool,
        input_data: Any = None,
        output_data: Any = None,
        process_time_ms: float = 0,
        error: str = "",
        metadata: Dict = None,
        persist: bool = True,
    ) -> StrategyResult:
        ts = time.time()
        result_id = self._generate_id(strategy_id, ts)
        
        result = StrategyResult(
            id=result_id,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            ts=ts,
            success=success,
            input_preview=self._truncate_preview(input_data),
            output_preview=self._truncate_preview(output_data),
            output_full=output_data if success else None,
            process_time_ms=process_time_ms,
            error=error,
            metadata=metadata or {},
        )
        
        with self._data_lock:
            if strategy_id not in self._cache:
                self._cache[strategy_id] = deque(maxlen=self._max_cache_size)
            self._cache[strategy_id].appendleft(result)
            
            self._stats["total_results"] += 1
            if success:
                self._stats["total_success"] += 1
            else:
                self._stats["total_failed"] += 1
            self._stats["total_process_time_ms"] += process_time_ms
            
            if persist:
                try:
                    key = f"{strategy_id}:{result_id}"
                    self._db[key] = result.to_dict()
                except Exception as e:
                    try:
                        payload = {
                            "level": "WARNING",
                            "source": "deva.strategy.result_store",
                            "message": f"Failed to persist result: {e}",
                        }
                        payload >> log
                    except Exception:
                        pass
        
        return result
    
    def _persist_result(self, result: StrategyResult):
        try:
            with self._data_lock:
                key = f"{result.strategy_id}:{result.id}"
                self._db[key] = result.to_dict()
        except Exception as e:
            try:
                payload = {
                    "level": "WARNING",
                    "source": "deva.strategy.result_store",
                    "message": f"Failed to persist result: {e}",
                }
                payload >> log
            except Exception:
                pass
    
    def get_recent(
        self,
        strategy_id: str,
        limit: int = 10,
    ) -> List[StrategyResult]:
        with self._data_lock:
            if strategy_id in self._cache:
                results = list(self._cache[strategy_id])[:limit]
                if results:
                    return results
            
            # If cache is empty, load from database
            db_results = []
            items = list(self._db.items())
            for key, data in items:
                if isinstance(data, dict) and data.get("strategy_id") == strategy_id:
                    result = StrategyResult(
                        id=data.get("id", ""),
                        strategy_id=data.get("strategy_id", ""),
                        strategy_name=data.get("strategy_name", ""),
                        ts=data.get("ts", 0),
                        success=data.get("success", False),
                        input_preview=data.get("input_preview", ""),
                        output_preview=data.get("output_preview", ""),
                        output_full=data.get("output_full"),
                        process_time_ms=data.get("process_time_ms", 0),
                        error=data.get("error", ""),
                        metadata=data.get("metadata", {}),
                    )
                    db_results.append(result)
            
            # Sort by timestamp (newest first)
            db_results.sort(key=lambda x: x.ts, reverse=True)
            db_results = db_results[:limit]
            
            # Update cache
            if db_results:
                if strategy_id not in self._cache:
                    self._cache[strategy_id] = deque(maxlen=self._max_cache_size)
                for result in reversed(db_results):  # Add in reverse order to maintain newest first
                    self._cache[strategy_id].appendleft(result)
            
            return db_results
    
    def get_by_id(self, result_id: str) -> Optional[StrategyResult]:
        with self._data_lock:
            for key, data in self._db.items():
                if isinstance(data, dict) and data.get("id") == result_id:
                    return StrategyResult(
                        id=data.get("id", ""),
                        strategy_id=data.get("strategy_id", ""),
                        strategy_name=data.get("strategy_name", ""),
                        ts=data.get("ts", 0),
                        success=data.get("success", False),
                        input_preview=data.get("input_preview", ""),
                        output_preview=data.get("output_preview", ""),
                        output_full=data.get("output_full"),
                        process_time_ms=data.get("process_time_ms", 0),
                        error=data.get("error", ""),
                        metadata=data.get("metadata", {}),
                    )
        return None
    
    def query(
        self,
        strategy_id: str = None,
        start_ts: float = None,
        end_ts: float = None,
        success_only: bool = False,
        limit: int = 100,
    ) -> List[StrategyResult]:
        results = []
        
        with self._data_lock:
            items = list(self._db.items())
        
        for key, data in items:
            if not isinstance(data, dict):
                continue
            
            if strategy_id and data.get("strategy_id") != strategy_id:
                continue
            
            ts = data.get("ts", 0)
            if start_ts and ts < start_ts:
                continue
            if end_ts and ts > end_ts:
                continue
            
            if success_only and not data.get("success", False):
                continue
            
            result = StrategyResult(
                id=data.get("id", ""),
                strategy_id=data.get("strategy_id", ""),
                strategy_name=data.get("strategy_name", ""),
                ts=ts,
                success=data.get("success", False),
                input_preview=data.get("input_preview", ""),
                output_preview=data.get("output_preview", ""),
                output_full=data.get("output_full"),
                process_time_ms=data.get("process_time_ms", 0),
                error=data.get("error", ""),
                metadata=data.get("metadata", {}),
            )
            results.append(result)
        
        results.sort(key=lambda x: x.ts, reverse=True)
        return results[:limit]
    
    def get_stats(self, strategy_id: str = None) -> dict:
        with self._data_lock:
            stats = dict(self._stats)
        
        if strategy_id:
            results = self.get_recent(strategy_id, limit=1000)
            if results:
                success_count = sum(1 for r in results if r.success)
                total_time = sum(r.process_time_ms for r in results)
                stats.update({
                    "results_count": len(results),
                    "success_count": success_count,
                    "failed_count": len(results) - success_count,
                    "avg_process_time_ms": total_time / len(results) if results else 0,
                    "success_rate": success_count / len(results) if results else 0,
                })
        
        if stats.get("total_results", 0) > 0:
            stats["avg_process_time_ms"] = stats["total_process_time_ms"] / stats["total_results"]
            stats["success_rate"] = stats["total_success"] / stats["total_results"]
        
        return stats
    
    def clear_cache(self, strategy_id: str = None):
        with self._data_lock:
            if strategy_id:
                self._cache.pop(strategy_id, None)
            else:
                self._cache.clear()
    
    def clear_db(self, strategy_id: str = None):
        with self._data_lock:
            if strategy_id:
                keys_to_delete = [
                    k for k in self._db.keys()
                    if k.startswith(f"{strategy_id}:")
                ]
                for key in keys_to_delete:
                    del self._db[key]
            else:
                self._db.clear()
    
    def export_results(
        self,
        strategy_id: str = None,
        format: str = "json",
        limit: int = 1000,
    ) -> str:
        results = self.query(strategy_id=strategy_id, limit=limit)
        
        if format == "json":
            return json.dumps(
                [r.to_dict() for r in results],
                ensure_ascii=False,
                indent=2,
            )
        elif format == "csv":
            import io
            output = io.StringIO()
            output.write("id,strategy_name,ts,success,process_time_ms,error\n")
            for r in results:
                output.write(f"{r.id},{r.strategy_name},{r.ts},{r.success},{r.process_time_ms},\"{r.error[:100]}\"\n")
            return output.getvalue()
        else:
            return json.dumps(
                [r.to_dict() for r in results],
                ensure_ascii=False,
                indent=2,
            )
    
    def get_trend_data(
        self,
        strategy_id: str,
        interval_minutes: int = 5,
        limit: int = 100,
    ) -> dict:
        results = self.get_recent(strategy_id, limit=limit)
        
        if not results:
            return {
                "timestamps": [],
                "success_counts": [],
                "failed_counts": [],
                "avg_process_times": [],
                "process_counts": [],
            }
        
        interval_seconds = interval_minutes * 60
        now = time.time()
        
        buckets = {}
        for r in results:
            bucket_ts = int(r.ts // interval_seconds) * interval_seconds
            if bucket_ts not in buckets:
                buckets[bucket_ts] = {"success": 0, "failed": 0, "total_time": 0, "count": 0}
            
            if r.success:
                buckets[bucket_ts]["success"] += 1
            else:
                buckets[bucket_ts]["failed"] += 1
            buckets[bucket_ts]["total_time"] += r.process_time_ms
            buckets[bucket_ts]["count"] += 1
        
        sorted_buckets = sorted(buckets.items(), key=lambda x: x[0], reverse=True)[:limit]
        
        return {
            "timestamps": [datetime.fromtimestamp(ts).strftime("%H:%M") for ts, _ in sorted_buckets],
            "success_counts": [b["success"] for _, b in sorted_buckets],
            "failed_counts": [b["failed"] for _, b in sorted_buckets],
            "avg_process_times": [b["total_time"] / b["count"] if b["count"] > 0 else 0 for _, b in sorted_buckets],
            "process_counts": [b["count"] for _, b in sorted_buckets],
        }
    
    def cleanup(self, strategy_id: str, max_count: int):
        """清理超过限制的历史记录"""
        with self._data_lock:
            # 收集该策略的所有结果键
            keys = []
            for key in self._db.keys():
                if key.startswith(f"{strategy_id}:"):
                    keys.append(key)
            
            # 如果数量超过限制，删除最旧的记录
            if len(keys) > max_count:
                # 收集所有结果并按时间戳排序
                results = []
                for key in keys:
                    data = self._db.get(key)
                    if isinstance(data, dict):
                        results.append((key, data.get("ts", 0)))
                
                # 按时间戳排序（最新的在前）
                results.sort(key=lambda x: x[1], reverse=True)
                
                # 保留前 max_count 条，删除其余的
                keys_to_delete = [key for key, _ in results[max_count:]]
                for key in keys_to_delete:
                    del self._db[key]
                
                # 同时清理缓存
                if strategy_id in self._cache:
                    cache_results = list(self._cache[strategy_id])
                    if len(cache_results) > max_count:
                        self._cache[strategy_id] = deque(cache_results[:max_count], maxlen=self._max_cache_size)


store = ResultStore()


def get_result_store() -> ResultStore:
    return store
