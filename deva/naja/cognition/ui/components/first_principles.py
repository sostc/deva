"""
First Principles 组件 - 因果推理板块

展示 FirstPrinciplesMind 的因果图谱统计、因果链追踪、矛盾检测结果、
推理引擎状态、思考深度和觉醒度。
"""


def render_first_principles(ui):
    try:
        from deva.naja.cognition.analysis.first_principles_mind import (
            FirstPrinciplesMind, ThoughtLevel
        )
        mind = FirstPrinciplesMind()
    except Exception:
        return

    from pywebio.output import put_html

    # --- 获取数据 ---
    try:
        analyzer = mind.first_principles_analyzer
        causality_summary = analyzer.causality_tracker.get_causality_summary()
        contradiction_summary = analyzer.contradiction_detector.get_contradiction_summary()
        graph_stats = causality_summary.get("graph_stats", {})
        insights_summary = analyzer.get_insights_summary()
        depth = mind._thinking_depth
        awareness = mind._awareness_level
    except Exception:
        return

    # --- 思考深度映射 ---
    depth_labels = {
        ThoughtLevel.SURFACE: ("表面现象", "#94a3b8", 1),
        ThoughtLevel.PATTERN: ("模式识别", "#60a5fa", 2),
        ThoughtLevel.CAUSAL: ("因果关系", "#a855f7", 3),
        ThoughtLevel.FIRST_PRINCIPLES: ("第一性原理", "#22c55e", 4),
        ThoughtLevel.META: ("元认知", "#f59e0b", 5),
    }
    depth_label, depth_color, depth_level = depth_labels.get(
        depth, ("未知", "#94a3b8", 0)
    )
    depth_pct = int(depth_level / 5 * 100)

    # --- 觉醒度 ---
    awareness_pct = int(awareness * 100)
    if awareness >= 0.8:
        awareness_color = "#22c55e"
        awareness_label = "高度觉醒"
    elif awareness >= 0.5:
        awareness_color = "#f59e0b"
        awareness_label = "中等觉醒"
    else:
        awareness_color = "#ef4444"
        awareness_label = "低觉醒"

    # --- 矛盾类型分布 ---
    by_type = contradiction_summary.get("by_type", {})
    semantic_cnt = by_type.get("semantic", 0)
    logical_cnt = by_type.get("logical", 0)
    data_cnt = by_type.get("data", 0)
    total_contradictions = contradiction_summary.get("contradictions_found", 0)
    severe_cnt = contradiction_summary.get("severe_contradictions", 0)
    avg_severity = contradiction_summary.get("avg_severity", 0)

    # --- 洞察分布 ---
    by_insight_type = insights_summary.get("by_type", {})
    by_insight_level = insights_summary.get("by_level", {})
    total_insights = insights_summary.get("total_insights", 0)

    # === 渲染 ===

    # 头部
    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <div style="font-size: 13px; font-weight: 600; color: #a855f7;">
                🧠 因果推理（第一性原理）
            </div>
            <div style="font-size: 10px; color: #475569;">
                觉醒度: <span style="color: {awareness_color};">{awareness_pct}%</span> · 深度: <span style="color: {depth_color};">{depth_label}</span>
            </div>
        </div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
            因果图谱 × 矛盾检测 × 多层推理 → 深度认知
        </div>
    """)

    # 思考深度 + 觉醒度 进度条
    put_html(f"""
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px;">
            <div style="background: rgba(168,85,247,0.08); border: 1px solid rgba(168,85,247,0.15); padding: 8px 12px; border-radius: 8px;">
                <div style="font-size: 10px; color: #94a3b8; margin-bottom: 4px;">🎯 思考深度</div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div style="flex: 1; height: 6px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden;">
                        <div style="width: {depth_pct}%; height: 100%; background: {depth_color}; border-radius: 3px;"></div>
                    </div>
                    <div style="font-size: 11px; color: {depth_color}; font-weight: 600; white-space: nowrap;">{depth_label}</div>
                </div>
            </div>
            <div style="background: rgba(168,85,247,0.08); border: 1px solid rgba(168,85,247,0.15); padding: 8px 12px; border-radius: 8px;">
                <div style="font-size: 10px; color: #94a3b8; margin-bottom: 4px;">👁️ 觉醒度</div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div style="flex: 1; height: 6px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden;">
                        <div style="width: {awareness_pct}%; height: 100%; background: {awareness_color}; border-radius: 3px;"></div>
                    </div>
                    <div style="font-size: 11px; color: {awareness_color}; font-weight: 600; white-space: nowrap;">{awareness_label} {awareness_pct}%</div>
                </div>
            </div>
        </div>
    """)

    # 因果图谱统计卡片
    nodes = graph_stats.get("nodes", 0)
    edges = graph_stats.get("edges", 0)
    avg_degree = graph_stats.get("avg_degree", 0)
    temporal = graph_stats.get("temporal_patterns", 0)
    known_causes = causality_summary.get("known_causes", 0)
    known_effects = causality_summary.get("known_effects", 0)
    chains = causality_summary.get("chains", 0)
    knowledge_size = causality_summary.get("knowledge_size", 0)
    counterfactuals = causality_summary.get("counterfactuals", 0)

    put_html(f"""
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px; font-weight: 500;">📊 因果图谱</div>
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 12px;">
            <div style="background: rgba(96,165,250,0.1); border: 1px solid rgba(96,165,250,0.2); padding: 6px 8px; border-radius: 6px; text-align: center;">
                <div style="font-size: 15px; color: #60a5fa; font-weight: 700;">{nodes}</div>
                <div style="font-size: 9px; color: #94a3b8;">节点</div>
            </div>
            <div style="background: rgba(96,165,250,0.1); border: 1px solid rgba(96,165,250,0.2); padding: 6px 8px; border-radius: 6px; text-align: center;">
                <div style="font-size: 15px; color: #60a5fa; font-weight: 700;">{edges}</div>
                <div style="font-size: 9px; color: #94a3b8;">边</div>
            </div>
            <div style="background: rgba(96,165,250,0.1); border: 1px solid rgba(96,165,250,0.2); padding: 6px 8px; border-radius: 6px; text-align: center;">
                <div style="font-size: 15px; color: #60a5fa; font-weight: 700;">{avg_degree:.1f}</div>
                <div style="font-size: 9px; color: #94a3b8;">平均度</div>
            </div>
            <div style="background: rgba(96,165,250,0.1); border: 1px solid rgba(96,165,250,0.2); padding: 6px 8px; border-radius: 6px; text-align: center;">
                <div style="font-size: 15px; color: #60a5fa; font-weight: 700;">{temporal}</div>
                <div style="font-size: 9px; color: #94a3b8;">时序模式</div>
            </div>
        </div>
    """)

    # 因果链追踪
    put_html(f"""
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px; font-weight: 500;">🔗 因果链追踪</div>
        <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; margin-bottom: 12px;">
            <div style="background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                <div style="font-size: 14px; color: #22c55e; font-weight: 700;">{known_causes}</div>
                <div style="font-size: 9px; color: #94a3b8;">已知因</div>
            </div>
            <div style="background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                <div style="font-size: 14px; color: #22c55e; font-weight: 700;">{known_effects}</div>
                <div style="font-size: 9px; color: #94a3b8;">已知果</div>
            </div>
            <div style="background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                <div style="font-size: 14px; color: #22c55e; font-weight: 700;">{chains}</div>
                <div style="font-size: 9px; color: #94a3b8;">因果链</div>
            </div>
            <div style="background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                <div style="font-size: 14px; color: #22c55e; font-weight: 700;">{knowledge_size}</div>
                <div style="font-size: 9px; color: #94a3b8;">知识库</div>
            </div>
            <div style="background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                <div style="font-size: 14px; color: #22c55e; font-weight: 700;">{counterfactuals}</div>
                <div style="font-size: 9px; color: #94a3b8;">反事实</div>
            </div>
        </div>
    """)

    # 矛盾检测
    severity_color = "#22c55e" if avg_severity < 0.3 else ("#f59e0b" if avg_severity < 0.6 else "#ef4444")
    severe_badge = f'<span style="color: #ef4444; font-weight: 600;"> ⚠️ {severe_cnt}严重</span>' if severe_cnt > 0 else ""

    # 矛盾类型分布条
    type_total = semantic_cnt + logical_cnt + data_cnt
    if type_total > 0:
        sem_pct = int(semantic_cnt / type_total * 100)
        log_pct = int(logical_cnt / type_total * 100)
        dat_pct = 100 - sem_pct - log_pct
    else:
        sem_pct = log_pct = dat_pct = 0

    put_html(f"""
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px; font-weight: 500;">
            ⚡ 矛盾检测 <span style="font-size: 10px; color: #475569;">({total_contradictions} 个矛盾)</span>{severe_badge}
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px;">
            <div style="background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.15); padding: 8px 10px; border-radius: 6px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-size: 10px; color: #94a3b8;">叙事总数</span>
                    <span style="font-size: 13px; color: #f1f5f9; font-weight: 600;">{contradiction_summary.get('total_narratives', 0)}</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 10px; color: #94a3b8;">平均严重度</span>
                    <span style="font-size: 13px; color: {severity_color}; font-weight: 600;">{avg_severity:.2f}</span>
                </div>
            </div>
            <div style="background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.15); padding: 8px 10px; border-radius: 6px;">
                <div style="font-size: 10px; color: #94a3b8; margin-bottom: 6px;">类型分布</div>
                <div style="height: 8px; background: rgba(255,255,255,0.06); border-radius: 4px; overflow: hidden; display: flex;">
                    <div style="width: {sem_pct}%; background: #60a5fa;" title="语义矛盾 {semantic_cnt}"></div>
                    <div style="width: {log_pct}%; background: #f59e0b;" title="逻辑矛盾 {logical_cnt}"></div>
                    <div style="width: {dat_pct}%; background: #ef4444;" title="数据矛盾 {data_cnt}"></div>
                </div>
                <div style="display: flex; gap: 8px; margin-top: 4px;">
                    <span style="font-size: 9px; color: #60a5fa;">● 语义 {semantic_cnt}</span>
                    <span style="font-size: 9px; color: #f59e0b;">● 逻辑 {logical_cnt}</span>
                    <span style="font-size: 9px; color: #ef4444;">● 数据 {data_cnt}</span>
                </div>
            </div>
        </div>
    """)

    # 洞察分布
    if total_insights > 0:
        insight_types = [
            ("因果", by_insight_type.get("cause", 0), "#60a5fa"),
            ("矛盾", by_insight_type.get("contradiction", 0), "#ef4444"),
            ("机会", by_insight_type.get("opportunity", 0), "#22c55e"),
            ("风险", by_insight_type.get("risk", 0), "#f59e0b"),
            ("推理", by_insight_type.get("reasoning", 0), "#a855f7"),
            ("模式", by_insight_type.get("pattern", 0), "#14b8a6"),
        ]
        insight_level_items = [
            ("表面", by_insight_level.get("surface", 0), "#94a3b8"),
            ("模式", by_insight_level.get("pattern", 0), "#60a5fa"),
            ("因果", by_insight_level.get("causal", 0), "#a855f7"),
            ("原理", by_insight_level.get("first_principles", 0), "#22c55e"),
        ]

        type_badges = " ".join(
            f'<span style="display: inline-block; background: rgba({_hex_to_rgb(c)},0.15); color: {c}; '
            f'padding: 2px 6px; border-radius: 4px; font-size: 9px; margin-right: 2px;">'
            f'{name} {cnt}</span>'
            for name, cnt, c in insight_types if cnt > 0
        )
        level_badges = " ".join(
            f'<span style="display: inline-block; background: rgba({_hex_to_rgb(c)},0.15); color: {c}; '
            f'padding: 2px 6px; border-radius: 4px; font-size: 9px; margin-right: 2px;">'
            f'{name} {cnt}</span>'
            for name, cnt, c in insight_level_items if cnt > 0
        )

        put_html(f"""
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px; font-weight: 500;">
            💡 洞察分布 <span style="font-size: 10px; color: #475569;">({total_insights} 个)</span>
        </div>
        <div style="margin-bottom: 6px;">
            <div style="font-size: 9px; color: #64748b; margin-bottom: 3px;">按类型</div>
            {type_badges}
        </div>
        <div style="margin-bottom: 4px;">
            <div style="font-size: 9px; color: #64748b; margin-bottom: 3px;">按深度</div>
            {level_badges}
        </div>
        """)

    # 关闭容器
    put_html("</div>")


def _hex_to_rgb(hex_color: str) -> str:
    """将 #rrggbb 转为 r,g,b 字符串"""
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"
