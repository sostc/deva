"""闭环状态审计系统

用于追踪和记录系统中各个闭环的执行状态、数据流转路径。
支持：
- 6大闭环的全程追踪：数据流、决策、Bandit、Alaya、全球市场、预感知
- 数据流转摘要记录
- 执行耗时统计
- 失败告警
- 事后查询和分析

Usage:
    from deva.naja.infra.observability.loop_audit import LoopAudit, get_loop_audit_logger

    # 方式1：上下文管理器（推荐）
    with LoopAudit("dataflow", "strategy_execute") as audit:
        audit.record_data_in({"strategy": "新闻舆情", "rows": 100})
        result = strategy.execute(data)
        audit.record_data_out({"success": True, "signals": 5})

    # 方式2：直接调用
    logger = get_loop_audit_logger()
    logger.log_stage("decision", "manas_compute", status="running")
    ...
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from deva import NB

LOOP_AUDIT_TABLE = "naja_loop_audit"

logger = logging.getLogger(__name__)


class LoopType(Enum):
    DATAFLOW = "dataflow"
    DECISION = "decision"
    BANDIT = "bandit"
    ALAYA = "alaya"
    GLOBAL_MARKET = "global_market"
    SENSES = "senses"


class StageStatus(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class LoopAuditRecord:
    loop_id: str
    loop_type: Union[str, LoopType]
    stage: str
    timestamp: float
    data_in_summary: Dict[str, Any]
    data_out_summary: Dict[str, Any]
    status: Union[str, StageStatus]
    duration_ms: float
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_loop_id: str = ""

    def __post_init__(self):
        if isinstance(self.loop_type, str):
            try:
                self.loop_type = LoopType(self.loop_type)
            except ValueError:
                pass
        if isinstance(self.status, str):
            try:
                self.status = StageStatus(self.status)
            except ValueError:
                pass

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("loop_type"), LoopType):
            d["loop_type"] = d["loop_type"].value
        if isinstance(d.get("status"), StageStatus):
            d["status"] = d["status"].value
        d["timestamp_str"] = datetime.fromtimestamp(self.timestamp).isoformat()
        return d


def summarize_data(data: Any, max_len: int = 100) -> Dict[str, Any]:
    """将数据转换为摘要形式，避免记录完整数据"""
    if data is None:
        return {"type": "none"}

    data_type = type(data).__name__

    if data_type == "DataFrame":
        import pandas as pd
        return {
            "type": "DataFrame",
            "rows": len(data),
            "cols": list(data.columns[:10]) if hasattr(data, "columns") else [],
            "dtypes": {k: str(v) for k, v in data.dtypes.to_dict().items()} if hasattr(data, "dtypes") else {},
        }

    if data_type == "ndarray":
        return {"type": "ndarray", "shape": list(data.shape) if hasattr(data, "shape") else []}

    if isinstance(data, dict):
        keys = list(data.keys())[:20]
        return {"type": "dict", "keys": keys, "size": len(str(data))}

    if isinstance(data, (list, tuple)):
        return {"type": data_type, "len": len(data)}

    if isinstance(data, str):
        return {"type": "str", "len": len(data), "preview": data[:max_len]}

    if isinstance(data, (int, float, bool)):
        return {"type": data_type, "value": data}

    return {"type": data_type, "str": str(data)[:max_len]}


class LoopAuditLogger:
    _instance: Optional["LoopAuditLogger"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._db: Optional[NB] = None
        self._log_dir = Path.home() / ".deva" / "naja_logs" / "loop_audit"
        self._current_log_file: Optional[Path] = None
        self._log_file_handle = None
        self._loop_counter = 0
        self._counter_lock = threading.Lock()
        self._active_loops: Dict[str, LoopAuditRecord] = {}
        self._active_lock = threading.Lock()
        self._last_prune_ts: float = 0.0

    @classmethod
    def get_instance(cls) -> "LoopAuditLogger":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._open_log_file()

        try:
            self._db = NB(LOOP_AUDIT_TABLE, key_mode="time")
        except Exception as e:
            logger.warning(f"[LoopAudit] 无法初始化DB: {e}")
            self._db = None

        # 启动即做一次轮转清理（DB 记录 + 日志文件），此后由 _write_log 按小时节流。
        self._maybe_prune(force=True)

    # 注：旧版这里有个 _ensure_table()，试图用原生 SQL 建一张列式宽表
    # （loop_id / loop_type / timestamp ... PRIMARY KEY(loop_id, stage)）。
    # 但表先由上面的 NB(LOOP_AUDIT_TABLE) 以 DBStream 形式建成了 (key, value)，
    # “CREATE TABLE IF NOT EXISTS” 于是变成 no-op —— 列式结构从未存在，
    # 而读取端（本文件与 loop_audit_ui）却按列式字段查询，全部抛错被静默吞掉。
    # 现已删除：表结构以 DBStream 为唯一事实，写入/读取都经它进行。

    def _open_log_file(self):
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self._log_dir / f"naja_loop_audit_{today}.log"

        if self._current_log_file != log_file:
            if self._log_file_handle:
                self._log_file_handle.close()

            self._current_log_file = log_file
            self._log_file_handle = open(log_file, "a", encoding="utf-8")

    def _generate_loop_id(self, loop_type: Union[str, LoopType]) -> str:
        with self._counter_lock:
            self._loop_counter += 1
            counter = self._loop_counter

        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        time_str = now.strftime("%H%M%S")
        lt = loop_type.value if isinstance(loop_type, LoopType) else loop_type
        return f"loop-{lt[:3]}-{date_str}-{time_str}-{counter:04d}"

    def log_stage(
        self,
        loop_type: Union[str, LoopType],
        stage: str,
        status: Union[str, StageStatus] = "running",
        data_in: Any = None,
        data_out: Any = None,
        error: str = "",
        metadata: Dict[str, Any] = None,
        loop_id: str = None,
        parent_loop_id: str = "",
    ) -> str:
        timestamp = time.time()

        if loop_id is None:
            loop_id = self._generate_loop_id(loop_type)

        data_in_summary = summarize_data(data_in) if data_in is not None else {}
        data_out_summary = summarize_data(data_out) if data_out is not None else {}

        record = LoopAuditRecord(
            loop_id=loop_id,
            loop_type=loop_type,
            stage=stage,
            timestamp=timestamp,
            data_in_summary=data_in_summary,
            data_out_summary=data_out_summary,
            status=status,
            duration_ms=0,
            error=error,
            metadata=metadata or {},
            parent_loop_id=parent_loop_id,
        )

        self._write_log(record)

        if status == "running":
            with self._active_lock:
                self._active_loops[loop_id] = record

        return loop_id

    def finish_stage(
        self,
        loop_id: str,
        stage: str,
        status: Union[str, StageStatus] = "completed",
        data_out: Any = None,
        error: str = "",
    ):
        with self._active_lock:
            record = self._active_loops.get(loop_id)

        if record is None:
            record = LoopAuditRecord(
                loop_id=loop_id,
                loop_type="",
                stage=stage,
                timestamp=time.time(),
                data_in_summary={},
                data_out_summary={},
                status=status,
                duration_ms=0,
            )

        duration_ms = (time.time() - record.timestamp) * 1000
        data_out_summary = summarize_data(data_out) if data_out is not None else record.data_out_summary

        finished_record = LoopAuditRecord(
            loop_id=loop_id,
            loop_type=record.loop_type,
            stage=stage,
            timestamp=record.timestamp,
            data_in_summary=record.data_in_summary,
            data_out_summary=data_out_summary,
            status=status,
            duration_ms=duration_ms,
            error=error,
            metadata=record.metadata,
            parent_loop_id=record.parent_loop_id,
        )

        self._write_log(finished_record)

        with self._active_lock:
            self._active_loops.pop(loop_id, None)

    def _write_log(self, record: LoopAuditRecord):
        log_line = json.dumps(record.to_dict(), ensure_ascii=False, default=str)

        try:
            if self._log_file_handle:
                self._log_file_handle.write(log_line + "\n")
                self._log_file_handle.flush()
        except Exception:
            pass

        if self._db is not None:
            try:
                key = f"{record.loop_id}:{record.stage}"
                self._db[key] = record.to_dict()
            except Exception:
                pass
            self._maybe_prune()

    # ------------------------------------------------------------------
    # 保留期 / 轮转清理
    # ------------------------------------------------------------------
    KEEP_DAYS = int(os.environ.get("NAJA_LOOP_AUDIT_KEEP_DAYS") or "7")
    PRUNE_INTERVAL_SECONDS = 3600

    def _maybe_prune(self, force: bool = False):
        """按 PRUNE_INTERVAL_SECONDS 节流地清理过期审计记录与日志文件。"""
        now = time.time()
        if not force and now - self._last_prune_ts < self.PRUNE_INTERVAL_SECONDS:
            return
        self._last_prune_ts = now
        try:
            self.prune_old_records(self.KEEP_DAYS)
        except Exception as e:
            logger.warning(f"[LoopAudit] 清理失败: {e}")

    def prune_old_records(self, keep_days: int = None) -> int:
        """清理超过保留期的审计记录（DB 记录 + 日志文件），返回删除的 DB 条数。

        注意：本表的 key 形如 ``{loop_id}:{stage}``（loop_id 内嵌时间串），
        **不是**时间戳 —— ``DBStream.prune_older_than`` 的 key 解析对它无效，
        因此这里按 value（dict）内的 ``timestamp`` 字段做轮转。
        """
        if keep_days is None:
            keep_days = self.KEEP_DAYS
        cutoff = time.time() - keep_days * 86400

        removed = 0
        if self._db is not None:
            try:
                removed = self._db.prune_older_than_field("timestamp", cutoff)
            except Exception as e:
                logger.warning(f"[LoopAudit] DB 清理失败: {e}")

        self._rotate_log_files(cutoff)
        return removed

    def _rotate_log_files(self, cutoff_ts: float):
        """删除修改时间早于 cutoff 的审计日志文件（写入中的当天文件不会被删）。"""
        try:
            for f in self._log_dir.glob("naja_loop_audit_*.log"):
                try:
                    if f.stat().st_mtime < cutoff_ts:
                        f.unlink()
                except Exception:
                    pass
        except Exception:
            pass

    def _iter_db_records(self):
        """安全遍历 DBStream 中的所有记录 dict（跳过坏行）。"""
        if self._db is None:
            return
        try:
            keys = list(self._db)
        except Exception:
            return
        for key in keys:
            try:
                rec = self._db[key]
            except Exception:
                continue
            if isinstance(rec, dict):
                yield rec

    def get_loop_trace(self, loop_id: str) -> List[Dict[str, Any]]:
        results = [r for r in self._iter_db_records() if r.get("loop_id") == loop_id]
        results.sort(key=lambda r: r.get("timestamp") or 0)
        return results

    def get_loop_summary(
        self,
        since: float = None,
        loop_type: str = None,
        status: str = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        results = []
        for r in self._iter_db_records():
            if since and (r.get("timestamp") or 0) < since:
                continue
            if loop_type and r.get("loop_type") != loop_type:
                continue
            if status and r.get("status") != status:
                continue
            results.append(r)
        results.sort(key=lambda r: r.get("timestamp") or 0, reverse=True)
        return results[:limit]

    def get_loop_stats(self, since: float = None) -> Dict[str, Dict[str, Any]]:
        stats: Dict[str, Dict[str, Any]] = {}
        for r in self._iter_db_records():
            if since and (r.get("timestamp") or 0) < since:
                continue
            loop_type = r.get("loop_type") or "unknown"
            s = stats.setdefault(loop_type, {"count": 0, "_dur_sum": 0.0, "_dur_n": 0})
            s["count"] += 1
            status = r.get("status")
            if status:
                s[f"status_{status}"] = s.get(f"status_{status}", 0) + 1
            dur = r.get("duration_ms")
            if isinstance(dur, (int, float)):
                s["_dur_sum"] += dur
                s["_dur_n"] += 1

        for s in stats.values():
            n = s.pop("_dur_n", 0)
            total_dur = s.pop("_dur_sum", 0.0)
            if n:
                s["avg_duration_ms"] = round(total_dur / n, 2)
        return stats

    def close(self):
        if self._log_file_handle:
            self._log_file_handle.close()
            self._log_file_handle = None


class LoopAudit:
    _logger: LoopAuditLogger = None

    def __init__(
        self,
        loop_type: Union[str, LoopType],
        stage: str,
        data_in: Any = None,
        metadata: Dict[str, Any] = None,
        loop_id: str = None,
        parent_loop_id: str = "",
    ):
        self.loop_type = loop_type
        self.stage = stage
        self.loop_id = loop_id
        self.parent_loop_id = parent_loop_id
        self._data_in = data_in
        self._metadata = metadata or {}
        self._finished = False

        if LoopAudit._logger is None:
            LoopAudit._logger = LoopAuditLogger.get_instance()

    def __enter__(self):
        self.loop_id = self._logger.log_stage(
            loop_type=self.loop_type,
            stage=self.stage,
            status="running",
            data_in=self._data_in,
            metadata=self._metadata,
            loop_id=self.loop_id,
            parent_loop_id=self.parent_loop_id,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._finished:
            return

        if exc_type is not None:
            self._logger.finish_stage(
                loop_id=self.loop_id,
                stage=self.stage,
                status="failed",
                error=f"{exc_type.__name__}: {exc_val}",
            )
        else:
            self._logger.finish_stage(
                loop_id=self.loop_id,
                stage=self.stage,
                status="completed",
            )

        self._finished = True

    def record_data_out(self, data_out: Any):
        self._logger.finish_stage(
            loop_id=self.loop_id,
            stage=self.stage,
            status="completed",
            data_out=data_out,
        )
        self._finished = True

    def record_error(self, error: str):
        self._logger.finish_stage(
            loop_id=self.loop_id,
            stage=self.stage,
            status="failed",
            error=error,
        )
        self._finished = True


def get_loop_audit_logger() -> LoopAuditLogger:
    return LoopAuditLogger.get_instance()


def audit(loop_type: str, stage: str):
    return LoopAudit(loop_type, stage)