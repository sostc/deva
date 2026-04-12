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
    loop_type: str
    stage: str
    timestamp: float
    data_in_summary: Dict[str, Any]
    data_out_summary: Dict[str, Any]
    status: str
    duration_ms: float
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_loop_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
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
            import logging
            logging.warning(f"[LoopAudit] 无法初始化DB: {e}")
            self._db = None

        self._ensure_table()

    def _ensure_table(self):
        if self._db is None:
            return
        try:
            conn = sqlite3.connect(str(Path.home() / ".deva" / "nb.sqlite"))
            cur = conn.cursor()
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {LOOP_AUDIT_TABLE} (
                    loop_id TEXT,
                    loop_type TEXT,
                    stage TEXT,
                    timestamp REAL,
                    data_in_summary TEXT,
                    data_out_summary TEXT,
                    status TEXT,
                    duration_ms REAL,
                    error TEXT,
                    metadata TEXT,
                    parent_loop_id TEXT,
                    PRIMARY KEY (loop_id, stage)
                )
            """)
            conn.close()
        except Exception as e:
            import logging
            logging.warning(f"[LoopAudit] 建表失败: {e}")

    def _open_log_file(self):
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self._log_dir / f"naja_loop_audit_{today}.log"

        if self._current_log_file != log_file:
            if self._log_file_handle:
                self._log_file_handle.close()

            self._current_log_file = log_file
            self._log_file_handle = open(log_file, "a", encoding="utf-8")

    def _generate_loop_id(self, loop_type: str) -> str:
        with self._counter_lock:
            self._loop_counter += 1
            counter = self._loop_counter

        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        time_str = now.strftime("%H%M%S")
        return f"loop-{loop_type[:3]}-{date_str}-{time_str}-{counter:04d}"

    def log_stage(
        self,
        loop_type: str,
        stage: str,
        status: str = "running",
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
        status: str = "completed",
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

    def get_loop_trace(self, loop_id: str) -> List[Dict[str, Any]]:
        if self._db is None:
            return []

        try:
            conn = sqlite3.connect(str(Path.home() / ".deva" / "nb.sqlite"))
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM {LOOP_AUDIT_TABLE} WHERE loop_id = ? ORDER BY timestamp",
                (loop_id,),
            )
            columns = [desc[0] for desc in cur.description]
            results = []
            for row in cur.fetchall():
                d = dict(zip(columns, row))
                d["data_in_summary"] = json.loads(d["data_in_summary"]) if d["data_in_summary"] else {}
                d["data_out_summary"] = json.loads(d["data_out_summary"]) if d["data_out_summary"] else {}
                d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
                results.append(d)
            conn.close()
            return results
        except Exception:
            return []

    def get_loop_summary(
        self,
        since: float = None,
        loop_type: str = None,
        status: str = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        if self._db is None:
            return []

        try:
            conn = sqlite3.connect(str(Path.home() / ".deva" / "nb.sqlite"))
            cur = conn.cursor()

            query = f"SELECT * FROM {LOOP_AUDIT_TABLE}"
            conditions = []
            params = []

            if since:
                conditions.append("timestamp >= ?")
                params.append(since)

            if loop_type:
                conditions.append("loop_type = ?")
                params.append(loop_type)

            if status:
                conditions.append("status = ?")
                params.append(status)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cur.execute(query, params)
            columns = [desc[0] for desc in cur.description]
            results = []
            for row in cur.fetchall():
                d = dict(zip(columns, row))
                d["data_in_summary"] = json.loads(d["data_in_summary"]) if d["data_in_summary"] else {}
                d["data_out_summary"] = json.loads(d["data_out_summary"]) if d["data_out_summary"] else {}
                d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
                results.append(d)
            conn.close()
            return results
        except Exception:
            return []

    def get_loop_stats(self, since: float = None) -> Dict[str, Dict[str, Any]]:
        if self._db is None:
            return {}

        try:
            conn = sqlite3.connect(str(Path.home() / ".deva" / "nb.sqlite"))
            cur = conn.cursor()

            base_query = f"FROM {LOOP_AUDIT_TABLE}"
            if since:
                base_query += f" WHERE timestamp >= {since}"

            cur.execute(f"SELECT loop_type, COUNT(*) as count {base_query} GROUP BY loop_type")
            loop_counts = {row[0]: {"count": row[1]} for row in cur.fetchall()}

            cur.execute(f"SELECT loop_type, status, COUNT(*) as count {base_query} GROUP BY loop_type, status")
            for row in cur.fetchall():
                loop_type, status, count = row
                if loop_type not in loop_counts:
                    loop_counts[loop_type] = {"count": 0}
                loop_counts[loop_type][f"status_{status}"] = count

            cur.execute(f"SELECT loop_type, AVG(duration_ms) as avg_duration {base_query} GROUP BY loop_type")
            for row in cur.fetchall():
                loop_type, avg_duration = row
                if loop_type in loop_counts:
                    loop_counts[loop_type]["avg_duration_ms"] = round(avg_duration, 2)

            conn.close()
            return loop_counts
        except Exception:
            return {}

    def close(self):
        if self._log_file_handle:
            self._log_file_handle.close()
            self._log_file_handle = None


class LoopAudit:
    _logger: LoopAuditLogger = None

    def __init__(
        self,
        loop_type: str,
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