"""
FocusAdmin —— 「关注管理」的后端 API（**纯 dict 进出，供 UI 用**）

═══════════════════════════════════════════════════════════════════════════
职责
═══════════════════════════════════════════════════════════════════════════

给 ``/focusadmin`` 页面提供四块能力，全部以**纯 dict** 返回，绝不把
``FocusItem`` / ``USStockPosition`` 这类内部对象漏给 UI：

    ① 关注主题    list / add / update / remove
    ② 持仓        按账户分组查看 + 「手动」账户增删改
    ③ 自选        list / add / update / remove（``naja_watchlist`` 的 ``stocks``）
    ④ 推导        preview（只看） / apply（采纳） / revoke（一键撤销）

═══════════════════════════════════════════════════════════════════════════
三守约（沿用 decision/query.py 的既有约定）
═══════════════════════════════════════════════════════════════════════════

1. **不兜底合成**：读不到就 ``{"ok": False, "reason": ...}``，
   不用默认值假装读到了（本项目最贵的教训）。
2. **降级必留痕**：任何一步失败都带 ``reason`` / ``degraded``。
3. **写操作后失效焦点缓存**：``news/focus.py`` 有 60s TTL 缓存，
   不失效的话"UI 改了、报告 60 秒后才变"会被当成 bug。

═══════════════════════════════════════════════════════════════════════════
账户真相（UI 要如实展示，不要美化）
═══════════════════════════════════════════════════════════════════════════

* ``虚拟测试``  —— 模拟盘；``_virtual_portfolio`` 未注入时**建不起来**
* ``Spark`` / ``Cutie``  —— 券商账户（配置文件加载）
* ``FutuReal``  —— 富途同步账户，**由 ``futu_portfolio_syncer`` 注册**；
  同步器没跑时它就不存在（时序依赖，不是 bug）
* ``手动``  —— 用户手填的真实仓位（本模块的 CRUD 对象）
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

SOURCE_DERIVED = "derived"
SOURCE_USER = "user"

_MANUAL_ACCOUNT_ATTR = "手动"


# ── 懒加载（避免导入期成环：news → attention → bandit）──────────────────

def _fm() -> Any:
    from deva.naja.attention.focus_manager import get_attention_focus_manager
    return get_attention_focus_manager()


def _pf() -> Any:
    from deva.naja.attention.portfolio import get_portfolio
    return get_portfolio()


def _pm() -> Any:
    from deva.naja.bandit.portfolio_manager import get_portfolio_manager
    return get_portfolio_manager()


def _manual_account_name() -> str:
    try:
        from deva.naja.bandit.portfolio_manager import MANUAL_ACCOUNT
        return MANUAL_ACCOUNT
    except Exception:
        return _MANUAL_ACCOUNT_ATTR


def _invalidate_focus_cache() -> None:
    """写操作后让 ``news/focus.py`` 的快照缓存立即失效。"""
    try:
        from deva.naja.news.focus import invalidate_focus_cache
        invalidate_focus_cache()
    except Exception as e:  # 缓存失效失败不该让写操作失败，但要说出来
        log.warning("[FocusAdmin] 焦点缓存失效失败（改动可能延迟生效）: %s", e)


def _position_row(pos: Any) -> Dict[str, Any]:
    from deva.naja.attention.portfolio import position_to_dict
    return position_to_dict(pos)


def _topic_row(item: Any) -> Dict[str, Any]:
    return {
        "topic": getattr(item, "focus_id", ""),
        "display_name": getattr(item, "display_name", "") or getattr(item, "focus_id", ""),
        "source": getattr(item, "source", ""),
        "priority": round(float(getattr(item, "priority", 0.0) or 0.0), 4),
        "status": getattr(item, "status", ""),
        "linked_blocks": list(getattr(item, "linked_blocks", None) or []),
        "add_time": float(getattr(item, "add_time", 0.0) or 0.0),
    }


# ── ① 关注主题 ──────────────────────────────────────────────────────────

def list_topics() -> Dict[str, Any]:
    """列出全部关注主题（区分手动 / 推导来源）。"""
    try:
        fm = _fm()
        summary = fm.get_summary()
    except Exception as e:
        return {"ok": False, "reason": f"关注管理器不可用（{type(e).__name__}: {e}）",
                "topics": [], "manual": [], "derived": []}

    rows = [_topic_row(i) for i in (getattr(summary, "narratives", None) or [])]
    manual = [r for r in rows if r["source"] != SOURCE_DERIVED]
    derived = [r for r in rows if r["source"] == SOURCE_DERIVED]
    # 稳定的展示顺序：手动在前，各自按优先级降序
    manual.sort(key=lambda r: (-r["priority"], r["topic"]))
    derived.sort(key=lambda r: (-r["priority"], r["topic"]))
    return {"ok": True, "reason": "", "topics": manual + derived,
            "manual": manual, "derived": derived}


def add_topic(name: str, priority: float = 0.7) -> Dict[str, Any]:
    """新增一个**手动**关注主题（``source="user"``）。已存在则拒绝，不覆盖。"""
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "reason": "主题名不能为空"}
    try:
        priority = float(priority)
    except (TypeError, ValueError):
        return {"ok": False, "reason": f"优先级非法: {priority!r}"}
    priority = min(1.0, max(0.0, priority))

    try:
        fm = _fm()
        existing = set(fm.get_watched_narratives() or [])
    except Exception as e:
        return {"ok": False, "reason": f"关注管理器不可用（{type(e).__name__}: {e}）"}

    if name in existing:
        return {"ok": False, "reason": f"主题「{name}」已存在（如需改优先级请用 update）"}

    try:
        item = fm.follow_narrative(name, priority=priority, source=SOURCE_USER)
    except Exception as e:
        return {"ok": False, "reason": f"写入失败（{type(e).__name__}: {e}）"}

    _invalidate_focus_cache()
    return {"ok": True, "reason": "", "topic": _topic_row(item)}


def update_topic(name: str, priority: Optional[float] = None) -> Dict[str, Any]:
    """修改主题的优先级。

    **保留原 ``source``** —— 直接调 ``follow_narrative`` 会把 source 改掉，
    那样"撤销推导"就会顺手删掉用户手动加的主题。
    """
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "reason": "主题名不能为空"}
    if priority is None:
        return {"ok": False, "reason": "没有要修改的字段（当前仅支持 priority）"}
    try:
        priority = min(1.0, max(0.0, float(priority)))
    except (TypeError, ValueError):
        return {"ok": False, "reason": f"优先级非法: {priority!r}"}

    try:
        fm = _fm()
        items = list(getattr(fm.get_summary(), "narratives", None) or [])
    except Exception as e:
        return {"ok": False, "reason": f"关注管理器不可用（{type(e).__name__}: {e}）"}

    target = next((i for i in items if getattr(i, "focus_id", "") == name), None)
    if target is None:
        return {"ok": False, "reason": f"主题「{name}」不在关注列表里"}

    try:
        item = fm.follow_narrative(
            name, priority=priority,
            source=getattr(target, "source", SOURCE_USER),
            blocks=list(getattr(target, "linked_blocks", None) or []) or None,
        )
    except Exception as e:
        return {"ok": False, "reason": f"写入失败（{type(e).__name__}: {e}）"}

    _invalidate_focus_cache()
    return {"ok": True, "reason": "", "topic": _topic_row(item)}


def remove_topic(name: str) -> Dict[str, Any]:
    """取消关注一个主题。"""
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "reason": "主题名不能为空"}
    try:
        fm = _fm()
        existing = set(fm.get_watched_narratives() or [])
    except Exception as e:
        return {"ok": False, "reason": f"关注管理器不可用（{type(e).__name__}: {e}）"}

    if name not in existing:
        return {"ok": False, "reason": f"主题「{name}」不在关注列表里"}
    try:
        fm.unfollow_narrative(name)
    except Exception as e:
        return {"ok": False, "reason": f"删除失败（{type(e).__name__}: {e}）"}

    _invalidate_focus_cache()
    return {"ok": True, "reason": "", "removed": name}


# ── ② 持仓 ──────────────────────────────────────────────────────────────

def list_positions() -> Dict[str, Any]:
    """按账户列出持仓 + 账户健康状态。

    「手动」账户即使为空也**总是出现**（否则用户找不到入口往里加东西）。
    """
    degraded: List[str] = []
    manual_name = _manual_account_name()

    accounts: List[Dict[str, Any]] = []
    status: Dict[str, Any] = {}
    try:
        pm = _pm()
    except Exception as e:
        return {"ok": False, "reason": f"PortfolioManager 不可用（{type(e).__name__}: {e}）",
                "accounts": [], "status": {}, "manual_account": manual_name,
                "degraded": [f"账户读取失败：{e}"]}

    try:
        status = pm.get_account_status() or {}
    except Exception as e:
        degraded.append(f"账户状态读取失败（{type(e).__name__}: {e}）")

    try:
        portfolios = pm.get_brokerage_portfolios() or {}
    except Exception as e:
        portfolios = {}
        degraded.append(f"券商账户读取失败（{type(e).__name__}: {e}）")

    for name, portfolio in portfolios.items():
        try:
            positions = [_position_row(p) for p in portfolio.get_open_positions()]
            summary = portfolio.get_summary()
        except Exception as e:
            degraded.append(f"账户 {name} 持仓读取失败（{type(e).__name__}: {e}）")
            continue
        accounts.append({
            "name": name,
            "kind": "manual" if name == manual_name else "brokerage",
            "positions": positions,
            "position_count": len(positions),
            "summary": summary,
        })

    if manual_name not in {a["name"] for a in accounts}:
        accounts.append({
            "name": manual_name, "kind": "manual", "positions": [],
            "position_count": 0, "summary": {},
        })

    accounts.sort(key=lambda a: (a["kind"] != "manual", a["name"]))

    failures = status.get("failures") or []
    if failures:
        degraded.append(
            f"有账户初始化失败：{failures}——它们的持仓**读不到**，"
            "并不代表这些账户里没有仓位"
        )

    return {"ok": True, "reason": "", "accounts": accounts, "status": status,
            "manual_account": manual_name, "degraded": degraded}


def add_position(code: str, name: str = "", price: float = 0.0,
                 quantity: float = 0.0) -> Dict[str, Any]:
    """在「手动」账户新增持仓（用户手填的真实仓位）。"""
    try:
        result = _pf().add_manual_position(code, name, price, quantity)
    except Exception as e:
        return {"ok": False, "reason": f"写入失败（{type(e).__name__}: {e}）"}
    if result.get("ok"):
        _invalidate_focus_cache()
    return result


def update_position(position_id: str, **fields) -> Dict[str, Any]:
    """修改「手动」账户的一个持仓。"""
    try:
        result = _pf().update_manual_position(position_id, **fields)
    except Exception as e:
        return {"ok": False, "reason": f"修改失败（{type(e).__name__}: {e}）"}
    if result.get("ok"):
        _invalidate_focus_cache()
    return result


def remove_position(position_id: str, exit_price: float = 0.0) -> Dict[str, Any]:
    """移除「手动」账户的一个持仓（软删除，保留历史）。"""
    try:
        result = _pf().remove_manual_position(position_id, exit_price)
    except Exception as e:
        return {"ok": False, "reason": f"删除失败（{type(e).__name__}: {e}）"}
    if result.get("ok"):
        _invalidate_focus_cache()
    return result


# ── ③ 自选 ──────────────────────────────────────────────────────────────
#
# 「自选」= ``naja_watchlist`` 的 ``stocks`` 键（用户在看、但还没买的票）。
# 与「持仓」并列而不是合并：一个是"我的钱"，一个是"我在看的"，混在一起
# 会让前者被后者稀释（news/digest.py 的分组口径也是这么分开的）。

def list_watchlist() -> Dict[str, Any]:
    """列出自选股（纯 dict 列表）。读不到就如实报错，不兜底造空列表糊弄。"""
    try:
        items = _pf().list_watchlist_items()
    except Exception as e:
        return {"ok": False, "reason": f"自选读取失败（{type(e).__name__}: {e}）",
                "items": [], "count": 0}
    return {"ok": True, "reason": "", "items": items, "count": len(items)}


def add_watchlist(code: str, name: str = "") -> Dict[str, Any]:
    """新增自选。已存在则拒绝，不覆盖。"""
    try:
        result = _pf().add_watchlist_item(code, name)
    except Exception as e:
        return {"ok": False, "reason": f"写入失败（{type(e).__name__}: {e}）"}
    if result.get("ok"):
        _invalidate_focus_cache()
    return result


def update_watchlist(code: str, name: str = "") -> Dict[str, Any]:
    """修改自选的展示名。"""
    try:
        result = _pf().update_watchlist_item(code, name)
    except Exception as e:
        return {"ok": False, "reason": f"修改失败（{type(e).__name__}: {e}）"}
    if result.get("ok"):
        _invalidate_focus_cache()
    return result


def remove_watchlist(code: str) -> Dict[str, Any]:
    """移除自选。"""
    try:
        result = _pf().remove_watchlist_item(code)
    except Exception as e:
        return {"ok": False, "reason": f"删除失败（{type(e).__name__}: {e}）"}
    if result.get("ok"):
        _invalidate_focus_cache()
    return result


# ── ④ 推导 ──────────────────────────────────────────────────────────────

def derive_preview(max_topics: int = 8) -> Dict[str, Any]:
    """只看不写：从当前持仓推导候选主题。"""
    from deva.naja.news.focus_advisor import derive_topics
    try:
        return derive_topics(max_topics=max_topics)
    except Exception as e:
        return {"available": False, "reason": f"推导失败（{type(e).__name__}: {e}）",
                "holdings": [], "topics": [], "degraded": [], "sources": []}


def apply_derived(max_topics: int = 8,
                  min_score: Optional[float] = None) -> Dict[str, Any]:
    """推导并**采纳**（写入 ``source="derived"``）。

    先 preview 再 apply：preview 的 ``topics`` 就是采纳输入，
    避免"预览看到的"和"实际写入的"不是同一批。
    """
    from deva.naja.news.focus_advisor import (
        DEFAULT_APPLY_MIN_SCORE, apply_derived_topics,
    )
    preview = derive_preview(max_topics=max_topics)
    if not preview.get("available"):
        return {"ok": False,
                "reason": preview.get("reason") or "推导不可用，未采纳任何主题",
                "applied": [], "skipped": [], "already": [],
                "topics": [], "degraded": preview.get("degraded") or []}

    threshold = DEFAULT_APPLY_MIN_SCORE if min_score is None else float(min_score)
    try:
        result = apply_derived_topics(preview["topics"], min_score=threshold)
    except Exception as e:
        return {"ok": False, "reason": f"采纳失败（{type(e).__name__}: {e}）",
                "applied": [], "skipped": [], "already": [],
                "topics": preview["topics"], "degraded": preview.get("degraded") or []}

    if result.get("applied"):
        _invalidate_focus_cache()
    result["topics"] = preview["topics"]
    result["degraded"] = preview.get("degraded") or []
    return result


def revoke_derived() -> Dict[str, Any]:
    """一键撤销所有推导来的关注主题（手动关注不受影响）。

    撤销会记进「已撤销」名单——自动采纳不会再把这些主题加回来。
    """
    from deva.naja.news.focus_advisor import revoke_derived_topics
    try:
        result = revoke_derived_topics()
    except Exception as e:
        return {"ok": False, "reason": f"撤销失败（{type(e).__name__}: {e}）", "removed": []}
    if result.get("removed"):
        _invalidate_focus_cache()
    return result


# ── 一屏总览（UI 首屏）────────────────────────────────────────────────────

def get_focus_overview(max_topics: int = 8) -> Dict[str, Any]:
    """一次拿齐：主题 + 持仓 + 自选 + 推导候选。任一子块失败不影响其它块。"""
    return {
        "topics": list_topics(),
        "positions": list_positions(),
        "watchlist": list_watchlist(),
        "derived": derive_preview(max_topics=max_topics),
    }


__all__ = [
    "list_topics", "add_topic", "update_topic", "remove_topic",
    "list_positions", "add_position", "update_position", "remove_position",
    "list_watchlist", "add_watchlist", "update_watchlist", "remove_watchlist",
    "derive_preview", "apply_derived", "revoke_derived", "get_focus_overview",
    "SOURCE_DERIVED", "SOURCE_USER",
]
