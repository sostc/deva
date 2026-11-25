"""
geo_risk 存储层：一个 sqlite 库、一条写线程、写入统一排队

为什么不用 NB（SqliteDict）：
    `SqliteDict.__init__` 会 fork 一个 `SqliteMultithread` 写线程，而且没有常规
    的关闭路径。当前 naja 里 49 个这类线程就是这么来的；本系统还会再加十几张
    表，按 NB 的写法就是线性叠加永不回收。这里自建「单写线程 + 队列」的库。

线程模型：
    - 写：唯一一条 `geo-risk-db-writer` 线程，串行执行队列里的每个 job，
      每个 job 一个事务（commit / rollback 都在这一条线程里）。
    - 读：独立的只读连接 + 读锁；WAL 模式下读不阻塞写。
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import queue
import sqlite3
import threading
from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .schema import DDL, ENTITY_KINDS, FROZEN_COLUMNS, JSON_COLUMNS, WRITER_THREAD_NAME

log = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".naja" / "geo_risk" / "geo_risk.db"

#: evidence 允许的 subject_type（冻结）
SUBJECT_TYPES = ("entity", "project")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sql_insert(table: str, *, upsert_key: Optional[str] = None) -> str:
    cols = FROZEN_COLUMNS[table]
    placeholders = ", ".join(f":{c}" for c in cols)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    if upsert_key:
        # 快照表允许按主键更新，但 created_at 永远保留第一次写入的值
        keep = {"created_at", upsert_key}
        sets = ", ".join(f"{c} = excluded.{c}" for c in cols if c not in keep)
        sql += f" ON CONFLICT({upsert_key}) DO UPDATE SET {sets}"
    return sql


INSERT_ENTITY = _sql_insert("entity", upsert_key="entity_id")
INSERT_PROJECT = _sql_insert("project", upsert_key="project_id")
INSERT_EVIDENCE = _sql_insert("evidence")


class _WriteResult:
    """写 job 的返回值：value 给调用方，seq 只有 evidence 追加才会带。

    ❗不能拿任意 int 返回值当 seq —— 实体/项目 upsert 返回的是条数，
    早期版本就是这么把 _seq 顶到 10、导致种子 evidence 的 write_seq 从 11 开始的。
    """

    __slots__ = ("value", "seq")

    def __init__(self, value: Any, seq: Optional[int] = None):
        self.value = value
        self.seq = seq


class GeoRiskDB:
    """单写线程的 geo_risk 库。

    Args:
        path: sqlite 文件路径；测试一律传临时路径，生产默认 ``~/.naja/geo_risk/geo_risk.db``。
    """

    def __init__(self, path: Optional[Union[str, Path]] = None):
        self.path = Path(path) if path is not None else DEFAULT_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._queue: "queue.Queue[Optional[Tuple[Callable, Future, str]]]" = queue.Queue()
        self._closed = False
        self._seq = 0
        self._worker: Optional[threading.Thread] = None

        # 1) 同步建库/建表。此刻还没有写线程，不存在竞争。
        conn = sqlite3.connect(str(self.path))
        try:
            conn.executescript(DDL)
            conn.commit()
        finally:
            conn.close()

        # 2) 只读连接（WAL 下读不阻塞写）
        self._read_conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._read_conn.row_factory = sqlite3.Row
        self._read_conn.execute("PRAGMA busy_timeout=5000")
        self._read_lock = threading.Lock()

        # 3) 续上 write_seq（进程重启后仍然单调）
        cur = self._read_conn.execute("SELECT COALESCE(MAX(write_seq), 0) FROM evidence")
        self._seq = int(cur.fetchone()[0])
        cur.close()

        # 4) 唯一写线程
        self._worker = threading.Thread(
            target=self._writer_loop,
            name=WRITER_THREAD_NAME,
            daemon=True,
        )
        self._worker.start()

    # ------------------------------------------------------------------ 写
    @property
    def is_closed(self) -> bool:
        return self._closed

    def submit(self, fn: Callable, label: str = "") -> Future:
        """把一个写 job 排进队列，返回 Future。

        `fn(conn)` 在写线程里执行，返回值为 Future 的结果；抛异常则整笔回滚，
        异常通过 Future 暴露给调用方——不静默吞掉。
        """
        if self._closed:
            raise RuntimeError("GeoRiskDB 已关闭，不能再提交写请求")
        fut: Future = Future()
        self._queue.put((fn, fut, label))
        return fut

    def flush(self) -> None:
        """等队列里已经提交的写全部落库（用于测试与收尾）"""
        self.submit(lambda conn: None, label="flush").result()

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.flush()
        finally:
            self._closed = True
            self._queue.put(None)
            if self._worker is not None:
                self._worker.join(timeout=10)
            try:
                with self._read_lock:
                    self._read_conn.close()
            except Exception:
                pass

    def _writer_loop(self) -> None:
        conn = sqlite3.connect(str(self.path))
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            while True:
                item = self._queue.get()
                try:
                    if item is None:
                        return
                    fn, fut, label = item
                    try:
                        result = fn(conn)
                        conn.commit()
                        # 只有 commit 成功才推进 seq（rollback 时不产生空洞）
                        if isinstance(result, _WriteResult):
                            if result.seq is not None and result.seq > self._seq:
                                self._seq = result.seq
                            result = result.value
                        if not fut.cancelled():
                            fut.set_result(result)
                    except BaseException as exc:  # noqa: BLE001 - 必须把失败暴露给调用方
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        log.error("[GeoRisk] 写入失败 label=%s err=%s", label, exc)
                        if not fut.cancelled():
                            fut.set_exception(exc)
                finally:
                    self._queue.task_done()
        finally:
            conn.close()

    # ------------------------------------------------------------- 规范化
    @staticmethod
    def _normalize(table: str, row: Dict[str, Any], required: Sequence[str]) -> Dict[str, Any]:
        cols = FROZEN_COLUMNS[table]
        unknown = set(row) - set(cols)
        if unknown:
            raise ValueError(f"{table} 不认识的字段（字段已冻结）: {sorted(unknown)}")
        missing = [c for c in required if not row.get(c) and row.get(c) != 0]
        if missing:
            raise ValueError(f"{table} 缺少必填字段: {missing}")

        payload: Dict[str, Any] = {}
        for c in cols:
            v = row.get(c)
            if c in JSON_COLUMNS.get(table, ()):
                v = json.dumps(v if v is not None else ({} if c in ("customer_mix",) else []),
                               ensure_ascii=False, sort_keys=True)
            payload[c] = v

        if table in ("entity", "project"):
            payload["created_at"] = row.get("created_at") or _now()
            payload["updated_at"] = row.get("updated_at") or payload["created_at"]
        return payload

    # -------------------------------------------------------------- 写接口
    def upsert_entities(self, rows: Sequence[Dict[str, Any]]) -> Future:
        """写入/更新实体（当前快照）。"""
        def job(conn: sqlite3.Connection):
            payloads = []
            for r in rows:
                p = self._normalize("entity", r, ("entity_id", "kind", "canonical_name"))
                if p["kind"] not in ENTITY_KINDS:
                    raise ValueError(f"未知实体类型 {p['kind']!r}，允许值: {ENTITY_KINDS}")
                payloads.append(p)
            conn.executemany(INSERT_ENTITY, payloads)
            return len(payloads)

        return self.submit(job, label=f"entity.upsert[{len(rows)}]")

    def upsert_projects(self, rows: Sequence[Dict[str, Any]]) -> Future:
        """写入/更新项目（当前快照）。"""
        def job(conn: sqlite3.Connection):
            payloads = [
                self._normalize("project", r, ("project_id", "operator_entity_id", "name"))
                for r in rows
            ]
            conn.executemany(INSERT_PROJECT, payloads)
            return len(payloads)

        return self.submit(job, label=f"project.upsert[{len(rows)}]")

    def add_evidence(self, rows: Sequence[Dict[str, Any]]) -> Future:
        """追加证据（历史轨迹）。write_seq 由写线程单调分配。"""
        def job(conn: sqlite3.Connection):
            base = self._seq
            payloads = []
            for i, r in enumerate(rows, 1):
                if "write_seq" in r:
                    raise ValueError("write_seq 由存储层分配，调用方不得指定")
                p = self._normalize(
                    "evidence", r, ("evidence_id", "subject_type", "subject_id", "source", "url")
                )
                if p["subject_type"] not in SUBJECT_TYPES:
                    raise ValueError(f"未知 subject_type {p['subject_type']!r}，允许值: {SUBJECT_TYPES}")
                p["content_hash"] = p["content_hash"] or _sha256(f"{p['url']}\n{p.get('quote') or ''}")
                p["retrieved_at"] = p["retrieved_at"] or _now()
                p["write_seq"] = base + i
                payloads.append(p)
            conn.executemany(INSERT_EVIDENCE, payloads)
            return _WriteResult(len(payloads), seq=base + len(payloads))

        return self.submit(job, label=f"evidence.append[{len(rows)}]")

    def add_series(self, rows: Sequence[Dict[str, Any]]) -> Future:
        """追加模型输入时序（append-only，重复 series_id 直接忽略）。

        ❗只写真实抽取到的字段：调用方负责不把 None 当 0 塞进来。
        """
        required = ("series_id", "project_id", "metric", "as_of", "value", "source_id")

        def job(conn: sqlite3.Connection):
            payloads = []
            for r in rows:
                missing = [c for c in required if not r.get(c) and r.get(c) != 0]
                if missing:
                    raise ValueError(f"series 缺少必填字段: {missing}")
                payloads.append({
                    "series_id": str(r["series_id"]),
                    "project_id": str(r["project_id"]),
                    "metric": str(r["metric"]),
                    "as_of": str(r["as_of"]),
                    "value": str(r["value"]),
                    "source_id": str(r["source_id"]),
                    "observed_at": str(r.get("observed_at") or _now()),
                    "quality": str(r["quality"]) if r.get("quality") is not None else None,
                })
            conn.executemany(
                "INSERT OR IGNORE INTO series "
                "(series_id, project_id, metric, as_of, value, source_id, observed_at, quality) "
                "VALUES (:series_id, :project_id, :metric, :as_of, :value, :source_id, "
                ":observed_at, :quality)",
                payloads,
            )
            return len(payloads)

        return self.submit(job, label=f"series.append[{len(rows)}]")

    def latest_series(self, project_id: str) -> Dict[str, Any]:
        """取某项目每个 metric 的最新值；没有就是没有，不返回默认 0。"""
        rows = self.query(
            "SELECT metric, value, as_of, quality FROM series "
            "WHERE project_id = ? ORDER BY as_of DESC, observed_at DESC",
            (project_id,),
        )
        out: Dict[str, Any] = {}
        for r in rows:
            if r["metric"] not in out:
                out[r["metric"]] = dict(r)
        return out

    # -------------------------------------------------------------- 读接口
    def query(self, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
        with self._read_lock:
            cur = self._read_conn.execute(sql, params)
            rows = cur.fetchall()
            cur.close()
        return rows

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        rows = self.query(sql, params)
        return rows[0][0] if rows else None

    def count(self, table: str) -> int:
        if table not in FROZEN_COLUMNS:
            raise ValueError(f"未知表 {table!r}")
        return int(self.scalar(f"SELECT COUNT(*) FROM {table}") or 0)

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        rows = self.query("SELECT * FROM entity WHERE entity_id = ?", (entity_id,))
        return self._row_to_dict("entity", rows[0]) if rows else None

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        rows = self.query("SELECT * FROM project WHERE project_id = ?", (project_id,))
        return self._row_to_dict("project", rows[0]) if rows else None

    def list_evidence(self, subject_type: str, subject_id: str) -> List[Dict[str, Any]]:
        rows = self.query(
            "SELECT * FROM evidence WHERE subject_type = ? AND subject_id = ? ORDER BY write_seq",
            (subject_type, subject_id),
        )
        return [dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(table: str, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        for c in JSON_COLUMNS.get(table, ()):
            if d.get(c) is not None:
                d[c] = json.loads(d[c])
        return d

    # ------------------------------------------------------------------ 观测
    def stats(self) -> Dict[str, Any]:
        from deva.naja.geo_risk.store.schema import WRITER_THREAD_NAME as _name

        alive = [t for t in threading.enumerate() if t.name == _name and t.is_alive()]
        return {
            "path": str(self.path),
            "writer_threads": len(alive),
            "queued": self._queue.qsize(),
            "write_seq": self._seq,
            "closed": self._closed,
        }


# ------------------------------------------------------------------ 单例
_REGISTRY: Dict[Path, GeoRiskDB] = {}
_REGISTRY_LOCK = threading.Lock()


def get_db(path: Optional[Union[str, Path]] = None) -> GeoRiskDB:
    """按路径取单例（默认生产路径）。"""
    key = Path(path) if path is not None else DEFAULT_DB_PATH
    with _REGISTRY_LOCK:
        db = _REGISTRY.get(key)
        if db is None or db.is_closed:
            db = GeoRiskDB(key)
            _REGISTRY[key] = db
        return db


def close_all() -> None:
    with _REGISTRY_LOCK:
        dbs = list(_REGISTRY.values())
        _REGISTRY.clear()
    for db in dbs:
        try:
            db.close()
        except Exception:
            pass


atexit.register(close_all)
