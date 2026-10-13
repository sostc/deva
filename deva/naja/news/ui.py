"""
关注管理页面（``/focusadmin``）

═══════════════════════════════════════════════════════════════════════════
页面结构（自上而下四块）
═══════════════════════════════════════════════════════════════════════════

    ① 持仓      按账户分组；「手动」账户可增删改（其余账户只读）
    ② 自选      在看、还没买的票；增删改（写 ``naja_watchlist.stocks``）
    ③ 关注主题   增删改查；手动 / 推导来源分开显示，推导的能一键撤销
    ④ 推导候选   从持仓推出「该关注什么」，可预览、可采纳

═══════════════════════════════════════════════════════════════════════════
实现约定
═══════════════════════════════════════════════════════════════════════════

* **每次 ``put_html`` 都传完整闭合的片段**——PyWebIO 把每次调用当独立 DOM
  片段插入，跨调用拆标签会被浏览器自动补闭合，容器变空壳、布局全乱，
  而且不抛异常（2026-10-12 在 /health 上踩过）。
* 所有数据来自 ``news/focus_admin.py``，UI 层**不做任何业务判断**，
  只负责显示 ``{"ok": False, "reason": ...}``。
* 写操作后重绘整块 scope，不做局部 patch。
"""

from __future__ import annotations

import html as _html
import logging
from typing import Any, Dict, List

from pywebio.output import (
    clear, put_buttons, put_html, put_scope, put_table, use_scope,
)

log = logging.getLogger(__name__)

SCOPE = "focus_admin_root"

_CARD = ("background:#fff;border:1px solid #e2e8f0;border-radius:10px;"
         "padding:14px 16px;margin-bottom:14px;")
_TITLE = "font-size:14px;font-weight:600;color:#0f172a;margin:0 0 10px;"
_MUTED = "font-size:12px;color:#64748b;"
_TH = ("padding:8px 10px;text-align:left;font-size:12px;color:#475569;"
       "background:#f8fafc;border-bottom:1px solid #e2e8f0;font-weight:600;")
_TD = "padding:8px 10px;font-size:12px;color:#1e293b;border-bottom:1px solid #f1f5f9;"


def _esc(value: Any) -> str:
    return _html.escape(str(value if value is not None else ""))


def _fmt(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return _esc(value)


# ── 各块的 HTML 片段（每次都是完整闭合片段）────────────────────────────

def _stats_html(positions: Dict[str, Any], topics: Dict[str, Any],
                watchlist: Dict[str, Any], derived: Dict[str, Any]) -> str:
    accounts = positions.get("accounts") or []
    total_pos = sum(int(a.get("position_count") or 0) for a in accounts)
    manual = next((a for a in accounts if a.get("kind") == "manual"), None)
    manual_n = int((manual or {}).get("position_count") or 0)
    n_topic = len(topics.get("topics") or [])
    n_watch = int(watchlist.get("count") or 0)
    n_derived = len(derived.get("topics") or [])

    def card(label: str, value: Any, color: str) -> str:
        return (
            f'<div style="flex:1;min-width:110px;background:#fff;border:1px solid #e2e8f0;'
            f'border-radius:10px;padding:12px 14px;">'
            f'<div style="font-size:20px;font-weight:600;color:{color};">{_esc(value)}</div>'
            f'<div style="font-size:11px;color:#64748b;margin-top:2px;">{_esc(label)}</div></div>'
        )

    return (
        '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;">'
        + card("持仓总数", total_pos, "#1d4ed8")
        + card("手动仓位", manual_n, "#0f766e")
        + card("自选", n_watch, "#0891b2")
        + card("关注主题", n_topic, "#7c3aed")
        + card("推导候选", n_derived, "#b45309")
        + "</div>"
    )


def _positions_html(data: Dict[str, Any]) -> str:
    if not data.get("ok"):
        return (f'<div style="{_CARD}"><div style="{_TITLE}">持仓</div>'
                f'<div style="{_MUTED}">读取失败：{_esc(data.get("reason"))}</div></div>')

    accounts = data.get("accounts") or []
    if not accounts:
        body = f'<div style="{_MUTED}">没有任何账户</div>'
    else:
        blocks = []
        for acc in accounts:
            kind = acc.get("kind")
            badge = ("手动" if kind == "manual" else "券商")
            badge_color = "#0f766e" if kind == "manual" else "#475569"
            rows = "".join(
                f"<tr>"
                f'<td style="{_TD}">{_esc(p.get("stock_code"))}</td>'
                f'<td style="{_TD}">{_esc(p.get("stock_name"))}</td>'
                f'<td style="{_TD}">{_fmt(p.get("quantity"), 0)}</td>'
                f'<td style="{_TD}">{_fmt(p.get("entry_price"))}</td>'
                f'<td style="{_TD}">{_fmt(p.get("current_price"))}</td>'
                f'<td style="{_TD}">{_fmt(p.get("return_pct"))}%</td>'
                f"</tr>"
                for p in (acc.get("positions") or [])
            )
            table = (
                f'<table style="width:100%;border-collapse:collapse;margin-top:8px;">'
                f'<tr><th style="{_TH}">代码</th><th style="{_TH}">名称</th>'
                f'<th style="{_TH}">数量</th><th style="{_TH}">成本</th>'
                f'<th style="{_TH}">现价</th><th style="{_TH}">收益率</th></tr>'
                f"{rows}</table>"
                if rows else f'<div style="{_MUTED}margin-top:6px;">（空）</div>'
            )
            blocks.append(
                f'<div style="border:1px solid #e2e8f0;border-radius:8px;'
                f'padding:10px 12px;margin-bottom:8px;">'
                f'<div style="display:flex;justify-content:space-between;">'
                f'<div><b style="font-size:13px;color:#0f172a;">{_esc(acc.get("name"))}</b>'
                f'<span style="margin-left:8px;font-size:10px;color:{badge_color};'
                f'background:{badge_color}14;border:1px solid {badge_color}44;'
                f'border-radius:8px;padding:1px 6px;">{badge}</span></div>'
                f'<div style="{_MUTED}">{int(acc.get("position_count") or 0)} 个持仓</div>'
                f"</div>{table}</div>"
            )
        body = "".join(blocks)

    degraded = data.get("degraded") or []
    warn = ""
    if degraded:
        items = "".join(f"<li>{_esc(d)}</li>" for d in degraded)
        warn = (
            f'<div style="margin-top:10px;background:#fffbeb;border:1px solid #fde68a;'
            f'border-radius:8px;padding:8px 12px;font-size:11px;color:#92400e;">'
            f"<b>⚠️ 注意</b><ul style=\"margin:4px 0 0;padding-left:18px;\">{items}</ul></div>"
        )

    return (f'<div style="{_CARD}">'
            f'<div style="{_TITLE}">① 持仓（手动账户可增删改）</div>'
            f"{body}{warn}</div>")


def _watchlist_html(data: Dict[str, Any]) -> str:
    if not data.get("ok"):
        return (f'<div style="{_CARD}"><div style="{_TITLE}">自选</div>'
                f'<div style="{_MUTED}">读取失败：{_esc(data.get("reason"))}</div></div>')

    items = data.get("items") or []
    if items:
        rows = "".join(
            f"<tr>"
            f'<td style="{_TD}">{_esc(it.get("code"))}</td>'
            f'<td style="{_TD}">{_esc(it.get("name"))}</td>'
            f'<td style="{_TD}">{_esc(it.get("bucket"))}</td>'
            f"</tr>"
            for it in items
        )
        body = (
            f'<table style="width:100%;border-collapse:collapse;">'
            f'<tr><th style="{_TH}">代码</th><th style="{_TH}">名称</th>'
            f'<th style="{_TH}">来源键</th></tr>{rows}</table>'
        )
    else:
        body = f'<div style="{_MUTED}">（空）—— 在看、但还没买的票放这里</div>'

    return (f'<div style="{_CARD}">'
            f'<div style="{_TITLE}">② 自选（在看、还没买的票）</div>'
            f"{body}</div>")


def _topics_html(data: Dict[str, Any]) -> str:
    if not data.get("ok"):
        return (f'<div style="{_CARD}"><div style="{_TITLE}">关注主题</div>'
                f'<div style="{_MUTED}">读取失败：{_esc(data.get("reason"))}</div></div>')

    def section(title: str, rows: List[Dict[str, Any]], color: str) -> str:
        if not rows:
            return (f'<div style="margin-top:10px;"><b style="font-size:12px;color:{color};">'
                    f"{_esc(title)}</b><div style=\"{_MUTED}margin-top:4px;\">（空）</div></div>")
        items = "".join(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'border-bottom:1px solid #f1f5f9;padding:5px 0;">'
            f'<div><span style="font-size:12px;color:#0f172a;">{_esc(r.get("topic"))}</span>'
            f'<span style="margin-left:8px;font-size:10px;color:#64748b;">'
            f'优先级 {_fmt(r.get("priority"))}</span></div>'
            f'<span style="font-size:10px;color:{color};">{_esc(r.get("source"))}</span></div>'
            for r in rows
        )
        return (f'<div style="margin-top:10px;"><b style="font-size:12px;color:{color};">'
                f"{_esc(title)}（{len(rows)}）</b>{items}</div>")

    return (f'<div style="{_CARD}">'
            f'<div style="{_TITLE}">③ 关注主题</div>'
            + section("手动关注", data.get("manual") or [], "#7c3aed")
            + section("推导关注（可一键撤销）", data.get("derived") or [], "#b45309")
            + "</div>")


def _derived_html(data: Dict[str, Any]) -> str:
    if not data.get("available"):
        return (f'<div style="{_CARD}"><div style="{_TITLE}">④ 推导候选</div>'
                f'<div style="{_MUTED}">{_esc(data.get("reason") or "不可用")}</div></div>')

    holdings = "、".join(
        f'{_esc(h.get("name"))}({_esc(h.get("code"))})' for h in (data.get("holdings") or [])
    )
    rows = "".join(
        f"<tr>"
        f'<td style="{_TD}"><b>{_esc(t.get("topic"))}</b></td>'
        f'<td style="{_TD}">{_fmt(t.get("score"))}</td>'
        f'<td style="{_TD}">{_esc("/".join(t.get("relation_labels") or []))}</td>'
        f'<td style="{_TD}">{_esc("、".join(t.get("from_holdings") or []))}</td>'
        f'<td style="{_TD};color:#64748b;">{_esc((t.get("evidence") or [""])[0])}</td>'
        f"</tr>"
        for t in (data.get("topics") or [])
    )
    table = (
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<tr><th style="{_TH}">主题</th><th style="{_TH}">得分</th>'
        f'<th style="{_TH}">关系</th><th style="{_TH}">来自持仓</th>'
        f'<th style="{_TH}">依据</th></tr>{rows}</table>'
        if rows else f'<div style="{_MUTED}">没有推导出候选主题</div>'
    )

    degraded = data.get("degraded") or []
    warn = ""
    if degraded:
        items = "".join(f"<li>{_esc(d)}</li>" for d in degraded)
        warn = (f'<div style="margin-top:8px;background:#fffbeb;border:1px solid #fde68a;'
                f'border-radius:8px;padding:8px 12px;font-size:11px;color:#92400e;">'
                f'<b>⚠️ 推导降级留痕</b><ul style="margin:4px 0 0;padding-left:18px;">'
                f"{items}</ul></div>")

    return (f'<div style="{_CARD}">'
            f'<div style="{_TITLE}">④ 推导候选（依据持仓推导「该关注什么」）</div>'
            f'<div style="{_MUTED}margin-bottom:8px;">依据持仓：{holdings or "无"}</div>'
            f"{table}{warn}</div>")


# ── 主渲染 ──────────────────────────────────────────────────────────────

def render_focus_admin(ctx: Dict[str, Any]) -> None:
    """渲染关注管理页（同步；按钮回调里用 run_async 触发异步操作）。"""
    from deva.naja.news import focus_admin as fa

    clear(SCOPE)
    with use_scope(SCOPE):
        try:
            overview = fa.get_focus_overview()
        except Exception as e:
            put_html(
                f'<div style="{_CARD}"><b style="color:#b91c1c;">'
                f"读取失败（{_esc(type(e).__name__)}）：{_esc(e)}</b></div>"
            )
            return

        topics = overview.get("topics") or {}
        positions = overview.get("positions") or {}
        watchlist = overview.get("watchlist") or {}
        derived = overview.get("derived") or {}

        put_html(_stats_html(positions, topics, watchlist, derived))

        # ① 持仓 + 手动账户操作按钮
        put_html(_positions_html(positions))
        put_scope("focus_pos_actions")
        with use_scope("focus_pos_actions"):
            put_buttons(
                [{"label": "➕ 手动加仓", "value": "add_pos", "color": "primary"}],
                onclick=lambda v: _dispatch(v, ctx), small=True,
            )

        # ② 自选 + 操作按钮（在看、还没买的票）
        put_html(_watchlist_html(watchlist))
        put_scope("focus_watch_actions")
        with use_scope("focus_watch_actions"):
            put_buttons(
                [
                    {"label": "➕ 新增自选", "value": "add_watch", "color": "primary"},
                    {"label": "✏️ 改名称", "value": "edit_watch", "color": "info"},
                    {"label": "🗑️ 删除自选", "value": "del_watch", "color": "danger"},
                ],
                onclick=lambda v: _dispatch(v, ctx), small=True,
            )

        # ③ 主题 + 操作按钮
        put_html(_topics_html(topics))
        put_scope("focus_topic_actions")
        with use_scope("focus_topic_actions"):
            put_buttons(
                [
                    {"label": "➕ 新增主题", "value": "add_topic", "color": "primary"},
                    {"label": "✏️ 改优先级", "value": "edit_topic", "color": "info"},
                    {"label": "🗑️ 删除主题", "value": "del_topic", "color": "danger"},
                ],
                onclick=lambda v: _dispatch(v, ctx), small=True,
            )

        # ④ 推导候选 + 操作按钮
        put_html(_derived_html(derived))
        put_scope("focus_derived_actions")
        with use_scope("focus_derived_actions"):
            put_buttons(
                [
                    {"label": "🔄 重新推导", "value": "refresh", "color": "secondary"},
                    {"label": "✅ 推导并采纳", "value": "derive_apply", "color": "success"},
                    {"label": "↩️ 撤销推导", "value": "derive_revoke", "color": "warning"},
                ],
                onclick=lambda v: _dispatch(v, ctx), small=True,
            )


# ── 交互处理 ────────────────────────────────────────────────────────────

def _dispatch(action: str, ctx: Dict[str, Any]) -> None:
    """按钮回调（同步入口）→ 异步处理。"""
    from pywebio.session import run_async
    run_async(_handle(action, ctx))


async def _handle(action: str, ctx: Dict[str, Any]) -> None:
    from deva.naja.news import focus_admin as fa

    toast = ctx["toast"]

    if action == "refresh":
        render_focus_admin(ctx)
        return

    if action == "add_topic":
        form = await ctx["input_group"]("新增关注主题", [
            ctx["input"]("主题名", name="name", required=True,
                         placeholder="如：半导体 / HBM / 光模块"),
            ctx["input"]("优先级 (0~1)", name="priority", type=ctx["NUMBER"],
                         value=0.7),
        ])
        result = fa.add_topic(form["name"], form["priority"])
        toast(result.get("reason") or f"已新增「{form['name']}」",
              color="success" if result.get("ok") else "error")

    elif action == "edit_topic":
        naming = await ctx["input_group"]("修改主题优先级", [
            ctx["input"]("主题名（须已存在）", name="name", required=True),
            ctx["input"]("新优先级 (0~1)", name="priority", type=ctx["NUMBER"],
                         value=0.7),
        ])
        result = fa.update_topic(naming["name"], naming["priority"])
        toast(result.get("reason") or "已更新", color="success" if result.get("ok") else "error")

    elif action == "del_topic":
        naming = await ctx["input_group"]("删除关注主题", [
            ctx["input"]("主题名（须已存在）", name="name", required=True),
        ])
        result = fa.remove_topic(naming["name"])
        toast(result.get("reason") or f"已删除「{naming['name']}」",
              color="success" if result.get("ok") else "error")

    elif action == "add_pos":
        form = await ctx["input_group"]("手动加仓（写入「手动」账户）", [
            ctx["input"]("股票代码", name="code", required=True, placeholder="如 nvda"),
            ctx["input"]("名称", name="name", placeholder="如 英伟达"),
            ctx["input"]("成本价", name="price", type=ctx["NUMBER"], value=0.0),
            ctx["input"]("数量", name="quantity", type=ctx["NUMBER"], required=True),
        ])
        result = fa.add_position(form["code"], form.get("name") or "", form["price"] or 0.0,
                                 form["quantity"] or 0.0)
        toast(result.get("reason") or "已加入手动账户",
              color="success" if result.get("ok") else "error")

    elif action == "edit_pos":
        form = await ctx["input_group"]("修改手动仓位", [
            ctx["input"]("position_id", name="pid", required=True,
                         placeholder="从持仓行末尾复制"),
            ctx["input"]("新数量（留空不改）", name="quantity", type=ctx["NUMBER"]),
            ctx["input"]("新成本价（留空不改）", name="entry_price", type=ctx["NUMBER"]),
        ])
        fields = {}
        if form.get("quantity") not in (None, ""):
            fields["quantity"] = form["quantity"]
        if form.get("entry_price") not in (None, ""):
            fields["entry_price"] = form["entry_price"]
        if not fields:
            toast("没有填写要修改的字段", color="warn")
        else:
            result = fa.update_position(form["pid"], **fields)
            toast(result.get("reason") or "已修改", color="success" if result.get("ok") else "error")

    elif action == "del_pos":
        form = await ctx["input_group"]("删除手动仓位", [
            ctx["input"]("position_id", name="pid", required=True,
                         placeholder="从持仓行末尾复制"),
        ])
        result = fa.remove_position(form["pid"])
        toast(result.get("reason") or "已移除（保留历史）",
              color="success" if result.get("ok") else "error")

    elif action == "add_watch":
        form = await ctx["input_group"]("新增自选（在看、还没买的票）", [
            ctx["input"]("代码 / 名称", name="code", required=True,
                         placeholder="如 nvda / 宁德时代"),
            ctx["input"]("展示名", name="name", placeholder="留空则用代码"),
        ])
        result = fa.add_watchlist(form["code"], form.get("name") or "")
        toast(result.get("reason") or f"已加入自选「{form['code']}」",
              color="success" if result.get("ok") else "error")

    elif action == "edit_watch":
        form = await ctx["input_group"]("修改自选展示名", [
            ctx["input"]("代码 / 名称（须已存在）", name="code", required=True),
            ctx["input"]("新展示名", name="name", required=True),
        ])
        result = fa.update_watchlist(form["code"], form["name"])
        toast(result.get("reason") or "已更新", color="success" if result.get("ok") else "error")

    elif action == "del_watch":
        form = await ctx["input_group"]("删除自选", [
            ctx["input"]("代码 / 名称（须已存在）", name="code", required=True),
        ])
        result = fa.remove_watchlist(form["code"])
        toast(result.get("reason") or f"已删除「{form['code']}」",
              color="success" if result.get("ok") else "error")

    elif action == "derive_apply":
        result = fa.apply_derived()
        if result.get("ok"):
            applied = result.get("applied") or []
            already = result.get("already") or []
            msg = f"已采纳 {len(applied)} 个主题"
            if applied:
                msg += f"：{'、'.join(applied)}"
            if already:
                msg += f"（{len(already)} 个已关注，未覆盖）"
            toast(msg, color="success" if applied else "warn")
        else:
            toast(result.get("reason") or "采纳失败", color="error")

    elif action == "derive_revoke":
        result = fa.revoke_derived()
        if result.get("ok"):
            removed = result.get("removed") or []
            toast(f"已撤销 {len(removed)} 个推导主题", color="success")
        else:
            toast(result.get("reason") or "撤销失败", color="error")

    else:
        toast(f"未知操作：{action}", color="error")
        return

    render_focus_admin(ctx)


__all__ = ["render_focus_admin", "SCOPE"]
