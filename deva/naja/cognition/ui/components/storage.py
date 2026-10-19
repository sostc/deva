"""Storage 组件 —— 分层记忆

2026-10-19 重排：容量条保留在卡面（这是"记住多少"的直接答案），
衰减参数/强化保护是配置明细，收进折叠块；字号统一到 11px 下限。
"""

import html

from pywebio.output import put_html

from .layout import card, fold


def _fmt_duration(seconds) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:.1f}h"
    if seconds >= 60:
        return f"{int(seconds / 60)}m"
    return f"{int(seconds)}s"


def _layer(label: str, icon: str, size, cap, pct: int, color: str, note: str = "") -> str:
    cap_text = f"/ {cap}" if cap else ""
    note_html = f'<span style="font-size: 11px; color: #64748b;">{note}</span>' if note else ""
    return f"""
    <div style="background: {color}12; border: 1px solid {color}30; border-radius: 8px; padding: 10px 12px;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px;">
            <span style="font-size: 11px; color: {color};">{icon} {label}</span>
            <span style="font-size: 13px; color: #e2e8f0; font-weight: 600;">{size} <span style="font-size: 11px; color: #64748b;">{cap_text}</span></span>
        </div>
        <div style="height: 5px; background: rgba(255,255,255,.08); border-radius: 3px; overflow: hidden;">
            <div style="width: {pct}%; height: 100%; background: {color}; border-radius: 3px;"></div>
        </div>
        {note_html}
    </div>
    """


def render_storage(ui):
    if not ui.engine:
        return

    report = ui.engine.get_memory_report()
    memory_layers = report.get('memory_layers', {})

    short = memory_layers.get('short', {})
    mid = memory_layers.get('mid', {})
    short_size = short.get('size', 0)
    short_cap = short.get('capacity', 1000)
    mid_size = mid.get('size', 0)
    mid_cap = mid.get('capacity', 5000)

    short_pct = min(100, int(short_size / short_cap * 100)) if short_cap else 0
    mid_pct = min(100, int(mid_size / mid_cap * 100)) if mid_cap else 0

    short_color = "#60a5fa"
    mid_color = "#fbbf24"
    if short_pct >= 90:
        short_color = "#f87171"

    body = f"""
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
        {_layer("短期", "⚡", short_size, short_cap, short_pct, short_color,
                "容量已满，新事件正在挤出旧事件" if short_pct >= 90 else "")}
        {_layer("中期", "📦", mid_size, mid_cap, mid_pct, mid_color)}
    </div>
    """

    # ── 衰减参数（配置明细，折叠）──
    try:
        from deva.naja.cognition.memory_manager import MemoryManager
        mm = MemoryManager()

        params = [
            ("短期半衰期", _fmt_duration(getattr(mm, 'short_term_half_life', 300))),
            ("中期半衰期", _fmt_duration(getattr(mm, 'mid_term_half_life', 3600))),
            ("主题半衰期", _fmt_duration(getattr(mm, 'topic_half_life', 1800))),
            ("中期阈值", f"{getattr(mm, 'mid_memory_threshold', 0.7):.0%}"),
            ("强化保护", _fmt_duration(getattr(mm, 'reinforcement_shield', 60))),
            ("归档间隔", _fmt_duration(getattr(mm, 'long_memory_interval', 86400))),
        ]
        cells = "".join(
            f'<div style="background: rgba(255,255,255,.03); border-radius: 6px; padding: 6px 8px; text-align: center;">'
            f'<div style="font-size: 13px; color: #cbd5e1; font-weight: 600;">{value}</div>'
            f'<div style="font-size: 11px; color: #64748b;">{label}</div></div>'
            for label, value in params
        )
        body += fold(
            "衰减参数 & 强化保护",
            f'<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px;">{cells}</div>',
            meta="MemoryManager 配置",
        )
    except Exception:
        pass

    # ── 长期记忆摘要 ──
    long_summary = report.get('long_term_summary', '')
    if long_summary:
        body += fold(
            "长期记忆摘要",
            f"""
            <div style="background: rgba(168,85,247,.05); border-left: 3px solid rgba(168,85,247,.35);
                        padding: 8px 10px; font-size: 11px; color: #c4b5fd; line-height: 1.6;">
                {html.escape(long_summary[:400])}{'…' if len(long_summary) > 400 else ''}
            </div>
            """,
        )

    put_html(card(
        title="记忆存储",
        icon="🧠",
        meta=f"短期 <b>{short_size}</b> · 中期 <b>{mid_size}</b>",
        body=body,
    ))
