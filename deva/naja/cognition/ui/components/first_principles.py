"""First Principles 组件 —— 因果推理（第一性原理）

展示 FirstPrinciplesMind 的因果图谱统计、因果链追踪、矛盾检测结果、
推理引擎状态、思考深度和觉醒度。

2026-10-19 重排：空态压成一行；删掉「因果图谱 × 矛盾检测 × 多层推理 →
深度认知」这类模块说明行；8px 标签统一抬到 11px；洞察分布默认折叠。
"""

from pywebio.output import put_html

from .layout import card, empty_line, fold


def _tiles(items, cols: int = 4) -> str:
    cells = "".join(
        f'<div style="background: {color}12; border: 1px solid {color}2e; padding: 6px 8px;'
        f'border-radius: 6px; text-align: center;">'
        f'<div style="font-size: 14px; color: {color}; font-weight: 700;">{value}</div>'
        f'<div style="font-size: 11px; color: #94a3b8;">{label}</div></div>'
        for label, value, color in items
    )
    return f'<div style="display: grid; grid-template-columns: repeat({cols}, 1fr); gap: 6px;">{cells}</div>'


def _bar(label: str, pct: int, color: str, text: str) -> str:
    return f"""
    <div style="background: {color}0f; border: 1px solid {color}26; padding: 8px 12px; border-radius: 8px;">
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 5px;">{label}</div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <div style="flex: 1; height: 6px; background: rgba(255,255,255,.06); border-radius: 3px; overflow: hidden;">
                <div style="width: {pct}%; height: 100%; background: {color}; border-radius: 3px;"></div>
            </div>
            <div style="font-size: 11px; color: {color}; font-weight: 600; white-space: nowrap;">{text}</div>
        </div>
    </div>
    """


def render_first_principles(ui):
    has_data = False
    mind = None
    causality_summary = None
    contradiction_summary = None
    graph_stats = None
    insights_summary = None
    depth = None
    awareness = None

    try:
        from deva.naja.cognition.analysis.first_principles_mind import FirstPrinciplesMind
        mind = FirstPrinciplesMind()
    except Exception:
        pass

    if mind:
        try:
            analyzer = mind.first_principles_analyzer
            causality_summary = analyzer.causality_tracker.get_causality_summary()
            contradiction_summary = analyzer.contradiction_detector.get_contradiction_summary()
            graph_stats = causality_summary.get("graph_stats", {})
            insights_summary = analyzer.get_insights_summary()
            depth = mind._thinking_depth
            awareness = mind._awareness_level

            nodes = graph_stats.get("nodes", 0)
            contradictions = contradiction_summary.get("contradictions_found", 0)
            total_insights = insights_summary.get("total_insights", 0)
            has_data = (nodes > 0 or contradictions > 0 or total_insights > 0)
        except Exception:
            pass

    # ── 头部指标 ──
    depth_label, depth_color, depth_level = "未知", "#94a3b8", 0
    if depth:
        try:
            from deva.naja.cognition.analysis.first_principles_mind import ThoughtLevel
            depth_labels = {
                ThoughtLevel.SURFACE: ("表面现象", "#94a3b8", 1),
                ThoughtLevel.PATTERN: ("模式识别", "#60a5fa", 2),
                ThoughtLevel.CAUSAL: ("因果关系", "#a855f7", 3),
                ThoughtLevel.FIRST_PRINCIPLES: ("第一性原理", "#22c55e", 4),
                ThoughtLevel.META: ("元认知", "#f59e0b", 5),
            }
            depth_label, depth_color, depth_level = depth_labels.get(depth, ("未知", "#94a3b8", 0))
        except Exception:
            pass

    awareness_pct, awareness_color, awareness_label = 0, "#94a3b8", "未就绪"
    if awareness:
        awareness_pct = int(awareness * 100)
        if awareness >= 0.8:
            awareness_color, awareness_label = "#22c55e", "高度觉醒"
        elif awareness >= 0.5:
            awareness_color, awareness_label = "#f59e0b", "中等觉醒"
        else:
            awareness_color, awareness_label = "#ef4444", "低觉醒"

    meta = (f'觉醒度 <b style="color: {awareness_color};">{awareness_pct}%</b> · '
            f'深度 <b style="color: {depth_color};">{depth_label}</b>')

    if not mind:
        put_html(card(title="因果推理（第一性原理）", icon="🧠", meta=meta,
                      body=empty_line("推理引擎未就绪", "等待系统初始化")))
        return

    if not has_data:
        put_html(card(title="因果推理（第一性原理）", icon="🧠", meta=meta,
                      body=empty_line("正在构建认知模型", "系统在积累市场因果关系，有结论后会出现在这里")))
        return

    depth_pct = int(depth_level / 5 * 100)
    body = f"""
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
        {_bar("🎯 思考深度", depth_pct, depth_color, depth_label)}
        {_bar("👁️ 觉醒度", awareness_pct, awareness_color, f"{awareness_label} {awareness_pct}%")}
    </div>
    """

    nodes = graph_stats.get("nodes", 0)
    edges = graph_stats.get("edges", 0)
    avg_degree = graph_stats.get("avg_degree", 0)
    temporal = graph_stats.get("temporal_patterns", 0)
    known_causes = causality_summary.get("known_causes", 0)
    known_effects = causality_summary.get("known_effects", 0)
    chains = causality_summary.get("chains", 0)
    knowledge_size = causality_summary.get("knowledge_size", 0)
    counterfactuals = causality_summary.get("counterfactuals", 0)

    body += f"""
    <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.06);">
        <div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">📊 因果图谱</div>
        {_tiles([("节点", nodes, "#60a5fa"), ("边", edges, "#60a5fa"),
                 ("平均度", f"{avg_degree:.1f}", "#60a5fa"), ("时序模式", temporal, "#60a5fa")])}
    </div>
    """

    detail = f"""
    <div>
        <div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">🔗 因果链追踪</div>
        {_tiles([("已知因", known_causes, "#22c55e"), ("已知果", known_effects, "#22c55e"),
                 ("因果链", chains, "#22c55e"), ("知识库", knowledge_size, "#22c55e"),
                 ("反事实", counterfactuals, "#22c55e")], cols=5)}
    </div>
    """

    # ── 矛盾检测 ──
    by_type = contradiction_summary.get("by_type", {}) or {}
    semantic_cnt = by_type.get("semantic", 0)
    logical_cnt = by_type.get("logical", 0)
    data_cnt = by_type.get("data", 0)
    total_contradictions = contradiction_summary.get("contradictions_found", 0)
    severe_cnt = contradiction_summary.get("severe_contradictions", 0)
    avg_severity = contradiction_summary.get("avg_severity", 0)
    severity_color = "#22c55e" if avg_severity < 0.3 else ("#f59e0b" if avg_severity < 0.6 else "#ef4444")
    severe_badge = (f'<span style="color: #ef4444;"> · {severe_cnt} 严重</span>' if severe_cnt > 0 else "")

    type_total = semantic_cnt + logical_cnt + data_cnt
    if type_total > 0:
        sem_pct = int(semantic_cnt / type_total * 100)
        log_pct = int(logical_cnt / type_total * 100)
        dat_pct = 100 - sem_pct - log_pct
    else:
        sem_pct = log_pct = dat_pct = 0

    detail += f"""
    <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.06);">
        <div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">
            ⚡ 矛盾检测 <span style="color: #475569;">({total_contradictions} 个)</span>{severe_badge}
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
            <div style="background: rgba(239,68,68,.06); border: 1px solid rgba(239,68,68,.15);
                        padding: 8px 10px; border-radius: 6px;">
                <div style="display: flex; justify-content: space-between; font-size: 11px;
                            color: #94a3b8; margin-bottom: 5px;">
                    <span>叙事总数</span>
                    <span style="color: #e2e8f0; font-weight: 600;">{contradiction_summary.get('total_narratives', 0)}</span>
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8;">
                    <span>平均严重度</span>
                    <span style="color: {severity_color}; font-weight: 600;">{avg_severity:.2f}</span>
                </div>
            </div>
            <div style="background: rgba(239,68,68,.06); border: 1px solid rgba(239,68,68,.15);
                        padding: 8px 10px; border-radius: 6px;">
                <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px;">类型分布</div>
                <div style="height: 7px; background: rgba(255,255,255,.06); border-radius: 4px;
                            overflow: hidden; display: flex;">
                    <div style="width: {sem_pct}%; background: #60a5fa;"></div>
                    <div style="width: {log_pct}%; background: #f59e0b;"></div>
                    <div style="width: {dat_pct}%; background: #ef4444;"></div>
                </div>
                <div style="display: flex; gap: 8px; margin-top: 5px; font-size: 11px;">
                    <span style="color: #60a5fa;">● 语义 {semantic_cnt}</span>
                    <span style="color: #f59e0b;">● 逻辑 {logical_cnt}</span>
                    <span style="color: #ef4444;">● 数据 {data_cnt}</span>
                </div>
            </div>
        </div>
    </div>
    """

    # ── 洞察分布：折叠 ──
    total_insights = insights_summary.get("total_insights", 0)
    if total_insights > 0:
        by_insight_type = insights_summary.get("by_type", {}) or {}
        by_insight_level = insights_summary.get("by_level", {}) or {}
        type_items = [
            ("因果", by_insight_type.get("cause", 0), "#60a5fa"),
            ("矛盾", by_insight_type.get("contradiction", 0), "#ef4444"),
            ("机会", by_insight_type.get("opportunity", 0), "#22c55e"),
            ("风险", by_insight_type.get("risk", 0), "#f59e0b"),
            ("推理", by_insight_type.get("reasoning", 0), "#a855f7"),
            ("模式", by_insight_type.get("pattern", 0), "#14b8a6"),
        ]
        level_items = [
            ("表面", by_insight_level.get("surface", 0), "#94a3b8"),
            ("模式", by_insight_level.get("pattern", 0), "#60a5fa"),
            ("因果", by_insight_level.get("causal", 0), "#a855f7"),
            ("原理", by_insight_level.get("first_principles", 0), "#22c55e"),
        ]
        type_badges = " ".join(
            f'<span class="cog-pill" style="background: {c}25; color: {c};">{name} {cnt}</span>'
            for name, cnt, c in type_items if cnt > 0
        ) or '<span style="color:#64748b;font-size:11px;">暂无</span>'
        level_badges = " ".join(
            f'<span class="cog-pill" style="background: {c}25; color: {c};">{name} {cnt}</span>'
            for name, cnt, c in level_items if cnt > 0
        ) or '<span style="color:#64748b;font-size:11px;">暂无</span>'

        body += fold(
            f"洞察分布 · {total_insights} 条",
            f"""
            <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">按类型</div>
            <div style="line-height: 2;">{type_badges}</div>
            <div style="font-size: 11px; color: #64748b; margin: 8px 0 4px;">按深度</div>
            <div style="line-height: 2;">{level_badges}</div>
            """,
        )

    body += fold(
        "因果链与矛盾检测",
        detail,
        meta=f"{chains} 条链 · {total_contradictions} 个矛盾",
    )

    put_html(card(title="因果推理（第一性原理）", icon="🧠", meta=meta, body=body))
