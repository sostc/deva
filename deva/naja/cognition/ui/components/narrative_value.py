"""
Narrative Value 组件 - 叙事价值发现板块

展示 OPPORTUNITY_TYPES 供需映射表（token供给不足→扩产机会等）、
当前检测到的供需问题和投资机会、受益标的列表、RESOLVERS 解决者进展。
"""


def render_narrative_value(ui):
    from pywebio.output import put_html

    # --- 获取 NarrativeTracker ---
    try:
        tracker = ui.engine._news_mind._narrative_tracker
    except Exception:
        return

    try:
        from deva.naja.cognition.narrative.tracker import (
            OPPORTUNITY_TYPES, RESOLVERS
        )
        po_summary = tracker.get_problem_opportunity_summary()
        vm_summary = tracker.get_value_market_summary()
    except Exception:
        return

    # --- 解析数据 ---
    problems = po_summary.get("problems", [])
    opportunities = po_summary.get("opportunities", [])
    resolvers = po_summary.get("resolvers", [])
    recommendation = po_summary.get("recommendation", "WATCH")

    value_score = vm_summary.get("value_score", 0)
    market_score = vm_summary.get("market_narrative_score", 0)
    vm_reason = vm_summary.get("reason", "")
    vm_recommendation = vm_summary.get("recommendation", "WATCH")
    signals = vm_summary.get("signals", [])

    # 推荐颜色
    rec_config = {
        "BUY": ("#22c55e", "🟢"),
        "WATCH": ("#f59e0b", "🟡"),
        "HOLD": ("#3b82f6", "🔵"),
        "SELL": ("#ef4444", "🔴"),
        "AVOID": ("#ef4444", "🔴"),
    }
    rec_color, rec_icon = rec_config.get(vm_recommendation, ("#94a3b8", "⚪"))

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
            <div style="font-size: 13px; font-weight: 600; color: #22c55e;">
                💎 叙事价值发现
            </div>
            <div style="font-size: 10px; color: #475569;">
                推荐: <span style="color: {rec_color}; font-weight: 600;">{rec_icon} {vm_recommendation}</span>
            </div>
        </div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
            供需问题 → 投资机会 → 受益标的 → 解决者追踪
        </div>
    """)

    # 价值/市场双评分
    value_pct = min(int(value_score * 100), 100) if value_score else 0
    market_pct = min(int(market_score * 100), 100) if market_score else 0
    value_color = "#22c55e" if value_score >= 0.6 else ("#f59e0b" if value_score >= 0.3 else "#94a3b8")
    market_color = "#3b82f6" if market_score >= 0.6 else ("#f59e0b" if market_score >= 0.3 else "#94a3b8")

    put_html(f"""
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px;">
            <div style="background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.15); padding: 8px 12px; border-radius: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <span style="font-size: 10px; color: #94a3b8;">💎 供需价值</span>
                    <span style="font-size: 14px; color: {value_color}; font-weight: 700;">{value_pct}%</span>
                </div>
                <div style="height: 5px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden;">
                    <div style="width: {value_pct}%; height: 100%; background: {value_color}; border-radius: 3px;"></div>
                </div>
                <div style="font-size: 9px; color: #64748b; margin-top: 3px;">Dynamics - 主动价值发现</div>
            </div>
            <div style="background: rgba(59,130,246,0.08); border: 1px solid rgba(59,130,246,0.15); padding: 8px 12px; border-radius: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <span style="font-size: 10px; color: #94a3b8;">📊 市场叙事</span>
                    <span style="font-size: 14px; color: {market_color}; font-weight: 700;">{market_pct}%</span>
                </div>
                <div style="height: 5px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden;">
                    <div style="width: {market_pct}%; height: 100%; background: {market_color}; border-radius: 3px;"></div>
                </div>
                <div style="font-size: 9px; color: #64748b; margin-top: 3px;">Sentiment - 市场情绪参考</div>
            </div>
        </div>
    """)

    # 原因说明
    if vm_reason:
        put_html(f"""
        <div style="
            background: rgba(34,197,94,0.04);
            border-left: 3px solid rgba(34,197,94,0.3);
            padding: 6px 10px;
            margin-bottom: 14px;
            border-radius: 0 6px 6px 0;
        ">
            <div style="font-size: 10px; color: #86efac;">{vm_reason}</div>
        </div>
        """)

    # 当前检测到的供需问题 & 机会
    if problems or opportunities:
        items_html = ""
        for opp in opportunities:
            cat = opp.get("category", "?")
            opp_name = opp.get("opportunity", "?")
            beneficiaries = opp.get("beneficiaries", [])
            desc = opp.get("description", "")
            ben_badges = " ".join(
                f'<span style="display: inline-block; background: rgba(34,197,94,0.15); color: #22c55e; '
                f'padding: 1px 5px; border-radius: 3px; font-size: 9px; margin: 1px;">{b}</span>'
                for b in beneficiaries[:6]
            )
            items_html += f"""
            <div style="padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.04);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <span style="font-size: 10px; color: #f59e0b; font-weight: 600;">⚡ {cat}</span>
                    <span style="font-size: 10px; color: #22c55e;">→ {opp_name}</span>
                </div>
                <div style="font-size: 9px; color: #64748b; margin-bottom: 4px;">{desc}</div>
                <div>{ben_badges}</div>
            </div>
            """

        if items_html:
            put_html(f"""
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px; font-weight: 500;">
                🎯 活跃供需机会 <span style="font-size: 10px; color: #475569;">({len(opportunities)} 个)</span>
            </div>
            <div style="
                background: rgba(34,197,94,0.04);
                border: 1px solid rgba(34,197,94,0.1);
                border-radius: 8px;
                overflow: hidden;
                margin-bottom: 12px;
            ">
                {items_html}
            </div>
            """)

    # OPPORTUNITY_TYPES 全景映射表（折叠式）
    mapping_rows = ""
    for problem_type, info in OPPORTUNITY_TYPES.items():
        is_active = any(p.get("category") == problem_type for p in problems)
        active_dot = '<span style="color: #22c55e;">●</span>' if is_active else '<span style="color: #334155;">○</span>'
        bens = ", ".join(info.get("beneficiaries", [])[:3])
        mapping_rows += f"""
        <div style="display: grid; grid-template-columns: 20px 2fr 1.5fr 2fr; gap: 4px; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.03); align-items: center;">
            <div style="font-size: 10px; text-align: center;">{active_dot}</div>
            <div style="font-size: 9px; color: #f1f5f9;">{problem_type}</div>
            <div style="font-size: 9px; color: #22c55e;">{info.get('opportunity', '')}</div>
            <div style="font-size: 9px; color: #64748b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{bens}</div>
        </div>
        """

    put_html(f"""
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px; font-weight: 500;">📋 供需→机会 映射表</div>
        <div style="
            background: rgba(255,255,255,0.02);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 8px;
            padding: 6px 10px;
            margin-bottom: 12px;
        ">
            <div style="display: grid; grid-template-columns: 20px 2fr 1.5fr 2fr; gap: 4px; padding-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.08);">
                <div style="font-size: 8px; color: #475569;"></div>
                <div style="font-size: 8px; color: #475569;">供需问题</div>
                <div style="font-size: 8px; color: #475569;">投资机会</div>
                <div style="font-size: 8px; color: #475569;">受益标的</div>
            </div>
            {mapping_rows}
        </div>
    """)

    # RESOLVERS 解决者追踪
    if resolvers or RESOLVERS:
        resolver_html = ""
        for name, info in RESOLVERS.items():
            problem = info.get("problem", "")
            r_list = info.get("resolvers", [])
            progress = info.get("progress", {})
            opportunity = info.get("opportunity", "")

            # 是否有活跃解决者
            is_active = any(r.get("name") == name for r in resolvers)
            border_color = "rgba(34,197,94,0.2)" if is_active else "rgba(255,255,255,0.06)"

            progress_badges = " ".join(
                f'<span style="font-size: 8px; color: #94a3b8;">{k}: <span style="color: #f59e0b;">{v}</span></span>'
                for k, v in progress.items()
            )

            resolver_html += f"""
            <div style="background: rgba(255,255,255,0.02); border: 1px solid {border_color}; padding: 6px 8px; border-radius: 6px;">
                <div style="font-size: 10px; color: #f1f5f9; font-weight: 600; margin-bottom: 2px;">{name}</div>
                <div style="font-size: 9px; color: #64748b; margin-bottom: 3px;">🔧 {problem} → {opportunity}</div>
                <div style="display: flex; flex-wrap: wrap; gap: 6px;">{progress_badges}</div>
            </div>
            """

        put_html(f"""
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px; font-weight: 500;">🔧 解决者追踪</div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">
            {resolver_html}
        </div>
        """)

    # 关闭容器
    put_html("</div>")
