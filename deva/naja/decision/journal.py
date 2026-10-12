"""决策留痕的**落盘**日志（重启可回放）。

为什么要有它
------------
``TradingCenter`` 的内存队列只能回答"本进程最近决策了什么"，重启即清空。
要做复盘 / 归因 / 审计，决策历史必须**跨进程存活**。

实现选型：直接复用本仓既有的 ``NB``（命名 DBStream）落盘设施——与
``SnapshotManager``（`state/snapshot.py`）、``LoopAudit`` 同构::

    NB(name, key_mode="time", time_dict_policy="append", maxsize=N)

- ``key_mode="time"``：键是时间戳，天然有序，读的时候按时间倒排即可；
- ``time_dict_policy="append"``：允许把整条 dict 当一条事件写入（默认是 reject）；
- ``maxsize``：写满自动按时间淘汰最旧记录，**不会无限增长**。

⚠️ 实测坑（务必记住）：SqliteDict 会把键**字符串化**——``db.keys()`` 拿回来的是
``'1791815588.36554'`` 这种字符串，不是 float。所以排序/取窗必须
``float(key)``；直接 ``key > cutoff`` 比较会在 str/float 之间报 TypeError
或静默给出错误顺序。

⚠️ 另一个坑：``maxsize`` 的淘汰是按**时间索引**做的。若给 ``append`` 传一个
很旧的时间戳（例如为了测试传 1000.5），这条记录会**立刻被自己挤掉**。
所以写入键必须是"当前时间附近"的值。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

TABLE_DECISION_JOURNAL = "naja_decision_journal"

# 落盘上限。决策是低频事件（一次策略信号一条），2000 条足够覆盖很长时间的复盘；
# 超限由 DBStream 自动淘汰最旧记录。
DECISION_JOURNAL_MAXSIZE = 2000


class DecisionJournal:
    """决策留痕日志（落盘）。

    只负责"存 / 取"，不做任何判断。写失败**绝不**向决策路径抛异常——
    留痕是旁路，不能因为它挂掉而让决策失败。
    """

    def __init__(
        self,
        table: str = TABLE_DECISION_JOURNAL,
        *,
        maxsize: int = DECISION_JOURNAL_MAXSIZE,
        db: Any = None,
    ):
        self.table = table
        self._last_ts = 0.0
        self._lock = threading.Lock()

        if db is not None:
            self._db = db
            return
        try:
            # 惰性导入：``deva`` 包的装配较重，且这里要保持模块导入轻量，
            # 避免 ``decision`` 包与 ``deva`` 顶层之间出现导入顺序地雷。
            from deva import NB

            self._db = NB(
                table,
                key_mode="time",
                time_dict_policy="append",
                maxsize=maxsize,
            )
        except Exception as e:
            log.warning(f"[DecisionJournal] 无法初始化落盘表 {table!r}: {e}")
            self._db = None

    # ── 写 ────────────────────────────────────────────────────────────────

    def record(self, entry: Dict[str, Any]) -> Optional[float]:
        """落盘一条决策留痕。

        Returns:
            实际写入的时间键；落盘不可用时返回 ``None``。
        """
        if self._db is None:
            return None
        if not isinstance(entry, dict):
            return None

        payload = dict(entry)
        with self._lock:
            ts = self._next_ts(payload.get("recorded_at"))
            payload["recorded_at"] = ts
            try:
                self._db.append(payload, key=ts)
            except Exception as e:
                log.warning(f"[DecisionJournal] 落盘失败: {e}")
                return None
        return ts

    def _next_ts(self, raw: Any) -> float:
        """取一个**严格递增**的时间键。

        同一毫秒（甚至同一微秒）内的两次决策若用同一个键会互相覆盖，
        所以用 ``_last_ts`` 做单调兜底。
        """
        try:
            ts = float(raw)
        except (TypeError, ValueError):
            ts = time.time()
        if ts <= self._last_ts:
            ts = self._last_ts + 1e-6
        self._last_ts = ts
        return ts

    # ── 读 ────────────────────────────────────────────────────────────────

    def _sorted_entries(self) -> List[Dict[str, Any]]:
        """全部留痕，按时间**倒序**（最新在前）。"""
        if self._db is None:
            return []
        try:
            items = list(self._db.items())
        except Exception as e:
            log.warning(f"[DecisionJournal] 读取留痕失败: {e}")
            return []

        def _key_ts(kv) -> float:
            try:
                return float(kv[0])
            except (TypeError, ValueError):
                return 0.0

        items.sort(key=_key_ts, reverse=True)
        out: List[Dict[str, Any]] = []
        for _, value in items:
            if isinstance(value, dict):
                out.append(dict(value))
        return out

    def recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        """最近若干条（最新在前）。"""
        n = _safe_int(limit, 100)
        if n <= 0:
            return []
        return self._sorted_entries()[:n]

    def history(self, hours: float = 24.0, limit: int = 200) -> List[Dict[str, Any]]:
        """时间窗内的留痕（最新在前）——回放用。"""
        n = _safe_int(limit, 200)
        if n <= 0:
            return []
        try:
            cutoff = time.time() - float(hours) * 3600.0
        except (TypeError, ValueError):
            cutoff = 0.0

        out: List[Dict[str, Any]] = []
        for entry in self._sorted_entries():
            try:
                ts = float(entry.get("recorded_at") or 0.0)
            except (TypeError, ValueError):
                ts = 0.0
            if ts >= cutoff:
                out.append(entry)
            if len(out) >= n:
                break
        return out

    def count(self) -> int:
        """落盘留痕总条数。"""
        if self._db is None:
            return 0
        try:
            return len(list(self._db.keys()))
        except Exception:
            return 0

    def stats(self) -> Dict[str, Any]:
        return {
            "table": self.table,
            "available": self._db is not None,
            "total": self.count(),
            "capacity": DECISION_JOURNAL_MAXSIZE,
        }

    # ── 维护（测试 / 运维用）─────────────────────────────────────────────

    def clear(self) -> int:
        """清空本表。**仅供测试与运维**，决策路径不应调用。"""
        if self._db is None:
            return 0
        try:
            keys = list(self._db.keys())
        except Exception:
            return 0
        removed = 0
        for key in keys:
            try:
                del self._db.db[key]
                removed += 1
            except Exception:
                pass
        try:
            self._db.db.commit()
        except Exception:
            pass
        return removed


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


_journal: Optional[DecisionJournal] = None
_journal_lock = threading.Lock()


def get_decision_journal() -> DecisionJournal:
    """获取全局决策留痕日志（单例）。"""
    global _journal
    if _journal is None:
        with _journal_lock:
            if _journal is None:
                _journal = DecisionJournal()
    return _journal


__all__ = [
    "TABLE_DECISION_JOURNAL",
    "DECISION_JOURNAL_MAXSIZE",
    "DecisionJournal",
    "get_decision_journal",
]
