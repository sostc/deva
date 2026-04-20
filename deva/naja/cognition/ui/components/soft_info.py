"""
Soft Info Confidence 组件 - 软信息置信度板块

展示各来源（叙事/新闻/情绪/共振）的基础置信度、
软信息基础权重、有效权重计算公式说明。
"""


def render_soft_info(ui):
    from pywebio.output import put_html

    # --- 获取数据 ---
    has_data = False
    evaluator = None
    source_confidences = None
    base_weight = None

    try:
        from deva.naja.cognition.analysis.soft_info_confidence import (
            SoftInfoConfidence, SoftInfoSource
        )
        evaluator = SoftInfoConfidence()
        source_confidences = evaluator._source_confidences
        base_weight = evaluator._base_soft_weight
        has_data = True  # 这个组件即使没有动态数据也应该显示配置信息
    except Exception:
        pass

    # --- 头部始终显示 ---
    base_weight_pct = int(base_weight * 100) if base_weight else 0
    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <div style="font-size: 13px; font-weight: 600; color: #14b8a6;">
                🎚️ 软信息置信度
            </div>
            <div style="font-size: 10px; color: #475569;">
                基础权重: <span style="color: #14b8a6; font-weight: 600;">{base_weight_pct}%</span>
            </div>
        </div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
            硬数据 = 主角 ({100 - base_weight_pct}%) · 软信息 = 调味剂 ({base_weight_pct}%) · 置信度决定影响程度
        </div>
    """)

    # --- 无数据状态 ---
    if not evaluator:
        put_html("""
        <div style="text-align: center; padding: 24px 16px;">
            <div style="font-size: 32px; margin-bottom: 12px;">🎚️</div>
            <div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">置信度评估器未就绪</div>
            <div style="font-size: 10px; color: #475569;">等待系统初始化，将在此展示软信息置信度配置</div>
        </div>
        """)
        put_html('</div>')
        return

    # --- 有数据时渲染内容 ---
    # 权重公式说明
    put_html(f"""
        <div style="
            background: rgba(20,184,166,0.06);
            border: 1px solid rgba(20,184,166,0.12);
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 14px;
        ">
            <div style="font-size: 10px; color: #94a3b8; margin-bottom: 4px;">📐 有效权重公式</div>
            <div style="font-size: 12px; color: #f1f5f9; font-family: 'SF Mono', monospace;">
                effective_weight = base_weight ({base_weight}) × confidence
            </div>
            <div style="font-size: 9px; color: #64748b; margin-top: 3px;">
                置信度越高 → 软信息影响越大 · 置信度越低 → 软信息影响越小
            </div>
        </div>
    """)

    # 各来源置信度卡片
    try:
        from deva.naja.cognition.analysis.soft_info_confidence import SoftInfoSource
        source_config = {
            SoftInfoSource.NARRATIVE_TRACKER.value: {
                "name": "叙事追踪",
                "icon": "📖",
                "color": "#a855f7",
                "desc": "叙事稳定性 × 来源可靠性",
            },
            SoftInfoSource.NEWS_MIND.value: {
                "name": "新闻舆情",
                "icon": "📰",
                "color": "#60a5fa",
                "desc": "新闻质量 × 一致性",
            },
            SoftInfoSource.MARKET_SENTIMENT.value: {
                "name": "市场情绪",
                "icon": "📊",
                "color": "#22c55e",
                "desc": "情绪强度 × 持续性",
            },
            SoftInfoSource.CROSS_SIGNAL.value: {
                "name": "跨信号共振",
                "icon": "🔄",
                "color": "#f97316",
                "desc": "多源一致性 × 时间窗口",
            },
        }
    except Exception:
        # 如果无法导入枚举，使用默认配置
        source_config = {}

    # 如果没有配置，使用通用显示
    if not source_config and source_confidences:
        for source_key in source_confidences.keys():
            source_config[source_key] = {
                "name": source_key,
                "icon": "📌",
                "color": "#94a3b8",
                "desc": "",
            }

    cards_html = ""
    if source_confidences:
        for source_key, conf_value in source_confidences.items():
            cfg = source_config.get(source_key, {
                "name": source_key, "icon": "📌", "color": "#94a3b8", "desc": ""
            })
            conf_pct = int(conf_value * 100)
            effective = base_weight * conf_value if base_weight else 0
            effective_pct = f"{effective:.1%}"

            # 置信度颜色
            if conf_value >= 0.65:
                bar_color = "#22c55e"
            elif conf_value >= 0.5:
                bar_color = "#f59e0b"
            else:
                bar_color = "#ef4444"

            cards_html += f"""
            <div style="
                background: {cfg['color']}10;
                border: 1px solid {cfg['color']}20;
                padding: 10px 12px;
                border-radius: 8px;
            ">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <div style="font-size: 11px; color: {cfg['color']}; font-weight: 600;">
                        {cfg['icon']} {cfg['name']}
                    </div>
                    <div style="font-size: 12px; color: #f1f5f9; font-weight: 700;">{conf_pct}%</div>
                </div>
                <div style="height: 6px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden; margin-bottom: 6px;">
                    <div style="width: {conf_pct}%; height: 100%; background: {bar_color}; border-radius: 3px;"></div>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-size: 9px; color: #64748b;">{cfg['desc']}</div>
                    <div style="font-size: 9px; color: #94a3b8;">有效权重 <span style="color: {cfg['color']};">{effective_pct}</span></div>
                </div>
            </div>
            """

    if cards_html:
        put_html(f"""
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px;">
                {cards_html}
            </div>
        """)

    # 矛盾处理规则
    put_html("""
        <div style="
            background: rgba(239,68,68,0.06);
            border: 1px solid rgba(239,68,68,0.12);
            border-radius: 8px;
            padding: 8px 12px;
        ">
            <div style="font-size: 10px; color: #94a3b8; margin-bottom: 4px;">⚠️ 硬软矛盾处理</div>
            <div style="font-size: 10px; color: #f87171;">
                当硬数据（量价）与软信息（叙事/新闻）方向矛盾时 → 以硬数据为主，软信息权重自动衰减
            </div>
        </div>
    """)

    # 关闭容器
    put_html('</div>')
