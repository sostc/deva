"""
末那识行动门的审计留痕。

================================================================================
为什么值得做
================================================================================

每次 `ManasEngine.compute()` 都会产出两样东西：一个**决定**（should_act /
action_type）和一句**理由**（action_gate_reason，形如「策略不自信 | 行动:hold
| ✗未通过」）。后者此前只挂在 UI 上一次性的输出里，回看即失。

而在风控语境里，这句理由恰恰是最有价值的记录：它把「没动」从「没信号」
变成「有理由的拒绝」。按次留痕之后就能回答：

    · 过去 8 小时里，行动门拒绝了它多少次？最常见的拒绝理由是什么？
    · 拒绝理由是**稳定偏好**（例如长期「策略不自信」）还是**一次性事件**？
    · 某个改动上线后，拒绝率有没有变化？

它也是「可解释性」的最低成本落地方式——不新增任何计算，只是把既有输出存下来。

================================================================================
设计要点
================================================================================

    · 有界环形缓冲（默认 500 条），不会无限增长；
    · **连续重复折叠**：相邻两次 (action_type, should_act, reason) 完全相同时
      不新增行，而是给上一行 `occurrences += 1` 并刷新 `last_ts`。
      否则 1 秒一次的心跳会把缓冲刷满成同一句话。
    · 落盘节流：每 N 次记录才写一次 NB（默认 50），避免每秒一次 DB 写；
      `persist(force=True)` 可强制落盘（供退出/快照时调用）。
    · **审计永不抛异常**：留痕是旁路，任何失败都只能降级为「少了一条记录」，
      绝不能影响决策本身。
"""

from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

import logging

log = logging.getLogger(__name__)

#: NB 表名（与 attention/tracking 下的表命名风格一致）
GATE_AUDIT_TABLE = "naja_manas_gate_audit"

#: 落盘时的键名（NB 是 kv 表，用一个固定 key 存整个列表）
_GATE_AUDIT_KEY = "entries"


class GateAuditLog:
    """行动门留痕（有界 + 连续重复折叠 + 节流落盘）。"""

    def __init__(self, maxlen: int = 500, persist_every: int = 50,
                 table: str = GATE_AUDIT_TABLE):
        self._entries: Deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self._persist_every = max(1, persist_every)
        self._since_persist = 0
        self._table = table
        self._db = None
        self._record_count = 0

    # ── 记录 ────────────────────────────────────────────────────────────────

    def record(self, output: Any) -> Optional[Dict[str, Any]]:
        """记录一次行动门判定。output 为 ManasOutput（鸭子类型，只读四个字段）。

        返回本次写入/更新的行；失败返回 None（绝不抛异常）。
        """
        try:
            entry = self._build_entry(output)
        except Exception as e:  # noqa: BLE001 - 留痕是旁路，失败只能降级
            log.debug("[GateAudit] 构造记录失败，跳过: %s", e)
            return None

        try:
            last = self._entries[-1] if self._entries else None
            if last is not None and self._is_same_decision(last, entry):
                # 连续同一判定：折叠，避免心跳把缓冲刷成同一句话。
                # ❗数值字段必须一起刷新到**最新一次**：区间里环境是会变的
                #   （例如宏观流动性刚接上、regime_score 从 0 变成 0.4），若数值
                #   永远停在区间首条，「显示的数不是现在的数」—— 比不显示更误导。
                #   ts 保留区间起点（首次发生），last_ts 记最近一次。
                last["occurrences"] += 1
                last["last_ts"] = entry["ts"]
                for key, value in entry.items():
                    if key != "ts":
                        last[key] = value
            else:
                entry["occurrences"] = 1
                self._entries.append(entry)

            self._record_count += 1
            self._since_persist += 1
            if self._since_persist >= self._persist_every:
                self.persist()
            return entry
        except Exception as e:  # noqa: BLE001
            log.debug("[GateAudit] 写入缓冲失败: %s", e)
            return None

    @staticmethod
    def _build_entry(output: Any) -> Dict[str, Any]:
        def _val(name: str, default: Any = None) -> Any:
            v = getattr(output, name, default)
            return getattr(v, "value", v)

        factors = getattr(output, "gate_factors", None) or {}
        return {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "should_act": bool(getattr(output, "should_act", False)),
            "action_type": _val("action_type"),
            "reason": getattr(output, "action_gate_reason", "") or "",
            # ❗归因必须一起留痕：只存一句话（「策略不自信 | …」）事后仍分不清
            #   到底是**大环境**不适合，还是**策略历史**拖后腿 —— 前者该等，
            #   后者是数据问题。dominant = 缺口最大（真正卡住）的那一维。
            "dominant_factor": factors.get("dominant"),
            "factors": factors.get("factors"),
            "discount": factors.get("discount"),
            # ❗意愿接线同样要留痕：本次判定**实际用的门槛**是多少、人的意愿把
            #   门槛放宽了多少。否则事后只看「终分 0.41 < 门槛 0.50」会以为判错，
            #   其实是意愿把门槛降到了 0.35。effective_threshold 与 reason 必须自洽。
            "intent_confidence": round(float(getattr(output, "intent_confidence", 0.0) or 0.0), 4),
            "intent_relaxation": round(float(getattr(output, "intent_relaxation", 0.0) or 0.0), 4),
            "effective_threshold": round(float(getattr(output, "effective_threshold", 0.0) or 0.0), 4),
            "manas_score": round(float(getattr(output, "manas_score", 0.0) or 0.0), 4),
            "alpha": round(float(getattr(output, "alpha", 0.0) or 0.0), 4),
            "timing_score": round(float(getattr(output, "timing_score", 0.0) or 0.0), 4),
            # ❗regime_score 也留痕：它是「大环境（含宏观流动性）」进决策的唯一
            #   通道 —— 由 trend / liquidity(macro*2-1) / diffusion 加权而来，
            #   再经调节链折算成折扣。折扣恒 0.85 就等于 regime_score 恒 0，
            #   只存折扣看不出来「是环境真的中性」还是「这条线压根没接上」。
            "regime_score": round(float(getattr(output, "regime_score", 0.0) or 0.0), 4),
            "risk_temperature": round(float(getattr(output, "risk_temperature", 0.0) or 0.0), 4),
            "confidence_score": round(float(getattr(output, "confidence_score", 0.0) or 0.0), 4),
            "bias_state": _val("bias_state"),
        }

    @staticmethod
    def _is_same_decision(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        return (a.get("action_type") == b.get("action_type")
                and a.get("should_act") == b.get("should_act")
                and a.get("reason") == b.get("reason"))

    # ── 读取 ────────────────────────────────────────────────────────────────

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """最近的判定记录（时间正序）。"""
        if limit <= 0:
            return []
        return [dict(e) for e in list(self._entries)[-limit:]]

    def stats(self) -> Dict[str, Any]:
        """汇总：总判定次数、拒绝率、首次/最近时间、Top 拒绝理由。"""
        if not self._entries:
            return {
                "total_decisions": 0, "hold_ratio": None,
                "first_ts": None, "last_ts": None, "top_reasons": [],
            }

        total = sum(e.get("occurrences", 1) for e in self._entries)
        holds = sum(e.get("occurrences", 1) for e in self._entries if not e.get("should_act"))

        reason_counts: Dict[str, int] = {}
        for e in self._entries:
            key = e.get("reason") or "(空)"
            reason_counts[key] = reason_counts.get(key, 0) + e.get("occurrences", 1)
        top_reasons = sorted(reason_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]

        return {
            "total_decisions": total,
            "hold_ratio": round(holds / total, 4) if total else None,
            "first_ts": self._entries[0].get("ts"),
            "last_ts": self._entries[-1].get("ts"),
            "top_reasons": [{"reason": r, "count": c} for r, c in top_reasons],
        }

    def __len__(self) -> int:
        return len(self._entries)

    # ── 落盘 ────────────────────────────────────────────────────────────────

    def _get_db(self):
        if self._db is None:
            from deva import NB
            self._db = NB(self._table)
        return self._db

    def persist(self, force: bool = False) -> bool:
        """把缓冲写入 NB。成功返回 True。失败只降级，不抛。"""
        if not force and self._since_persist == 0:
            return False
        try:
            db = self._get_db()
            db[_GATE_AUDIT_KEY] = self.recent(limit=len(self._entries))
            if hasattr(db, "persist"):
                db.persist()
            self._since_persist = 0
            return True
        except Exception as e:  # noqa: BLE001
            log.debug("[GateAudit] 落盘失败（降级为仅内存）: %s", e)
            return False

    def load(self) -> int:
        """从 NB 恢复缓冲，返回载入条数。"""
        try:
            db = self._get_db()
            rows = db.get(_GATE_AUDIT_KEY) or []
            for row in rows[-self._entries.maxlen:]:
                self._entries.append(dict(row))
            return len(self._entries)
        except Exception as e:  # noqa: BLE001
            log.debug("[GateAudit] 载入失败: %s", e)
            return 0


_gate_audit: Optional[GateAuditLog] = None


def get_gate_audit_log() -> GateAuditLog:
    """获取全局行动门留痕（懒加载单例）。"""
    global _gate_audit
    if _gate_audit is None:
        _gate_audit = GateAuditLog()
    return _gate_audit


__all__ = ["GateAuditLog", "GATE_AUDIT_TABLE", "get_gate_audit_log"]
