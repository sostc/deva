"""Propagation 组件 —— 全球流动性传播网络

2026-10-19 重排：空态从两块 230px 卡片压成一行；删掉「节点变化 → 沿边传播 →
验证结果 → 动态调权」这类模块说明行。

预测闭环不再在这里重复渲染 —— 它与「流动性预测闭环」卡片读的是同一份
`get_liquidity_stats()`，同一批数字出现两次只会让人怀疑哪个才是真的。
"""

import html

from pywebio.output import put_html

from .layout import card, empty_line, report_empty


_MARKET_LEVEL_COLORS = {
    "critical": "#ef4444",
    "high": "#f97316",
    "medium": "#eab308",
    "low": "#22c55e",
    "dormant": "#64748b",
}


def render_propagation(ui):
    has_data = False
    propagation_engine = None
    structure = None
    resonance_signals = None

    try:
        newsmind = getattr(ui.engine, '_news_mind', None)
        if newsmind:
            propagation_engine = getattr(newsmind, 'propagation_engine', None)
    except Exception:
        pass

    if propagation_engine:
        try:
            structure = propagation_engine.get_liquidity_structure()
            if "error" not in structure:
                has_data = len(structure.get("active_markets", [])) > 0
            resonance_signals = propagation_engine.get_resonance_signals()
            if resonance_signals:
                has_data = True
        except Exception:
            pass

    active_markets_count = 0
    edges_count = 0
    if structure and "error" not in structure:
        active_markets_count = len(structure.get("active_markets", []))
        edges_count = len(structure.get("edges", {}))

    meta = f"{active_markets_count} 个活跃市场 · {edges_count} 条传播路径"

    if not propagation_engine:
        report_empty("🌐", "全球流动性传播网络", "传播引擎未就绪", "等待系统初始化")
        return

    if not has_data:
        report_empty("🌐", "全球流动性传播网络", "暂无活跃市场变化", "监控中")
        return

    sections = []

    active_markets = structure.get("active_markets", []) if structure else []
    markets = structure.get("markets", {}) if structure else {}
    edges = structure.get("edges", {}) if structure else {}

    if active_markets:
        chips = ""
        for market_id in active_markets[:8]:
            m_info = markets.get(market_id, {})
            color = _MARKET_LEVEL_COLORS.get(m_info.get("attention_level", "unknown"), "#64748b")
            chips += f"""
            <span style="display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
                         background: {color}1f; border: 1px solid {color}4d; border-radius: 6px;
                         font-size: 11px; color: #cbd5e1; margin: 0 5px 5px 0;">
                <span style="width: 7px; height: 7px; border-radius: 50%; background: {color};"></span>
                {html.escape(str(m_info.get("name", market_id)))}
                <span style="color: {color};">{m_info.get('attention_score', 0):.2f}</span>
            </span>
            """
        sections.append(
            f'<div><div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">活跃市场</div>{chips}</div>'
        )

    if edges:
        rows = ""
        for _key, e_info in sorted(edges.items(), key=lambda x: -x[1].get("current_weight", 0))[:5]:
            weight = e_info.get("current_weight", 0)
            weight_color = "#10b981" if weight > 0.7 else ("#eab308" if weight > 0.4 else "#64748b")
            rows += f"""
            <div style="display: flex; align-items: center; gap: 8px; padding: 5px 9px;
                        background: rgba(255,255,255,.02); border-radius: 6px; margin-bottom: 4px;
                        font-size: 11px;">
                <span style="color: #10b981;">{html.escape(str(e_info.get('from_market', '')))}</span>
                <span style="color: #475569;">→</span>
                <span style="color: #f97316;">{html.escape(str(e_info.get('to_market', '')))}</span>
                <span style="color: {weight_color}; margin-left: auto;">强度 {weight:.2f}</span>
                <span style="color: #64748b;">置信 {e_info.get('confidence', 0):.0%}</span>
                <span style="color: #64748b;">延迟 {e_info.get('delay_hours', 0):.0f}h</span>
            </div>
            """
        sections.append(
            f'<div style="margin-top: 10px;"><div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">活跃传播路径</div>{rows}</div>'
        )

    if resonance_signals:
        rows = ""
        for sig in resonance_signals[:3]:
            change = sig.get("change", 0)
            change_color = "#10b981" if change > 0 else "#ef4444"
            rows += f"""
            <div style="display: flex; justify-content: space-between; gap: 8px; padding: 4px 8px;
                        background: rgba(255,255,255,.02); border-radius: 4px; margin-bottom: 3px; font-size: 11px;">
                <span style="color: #cbd5e1;">{html.escape(str(sig.get("name", "")))}</span>
                <span style="color: {change_color};">{change:+.2f}%</span>
                <span style="color: #64748b;">注意力 {sig.get('attention_score', 0):.2f}</span>
            </div>
            """
        sections.append(
            f'<div style="margin-top: 10px;"><div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">共振信号</div>{rows}</div>'
        )

    put_html(card(
        title="全球流动性传播网络",
        icon="🌐",
        meta=meta,
        body="".join(sections) or empty_line("暂无明细"),
    ))
