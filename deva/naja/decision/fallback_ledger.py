"""兜底放行留痕 —— 独立于 ``DecisionJournal`` 的执行层事件。

为什么单独一张表
----------------
面板上的「已批准 / 已否决」数的是 ``DecisionPlan.approved``，也就是
``TradingCenter.process_strategy_signal`` 的**判定**。但底仓补仓还有一条
降级路径：决策中心否决（Manas hold）后，临近收盘由 ``CoreEstablishGate``
按 ``source="deadline"`` 放行并真实下单。这条路径的判定是「否决」，
执行却是「买入」——只数 ``approved`` 就会出现「已批准 0 但确实有成交」。

把兜底事件写进 ``DecisionJournal`` 不行：那会挤占它 2000 条的判定窗口，
把真实否决挤出视野，还污染了 ``approved`` 的语义。所以另开一张独立表，
只记**真实成交后的兜底放行**，供面板作为第三类计数单独展示。

去重口径
--------
收盘前 30 分钟的轮询每 30 秒一次，闸门每次都会返回 ``source="deadline"``，
但其中大部分轮次因为「在飞单 / 额度不足 / 已成交」并没有真的下单。
因此只在 ``open_position`` 确认成交后写一条，并按 ``(code, trade_date)``
去重 —— 一个标的一个交易日只记一次，数字才和「今天走过兜底」对得上。

写失败绝不抛给交易路径：留痕是旁路，和 ``DecisionJournal`` 同一纪律。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

TABLE_DEADLINE_FALLBACK = "naja_deadline_fallback_journal"

# 兜底放行是低频事件（每标的每交易日最多一条），500 条足够覆盖很长时间；
# 与 DecisionJournal 一样由 DBStream 按时间淘汰，不会无限增长。
DEADLINE_FALLBACK_MAXSIZE = 500


class DeadlineFallbackLedger:
    """兜底放行留痕（落盘、有界、写失败静默）。"""

    def __init__(
        self,
        table: str = TABLE_DEADLINE_FALLBACK,
        *,
        maxsize: int = DEADLINE_FALLBACK_MAXSIZE,
        db: Any = None,
    ):
        self.table = table
        self._last_ts = 0.0
        self._lock = threading.Lock()

        if db is not None:
            self._db = db
            return
        try:
            # 与 DecisionJournal 同构：惰性导入 deva 顶层，避免包初始化顺序地雷。
            from deva import NB

            self._db = NB(
                table,
                key_mode="time",
                time_dict_policy="append",
                maxsize=maxsize,
            )
        except Exception as e:
            log.warning(f"[DeadlineFallbackLedger] 无法初始化落盘表 {table!r}: {e}")
            self._db = None

    # ── 写 ────────────────────────────────────────────────────────────

    def record(
        self,
        *,
        code: str,
        name: str = "",
        trade_date: str = "",
        qty: float = 0.0,
        price: float = 0.0,
        reason: str = "",
        size_hint: float = 0.0,
    ) -> Optional[float]:
        """记一条兜底放行；同标的同交易日重复调用返回 ``None``。"""
        if self._db is None:
            return None
        payload: Dict[str, Any] = dict(
            code=code,
            name=name,
            trade_date=trade_date,
            qty=qty,
            price=price,
            reason=reason,
            size_hint=size_hint,
            source="deadline",
        )
        # 去重放在锁内：轮询线程只有一个，但锁内检查避免未来多线程重复写入。
        with self._lock:
            for prior in self._sorted_entries_unlocked():
                if (prior.get("code") == code
                        and prior.get("trade_date") == trade_date):
                    return None
            ts = self._next_ts(time.time())
            payload["recorded_at"] = ts
            try:
                self._db.append(payload, key=ts)
            except Exception as e:
                log.warning(f"[DeadlineFallbackLedger] 落盘失败: {e}")
                return None
        return ts

    def _next_ts(self, raw: Any) -> float:
        try:
            ts = float(raw)
        except (TypeError, ValueError):
            ts = time.time()
        if ts <= self._last_ts:
            ts = self._last_ts + 1e-6
        self._last_ts = ts
        return ts

    # ── 读 ────────────────────────────────────────────────────────────

    def _sorted_entries_unlocked(self) -> List[Dict[str, Any]]:
        if self._db is None:
            return []
        try:
            items = list(self._db.items())
        except Exception as e:
            log.warning(f"[DeadlineFallbackLedger] 读取留痕失败: {e}")
            return []

        def _key_ts(kv) -> float:
            try:
                return float(kv[0])
            except (TypeError, ValueError):
                return 0.0

        items.sort(key=_key_ts, reverse=True)
        return [dict(v) for _, v in items if isinstance(v, dict)]

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            n = int(limit)
        except (TypeError, ValueError):
            n = 20
        if n <= 0:
            return []
        with self._lock:
            return self._sorted_entries_unlocked()[:n]

    def count(self) -> int:
        if self._db is None:
            return 0
        try:
            return len(list(self._db.keys()))
        except Exception:
            return 0

    def clear(self) -> int:
        """仅供测试与运维。"""
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


_ledger: Optional[DeadlineFallbackLedger] = None
_ledger_lock = threading.Lock()


def get_deadline_fallback_ledger() -> DeadlineFallbackLedger:
    """全局单例（惰性创建，避免 import 期打开数据库）。"""
    global _ledger
    if _ledger is None:
        with _ledger_lock:
            if _ledger is None:
                _ledger = DeadlineFallbackLedger()
    return _ledger


def record_deadline_fallback(**kwargs) -> Optional[float]:
    """记一条兜底放行；留痕不可用时静默返回 ``None``。"""
    try:
        return get_deadline_fallback_ledger().record(**kwargs)
    except Exception as e:  # 绝不把留痕故障传播到交易路径
        log.warning(f"[DeadlineFallbackLedger] 记录失败（不影响下单）: {e}")
        return None


def get_deadline_fallback_count() -> int:
    """面板用：历史兜底放行次数；读不到返回 0。"""
    try:
        return get_deadline_fallback_ledger().count()
    except Exception:
        return 0


__all__ = [
    "TABLE_DEADLINE_FALLBACK",
    "DEADLINE_FALLBACK_MAXSIZE",
    "DeadlineFallbackLedger",
    "get_deadline_fallback_ledger",
    "record_deadline_fallback",
    "get_deadline_fallback_count",
]
