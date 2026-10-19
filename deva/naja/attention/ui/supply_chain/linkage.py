"""供应链-叙事联动面板（``/supplychain`` 页）

═══════════════════════════════════════════════════════════════════════════
为什么从认知页搬到这里
═══════════════════════════════════════════════════════════════════════════

``/supplychain`` 页原本只有**静态**知识图谱（节点/边统计、热门题材映射、
英伟达关系图 SVG、A 股全景），缺的是「**叙事**这一侧现在发生了什么」——
也就是 ``NarrativeSupplyChainLinker`` 的运行时产出：最热叙事、最近风险事件。

而这块内容此前挂在认知页「深度分析」里（172px），属于典型的**放错家**：
它是供应链视图的一半，不是认知层的一个结论。搬回来后这页才完整
（静态图谱 + 动态叙事联动），认知页也少一块重复的领域视图。

═══════════════════════════════════════════════════════════════════════════
❗配色：深色卡
═══════════════════════════════════════════════════════════════════════════

本页的卡片本来就是深色的（``graph.py`` 用 ``#1e293b`` 底 + ``#f1f5f9`` 字），
所以这里沿用同一套，不另起一摊。站点正文虽是白底，但整页卡片都是深色，
跟着邻居走才不会突兀。

═══════════════════════════════════════════════════════════════════════════
返回片段而不是直接 put_html
═══════════════════════════════════════════════════════════════════════════

``render_supply_chain_knowledge_graph_page()`` 把整页拼成一个字符串后
**一次性** ``put_html``（一份 HTML 绝不能拆多次输出）。所以这里只负责
造片段，由调用方决定放在哪、什么时候输出。
"""

from __future__ import annotations

import html
import logging
from datetime import datetime

log = logging.getLogger(__name__)

_CARD = "background:#1e293b;border-radius:12px;padding:20px;margin:12px 0;"
_TITLE = "margin:0 0 14px 0;color:#f1f5f9;font-size:16px;"
_SUB = "font-size:11px;color:#94a3b8;margin-bottom:7px;"
_MUTED = "font-size:11px;color:#64748b;"


def _get_linker():
    from deva.naja.cognition import get_supply_chain_linker

    return get_supply_chain_linker()


def build_supply_chain_linkage_html() -> str:
    """返回「🔗 供应链-叙事联动」面板的 HTML 片段（永远有输出）。"""
    hot_narratives = []
    recent_events = []
    summary = {
        "total_narratives": 0,
        "total_stocks_mapped": 0,
        "recent_events_count": 0,
    }
    ok = False
    try:
        linker = _get_linker()
        hot_narratives = linker.get_hot_narratives(8) or []
        recent_events = linker.get_recent_events(5) or []
        summary = linker.get_supply_chain_summary() or summary
        ok = True
    except Exception:
        log.debug("[SupplyChainLinkage] 联动数据不可用（面板按空态渲染）", exc_info=True)

    meta = (
        f"{summary.get('total_narratives', 0)} 叙事 · "
        f"{summary.get('total_stocks_mapped', 0)} 股票 · "
        f"{summary.get('recent_events_count', 0)} 事件"
    )

    if not ok or (not hot_narratives and not recent_events):
        # ❗空态一行即可。原来在认知页是一张 172px 的卡片说「暂无」，
        # 数据没有的时候不应该占半屏。
        return (
            f'<div style="{_CARD}">'
            f'<h3 style="{_TITLE}">🔗 供应链-叙事联动 '
            f'<span style="font-size:11px;color:#64748b;font-weight:400;">{html.escape(meta)}</span>'
            "</h3>"
            f'<div style="{_MUTED}">等待供应链数据 · 需新闻流入且叙事追踪激活后才有映射</div>'
            "</div>"
        )

    hot_html = ""
    for narrative, importance in hot_narratives:
        alpha = 0.2 + min(1.0, float(importance) / 3.0) * 0.6
        hot_html += (
            f'<span style="background:rgba(239,68,68,{alpha:.2f});padding:3px 10px;'
            'border-radius:14px;font-size:11px;color:#fff;margin:0 4px 4px 0;'
            f'display:inline-block;">{html.escape(str(narrative))} '
            f'({float(importance):.1f})</span>'
        )

    events_html = ""
    for event in recent_events[-5:]:
        try:
            time_str = datetime.fromtimestamp(event.timestamp).strftime("%m-%d %H:%M")
        except Exception:
            time_str = "-"
        risk_value = getattr(event.risk_level, "value", str(event.risk_level))
        risk_color = "#ef4444" if risk_value in ("high", "critical") else "#ca8a04"
        events_html += (
            '<div style="background:rgba(255,255,255,0.05);border-radius:6px;'
            f'padding:7px 9px;margin-bottom:5px;border-left:3px solid {risk_color};">'
            '<div style="display:flex;justify-content:space-between;gap:8px;">'
            f'<span style="color:#f1f5f9;font-size:11px;">'
            f"{html.escape(str(event.description))}</span>"
            f'<span style="{_MUTED}flex-shrink:0;">{time_str}</span>'
            "</div>"
            f'<div style="{_MUTED}margin-top:3px;">'
            f"关联 {html.escape(', '.join((event.narratives or [])[:4]))}</div>"
            "</div>"
        )

    return (
        f'<div style="{_CARD}">'
        f'<h3 style="{_TITLE}">🔗 供应链-叙事联动 '
        f'<span style="font-size:11px;color:#64748b;font-weight:400;">{html.escape(meta)}</span>'
        "</h3>"
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;">'
        "<div>"
        f'<div style="{_SUB}">🔥 最热叙事</div>'
        '<div style="max-height:132px;overflow-y:auto;">'
        + (hot_html or f'<span style="{_MUTED}">暂无热度数据</span>')
        + "</div></div>"
        "<div>"
        f'<div style="{_SUB}">⚠️ 最近风险事件</div>'
        '<div style="max-height:132px;overflow-y:auto;">'
        + (events_html or f'<span style="{_MUTED}">暂无风险事件</span>')
        + "</div></div>"
        "</div></div>"
    )


__all__ = ["build_supply_chain_linkage_html"]
