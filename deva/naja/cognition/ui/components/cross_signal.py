"""Cross Signal 组件 —— 跨信号共振检测

2026-10-19 重排：
- 原来用「开 div / 关 div」跨多次 put_html 拼一张卡 —— PyWebIO 的 put_html 是
  并列追加，跨调用不会嵌套，所以那个容器其实被浏览器就地闭合了，末尾的
  `</div>` 是孤儿标签。现在合并成一次 put_html。
- 删掉「新闻 × 注意力 / 新闻 × 宏观叙事 / 市场 × 市场 → 三层共振」说明行和三张
  纯解释性卡片（它们描述的是"这个模块做什么"，不是"现在发生了什么"）。
- 共振明细默认折叠，平时只看计数。
"""

import html

from pywebio.output import put_html

from deva.naja.infra.ui.ui_style import format_timestamp

from .layout import card, fold


_RESONANCE_COLORS = {
    "temporal": "#60a5fa",
    "intensity": "#f97316",
    "narrative": "#a855f7",
    "correlation": "#14b8a6",
}

_MARKET_COLORS = {
    "intensity": "#f97316",
    "macro": "#a855f7",
    "cross_market": "#14b8a6",
}


def _stat(label: str, value, color: str, sub: str = "") -> str:
    sub_html = f'<div style="font-size: 11px; color: #64748b;">{sub}</div>' if sub else ""
    return f"""
    <div style="background: {color}14; border: 1px solid {color}2e; padding: 7px 10px;
                border-radius: 8px; text-align: center;">
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 2px;">{label}</div>
        <div style="font-size: 16px; font-weight: 700; color: {color};">{value}</div>
        {sub_html}
    </div>
    """


def render_cross_signal(ui):
    try:
        from ...analysis.cross_signal_analyzer import get_cross_signal_analyzer
        analyzer = get_cross_signal_analyzer()
        if not analyzer:
            return
    except Exception:
        return

    stats = analyzer.get_stats()
    recent_resonances = analyzer.get_recent_resonances(n=8) or []
    high_resonance_blocks = analyzer.get_high_resonance_blocks(threshold=0.7, n=5) or []
    market_resonance_summary = analyzer.get_market_resonance_summary() or {}

    llm_cooldown_remaining = stats.get('llm_cooldown_remaining', 0)
    llm_ready = "🔥 就绪" if analyzer.should_trigger_llm() else f"💤 冷却 {int(llm_cooldown_remaining)}s"

    stats_row = "".join([
        _stat("📰 新闻缓冲", stats.get('news_buffer_size', 0), "#f97316"),
        _stat("👁️ 注意力缓冲", stats.get('attention_buffer_size', 0), "#a855f7"),
        _stat("📊 市场缓冲", stats.get('market_buffer_size', 0), "#14b8a6"),
        _stat("⚡ 题材共振", stats.get('resonance_history_size', 0), "#60a5fa",
              f"近 1 分钟 {stats.get('recent_resonance_count', 0)}"),
        _stat("🌐 市场共振", stats.get('market_resonance_history_size', 0), "#fb923c",
              f"近 1 分钟 {stats.get('recent_market_resonance_count', 0)}"),
    ])

    body = f'<div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px;">{stats_row}</div>'

    # ── 高共振题材（有才画）──
    if high_resonance_blocks:
        bars = ""
        for block_id, avg_score in high_resonance_blocks[:5]:
            bar_width = min(100, int(avg_score * 100))
            color = '#f87171' if avg_score >= 0.85 else ('#fb923c' if avg_score >= 0.7 else '#60a5fa')
            bars += f"""
            <div style="margin-bottom: 6px;">
                <div style="display: flex; justify-content: space-between; font-size: 11px;
                            color: #94a3b8; margin-bottom: 2px;">
                    <span style="color: #cbd5e1;">{html.escape(str(block_id))}</span>
                    <span style="color: {color}; font-weight: 600;">{avg_score:.2f}</span>
                </div>
                <div style="height: 4px; background: rgba(255,255,255,.08); border-radius: 2px;">
                    <div style="width: {bar_width}%; height: 100%; background: {color}; border-radius: 2px;"></div>
                </div>
            </div>
            """
        body += f"""
        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.06);">
            <div style="font-size: 11px; color: #f97316; font-weight: 600; margin-bottom: 8px;">🔥 高共振题材</div>
            {bars}
        </div>
        """

    # ── 共振明细，默认折叠 ──
    detail_parts = []

    if recent_resonances:
        items = ""
        for res in recent_resonances[-6:]:
            color = _RESONANCE_COLORS.get(res.resonance_type.value, '#60a5fa')
            sentiment_icon = "📈" if res.news_sentiment > 0.2 else "📉" if res.news_sentiment < -0.2 else "📊"
            attention_icon = "🔥" if res.attention_weight > 0.6 else "⚡" if res.attention_weight > 0.3 else "💤"
            ts_str = format_timestamp(res.timestamp) if res.timestamp else "-"
            items += f"""
            <div style="display: flex; align-items: center; gap: 8px; padding: 6px 8px;
                        background: rgba(255,255,255,.02); border-radius: 6px; margin-bottom: 4px;
                        border-left: 2px solid {color};">
                <div style="flex: 1; min-width: 0;">
                    <div style="font-size: 11px; color: #cbd5e1; overflow: hidden;
                                text-overflow: ellipsis; white-space: nowrap;">
                        {html.escape(str(res.block_name or res.block_id))}
                    </div>
                    <div style="font-size: 11px; color: #64748b;">{sentiment_icon} {res.news_sentiment:+.2f} {attention_icon} {res.attention_weight:.2f}</div>
                </div>
                <div style="text-align: right; flex-shrink: 0;">
                    <div style="font-size: 11px; font-weight: 600; color: {color};">{res.resonance_score:.2f}</div>
                    <div style="font-size: 11px; color: #475569;">{ts_str[-8:]}</div>
                </div>
            </div>
            """
        detail_parts.append(
            f'<div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">📋 最近共振信号</div>{items}'
        )

    resonance_list = market_resonance_summary.get('共振列表', []) or []
    if resonance_list:
        items = ""
        for res in resonance_list[:6]:
            color = _MARKET_COLORS.get('intensity', '#f97316')
            change = res.get('market_change')
            change_str = f"{change:+.1f}%" if isinstance(change, (int, float)) else str(change or 'N/A')
            items += f"""
            <div style="display: flex; align-items: center; gap: 8px; padding: 6px 8px;
                        background: rgba(255,255,255,.02); border-radius: 6px; margin-bottom: 4px;
                        border-left: 2px solid {color};">
                <div style="flex: 1; min-width: 0;">
                    <div style="font-size: 11px; color: #cbd5e1;">{html.escape(str(res.get('market_name') or res.get('market_index')))}</div>
                    <div style="font-size: 11px; color: #64748b;">{html.escape(str(res.get('narrative', '')))} {change_str}</div>
                </div>
                <div style="text-align: right; flex-shrink: 0;">
                    <div style="font-size: 11px; font-weight: 600; color: {color};">{res.get('resonance_score', 0):.2f}</div>
                    <div style="font-size: 11px; color: #475569;">{html.escape(str(res.get('stage', 'N/A')))}</div>
                </div>
            </div>
            """
        detail_parts.append(
            f'<div style="font-size: 11px; color: #64748b; margin: 10px 0 6px;">🌐 市场共振信号</div>{items}'
        )

    if detail_parts:
        body += fold(
            "共振明细",
            "".join(detail_parts),
            meta=f"{len(recent_resonances)} 条题材 · {len(resonance_list)} 条市场",
        )

    put_html(card(
        title="跨信号分析（共振检测）",
        icon="🔄",
        meta=f"LLM 层 {llm_ready}",
        body=body,
    ))
