"""首页「全量清单」面板 —— 把 FleetRegistry 里的每一条都摊开给人看

卡片只放结论（运行中 5 / 共 17），但**结论是怎么来的必须能追**。这个面板就是
那个「展开看明细」的地方：每个取数点、每条策略的 来源 / 状态 / 最近成功 /
最近失败 / 节拍 / 备注 一行摆出来。

为什么必须有它：口径一统到全系统之后，「17 个策略」这种数字本身就不再可信
—— 除非能一眼看到这 17 个是谁。数字被质疑时，答案要在这里，不用去翻代码。

❗配色：本面板写在**页面底色**上，而首页 body 实测是白底（rgb(255,255,255)），
所以文字一律用**深色**。曾经把卡片那套近白色（#e2e8f0）直接搬过来，在白底上
几乎看不见 —— 卡片有深色渐变垫底，这里没有。
"""

import html
import time

from deva.naja.infra.observability.fleet_registry import (
    KIND_DATASOURCE, KIND_STRATEGY,
    ST_RUNNING, ST_STOPPED, ST_UNKNOWN, ST_SKIPPED,
    get_fleet_registry,
)

# 白底可读的状态色（比卡片上的亮色深一档）
_STATE_STYLE = {
    ST_RUNNING: ("#16a34a", "运行中"),
    ST_STOPPED: ("#2563eb", "已停止"),
    ST_UNKNOWN: ("#d97706", "未知"),
    ST_SKIPPED: ("#94a3b8", "按设计跳过"),
}
_FALLBACK_STYLE = ("#94a3b8", "未知")

_SOURCE_LABEL = {
    "datasource_mgr": "数据源体系",
    "strategy_mgr": "声明式策略",
    "hotspot": "热点策略",
    "runner": "常驻运行器",
    "probe": "探针",
    "manifest": "声明登记",
}

_BORDER = "#e2e8f0"
_TEXT = "#1e293b"
_MUTED = "#64748b"
_SUB = "#475569"


def _ago(ts) -> str:
    try:
        ts = float(ts or 0)
    except (TypeError, ValueError):
        return "—"
    if ts <= 0:
        return "从未"
    delta = max(0.0, time.time() - ts)
    if delta < 90:
        return "刚刚"
    if delta < 5400:
        return f"{int(delta // 60)} 分钟前"
    if delta < 172800:
        return f"{int(delta // 3600)} 小时前"
    return f"{int(delta // 86400)} 天前"


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _table(cards) -> str:
    if not cards:
        return f'<div style="font-size:12px;color:{_MUTED};padding:6px 0;">（无）</div>'

    rows = []
    for c in cards:
        color, label = _STATE_STYLE.get(c.state, _FALLBACK_STYLE)
        rows.append(
            "<tr>"
            f'<td style="padding:5px 8px;border-bottom:1px solid {_BORDER};'
            f'color:{_TEXT};">{_esc(c.name)}</td>'
            f'<td style="padding:5px 8px;border-bottom:1px solid {_BORDER};color:{_MUTED};'
            f'white-space:nowrap;">{_esc(_SOURCE_LABEL.get(c.source, c.source))}</td>'
            f'<td style="padding:5px 8px;border-bottom:1px solid {_BORDER};color:{color};'
            f'white-space:nowrap;">● {label}</td>'
            f'<td style="padding:5px 8px;border-bottom:1px solid {_BORDER};color:{_SUB};'
            f'white-space:nowrap;">{_ago(c.last_success_ts)}</td>'
            f'<td style="padding:5px 8px;border-bottom:1px solid {_BORDER};color:{_SUB};'
            f'white-space:nowrap;">{_ago(c.last_error_ts)}</td>'
            f'<td style="padding:5px 8px;border-bottom:1px solid {_BORDER};color:{_MUTED};'
            f'white-space:nowrap;">{_esc(c.cadence) or "—"}</td>'
            f'<td style="padding:5px 8px;border-bottom:1px solid {_BORDER};color:{_MUTED};">'
            f'{_esc(c.note) or "—"}</td>'
            "</tr>"
        )
    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:11px;">
        <thead>
            <tr style="text-align:left;color:{_MUTED};">
                <th style="padding:5px 8px;">名称</th>
                <th style="padding:5px 8px;">来源</th>
                <th style="padding:5px 8px;">状态</th>
                <th style="padding:5px 8px;">最近成功</th>
                <th style="padding:5px 8px;">最近失败</th>
                <th style="padding:5px 8px;">节拍</th>
                <th style="padding:5px 8px;">备注</th>
            </tr>
        </thead>
        <tbody>{"".join(rows)}</tbody>
    </table>
    """


def _source_status_line() -> str:
    """采集来源自身的健康。适配器炸了要在这里写明，不许静默。"""
    sources = get_fleet_registry().all_sources()
    if not sources:
        return ""
    bad = [(k, v) for k, v in sources.items() if not v.get("ok")]
    if not bad:
        return (f'<div style="font-size:11px;color:#16a34a;margin:6px 0 2px 2px;">'
                f'采集来源 {len(sources)} 个全部正常</div>')
    parts = "；".join(
        f"{_esc(_SOURCE_LABEL.get(k, k))}：{_esc(v.get('error'))}" for k, v in bad
    )
    return (f'<div style="font-size:11px;color:#dc2626;margin:6px 0 2px 2px;">'
            f'⚠ 采集失败：{parts}</div>')


def render_fleet_panel(ctx: dict):
    """渲染首页的可展开全量清单。"""
    reg = get_fleet_registry()
    ds_cards = reg.snapshot(kind=KIND_DATASOURCE)
    st_cards = reg.snapshot(kind=KIND_STRATEGY)
    refreshed = _ago(reg.last_refresh_ts()) if reg.last_refresh_ts() else "尚未采集"

    ctx["put_html"](f"""
    <details style="margin:12px 0 18px 2px;">
        <summary style="cursor:pointer;font-size:13px;color:{_TEXT};font-weight:600;
                        padding:8px 0;">
            🔍 全量清单 —— 数据源 {len(ds_cards)} 个 · 策略 {len(st_cards)} 个
            <span style="font-size:11px;color:{_MUTED};font-weight:400;">
                （采集于 {refreshed}）
            </span>
        </summary>
        {_source_status_line()}
        <div style="font-size:12px;color:{_TEXT};font-weight:600;margin:10px 0 4px 2px;">
            📡 数据源 / 取数点（{len(ds_cards)}）
        </div>
        {_table(ds_cards)}
        <div style="font-size:12px;color:{_TEXT};font-weight:600;margin:14px 0 4px 2px;">
            📊 策略 / 运行器（{len(st_cards)}）
        </div>
        {_table(st_cards)}
        <div style="font-size:10px;color:{_MUTED};margin:8px 0 0 2px;line-height:1.7;">
            状态四态：● 运行中 · ● 已停止 · ● 未知（读不到状态，<b>绝不当作 0</b>，
            备注里写原因）· ● 按设计跳过（如收盘后行情源）。
            「最近失败」只看时间戳新鲜度，累计错误次数不作当前故障判据。
        </div>
    </details>
    """)


__all__ = ["render_fleet_panel"]
