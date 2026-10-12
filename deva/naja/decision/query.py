"""决策查询服务：把 ``DecisionPlan`` 以 **纯 dict** 暴露给 UI。

为什么单独一个模块（架构基准 §6.4「UI 不深入核心对象」）::

    UI ──► decision.query（本模块）──► TradingCenter 的留痕队列 ──► DecisionPlan

UI 侧**不**直接持有 ``DecisionPlan`` / ``FusionOutput`` 这些核心对象，只消费
``dict``。这样决策产物换实现（加字段 / 换 dataclass）时，UI 不受影响；
反过来 UI 也无法"顺手"改决策对象。

约定：
- 所有函数返回**副本**，调用方改不动留痕队列。
- 没有决策历史时**如实返回空**（``available=False`` / ``None`` / ``[]``），
  绝不兜底合成一条"看起来像"的计划——那会把"还没决策"伪装成"决策了"，
  正是本项目反复踩的静默失效。
- 本模块**惰性**导入 ``TradingCenter``（``trading_center`` 依赖 ``decision``
  包，模块级反向导入会成环）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _get_center():
    """拿 TradingCenter；不可用时返回 ``None``（查询方自行降级）。"""
    try:
        from deva.naja.attention.orchestration.trading_center import get_trading_center
        return get_trading_center()
    except Exception as e:  # pragma: no cover - 依赖缺失时才走到
        log.debug(f"[decision.query] TradingCenter 不可用: {e}")
        return None


def get_decision_plan_summary(limit: int = 10) -> Dict[str, Any]:
    """dashboard 用的决策面板数据（纯 dict）。

    Returns:
        ``{"available": bool, "latest": dict|None, "recent": [dict],
        "stats": {...}, "reason": str|None}``。``available=False`` 表示
        还没产生过决策，或决策中心不可用（``reason`` 说明原因）。
    """
    center = _get_center()
    if center is None:
        return _empty_summary("决策中心不可用（TradingCenter 未装配）")
    try:
        return center.get_decision_plan_summary(limit=limit)
    except Exception as e:
        log.debug(f"[decision.query] 读取决策留痕失败: {e}")
        return _empty_summary(f"读取决策留痕失败: {e}")


def get_latest_decision_plan() -> Optional[Dict[str, Any]]:
    """最新一条决策产物；没有则 ``None``（不兜底合成）。"""
    center = _get_center()
    if center is None:
        return None
    try:
        return center.get_latest_decision()
    except Exception as e:
        log.debug(f"[decision.query] 读取最新决策失败: {e}")
        return None


def get_recent_decision_plans(limit: int = 10) -> List[Dict[str, Any]]:
    """最近若干条决策产物（最新在前）；没有则空列表。"""
    center = _get_center()
    if center is None:
        return []
    try:
        return center.get_recent_decisions(limit=limit)
    except Exception as e:
        log.debug(f"[decision.query] 读取决策历史失败: {e}")
        return []


def _empty_summary(reason: str) -> Dict[str, Any]:
    return {
        "available": False,
        "latest": None,
        "recent": [],
        "stats": {"total": 0, "shown": 0, "approved": 0, "actionable": 0},
        "reason": reason,
    }


__all__ = [
    "get_decision_plan_summary",
    "get_latest_decision_plan",
    "get_recent_decision_plans",
]
