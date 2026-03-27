"""策略执行结果存储模块 - 流式改造版

架构设计：
1. 热数据：SignalStream 内存流（实时处理用）
2. 错误日志：JSON Lines 文件（按天存放，顺序写）
3. 统计：内存增量统计（无持久化，需要可从日志重建）

移除：SQLite 批量写入
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from deva import NB

logger = logging.getLogger(__name__)

try:
    from ..log_stream import get_log_stream, log_strategy
    LOG_STREAM_AVAILABLE = True
except ImportError:
    LOG_STREAM_AVAILABLE = False


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

    priority: float = 0.5
    attention_score: float = 0.0
    matches_attention_focus: bool = False
    matches_held_symbol: bool = False
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
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
            "priority": self.priority,
            "attention_score": self.attention_score,
            "matches_attention_focus": self.matches_attention_focus,
            "matches_held_symbol": self.matches_held_symbol,
            "tags": self.tags,
        }

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "ts": self.ts,
            "ts_readable": datetime.fromtimestamp(self.ts).strftime("%Y-%m-%d %H:%M:%S"),
            "success": self.success,
            "process_time_ms": self.process_time_ms,
            "error": self.error[:100] if self.error else "",
            "priority": self.priority,
        }

    def get_symbol(self) -> str:
        """从 output_full 或 metadata 中提取股票代码"""
        if self.output_full and isinstance(self.output_full, dict):
            return self.output_full.get("symbol", "") or self.output_full.get("stock_code", "")
        if isinstance(self.metadata, dict):
            return self.metadata.get("symbol", "") or self.metadata.get("stock_code", "")
        return ""

    def get_sector(self) -> str:
        """从 output_full 或 metadata 中提取板块信息"""
        if self.output_full and isinstance(self.output_full, dict):
            return self.output_full.get("sector", "") or self.output_full.get("industry", "")
        if isinstance(self.metadata, dict):
            return self.metadata.get("sector", "") or self.metadata.get("industry", "")
        return ""

    def get_score(self) -> float:
        """从 output_full 或 metadata 中提取信号分数"""
        if self.output_full and isinstance(self.output_full, dict):
            return float(self.output_full.get("score", 0.5))
        if isinstance(self.metadata, dict):
            return float(self.metadata.get("score", 0.5))
        return 0.5

    def compute_priority(self, query_state) -> float:
        """根据 QueryState 计算信号优先级

        Args:
            query_state: QueryState 实例，包含:
                - attention_focus: dict{sector/symbol: weight}
                - portfolio_state: dict{held_symbols: [...]}
                - market_regime: dict{type: str}

        Returns:
            float: 优先级 [0, 1]
        """
        priority = self.get_score()

        if query_state:
            attention_focus = getattr(query_state, 'attention_focus', {}) or {}
            portfolio_state = getattr(query_state, 'portfolio_state', {}) or {}
            market_regime = getattr(query_state, 'market_regime', {}) or {}

            symbol = self.get_symbol()
            sector = self.get_sector()

            held_symbols = set(portfolio_state.get("held_symbols", []))
            if symbol and symbol in held_symbols:
                priority *= 0.3
                self.matches_held_symbol = True
                self.tags.append("already_held")

            if attention_focus:
                max_focus_weight = 0.0
                for focus_key, focus_weight in attention_focus.items():
                    if focus_key == symbol or focus_key == sector:
                        max_focus_weight = max(max_focus_weight, focus_weight)

                if max_focus_weight > 0:
                    priority *= (1 + max_focus_weight * 0.5)
                    self.matches_attention_focus = True
                    self.tags.append("attention_focus")

            regime_type = market_regime.get("type", "neutral") if isinstance(market_regime, dict) else "neutral"
            if regime_type in ("trend_up", "trend_down"):
                priority *= 1.2
                self.tags.append(f"regime_{regime_type}")

            global_attention = getattr(query_state, '_last_global_attention', None)
            if global_attention is not None and global_attention < 0.3:
                priority *= 0.7
                self.tags.append("low_attention_period")

        self.priority = max(0.0, min(1.0, priority))
        return self.priority


class StreamResultStore:
    """流式策略结果存储器

    设计原则：
    - 热数据走 SignalStream（内存），不落盘
    - 错误日志走文件（JSON Lines），按天切分
    - 统计用内存增量计算，不持久化

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 资源管理：StreamResultStore 持有数据库连接（NB）和日志文件句柄，这些是
       操作系统资源，多个实例会导致资源浪费和竞争。

    2. 全局唯一性：策略执行结果应该只有一份，所有地方看到的结果应该一致。如果
       存在多个实例，可能导致结果不一致。

    3. 生命周期：ResultStore 的生命周期与系统一致，随系统启动和关闭。

    4. 依赖注入支持：如需测试，可以设置 _signal_stream/_radar_engine/_insight_engine
       等属性来注入 mock 对象。
    ================================================================================
    """

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
        if getattr(self, "_initialized", False):
            return

        self._cache: Dict[str, deque] = {}
        self._max_cache_size = 200

        self._stats = {
            "total_results": 0,
            "total_success": 0,
            "total_failed": 0,
            "total_process_time_ms": 0,
        }
        self._stats_lock = threading.Lock()

        self._log_dir = self._get_log_dir()
        self._current_log_file: Optional[str] = None
        self._current_log_handle: Optional[Any] = None
        self._log_lock = threading.Lock()

        self._initialized = True
        logger.info(f"StreamResultStore 初始化，日志目录: {self._log_dir}")

    def _get_log_dir(self) -> str:
        """获取日志目录"""
        base_dir = os.path.expanduser("~/.deva/naja_logs")
        log_dir = os.path.join(base_dir, "results")
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        return log_dir

    def _get_log_filename(self, ts: float = None) -> str:
        """获取指定时间的日志文件名"""
        if ts is None:
            ts = time.time()
        date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        return os.path.join(self._log_dir, f"naja_results_{date_str}.log")

    def _rotate_log_if_needed(self, ts: float = None):
        """检查是否需要切换日志文件（按天切分）"""
        new_filename = self._get_log_filename(ts)
        if new_filename != self._current_log_file:
            if self._current_log_handle:
                try:
                    self._current_log_handle.close()
                except Exception:
                    pass
            self._current_log_file = new_filename
            self._current_log_handle = open(new_filename, "a", buffering=1, encoding="utf-8")
            logger.info(f"日志文件切换: {new_filename}")

    def _write_log(self, record: dict):
        """写入日志（线程安全，顺序写）"""
        ts = record.get("ts", time.time())
        self._rotate_log_if_needed(ts)

        with self._log_lock:
            if self._current_log_handle:
                try:
                    self._current_log_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    self._current_log_handle.flush()
                except Exception as e:
                    logger.error(f"写入日志失败: {e}")

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
        dispatch: bool = True,
    ) -> StrategyResult:
        """保存策略执行结果

        Args:
            dispatch: 是否触发分发（默认True，设为False可仅做存储）
        """
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

        self._update_stats(result)

        self._write_log(result.to_dict())

        self._update_cache(strategy_id, result)

        if dispatch:
            self._do_dispatch(result, output_data)

        return result

    def _do_dispatch(self, result: StrategyResult, output_data: Any) -> None:
        """触发信号分发（到 SignalStream/Radar/Cognition/Bandit）

        注意：这是存储后的异步分发，不影响存储主流程。
        分发逻辑已迁移到 SignalDispatcher，这里保留是为了向后兼容。
        """
        try:
            from ..signal.dispatcher import dispatch_result
            dispatch_result(result)
        except Exception:
            pass

        if LOG_STREAM_AVAILABLE:
            try:
                from ..log_stream import log_strategy
                signal_type = ""
                if isinstance(output_data, dict):
                    signal_type = output_data.get("signal_type", "")
                level = "INFO" if result.success else "ERROR"
                message = f"策略执行{'成功' if result.success else '失败'}: {result.strategy_name}, 信号类型: {signal_type}"
                log_strategy(level, result.strategy_id, result.strategy_name, message,
                           score=output_data.get("score") if isinstance(output_data, dict) else None,
                           process_time_ms=result.process_time_ms)
            except Exception:
                pass

    def _update_stats(self, result: StrategyResult):
        """增量更新统计"""
        with self._stats_lock:
            self._stats["total_results"] += 1
            if result.success:
                self._stats["total_success"] += 1
            else:
                self._stats["total_failed"] += 1
            self._stats["total_process_time_ms"] += result.process_time_ms

    def _update_cache(self, strategy_id: str, result: StrategyResult):
        """更新内存缓存"""
        if strategy_id not in self._cache:
            self._cache[strategy_id] = deque(maxlen=self._max_cache_size)
        self._cache[strategy_id].appendleft(result)

    def get_recent(
        self,
        strategy_id: str,
        limit: int = 10,
    ) -> List[StrategyResult]:
        """获取最近的策略结果（从内存缓存）"""
        if strategy_id in self._cache:
            results = list(self._cache[strategy_id])[:limit]
            if results:
                return results

        return []

    def get_by_id(self, result_id: str) -> Optional[StrategyResult]:
        """通过 ID 查询（从日志文件）"""
        records = self._scan_logs_for_result_id(result_id)
        if records:
            return self._dict_to_result(records[0])
        return None

    def _scan_logs_for_result_id(self, result_id: str, max_days: int = 7) -> List[dict]:
        """扫描日志文件查找指定 result_id"""
        results = []
        now = time.time()

        for day_offset in range(max_days):
            ts = now - (day_offset * 86400)
            log_file = self._get_log_filename(ts)

            if not os.path.exists(log_file):
                continue

            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            if record.get("id") == result_id:
                                results.append(record)
                                if len(results) >= 1:
                                    return results
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.debug(f"读取日志文件 {log_file} 失败: {e}")

        return results

    def query(
        self,
        strategy_id: str = None,
        start_ts: float = None,
        end_ts: float = None,
        success_only: bool = False,
        limit: int = 100,
    ) -> List[StrategyResult]:
        """查询策略结果（从日志文件）"""
        results = []
        now = time.time()
        max_days = 7

        if start_ts:
            start_date = datetime.fromtimestamp(start_ts)
        else:
            start_date = datetime.fromtimestamp(now - (max_days * 86400))

        if end_ts:
            end_date = datetime.fromtimestamp(end_ts)
        else:
            end_date = datetime.fromtimestamp(now)

        current_date = start_date
        while current_date <= end_date:
            log_file = self._get_log_filename(current_date.timestamp())

            if os.path.exists(log_file):
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                record = json.loads(line)
                                if self._match_query(record, strategy_id, start_ts, end_ts, success_only):
                                    results.append(self._dict_to_result(record))
                                    if len(results) >= limit:
                                        break
                            except json.JSONDecodeError:
                                continue
                except Exception as e:
                    logger.debug(f"读取日志文件 {log_file} 失败: {e}")

            if len(results) >= limit:
                break

            current_date = current_date + __import__("datetime").timedelta(days=1)

        results.sort(key=lambda x: x.ts, reverse=True)
        return results[:limit]

    def _match_query(
        self,
        record: dict,
        strategy_id: str = None,
        start_ts: float = None,
        end_ts: float = None,
        success_only: bool = False,
    ) -> bool:
        """判断记录是否匹配查询条件"""
        if strategy_id and record.get("strategy_id") != strategy_id:
            return False

        ts = record.get("ts", 0)
        if start_ts and ts < start_ts:
            return False
        if end_ts and ts > end_ts:
            return False

        if success_only and not record.get("success", False):
            return False

        return True

    def _dict_to_result(self, data: dict) -> StrategyResult:
        """将字典转换为 StrategyResult"""
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

    def query_errors(
        self,
        strategy_id: str = None,
        start_ts: float = None,
        end_ts: float = None,
        limit: int = 100,
    ) -> List[StrategyResult]:
        """专门查询错误记录（从日志文件）"""
        results = []
        now = time.time()
        max_days = 7

        if start_ts:
            start_date = datetime.fromtimestamp(start_ts)
        else:
            start_date = datetime.fromtimestamp(now - (max_days * 86400))

        if end_ts:
            end_date = datetime.fromtimestamp(end_ts)
        else:
            end_date = datetime.fromtimestamp(now)

        current_date = start_date
        while current_date <= end_date:
            log_file = self._get_log_filename(current_date.timestamp())

            if os.path.exists(log_file):
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                record = json.loads(line)
                                if not record.get("success", True):
                                    if self._match_query(record, strategy_id, start_ts, end_ts, False):
                                        results.append(self._dict_to_result(record))
                                        if len(results) >= limit:
                                            break
                            except json.JSONDecodeError:
                                continue
                except Exception:
                    pass

            if len(results) >= limit:
                break

            current_date = current_date + __import__("datetime").timedelta(days=1)

        results.sort(key=lambda x: x.ts, reverse=True)
        return results[:limit]

    def get_stats(self, strategy_id: str = None) -> dict:
        """获取统计信息"""
        with self._stats_lock:
            stats = dict(self._stats)

        if strategy_id and strategy_id in self._cache:
            cache_results = list(self._cache[strategy_id])
            if cache_results:
                success_count = sum(1 for r in cache_results if r.success)
                total_time = sum(r.process_time_ms for r in cache_results)
                stats.update({
                    "results_count": len(cache_results),
                    "success_count": success_count,
                    "failed_count": len(cache_results) - success_count,
                    "avg_process_time_ms": total_time / len(cache_results) if cache_results else 0,
                    "success_rate": success_count / len(cache_results) if cache_results else 0,
                })

        if stats.get("total_results", 0) > 0:
            stats["avg_process_time_ms"] = stats["total_process_time_ms"] / stats["total_results"]
            stats["success_rate"] = stats["total_success"] / stats["total_results"]

        return stats

    def get_trend_data(
        self,
        strategy_id: str,
        interval_minutes: int = 5,
        limit: int = 100,
    ) -> dict:
        """获取趋势数据"""
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

    def clear_cache(self, strategy_id: str = None):
        """清空缓存"""
        if strategy_id:
            self._cache.pop(strategy_id, None)
        else:
            self._cache.clear()

    def get_health_summary(self) -> Dict[str, Any]:
        """获取健康状态摘要"""
        last_write_ts = self._get_last_write_timestamp()
        seconds_since_write = None
        if last_write_ts:
            seconds_since_write = time.time() - last_write_ts

        return {
            "last_write_time": last_write_ts,
            "seconds_since_write": seconds_since_write,
            "total_results": self._stats.get("total_results", 0),
            "total_success": self._stats.get("total_success", 0),
            "total_failed": self._stats.get("total_failed", 0),
        }

    def _get_last_write_timestamp(self) -> Optional[float]:
        """获取最后写入时间戳"""
        for strategy_id, cache in self._cache.items():
            if cache:
                last_result = cache[0]
                if last_result and hasattr(last_result, 'ts'):
                    return last_result.ts
        return None

    def should_alert_no_writes(self, stale_seconds: float = 300, cooldown_seconds: float = 300) -> Dict[str, Any]:
        """检查是否应该告警（久未写入）"""
        health = self.get_health_summary()
        seconds_since_write = health.get("seconds_since_write")

        if seconds_since_write is None:
            return {"should_alert": False, "reason": "no_data"}

        if seconds_since_write > stale_seconds:
            return {
                "should_alert": True,
                "seconds_since_write": seconds_since_write,
                "reason": "stale",
            }

        return {"should_alert": False, "seconds_since_write": seconds_since_write}

    def close(self):
        """关闭 ResultStore"""
        if self._current_log_handle:
            try:
                self._current_log_handle.close()
            except Exception:
                pass
            self._current_log_handle = None
            self._current_log_file = None
        logger.info("StreamResultStore 已关闭")


store = StreamResultStore()


def get_result_store() -> StreamResultStore:
    return store


ResultStore = StreamResultStore


def migrate_from_old_resultstore():
    """从旧 ResultStore 迁移的辅助函数

    如果之前有数据需要迁移，可以调用此函数。
    注意：迁移是一次性的，迁移完成后旧数据可以删除。
    """
    old_db = NB("naja_strategy_results")
    old_index_db = NB("naja_result_index")

    results_written = 0
    errors = 0

    for key in old_db.keys():
        try:
            data = old_db.get(key)
            if isinstance(data, dict):
                log_record = {
                    "id": data.get("id", ""),
                    "strategy_id": data.get("strategy_id", ""),
                    "strategy_name": data.get("strategy_name", ""),
                    "ts": data.get("ts", 0),
                    "success": data.get("success", False),
                    "input_preview": data.get("input_preview", ""),
                    "output_preview": data.get("output_preview", ""),
                    "process_time_ms": data.get("process_time_ms", 0),
                    "error": data.get("error", ""),
                    "metadata": data.get("metadata", {}),
                }

                log_file = store._get_log_filename(log_record["ts"])
                Path(log_file).parent.mkdir(parents=True, exist_ok=True)

                with open(log_file, "a", buffering=1, encoding="utf-8") as f:
                    f.write(json.dumps(log_record, ensure_ascii=False) + "\n")

                results_written += 1
        except Exception:
            errors += 1

    logger.info(f"迁移完成: 成功 {results_written} 条，失败 {errors} 条")
    return {"success": results_written, "errors": errors}
