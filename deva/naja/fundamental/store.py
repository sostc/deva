"""财报落地仓（SQLite）。

为什么不用内存缓存
------------------
``FinancialDataFetcher`` 只有 24h 内存缓存，进程一重启就清零，也无法回答
「这条数据是什么时候拉的、有没有被修订过」。财报是季频数据，一年只变四次，
落库的成本极低，收益是：重启不丢、可回溯、可离线回测打分函数。

表结构刻意保持窄：一行 = 一只票的一期财报，业务字段全部塞进 ``payload``
的 JSON。财报口径常变（今年加个字段、明年换个数），窄表 + JSON 比频繁
迁移 schema 稳。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

#: 与 Naja 其他运行数据同目录，便于整体备份/迁移
DEFAULT_DB_PATH = Path.home() / ".naja" / "fundamentals.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS financials (
    symbol      TEXT NOT NULL,
    period      TEXT NOT NULL,
    period_end  TEXT,
    source      TEXT NOT NULL,
    fetched_at  REAL NOT NULL,
    payload     TEXT NOT NULL,
    PRIMARY KEY (symbol, period)
);
CREATE INDEX IF NOT EXISTS idx_fin_symbol_end
    ON financials(symbol, period_end DESC);

-- 估值/打分结果按日缓存：同一天重启不必重拉 5 年日线 + SEC 全量 facts
CREATE TABLE IF NOT EXISTS evaluations (
    symbol      TEXT NOT NULL,
    as_of       TEXT NOT NULL,
    computed_at REAL NOT NULL,
    payload     TEXT NOT NULL,
    PRIMARY KEY (symbol, as_of)
);
"""


class FundamentalStore:
    """财报读写。**只做存取，不做判断**。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def upsert(self, symbol: str, period: str, payload: Dict[str, Any]) -> None:
        """写入一期财报。

        同一 (symbol, period) 再次写入会覆盖并刷新 ``fetched_at`` ——
        财报修订（重述）本就该覆盖旧值，历史价值在于「最新一次的口径」。
        """
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO financials"
                " (symbol, period, period_end, source, fetched_at, payload)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(symbol).upper(),
                    str(period),
                    payload.get("period_end") or "",
                    payload.get("source") or "",
                    time.time(),
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )

    def latest(self, symbol: str) -> Optional[Dict[str, Any]]:
        rows = self.history(symbol, limit=1)
        return rows[0] if rows else None

    def history(self, symbol: str, limit: int = 8) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT payload, fetched_at FROM financials WHERE symbol = ?"
                " ORDER BY period_end DESC, period DESC LIMIT ?",
                (str(symbol).upper(), int(limit)),
            )
            out = []
            for row in cur.fetchall():
                try:
                    item = json.loads(row["payload"])
                except (TypeError, ValueError):
                    continue
                item["_fetched_at"] = row["fetched_at"]
                out.append(item)
            return out

    # ------------------------------------------------------------ 估值缓存

    def put_evaluation(self, symbol: str, as_of: str, payload: Dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO evaluations (symbol, as_of, computed_at, payload)"
                " VALUES (?, ?, ?, ?)",
                (
                    str(symbol).upper(),
                    str(as_of),
                    time.time(),
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )

    def get_evaluation(self, symbol: str, as_of: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload FROM evaluations WHERE symbol = ? AND as_of = ?",
                (str(symbol).upper(), str(as_of)),
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["payload"])
        except (TypeError, ValueError):
            return None

    def latest_evaluation(self, symbol: str) -> Optional[Dict[str, Any]]:
        """最近一次算过的估值（不限于今天）。

        用途是**重启预热**：新进程启动后 1~2 分钟内基本面线程还没跑完，
        这段时间不该让挡位凭空消失（消失会被环境门当成「不知道」而打折）。
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload, computed_at FROM evaluations WHERE symbol = ?"
                " ORDER BY computed_at DESC LIMIT 1",
                (str(symbol).upper(),),
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            return None
        payload["_computed_at"] = row["computed_at"]
        return payload

    def stats(self) -> Dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM financials").fetchone()[0]
            symbols = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT symbol FROM financials ORDER BY symbol"
                ).fetchall()
            ]
            newest = conn.execute(
                "SELECT MAX(fetched_at) FROM financials"
            ).fetchone()[0]
            evaluations = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
        return {
            "db_path": str(self.db_path),
            "rows": int(total),
            "symbols": symbols,
            "evaluations": int(evaluations),
            "last_fetch_age_s": None if not newest else round(time.time() - newest, 1),
        }
