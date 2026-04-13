"""Radar UI 常量 — 时间格式化、事件徽章渲染、交易时段映射"""

from datetime import datetime

from deva.naja.register import SR


def _fmt_time(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _render_event_badge(event_type: str, score: float = 0.5) -> str:
    """渲染事件类型徽章"""
    color_map = {
        "radar_pattern": ("📊", "#2563eb", "rgba(37,99,235,0.1)"),
        "pattern": ("📊", "#2563eb", "rgba(37,99,235,0.1)"),
        "radar_data_distribution_shift": ("📉", "#9333ea", "rgba(147,51,234,0.1)"),
        "drift": ("📉", "#9333ea", "rgba(147,51,234,0.1)"),
        "radar_anomaly": ("⚡", "#dc2626", "rgba(220,38,38,0.1)"),
        "anomaly": ("⚡", "#dc2626", "rgba(220,38,38,0.1)"),
        "radar_block_anomaly": ("🔥", "#ef4444", "rgba(239,68,68,0.1)"),
        "block_anomaly": ("🔥", "#ef4444", "rgba(239,68,68,0.1)"),
        "block_hotspot": ("🔥", "#ef4444", "rgba(239,68,68,0.1)"),
    }

    icon, color, bg = color_map.get(event_type, ("📌", "#6b7280", "rgba(107,114,128,0.1)"))

    if event_type in ("block_anomaly", "radar_block_anomaly"):
        label = "题材联动"
    elif event_type == "block_hotspot":
        label = "题材热点"
    elif event_type == "radar_data_distribution_shift":
        label = "数据漂移"
    elif event_type == "radar_pattern":
        label = "模式"
    elif event_type == "radar_anomaly":
        label = "异常"
    else:
        label = event_type

    score_color = "#f87171" if score > 0.7 else ("#fb923c" if score > 0.5 else "#60a5fa")

    return f'''<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:4px;font-size:12px;font-weight:500;background:{bg};color:{color};">
        {icon} {label}
    </span><span style="font-size:11px;color:{score_color};margin-left:4px;">{score:.2f}</span>'''


# ---------------------------------------------------------------------------
# 交易时段状态
# ---------------------------------------------------------------------------

_PHASE_MAP_CN = {
    "trading": ("A股交易中", "#22c55e"),
    "pre_market": ("A股盘前", "#f59e0b"),
    "lunch": ("A股午休", "#64748b"),
    "post_market": ("A股盘后", "#64748b"),
    "closed": ("A股休市", "#dc2626"),
}

_PHASE_MAP_US = {
    "trading": ("美股交易中", "#22c55e"),
    "pre_market": ("美股盘前", "#f59e0b"),
    "post_market": ("美股盘后", "#64748b"),
    "closed": ("美股休市", "#dc2626"),
}


def get_cn_trading_status() -> tuple:
    """获取A股交易时段状态"""
    try:
        from deva.naja.register import ensure_trading_clocks
        ensure_trading_clocks()
        tc = SR('trading_clock')
        phase = tc.cn_phase
        return _PHASE_MAP_CN.get(phase, ("A股未知", "#64748b"))
    except Exception:
        return ("A股状态未知", "#64748b")


def get_us_trading_status() -> tuple:
    """获取美股交易时段状态"""
    try:
        from deva.naja.register import ensure_trading_clocks
        ensure_trading_clocks()
        tc = SR('trading_clock')
        phase = tc.us_phase
        return _PHASE_MAP_US.get(phase, ("美股未知", "#64748b"))
    except Exception:
        return ("美股状态未知", "#64748b")
