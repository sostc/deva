"""Soft Info Confidence 组件 —— 软信息置信度

展示各来源（叙事/新闻/情绪/共振）的基础置信度、软信息基础权重、有效权重公式。

2026-10-19 重排：公式与矛盾处理规则收进折叠块；删掉「硬数据 = 主角 (70%) ·
软信息 = 调味剂 (30%)」这类说明行（数值已在 header meta 上）；字号统一 11px。
"""

import html

from pywebio.output import put_html

from .layout import card, empty_line, fold


def _source_card(name: str, icon: str, color: str, desc: str, conf_value: float, base_weight) -> str:
    conf_pct = int(conf_value * 100)
    effective = base_weight * conf_value if base_weight else 0
    bar_color = "#22c55e" if conf_value >= 0.65 else ("#f59e0b" if conf_value >= 0.5 else "#ef4444")
    return f"""
    <div style="background: {color}10; border: 1px solid {color}26; padding: 9px 11px; border-radius: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px;">
            <div style="font-size: 11px; color: {color}; font-weight: 600;">{icon} {html.escape(name)}</div>
            <div style="font-size: 13px; color: #e2e8f0; font-weight: 700;">{conf_pct}%</div>
        </div>
        <div style="height: 5px; background: rgba(255,255,255,.06); border-radius: 3px;
                    overflow: hidden; margin-bottom: 5px;">
            <div style="width: {conf_pct}%; height: 100%; background: {bar_color}; border-radius: 3px;"></div>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 11px;">
            <span style="color: #64748b;">{html.escape(desc)}</span>
            <span style="color: #94a3b8;">有效 <span style="color: {color};">{effective:.1%}</span></span>
        </div>
    </div>
    """


def render_soft_info(ui):
    evaluator = None
    source_confidences = None
    base_weight = None

    try:
        from deva.naja.cognition.analysis.soft_info_confidence import SoftInfoConfidence
        evaluator = SoftInfoConfidence()
        source_confidences = evaluator._source_confidences
        base_weight = evaluator._base_soft_weight
    except Exception:
        pass

    base_weight_pct = int(base_weight * 100) if base_weight else 0
    meta = f'软信息基础权重 <b style="color: #14b8a6;">{base_weight_pct}%</b>'

    if not evaluator:
        put_html(card(title="软信息置信度", icon="🎚️", meta=meta,
                      body=empty_line("置信度评估器未就绪", "等待系统初始化")))
        return

    try:
        from deva.naja.cognition.analysis.soft_info_confidence import SoftInfoSource
        source_config = {
            SoftInfoSource.NARRATIVE_TRACKER.value: ("叙事追踪", "📖", "#a855f7", "叙事稳定性 × 来源可靠性"),
            SoftInfoSource.NEWS_MIND.value: ("新闻舆情", "📰", "#60a5fa", "新闻质量 × 一致性"),
            SoftInfoSource.MARKET_SENTIMENT.value: ("市场情绪", "📊", "#22c55e", "情绪强度 × 持续性"),
            SoftInfoSource.CROSS_SIGNAL.value: ("跨信号共振", "🔄", "#f97316", "多源一致性 × 时间窗口"),
        }
    except Exception:
        source_config = {}

    if not source_config and source_confidences:
        source_config = {
            key: (key, "📌", "#94a3b8", "")
            for key in source_confidences.keys()
        }

    cards = ""
    for source_key, conf_value in (source_confidences or {}).items():
        name, icon, color, desc = source_config.get(
            source_key, (source_key, "📌", "#94a3b8", "")
        )
        cards += _source_card(name, icon, color, desc, conf_value, base_weight)

    body = f'<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">{cards}</div>' if cards \
        else empty_line("暂无来源置信度")

    body += fold(
        "权重公式与硬软矛盾规则",
        f"""
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px;">📐 有效权重</div>
        <div style="font-family: 'SF Mono', monospace; font-size: 12px; color: #e2e8f0;
                    background: rgba(20,184,166,.06); border: 1px solid rgba(20,184,166,.12);
                    border-radius: 6px; padding: 8px 10px;">
            effective_weight = base_weight ({base_weight}) × confidence
        </div>
        <div style="font-size: 11px; color: #64748b; margin: 6px 0 12px;">
            置信度越高 → 软信息影响越大
        </div>
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">⚠️ 硬软矛盾处理</div>
        <div style="font-size: 11px; color: #f87171; line-height: 1.6;">
            当硬数据（量价）与软信息（叙事/新闻）方向矛盾时 → 以硬数据为主，软信息权重自动衰减
        </div>
        """,
        meta="只读配置",
    )

    put_html(card(title="软信息置信度", icon="🎚️", meta=meta, body=body))
