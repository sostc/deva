"""Naja 管理页公共样式。"""

from datetime import datetime
from html import escape
from typing import Iterable, Optional


_BASE_ADMIN_CSS = """
.pywebio-btn {
    border-radius: 6px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
    border: 1px solid transparent !important;
}
.pywebio-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}
.btn-primary, .pywebio-btn-primary {
    background: #5c8dd6 !important;
    color: white !important;
    border-color: #4a7bc4 !important;
}
.btn-primary:hover, .pywebio-btn-primary:hover {
    background: #4a7bc4 !important;
}
.btn-success {
    background: #5cb85c !important;
    color: white !important;
    border-color: #4cae4c !important;
}
.btn-success:hover {
    background: #4cae4c !important;
}
.btn-danger {
    background: #d9534f !important;
    color: white !important;
    border-color: #c9302c !important;
}
.btn-danger:hover {
    background: #c9302c !important;
}
.btn-warning {
    background: #f0ad4e !important;
    color: white !important;
    border-color: #ec971f !important;
}
.btn-warning:hover {
    background: #ec971f !important;
}
.btn-info {
    background: #5bc0de !important;
    color: white !important;
    border-color: #46b8da !important;
}
.btn-info:hover {
    background: #46b8da !important;
}
.btn-default {
    background: #f8f9fa !important;
    color: #495057 !important;
    border-color: #dee2e6 !important;
}
.btn-default:hover {
    background: #e9ecef !important;
}
.pywebio-btn-group {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 8px !important;
}
.pywebio-btn-group .pywebio-btn {
    margin: 0 !important;
}
.pywebio-btn-sm {
    padding: 4px 12px !important;
    font-size: 12px !important;
}
.pywebio-table .pywebio-btn {
    padding: 3px 10px !important;
    font-size: 12px !important;
}
"""

_COMPACT_TABLE_CSS = """
.pywebio-table tbody tr { height: 48px; max-height: 48px; }
.pywebio-table tbody td { vertical-align: middle; padding: 8px 12px; }
.pywebio-table tbody td > div { max-height: 40px; overflow: hidden; }
"""

_CATEGORY_TABS_CSS = """
.category-tabs { margin-bottom: 16px; }
.category-tabs .pywebio-btn-group { display: flex; flex-wrap: wrap; gap: 8px; }
.category-tabs button {
    border-radius: 20px !important;
    padding: 6px 16px !important;
    font-size: 13px !important;
    transition: all 0.2s ease;
}
.category-tabs button:hover { transform: translateY(-1px); }
.category-tabs button.active {
    background: linear-gradient(135deg, #667eea, #764ba2) !important;
    color: white !important;
}
"""


def apply_strategy_like_styles(
    ctx: dict,
    scope: Optional[str] = None,
    *,
    include_compact_table: bool = False,
    include_category_tabs: bool = False,
) -> None:
    """注入与策略页一致的管理样式。"""
    css_parts = [_BASE_ADMIN_CSS]
    if include_compact_table:
        css_parts.append(_COMPACT_TABLE_CSS)
    if include_category_tabs:
        css_parts.append(_CATEGORY_TABS_CSS)

    kwargs = {"scope": scope} if scope else {}
    ctx["put_html"](f"<style>{''.join(css_parts)}</style>", **kwargs)


def render_stats_cards(cards: Iterable[dict]) -> str:
    """渲染统一风格统计卡片。"""
    card_html = []
    for card in cards:
        label = escape(str(card.get("label", "")))
        value = escape(str(card.get("value", "0")))
        gradient = card.get("gradient", "linear-gradient(135deg,#667eea,#764ba2)")
        shadow = card.get("shadow", "rgba(102,126,234,0.3)")
        card_html.append(
            f"""
            <div style="flex:1;min-width:140px;background:{gradient};padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px {shadow};">
                <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">{label}</div>
                <div style="font-size:32px;font-weight:700;">{value}</div>
            </div>
            """
        )

    return f'<div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:24px;">{"".join(card_html)}</div>'


def render_empty_state(message: str) -> str:
    """渲染统一空状态。"""
    return (
        '<div style="padding:40px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">'
        f"{escape(message)}"
        "</div>"
    )


def format_timestamp(ts: float, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化时间戳为可读字符串

    参数:
        ts: Unix时间戳
        fmt: 时间格式字符串，默认为完整日期时间格式

    返回:
        格式化后的时间字符串，如果ts为空则返回"-"
    """
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime(fmt)


def render_status_badge(is_running: bool) -> str:
    """渲染运行状态徽章

    参数:
        is_running: 是否运行中

    返回:
        HTML格式的状态徽章字符串
    """
    if is_running:
        return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#e8f5e9;color:#2e7d32;">● 运行中</span>'
    return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#f5f5f5;color:#757575;">○ 已停止</span>'


def render_detail_section(title: str) -> str:
    """渲染详情部分的标题分隔线

    参数:
        title: 部分标题

    返回:
        HTML格式的分隔线字符串
    """
    return f"""
    <div style="margin:20px 0 12px 0;padding-bottom:8px;border-bottom:2px solid #e0e0e0;">
        <span style="font-size:15px;font-weight:600;color:#333;">{title}</span>
    </div>
    """
